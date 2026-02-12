# app/mcp/knowledge/indexing/pageindex_adapter.py
"""
PageIndex Gemini Adapter
========================
PageIndex là thư viện tree-indexing hardcode dùng OpenAI.
Module này cung cấp:

1. Gemini adapter: monkey-patch PageIndex utils để dùng Gemini
2. Fallback: nếu PageIndex không cài, dùng Gemini trực tiếp
   để sinh tree index từ markdown (prompt-based approach)

Cả 2 cách đều output cùng format JSON tree.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def _get_model_id() -> str:
    """Get model ID from env or default."""
    return os.getenv("GEMINI_KNOWLEDGE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _get_api_key() -> str:
    """Get Google API key."""
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        try:
            from app.core.settings import settings
            key = settings.GOOGLE_API_KEY.get_secret_value()
        except Exception:
            pass
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    return key


def _get_gemini_model():
    """Get configured Gemini model instance."""
    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    return genai.GenerativeModel(_get_model_id())


# ===================================================================
# Option A: PageIndex with Gemini monkey-patch
# ===================================================================

def _patch_pageindex_for_gemini():
    """
    Monkey-patch PageIndex's LLM call functions to use Gemini.

    PageIndex uses 2 functions in utils.py:
    - ChatGPT_API(model, prompt, api_key) -> str
    - ChatGPT_API_async(model, prompt, api_key) -> str
    """
    model = _get_gemini_model()

    def gemini_chat(model_name: str, prompt: str, api_key: str = None) -> str:
        response = model.generate_content(prompt)
        return response.text

    async def gemini_chat_async(model_name: str, prompt: str, api_key: str = None) -> str:
        response = await model.generate_content_async(prompt)
        return response.text

    import pageindex.utils as utils
    utils.ChatGPT_API = gemini_chat
    utils.ChatGPT_API_async = gemini_chat_async


def build_tree_with_pageindex(md_path: str) -> Dict[str, Any]:
    """
    Build tree using actual PageIndex library (patched for Gemini).

    Requires: pip install pageindex (or clone the repo)
    """
    import asyncio
    _patch_pageindex_for_gemini()

    from pageindex.page_index_md import md_to_tree

    model_id = _get_model_id()
    tree = asyncio.run(md_to_tree(
        md_path=md_path,
        if_thinning=False,
        if_add_node_summary="yes",
        model=model_id,
    ))

    return tree


# ===================================================================
# Option B: Direct Gemini tree generation (no PageIndex dependency)
# ===================================================================

def _parse_markdown_structure(content: str) -> List[Dict[str, Any]]:
    """
    Parse markdown headers into a preliminary tree structure.
    This mirrors what PageIndex's page_index_md.py does internally.

    Returns list of nodes with: title, level, line_start, line_end, text
    """
    lines = content.split('\n')
    nodes = []
    current_node = None

    for i, line in enumerate(lines):
        # Detect header level
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            # Close previous node
            if current_node is not None:
                current_node['line_end'] = i - 1
                current_node['text'] = '\n'.join(
                    lines[current_node['line_start']:i]
                ).strip()
                nodes.append(current_node)

            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            current_node = {
                'title': title,
                'level': level,
                'line_start': i,
                'line_end': i,
                'text': '',
            }

    # Close last node
    if current_node is not None:
        current_node['line_end'] = len(lines) - 1
        current_node['text'] = '\n'.join(
            lines[current_node['line_start']:]
        ).strip()
        nodes.append(current_node)

    return nodes


def _build_hierarchy(flat_nodes: List[Dict]) -> List[Dict[str, Any]]:
    """
    Convert flat list of nodes into nested tree using header levels.
    Uses a stack-based algorithm (same approach as PageIndex).
    """
    if not flat_nodes:
        return []

    # Assign node IDs
    for i, node in enumerate(flat_nodes):
        node['node_id'] = f"{i:04d}"

    # Build tree using stack
    root_nodes = []
    stack = []  # [(level, node)]

    for node in flat_nodes:
        tree_node = {
            'title': node['title'],
            'node_id': node['node_id'],
            'summary': '',  # Will be filled by LLM
            'start_index': node['line_start'],
            'end_index': node['line_end'],
            'text': node['text'],
            'nodes': [],
        }

        level = node['level']

        # Pop stack until we find parent
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Add as child of the top of stack
            stack[-1][1]['nodes'].append(tree_node)
        else:
            # Top-level node
            root_nodes.append(tree_node)

        stack.append((level, tree_node))

    return root_nodes


def _generate_summaries(tree_nodes: List[Dict], model) -> None:
    """
    Generate LLM summaries for each node in the tree (in-place).
    Leaf nodes get content summaries; parent nodes get structural summaries.
    """
    for node in tree_nodes:
        # Recursively process children first
        if node.get('nodes'):
            _generate_summaries(node['nodes'], model)

        # Generate summary
        text = node.get('text', '')
        if len(text) < 50:
            node['summary'] = text
            continue

        # Truncate very long texts for summary
        text_for_summary = text[:3000] if len(text) > 3000 else text

        prompt = f"""Tóm tắt ngắn gọn (1-2 câu, tối đa 100 từ) nội dung chính của đoạn văn bản quy định sau.
Giữ nguyên các con số, thời hạn, điều kiện quan trọng.

TIÊU ĐỀ: {node['title']}

NỘI DUNG:
{text_for_summary}

TÓM TẮT:"""

        try:
            response = model.generate_content(prompt)
            node['summary'] = response.text.strip()
        except Exception as e:
            # Fallback: use first 100 chars
            node['summary'] = text[:100] + "..." if len(text) > 100 else text


def build_tree_with_gemini(md_path: str) -> Dict[str, Any]:
    """
    Build tree index directly using Gemini (no PageIndex dependency).

    This implements the same concept as PageIndex but simpler:
    1. Parse markdown headers into flat nodes
    2. Build hierarchy from header levels
    3. Generate LLM summaries for each node

    Args:
        md_path: Path to markdown file

    Returns:
        Tree structure dict compatible with PageIndex format
    """
    md_path = Path(md_path)
    content = md_path.read_text(encoding="utf-8")
    model = _get_gemini_model()

    print(f"    Using model: {_get_model_id()}")
    print(f"    Document size: {len(content)} chars")

    # Step 1: Parse markdown into flat nodes
    flat_nodes = _parse_markdown_structure(content)
    print(f"    Parsed {len(flat_nodes)} sections from headers")

    # Step 2: Build hierarchy
    tree_structure = _build_hierarchy(flat_nodes)

    # Step 3: Generate summaries
    print(f"    Generating summaries...")
    _generate_summaries(tree_structure, model)

    # Step 4: Generate document description
    titles = [n['title'] for n in flat_nodes[:10]]
    doc_description_prompt = f"""Mô tả ngắn gọn (1 câu) nội dung chính của tài liệu có các phần:
{chr(10).join('- ' + t for t in titles)}

MÔ TẢ:"""

    try:
        response = model.generate_content(doc_description_prompt)
        doc_description = response.text.strip()
    except Exception:
        doc_description = f"Tài liệu {md_path.stem}"

    return {
        "doc_name": md_path.stem,
        "doc_description": doc_description,
        "structure": tree_structure,
    }


# ===================================================================
# Public API: auto-select best method
# ===================================================================

def build_tree_from_markdown(md_path: str) -> Dict[str, Any]:
    """
    Build PageIndex-compatible tree from a markdown file.

    Automatically uses PageIndex if installed, otherwise falls back to
    direct Gemini approach.

    Args:
        md_path: Path to markdown file

    Returns:
        Tree structure dict with: doc_name, doc_description, structure[]
        Each node has: title, node_id, summary, start_index, end_index, text, nodes[]
    """
    try:
        import pageindex  # noqa: F401
        print("    Using PageIndex library (Gemini-patched)")
        return build_tree_with_pageindex(md_path)
    except ImportError:
        print("    Using direct Gemini tree generation")
        return build_tree_with_gemini(md_path)
