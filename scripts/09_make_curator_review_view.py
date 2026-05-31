#!/usr/bin/env python3

from pathlib import Path
import argparse
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def safe_read_json(path):
    if path.exists():
        return json.loads(path.read_text())
    return {}


def autosize_excel(writer):
    workbook = writer.book
    for ws in workbook.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for col_cells in ws.columns:
            max_len = 10
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                val = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    with_paper = OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"
    base = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"

    if with_paper.exists():
        rows_file = with_paper
    elif base.exists():
        rows_file = base
    else:
        raise FileNotFoundError(f"No agent-filled rows found for PMID {pmid}")

    df = pd.read_csv(rows_file, sep="\t", dtype=str).fillna("")

    keep_cols = [
        "Run",
        "BioSample",
        "SampleName",
        "BioProject",
        "LibraryStrategy",
        "Cell_Cycle_Stage",
        "Life_Stage",
        "Target",
        "Strain",
        "Substrain",
        "Mutant",
        "Condition1",
        "Condition2",
        "Condition3",
        "experimental_factor",
        "control_role",
        "curator_condition_note",
        "replicate_number",
        "technical_run_count",
        "technical_run_group",
        "assigned_control1",
        "assigned_control_biosample1",
        "assigned_control_sample1",
        "assigned_control2",
        "assigned_control_biosample2",
        "assigned_control_sample2",
        "background_or_control_1",
        "background_or_control_2",
        "sra_row_omics",
        "paper_other_assays",
        "Notes",
        "paper_note",
        "paper_omics_used",
        "paper_omics_mentions",
        "condition_interpretation",
        "curation_source",
        "curation_confidence",
        "curation_note",
        "curation_evidence",
        "needs_human_review",
        "review_priority",
        "review_reason",
    ]

    keep_cols = [c for c in keep_cols if c in df.columns]
    curator = df[keep_cols].copy()

    for col in ["reviewer", "review_status", "reviewer_note", "reviewer_corrected_value"]:
        if col not in curator.columns:
            curator[col] = ""

    review = curator[curator["needs_human_review"].map(clean) == "yes"].copy()

    group_cols = [
        c for c in [
            "Strain",
            "Cell_Cycle_Stage",
            "Mutant",
            "Condition1",
            "background_or_control_1",
            "needs_human_review",
            "review_priority",
            "review_reason",
        ]
        if c in df.columns
    ]

    if group_cols:
        group_summary = (
            df.groupby(group_cols, dropna=False)
            .agg(
                n_runs=("Run", "count"),
                runs=("Run", lambda x: ";".join(map(str, x))),
            )
            .reset_index()
            .sort_values(["needs_human_review", "Strain", "Condition1"], ascending=[False, True, True])
        )
    else:
        group_summary = pd.DataFrame()

    context = safe_read_json(OUT / f"PMID_{pmid}_paper_context.json")
    context_df = pd.DataFrame(
        [{"field": k, "value": v} for k, v in context.items()]
    ) if context else pd.DataFrame(columns=["field", "value"])

    out_xlsx = OUT / f"PMID_{pmid}_curator_review_view.xlsx"

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        curator.to_excel(writer, sheet_name="Curator_View", index=False)
        review.to_excel(writer, sheet_name="Needs_Review", index=False)
        group_summary.to_excel(writer, sheet_name="Group_Summary", index=False)
        context_df.to_excel(writer, sheet_name="Paper_Context", index=False)
        autosize_excel(writer)

    print(f"\n=== Curator review view for PMID {pmid} ===")
    print(f"Input rows: {df.shape[0]}")
    print(f"Rows needing review: {review.shape[0]}")
    print(f"Wrote: {out_xlsx}")
    print(f"\nOpen with:\nopen {out_xlsx}")


if __name__ == "__main__":
    main()
