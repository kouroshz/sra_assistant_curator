#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


CONTROL_MUTANTS = {
    "wild type",
    "wildtype",
    "wt",
    "vector control",
    "transfection control",
}


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def lower(x):
    return clean(x).lower()


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


def is_temperature(cond):
    return bool(re.search(r"^\d+(?:\.\d+)?\s*c$", clean(cond).replace("°", ""), flags=re.I))


def is_control_mutant(mutant):
    return lower(mutant) in CONTROL_MUTANTS


def experimental_factor(row, stage_only_design=False, genetic_design=False):
    cond = clean(row.get("Condition1", ""))
    cond_l = lower(cond)
    mutant = clean(row.get("Mutant", ""))
    mutant_l = lower(mutant)

    if is_temperature(cond):
        return "temperature"

    if any(x in cond_l for x in ["starv", "nutrient", "glucose", "isoleucine", "amino acid", "serum-free"]):
        return "nutrient"

    if any(x in cond_l for x in ["glcn", "shld", "dha", "artemisinin", "drug", "wr", "rapamycin", "atc", "dd"]):
        return "drug"

    if any(x in cond_l for x in ["baseline", "static", "suspended", "suspension", "hypoxia", "culture"]):
        return "culture_condition"

    if any(x in cond_l for x in ["hpi", "hour", "hr", "day", "dpi", "time"]):
        return "timecourse"

    if mutant and not is_control_mutant(mutant):
        return "genetic"

    # WT/vector/transfection controls in a genetic perturbation paper
    # are part of the genetic/background-control design.
    if genetic_design and is_control_mutant(mutant):
        return "genetic"

    if stage_only_design:
        return "developmental"

    return "unknown"


def control_role(row):
    cond = clean(row.get("Condition1", ""))
    cond_l = lower(cond)
    mutant = clean(row.get("Mutant", ""))
    bg = lower(row.get("background_or_control_1", ""))
    assigned = clean(row.get("assigned_control1", ""))

    if cond == "37C":
        return "control"

    if cond in {"Baseline", "Static"}:
        return "control"

    if cond in {"41C"}:
        return "experimental"

    if "control condition" in bg:
        return "control"

    if bg == "yes" or bg.startswith("control for"):
        return "control"

    if is_control_mutant(mutant) and not cond:
        return "control"

    if assigned:
        return "experimental"

    if cond:
        return "experimental"

    if mutant and not is_control_mutant(mutant):
        return "experimental"

    return "unknown"


def curator_note(row):
    cond = clean(row.get("Condition1", ""))
    cond_l = lower(cond)
    mutant = clean(row.get("Mutant", ""))
    target = clean(row.get("Target", ""))
    strain = clean(row.get("Strain", ""))
    stage = clean(row.get("Cell_Cycle_Stage", ""))
    role = clean(row.get("control_role", ""))
    assigned = clean(row.get("assigned_control1", ""))
    bg = clean(row.get("background_or_control_1", ""))

    label = " / ".join([x for x in [strain, stage, mutant, cond] if x])

    if cond == "41C":
        return "41C heat-shock sample; compare to same-strain/same-genotype 37C controls."

    if cond == "37C":
        return "37C control condition for matched heat-shock comparison."

    if cond == "GlcN+":
        return "GlcN-treated conditional PfRrp6-DD sample; compare to untreated PfRrp6-DD same stage/clone when available."

    if cond == "Shld1+":
        return "Shld1+ PfRrp6-FKBP sample; compare to matched Shld1- control."

    if cond == "Shld1-":
        return "Shld1- PfRrp6-FKBP control condition for Shld1+ comparison."

    if cond.startswith("WR "):
        return "WR-selected PfMaf1-OE sample; confirm whether WR indicates selection context or acute treatment."

    if cond == "Baseline":
        return "Baseline culture control condition."

    if cond == "Static":
        return "Static culture control condition."

    if cond == "Suspended":
        return "Moving-suspension culture condition; compare to same-strain Baseline and/or Static controls."

    if "starv" in cond_l or "nutrient" in cond_l:
        return f"{cond} sample; compare to matched nutrient-replete/control condition."

    if is_control_mutant(mutant) and role == "control":
        return "Wild-type/vector/background control sample."

    if mutant and not is_control_mutant(mutant) and assigned:
        return f"{label}; experimental sample with proposed matched control assignment."

    if mutant and not is_control_mutant(mutant):
        if target:
            return f"Genetic perturbation of {target}; confirm matched background/control from paper."
        return "Genetic perturbation sample; confirm matched background/control from paper."

    if bg:
        return bg

    return "Curator should confirm experimental condition and comparator."


def detect_genetic_design(df):
    if "Mutant" not in df.columns:
        return False

    mutants = {clean(x) for x in df["Mutant"] if clean(x)}
    non_control_mutants = [m for m in mutants if not is_control_mutant(m)]

    return bool(non_control_mutants)


def detect_stage_only_design(df):
    if "Cell_Cycle_Stage" not in df.columns:
        return False

    stages = {clean(x) for x in df["Cell_Cycle_Stage"] if clean(x)}
    conditions = {clean(x) for x in df.get("Condition1", pd.Series([""] * len(df))) if clean(x)}
    mutants = {clean(x) for x in df.get("Mutant", pd.Series([""] * len(df))) if clean(x)}

    if len(stages) > 1 and not conditions:
        non_control_mutants = [m for m in mutants if not is_control_mutant(m)]
        if not non_control_mutants:
            return True

    return False


def add_fields(df):
    df = df.copy().fillna("")

    for c in ["experimental_factor", "control_role", "curator_condition_note"]:
        if c not in df.columns:
            df[c] = ""

    stage_only = detect_stage_only_design(df)
    genetic_design = detect_genetic_design(df)

    for idx, row in df.iterrows():
        factor = experimental_factor(
            row,
            stage_only_design=stage_only,
            genetic_design=genetic_design,
        )
        df.at[idx, "experimental_factor"] = factor

    # Need experimental_factor first, then role/note.
    for idx, row in df.iterrows():
        role = control_role(row)
        df.at[idx, "control_role"] = role

    for idx, row in df.iterrows():
        df.at[idx, "curator_condition_note"] = curator_note(row)

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = clean(args.pmid)

    rows_file = find_rows_file(pmid)
    df = pd.read_csv(rows_file, sep="\t", dtype=str).fillna("")
    out_df = add_fields(df)
    out_df.to_csv(rows_file, sep="\t", index=False)

    workbook = find_workbook(pmid)

    if workbook is not None:
        sheets = pd.read_excel(workbook, sheet_name=None, dtype=str)
        sheets = {k: v.fillna("") for k, v in sheets.items()}

        if "Sheet" in sheets and "Run" in sheets["Sheet"].columns:
            main_sheet = sheets["Sheet"].copy()

            for c in ["experimental_factor", "control_role", "curator_condition_note"]:
                if c not in main_sheet.columns:
                    main_sheet[c] = ""

            lookup = {
                clean(r["Run"]): r
                for _, r in out_df.iterrows()
                if clean(r.get("Run", ""))
            }

            for idx, row in main_sheet.iterrows():
                run = clean(row.get("Run", ""))
                if run not in lookup:
                    continue
                for c in ["experimental_factor", "control_role", "curator_condition_note"]:
                    main_sheet.at[idx, c] = lookup[run].get(c, "")

            sheets["Sheet"] = main_sheet

            with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
                for s, d in sheets.items():
                    d.to_excel(writer, sheet_name=s[:31], index=False)

    print(f"\n=== Added curator condition fields for PMID {pmid} ===")
    print(f"Rows file updated: {rows_file}")
    if workbook:
        print(f"Workbook updated: {workbook}")

    show_cols = [
        "Run",
        "Mutant",
        "Condition1",
        "experimental_factor",
        "control_role",
        "curator_condition_note",
    ]
    show_cols = [c for c in show_cols if c in out_df.columns]
    print(out_df[show_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
