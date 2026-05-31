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


def ensure_cols(df, cols):
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


def append_reason(old, new):
    old = clean(old)
    new = clean(new)
    if not old:
        return new
    if new in old:
        return old
    return old + "; " + new


def remove_stale_reasons(reason):
    reason = clean(reason)
    parts = [p.strip() for p in reason.split(";") if p.strip()]
    keep = []
    for p in parts:
        low = p.lower()
        if "no obvious control found" in low:
            continue
        if low == "missing strain":
            continue
        keep.append(p)
    return "; ".join(keep)


def uniq_join(vals):
    vals = sorted(set(clean(v) for v in vals if clean(v)))
    return ";".join(vals)


def is_wt(row):
    return clean(row.get("Mutant", "")) == "wild type"


def is_arp4(row):
    return clean(row.get("Mutant", "")) == "PfArp4"


def is_glcn(row):
    return clean(row.get("Condition1", "")) == "GlcN+"


def patch_file(path):
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")

    needed = [
        "Mutant", "Target", "Condition1", "Strain", "Substrain",
        "experimental_factor", "control_role", "curator_condition_note",
        "review_reason", "needs_human_review", "review_priority",
        "curation_confidence", "assigned_control1",
        "assigned_control_biosample1", "assigned_control_sample1",
        "assigned_control2", "assigned_control_biosample2",
        "assigned_control_sample2", "background_or_control_1",
        "background_or_control_2",
    ]
    df = ensure_cols(df, needed)

    # Canonicalize labels.
    for idx, row in df.iterrows():
        mut = clean(row.get("Mutant", ""))

        if mut in {"PfArp4_GlcN+", "PfArp4-GlcN+", "PfArp4 GlcN+"}:
            df.at[idx, "Target"] = "PfArp4"
            df.at[idx, "Mutant"] = "PfArp4"
            df.at[idx, "Condition1"] = "GlcN+"
            df.at[idx, "experimental_factor"] = "genetic + drug"
            df.at[idx, "control_role"] = "experimental"

        elif mut == "PfArp4":
            df.at[idx, "Target"] = "PfArp4"
            df.at[idx, "Mutant"] = "PfArp4"
            df.at[idx, "experimental_factor"] = "genetic"
            df.at[idx, "control_role"] = "experimental"

        elif mut in {"WT_3D7G7", "WT 3D7G7", "WT_3D7-G7"}:
            df.at[idx, "Target"] = ""
            df.at[idx, "Mutant"] = "wild type"
            df.at[idx, "Strain"] = clean(row.get("Strain", "")) or "3D7"
            df.at[idx, "Substrain"] = clean(row.get("Substrain", "")) or "3D7-G7"
            df.at[idx, "Condition1"] = ""
            df.at[idx, "experimental_factor"] = "genetic"
            df.at[idx, "control_role"] = "control"
            df.at[idx, "background_or_control_1"] = "yes"
            df.at[idx, "curator_condition_note"] = "WT 3D7-G7 background control sample."

        elif mut in {"WT_3D7G7_GlcN+", "WT 3D7G7 GlcN+", "WT_3D7-G7_GlcN+"}:
            df.at[idx, "Target"] = ""
            df.at[idx, "Mutant"] = "wild type"
            df.at[idx, "Strain"] = clean(row.get("Strain", "")) or "3D7"
            df.at[idx, "Substrain"] = clean(row.get("Substrain", "")) or "3D7-G7"
            df.at[idx, "Condition1"] = "GlcN+"
            df.at[idx, "experimental_factor"] = "drug"
            df.at[idx, "control_role"] = "control"
            df.at[idx, "background_or_control_1"] = "GlcN-treated WT/background control"
            df.at[idx, "curator_condition_note"] = "GlcN-treated WT 3D7-G7 background control sample."

    # Build control lookups by stage.
    wt_by_stage = {}
    wt_glcn_by_stage = {}
    arp4_untreated_by_stage = {}

    for idx, row in df.iterrows():
        stage = clean(row.get("Cell_Cycle_Stage", ""))

        if is_wt(row) and not is_glcn(row):
            wt_by_stage.setdefault(stage, []).append(idx)

        if is_wt(row) and is_glcn(row):
            wt_glcn_by_stage.setdefault(stage, []).append(idx)

        if is_arp4(row) and not is_glcn(row):
            arp4_untreated_by_stage.setdefault(stage, []).append(idx)

    # Assign controls for PfArp4 rows.
    for idx, row in df.iterrows():
        if not is_arp4(row):
            continue

        stage = clean(row.get("Cell_Cycle_Stage", ""))

        if is_glcn(row):
            ctrl1 = df.loc[arp4_untreated_by_stage.get(stage, [])]
            ctrl2 = df.loc[wt_glcn_by_stage.get(stage, [])]

            if not ctrl1.empty:
                df.at[idx, "assigned_control1"] = uniq_join(ctrl1.get("Run", []))
                df.at[idx, "assigned_control_biosample1"] = uniq_join(ctrl1.get("BioSample", []))
                df.at[idx, "assigned_control_sample1"] = uniq_join(ctrl1.get("SampleName", []))
                df.at[idx, "background_or_control_1"] = "same-stage untreated PfArp4 control; confirm from paper"

            if not ctrl2.empty:
                df.at[idx, "assigned_control2"] = uniq_join(ctrl2.get("Run", []))
                df.at[idx, "assigned_control_biosample2"] = uniq_join(ctrl2.get("BioSample", []))
                df.at[idx, "assigned_control_sample2"] = uniq_join(ctrl2.get("SampleName", []))
                df.at[idx, "background_or_control_2"] = "same-stage GlcN-treated WT/background control; confirm from paper"

            df.at[idx, "curator_condition_note"] = (
                f"GlcN-treated PfArp4 sample; compare to same-stage untreated PfArp4 "
                f"and GlcN-treated WT/background where available. Stage={stage or 'unknown'}."
            )

        else:
            ctrl1 = df.loc[wt_by_stage.get(stage, [])]

            if not ctrl1.empty:
                df.at[idx, "assigned_control1"] = uniq_join(ctrl1.get("Run", []))
                df.at[idx, "assigned_control_biosample1"] = uniq_join(ctrl1.get("BioSample", []))
                df.at[idx, "assigned_control_sample1"] = uniq_join(ctrl1.get("SampleName", []))
                df.at[idx, "background_or_control_1"] = "same-stage WT / 3D7-G7 background control; confirm from paper"

            df.at[idx, "curator_condition_note"] = (
                f"Untreated PfArp4 sample; compare to same-stage WT/background. "
                f"Stage={stage or 'unknown'}."
            )

        reason = remove_stale_reasons(df.at[idx, "review_reason"])
        reason = append_reason(reason, "Control assignment inferred by PMID-specific PfArp4/GlcN rule; curator should confirm from paper.")
        df.at[idx, "review_reason"] = reason
        df.at[idx, "needs_human_review"] = "yes"
        df.at[idx, "review_priority"] = "medium"
        df.at[idx, "curation_confidence"] = "medium"

    # Clean stale review reasons for WT controls.
    for idx, row in df.iterrows():
        if is_wt(row):
            df.at[idx, "review_reason"] = remove_stale_reasons(row.get("review_reason", ""))
            df.at[idx, "needs_human_review"] = "no"
            df.at[idx, "review_priority"] = "low"
            df.at[idx, "curation_confidence"] = "high"

    df.to_csv(path, sep="\t", index=False)
    print(f"Updated {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid", default="32552779")
    args = ap.parse_args()

    if clean(args.pmid) != "32552779":
        print(f"No PfArp4 patch configured for PMID {args.pmid}; no-op.")
        return

    for suffix in [
        "agent_filled_master_rows.tsv",
        "agent_filled_master_rows_with_paper_context.tsv",
    ]:
        f = OUT / f"PMID_32552779_{suffix}"
        if f.exists():
            patch_file(f)
        else:
            print(f"Missing: {f}")


if __name__ == "__main__":
    main()
