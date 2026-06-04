#!/usr/bin/env python3
"""
Inspect Plasmodium ChIP metadata master sheet before building ChIP AI pipeline.

This is read-only. It writes small summary tables/reports to:
  outputs/06_CHIP_AI_ASSIST/00_inspect/
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import re

OUT = Path("outputs/06_CHIP_AI_ASSIST/00_inspect")
OUT.mkdir(parents=True, exist_ok=True)

DATA = Path("data")

def find_chip_master():
    candidates = sorted(DATA.glob("*chip*metadata*.xlsx")) + sorted(DATA.glob("*ChIP*metadata*.xlsx"))
    if not candidates:
        candidates = sorted(DATA.glob("*chip*.xlsx")) + sorted(DATA.glob("*ChIP*.xlsx"))
    if not candidates:
        raise SystemExit("No ChIP Excel master found under data/. Please check filename/path.")
    print("Candidate ChIP masters:")
    for i, p in enumerate(candidates, 1):
        print(f"  {i}. {p}")
    return candidates[0]

def norm_col(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")

def pick_col(cols, candidates):
    norm_map = {norm_col(c): c for c in cols}
    for cand in candidates:
        key = norm_col(cand)
        if key in norm_map:
            return norm_map[key]
    for c in cols:
        nc = norm_col(c)
        for cand in candidates:
            if norm_col(cand) in nc:
                return c
    return None

def safe_counts(df, col):
    if col is None or col not in df.columns:
        return pd.DataFrame(columns=["value", "n"])
    s = df[col].fillna("").astype(str).str.strip()
    vc = s.replace("", "<blank>").value_counts().reset_index()
    vc.columns = ["value", "n"]
    return vc

def main():
    xlsx = find_chip_master()
    xl = pd.ExcelFile(xlsx)

    report = []
    report.append("# ChIP Master Inspection Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append(f"Input file: `{xlsx}`")
    report.append("")
    report.append("## Sheets")
    for sh in xl.sheet_names:
        report.append(f"- {sh}")

    # Choose first sheet by default unless another has more rows.
    sheet_info = []
    frames = {}
    for sh in xl.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sh, dtype=str).fillna("")
        frames[sh] = df
        sheet_info.append((sh, df.shape[0], df.shape[1]))

    sheet_summary = pd.DataFrame(sheet_info, columns=["sheet", "n_rows", "n_cols"])
    sheet_summary.to_csv(OUT / "chip_master_sheet_summary.tsv", sep="\t", index=False)

    main_sheet = sheet_summary.sort_values("n_rows", ascending=False).iloc[0]["sheet"]
    df = frames[main_sheet].copy()

    report.append("")
    report.append("## Main sheet selected")
    report.append("")
    report.append(f"- `{main_sheet}` with {df.shape[0]} rows and {df.shape[1]} columns")
    report.append("")

    cols = list(df.columns)
    col_summary = pd.DataFrame({"column": cols, "normalized": [norm_col(c) for c in cols]})
    col_summary.to_csv(OUT / "chip_master_columns.tsv", sep="\t", index=False)

    # Guess important columns.
    col_run = pick_col(cols, ["Run", "SRR", "run_accession"])
    col_pmid = pick_col(cols, ["PMID", "PubMed", "pubmed_id"])
    col_bioproject = pick_col(cols, ["BioProject", "bioproject", "BioProject ID"])
    col_biosample = pick_col(cols, ["BioSample", "biosample"])
    col_title = pick_col(cols, ["Title", "paper_title", "Study Title"])
    col_target = pick_col(cols, ["target", "Target", "antibody", "Antibody", "chip_target", "factor", "histone_mark"])
    col_background = pick_col(cols, ["background", "Background", "Input", "input", "control", "Control"])
    col_control1 = pick_col(cols, ["assigned_control1", "control1", "Control1", "assigned control"])
    col_strategy = pick_col(cols, ["LibraryStrategy", "library_strategy", "Assay", "assay_type"])
    col_strain = pick_col(cols, ["strain", "Strain", "isolate", "line"])
    col_stage = pick_col(cols, ["stage", "Stage", "Life_Stage", "developmental_stage", "Cell_Cycle_Stage"])
    col_condition = pick_col(cols, ["condition", "Condition", "treatment", "Treatment"])

    guessed = pd.DataFrame([
        ("run", col_run),
        ("pmid", col_pmid),
        ("bioproject", col_bioproject),
        ("biosample", col_biosample),
        ("title", col_title),
        ("target_or_antibody", col_target),
        ("background_or_input", col_background),
        ("assigned_control1", col_control1),
        ("library_strategy", col_strategy),
        ("strain", col_strain),
        ("stage", col_stage),
        ("condition", col_condition),
    ], columns=["field", "guessed_column"])
    guessed.to_csv(OUT / "chip_master_guessed_columns.tsv", sep="\t", index=False)

    # Basic counts.
    counts = {
        "n_rows": len(df),
        "n_unique_runs": df[col_run].nunique() if col_run else "",
        "n_unique_pmids": df[col_pmid].replace("", pd.NA).dropna().nunique() if col_pmid else "",
        "n_blank_pmids": int((df[col_pmid].astype(str).str.strip() == "").sum()) if col_pmid else "",
        "n_unique_bioprojects": df[col_bioproject].replace("", pd.NA).dropna().nunique() if col_bioproject else "",
        "n_unique_targets_or_antibodies": df[col_target].replace("", pd.NA).dropna().nunique() if col_target else "",
        "n_nonempty_background_or_input": int((df[col_background].astype(str).str.strip() != "").sum()) if col_background else "",
        "n_nonempty_assigned_control1": int((df[col_control1].astype(str).str.strip() != "").sum()) if col_control1 else "",
    }
    pd.DataFrame([counts]).to_csv(OUT / "chip_master_basic_counts.tsv", sep="\t", index=False)

    # Group counts.
    group_cols = [c for c in [col_pmid, col_bioproject] if c]
    if group_cols:
        g = (
            df.groupby(group_cols, dropna=False)
              .size()
              .reset_index(name="n_rows")
              .sort_values("n_rows", ascending=False)
        )
        g.to_csv(OUT / "chip_pmid_bioproject_groups.tsv", sep="\t", index=False)

    for name, col in [
        ("targets_or_antibodies", col_target),
        ("background_or_input", col_background),
        ("assigned_control1", col_control1),
        ("library_strategy", col_strategy),
        ("strain", col_strain),
        ("stage", col_stage),
        ("condition", col_condition),
        ("pmid", col_pmid),
        ("bioproject", col_bioproject),
    ]:
        safe_counts(df, col).to_csv(OUT / f"chip_counts_by_{name}.tsv", sep="\t", index=False)

    # Report text.
    report.append("## Guessed important columns")
    report.append("")
    for _, r in guessed.iterrows():
        report.append(f"- {r['field']}: `{r['guessed_column']}`")
    report.append("")
    report.append("## Basic counts")
    report.append("")
    for k, v in counts.items():
        report.append(f"- {k}: {v}")

    if col_target:
        top_targets = safe_counts(df, col_target).head(20)
        report.append("")
        report.append("## Top target/antibody values")
        report.append("")
        for _, r in top_targets.iterrows():
            report.append(f"- {r['value']}: {r['n']}")

    if group_cols:
        report.append("")
        report.append("## Largest PMID/BioProject groups")
        report.append("")
        for _, r in g.head(20).iterrows():
            label = " / ".join([str(r[c]) for c in group_cols])
            report.append(f"- {label}: {r['n_rows']} rows")

    out_md = OUT / "CHIP_MASTER_INSPECTION_REPORT.md"
    out_md.write_text("\n".join(report))

    print("Input:", xlsx)
    print("Main sheet:", main_sheet)
    print("Wrote:", out_md)
    print("Wrote outputs to:", OUT)
    print()
    print(pd.DataFrame([counts]).to_string(index=False))
    print()
    print("Guessed columns:")
    print(guessed.to_string(index=False))

if __name__ == "__main__":
    main()
