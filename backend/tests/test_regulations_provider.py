# tests/test_regulations_provider.py
"""
Test script for RegulationsProvider
===================================
Kiểm tra hoạt động của provider tra cứu quy định.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.mcp.providers.regulations_provider import RegulationsProvider


async def test_provider():
    """Test basic provider functionality"""
    print("=" * 60)
    print("Testing RegulationsProvider")
    print("=" * 60)

    # Initialize provider
    provider = RegulationsProvider()
    await provider.initialize()

    print(f"\n✅ Provider initialized successfully!")
    print(f"   - Documents loaded: {provider.document_count}")
    print(f"   - Total chunks: {provider.chunk_count}")

    # List documents
    print("\n📄 Available documents:")
    for doc in provider.list_documents():
        print(f"   - {doc['title']}")

    # Test queries
    test_queries = [
        "nghỉ phép được bao nhiêu ngày",
        "công ty hỗ trợ du lịch bao nhiêu tiền",
        "vay tiền từ công ty được bao nhiêu",
        "công tác phí đi Đà Nẵng",
        "nghỉ thai sản được bao lâu",
        "thưởng lễ 30/4 bao nhiêu",
        "giờ làm việc của công ty",
    ]

    print("\n" + "=" * 60)
    print("Testing search queries")
    print("=" * 60)

    for query in test_queries:
        print(f"\n🔍 Query: \"{query}\"")
        result = await provider.retrieve(query, top_k=2)

        if result.chunks:
            print(f"   Found {result.total_found} matches, showing top {len(result.chunks)}:")
            for i, chunk in enumerate(result.chunks, 1):
                score_pct = int(chunk.score * 100)
                title = chunk.metadata.get('title', 'Unknown')[:50]
                print(f"   [{i}] Score: {score_pct}% | {chunk.source[:60]}...")
        else:
            print("   ❌ No matches found")

    # Test context generation
    print("\n" + "=" * 60)
    print("Testing context generation")
    print("=" * 60)

    context = await provider.get_context_for_query(
        "nghỉ phép năm được bao nhiêu ngày",
        max_chunks=2,
        include_full_doc=False
    )
    print(f"\n📝 Generated context (first 500 chars):")
    print(context[:500] + "..." if len(context) > 500 else context)

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_provider())
