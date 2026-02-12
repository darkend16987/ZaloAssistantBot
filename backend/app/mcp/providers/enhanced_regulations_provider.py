# app/mcp/providers/enhanced_regulations_provider.py
"""
Enhanced Regulations Provider
=============================
Provider kết hợp 3 chiến lược retrieval:

1. Entity lookup (langextract): Tra cứu nhanh từ entities đã trích xuất offline.
   Không cần LLM call, chỉ matching trên structured data.
   → Tốt cho câu hỏi cụ thể: "thử việc có tính phép không?"

2. Tree reasoning (PageIndex): Dùng 1 LLM call để navigate tree structure
   và tìm section phù hợp nhất.
   → Tốt cho câu hỏi phức tạp cần context rộng.

3. Legacy keyword (fallback): Dùng RegulationsProvider hiện tại.
   → Backup khi 2 phương pháp trên chưa sẵn sàng.

Flow:
    User query → entity lookup (instant) + tree reasoning (1 LLM call) + legacy
                 ↓
                 Merge & deduplicate → top_k chunks → return

Backward compatible: nếu chưa có pre-computed indexes thì tự động
fall back hoàn toàn về RegulationsProvider legacy.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from app.mcp.core.base_provider import ProviderConfig, ProviderStatus
from app.mcp.providers.base_knowledge_provider import (
    BaseKnowledgeProvider,
    KnowledgeChunk,
    RetrievalResult,
    RetrievalStrategy,
)
from app.mcp.providers.regulations_provider import RegulationsProvider

logger = logging.getLogger(__name__)


class EnhancedRegulationsProvider(BaseKnowledgeProvider):
    """
    Enhanced knowledge provider combining entity lookup + tree reasoning + legacy search.

    Auto-falls back to legacy RegulationsProvider if pre-computed indexes don't exist.
    This makes it safe to deploy without running the offline pipeline first.
    """

    # Paths to pre-computed data
    INDEXED_DIR = Path(__file__).parent.parent / "knowledge" / "indexed"
    EXTRACTED_DIR = Path(__file__).parent.parent / "knowledge" / "extracted"

    def __init__(
        self,
        knowledge_path: Optional[Path] = None,
        config: Optional[ProviderConfig] = None
    ):
        super().__init__(
            config or ProviderConfig(name="regulations"),
            strategy=RetrievalStrategy.HYBRID
        )
        # Legacy provider for backward compatibility
        self._legacy = RegulationsProvider(knowledge_path=knowledge_path, config=config)

        # Enhanced data stores
        self._tree_indexes: Dict[str, dict] = {}     # doc_id -> tree JSON
        self._entities: Dict[str, list] = {}          # doc_id -> [entity dicts]
        self._has_trees = False
        self._has_entities = False

    @property
    def name(self) -> str:
        return "regulations"

    # ===================================================================
    # Initialization
    # ===================================================================

    async def initialize(self) -> None:
        """Initialize legacy provider + load pre-computed indexes if available."""
        # Always initialize legacy (guaranteed to work)
        await self._legacy.initialize()

        # Try loading pre-computed data
        self._load_tree_indexes()
        self._load_entities()

        enhancement_parts = []
        if self._has_trees:
            tree_nodes = sum(
                self._count_nodes(t.get("structure", []))
                for t in self._tree_indexes.values()
            )
            enhancement_parts.append(f"{len(self._tree_indexes)} trees ({tree_nodes} nodes)")
        if self._has_entities:
            entity_count = sum(len(e) for e in self._entities.values())
            enhancement_parts.append(f"{entity_count} entities")

        if enhancement_parts:
            logger.info(f"Enhanced mode active: {', '.join(enhancement_parts)}")
        else:
            logger.info("Enhanced indexes not found, using legacy mode only")

        self._status = self._legacy._status

    def _load_tree_indexes(self):
        """Load pre-computed PageIndex trees from disk."""
        if not self.INDEXED_DIR.exists():
            return
        for tree_path in self.INDEXED_DIR.glob("*_tree.json"):
            doc_id = tree_path.stem.replace("_tree", "")
            try:
                with open(tree_path, "r", encoding="utf-8") as f:
                    self._tree_indexes[doc_id] = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load tree {tree_path}: {e}")
        self._has_trees = bool(self._tree_indexes)

    def _load_entities(self):
        """Load pre-computed langextract entities from disk."""
        entities_path = self.EXTRACTED_DIR / "entities.json"
        if not entities_path.exists():
            return
        try:
            with open(entities_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for doc_id, doc_data in data.items():
                entities = doc_data.get("entities", [])
                if entities:
                    self._entities[doc_id] = entities
        except Exception as e:
            logger.warning(f"Failed to load entities: {e}")
        self._has_entities = bool(self._entities)

    # ===================================================================
    # Main Retrieval
    # ===================================================================

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """
        3-layer hybrid retrieval.

        Returns chunks scored and merged from all available strategies.
        """
        # If no enhanced data, use legacy directly
        if not self._has_trees and not self._has_entities:
            return await self._legacy.retrieve(query, top_k, filters)

        all_chunks: List[KnowledgeChunk] = []

        # Strategy 1: Entity lookup (instant, no LLM)
        if self._has_entities:
            entity_chunks = self._entity_lookup(query, filters)
            all_chunks.extend(entity_chunks)

        # Strategy 2: Tree reasoning (1 LLM call)
        if self._has_trees:
            try:
                tree_chunks = await self._tree_retrieve(query, filters)
                all_chunks.extend(tree_chunks)
            except Exception as e:
                logger.warning(f"Tree retrieval failed, skipping: {e}")

        # Strategy 3: Legacy keyword (always available)
        legacy_result = await self._legacy.retrieve(query, top_k=2, filters=filters)
        for chunk in legacy_result.chunks:
            # Lower score for legacy to prefer enhanced results
            # But only if we actually got enhanced results
            if all_chunks:
                chunk.score *= 0.7
            all_chunks.append(chunk)

        # Deduplicate by content similarity
        all_chunks = self._deduplicate_chunks(all_chunks)

        # Sort by score and limit
        all_chunks.sort(key=lambda c: c.score, reverse=True)

        return RetrievalResult(
            chunks=all_chunks[:top_k],
            query=query,
            total_found=len(all_chunks)
        )

    # ===================================================================
    # Strategy 1: Entity Lookup (langextract)
    # ===================================================================

    def _entity_lookup(
        self, query: str, filters: Optional[Dict] = None
    ) -> List[KnowledgeChunk]:
        """
        Fast entity-based lookup.

        Matches query against pre-extracted structured entities.
        No LLM call needed - pure text matching on attributes.
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())
        chunks = []

        for doc_id, entities in self._entities.items():
            if filters and filters.get("doc_id") and filters["doc_id"] != doc_id:
                continue

            for entity in entities:
                score = self._score_entity(query_lower, query_words, entity)
                if score > 0.3:
                    content = self._format_entity_as_context(entity)
                    chunks.append(KnowledgeChunk(
                        content=content,
                        source=f"Quy định (structured) - {entity.get('class', 'Rule')}",
                        metadata={
                            "doc_id": doc_id,
                            "entity_class": entity.get("class", ""),
                            "rule_type": entity.get("attributes", {}).get("rule_type", ""),
                            "source_type": "entity_lookup",
                        },
                        score=score
                    ))

        return chunks

    def _score_entity(
        self, query: str, query_words: set, entity: dict
    ) -> float:
        """Score relevance of an entity to the query."""
        score = 0.0

        # Match entity text
        entity_text = entity.get("text", "").lower()
        entity_words = set(entity_text.split())
        text_overlap = len(query_words & entity_words)
        if text_overlap:
            score += min(text_overlap / max(len(query_words), 1), 1.0) * 0.3

        # Match attribute values
        attrs = entity.get("attributes", {})
        attr_match_count = 0
        for key, value in attrs.items():
            value_lower = str(value).lower()
            if any(w in value_lower for w in query_words):
                attr_match_count += 1
            if any(w in key.lower() for w in query_words):
                attr_match_count += 1
        if attr_match_count:
            score += min(attr_match_count * 0.15, 0.4)

        # Bonus for specific rule_type matching common Vietnamese keywords
        rule_type = attrs.get("rule_type", "").lower()
        keyword_bonuses = {
            "phép": ["leave", "annual_leave", "prorated_leave", "leave_accrual",
                      "leave_credit", "leave_advance"],
            "thử việc": ["probation"],
            "chính thức": ["probation"],
            "thai sản": ["maternity", "paternity"],
            "kết hôn": ["special_leave", "wedding"],
            "giờ làm": ["working_hours", "working_days"],
            "đi muộn": ["lateness", "late_threshold"],
            "kỷ luật": ["disciplinary", "termination"],
            "vay": ["loan", "financial"],
        }
        for keyword, rule_types in keyword_bonuses.items():
            if keyword in query:
                if any(rt in rule_type for rt in rule_types):
                    score += 0.3

        return min(score, 1.0)

    def _format_entity_as_context(self, entity: dict) -> str:
        """Format a structured entity as readable context for LLM."""
        lines = []
        entity_class = entity.get("class", "Rule")
        entity_text = entity.get("text", "")
        lines.append(f"**[{entity_class}]** {entity_text}")

        attrs = entity.get("attributes", {})
        important_keys = [
            "rule_type", "condition", "duration", "amount",
            "calculation_method", "mechanism", "pay_status",
            "legal_reference", "restriction", "example",
        ]
        for key in important_keys:
            if key in attrs:
                lines.append(f"  - {key}: {attrs[key]}")

        # Any remaining keys
        for key, value in attrs.items():
            if key not in important_keys:
                lines.append(f"  - {key}: {value}")

        return "\n".join(lines)

    # ===================================================================
    # Strategy 2: Tree Reasoning (PageIndex)
    # ===================================================================

    async def _tree_retrieve(
        self, query: str, filters: Optional[Dict] = None
    ) -> List[KnowledgeChunk]:
        """
        Use LLM to reason over tree structure and find relevant nodes.

        Sends compact tree (titles + summaries, NO full text) to LLM.
        LLM returns relevant node_ids.
        We then fetch full text from those nodes.

        Cost: 1 LLM call for tree navigation.
        """
        if not self._tree_indexes:
            return []

        # Build compact tree for all relevant documents
        compact_trees = {}
        for doc_id, tree in self._tree_indexes.items():
            if filters and filters.get("doc_id") and filters["doc_id"] != doc_id:
                continue
            compact = self._strip_tree_text(tree.get("structure", []))
            if compact:
                compact_trees[doc_id] = {
                    "description": tree.get("doc_description", ""),
                    "structure": compact,
                }

        if not compact_trees:
            return []

        # Single LLM call: ask which nodes are relevant
        from app.services.gemini import get_knowledge_model
        model = get_knowledge_model()

        # Build compact tree representation
        tree_repr = json.dumps(compact_trees, ensure_ascii=False, indent=2)

        # Limit tree size to avoid token overflow
        if len(tree_repr) > 8000:
            tree_repr = tree_repr[:8000] + "\n... (truncated)"

        prompt = f"""Bạn là hệ thống truy xuất thông tin. Cho các cây tài liệu bên dưới (chỉ tiêu đề và tóm tắt), hãy xác định các node chứa thông tin liên quan nhất đến câu hỏi.

CÂY TÀI LIỆU:
{tree_repr}

CÂU HỎI: "{query}"

Trả về JSON array gồm tối đa 3 node phù hợp nhất:
[{{"doc_id": "...", "node_id": "...", "relevance": "high/medium"}}]

Chỉ trả về JSON array, không thêm text khác. Nếu không tìm thấy node liên quan, trả về []."""

        try:
            response = await model.generate_content_async(prompt)
            text = response.text.strip()

            # Clean JSON from markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text

            relevant_nodes = json.loads(text.strip())
        except Exception as e:
            logger.warning(f"Tree reasoning LLM call failed: {e}")
            return []

        # Fetch full text from identified nodes
        chunks = []
        for node_ref in relevant_nodes[:3]:
            doc_id = node_ref.get("doc_id", "")
            node_id = node_ref.get("node_id", "")
            relevance = node_ref.get("relevance", "medium")

            tree = self._tree_indexes.get(doc_id, {})
            node = self._find_node_by_id(tree.get("structure", []), node_id)

            if node and node.get("text"):
                score = 0.95 if relevance == "high" else 0.80
                chunks.append(KnowledgeChunk(
                    content=node["text"],
                    source=f"{tree.get('doc_name', doc_id)} - {node.get('title', '')}",
                    metadata={
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "source_type": "tree_reasoning",
                    },
                    score=score
                ))

        return chunks

    def _strip_tree_text(self, nodes: list) -> list:
        """
        Create compact version of tree (titles + summaries only).
        Removes full text to minimize tokens sent to LLM.
        """
        compact = []
        for node in nodes:
            compact_node = {
                "title": node.get("title", ""),
                "node_id": node.get("node_id", ""),
                "summary": node.get("summary", node.get("prefix_summary", "")),
            }
            children = node.get("nodes", [])
            if children:
                compact_node["nodes"] = self._strip_tree_text(children)
            compact.append(compact_node)
        return compact

    def _find_node_by_id(self, nodes: list, target_id: str) -> Optional[dict]:
        """Find a node by node_id in the tree (recursive)."""
        for node in nodes:
            if node.get("node_id") == target_id:
                return node
            found = self._find_node_by_id(node.get("nodes", []), target_id)
            if found:
                return found
        return None

    # ===================================================================
    # Utility
    # ===================================================================

    def _deduplicate_chunks(self, chunks: List[KnowledgeChunk]) -> List[KnowledgeChunk]:
        """
        Remove near-duplicate chunks by content overlap.

        If two chunks have >60% word overlap, keep the higher-scored one.
        """
        if len(chunks) <= 1:
            return chunks

        # Sort by score descending so we keep higher-scored chunks
        chunks.sort(key=lambda c: c.score, reverse=True)

        result = []
        for chunk in chunks:
            chunk_words = set(chunk.content.lower().split())
            is_duplicate = False

            for existing in result:
                existing_words = set(existing.content.lower().split())
                if not chunk_words or not existing_words:
                    continue
                overlap = len(chunk_words & existing_words)
                max_len = max(len(chunk_words), len(existing_words))
                if overlap / max_len > 0.6:
                    is_duplicate = True
                    break

            if not is_duplicate:
                result.append(chunk)

        return result

    def _count_nodes(self, nodes: list) -> int:
        """Count total nodes in tree structure."""
        count = len(nodes)
        for node in nodes:
            count += self._count_nodes(node.get("nodes", []))
        return count

    # ===================================================================
    # Delegate unchanged methods to legacy provider
    # ===================================================================

    async def health_check(self) -> ProviderStatus:
        return await self._legacy.health_check()

    async def index_document(
        self, content: str, source: str, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        return await self._legacy.index_document(content, source, metadata)

    def list_documents(self) -> List[Dict[str, str]]:
        return self._legacy.list_documents()

    def get_document(self, doc_id: str):
        return self._legacy.get_document(doc_id)

    def get_full_content(self, doc_id: str) -> Optional[str]:
        return self._legacy.get_full_content(doc_id)

    @property
    def document_count(self) -> int:
        return self._legacy.document_count

    @property
    def chunk_count(self) -> int:
        return self._legacy.chunk_count

    @property
    def enhancement_status(self) -> Dict[str, Any]:
        """Report on which enhanced features are active."""
        return {
            "has_tree_indexes": self._has_trees,
            "tree_count": len(self._tree_indexes),
            "has_entities": self._has_entities,
            "entity_count": sum(len(e) for e in self._entities.values()),
            "mode": (
                "enhanced (tree + entities)"
                if self._has_trees and self._has_entities
                else "enhanced (tree only)"
                if self._has_trees
                else "enhanced (entities only)"
                if self._has_entities
                else "legacy"
            ),
        }
