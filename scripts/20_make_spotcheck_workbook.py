#!/usr/bin/env python3

from pathlib import Path
import argparse
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

KEEP_COLS = [
    "PMID",
    "Title",
    "n_rows",
    "n_runs",
    "n_biosamples",
    "sra_row_omics",
    "experimental_factor",
    "control_role",
    "Life_Stage",
    "Cell_Cycle_Stage",
    "Strain",
    "Substrain",
    "Target",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "background_or_control_1",
    "assigned_control_biosample1",
    "assigned_control_sample1",
    "background_or_control_2",
    "assigned_control_biosample2",
    "assigned_control_sample2",
    "curator_condition_note",
    "needs_review_yes",
    "confidence_values",
    "review_reasons",
    "example_runs",
    "example_biosamples",
    "example_samples",
    "primary_review_file",
]

def clean_sheet_name(x):
    x = str(x)
    for ch in r'[]:*?/\\':
        x = x.replace(ch, "_")
    return x[:31]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pmids",
        default="31737630,32487761,34365503,35288749,37833314",
        help="Comma-separated PMIDs to include",
    )
    args = ap.parse_args()

    pmids = [x.strip() for x in args.pmids.split(",") if x.strip()]

    f = OUT / "curator_group_level_review_index.tsv"
    df = pd.read_csv(f, sep="\t", dtype=str).fillna("")

    out = OUT / "spotcheck_selected_pmids.xlsx"

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary_rows = []

        for pmid in pmids:
            sub = df[df["PMID"].astype(str) == pmid].copy()

            for c in KEEP_COLS:
                if c not in sub.columns:
                    sub[c] = ""

            sub = sub[KEEP_COLS].copy()

            sub.insert(0, "spotcheck_status", "")
            sub.insert(1, "spotcheck_note", "")
            sub.insert(2, "recommended_patch", "")

            sub.to_excel(writer, sheet_name=clean_sheet_name(pmid), index=False)

            summary_rows.append({
                "PMID": pmid,
                "n_groups": len(sub),
                "n_rows_total": pd.to_numeric(sub["n_rows"], errors="coerce").fillna(0).sum(),
                "suggested_status": "",
                "overall_note": "",
                "recommended_patch": "",
            })

        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Spotcheck_Summary", index=False)

    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
