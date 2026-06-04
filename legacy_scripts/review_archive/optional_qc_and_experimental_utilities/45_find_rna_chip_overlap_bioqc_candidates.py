#!/usr/bin/env python3
"""
Find candidate papers/BioProjects for biological QC across RNA and ChIP master sheets.

Read-only.

Outputs:
  outputs/05_BIOLOGICAL_QC/rna_chip_overlap_candidates.tsv
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


RNA_XLSX = Path("data/rna_seq_metadata_2026-05-05_original.xlsx")
CHIP_XLSX = Path("data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx")
OUTDIR = Path("outputs/05_BIOLOGICAL_QC")


def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def first_nonempty(series):
    vals = [clean(x) for x in series if clean(x)]
    return vals[0] if vals else ""


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    rna = pd.read_excel(RNA_XLSX, dtype=str).fillna("")
    chip = pd.read_excel(CHIP_XLSX, dtype=str).fillna("")

    # Normalize likely column names.
    rna_cols = {c.lower(): c for c in rna.columns}
    chip_cols = {c.lower(): c for c in chip.columns}

    rna_pmid_col = rna_cols.get("pmid")
    rna_bioproject_col = rna_cols.get("bioproject") or rna_cols.get("bioproject id") or rna_cols.get("bioproject_id")
    rna_run_col = rna_cols.get("run")

    chip_pmid_col = chip_cols.get("pmid")
    chip_bioproject_col = chip_cols.get("bioproject") or chip_cols.get("bioproject id") or chip_cols.get("bioproject_id")
    chip_run_col = chip_cols.get("run")

    if not rna_pmid_col or not rna_bioproject_col or not rna_run_col:
        raise SystemExit(f"Could not identify RNA PMID/BioProject/Run columns. RNA columns={list(rna.columns)}")

    if not chip_run_col:
        raise SystemExit(f"Could not identify ChIP Run column. ChIP columns={list(chip.columns)}")

    # ChIP may use paper_link rather than PMID. Keep both if available.
    chip_paper_link_col = chip_cols.get("paper_link")

    rna["PMID_norm"] = rna[rna_pmid_col].map(clean)
    rna["BioProject_norm"] = rna[rna_bioproject_col].map(clean)
    rna["Run_norm"] = rna[rna_run_col].map(clean)

    if chip_pmid_col:
        chip["PMID_norm"] = chip[chip_pmid_col].map(clean)
    else:
        chip["PMID_norm"] = ""

    if chip_bioproject_col:
        chip["BioProject_norm"] = chip[chip_bioproject_col].map(clean)
    else:
        chip["BioProject_norm"] = ""

    chip["Run_norm"] = chip[chip_run_col].map(clean)
    chip["paper_link_norm"] = chip[chip_paper_link_col].map(clean) if chip_paper_link_col else ""

    # Current active trusted RNA universe excludes no PMID and special single-cell paper.
    rna_trusted = rna[(rna["PMID_norm"] != "") & (rna["PMID_norm"] != "30320226")].copy()

    rna_by_pmid = (
        rna_trusted.groupby("PMID_norm")
        .agg(
            rna_rows=("Run_norm", "size"),
            rna_runs=("Run_norm", pd.Series.nunique),
            rna_bioprojects=("BioProject_norm", lambda x: ";".join(sorted(set(clean(v) for v in x if clean(v))))),
            rna_titles=("Title", first_nonempty) if "Title" in rna_trusted.columns else ("Run_norm", first_nonempty),
        )
        .reset_index()
        .rename(columns={"PMID_norm": "PMID"})
    )

    # ChIP may or may not have PMID. If it does, overlap directly by PMID.
    rows = []

    if chip["PMID_norm"].ne("").any():
        chip_by_pmid = (
            chip[chip["PMID_norm"] != ""]
            .groupby("PMID_norm")
            .agg(
                chip_rows=("Run_norm", "size"),
                chip_runs=("Run_norm", pd.Series.nunique),
                chip_bioprojects=("BioProject_norm", lambda x: ";".join(sorted(set(clean(v) for v in x if clean(v))))),
                chip_targets=("Target", lambda x: ";".join(sorted(set(clean(v) for v in x if clean(v)))) if "Target" in chip.columns else ""),
                chip_background_nonempty=("background_sample", lambda x: sum(1 for v in x if clean(v))) if "background_sample" in chip.columns else ("Run_norm", lambda x: 0),
                chip_assigned_control1_nonempty=("assigned_control1", lambda x: sum(1 for v in x if clean(v))) if "assigned_control1" in chip.columns else ("Run_norm", lambda x: 0),
                chip_paper_link=("paper_link_norm", first_nonempty),
            )
            .reset_index()
            .rename(columns={"PMID_norm": "PMID"})
        )

        overlap = rna_by_pmid.merge(chip_by_pmid, on="PMID", how="inner")
        rows.append(overlap)

    # Also look for BioProject overlaps, because ChIP PMID may be absent.
    rna_by_bp = (
        rna_trusted[rna_trusted["BioProject_norm"] != ""]
        .groupby("BioProject_norm")
        .agg(
            PMID=("PMID_norm", lambda x: ";".join(sorted(set(clean(v) for v in x if clean(v))))),
            rna_rows=("Run_norm", "size"),
            rna_runs=("Run_norm", pd.Series.nunique),
            rna_bioprojects=("BioProject_norm", first_nonempty),
            rna_titles=("Title", first_nonempty) if "Title" in rna_trusted.columns else ("Run_norm", first_nonempty),
        )
        .reset_index()
        .rename(columns={"BioProject_norm": "overlap_bioproject"})
    )

    chip_by_bp = (
        chip[chip["BioProject_norm"] != ""]
        .groupby("BioProject_norm")
        .agg(
            chip_rows=("Run_norm", "size"),
            chip_runs=("Run_norm", pd.Series.nunique),
            chip_bioprojects=("BioProject_norm", first_nonempty),
            chip_targets=("Target", lambda x: ";".join(sorted(set(clean(v) for v in x if clean(v)))) if "Target" in chip.columns else ""),
            chip_background_nonempty=("background_sample", lambda x: sum(1 for v in x if clean(v))) if "background_sample" in chip.columns else ("Run_norm", lambda x: 0),
            chip_assigned_control1_nonempty=("assigned_control1", lambda x: sum(1 for v in x if clean(v))) if "assigned_control1" in chip.columns else ("Run_norm", lambda x: 0),
            chip_paper_link=("paper_link_norm", first_nonempty),
        )
        .reset_index()
        .rename(columns={"BioProject_norm": "overlap_bioproject"})
    )

    bp_overlap = rna_by_bp.merge(chip_by_bp, on="overlap_bioproject", how="inner")
    if not bp_overlap.empty:
        rows.append(bp_overlap)

    if rows:
        out = pd.concat(rows, ignore_index=True, sort=False).drop_duplicates()
    else:
        out = pd.DataFrame()

    if not out.empty:
        # Score candidate usefulness.
        out["score"] = (
            out.get("rna_rows", 0).astype(float).clip(upper=100)
            + out.get("chip_rows", 0).astype(float).clip(upper=100)
            + 10 * (out.get("chip_targets", "").astype(str).str.len() > 0).astype(int)
            + 10 * (out.get("chip_background_nonempty", 0).astype(float) > 0).astype(int)
            + 10 * (out.get("chip_assigned_control1_nonempty", 0).astype(float) > 0).astype(int)
        )

        out = out.sort_values(["score", "rna_rows", "chip_rows"], ascending=False)

    out_path = OUTDIR / "rna_chip_overlap_candidates.tsv"
    out.to_csv(out_path, sep="\t", index=False)

    print("Wrote:", out_path)
    print("Candidates:", len(out))
    if not out.empty:
        show_cols = [c for c in [
            "score", "PMID", "overlap_bioproject",
            "rna_rows", "rna_runs", "chip_rows", "chip_runs",
            "rna_bioprojects", "chip_bioprojects",
            "chip_targets", "chip_background_nonempty",
            "chip_assigned_control1_nonempty",
            "rna_titles", "chip_paper_link",
        ] if c in out.columns]
        print(out[show_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
