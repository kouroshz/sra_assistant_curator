#!/usr/bin/env python3

"""
Add stable row and curation-group IDs to the master metadata workbook.

This script does NOT overwrite the master sheet.
It creates a rowwise draft table with:
  - source_row_number
  - source_row_id
  - curation_group_id
  - curation_group_size

The goal is to support safe curator review and later merge-back.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path("data/rna_seq_metadata_2026-05-05_original.xlsx")
DEFAULT_OUT_TSV = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv")
DEFAULT_GROUP_MAP = Path("outputs/02_QC_SUMMARIES/curation_group_id_map.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/stable_id_summary.tsv")
DEFAULT_EXCLUDED = Path("outputs/02_QC_SUMMARIES/excluded_special_case_rows.tsv")
DEFAULT_EXCLUDE_PMIDS = ["30320226"]


# These columns define preliminary biological/sample-level grouping.
# They intentionally exclude Run, BioSample, replicate_number, and file paths.
PREFERRED_GROUP_COLUMNS = [
    "PMID",
    "BioProject",
    "LibraryStrategy",
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


SOURCE_FINGERPRINT_COLUMNS = [
    "Run",
    "BioSample",
    "BioProject",
    "PMID",
    "Title",
    "LibraryStrategy",
    "download_path",
]


def clean_value(x) -> str:
    """Normalize missing/string values for stable hashing."""
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def stable_hash(values: list[str], n: int = 12) -> str:
    joined = "||".join(clean_value(v) for v in values)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:n]


def existing_columns(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


def make_group_key(row: pd.Series, group_cols: list[str]) -> list[str]:
    return [clean_value(row.get(c, "")) for c in group_cols]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sheet", default=None, help="Excel sheet name. Default: first sheet.")
    parser.add_argument("--out-tsv", type=Path, default=DEFAULT_OUT_TSV)
    parser.add_argument("--group-map", type=Path, default=DEFAULT_GROUP_MAP)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--excluded-rows", type=Path, default=DEFAULT_EXCLUDED)
    parser.add_argument(
        "--exclude-pmids",
        nargs="*",
        default=DEFAULT_EXCLUDE_PMIDS,
        help="PMIDs to exclude from normal rowwise/group-level curator workflow.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input workbook not found: {args.input}")

    args.out_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.group_map.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.excluded_rows.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(args.input, sheet_name=args.sheet, dtype=object)

    if isinstance(df, dict):
        first_sheet = next(iter(df))
        df = df[first_sheet]

    # Preserve Excel row number. Header is row 1, first data row is row 2.
    df.insert(0, "source_row_number", range(2, len(df) + 2))

    n_rows_before_exclusion = len(df)

    # Exclude special cases from the normal curator workflow.
    # These are not deleted from the source workbook; they are simply routed out.
    excluded_df = pd.DataFrame()
    if "PMID" in df.columns and args.exclude_pmids:
        exclude_set = {str(x).strip() for x in args.exclude_pmids}
        pmid_as_str = df["PMID"].astype(str).str.strip()
        excluded_df = df[pmid_as_str.isin(exclude_set)].copy()
        df = df[~pmid_as_str.isin(exclude_set)].copy()

    if not excluded_df.empty:
        excluded_df.to_csv(args.excluded_rows, sep="\t", index=False)
    else:
        pd.DataFrame(columns=df.columns).to_csv(args.excluded_rows, sep="\t", index=False)

    source_cols = existing_columns(df, SOURCE_FINGERPRINT_COLUMNS)
    if not source_cols:
        raise ValueError("None of the expected source fingerprint columns were found.")

    group_cols = existing_columns(df, PREFERRED_GROUP_COLUMNS)
    if not group_cols:
        raise ValueError("None of the expected group columns were found.")

    # Stable row ID: original Excel row number plus content fingerprint.
    source_ids = []
    for _, row in df.iterrows():
        vals = [row.get(c, "") for c in source_cols]
        h = stable_hash(vals, n=10)
        source_ids.append(f"SRC{int(row['source_row_number']):06d}_{h}")

    df.insert(1, "source_row_id", source_ids)

    if df["source_row_id"].duplicated().any():
        dupes = df.loc[df["source_row_id"].duplicated(), "source_row_id"].tolist()
        raise ValueError(f"Duplicate source_row_id values detected: {dupes[:5]}")

    # Group ID: stable hash over curator-relevant biological/sample metadata.
    group_keys = df.apply(lambda r: make_group_key(r, group_cols), axis=1)
    group_hashes = group_keys.apply(lambda vals: stable_hash(vals, n=12))
    df.insert(2, "curation_group_id", group_hashes.apply(lambda h: f"CGRP_{h}"))

    group_sizes = df.groupby("curation_group_id")["source_row_id"].transform("size")
    df.insert(3, "curation_group_size", group_sizes)

    # Group map for QC/review.
    agg_dict = {
        "source_row_id": lambda x: ",".join(map(str, x)),
    }
    if "Run" in df.columns:
        agg_dict["Run"] = lambda x: ",".join(sorted(set(clean_value(v) for v in x if clean_value(v))))
    if "BioSample" in df.columns:
        agg_dict["BioSample"] = lambda x: ",".join(sorted(set(clean_value(v) for v in x if clean_value(v))))

    for c in group_cols:
        agg_dict[c] = lambda x: "; ".join(sorted(set(clean_value(v) for v in x if clean_value(v))))

    group_map = (
        df.groupby("curation_group_id", dropna=False)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={
            "source_row_id": "source_row_ids",
            "Run": "runs",
            "BioSample": "biosamples",
        })
    )
    group_map.insert(1, "n_rows", df.groupby("curation_group_id").size().values)

    # Summary.
    rows = len(df)
    n_groups = df["curation_group_id"].nunique()
    n_source_ids = df["source_row_id"].nunique()
    n_runs = df["Run"].nunique(dropna=True) if "Run" in df.columns else pd.NA
    missing_runs = int(df["Run"].isna().sum()) if "Run" in df.columns else pd.NA
    duplicated_runs = int(df["Run"].duplicated().sum()) if "Run" in df.columns else pd.NA

    summary = pd.DataFrame(
        [
            {"metric": "input_workbook", "value": str(args.input)},
            {"metric": "n_rows_before_exclusion", "value": n_rows_before_exclusion},
            {"metric": "excluded_pmids", "value": ",".join(args.exclude_pmids)},
            {"metric": "n_excluded_rows", "value": len(excluded_df)},
            {"metric": "excluded_rows_file", "value": str(args.excluded_rows)},
            {"metric": "n_rows", "value": rows},
            {"metric": "n_unique_source_row_id", "value": n_source_ids},
            {"metric": "n_curation_groups", "value": n_groups},
            {"metric": "n_unique_Run", "value": n_runs},
            {"metric": "n_missing_Run", "value": missing_runs},
            {"metric": "n_duplicated_Run_rows", "value": duplicated_runs},
            {"metric": "source_fingerprint_columns", "value": ",".join(source_cols)},
            {"metric": "curation_group_columns", "value": ",".join(group_cols)},
        ]
    )

    df.to_csv(args.out_tsv, sep="\t", index=False)
    group_map.to_csv(args.group_map, sep="\t", index=False)
    summary.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote rowwise table: {args.out_tsv}")
    print(f"Wrote group map:     {args.group_map}")
    print(f"Wrote summary:       {args.summary}")
    print(f"Rows: {rows}")
    print(f"Curation groups: {n_groups}")
    print(f"Group columns used: {', '.join(group_cols)}")


if __name__ == "__main__":
    main()
