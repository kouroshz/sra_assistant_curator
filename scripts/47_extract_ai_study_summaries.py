#!/usr/bin/env python3
"""
Extract study_summary and global_warnings from active validated AI curation JSONs.

Read-only. Does not modify AI outputs.

Inputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_packet_status_inventory.tsv
  latest PASS validation summaries
  active AI JSONs

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES.md
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pandas as pd


DEEP_QC = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")
PACKET_INV = DEEP_QC / "ai_packet_status_inventory.tsv"


def clean(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def metric_value_tsv(path: Path) -> dict[str, str]:
    df = read_tsv(path)
    if df.empty:
        return {}
    if {"metric", "value"}.issubset(df.columns):
        return {
            clean(r["metric"]): clean(r["value"])
            for _, r in df.iterrows()
            if clean(r.get("metric", ""))
        }
    return {c: clean(df.iloc[0].get(c, "")) for c in df.columns}


def as_joined(x) -> str:
    if x is None:
        return ""
    if isinstance(x, list):
        return " | ".join(clean(v) for v in x if clean(v))
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False)
    return clean(x)


def main() -> None:
    if not PACKET_INV.exists():
        raise FileNotFoundError(
            f"Missing {PACKET_INV}. Run scripts/43_deep_qc_ai_outputs.py first."
        )

    inv = read_tsv(PACKET_INV)
    pass_inv = inv[inv["latest_validation_status"] == "PASS"].copy()

    rows = []

    for _, r in pass_inv.iterrows():
        packet_id = clean(r.get("packet_id", ""))
        summary_path = Path(clean(r.get("latest_validation_summary", "")))

        if not summary_path.exists():
            rows.append({
                "packet_id": packet_id,
                "pmid": clean(r.get("pmid", "")),
                "bioproject": clean(r.get("bioproject", "")),
                "summary_status": "missing_validation_summary",
            })
            continue

        val = metric_value_tsv(summary_path)
        ai_json = Path(clean(val.get("ai_json", "")))

        if not ai_json.exists():
            rows.append({
                "packet_id": packet_id,
                "pmid": clean(r.get("pmid", "")),
                "bioproject": clean(r.get("bioproject", "")),
                "summary_status": "missing_ai_json",
                "ai_json": str(ai_json),
            })
            continue

        try:
            obj = json.loads(ai_json.read_text())
        except Exception as e:
            rows.append({
                "packet_id": packet_id,
                "pmid": clean(r.get("pmid", "")),
                "bioproject": clean(r.get("bioproject", "")),
                "summary_status": "json_read_error",
                "json_error": str(e),
                "ai_json": str(ai_json),
            })
            continue

        ss = obj.get("study_summary", {}) or {}
        if not isinstance(ss, dict):
            ss = {"raw_study_summary": ss}

        rows.append({
            "packet_id": packet_id,
            "pmid": clean(obj.get("pmid", "")) or clean(r.get("pmid", "")),
            "bioproject": clean(obj.get("bioproject", "")) or clean(r.get("bioproject", "")),
            "summary_status": "ok" if ss else "missing_study_summary",
            "ai_review_status": clean(obj.get("ai_review_status", "")),
            "assay_class_confirmed": clean(obj.get("assay_class_confirmed", "")),
            "one_sentence_summary": clean(ss.get("one_sentence_summary", "")),
            "study_goal": clean(ss.get("study_goal", "")),
            "organism_strain": clean(ss.get("organism_strain", "")),
            "assay_types": as_joined(ss.get("assay_types", "")),
            "main_comparisons_or_sample_axes": as_joined(ss.get("main_comparisons_or_sample_axes", "")),
            "paper_evidence_locations": as_joined(ss.get("paper_evidence_locations", "")),
            "raw_study_summary_json": json.dumps(ss, ensure_ascii=False),
            "global_warnings": as_joined(obj.get("global_warnings", [])),
            "n_sample_map_entries": len(obj.get("sample_map", []) or []),
            "n_rowwise_suggestions": len(obj.get("rowwise_suggestions", []) or []),
            "ai_json": str(ai_json),
        })

    out = pd.DataFrame(rows)
    out_path = DEEP_QC / "ai_study_summaries.tsv"
    out.to_csv(out_path, sep="\t", index=False)

    md = []
    md.append("# AI Study Summaries")
    md.append("")
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append(f"PASS packets summarized: {len(out)}")
    md.append("")

    if not out.empty:
        md.append("## Summary status")
        md.append("")
        for k, v in out["summary_status"].value_counts().items():
            md.append(f"- {k}: {v}")
        md.append("")

        md.append("## Per-packet summaries")
        md.append("")
        for _, row in out.sort_values(["pmid", "bioproject"]).iterrows():
            md.append(f"### {row['packet_id']}")
            md.append("")
            md.append(f"- PMID: {row.get('pmid', '')}")
            md.append(f"- BioProject: {row.get('bioproject', '')}")
            md.append(f"- Assay class: {row.get('assay_class_confirmed', '')}")
            md.append(f"- Assays: {row.get('assay_types', '')}")
            md.append(f"- Organism/strain: {row.get('organism_strain', '')}")
            md.append(f"- Summary: {row.get('one_sentence_summary', '')}")
            md.append(f"- Study goal: {row.get('study_goal', '')}")
            md.append(f"- Main axes: {row.get('main_comparisons_or_sample_axes', '')}")
            warnings = clean(row.get("global_warnings", ""))
            if warnings:
                md.append(f"- Warnings: {warnings}")
            md.append("")

    md_path = DEEP_QC / "AI_STUDY_SUMMARIES.md"
    md_path.write_text("\n".join(md))

    print("Wrote:", out_path)
    print("Wrote:", md_path)
    print()
    print("Summary status:")
    if out.empty:
        print("No summaries found.")
    else:
        print(out["summary_status"].value_counts().to_string())
        print()
        cols = [
            "packet_id", "pmid", "bioproject", "summary_status",
            "assay_types", "organism_strain", "one_sentence_summary"
        ]
        print(out[[c for c in cols if c in out.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
