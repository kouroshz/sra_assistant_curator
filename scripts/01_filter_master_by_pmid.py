#!/usr/bin/env python3

from pathlib import Path
import argparse
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

MASTER = DATA / "rna_seq_metadata_v1_2026-05-05.xlsx"


CURATION_COLUMNS = [
    "Cell_Cycle_Stage",
    "Life_Stage",
    "Target",
    "Strain",
    "Substrain",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "background_or_control_1",
    "background_or_control_2",
    "Notes",
    "replicate_number",
    "assigned_control1",
    "assigned_control2",
    "curation_source",
    "curation_confidence",
    "curation_evidence",
    "needs_human_review",
    "review_priority",
    "review_reason",
    "reviewer",
    "review_status",
    "reviewer_note",
]


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def find_col(df, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lookup:
            return lookup[key]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--sheet", default="Sheet")
    args = parser.parse_args()

    pmid = clean(args.pmid)

    print(f"\n=== Filtering master sheet for PMID {pmid} ===")

    master = pd.read_excel(MASTER, sheet_name=args.sheet, dtype=str).fillna("")
    master.columns = [str(c).strip() for c in master.columns]

    pmid_col = find_col(master, ["PMID", "PubMed ID", "pubmed_id"])
    run_col = find_col(master, ["Run", "SRR", "Run accession"])
    bioproject_col = find_col(master, ["BioProject", "BioProject ID", "bioproject"])
    biosample_col = find_col(master, ["BioSample", "BioSample ID", "biosample"])
    sample_col = find_col(master, ["SampleName", "Sample Name", "GEO_Accession", "GEO Accession"])
    assay_col = find_col(master, ["LibraryStrategy", "Assay Type", "Library Strategy"])

    if pmid_col is None:
        raise ValueError("Could not find PMID column in master sheet.")
    if run_col is None:
        raise ValueError("Could not find Run/SRR column in master sheet.")

    # Ensure expected curation columns exist.
    for col in CURATION_COLUMNS:
        if col not in master.columns:
            master[col] = ""

    master["_pmid_norm"] = master[pmid_col].map(clean)
    master["_run_norm"] = master[run_col].map(clean)

    subset = master[master["_pmid_norm"] == pmid].copy()

    if subset.empty:
        raise ValueError(f"No rows found for PMID {pmid}")

    out_subset = OUT / f"PMID_{pmid}_master_subset.tsv"
    out_summary = OUT / f"PMID_{pmid}_master_subset_summary.json"

    subset.to_csv(out_subset, sep="\t", index=False)

    summary = {
        "pmid": pmid,
        "n_rows": int(subset.shape[0]),
        "n_unique_runs": int(subset["_run_norm"].nunique()),
        "columns_detected": {
            "pmid": pmid_col,
            "run": run_col,
            "bioproject": bioproject_col,
            "biosample": biosample_col,
            "sample": sample_col,
            "assay": assay_col,
        },
        "bioproject_counts": subset[bioproject_col].value_counts().to_dict() if bioproject_col else {},
        "assay_counts": subset[assay_col].value_counts().to_dict() if assay_col else {},
        "curation_columns_present_or_added": CURATION_COLUMNS,
    }

    with open(out_summary, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Rows: {subset.shape[0]}")
    print(f"Unique runs: {subset['_run_norm'].nunique()}")

    if bioproject_col:
        print("\nBioProject counts:")
        print(subset[bioproject_col].value_counts().to_string())

    if assay_col:
        print("\nAssay counts:")
        print(subset[assay_col].value_counts().to_string())

    print("\nWrote:")
    print(out_subset)
    print(out_summary)
    print("\nDone.")


if __name__ == "__main__":
    main()
