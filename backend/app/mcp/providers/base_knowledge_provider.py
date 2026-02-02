# app/mcp/providers/base_knowledge_provider.py
"""
Base Knowledge Provider
=======================
Abstract base cho các knowledge providers như:
- RAG (Retrieval Augmented Generation)
- Vector databases
- Document stores
- FAQ systems

Được thiết kế để dễ dàng mở rộng cho các use cases sau:
- Company knowledge base
- Product documentation
- FAQ chatbot
- Policy documents
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus


class RetrievalStrategy(str, Enum):
    """Strategies for retrieving knowledge"""
    SEMANTIC = "semantic"      # Vector similarity search
    KEYWORD = "keyword"        # Traditional keyword search
    HYBRID = "hybrid"          # Combination of both
    EXACT = "exact"           # Exact match only


@dataclass
class KnowledgeChunk:
    """
    A single piece of knowledge/content.

    Attributes:
        content: The actual text content
        source: Where this came from (file, URL, etc.)
        metadata: Additional info (page number, section, etc.)
        score: Relevance score (0-1)
    """
    content: str
    source: str
    metadata: Dict[str, Any]
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
            "score": self.score
        }


@dataclass
class RetrievalResult:
    """
    Result from knowledge retrieval.

    Attributes:
        chunks: List of relevant knowledge chunks
        query: Original query
        total_found: Total matches found
    """
    chunks: List[KnowledgeChunk]
    query: str
    total_found: int

    @property
    def best_chunk(self) -> Optional[KnowledgeChunk]:
        """Get the highest scoring chunk"""
        if not self.chunks:
            return None
        return max(self.chunks, key=lambda c: c.score)

    def get_combined_content(self, max_chunks: int = 5) -> str:
        """Combine top chunks into single context"""
        top_chunks = sorted(self.chunks, key=lambda c: c.score, reverse=True)[:max_chunks]
        return "\n\n---\n\n".join([c.content for c in top_chunks])


class BaseKnowledgeProvider(BaseProvider):
    """
    Abstract base class cho knowledge providers.

    Implement class này để tạo:
    - RAG systems với vector databases
    - Document search systems
    - FAQ retrieval systems
    - Any knowledge-based retrieval

    Example implementation:
        class ChromaDBProvider(BaseKnowledgeProvider):
            async def retrieve(self, query, top_k=5):
                results = self.collection.query(query, n_results=top_k)
                chunks = [KnowledgeChunk(...) for r in results]
                return RetrievalResult(chunks=chunks, query=query, total_found=len(chunks))

            async def index_document(self, content, source, metadata):
                self.collection.add(documents=[content], metadatas=[metadata])
                return True
    """

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        strategy: RetrievalStrategy = RetrievalStrategy.SEMANTIC
    ):
        super().__init__(config)
        self._strategy = strategy

    @property
    def strategy(self) -> RetrievalStrategy:
        return self._strategy

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """
        Retrieve relevant knowledge chunks for a query.

        Args:
            query: Search query
            top_k: Number of results to return
            filters: Optional filters (source, date, category, etc.)

        Returns:
            RetrievalResult with matching chunks
        """
        pass

    @abstractmethod
    async def index_document(
        self,
        content: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a document to the knowledge base.

        Args:
            content: Document content
            source: Source identifier
            metadata: Additional metadata

        Returns:
            True if successful
        """
        pass

    async def search_and_format(
        self,
        query: str,
        top_k: int = 3
    ) -> str:
        """
        Search and return formatted context for LLM.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            Formatted string with context
        """
        result = await self.retrieve(query, top_k)

        if not result.chunks:
            return "Không tìm thấy thông tin liên quan."

        formatted = f"### Thông tin tham khảo ({len(result.chunks)} nguồn):\n\n"
        for i, chunk in enumerate(result.chunks[:top_k], 1):
            formatted += f"**[{i}] {chunk.source}**\n{chunk.content}\n\n"

        return formatted


class SimpleRAGProvider(BaseKnowledgeProvider):
    """
    Simple in-memory RAG provider for testing/development.

    Sử dụng TF-IDF cho keyword matching.
    Trong production, nên sử dụng ChromaDB, Pinecone, etc.

    Usage:
        provider = SimpleRAGProvider()
        await provider.initialize()

        # Index documents
        await provider.index_document("Python là ngôn ngữ lập trình...", "python_intro.md")
        await provider.index_document("Async programming trong Python...", "async_guide.md")

        # Retrieve
        result = await provider.retrieve("async là gì")
        print(result.best_chunk.content)
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(
            config or ProviderConfig(name="simple_rag"),
            strategy=RetrievalStrategy.KEYWORD
        )
        self._documents: List[Dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "simple_rag"

    async def initialize(self) -> None:
        self._documents = []
        self._status = ProviderStatus.HEALTHY

    async def health_check(self) -> ProviderStatus:
        self._status = ProviderStatus.HEALTHY
        return self._status

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """Simple keyword-based retrieval"""
        query_terms = set(query.lower().split())

        scored_docs = []
        for doc in self._documents:
            content_terms = set(doc['content'].lower().split())
            # Simple Jaccard similarity
            intersection = query_terms & content_terms
            union = query_terms | content_terms
            score = len(intersection) / len(union) if union else 0

            if score > 0:
                chunk = KnowledgeChunk(
                    content=doc['content'],
                    source=doc['source'],
                    metadata=doc.get('metadata', {}),
                    score=score
                )
                scored_docs.append(chunk)

        # Sort by score
        scored_docs.sort(key=lambda x: x.score, reverse=True)

        return RetrievalResult(
            chunks=scored_docs[:top_k],
            query=query,
            total_found=len(scored_docs)
        )

    async def index_document(
        self,
        content: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Add document to in-memory store"""
        self._documents.append({
            'content': content,
            'source': source,
            'metadata': metadata or {}
        })
        return True

    async def clear_index(self) -> bool:
        """Clear all indexed documents"""
        self._documents = []
        return True

    @property
    def document_count(self) -> int:
        return len(self._documents)
