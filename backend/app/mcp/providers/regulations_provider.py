# app/mcp/providers/regulations_provider.py
"""
Regulations Knowledge Provider
==============================
Provider xử lý các văn bản quy định, quy chế, nội quy của công ty.

Sử dụng phương pháp Hybrid Retrieval:
1. Keyword-based: Dựa trên query_mappings và keywords từ index.json
2. Section-aware: Chunk theo cấu trúc document (## headers)
3. Full-context fallback: Gửi toàn bộ document nếu cần (cho doc nhỏ)

Đây là giải pháp tối ưu cho:
- Document có cấu trúc rõ ràng (Markdown với headers)
- Kích thước trung bình (<50K tokens)
- Chạy trên PC thông thường (không cần GPU/vector DB)
"""

import json
import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus
from app.mcp.providers.base_knowledge_provider import (
    BaseKnowledgeProvider,
    KnowledgeChunk,
    RetrievalResult,
    RetrievalStrategy
)

logger = logging.getLogger(__name__)


@dataclass
class DocumentMeta:
    """Metadata for a single document"""
    id: str
    file: str
    title: str
    description: str
    keywords: List[str]
    sections: List[Dict[str, Any]]
    effective_date: str
    content: str = ""  # Loaded content
    chunks: List[Dict[str, Any]] = None  # Parsed chunks

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = []


class RegulationsProvider(BaseKnowledgeProvider):
    """
    Knowledge provider cho các văn bản quy định, quy chế, nội quy.

    Features:
    - Tự động load documents từ thư mục cấu hình
    - Hybrid search: keyword + section-based
    - Query mapping cho các câu hỏi phổ biến
    - Caching để tối ưu performance

    Usage:
        provider = RegulationsProvider()
        await provider.initialize()

        # Search
        result = await provider.retrieve("nghỉ phép bao nhiêu ngày")
        print(result.best_chunk.content)

        # Get full document
        doc = provider.get_document("noi_quy_lao_dong")
    """

    DEFAULT_KNOWLEDGE_PATH = Path(__file__).parent.parent / "knowledge" / "regulations"

    def __init__(
        self,
        knowledge_path: Optional[Path] = None,
        config: Optional[ProviderConfig] = None
    ):
        super().__init__(
            config or ProviderConfig(name="regulations"),
            strategy=RetrievalStrategy.HYBRID
        )
        self._knowledge_path = knowledge_path or self.DEFAULT_KNOWLEDGE_PATH
        self._documents: Dict[str, DocumentMeta] = {}
        self._query_mappings: Dict[str, List[str]] = {}
        self._all_keywords: Dict[str, List[str]] = {}  # keyword -> [doc_ids]
        self._index_data: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "regulations"

    async def initialize(self) -> None:
        """Load all documents and build index"""
        try:
            # Load index.json
            index_path = self._knowledge_path / "index.json"
            if not index_path.exists():
                logger.warning(f"Index file not found: {index_path}")
                self._status = ProviderStatus.DEGRADED
                return

            with open(index_path, 'r', encoding='utf-8') as f:
                self._index_data = json.load(f)

            # Load query mappings
            self._query_mappings = self._index_data.get("query_mappings", {})

            # Load each document
            for doc_info in self._index_data.get("documents", []):
                doc_id = doc_info["id"]
                doc_path = self._knowledge_path / doc_info["file"]

                if not doc_path.exists():
                    logger.warning(f"Document not found: {doc_path}")
                    continue

                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                doc = DocumentMeta(
                    id=doc_id,
                    file=doc_info["file"],
                    title=doc_info["title"],
                    description=doc_info["description"],
                    keywords=doc_info.get("keywords", []),
                    sections=doc_info.get("sections", []),
                    effective_date=doc_info.get("effective_date", ""),
                    content=content
                )

                # Parse chunks from content
                doc.chunks = self._parse_chunks(content, doc_id)

                self._documents[doc_id] = doc

                # Build keyword index
                for keyword in doc.keywords:
                    keyword_lower = keyword.lower()
                    if keyword_lower not in self._all_keywords:
                        self._all_keywords[keyword_lower] = []
                    self._all_keywords[keyword_lower].append(doc_id)

            logger.info(f"Loaded {len(self._documents)} documents with {sum(len(d.chunks) for d in self._documents.values())} chunks")
            self._status = ProviderStatus.HEALTHY

        except Exception as e:
            logger.error(f"Error initializing RegulationsProvider: {e}")
            self._status = ProviderStatus.UNAVAILABLE
            raise

    def _parse_chunks(self, content: str, doc_id: str) -> List[Dict[str, Any]]:
        """
        Parse document into chunks based on headers.

        Chunking strategy:
        - Level 1: ## headers (Điều X, main sections)
        - Level 2: ### headers (Khoản X.Y, subsections)
        - Keep context: include parent header in chunk
        """
        chunks = []
        lines = content.split('\n')

        current_h1 = ""  # # header
        current_h2 = ""  # ## header
        current_chunk = []
        chunk_start_line = 0

        for i, line in enumerate(lines):
            # Detect headers
            if line.startswith('# ') and not line.startswith('## '):
                # Document title - skip chunking, used as context
                current_h1 = line[2:].strip()
                continue
            elif line.startswith('## '):
                # Save previous chunk
                if current_chunk:
                    chunk_text = '\n'.join(current_chunk).strip()
                    if chunk_text:
                        chunks.append({
                            "id": f"{doc_id}_{len(chunks)}",
                            "title": current_h2 or current_h1,
                            "content": chunk_text,
                            "parent": current_h1,
                            "line_start": chunk_start_line,
                            "line_end": i - 1
                        })

                current_h2 = line[3:].strip()
                current_chunk = [line]
                chunk_start_line = i
            elif line.startswith('### '):
                # Include in current chunk but mark subsection
                current_chunk.append(line)
            else:
                current_chunk.append(line)

        # Don't forget last chunk
        if current_chunk:
            chunk_text = '\n'.join(current_chunk).strip()
            if chunk_text:
                chunks.append({
                    "id": f"{doc_id}_{len(chunks)}",
                    "title": current_h2 or current_h1,
                    "content": chunk_text,
                    "parent": current_h1,
                    "line_start": chunk_start_line,
                    "line_end": len(lines) - 1
                })

        return chunks

    async def health_check(self) -> ProviderStatus:
        """Check if documents are loaded"""
        if not self._documents:
            self._status = ProviderStatus.DEGRADED
        else:
            self._status = ProviderStatus.HEALTHY
        return self._status

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """
        Hybrid retrieval: query mapping + keyword + content matching.

        Args:
            query: User's question
            top_k: Number of chunks to return
            filters: Optional filters (doc_id, section, etc.)

        Returns:
            RetrievalResult with relevant chunks
        """
        query_lower = query.lower()
        scored_chunks: List[Tuple[KnowledgeChunk, float]] = []

        # Step 1: Check query mappings (returns doc_id -> [section_ids])
        mapped_sections = self._get_mapped_sections(query_lower)

        # Step 2: Check keyword matches
        keyword_docs = self._get_keyword_matched_documents(query_lower)

        # Combine and dedupe
        relevant_doc_ids = list(set(list(mapped_sections.keys()) + keyword_docs))

        # If no matches, search all documents
        if not relevant_doc_ids:
            relevant_doc_ids = list(self._documents.keys())

        # Build section-to-articles lookup for section-aware scoring
        section_articles: Dict[str, List] = {}
        for doc_id in relevant_doc_ids:
            doc = self._documents.get(doc_id)
            if not doc:
                continue
            for sec in doc.sections:
                key = f"{doc_id}#{sec['id']}"
                section_articles[key] = [str(a) for a in sec.get("articles", [])]

        # Step 3: Search chunks in relevant documents
        for doc_id in relevant_doc_ids:
            doc = self._documents.get(doc_id)
            if not doc:
                continue

            # Apply filters
            if filters:
                if filters.get("doc_id") and filters["doc_id"] != doc_id:
                    continue

            target_sections = mapped_sections.get(doc_id, [])

            for chunk in doc.chunks:
                # Check if this chunk belongs to a mapped section
                chunk_in_target_section = self._chunk_matches_section(
                    chunk, doc_id, target_sections, section_articles
                )

                score = self._calculate_relevance_score(
                    query_lower,
                    chunk,
                    doc_id in mapped_sections,
                    doc_id in keyword_docs,
                    chunk_in_target_section
                )

                if score > 0:
                    knowledge_chunk = KnowledgeChunk(
                        content=chunk["content"],
                        source=f"{doc.title} - {chunk['title']}",
                        metadata={
                            "doc_id": doc_id,
                            "chunk_id": chunk["id"],
                            "title": chunk["title"],
                            "parent": chunk["parent"],
                            "effective_date": doc.effective_date
                        },
                        score=score
                    )
                    scored_chunks.append((knowledge_chunk, score))

        # Sort by score and take top_k
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        result_chunks = [c for c, s in scored_chunks[:top_k]]

        return RetrievalResult(
            chunks=result_chunks,
            query=query,
            total_found=len(scored_chunks)
        )

    def _get_mapped_sections(self, query: str) -> Dict[str, List[str]]:
        """
        Get documents AND their target sections from query mappings.

        Returns:
            Dict mapping doc_id -> list of matched section_ids.
            Example: {"noi_quy_lao_dong": ["nghi_viec", "nghi_phep"]}
        """
        matched: Dict[str, List[str]] = {}
        for mapping_key, doc_refs in self._query_mappings.items():
            if mapping_key in query:
                for ref in doc_refs:
                    parts = ref.split('#', 1)
                    doc_id = parts[0]
                    section_id = parts[1] if len(parts) > 1 else None
                    if doc_id not in matched:
                        matched[doc_id] = []
                    if section_id and section_id not in matched[doc_id]:
                        matched[doc_id].append(section_id)
        return matched

    def _chunk_matches_section(
        self,
        chunk: Dict[str, Any],
        doc_id: str,
        target_sections: List[str],
        section_articles: Dict[str, List]
    ) -> bool:
        """Check if a chunk belongs to one of the target sections."""
        if not target_sections:
            return False

        chunk_title = chunk.get("title", "")
        # Extract article number from chunk title (e.g. "Điều 11: ..." → "11")
        article_match = re.search(r'Điều\s+(\d+)', chunk_title)
        if not article_match:
            return False
        article_num = article_match.group(1)

        for section_id in target_sections:
            key = f"{doc_id}#{section_id}"
            articles = section_articles.get(key, [])
            if article_num in articles:
                return True
        return False

    def _get_keyword_matched_documents(self, query: str) -> List[str]:
        """Get documents that have matching keywords"""
        matched = []
        query_words = set(query.split())

        for keyword, doc_ids in self._all_keywords.items():
            # Check if keyword is in query
            if keyword in query or any(keyword in word for word in query_words):
                matched.extend(doc_ids)

        return list(set(matched))

    @staticmethod
    def _get_bigrams(words: List[str]) -> List[str]:
        """Generate bigrams from word list: ['a','b','c'] → ['a b', 'b c']"""
        return [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

    def _calculate_relevance_score(
        self,
        query: str,
        chunk: Dict[str, Any],
        is_mapped: bool,
        has_keyword: bool,
        in_target_section: bool = False
    ) -> float:
        """
        Calculate relevance score for a chunk.

        Scoring factors (max 1.0):
        - Target section match: +0.35  (chunk is in the exact mapped section)
        - Query mapping match: +0.15   (document matched via query_mappings)
        - Keyword match: +0.10         (document matched via keywords)
        - Title bigram/word match: 0-0.15
        - Content bigram/word match: 0-0.20
        - Exact phrase in content: +0.05
        """
        score = 0.0

        # Highest priority: chunk is in the exact target section
        if in_target_section:
            score += 0.35

        # Bonus for mapped documents (lower than before since section boost exists)
        if is_mapped:
            score += 0.15

        # Bonus for keyword matched documents
        if has_keyword:
            score += 0.10

        query_lower = query.lower()
        query_word_list = query_lower.split()
        query_words = set(query_word_list)
        query_bigrams = set(self._get_bigrams(query_word_list))

        # --- Title matching (bigrams + words) ---
        title_lower = chunk["title"].lower()
        title_word_list = title_lower.split()
        title_words = set(title_word_list)
        title_bigrams = set(self._get_bigrams(title_word_list))

        # Bigram overlap in title (stronger signal)
        if query_bigrams and title_bigrams:
            bigram_overlap = len(query_bigrams & title_bigrams)
            if bigram_overlap > 0:
                score += min(bigram_overlap / len(query_bigrams), 1.0) * 0.10

        # Word overlap in title
        if query_words:
            title_overlap = len(query_words & title_words) / len(query_words)
            score += title_overlap * 0.05

        # --- Content matching (bigrams + words) ---
        content_lower = chunk["content"].lower()
        content_word_list = content_lower.split()
        content_words = set(content_word_list)
        content_bigrams = set(self._get_bigrams(content_word_list))

        # Bigram overlap in content (stronger than single words)
        if query_bigrams and content_bigrams:
            bigram_overlap = len(query_bigrams & content_bigrams)
            if bigram_overlap > 0:
                score += min(bigram_overlap / len(query_bigrams), 1.0) * 0.10

        # Word overlap in content
        if query_words:
            word_overlap = len(query_words & content_words)
            if word_overlap > 0:
                score += min(word_overlap / len(query_words), 1.0) * 0.10

        # Exact phrase match bonus
        if query_lower in content_lower:
            score += 0.05

        return min(score, 1.0)

    async def index_document(
        self,
        content: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add/update a document dynamically.

        For this provider, we recommend editing the files directly
        and reloading, but this method supports runtime updates.
        """
        doc_id = metadata.get("id", source.replace(" ", "_").lower()) if metadata else source.replace(" ", "_").lower()

        # Create minimal document meta
        doc = DocumentMeta(
            id=doc_id,
            file=f"{doc_id}.md",
            title=metadata.get("title", source) if metadata else source,
            description=metadata.get("description", "") if metadata else "",
            keywords=metadata.get("keywords", []) if metadata else [],
            sections=[],
            effective_date="",
            content=content
        )

        doc.chunks = self._parse_chunks(content, doc_id)
        self._documents[doc_id] = doc

        # Update keyword index
        for keyword in doc.keywords:
            keyword_lower = keyword.lower()
            if keyword_lower not in self._all_keywords:
                self._all_keywords[keyword_lower] = []
            if doc_id not in self._all_keywords[keyword_lower]:
                self._all_keywords[keyword_lower].append(doc_id)

        logger.info(f"Indexed document: {doc_id} with {len(doc.chunks)} chunks")
        return True

    # === Helper Methods ===

    def get_document(self, doc_id: str) -> Optional[DocumentMeta]:
        """Get a specific document by ID"""
        return self._documents.get(doc_id)

    def get_full_content(self, doc_id: str) -> Optional[str]:
        """Get full content of a document"""
        doc = self._documents.get(doc_id)
        return doc.content if doc else None

    def list_documents(self) -> List[Dict[str, str]]:
        """List all available documents"""
        return [
            {
                "id": doc.id,
                "title": doc.title,
                "description": doc.description
            }
            for doc in self._documents.values()
        ]

    async def get_context_for_query(
        self,
        query: str,
        max_chunks: int = 3,
        include_full_doc: bool = False
    ) -> str:
        """
        Get formatted context for LLM.

        Args:
            query: User's question
            max_chunks: Max chunks to include
            include_full_doc: If True and only 1 relevant doc, include full content

        Returns:
            Formatted context string
        """
        result = await self.retrieve(query, top_k=max_chunks)

        if not result.chunks:
            return "Không tìm thấy thông tin liên quan trong các quy định của công ty."

        # Check if all chunks are from same document
        doc_ids = set(c.metadata["doc_id"] for c in result.chunks)

        if include_full_doc and len(doc_ids) == 1:
            # Return full document for small docs
            doc_id = list(doc_ids)[0]
            doc = self._documents.get(doc_id)
            if doc and len(doc.content) < 15000:  # ~4000 tokens
                return f"### Tài liệu tham khảo: {doc.title}\n\n{doc.content}"

        # Return combined chunks
        context = "### Thông tin tham khảo từ quy định công ty:\n\n"
        for i, chunk in enumerate(result.chunks, 1):
            context += f"**[{i}] {chunk.source}**\n{chunk.content}\n\n---\n\n"

        return context

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return sum(len(d.chunks) for d in self._documents.values())
