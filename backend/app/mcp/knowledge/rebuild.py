# app/mcp/knowledge/rebuild.py
"""
Knowledge Base Rebuild Pipeline
================================
Chạy langextract + PageIndex để regenerate tất cả indexes.

Usage:
    cd backend
    python -m app.mcp.knowledge.rebuild                   # Full rebuild
    python -m app.mcp.knowledge.rebuild --extract-only     # Only langextract
    python -m app.mcp.knowledge.rebuild --index-only       # Only PageIndex
    python -m app.mcp.knowledge.rebuild --no-langextract   # Use Gemini fallback for extraction

Pipeline:
    1. langextract: .md → entities.json (structured rules & facts)
    2. PageIndex:   .md → *_tree.json   (hierarchical tree with summaries)

Output is saved to:
    - knowledge/extracted/entities.json
    - knowledge/indexed/<doc_name>_tree.json

These files are loaded at runtime by EnhancedRegulationsProvider.
"""

import argparse
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild knowledge base indexes (langextract + PageIndex)"
    )
    parser.add_argument(
        "--extract-only", action="store_true",
        help="Only run langextract entity extraction"
    )
    parser.add_argument(
        "--index-only", action="store_true",
        help="Only run PageIndex tree indexing"
    )
    parser.add_argument(
        "--no-langextract", action="store_true",
        help="Use direct Gemini instead of langextract for extraction"
    )
    args = parser.parse_args()

    # Load .env
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded .env from {env_path}")
    except ImportError:
        print("python-dotenv not available, using environment variables directly")

    # Check API key
    import os
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set. Set it in .env or environment.")
        sys.exit(1)

    model = os.getenv("GEMINI_KNOWLEDGE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    print(f"Using model: {model}")
    print()

    start = time.time()
    errors = []

    # ===================================================================
    # STEP 1: Entity Extraction (langextract)
    # ===================================================================
    if not args.index_only:
        print("=" * 60)
        print("STEP 1: Entity Extraction (langextract)")
        print("=" * 60)

        try:
            from app.mcp.knowledge.extraction.extractor import run_extraction
            run_extraction(use_langextract=not args.no_langextract)
        except Exception as e:
            print(f"\nERROR in extraction: {e}")
            errors.append(f"Extraction: {e}")

        print()

    # ===================================================================
    # STEP 2: Tree Indexing (PageIndex)
    # ===================================================================
    if not args.extract_only:
        print("=" * 60)
        print("STEP 2: Tree Indexing (PageIndex)")
        print("=" * 60)

        try:
            from app.mcp.knowledge.indexing.indexer import build_indexes
            build_indexes()
        except Exception as e:
            print(f"\nERROR in indexing: {e}")
            errors.append(f"Indexing: {e}")

        print()

    # ===================================================================
    # Summary
    # ===================================================================
    elapsed = time.time() - start
    print("=" * 60)

    if errors:
        print(f"Completed with {len(errors)} error(s) in {elapsed:.1f}s:")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"Knowledge base rebuilt successfully in {elapsed:.1f}s")

    # Show output files
    extracted_dir = Path(__file__).parent / "extracted"
    indexed_dir = Path(__file__).parent / "indexed"

    if extracted_dir.exists():
        files = list(extracted_dir.glob("*.json"))
        print(f"\nExtracted: {len(files)} file(s) in {extracted_dir}")
        for f in files:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")

    if indexed_dir.exists():
        files = list(indexed_dir.glob("*.json"))
        print(f"\nIndexed: {len(files)} file(s) in {indexed_dir}")
        for f in files:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")

    print()


if __name__ == "__main__":
    main()
