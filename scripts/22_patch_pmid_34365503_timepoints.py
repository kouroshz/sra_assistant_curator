#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

DAY_RE = re.compile(r"^D\d+$", re.I)

def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    return x

def patch_file(path):
    df = pd.read_csv(path, sep="\t", dtype=str).fillna("")

    for c in ["Cell_Cycle_Stage", "Condition2", "Life_Stage",
              "experimental_factor", "curator_condition_note",
              "review_reason", "needs_human_review",
              "review_priority", "curation_confidence"]:
        if c not in df.columns:
            df[c] = ""

    n = 0

    for idx, row in df.iterrows():
        cc = clean(row.get("Cell_Cycle_Stage", ""))

        if DAY_RE.match(cc):
            df.at[idx, "Condition2"] = cc
            df.at[idx, "Cell_Cycle_Stage"] = ""

            if not clean(row.get("Life_Stage", "")):
                df.at[idx, "Life_Stage"] = "gametocyte/developmental timecourse"

            old_factor = clean(row.get("experimental_factor", ""))
            if old_factor == "genetic":
                df.at[idx, "experimental_factor"] = "genetic + developmental_timecourse"
            elif not old_factor:
                df.at[idx, "experimental_factor"] = "developmental_timecourse"

            note = clean(row.get("curator_condition_note", ""))
            add = f"Developmental timepoint {cc}; moved from Cell_Cycle_Stage to Condition2."
            df.at[idx, "curator_condition_note"] = (note + "; " + add).strip("; ")

            reason = clean(row.get("review_reason", ""))
            add_reason = "Developmental day/timepoint parsed; curator should confirm from paper."
            if add_reason not in reason:
                df.at[idx, "review_reason"] = (reason + "; " + add_reason).strip("; ")

            df.at[idx, "needs_human_review"] = "yes"
            df.at[idx, "review_priority"] = "medium"
            df.at[idx, "curation_confidence"] = "medium"
            n += 1

    df.to_csv(path, sep="\t", index=False)
    print(f"Updated {path}; moved D* timepoints: {n}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmid", default="34365503")
    args = ap.parse_args()

    if clean(args.pmid) != "34365503":
        print(f"No patch configured for PMID {args.pmid}; no-op.")
        return

    for suffix in [
        "agent_filled_master_rows.tsv",
        "agent_filled_master_rows_with_paper_context.tsv",
    ]:
        f = OUT / f"PMID_34365503_{suffix}"
        if f.exists():
            patch_file(f)
        else:
            print(f"Missing: {f}")

if __name__ == "__main__":
    main()
