# Implementation Plan: PageIndex + langextract Knowledge Pipeline

## Overview

Replace the current keyword-based hybrid retrieval with a 2-layer intelligence pipeline:
- **langextract** (Google): Extract structured entities (leave policies, rules, conditions) with character-level source grounding
- **PageIndex** (Vectify): Build hierarchical tree index with LLM-generated summaries for reasoning-based retrieval

```
┌──────────────────────────────────────────────────────────────────┐
│                    CURRENT vs NEW PIPELINE                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CURRENT:  .md files → header chunking → keyword scoring → LLM  │
│                                                                  │
│  NEW:      .md files ──┬─→ langextract  ─→ structured entities   │
│                        │                    (facts, rules, etc.)  │
│                        └─→ PageIndex    ─→ tree index + summaries│
│                                                ↓                 │
│            User query  ──→ tree reasoning ──→ relevant nodes     │
│                        ──→ entity lookup  ──→ precise facts      │
│                                    ↓                             │
│                            combined context ──→ LLM synthesis    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Architecture Decision: Why This Combination

| Aspect | Current System | PageIndex Only | langextract Only | **PageIndex + langextract** |
|--------|---------------|----------------|------------------|----------------------------|
| Retrieval | Keyword match | Tree reasoning | N/A (extraction, not retrieval) | **Tree reasoning + structured lookup** |
| Precision | Low (word overlap) | High (LLM navigates structure) | Very high (grounded entities) | **Very high** |
| Calculations | LLM guesses | LLM reasons from text | Pre-extracted rules | **Pre-extracted rules + context** |
| Probation Q&A | Failed | Better (finds right section) | Best (has explicit rules) | **Best (both)** |
| Cost | Free | ~1 LLM call/query | Pre-computed (free at query time) | **~1 LLM call/query + pre-computed** |

---

## Phase 1: langextract Integration (Offline Entity Extraction)

### 1.1 Install Dependencies

```bash
# Add to requirements.txt
langextract>=1.1.0
```

**Impact**: Adds ~17 packages including google-genai, pydantic, numpy, pandas. Most overlap with existing deps.

### 1.2 Define Company Regulation Schemas

Create `backend/app/mcp/knowledge/extraction/schemas.py`:

```python
"""
Extraction schemas for company regulations.
Define few-shot examples that teach langextract how to extract
structured knowledge from our regulation documents.
"""
from langextract.data import ExampleData, Extraction

# Schema 1: Leave policy rules
LEAVE_POLICY_EXAMPLES = [
    ExampleData(
        text="""NLĐ làm việc đủ 12 tháng: 12 ngày phép/năm, hưởng nguyên lương (tương ứng 01 ngày phép/tháng).
NLĐ làm việc dưới 12 tháng: tính theo tỷ lệ tương ứng với số tháng thực tế làm việc.""",
        extractions=[
            Extraction(
                extraction_class="LeaveRule",
                extraction_text="12 ngày phép/năm",
                attributes={
                    "rule_type": "annual_leave_entitlement",
                    "condition": "làm việc đủ 12 tháng",
                    "duration": "12 ngày",
                    "period": "năm",
                    "pay_status": "hưởng nguyên lương",
                    "monthly_equivalent": "01 ngày/tháng"
                }
            ),
            Extraction(
                extraction_class="LeaveRule",
                extraction_text="tính theo tỷ lệ tương ứng với số tháng thực tế làm việc",
                attributes={
                    "rule_type": "prorated_leave",
                    "condition": "làm việc dưới 12 tháng",
                    "calculation_method": "tỷ lệ theo số tháng thực tế"
                }
            ),
        ]
    ),
    ExampleData(
        text="""Thời gian thử việc được tính là thời gian làm việc để tính số ngày nghỉ hằng năm,
nếu NLĐ tiếp tục làm việc cho công ty sau khi hết thời gian thử việc.
Trong thời gian thử việc, ngày phép được tích lũy nhưng chưa sử dụng được.
Khi được nhận chính thức, hệ thống sẽ truy cộng số ngày phép đã tích lũy.""",
        extractions=[
            Extraction(
                extraction_class="LeaveRule",
                extraction_text="Thời gian thử việc được tính là thời gian làm việc",
                attributes={
                    "rule_type": "probation_leave_counting",
                    "condition": "tiếp tục làm việc sau thử việc",
                    "mechanism": "truy cộng (backdate) khi nhận chính thức",
                    "during_probation": "tích lũy nhưng chưa sử dụng được"
                }
            ),
        ]
    ),

    # Schema 2: Working time rules
    ExampleData(
        text="""Ngày làm việc: Từ thứ 2 đến thứ 6.
Giờ làm việc: Buổi sáng: Từ 8h30 đến 12h (Sau 8h40 sẽ bị tính là đi muộn). Buổi chiều: Từ 13h đến 17h30.""",
        extractions=[
            Extraction(
                extraction_class="WorkingTimeRule",
                extraction_text="Từ thứ 2 đến thứ 6",
                attributes={
                    "rule_type": "working_days",
                    "days": "thứ 2 đến thứ 6",
                    "applies_to": "khối chức năng"
                }
            ),
            Extraction(
                extraction_class="WorkingTimeRule",
                extraction_text="Từ 8h30 đến 12h",
                attributes={
                    "rule_type": "working_hours",
                    "session": "buổi sáng",
                    "start": "8h30",
                    "end": "12h",
                    "late_threshold": "8h40"
                }
            ),
        ]
    ),

    # Schema 3: Benefit/allowance rules
    ExampleData(
        text="""Bản thân kết hôn: 03 ngày nghỉ hưởng lương.
Con đẻ, con nuôi kết hôn: 01 ngày nghỉ hưởng lương.""",
        extractions=[
            Extraction(
                extraction_class="BenefitRule",
                extraction_text="03 ngày nghỉ hưởng lương",
                attributes={
                    "rule_type": "special_leave",
                    "event": "bản thân kết hôn",
                    "duration": "03 ngày",
                    "pay_status": "hưởng lương"
                }
            ),
        ]
    ),
]

# Prompt description for extraction
REGULATION_EXTRACTION_PROMPT = """Extract all rules, policies, entitlements, and regulations from Vietnamese company labor documents.

For each rule, capture:
- rule_type: Category (e.g., annual_leave, probation, working_hours, special_leave, disciplinary)
- condition: When/who this rule applies to
- duration/amount: Quantitative values
- calculation_method: How to compute (if applicable)
- mechanism: How it works in practice
- pay_status: Paid or unpaid (if applicable)
- applies_to: Who this applies to (if specified)

Extract text must be copied verbatim from the source document in order of appearance."""
```

### 1.3 Create Extraction Runner

Create `backend/app/mcp/knowledge/extraction/extractor.py`:

```python
"""
Offline extraction runner.
Run this when regulation documents are updated to regenerate structured entities.

Usage:
    python -m app.mcp.knowledge.extraction.extractor
"""
import asyncio
import json
import os
from pathlib import Path

import langextract as lx
from langextract.io import save_annotated_documents

from .schemas import LEAVE_POLICY_EXAMPLES, REGULATION_EXTRACTION_PROMPT


KNOWLEDGE_DIR = Path(__file__).parent.parent / "regulations"
OUTPUT_DIR = Path(__file__).parent.parent / "extracted"


def extract_document(md_path: Path) -> dict:
    """Extract structured entities from a single markdown document."""
    text = md_path.read_text(encoding="utf-8")

    result = lx.extract(
        text_or_documents=text,
        prompt_description=REGULATION_EXTRACTION_PROMPT,
        examples=LEAVE_POLICY_EXAMPLES,
        model_id=os.getenv("GEMINI_KNOWLEDGE_MODEL", "gemini-2.5-flash"),
        extraction_passes=2,        # 2 passes for better recall
        max_char_buffer=2000,       # larger chunks for regulation context
        max_workers=5,
        use_schema_constraints=True,
    )

    # Convert to serializable format
    entities = []
    for ext in result.extractions:
        entities.append({
            "class": ext.extraction_class,
            "text": ext.extraction_text,
            "attributes": ext.attributes,
            "start_pos": ext.char_interval.start_pos if ext.char_interval else None,
            "end_pos": ext.char_interval.end_pos if ext.char_interval else None,
            "alignment": ext.alignment_status.name if ext.alignment_status else None,
        })

    return {
        "source_file": md_path.name,
        "entity_count": len(entities),
        "entities": entities,
    }


def run_extraction():
    """Extract all regulation documents."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(KNOWLEDGE_DIR.glob("*.md"))
    print(f"Found {len(md_files)} documents to extract")

    all_results = {}
    for md_path in md_files:
        print(f"  Extracting: {md_path.name}")
        result = extract_document(md_path)
        all_results[md_path.stem] = result
        print(f"    → {result['entity_count']} entities extracted")

    # Save combined output
    output_path = OUTPUT_DIR / "entities.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {output_path}")
    return all_results


if __name__ == "__main__":
    run_extraction()
```

### 1.4 Output Format

The extraction produces `backend/app/mcp/knowledge/extracted/entities.json`:

```json
{
  "noi_quy_lao_dong": {
    "source_file": "noi_quy_lao_dong.md",
    "entity_count": 45,
    "entities": [
      {
        "class": "LeaveRule",
        "text": "12 ngày phép/năm",
        "attributes": {
          "rule_type": "annual_leave_entitlement",
          "condition": "làm việc đủ 12 tháng",
          "duration": "12 ngày",
          "period": "năm",
          "monthly_equivalent": "01 ngày/tháng"
        },
        "start_pos": 1842,
        "end_pos": 1858,
        "alignment": "MATCH_EXACT"
      },
      {
        "class": "LeaveRule",
        "text": "Thời gian thử việc được tính là thời gian làm việc",
        "attributes": {
          "rule_type": "probation_leave_counting",
          "condition": "tiếp tục làm việc sau thử việc",
          "mechanism": "truy cộng khi nhận chính thức"
        },
        "start_pos": 2150,
        "end_pos": 2200,
        "alignment": "MATCH_EXACT"
      }
    ]
  }
}
```

---

## Phase 2: PageIndex Integration (Tree Indexing)

### 2.1 Install Dependencies

```bash
# Add to requirements.txt
# PageIndex local mode (clone as submodule or vendored)
PyPDF2>=3.0.1
pymupdf>=1.26.0
tiktoken>=0.11.0
pyyaml>=6.0.2
# openai is needed for PageIndex but we'll patch to use Gemini
```

**Important**: PageIndex is hardcoded to OpenAI. We have 3 options:
- **Option A**: Use LiteLLM as proxy (adds dependency but zero code changes)
- **Option B**: Patch `pageindex/utils.py` to use Gemini (minimal code, full control)
- **Option C**: Use PageIndex Cloud API (simplest but requires external API key + internet)

**Recommended: Option B** - Patch utils.py to support Gemini directly.

### 2.2 Vendor PageIndex with Gemini Adapter

Create `backend/app/mcp/knowledge/indexing/pageindex_adapter.py`:

```python
"""
Adapter to run PageIndex tree generation using Gemini instead of OpenAI.
Patches the LLM call functions to use google.generativeai.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import google.generativeai as genai
from app.core.settings import settings


# Configure Gemini
genai.configure(api_key=settings.GOOGLE_API_KEY.get_secret_value())
_model = genai.GenerativeModel(settings.GEMINI_KNOWLEDGE_MODEL or settings.GEMINI_MODEL)


def gemini_chat(model_name: str, prompt: str, api_key: str = None) -> str:
    """Drop-in replacement for PageIndex's ChatGPT_API."""
    response = _model.generate_content(prompt)
    return response.text


async def gemini_chat_async(model_name: str, prompt: str, api_key: str = None) -> str:
    """Drop-in replacement for PageIndex's ChatGPT_API_async."""
    response = await _model.generate_content_async(prompt)
    return response.text


def patch_pageindex():
    """Monkey-patch PageIndex to use Gemini instead of OpenAI."""
    import pageindex.utils as utils
    utils.ChatGPT_API = gemini_chat
    utils.ChatGPT_API_async = gemini_chat_async


def build_tree_from_markdown(md_path: str, config_overrides: dict = None) -> dict:
    """Build PageIndex tree from a markdown file using Gemini."""
    patch_pageindex()

    from pageindex.page_index_md import md_to_tree

    tree = asyncio.run(md_to_tree(
        md_path=md_path,
        if_thinning=False,         # Keep all sections
        if_add_node_summary="yes", # Generate summaries
        model=settings.GEMINI_KNOWLEDGE_MODEL or settings.GEMINI_MODEL,
        **(config_overrides or {})
    ))

    return tree
```

### 2.3 Create Tree Index Runner

Create `backend/app/mcp/knowledge/indexing/indexer.py`:

```python
"""
Offline tree index builder.
Run this when regulation documents are updated to regenerate tree indexes.

Usage:
    python -m app.mcp.knowledge.indexing.indexer
"""
import json
from pathlib import Path

from .pageindex_adapter import build_tree_from_markdown


KNOWLEDGE_DIR = Path(__file__).parent.parent / "regulations"
OUTPUT_DIR = Path(__file__).parent.parent / "indexed"


def build_indexes():
    """Build tree indexes for all markdown documents."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(KNOWLEDGE_DIR.glob("*.md"))
    print(f"Found {len(md_files)} documents to index")

    for md_path in md_files:
        print(f"  Building tree: {md_path.name}")
        tree = build_tree_from_markdown(str(md_path))

        output_path = OUTPUT_DIR / f"{md_path.stem}_tree.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)

        # Count nodes
        node_count = count_nodes(tree.get("structure", []))
        print(f"    → {node_count} nodes in tree")

    print(f"\nAll trees saved to {OUTPUT_DIR}")


def count_nodes(nodes: list) -> int:
    count = len(nodes)
    for node in nodes:
        count += count_nodes(node.get("nodes", []))
    return count


if __name__ == "__main__":
    build_indexes()
```

### 2.4 Output Format

The indexing produces `backend/app/mcp/knowledge/indexed/noi_quy_lao_dong_tree.json`:

```json
{
  "doc_name": "noi_quy_lao_dong",
  "doc_description": "Nội quy lao động quy định về thời gian làm việc, nghỉ phép, kỷ luật...",
  "structure": [
    {
      "title": "Điều 7: Nghỉ phép hàng năm",
      "node_id": "0003",
      "summary": "Quy định về số ngày nghỉ phép (12 ngày/năm), cách tính phép cho NV mới bao gồm thử việc, cơ chế tích lũy theo tháng, và ví dụ minh họa.",
      "start_index": 55,
      "end_index": 89,
      "nodes": [
        {
          "title": "Số ngày nghỉ phép",
          "node_id": "0004",
          "summary": "12 ngày/năm cho NLĐ đủ 12 tháng, tỷ lệ cho NLĐ dưới 12 tháng, tăng 1 ngày mỗi 5 năm.",
          "start_index": 57,
          "end_index": 60
        },
        {
          "title": "Cách tính ngày phép cho nhân viên mới (bao gồm thời gian thử việc)",
          "node_id": "0005",
          "summary": "Thử việc được tính vào thâm niên (NĐ 145/2020), tích lũy 1 ngày/tháng, truy cộng khi chính thức.",
          "start_index": 62,
          "end_index": 65
        }
      ]
    }
  ]
}
```

---

## Phase 3: New Knowledge Provider (Runtime Integration)

### 3.1 Create Enhanced Provider

Create `backend/app/mcp/providers/enhanced_regulations_provider.py`:

```python
"""
Enhanced Regulations Provider
=============================
Combines 3 retrieval strategies:
1. PageIndex tree reasoning (LLM navigates tree to find relevant sections)
2. langextract entity lookup (structured fact matching)
3. Legacy keyword matching (fallback)

The tree index and entities are pre-computed offline.
At query time, we only need 1 LLM call for tree navigation.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from app.mcp.providers.base_knowledge_provider import (
    BaseKnowledgeProvider, KnowledgeChunk, RetrievalResult, RetrievalStrategy
)
from app.mcp.providers.regulations_provider import RegulationsProvider
from app.core.settings import settings
from app.core.logging import logger


class EnhancedRegulationsProvider(BaseKnowledgeProvider):
    """
    Enhanced provider with PageIndex tree + langextract entities.

    Falls back to legacy RegulationsProvider if pre-computed indexes don't exist.
    """

    INDEXED_DIR = Path(__file__).parent.parent / "knowledge" / "indexed"
    EXTRACTED_DIR = Path(__file__).parent.parent / "knowledge" / "extracted"

    def __init__(self, **kwargs):
        super().__init__(
            config=kwargs.get("config"),
            strategy=RetrievalStrategy.HYBRID
        )
        self._legacy_provider = RegulationsProvider(**kwargs)
        self._tree_indexes: Dict[str, dict] = {}     # doc_id -> tree JSON
        self._entities: Dict[str, list] = {}          # doc_id -> entity list
        self._has_enhanced = False

    @property
    def name(self) -> str:
        return "regulations"

    async def initialize(self) -> None:
        # Always initialize legacy provider (guaranteed to work)
        await self._legacy_provider.initialize()

        # Try to load pre-computed indexes
        try:
            self._load_tree_indexes()
            self._load_entities()
            self._has_enhanced = bool(self._tree_indexes or self._entities)
            if self._has_enhanced:
                logger.info(
                    f"Enhanced mode: {len(self._tree_indexes)} trees, "
                    f"{sum(len(e) for e in self._entities.values())} entities"
                )
        except Exception as e:
            logger.warning(f"Enhanced indexes not available, using legacy: {e}")
            self._has_enhanced = False

        self._status = self._legacy_provider._status

    def _load_tree_indexes(self):
        if not self.INDEXED_DIR.exists():
            return
        for tree_path in self.INDEXED_DIR.glob("*_tree.json"):
            doc_id = tree_path.stem.replace("_tree", "")
            with open(tree_path, "r", encoding="utf-8") as f:
                self._tree_indexes[doc_id] = json.load(f)

    def _load_entities(self):
        entities_path = self.EXTRACTED_DIR / "entities.json"
        if not entities_path.exists():
            return
        with open(entities_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for doc_id, doc_data in data.items():
            self._entities[doc_id] = doc_data.get("entities", [])

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        if not self._has_enhanced:
            return await self._legacy_provider.retrieve(query, top_k, filters)

        chunks = []

        # Strategy 1: Entity lookup (fast, precise)
        entity_chunks = self._entity_lookup(query, filters)
        chunks.extend(entity_chunks)

        # Strategy 2: Tree reasoning (1 LLM call)
        tree_chunks = await self._tree_retrieve(query, filters)
        chunks.extend(tree_chunks)

        # Strategy 3: Legacy fallback for additional context
        legacy_result = await self._legacy_provider.retrieve(query, top_k=2, filters=filters)
        for chunk in legacy_result.chunks:
            # Avoid duplicates
            if not any(c.content == chunk.content for c in chunks):
                chunk.score *= 0.7  # Lower priority for legacy
                chunks.append(chunk)

        # Sort and limit
        chunks.sort(key=lambda c: c.score, reverse=True)
        return RetrievalResult(
            chunks=chunks[:top_k],
            query=query,
            total_found=len(chunks)
        )

    def _entity_lookup(
        self, query: str, filters: Optional[Dict] = None
    ) -> List[KnowledgeChunk]:
        """Fast entity-based lookup for precise fact retrieval."""
        query_lower = query.lower()
        chunks = []

        for doc_id, entities in self._entities.items():
            if filters and filters.get("doc_id") and filters["doc_id"] != doc_id:
                continue

            for entity in entities:
                # Score by attribute relevance
                score = self._score_entity(query_lower, entity)
                if score > 0.3:
                    # Format entity as readable context
                    content = self._format_entity(entity)
                    chunks.append(KnowledgeChunk(
                        content=content,
                        source=f"Structured data - {entity['class']}",
                        metadata={
                            "doc_id": doc_id,
                            "entity_class": entity["class"],
                            "source_type": "langextract"
                        },
                        score=score
                    ))

        return chunks

    def _score_entity(self, query: str, entity: dict) -> float:
        """Score an entity's relevance to the query."""
        score = 0.0
        query_words = set(query.split())

        # Check entity text
        entity_text = entity.get("text", "").lower()
        text_words = set(entity_text.split())
        overlap = len(query_words & text_words)
        if overlap:
            score += min(overlap / len(query_words), 1.0) * 0.4

        # Check attributes
        attrs = entity.get("attributes", {})
        for key, value in attrs.items():
            value_str = str(value).lower()
            if any(w in value_str for w in query_words):
                score += 0.2
            if any(w in key.lower() for w in query_words):
                score += 0.1

        # Bonus for rule_type matching common patterns
        rule_type = attrs.get("rule_type", "").lower()
        if "phép" in query and "leave" in rule_type:
            score += 0.3
        if "thử việc" in query and "probation" in rule_type:
            score += 0.3

        return min(score, 1.0)

    def _format_entity(self, entity: dict) -> str:
        """Format a structured entity as readable text for LLM context."""
        lines = [f"**[{entity['class']}]** {entity['text']}"]
        attrs = entity.get("attributes", {})
        for key, value in attrs.items():
            lines.append(f"  - {key}: {value}")
        return "\n".join(lines)

    async def _tree_retrieve(
        self, query: str, filters: Optional[Dict] = None
    ) -> List[KnowledgeChunk]:
        """Use LLM to reason over tree structure and find relevant nodes."""
        if not self._tree_indexes:
            return []

        # Build compact tree (titles + summaries only, no full text)
        compact_trees = {}
        for doc_id, tree in self._tree_indexes.items():
            if filters and filters.get("doc_id") and filters["doc_id"] != doc_id:
                continue
            compact_trees[doc_id] = self._compact_tree(tree.get("structure", []))

        if not compact_trees:
            return []

        # Single LLM call: ask which nodes are relevant
        from app.services.gemini import get_knowledge_model
        model = get_knowledge_model()

        tree_prompt = f"""Given these document trees (titles and summaries), identify the most relevant node_ids for the question.

DOCUMENT TREES:
{json.dumps(compact_trees, ensure_ascii=False, indent=2)}

QUESTION: "{query}"

Return a JSON array of objects: [{{"doc_id": "...", "node_id": "...", "reason": "..."}}]
Return only the top 3 most relevant nodes. Return ONLY valid JSON, no other text."""

        try:
            response = await model.generate_content_async(tree_prompt)
            text = response.text.strip()
            # Clean JSON from markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            relevant_nodes = json.loads(text)
        except Exception as e:
            logger.warning(f"Tree reasoning failed: {e}")
            return []

        # Fetch full text from identified nodes
        chunks = []
        for node_ref in relevant_nodes[:3]:
            doc_id = node_ref.get("doc_id")
            node_id = node_ref.get("node_id")
            tree = self._tree_indexes.get(doc_id, {})
            node = self._find_node(tree.get("structure", []), node_id)
            if node and node.get("text"):
                chunks.append(KnowledgeChunk(
                    content=node["text"],
                    source=f"{doc_id} - {node.get('title', '')}",
                    metadata={
                        "doc_id": doc_id,
                        "node_id": node_id,
                        "source_type": "pageindex_tree"
                    },
                    score=0.9  # High confidence from LLM reasoning
                ))

        return chunks

    def _compact_tree(self, nodes: list) -> list:
        """Strip full text from tree, keeping only titles and summaries."""
        compact = []
        for node in nodes:
            compact_node = {
                "title": node.get("title", ""),
                "node_id": node.get("node_id", ""),
                "summary": node.get("summary", node.get("prefix_summary", "")),
            }
            children = node.get("nodes", [])
            if children:
                compact_node["nodes"] = self._compact_tree(children)
            compact.append(compact_node)
        return compact

    def _find_node(self, nodes: list, target_id: str) -> Optional[dict]:
        """Find a node by ID in the tree."""
        for node in nodes:
            if node.get("node_id") == target_id:
                return node
            found = self._find_node(node.get("nodes", []), target_id)
            if found:
                return found
        return None

    # Delegate other methods to legacy provider
    async def health_check(self):
        return await self._legacy_provider.health_check()

    async def index_document(self, content, source, metadata=None):
        return await self._legacy_provider.index_document(content, source, metadata)

    def list_documents(self):
        return self._legacy_provider.list_documents()

    def get_document(self, doc_id):
        return self._legacy_provider.get_document(doc_id)
```

### 3.2 Update Bootstrap

In `backend/app/mcp/bootstrap.py`, replace:

```python
# Before
provider_registry.register(RegulationsProvider())

# After
from app.mcp.providers.enhanced_regulations_provider import EnhancedRegulationsProvider
provider_registry.register(EnhancedRegulationsProvider())
```

The enhanced provider auto-falls back to legacy if no pre-computed indexes exist.

---

## Phase 4: Preprocessing Pipeline (CLI Tool)

### 4.1 Create Management Command

Create `backend/app/mcp/knowledge/rebuild.py`:

```python
"""
Knowledge base rebuild pipeline.
Runs langextract + PageIndex to regenerate all indexes.

Usage:
    cd backend
    python -m app.mcp.knowledge.rebuild [--extract-only] [--index-only]
"""
import argparse
import time


def main():
    parser = argparse.ArgumentParser(description="Rebuild knowledge base indexes")
    parser.add_argument("--extract-only", action="store_true", help="Only run langextract")
    parser.add_argument("--index-only", action="store_true", help="Only run PageIndex")
    args = parser.parse_args()

    start = time.time()

    if not args.index_only:
        print("=" * 60)
        print("STEP 1: Running langextract (structured entity extraction)")
        print("=" * 60)
        from app.mcp.knowledge.extraction.extractor import run_extraction
        run_extraction()
        print()

    if not args.extract_only:
        print("=" * 60)
        print("STEP 2: Running PageIndex (tree index generation)")
        print("=" * 60)
        from app.mcp.knowledge.indexing.indexer import build_indexes
        build_indexes()
        print()

    elapsed = time.time() - start
    print(f"✓ Knowledge base rebuilt in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
```

### 4.2 File Structure After Implementation

```
backend/app/mcp/knowledge/
├── regulations/                    # Source documents (unchanged)
│   ├── index.json
│   ├── noi_quy_lao_dong.md
│   ├── quy_che_du_lich.md
│   ├── quy_cho_vay.md
│   └── dinh_muc_chi.md
│
├── extracted/                      # NEW: langextract output
│   └── entities.json               # Structured entities from all docs
│
├── indexed/                        # NEW: PageIndex output
│   ├── noi_quy_lao_dong_tree.json  # Tree index with summaries
│   ├── quy_che_du_lich_tree.json
│   ├── quy_cho_vay_tree.json
│   └── dinh_muc_chi_tree.json
│
├── extraction/                     # NEW: langextract config
│   ├── __init__.py
│   ├── schemas.py                  # Few-shot examples & prompt
│   └── extractor.py                # Extraction runner
│
├── indexing/                       # NEW: PageIndex config
│   ├── __init__.py
│   ├── pageindex_adapter.py        # Gemini adapter for PageIndex
│   └── indexer.py                  # Index builder
│
└── rebuild.py                      # CLI: rebuild all indexes
```

---

## Phase 5: Cost & Performance Analysis

### Offline Processing (run once per document update)

| Step | LLM Calls | Est. Cost (Gemini Flash) | Time |
|------|-----------|------------------------|------|
| langextract (4 docs, ~8K chars total) | ~20 calls | ~$0.01 | ~30s |
| PageIndex tree (4 docs) | ~40 calls | ~$0.02 | ~2min |
| **Total per rebuild** | **~60** | **~$0.03** | **~2.5min** |

### Runtime Query (per user question)

| Step | LLM Calls | Est. Cost | Latency |
|------|-----------|-----------|---------|
| Entity lookup | 0 (pre-computed) | $0.00 | <10ms |
| Tree reasoning | 1 call | ~$0.001 | ~1-2s |
| Legacy fallback | 0 (in-memory) | $0.00 | <10ms |
| Synthesis | 1 call | ~$0.001 | ~2-3s |
| **Total per query** | **2** | **~$0.002** | **~3-5s** |

**Comparison with current system:**

| Metric | Current | Enhanced |
|--------|---------|----------|
| LLM calls/query | 1 | 2 |
| Retrieval accuracy | Low (keyword match) | High (reasoning + entities) |
| Probation Q&A correct? | No | Yes |
| Temporal context? | No | Yes (entities have rule_type) |
| Cost/query | ~$0.001 | ~$0.002 |
| Latency | ~2-3s | ~3-5s |

---

## Phase 6: Testing Strategy

### 6.1 Test Cases for Probation Leave

```python
# test_enhanced_retrieval.py

PROBATION_LEAVE_TESTS = [
    {
        "query": "nếu tôi vào thử việc tháng 7, tháng 9 được nhận chính thức thì tháng 9 tôi sẽ có bao ngày nghỉ phép",
        "expected_answer_contains": ["02 ngày", "2 ngày"],
        "should_not_contain": ["4 ngày", "4 tháng"],
        "expected_entities": ["probation_leave_counting"],
    },
    {
        "query": "thử việc có được tính phép không",
        "expected_answer_contains": ["được tính", "tích lũy"],
        "expected_entities": ["probation_leave_counting"],
    },
    {
        "query": "tháng 10 tôi có bao nhiêu ngày phép nếu chính thức từ tháng 9",
        "expected_answer_contains": ["03 ngày", "3 ngày"],
        "should_not_contain": ["tổng cả năm"],
    },
]
```

### 6.2 Regression Tests

Run existing knowledge queries to ensure no regression:
- "Nghỉ phép được bao nhiêu ngày?" → 12 ngày/năm
- "Giờ làm việc công ty" → 8h30-12h, 13h-17h30
- "Công ty hỗ trợ du lịch bao nhiêu?" → (from quy_che_du_lich)
- "Vay tiền được bao nhiêu?" → (from quy_cho_vay)

---

## Implementation Order & Timeline

| Step | Description | Effort | Priority |
|------|-------------|--------|----------|
| 1 | Add langextract dep + schemas | 1 day | P0 |
| 2 | Create extraction runner + test on 1 doc | 1 day | P0 |
| 3 | Vendor PageIndex + Gemini adapter | 1 day | P0 |
| 4 | Create tree indexer + test on 1 doc | 1 day | P0 |
| 5 | Create EnhancedRegulationsProvider | 2 days | P0 |
| 6 | Update bootstrap + test full pipeline | 1 day | P0 |
| 7 | Create rebuild CLI | 0.5 day | P1 |
| 8 | Write test suite | 1 day | P1 |
| 9 | Docker + CI/CD integration | 0.5 day | P2 |
| **Total** | | **~8 days** | |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PageIndex OpenAI dependency | Can't use Gemini directly | Gemini adapter (Phase 2.2) |
| langextract schema quality | Poor entity extraction | Iterative schema refinement with validation |
| Pre-computed indexes stale | Wrong answers after doc update | rebuild.py + reminder in EXTENDING.md |
| Tree reasoning hallucinates node_ids | Retrieves wrong sections | Validate node_ids before fetching; fallback to legacy |
| Docker image size increase | Longer build/deploy | Multi-stage build; keep PyMuPDF optional |
| Cost increase (2x LLM calls) | ~$0.001 more/query | Negligible; cache tree reasoning results |

---

## Environment Variables (new)

```env
# .env additions
GEMINI_KNOWLEDGE_MODEL=gemini-2.5-pro   # Stronger model for knowledge tasks (optional)
```

No new API keys needed - everything runs on the existing Gemini API key.
