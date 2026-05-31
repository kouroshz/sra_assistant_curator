#!/usr/bin/env python3

from pathlib import Path
import argparse
import json
import os
import pandas as pd
from typing import Literal
from pydantic import BaseModel
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


class FieldUpdate(BaseModel):
    field: str
    value: str
    confidence: Literal["high", "medium", "low"]
    rationale: str
    evidence: str


class RowSuggestion(BaseModel):
    Run: str
    action: Literal["no_action", "confirm", "review", "suggest_update"]
    confidence: Literal["high", "medium", "low"]
    needs_human_review: Literal["yes", "no"]
    curator_note: str
    evidence: str
    suggested_field_updates: list[FieldUpdate]


class GroupSuggestion(BaseModel):
    group_label: str
    runs: list[str]
    suggestion: str
    confidence: Literal["high", "medium", "low"]
    needs_human_review: Literal["yes", "no"]
    evidence: str


class CuratorOutput(BaseModel):
    pmid: str
    paper_summary_note: str
    experimental_design_note: str
    metadata_confirmation_note: str
    control_logic_note: str
    paper_omics_used: list[str]
    paper_omics_mentioned_not_used: list[str]
    fields_confirmed: list[str]
    fields_uncertain: list[str]
    group_suggestions: list[GroupSuggestion]
    row_suggestions: list[RowSuggestion]
    curator_warnings: list[str]


def clean(x):
    return str(x).strip()


def pydantic_to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--mode", choices=["paper-summary", "curator"], default="curator")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""))
    parser.add_argument("--max-packet-chars", type=int, default=120000)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    if not args.model:
        raise ValueError("Set --model or export OPENAI_MODEL first.")

    packet_file = OUT / f"PMID_{pmid}_llm_packet.json"
    if not packet_file.exists():
        raise FileNotFoundError(f"Missing packet: {packet_file}. Run script 10 first.")

    packet_text = packet_file.read_text(encoding="utf-8")
    if len(packet_text) > args.max_packet_chars:
        packet_text = packet_text[:args.max_packet_chars] + "\n\n[PACKET_TRUNCATED]\n"

    if args.mode == "paper-summary":
        mode_instruction = """
Cheap mode:
- Do not produce many row-level suggestions.
- Focus on paper summary, experimental design, control logic, omics used, omics mentioned.
- Only suggest row updates if the paper explicitly contradicts or fills an important blank.
"""
    else:
        mode_instruction = """
Curator mode:
- Review group-level and row-level metadata.
- Focus on rows already flagged as needs_human_review.
- Confirm or question proposed controls.
- Suggest updates only for existing rows and allowed fields.
- Do not overwrite clear BioSample/GEO metadata unless the paper explicitly indicates a conflict.
"""

    system_prompt = f"""
You are an expert scientific metadata curator for public SRA/GEO parasite transcriptomics datasets.

Rules:
- Use BioSample/GEO/SRA metadata as primary evidence for row identity.
- Use the paper to confirm experimental design, controls, treatments, stages, strains, omics, and ambiguous cases.
- Do not add new rows.
- Do not invent missing data.
- If the paper does not support a field, say it needs human review.
- Keep notes concise and useful for a postdoc curator.
- Suggested updates are suggestions only.
- Evidence should be short and specific, preferably mentioning paper section/page context when available.
- Avoid long quotations.

{mode_instruction}
"""

    user_prompt = (
        "Return structured curator output for this PMID using the packet below.\n\n"
        + packet_text
    )

    client = OpenAI()

    response = client.responses.parse(
        model=args.model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        text_format=CuratorOutput,
    )

    parsed = response.output_parsed
    data = pydantic_to_dict(parsed)

    out_json = OUT / f"PMID_{pmid}_llm_curator_output.json"
    out_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    row_records = []
    for r in data.get("row_suggestions", []):
        row_records.append({
            "Run": r.get("Run", ""),
            "llm_action": r.get("action", ""),
            "llm_confidence": r.get("confidence", ""),
            "llm_needs_human_review": r.get("needs_human_review", ""),
            "llm_curator_note": r.get("curator_note", ""),
            "llm_evidence": r.get("evidence", ""),
            "llm_suggested_field_updates": json.dumps(r.get("suggested_field_updates", []), ensure_ascii=False),
        })

    group_records = []
    for g in data.get("group_suggestions", []):
        group_records.append({
            "group_label": g.get("group_label", ""),
            "runs": ";".join(g.get("runs", [])),
            "suggestion": g.get("suggestion", ""),
            "confidence": g.get("confidence", ""),
            "needs_human_review": g.get("needs_human_review", ""),
            "evidence": g.get("evidence", ""),
        })

    out_rows = OUT / f"PMID_{pmid}_llm_row_suggestions.tsv"
    out_groups = OUT / f"PMID_{pmid}_llm_group_suggestions.tsv"

    pd.DataFrame(row_records).to_csv(out_rows, sep="\t", index=False)
    pd.DataFrame(group_records).to_csv(out_groups, sep="\t", index=False)

    summary = pd.DataFrame([
        {"field": "paper_summary_note", "value": data.get("paper_summary_note", "")},
        {"field": "experimental_design_note", "value": data.get("experimental_design_note", "")},
        {"field": "metadata_confirmation_note", "value": data.get("metadata_confirmation_note", "")},
        {"field": "control_logic_note", "value": data.get("control_logic_note", "")},
        {"field": "paper_omics_used", "value": "; ".join(data.get("paper_omics_used", []))},
        {"field": "paper_omics_mentioned_not_used", "value": "; ".join(data.get("paper_omics_mentioned_not_used", []))},
        {"field": "fields_confirmed", "value": "; ".join(data.get("fields_confirmed", []))},
        {"field": "fields_uncertain", "value": "; ".join(data.get("fields_uncertain", []))},
        {"field": "curator_warnings", "value": "; ".join(data.get("curator_warnings", []))},
    ])

    out_summary = OUT / f"PMID_{pmid}_llm_summary.tsv"
    summary.to_csv(out_summary, sep="\t", index=False)

    print(f"\n=== LLM curator assist complete for PMID {pmid} ===")
    print(f"Mode: {args.mode}")
    print(f"Model: {args.model}")
    print(f"Group suggestions: {len(group_records)}")
    print(f"Row suggestions: {len(row_records)}")
    print("\nPaper summary:")
    print(data.get("paper_summary_note", ""))
    print("\nControl logic:")
    print(data.get("control_logic_note", ""))
    print("\nWarnings:")
    for w in data.get("curator_warnings", []):
        print(f"- {w}")

    print("\nWrote:")
    print(out_json)
    print(out_summary)
    print(out_rows)
    print(out_groups)


if __name__ == "__main__":
    main()
