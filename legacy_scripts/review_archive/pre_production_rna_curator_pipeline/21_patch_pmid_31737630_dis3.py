#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
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


def is_wt_control(row):
    mut = clean(row.get("Mutant", "")).lower()
    role = clean(row.get("control_role", "")).lower()
    return role == "control" and mut in {"wild type", "wt", "control", "vector control", "transfection control"}


def is_dis3_dd(mut):
    m = clean(mut).lower()
    return "dis3" in m and "dd" in m


def has_glcn(row):
    txt = " ".join([
        clean(row.get("Mutant", "")),
        clean(row.get("Condition1", "")),
        clean(row.get("curator_condition_note", "")),
    ]).lower()
    return "glcn" in txt


def uniq_join(vals):
    vals = sorted(set(clean(v) for v in vals if clean(v)))
    return ";".join(vals)


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


def assign_controls(df):
    df = df.copy()

    # Build same-stage lookup after canonicalization.
    wt_by_stage = {}
    untreated_dis3_by_stage = {}

    for idx, row in df.iterrows():
        stage = clean(row.get("Cell_Cycle_Stage", ""))

        if is_wt_control(row):
            wt_by_stage.setdefault(stage, []).append(idx)

        if (
            clean(row.get("Mutant", "")) == "PfDis3-DD"
            and clean(row.get("Condition1", "")) != "GlcN+"
            and clean(row.get("control_role", "")) == "experimental"
        ):
            untreated_dis3_by_stage.setdefault(stage, []).append(idx)

    for idx, row in df.iterrows():
        mut = clean(row.get("Mutant", ""))
        if mut != "PfDis3-DD":
            continue

        stage = clean(row.get("Cell_Cycle_Stage", ""))
        condition = clean(row.get("Condition1", ""))

        if condition == "GlcN+":
            ctrl_idxs = untreated_dis3_by_stage.get(stage, [])
            ctrl_note = "same-stage untreated PfDis3-DD control; confirm from paper"
            note = (
                f"GlcN-treated PfDis3-DD sample; compare to same-stage untreated PfDis3-DD. "
                f"Stage={stage or 'unknown'}."
            )
        else:
            ctrl_idxs = wt_by_stage.get(stage, [])
            ctrl_note = "same-stage WT / 3D7-G7 background control; confirm from paper"
            note = (
                f"Untreated PfDis3-DD sample; compare to same-stage WT/background. "
                f"Stage={stage or 'unknown'}."
            )

        if ctrl_idxs:
            ctrl = df.loc[ctrl_idxs]

            df.at[idx, "assigned_control1"] = uniq_join(ctrl.get("Run", []))
            df.at[idx, "assigned_control_biosample1"] = uniq_join(ctrl.get("BioSample", []))
            df.at[idx, "assigned_control_sample1"] = uniq_join(ctrl.get("SampleName", []))
            df.at[idx, "background_or_control_1"] = ctrl_note
            df.at[idx, "curator_condition_note"] = note

            reason = remove_stale_reasons(df.at[idx, "review_reason"])
            reason = append_reason(reason, "Control assignment inferred by PMID-specific Dis3 rule; curator should confirm from paper.")
            df.at[idx, "review_reason"] = reason

            df.at[idx, "needs_human_review"] = "yes"
            df.at[idx, "review_priority"] = "medium"
            df.at[idx, "curation_confidence"] = "medium"

    return df


def patch_file(path):
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")

    needed = [
        "Mutant",
        "Target",
        "Condition1",
        "experimental_factor",
        "control_role",
        "curator_condition_note",
        "review_reason",
        "needs_human_review",
        "review_priority",
        "curation_confidence",
        "assigned_control1",
        "assigned_control_biosample1",
        "assigned_control_sample1",
        "background_or_control_1",
    ]
    df = ensure_cols(df, needed)

    n_dis3_before = df["Mutant"].map(lambda x: is_dis3_dd(x)).sum()

    for idx, row in df.iterrows():
        mut = clean(row.get("Mutant", ""))

        if not is_dis3_dd(mut):
            continue

        glcn = has_glcn(row)

        df.at[idx, "Target"] = "PfDis3"
        df.at[idx, "Mutant"] = "PfDis3-DD"
        df.at[idx, "control_role"] = "experimental"

        if glcn:
            df.at[idx, "Condition1"] = "GlcN+"
            df.at[idx, "experimental_factor"] = "drug"
        else:
            # Preserve any real condition, but remove embedded GlcN from mutant.
            if clean(row.get("Condition1", "")).lower() in {"glcn+", "glcn"}:
                df.at[idx, "Condition1"] = "GlcN+"
                df.at[idx, "experimental_factor"] = "drug"
            else:
                df.at[idx, "Condition1"] = clean(row.get("Condition1", ""))
                df.at[idx, "experimental_factor"] = "genetic"

    df = assign_controls(df)

    df.to_csv(path, sep="\t", index=False)

    print(f"Updated {path}")
    print(f"Dis3 rows patched: {n_dis3_before}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid", default="31737630")
    args = ap.parse_args()

    pmid = clean(args.pmid)
    if pmid != "31737630":
        print(f"No Dis3 patch configured for PMID {pmid}; no-op.")
        return

    files = [
        OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv",
        OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv",
    ]

    for f in files:
        if f.exists():
            patch_file(f)
        else:
            print(f"Missing, skipped: {f}")


if __name__ == "__main__":
    main()
