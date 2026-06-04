#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"

GOLD = DATA / "32487761_Manually_Curated.xlsx"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def norm(x):
    x = clean(x).lower()
    x = x.replace("contorl", "control")
    x = x.replace("durg", "drug")
    x = x.replace("_", " ").replace("-", " ")
    x = re.sub(r"\s+", " ", x)
    return x.strip()


def compact(x):
    x = clean(x).lower()
    x = x.replace("contorl", "control")
    x = x.replace("durg", "drug")
    return re.sub(r"[^a-z0-9+]+", "", x)


def norm_stage(x):
    x = norm(x)
    if "ring" in x or x == "r":
        return "ring"
    if "troph" in x or x == "t":
        return "trophozoite"
    if "schiz" in x or x == "s":
        return "schizont"
    return x


def find_col(df, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for c in candidates:
        if c.strip().lower() in lookup:
            return lookup[c.strip().lower()]
    return None


def get_col(df, candidates):
    c = find_col(df, candidates)
    if c is None:
        return pd.Series([""] * len(df), index=df.index)
    return df[c].fillna("").astype(str)


def compare_basic(g, m, normalizer=norm):
    g = normalizer(g)
    m = normalizer(m)

    if not g and not m:
        return "both_blank"
    if g == m:
        return "match"
    if not m:
        return "manual_blank"
    if not g:
        return "agent_blank"
    return "mismatch"


def compare_mutant(agent_mutant, agent_condition, manual_mutant, manual_condition):
    am = compact(agent_mutant)
    ac = compact(agent_condition)
    mm = compact(manual_mutant)
    mc = compact(manual_condition)

    if not am and not mm:
        return "both_blank"

    if am == mm:
        return "match"

    # Agent split condition from mutant, while manual may combine them.
    if am and ac and am in mm and ac in mm:
        return "structured_match"

    # Manual split condition from mutant, while agent may combine them.
    if mm and mc and mm in am and mc in am:
        return "structured_match"

    if compact(f"{agent_mutant}-{agent_condition}") == mm:
        return "structured_match"

    if not mm:
        return "manual_blank"
    if not am:
        return "agent_blank"

    return "mismatch"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    agent_file = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"
    if not agent_file.exists():
        raise FileNotFoundError(f"Missing agent-filled rows: {agent_file}. Run script 04 first.")

    if not GOLD.exists():
        raise FileNotFoundError(f"Missing gold-standard manual curation file: {GOLD}")

    agent = pd.read_csv(agent_file, sep="\t", dtype=str).fillna("")
    gold = pd.read_excel(GOLD, dtype=str).fillna("")

    agent_run_col = find_col(agent, ["Run"])
    gold_run_col = find_col(gold, ["Run"])

    if agent_run_col is None or gold_run_col is None:
        raise ValueError("Could not find Run column in agent or gold table.")

    agent["_run_norm"] = agent[agent_run_col].map(clean)
    gold["_run_norm"] = gold[gold_run_col].map(clean)

    agent_cmp = pd.DataFrame({
        "_run_norm": agent["_run_norm"],
        "agent_stage": get_col(agent, ["Cell_Cycle_Stage"]),
        "agent_life_stage": get_col(agent, ["Life_Stage"]),
        "agent_target": get_col(agent, ["Target"]),
        "agent_strain": get_col(agent, ["Strain"]),
        "agent_substrain": get_col(agent, ["Substrain"]),
        "agent_mutant": get_col(agent, ["Mutant"]),
        "agent_condition1": get_col(agent, ["Condition1"]),
        "agent_notes": get_col(agent, ["Notes"]),
        "agent_replicate": get_col(agent, ["replicate_number"]),
        "agent_control": get_col(agent, ["assigned_control1"]),
        "agent_confidence": get_col(agent, ["curation_confidence"]),
        "agent_needs_review": get_col(agent, ["needs_human_review"]),
        "agent_review_reason": get_col(agent, ["review_reason"]),
    })

    gold_cmp = pd.DataFrame({
        "_run_norm": gold["_run_norm"],
        "gold_stage": get_col(gold, ["Cell_Cycle_Stage", "Cell Cycle Stage"]),
        "gold_life_stage": get_col(gold, ["Life_Stage", "Life Stage"]),
        "gold_target": get_col(gold, ["Target"]),
        "gold_strain": get_col(gold, ["Strain"]),
        "gold_substrain": get_col(gold, ["Substrain"]),
        "gold_mutant": get_col(gold, ["Mutant"]),
        "gold_condition1": get_col(gold, ["Condition1"]),
        "gold_notes": get_col(gold, ["Notes"]),
        "gold_replicate": get_col(gold, ["replicate_number", "Replicates"]),
        "gold_control1": get_col(gold, ["assigned_control1", "assigned_control_1"]),
        "gold_control2": get_col(gold, ["assigned_control2", "assigned_control_2"]),
    })

    merged = agent_cmp.merge(gold_cmp, on="_run_norm", how="outer", indicator=True)

    merged["cmp_stage"] = merged.apply(
        lambda r: compare_basic(r["agent_stage"], r["gold_stage"], norm_stage), axis=1
    )
    merged["cmp_strain"] = merged.apply(
        lambda r: compare_basic(r["agent_strain"], r["gold_strain"], norm), axis=1
    )
    merged["cmp_mutant"] = merged.apply(
        lambda r: compare_mutant(
            r["agent_mutant"],
            r["agent_condition1"],
            r["gold_mutant"],
            r["gold_condition1"],
        ),
        axis=1,
    )
    merged["cmp_condition1"] = merged.apply(
        lambda r: compare_basic(r["agent_condition1"], r["gold_condition1"], norm), axis=1
    )
    merged["cmp_notes"] = merged.apply(
        lambda r: compare_basic(r["agent_notes"], r["gold_notes"], norm), axis=1
    )

    compare_cols = ["cmp_stage", "cmp_strain", "cmp_mutant"]

    def row_status(row):
        if row["_merge"] != "both":
            return row["_merge"]

        vals = [row[c] for c in compare_cols]
        ok = {"match", "structured_match", "both_blank", "manual_blank"}

        if all(v in ok for v in vals):
            if "structured_match" in vals:
                return "structured_match"
            return "match"

        if any(v == "mismatch" for v in vals):
            return "mismatch"

        return "needs_check"

    merged["row_status"] = merged.apply(row_status, axis=1)

    out_cmp = OUT / f"PMID_{pmid}_agent_vs_gold_standard.tsv"
    out_summary = OUT / f"PMID_{pmid}_agent_vs_gold_standard_summary.tsv"
    out_mismatch = OUT / f"PMID_{pmid}_agent_vs_gold_standard_mismatches.tsv"

    summary_rows = []

    for col in ["_merge", "row_status", "cmp_stage", "cmp_strain", "cmp_mutant", "cmp_condition1", "cmp_notes"]:
        for k, v in merged[col].value_counts(dropna=False).items():
            summary_rows.append({"category": col, "metric": k, "value": int(v)})

    summary = pd.DataFrame(summary_rows)

    mismatches = merged[
        (merged["row_status"] == "mismatch") |
        (merged["cmp_notes"] == "mismatch") |
        (merged["cmp_condition1"] == "mismatch")
    ].copy()

    merged.to_csv(out_cmp, sep="\t", index=False)
    summary.to_csv(out_summary, sep="\t", index=False)
    mismatches.to_csv(out_mismatch, sep="\t", index=False)

    print(f"\n=== Agent vs gold-standard evaluation for PMID {pmid} ===")
    print(f"Agent rows: {(merged['_merge'] != 'right_only').sum()}")
    print(f"Gold rows: {(merged['_merge'] != 'left_only').sum()}")
    print(f"Overlap rows: {(merged['_merge'] == 'both').sum()}")
    print(f"Agent rows not in gold: {(merged['_merge'] == 'left_only').sum()}")
    print(f"Gold rows not in agent: {(merged['_merge'] == 'right_only').sum()}")

    print("\nRow status:")
    print(merged["row_status"].value_counts(dropna=False).to_string())

    print("\nCore field comparisons:")
    for col in compare_cols:
        print(f"\n{col}:")
        print(merged[col].value_counts(dropna=False).to_string())

    print("\nCondition/notes comparisons, less strict:")
    for col in ["cmp_condition1", "cmp_notes"]:
        print(f"\n{col}:")
        print(merged[col].value_counts(dropna=False).to_string())

    print("\nWrote:")
    print(out_cmp)
    print(out_summary)
    print(out_mismatch)


if __name__ == "__main__":
    main()
