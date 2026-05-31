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


def ensure_col(df, col):
    if col not in df.columns:
        df[col] = ""


def append_reason(existing, new):
    existing = clean(existing)
    new = clean(new)
    if not new:
        return existing
    if not existing:
        return new
    if new in existing:
        return existing
    return existing + "; " + new


def same_strain_stage_controls(df, row, condition):
    mask = (
        (df["Strain"].map(clean) == clean(row.get("Strain", ""))) &
        (df["Cell_Cycle_Stage"].map(clean) == clean(row.get("Cell_Cycle_Stage", ""))) &
        (df["Condition1"].map(clean) == condition)
    )
    return df.loc[mask, "Run"].map(clean).tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    in_xlsx = OUT / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.xlsx"
    in_rows = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"
    context_json = OUT / f"PMID_{pmid}_paper_context.json"

    if not in_xlsx.exists():
        raise FileNotFoundError(f"Missing filled master workbook: {in_xlsx}")
    if not in_rows.exists():
        raise FileNotFoundError(f"Missing filled master rows TSV: {in_rows}")
    if not context_json.exists():
        raise FileNotFoundError(f"Missing paper context JSON: {context_json}. Run script 07 first.")

    context = json.loads(context_json.read_text())

    all_sheets = pd.read_excel(in_xlsx, sheet_name=None, dtype=str)
    main_sheet_name = "Sheet"
    master = all_sheets[main_sheet_name].fillna("")
    rows = pd.read_csv(in_rows, sep="\t", dtype=str).fillna("")

    for df in [master, rows]:
        for col in [
            "paper_note",
            "paper_omics_used",
            "paper_omics_mentions",
            "paper_keyword_omics_mentions",
            "condition_interpretation",
            "paper_context_source",
            "paper_context_confidence",
            "paper_context_needs_review",
            "paper_context_review_reason",
            "assigned_control2",
            "background_or_control_2",
        ]:
            ensure_col(df, col)

    paper_note = clean(context.get("paper_note", ""))
    paper_omics_used = clean(context.get("paper_omics_used", ""))
    paper_omics_mentions = clean(context.get("paper_omics_mentions", ""))
    paper_keyword_omics_mentions = clean(context.get("paper_keyword_omics_mentions", ""))
    condition_interpretation = clean(context.get("condition_interpretation", ""))
    paper_review_reason = clean(context.get("review_reason", ""))

    # Identify PMID rows in master.
    pmid_mask = master["PMID"].map(clean) == pmid

    # Apply context columns to all rows for this PMID.
    for df, mask in [
        (master, pmid_mask),
        (rows, pd.Series([True] * len(rows), index=rows.index)),
    ]:
        df.loc[mask, "paper_note"] = paper_note
        df.loc[mask, "paper_omics_used"] = paper_omics_used
        df.loc[mask, "paper_omics_mentions"] = paper_omics_mentions
        df.loc[mask, "paper_keyword_omics_mentions"] = paper_keyword_omics_mentions
        df.loc[mask, "condition_interpretation"] = condition_interpretation
        df.loc[mask, "paper_context_source"] = "local PDF keyword extraction"
        df.loc[mask, "paper_context_confidence"] = "medium"
        df.loc[mask, "paper_context_needs_review"] = "yes"
        df.loc[mask, "paper_context_review_reason"] = paper_review_reason

    # Paper-aware condition refinement.
    # This is still conservative: it updates control/background logic but keeps curator review
    # for Suspended rows where biological comparison matters.
    def refine_condition_df(df):
        df = df.copy()

        for idx, row in df.iterrows():
            cond = clean(row.get("Condition1", ""))

            if cond == "Baseline":
                df.at[idx, "background_or_control_1"] = "baseline control condition"
                df.at[idx, "needs_human_review"] = "no"
                df.at[idx, "review_priority"] = "low"
                # keep review_reason blank unless there is a non-paper issue
                if clean(df.at[idx, "review_reason"]) == "Condition control assignment requires paper/manual confirmation":
                    df.at[idx, "review_reason"] = ""

            elif cond == "Static":
                # Static is explicitly a static culture control condition in the paper.
                df.at[idx, "background_or_control_1"] = "static culture control condition"
                df.at[idx, "assigned_control1"] = ";".join(same_strain_stage_controls(df, row, "Baseline"))
                df.at[idx, "background_or_control_2"] = "baseline controls also available for static-vs-baseline check"
                df.at[idx, "curation_confidence"] = "high"
                df.at[idx, "needs_human_review"] = "no"
                df.at[idx, "review_priority"] = "low"
                df.at[idx, "review_reason"] = ""

            elif cond == "Suspended":
                baseline = same_strain_stage_controls(df, row, "Baseline")
                static = same_strain_stage_controls(df, row, "Static")

                df.at[idx, "assigned_control1"] = ";".join(baseline)
                df.at[idx, "background_or_control_1"] = "same-strain/stage baseline controls"

                if static:
                    df.at[idx, "assigned_control2"] = ";".join(static)
                    df.at[idx, "background_or_control_2"] = "same-strain/stage static controls"

                df.at[idx, "curation_confidence"] = "medium"
                df.at[idx, "needs_human_review"] = "yes"
                df.at[idx, "review_priority"] = "medium"
                df.at[idx, "review_reason"] = append_reason(
                    "",
                    "Paper supports Baseline/Static as controls for Suspended; curator should confirm final comparator choice"
                )

        return df

    condition_values = set(rows["Condition1"].map(clean)) if "Condition1" in rows.columns else set()

    if condition_interpretation and {"Baseline", "Static", "Suspended"}.intersection(condition_values):
        rows_refined = refine_condition_df(rows)
    else:
        rows_refined = rows.copy()

    # Push refined row-level values back into master by Run.
    row_lookup = {clean(r["Run"]): r for _, r in rows_refined.iterrows()}

    for idx, row in master.loc[pmid_mask].iterrows():
        run = clean(row.get("Run", ""))
        if run not in row_lookup:
            continue
        rr = row_lookup[run]
        for col in rows_refined.columns:
            if col in master.columns:
                master.at[idx, col] = rr[col]

    all_sheets[main_sheet_name] = master

    out_xlsx = OUT / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.with_paper_context.xlsx"
    out_rows = OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        for sheet_name, df in all_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    rows_refined.to_csv(out_rows, sep="\t", index=False)

    print(f"\n=== Applied paper context to PMID {pmid} ===")
    print(f"Paper note: {paper_note}")
    print(f"Omics used: {paper_omics_used}")
    print(f"Omics mentions: {paper_omics_mentions}")
    print(f"Keyword omics mentions, unclassified: {paper_keyword_omics_mentions}")

    print("\nReview counts after paper context:")
    print(rows_refined["needs_human_review"].value_counts(dropna=False).to_string())

    print("\nCondition/control summary:")
    show = (
        rows_refined
        .groupby(["Strain", "Condition1", "background_or_control_1", "needs_human_review"], dropna=False)
        .size()
        .reset_index(name="n")
    )
    print(show.to_string(index=False))

    print("\nWrote:")
    print(out_xlsx)
    print(out_rows)
    print("\nOpen with:")
    print(f"open {out_xlsx}")


if __name__ == "__main__":
    main()
