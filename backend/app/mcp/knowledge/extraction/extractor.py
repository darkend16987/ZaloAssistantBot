# app/mcp/knowledge/extraction/extractor.py
"""
Offline Entity Extraction Runner
================================
Sử dụng langextract để trích xuất kiến thức có cấu trúc từ
các văn bản quy định của công ty.

Chạy offline khi tài liệu được cập nhật:
    cd backend
    python -m app.mcp.knowledge.extraction.extractor

Output: knowledge/extracted/entities.json
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Paths
KNOWLEDGE_DIR = Path(__file__).parent.parent / "regulations"
OUTPUT_DIR = Path(__file__).parent.parent / "extracted"


def _get_model_id() -> str:
    """Get the model ID for extraction from env or default."""
    return os.getenv("GEMINI_KNOWLEDGE_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _get_api_key() -> str:
    """Get the Google API key from env or settings."""
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        try:
            from app.core.settings import settings
            key = settings.GOOGLE_API_KEY.get_secret_value()
        except Exception:
            pass
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not set. Set it in .env or environment.")
    return key


def extract_document_with_langextract(md_path: Path) -> Dict[str, Any]:
    """
    Extract structured entities from a single markdown document using langextract.

    Args:
        md_path: Path to the markdown document

    Returns:
        Dict with source_file, entity_count, entities
    """
    import langextract as lx
    from .schemas import ALL_EXAMPLES, REGULATION_EXTRACTION_PROMPT

    text = md_path.read_text(encoding="utf-8")
    model_id = _get_model_id()

    print(f"    Using model: {model_id}")
    print(f"    Document size: {len(text)} chars")

    # Build examples in langextract format
    examples = []
    for ex in ALL_EXAMPLES:
        examples.append(lx.ExampleData(
            text=ex["text"],
            extractions=[
                lx.Extraction(
                    extraction_class=ext["class"],
                    extraction_text=ext["text"],
                    attributes=ext["attributes"]
                )
                for ext in ex["extractions"]
            ]
        ))

    # Run extraction
    result = lx.extract(
        text_or_documents=text,
        prompt_description=REGULATION_EXTRACTION_PROMPT,
        examples=examples,
        model_id=model_id,
        extraction_passes=2,        # 2 passes for better recall
        max_char_buffer=3000,       # larger chunks for regulation context
        max_workers=3,
        use_schema_constraints=True,
    )

    # Convert to serializable format
    entities = []
    for ext in result.extractions:
        entity = {
            "class": ext.extraction_class,
            "text": ext.extraction_text,
            "attributes": ext.attributes if ext.attributes else {},
        }
        # Add source grounding if available
        if hasattr(ext, 'char_interval') and ext.char_interval:
            entity["start_pos"] = ext.char_interval.start_pos
            entity["end_pos"] = ext.char_interval.end_pos
        if hasattr(ext, 'alignment_status') and ext.alignment_status:
            entity["alignment"] = ext.alignment_status.name

        entities.append(entity)

    return {
        "source_file": md_path.name,
        "model_used": model_id,
        "entity_count": len(entities),
        "entities": entities,
    }


def extract_document_with_gemini(md_path: Path) -> Dict[str, Any]:
    """
    Fallback: Extract structured entities using raw Gemini API
    when langextract is not installed.

    Uses the same schema concepts but via direct prompt engineering.
    """
    import google.generativeai as genai
    from .schemas import ALL_EXAMPLES, REGULATION_EXTRACTION_PROMPT

    text = md_path.read_text(encoding="utf-8")
    model_id = _get_model_id()
    api_key = _get_api_key()

    print(f"    Using model: {model_id} (direct Gemini fallback)")
    print(f"    Document size: {len(text)} chars")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_id)

    # Build few-shot examples as text
    examples_text = ""
    for i, ex in enumerate(ALL_EXAMPLES[:4], 1):  # Use first 4 examples
        examples_text += f"\n--- Example {i} ---\n"
        examples_text += f"INPUT TEXT: {ex['text'][:200]}...\n"
        examples_text += f"EXTRACTED: {json.dumps(ex['extractions'], ensure_ascii=False, indent=2)}\n"

    prompt = f"""{REGULATION_EXTRACTION_PROMPT}

### FEW-SHOT EXAMPLES ###
{examples_text}

### DOCUMENT TO EXTRACT ###
{text}

### OUTPUT FORMAT ###
Return a JSON array of extracted entities. Each entity must have:
- "class": entity class (LeaveRule, WorkingTimeRule, BenefitRule, DisciplinaryRule, FinancialRule, ProcedureRule)
- "text": exact text from document (verbatim)
- "attributes": dict of key-value pairs as described above

Return ONLY valid JSON array, no other text. No markdown fences."""

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(temperature=0.1)
    )

    # Parse response
    response_text = response.text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0]

    entities = json.loads(response_text)

    return {
        "source_file": md_path.name,
        "model_used": model_id,
        "entity_count": len(entities),
        "entities": entities,
    }


def run_extraction(use_langextract: bool = True) -> Dict[str, Any]:
    """
    Extract all regulation documents.

    Args:
        use_langextract: If True, use langextract library. If False, use direct Gemini.

    Returns:
        Dict of doc_id -> extraction results
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    md_files = list(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        print("No markdown documents found in", KNOWLEDGE_DIR)
        return {}

    print(f"Found {len(md_files)} documents to extract")

    # Check if langextract is available
    if use_langextract:
        try:
            import langextract  # noqa: F401
            extract_fn = extract_document_with_langextract
            print("Using langextract library")
        except ImportError:
            print("langextract not installed, using direct Gemini fallback")
            extract_fn = extract_document_with_gemini
    else:
        extract_fn = extract_document_with_gemini
        print("Using direct Gemini extraction")

    all_results = {}
    total_entities = 0

    for md_path in sorted(md_files):
        doc_id = md_path.stem
        print(f"\n  Extracting: {md_path.name}")

        try:
            result = extract_fn(md_path)
            all_results[doc_id] = result
            total_entities += result["entity_count"]
            print(f"    -> {result['entity_count']} entities extracted")
        except Exception as e:
            print(f"    -> ERROR: {e}")
            all_results[doc_id] = {
                "source_file": md_path.name,
                "entity_count": 0,
                "entities": [],
                "error": str(e)
            }

    # Save combined output
    output_path = OUTPUT_DIR / "entities.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {total_entities} entities from {len(md_files)} documents")
    print(f"Saved to {output_path}")
    return all_results


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Extract structured entities from regulation docs")
    parser.add_argument("--no-langextract", action="store_true",
                        help="Use direct Gemini instead of langextract")
    args = parser.parse_args()

    # Load .env if running standalone
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    run_extraction(use_langextract=not args.no_langextract)


if __name__ == "__main__":
    main()
