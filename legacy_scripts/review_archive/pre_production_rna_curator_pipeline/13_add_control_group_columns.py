#!/usr/bin/env python3

from pathlib import Path
import argparse
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


def split_runs(x):
    x = clean(x)
    if not x:
        return []
    return [clean(v) for v in x.replace(",", ";").split(";") if clean(v)]


def uniq_join(vals):
    vals = [clean(v) for v in vals if clean(v)]
    return ";".join(sorted(set(vals)))


def normalize_omics(x):
    x = clean(x)
    if x.lower() == "rna-seq":
        return "RNA-seq"
    if x.lower() == "chip-seq":
        return "ChIP-seq"
    return x


def find_rows_file(pmid):
    with_paper = OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"
    base = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"

    if with_paper.exists():
        return with_paper
    if base.exists():
        return base

    raise FileNotFoundError(f"No filled rows TSV found for PMID {pmid}")


def find_workbook(pmid):
    with_paper = OUT / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.with_paper_context.xlsx"
    base = OUT / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.xlsx"

    if with_paper.exists():
        return with_paper
    if base.exists():
        return base

    return None


def add_columns(df):
    df = df.copy().fillna("")

    required = [
        "technical_run_count",
        "technical_run_group",
        "assigned_control_biosample1",
        "assigned_control_sample1",
        "assigned_control_biosample2",
        "assigned_control_sample2",
        "sra_row_omics",
        "paper_other_assays",
    ]

    for c in required:
        if c not in df.columns:
            df[c] = ""

    run_to_biosample = {}
    run_to_sample = {}

    for _, row in df.iterrows():
        run = clean(row.get("Run", ""))
        if not run:
            continue
        run_to_biosample[run] = clean(row.get("BioSample", ""))
        run_to_sample[run] = clean(row.get("SampleName", ""))

    # Technical run groups by BioSample if available; otherwise SampleName.
    if "BioSample" in df.columns:
        group_key = df["BioSample"].map(clean)
    elif "SampleName" in df.columns:
        group_key = df["SampleName"].map(clean)
    else:
        group_key = pd.Series([""] * len(df), index=df.index)

    key_to_runs = {}
    for idx, key in group_key.items():
        if not key:
            continue
        run = clean(df.at[idx, "Run"])
        if not run:
            continue
        key_to_runs.setdefault(key, []).append(run)

    for idx, row in df.iterrows():
        key = clean(group_key.loc[idx])
        runs = sorted(set(key_to_runs.get(key, [])))

        if key and runs:
            df.at[idx, "technical_run_count"] = str(len(runs))
            df.at[idx, "technical_run_group"] = ";".join(runs)

        for slot in ["1", "2"]:
            control_col = f"assigned_control{slot}"
            if control_col not in df.columns:
                continue

            control_runs = split_runs(row.get(control_col, ""))
            control_biosamples = [run_to_biosample.get(r, "") for r in control_runs]
            control_samples = [run_to_sample.get(r, "") for r in control_runs]

            df.at[idx, f"assigned_control_biosample{slot}"] = uniq_join(control_biosamples)
            df.at[idx, f"assigned_control_sample{slot}"] = uniq_join(control_samples)

        df.at[idx, "sra_row_omics"] = normalize_omics(row.get("LibraryStrategy", ""))

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    rows_file = find_rows_file(pmid)
    df = pd.read_csv(rows_file, sep="\t", dtype=str).fillna("")
    out_df = add_columns(df)
    out_df.to_csv(rows_file, sep="\t", index=False)

    workbook = find_workbook(pmid)

    if workbook is not None:
        sheets = pd.read_excel(workbook, sheet_name=None, dtype=str)
        sheets = {k: v.fillna("") for k, v in sheets.items()}

        if "Sheet" in sheets and "Run" in sheets["Sheet"].columns:
            main = sheets["Sheet"].copy()

            add_cols = [
                "technical_run_count",
                "technical_run_group",
                "assigned_control_biosample1",
                "assigned_control_sample1",
                "assigned_control_biosample2",
                "assigned_control_sample2",
                "sra_row_omics",
                "paper_other_assays",
            ]

            for c in add_cols:
                if c not in main.columns:
                    main[c] = ""

            lookup = {
                clean(r["Run"]): r
                for _, r in out_df.iterrows()
                if clean(r.get("Run", ""))
            }

            for idx, row in main.iterrows():
                run = clean(row.get("Run", ""))
                if run not in lookup:
                    continue
                for c in add_cols:
                    main.at[idx, c] = lookup[run].get(c, "")

            sheets["Sheet"] = main

            with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
                for s, d in sheets.items():
                    d.to_excel(writer, sheet_name=s[:31], index=False)

    print(f"\n=== Added control/sample grouping columns for PMID {pmid} ===")
    print(f"Rows file updated: {rows_file}")
    if workbook:
        print(f"Workbook updated: {workbook}")

    show_cols = [
        "Run", "BioSample", "SampleName", "technical_run_count",
        "technical_run_group", "assigned_control1",
        "assigned_control_biosample1", "assigned_control_sample1",
        "sra_row_omics",
    ]
    show_cols = [c for c in show_cols if c in out_df.columns]
    print(out_df[show_cols].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
