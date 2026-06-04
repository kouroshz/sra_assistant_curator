#!/usr/bin/env python3

"""
Run the optional API-based agentic curator on ONE input packet.

This is intentionally single-packet only for pilot testing.

Safety:
  - API disabled by default unless AGENTIC_AI_ENABLE_API=1
  - does not modify master workbook
  - does not modify group-level curator table
  - writes suggestions only to outputs/04_AGENTIC_AI_ASSIST/
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/input_packets/agentic_ai_packet_index.tsv")
DEFAULT_OUT_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_suggestions")
DEFAULT_MODEL = "gpt-5.4-mini"


def read_text(path: Path, max_chars: int = 60000) -> str:
    text = path.read_text(errors="replace")
    return text[:max_chars]


def extract_pdf_text(pdf_path: Path, max_chars: int = 120000) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:
        return f"[PDF text extraction unavailable: {e}]"

    try:
        reader = PdfReader(str(pdf_path))
        chunks = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                chunks.append(f"\n\n--- PDF page {i + 1} ---\n{txt}")
            if sum(len(c) for c in chunks) >= max_chars:
                break
        out = "".join(chunks).strip()
        return out[:max_chars] if out else "[No text extracted from PDF.]"
    except Exception as e:
        return f"[PDF text extraction failed for {pdf_path}: {e}]"


def load_packet(packet_path: Path) -> dict:
    with open(packet_path) as fh:
        return json.load(fh)


def make_prompt(packet: dict, pdf_texts: dict[str, str]) -> str:
    trimmed_packet = dict(packet)

    # Keep row examples and metadata, but remove verbose schema? No, keep schema.
    packet_json = json.dumps(trimmed_packet, indent=2)

    pdf_block_parts = []
    for path, text in pdf_texts.items():
        pdf_block_parts.append(f"\n\n===== BEGIN PDF TEXT: {path} =====\n{text}\n===== END PDF TEXT =====")
    pdf_block = "\n".join(pdf_block_parts) if pdf_block_parts else "[No matching PDF text was available.]"

    return f"""
You are an expert assistant helping curate public Plasmodium SRA metadata.

You must return ONLY valid JSON. No markdown. No prose outside JSON.

Your job:
- use the packet metadata
- use the PDF text if available
- identify what the sample group represents
- suggest corrected metadata
- flag ambiguity
- reduce human curator burden
- do not invent facts
- if evidence is weak, say so clearly

Required JSON keys:
{json.dumps(packet.get("ai_output_schema", {}), indent=2)}

Important:
- ai_* fields are suggestions only.
- Human curators make final decisions.
- If the packet/PDF lacks enough evidence, use "unknown" or "insufficient_evidence".
- Keep evidence quotes short.
- Prefer precise paper section/table/figure/page references when visible.

===== BEGIN PACKET JSON =====
{packet_json}
===== END PACKET JSON =====

===== BEGIN PAPER TEXT CONTEXT =====
{pdf_block}
===== END PAPER TEXT CONTEXT =====
""".strip()


def safe_json_loads(s: str) -> dict:
    s = s.strip()

    # Handle accidental fenced JSON.
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].strip()

    try:
        return json.loads(s)
    except Exception:
        # Attempt to recover the first JSON object.
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start : end + 1])
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True, help="Path to one packet JSON.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-pdf-chars", type=int, default=120000)
    parser.add_argument("--dry-run", action="store_true", help="Write prompt only; do not call API.")
    args = parser.parse_args()

    load_dotenv(Path(".env"))

    if os.getenv("AGENTIC_AI_ENABLE_API", "0") != "1" and not args.dry_run:
        raise RuntimeError(
            "API usage is disabled by default. Set AGENTIC_AI_ENABLE_API=1 only when intentionally running API-assisted curation."
        )

    packet = load_packet(args.packet)
    group_id = packet.get("curation_group_id", args.packet.stem)

    pdf_texts = {}
    for pdf in packet.get("paper_context", {}).get("paper_pdf_candidates", []):
        p = Path(pdf)
        if p.exists():
            pdf_texts[str(p)] = extract_pdf_text(p, max_chars=args.max_pdf_chars)

    prompt = make_prompt(packet, pdf_texts)

    out_base = args.out_dir / group_id
    out_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prompt_path = out_base / f"{group_id}.prompt.{timestamp}.txt"
    raw_path = out_base / f"{group_id}.raw_response.{timestamp}.txt"
    json_path = out_base / f"{group_id}.ai_suggestion.{timestamp}.json"
    audit_path = out_base / f"{group_id}.audit.{timestamp}.json"

    prompt_path.write_text(prompt)

    if args.dry_run:
        print(f"Dry run. Wrote prompt: {prompt_path}")
        return

    model = args.model or os.getenv("OPENAI_SMALL_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL

    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
    )

    raw = response.output_text
    raw_path.write_text(raw)

    parsed = safe_json_loads(raw)
    json_path.write_text(json.dumps(parsed, indent=2))

    audit = {
        "timestamp": timestamp,
        "model": model,
        "packet": str(args.packet),
        "curation_group_id": group_id,
        "prompt_path": str(prompt_path),
        "raw_response_path": str(raw_path),
        "json_output_path": str(json_path),
        "pdfs_used": list(pdf_texts.keys()),
    }
    audit_path.write_text(json.dumps(audit, indent=2))

    print(f"Wrote AI suggestion JSON: {json_path}")
    print(f"Wrote raw response:       {raw_path}")
    print(f"Wrote audit:              {audit_path}")


if __name__ == "__main__":
    main()
