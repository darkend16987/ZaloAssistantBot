# app/mcp/knowledge/indexing/indexer.py
"""
Offline Tree Index Builder
==========================
Sử dụng PageIndex (hoặc Gemini fallback) để sinh tree index
cho các văn bản quy định.

Chạy offline khi tài liệu được cập nhật:
    cd backend
    python -m app.mcp.knowledge.indexing.indexer

Output: knowledge/indexed/<doc_name>_tree.json
"""

import json
from pathlib import Path
from typing import Dict, Any

from .pageindex_adapter import build_tree_from_markdown

KNOWLEDGE_DIR = Path(__file__).parent.parent / "regulations"
OUTPUT_DIR = Path(__file__).parent.parent / "indexed"


def count_nodes(nodes: list) -> int:
    """Recursively count all nodes in the tree."""
    count = len(nodes)
    for node in nodes:
        count += count_nodes(node.get("nodes", []))
    return count


def build_indexes() -> Dict[str, Any]:
    """
    Build tree indexes for all markdown documents.

    Returns:
        Dict of doc_id -> {node_count, output_path}
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        print("No markdown documents found in", KNOWLEDGE_DIR)
        return {}

    print(f"Found {len(md_files)} documents to index")

    results = {}

    for md_path in sorted(md_files):
        doc_id = md_path.stem
        print(f"\n  Building tree: {md_path.name}")

        try:
            tree = build_tree_from_markdown(str(md_path))

            output_path = OUTPUT_DIR / f"{doc_id}_tree.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False, indent=2)

            node_count = count_nodes(tree.get("structure", []))
            print(f"    -> {node_count} nodes in tree")
            print(f"    -> Saved to {output_path}")

            results[doc_id] = {
                "node_count": node_count,
                "output_path": str(output_path),
            }

        except Exception as e:
            print(f"    -> ERROR: {e}")
            results[doc_id] = {
                "node_count": 0,
                "error": str(e),
            }

    total_nodes = sum(r.get("node_count", 0) for r in results.values())
    print(f"\nTotal: {total_nodes} nodes from {len(md_files)} documents")
    print(f"All trees saved to {OUTPUT_DIR}")

    return results


def main():
    """CLI entry point."""
    # Load .env if running standalone
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    build_indexes()


if __name__ == "__main__":
    main()
