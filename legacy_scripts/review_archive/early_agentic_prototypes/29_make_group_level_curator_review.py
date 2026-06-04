#!/usr/bin/env python3

"""
Create a group-level curator review workbook from the stable-ID rowwise table.

This script does NOT call AI and does NOT modify the master sheet.
It prepares a human/agent-ready curator table.

Input:
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv

Outputs:
  outputs/00_FINAL_CURATOR_PACKAGE/curator_group_level_review_WITH_STABLE_IDS.xlsx
  outputs/01_CURRENT_DRAFT_TABLES/curator_group_level_review_WITH_STABLE_IDS.tsv
  outputs/02_QC_SUMMARIES/group_level_curator_review_summary.tsv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv")
DEFAULT_OUT_XLSX = Path("outputs/00_FINAL_CURATOR_PACKAGE/curator_group_level_review_WITH_STABLE_IDS.xlsx")
DEFAULT_OUT_TSV = Path("outputs/01_CURRENT_DRAFT_TABLES/curator_group_level_review_WITH_STABLE_IDS.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/group_level_curator_review_summary.tsv")


DISPLAY_COLUMNS = [
    "PMID",
    "BioProject",
    "LibraryStrategy",
    "Title",
    "study_title",
    "paper_title",
    "organism",
    "Cell_Cycle_Stage",
    "Life_Stage",
    "Target",
    "Strain",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "background_sample",
    "replicate_number",
    "assay_type",
    "LibraryLayout",
    "LibrarySelection",
    "LibrarySource",
]


def clean_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def collapse_unique(values, max_items=20) -> str:
    vals = sorted(set(clean_value(v) for v in values if clean_value(v)))
    if not vals:
        return ""
    if len(vals) > max_items:
        shown = vals[:max_items]
        return "; ".join(shown) + f"; ... [{len(vals)} unique]"
    return "; ".join(vals)


def collapse_runs(values, max_items=30) -> str:
    vals = sorted(set(clean_value(v) for v in values if clean_value(v)))
    if not vals:
        return ""
    if len(vals) > max_items:
        return ",".join(vals[:max_items]) + f",... [{len(vals)} runs]"
    return ",".join(vals)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-xlsx", type=Path, default=DEFAULT_OUT_XLSX)
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input stable-ID table not found: {args.input}")

    args.out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    args.out_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input, sep="\t", dtype=str)

    required = {"source_row_id", "source_row_number", "curation_group_id", "curation_group_size"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    rows = []
    for group_id, g in df.groupby("curation_group_id", dropna=False):
        row = {
            "curation_group_id": group_id,
            "n_source_rows": len(g),
            "source_row_ids": collapse_runs(g["source_row_id"], max_items=20),
            "source_row_numbers": collapse_runs(g["source_row_number"], max_items=20),
            "runs": collapse_runs(g["Run"], max_items=30) if "Run" in g.columns else "",
            "n_runs": g["Run"].nunique(dropna=True) if "Run" in g.columns else "",
            "biosamples": collapse_runs(g["BioSample"], max_items=30) if "BioSample" in g.columns else "",
            "n_biosamples": g["BioSample"].nunique(dropna=True) if "BioSample" in g.columns else "",
        }

        for col in DISPLAY_COLUMNS:
            if col in g.columns:
                row[col] = collapse_unique(g[col])

        # Agentic AI fields, initially blank.
        row.update({
            "ai_review_status": "",
            "ai_assay_type_suggestion": "",
            "ai_target_suggestion": "",
            "ai_stage_timepoint_suggestion": "",
            "ai_strain_suggestion": "",
            "ai_condition_suggestion": "",
            "ai_control_background_suggestion": "",
            "ai_evidence_summary": "",
            "ai_paper_evidence_quote_or_location": "",
            "ai_sra_biosample_evidence": "",
            "ai_confidence": "",
            "ai_warning_flags": "",
        })

        # Human curator fields, initially blank.
        row.update({
            "curator_review_status": "",
            "curator_assay_type": "",
            "curator_target": "",
            "curator_stage_timepoint": "",
            "curator_strain": "",
            "curator_mutant": "",
            "curator_condition": "",
            "curator_is_control_or_background": "",
            "curator_control_background_type": "",
            "curator_ready_for_processing": "",
            "curator_note": "",
        })

        rows.append(row)

    out = pd.DataFrame(rows)

    # Stable useful ordering.
    front = [
        "curation_group_id",
        "n_source_rows",
        "n_runs",
        "n_biosamples",
        "source_row_ids",
        "source_row_numbers",
        "runs",
        "biosamples",
        "PMID",
        "BioProject",
        "LibraryStrategy",
        "Title",
        "Cell_Cycle_Stage",
        "Life_Stage",
        "Target",
        "Strain",
        "Mutant",
        "Condition1",
        "Condition2",
        "Condition3",
        "background_sample",
    ]
    front = [c for c in front if c in out.columns]
    rest = [c for c in out.columns if c not in front]
    out = out[front + rest]

    out.to_csv(args.out_tsv, sep="\t", index=False)

    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="group_review", index=False)

        summary = pd.DataFrame([
            {"metric": "input_table", "value": str(args.input)},
            {"metric": "n_group_rows", "value": len(out)},
            {"metric": "n_total_source_rows", "value": len(df)},
            {"metric": "max_group_size", "value": int(out["n_source_rows"].max())},
            {"metric": "median_group_size", "value": float(out["n_source_rows"].median())},
            {"metric": "output_xlsx", "value": str(args.out_xlsx)},
            {"metric": "output_tsv", "value": str(args.out_tsv)},
        ])
        summary.to_excel(writer, sheet_name="summary", index=False)

    summary.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote curator workbook: {args.out_xlsx}")
    print(f"Wrote curator TSV:      {args.out_tsv}")
    print(f"Wrote summary:          {args.summary}")
    print(f"Group rows: {len(out)}")
    print(f"Source rows represented: {len(df)}")


if __name__ == "__main__":
    main()
