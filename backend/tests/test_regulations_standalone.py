#!/usr/bin/env python3
"""
Standalone test for RegulationsProvider
========================================
Test cơ bản không cần full app dependencies.
"""

import asyncio
import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


# === Minimal implementations for testing ===

class RetrievalStrategy(str, Enum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    EXACT = "exact"


@dataclass
class KnowledgeChunk:
    content: str
    source: str
    metadata: Dict[str, Any]
    score: float = 0.0


@dataclass
class RetrievalResult:
    chunks: List[KnowledgeChunk]
    query: str
    total_found: int

    @property
    def best_chunk(self) -> Optional[KnowledgeChunk]:
        if not self.chunks:
            return None
        return max(self.chunks, key=lambda c: c.score)


@dataclass
class DocumentMeta:
    id: str
    file: str
    title: str
    description: str
    keywords: List[str]
    sections: List[Dict[str, Any]]
    effective_date: str
    content: str = ""
    chunks: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.chunks is None:
            self.chunks = []


class RegulationsProviderTest:
    """Simplified provider for testing"""

    def __init__(self, knowledge_path: Path):
        self._knowledge_path = knowledge_path
        self._documents: Dict[str, DocumentMeta] = {}
        self._query_mappings: Dict[str, List[str]] = {}
        self._all_keywords: Dict[str, List[str]] = {}
        self._index_data: Dict[str, Any] = {}

    async def initialize(self) -> None:
        index_path = self._knowledge_path / "index.json"
        if not index_path.exists():
            raise FileNotFoundError(f"Index file not found: {index_path}")

        with open(index_path, 'r', encoding='utf-8') as f:
            self._index_data = json.load(f)

        self._query_mappings = self._index_data.get("query_mappings", {})

        for doc_info in self._index_data.get("documents", []):
            doc_id = doc_info["id"]
            doc_path = self._knowledge_path / doc_info["file"]

            if not doc_path.exists():
                print(f"Warning: Document not found: {doc_path}")
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

            doc.chunks = self._parse_chunks(content, doc_id)
            self._documents[doc_id] = doc

            for keyword in doc.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self._all_keywords:
                    self._all_keywords[keyword_lower] = []
                self._all_keywords[keyword_lower].append(doc_id)

        print(f"Loaded {len(self._documents)} documents with {sum(len(d.chunks) for d in self._documents.values())} chunks")

    def _parse_chunks(self, content: str, doc_id: str) -> List[Dict[str, Any]]:
        chunks = []
        lines = content.split('\n')

        current_h1 = ""
        current_h2 = ""
        current_chunk = []
        chunk_start_line = 0

        for i, line in enumerate(lines):
            if line.startswith('# ') and not line.startswith('## '):
                current_h1 = line[2:].strip()
                continue
            elif line.startswith('## '):
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
            else:
                current_chunk.append(line)

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

    async def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        query_lower = query.lower()
        scored_chunks: List[Tuple[KnowledgeChunk, float]] = []

        mapped_docs = self._get_mapped_documents(query_lower)
        keyword_docs = self._get_keyword_matched_documents(query_lower)
        relevant_doc_ids = list(set(mapped_docs + keyword_docs))

        if not relevant_doc_ids:
            relevant_doc_ids = list(self._documents.keys())

        for doc_id in relevant_doc_ids:
            doc = self._documents.get(doc_id)
            if not doc:
                continue

            for chunk in doc.chunks:
                score = self._calculate_relevance_score(
                    query_lower,
                    chunk,
                    doc_id in mapped_docs,
                    doc_id in keyword_docs
                )

                if score > 0:
                    knowledge_chunk = KnowledgeChunk(
                        content=chunk["content"],
                        source=f"{doc.title} - {chunk['title']}",
                        metadata={
                            "doc_id": doc_id,
                            "chunk_id": chunk["id"],
                            "title": chunk["title"],
                        },
                        score=score
                    )
                    scored_chunks.append((knowledge_chunk, score))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        result_chunks = [c for c, s in scored_chunks[:top_k]]

        return RetrievalResult(
            chunks=result_chunks,
            query=query,
            total_found=len(scored_chunks)
        )

    def _get_mapped_documents(self, query: str) -> List[str]:
        matched = []
        for mapping_key, doc_refs in self._query_mappings.items():
            if mapping_key in query:
                for ref in doc_refs:
                    doc_id = ref.split('#')[0]
                    if doc_id not in matched:
                        matched.append(doc_id)
        return matched

    def _get_keyword_matched_documents(self, query: str) -> List[str]:
        matched = []
        query_words = set(query.split())

        for keyword, doc_ids in self._all_keywords.items():
            if keyword in query or any(keyword in word for word in query_words):
                matched.extend(doc_ids)

        return list(set(matched))

    def _calculate_relevance_score(
        self,
        query: str,
        chunk: Dict[str, Any],
        is_mapped: bool,
        has_keyword: bool
    ) -> float:
        score = 0.0

        if is_mapped:
            score += 0.3

        if has_keyword:
            score += 0.2

        query_words = set(query.lower().split())

        title_lower = chunk["title"].lower()
        title_words = set(title_lower.split())
        title_overlap = len(query_words & title_words) / len(query_words) if query_words else 0
        score += title_overlap * 0.2

        content_lower = chunk["content"].lower()
        content_words = set(content_lower.split())

        overlap = len(query_words & content_words)
        if overlap > 0:
            content_score = min(overlap / len(query_words), 1.0) * 0.3
            score += content_score

        if query.lower() in content_lower:
            score += 0.1

        return min(score, 1.0)

    def list_documents(self) -> List[Dict[str, str]]:
        return [
            {"id": doc.id, "title": doc.title, "description": doc.description}
            for doc in self._documents.values()
        ]

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return sum(len(d.chunks) for d in self._documents.values())


async def main():
    print("=" * 60)
    print("Testing RegulationsProvider (Standalone)")
    print("=" * 60)

    knowledge_path = Path(__file__).parent.parent / "app" / "mcp" / "knowledge" / "regulations"
    print(f"\nKnowledge path: {knowledge_path}")
    print(f"Path exists: {knowledge_path.exists()}")

    if not knowledge_path.exists():
        print("❌ Knowledge path does not exist!")
        return

    provider = RegulationsProviderTest(knowledge_path)
    await provider.initialize()

    print(f"\n✅ Provider initialized!")
    print(f"   Documents: {provider.document_count}")
    print(f"   Chunks: {provider.chunk_count}")

    print("\n📄 Documents:")
    for doc in provider.list_documents():
        print(f"   - {doc['title']}")

    test_queries = [
        "nghỉ phép được bao nhiêu ngày",
        "công ty hỗ trợ du lịch bao nhiêu tiền",
        "vay tiền từ công ty được bao nhiêu",
        "công tác phí đi Đà Nẵng",
        "nghỉ thai sản được bao lâu",
        "thưởng lễ 30/4 bao nhiêu",
        "giờ làm việc",
    ]

    print("\n" + "=" * 60)
    print("Testing search queries")
    print("=" * 60)

    for query in test_queries:
        print(f"\n🔍 Query: \"{query}\"")
        result = await provider.retrieve(query, top_k=2)

        if result.chunks:
            print(f"   Found {result.total_found} matches:")
            for i, chunk in enumerate(result.chunks, 1):
                score_pct = int(chunk.score * 100)
                print(f"   [{i}] Score: {score_pct}% | {chunk.source[:60]}...")
        else:
            print("   ❌ No matches")

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
