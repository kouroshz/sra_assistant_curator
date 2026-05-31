#!/usr/bin/env python3

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

GROUP_COLS = [
    "PMID",
    "Title",
    "BioProject",
    "LibraryStrategy",
    "sra_row_omics",
    "Life_Stage",
    "Cell_Cycle_Stage",
    "Strain",
    "Substrain",
    "Target",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "experimental_factor",
    "control_role",
    "background_or_control_1",
    "background_or_control_2",
    "assigned_control1",
    "assigned_control_biosample1",
    "assigned_control_sample1",
    "assigned_control2",
    "assigned_control_biosample2",
    "assigned_control_sample2",
    "curator_condition_note",
    "special_handling",
    "curation_scope",
    "curator_review_unit",
    "row_level_curation_recommended",
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


def uniq_join(vals, n=8):
    vals = sorted(set(clean(v) for v in vals if clean(v)))
    if len(vals) > n:
        return ";".join(vals[:n]) + f";...(+{len(vals)-n})"
    return ";".join(vals)


def first_nonempty(vals):
    for v in vals:
        v = clean(v)
        if v:
            return v
    return ""


def main():
    all_rows = []

    for f in sorted(OUT.glob("PMID_*_agent_filled_master_rows_with_paper_context.tsv")):
        pmid = f.name.split("_")[1]
        df = pd.read_csv(f, sep="\t", dtype=str).fillna("")
        df["PMID"] = df.get("PMID", pmid).map(clean)
        all_rows.append(df)

    big = pd.concat(all_rows, ignore_index=True).fillna("")

    for c in GROUP_COLS:
        if c not in big.columns:
            big[c] = ""

    # Do not force 30320226 into row-level group review.
    ordinary = big[big["row_level_curation_recommended"].map(clean) != "no"].copy()
    special = big[big["row_level_curation_recommended"].map(clean) == "no"].copy()

    group_cols = [c for c in GROUP_COLS if c in ordinary.columns]

    grouped = (
        ordinary
        .groupby(group_cols, dropna=False)
        .agg(
            n_rows=("Run", "count"),
            n_runs=("Run", "nunique"),
            n_biosamples=("BioSample", "nunique"),
            n_experiments=("Experiment", "nunique"),
            example_runs=("Run", lambda x: uniq_join(x, n=6)),
            example_biosamples=("BioSample", lambda x: uniq_join(x, n=6)),
            example_samples=("SampleName", lambda x: uniq_join(x, n=6)),
            needs_review_yes=("needs_human_review", lambda x: int((x == "yes").sum())),
            confidence_values=("curation_confidence", lambda x: uniq_join(x, n=5)),
            review_reasons=("review_reason", lambda x: uniq_join(x, n=4)),
        )
        .reset_index()
    )

    # Special collapsed PMIDs: one row pointing to collapsed workbook.
    special_rows = []
    for pmid, sub in special.groupby("PMID"):
        collapsed = OUT / f"PMID_{pmid}_single_cell_collapsed_review.xlsx"
        special_rows.append({
            "PMID": pmid,
            "Title": first_nonempty(sub.get("Title", [])),
            "review_mode": "collapsed_special",
            "primary_review_file": str(collapsed),
            "n_rows": len(sub),
            "n_runs": sub["Run"].nunique() if "Run" in sub.columns else "",
            "n_biosamples": sub["BioSample"].nunique() if "BioSample" in sub.columns else "",
            "curator_action": "Review collapsed workbook only; do not manually curate SRR-level rows.",
            "special_handling": first_nonempty(sub.get("special_handling", [])),
            "curation_scope": first_nonempty(sub.get("curation_scope", [])),
            "review_unit": first_nonempty(sub.get("curator_review_unit", [])),
        })

    special_df = pd.DataFrame(special_rows)

    grouped["review_mode"] = "group_level"
    grouped["primary_review_file"] = grouped["PMID"].map(
        lambda p: str(OUT / f"PMID_{p}_curator_review_view.xlsx")
    )
    grouped["curator_action"] = "Review this biological/sample group; inspect representative rows if needed."

    # Put useful columns first.
    front = [
        "PMID", "Title", "review_mode", "primary_review_file",
        "n_rows", "n_runs", "n_biosamples", "n_experiments",
        "sra_row_omics", "experimental_factor", "control_role",
        "Life_Stage", "Cell_Cycle_Stage", "Strain", "Substrain",
        "Target", "Mutant", "Condition1", "Condition2", "Condition3",
        "background_or_control_1",
        "assigned_control_biosample1", "assigned_control_sample1",
        "background_or_control_2",
        "assigned_control_biosample2", "assigned_control_sample2",
        "curator_condition_note", "needs_review_yes",
        "confidence_values", "review_reasons",
        "example_runs", "example_biosamples", "example_samples",
        "curator_action",
    ]
    front = [c for c in front if c in grouped.columns]
    grouped = grouped[front + [c for c in grouped.columns if c not in front]]

    grouped = grouped.sort_values(["PMID", "experimental_factor", "control_role", "Mutant", "Condition1"])

    overview = pd.DataFrame([{
        "n_pmids_total": big["PMID"].nunique(),
        "n_row_level_pmids": ordinary["PMID"].nunique(),
        "n_special_collapsed_pmids": special["PMID"].nunique(),
        "n_srr_rows_total": len(big),
        "n_row_level_groups": len(grouped),
        "n_special_rows": len(special_df),
    }])

    out_xlsx = OUT / "curator_group_level_review_index.xlsx"
    out_tsv = OUT / "curator_group_level_review_index.tsv"

    grouped.to_csv(out_tsv, sep="\t", index=False)

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Overview", index=False)
        grouped.to_excel(writer, sheet_name="Group_Level_Index", index=False)
        special_df.to_excel(writer, sheet_name="Special_Collapsed", index=False)

    print("\n=== Group-level curator index written ===")
    print(out_xlsx)
    print(out_tsv)
    print("\nOverview:")
    print(overview.to_string(index=False))

    if not special_df.empty:
        print("\nSpecial collapsed:")
        print(special_df.to_string(index=False))


if __name__ == "__main__":
    main()
