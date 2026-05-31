#!/usr/bin/env python3

from pathlib import Path
import argparse
import re
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
CACHE = DATA / "biosample_cache"

MASTER = DATA / "rna_seq_metadata_v1_2026-05-05.xlsx"


EXTRA_COLUMNS = [
    "curation_source",
    "curation_confidence",
    "curation_evidence",
    "curation_note",
    "needs_human_review",
    "review_priority",
    "review_reason",
    "reviewer",
    "review_status",
    "reviewer_note",
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


def find_col(df, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lookup:
            return lookup[key]
    return None


def ensure_col(df, col):
    if col not in df.columns:
        df[col] = ""
    return col


def get_first(row, cols):
    for c in cols:
        if c in row.index:
            v = clean(row[c])
            if v:
                return v
    return ""


def normalize_condition(x):
    x0 = clean(x)
    xl = x0.lower().replace("°", "")

    if xl in {"baseline", "base line"}:
        return "Baseline"
    if xl in {"suspended", "suspension"}:
        return "Suspended"
    if xl in {"static"}:
        return "Static"

    # Temperature treatments, e.g. 37C, 41C, 37 C
    m = re.search(r"(\d+(?:\.\d+)?)\s*c\b", xl)
    if m:
        return f"{m.group(1)}C"

    return x0


def normalize_stage(x):
    x0 = clean(x)
    xl = x0.lower()
    if "ring" in xl:
        return "Ring"
    if "troph" in xl:
        return "Trophozoite"
    if "schiz" in xl:
        return "Schizont"
    return x0


def normalize_strain(x, source_name="", title=""):
    text = f"{clean(x)} {clean(source_name)} {clean(title)}".lower()
    if "3d7-g7" in text:
        return "3D7-G7"
    if "nf54" in text:
        return "NF54"
    if "w2mef" in text:
        return "W2mef"
    if "dd2" in text:
        return "Dd2"
    if "pb31" in text:
        return "PB31"
    if "pb4" in text:
        return "PB4"
    if "3d7" in text:
        return "3D7"
    return clean(x)


def infer_substrain(source_name, genotype="", title=""):
    text = " ".join([clean(source_name), clean(genotype), clean(title)])
    m = re.search(r"(PfRrp6-DD-[A-Za-z0-9]+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    if "3D7-G7" in text:
        return "3D7-G7"
    if re.search(r"\bNF54\b", text):
        return "NF54"
    return ""


def parse_genotype(genotype, source_name="", title=""):
    g = clean(genotype).replace("contorl", "control").replace("durg", "drug")
    source = clean(source_name).replace("contorl", "control").replace("durg", "drug")
    title_clean = clean(title).replace("contorl", "control").replace("durg", "drug")
    text = f"{g} {source} {title_clean}".lower()

    out = {
        "Target": "",
        "Mutant": g,
        "Condition1": "",
        "Condition2": "",
        "Condition3": "",
        "parse_note": "",
        "parse_confidence": "high",
    }

    # Controls first, before generic WT parsing.
    if "transfection_control" in text or "transfection control" in text:
        out["Mutant"] = "transfection control"
        return out

    if "vector" in text and "control" in text:
        out["Mutant"] = "vector control"
        return out

    if "wild type" in text or re.search(r"\bwt\b", text):
        out["Mutant"] = "wild type"

    if "rrp6" in text:
        out["Target"] = "PfRrp6"
        if "fkbp" in text:
            out["Mutant"] = "PfRrp6-FKBP"
            if "shld1+" in text:
                out["Condition1"] = "Shld1+"
            elif "shld1-" in text:
                out["Condition1"] = "Shld1-"
        elif "glcn+" in text or "glcn" in text:
            out["Mutant"] = "PfRrp6-DD"
            out["Condition1"] = "GlcN+"
        elif "dd" in text:
            out["Mutant"] = "PfRrp6-DD"

    if "maf1" in text:
        out["Target"] = "PfMaf1"
        out["Mutant"] = "PfMaf1-OE"
        wr = re.search(r"(\d+(?:\.\d+)?)\s*nM\s*(?:drug\s*)?\(?WR\)?", source, flags=re.IGNORECASE)
        if wr:
            out["Condition1"] = f"WR {wr.group(1)} nM"
            out["parse_note"] = "WR dose parsed from BioSample source_name; likely selection context, confirm from paper."
            out["parse_confidence"] = "medium"

    if "ruf6" in text:
        out["Target"] = "RUF6"
        out["Mutant"] = "RUF6-OE"

    # Generic piggyBac/delta mutant parsing, e.g. {delta}DHC piggyBac mutant
    if "piggybac" in text or "piggyBac".lower() in text:
        raw = g or title_clean
        raw_norm = raw.replace("{delta}", "Δ").replace("delta", "Δ")
        out["Mutant"] = clean(raw_norm)
        m = re.search(r"(?:Δ|delta)\s*([A-Za-z0-9_.-]+)", raw_norm, flags=re.IGNORECASE)
        if m:
            out["Target"] = m.group(1)

    return out


def infer_replicate(title, source_name=""):
    text = " ".join([clean(title), clean(source_name)])

    # Handles rep1, rep2, _rep1_, -rep2-, etc.
    m = re.search(r"(?:^|[_\-\s])rep(?:licate)?[_\-\s]*(\d+)(?:$|[_\-\s])", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def is_control(mutant):
    return clean(mutant) in {"wild type", "vector control", "transfection control"}


def assign_controls_for_subset(sub):
    """
    Simple rule-based control assignment within one PMID subset.
    Uses only populated metadata, not manual annotations.
    """
    sub = sub.copy()

    for col in ["assigned_control1", "assigned_control2", "background_or_control_1", "background_or_control_2"]:
        if col not in sub.columns:
            sub[col] = ""

    for idx, row in sub.iterrows():
        mutant = clean(row.get("Mutant", ""))
        stage = clean(row.get("Cell_Cycle_Stage", ""))
        condition = clean(row.get("Condition1", ""))
        strain = clean(row.get("Strain", ""))
        target = clean(row.get("Target", ""))
        run = clean(row.get("Run", ""))

        same_stage = sub[sub["Cell_Cycle_Stage"].map(clean) == stage].copy()

        control_runs = []
        control_note = ""
        confidence = clean(row.get("curation_confidence", "high"))
        review = clean(row.get("needs_human_review", "no"))
        review_priority = clean(row.get("review_priority", "low"))
        review_reason = clean(row.get("review_reason", ""))

        if is_control(mutant):
            sub.at[idx, "background_or_control_1"] = "yes"
            continue

        if mutant == "PfRrp6-FKBP" and condition == "Shld1+":
            cand = same_stage[
                (same_stage["Mutant"].map(clean) == "PfRrp6-FKBP") &
                (same_stage["Condition1"].map(clean) == "Shld1-")
            ]
            control_runs = cand["Run"].map(clean).tolist()
            control_note = "same-stage PfRrp6-FKBP Shld1-"

        elif mutant == "PfRrp6-DD" and condition == "GlcN+":
            cand = same_stage[
                (same_stage["Mutant"].map(clean) == "PfRrp6-DD") &
                (same_stage["Condition1"].map(clean) == "")
            ]

            # Prefer same clone/substrain, e.g. PfRrp6-DD-1C.
            this_substrain = clean(row.get("Substrain", ""))
            if this_substrain:
                preferred = cand[cand["Substrain"].map(clean) == this_substrain]
                if not preferred.empty:
                    cand = preferred

            control_runs = cand["Run"].map(clean).tolist()
            control_note = "same-stage untreated PfRrp6-DD, clone-preferred when available"

        elif mutant == "RUF6-OE":
            cand = same_stage[same_stage["Mutant"].map(clean) == "vector control"]
            control_runs = cand["Run"].map(clean).tolist()
            control_note = "same-stage vector control"

        elif mutant == "PfMaf1-OE":
            cand = same_stage[same_stage["Mutant"].map(clean) == "vector control"]
            control_runs = cand["Run"].map(clean).tolist()
            control_note = "proposed same-stage vector control; confirm from paper"
            confidence = "medium"
            review = "yes"
            review_priority = "high"
            review_reason = append_reason(review_reason, "PfMaf1-OE control requires paper/manual confirmation")

        elif condition.endswith("C") and condition != "37C":
            # Generic fever/temperature-style design: compare elevated temperature to 37C
            # within same strain, stage, and mutant/genotype when available.
            cand = same_stage[
                (same_stage["Strain"].map(clean) == strain) &
                (same_stage["Condition1"].map(clean) == "37C")
            ]
            if mutant:
                cand = cand[cand["Mutant"].map(clean) == mutant]

            control_runs = cand["Run"].map(clean).tolist()
            control_note = "proposed same-strain/stage/genotype 37C control; confirm from paper"
            confidence = "medium"
            review = "yes"
            review_priority = "medium"
            review_reason = append_reason(review_reason, "Temperature control assignment requires paper/manual confirmation")

        elif condition == "37C":
            sub.at[idx, "background_or_control_1"] = "37C control condition"
            continue

        elif condition and condition not in {"Baseline"} and mutant == "":
            cand = same_stage[
                (same_stage["Strain"].map(clean) == strain) &
                (same_stage["Condition1"].map(clean) == "Baseline")
            ]
            control_runs = cand["Run"].map(clean).tolist()
            control_note = "proposed same-strain/stage Baseline control; confirm from paper"
            confidence = "medium"
            review = "yes"
            review_priority = "medium"
            review_reason = append_reason(review_reason, "Condition control assignment requires paper/manual confirmation")

        elif condition == "Baseline" and mutant == "":
            sub.at[idx, "background_or_control_1"] = "baseline/control condition"
            continue

        elif mutant == "PfRrp6-DD" and condition == "":
            cand = same_stage[
                (same_stage["Mutant"].map(clean) == "wild type") &
                (same_stage["Strain"].map(clean).isin(["3D7-G7", "3D7"]))
            ]
            # Prefer 3D7-G7
            preferred = cand[cand["Strain"].map(clean) == "3D7-G7"]
            if not preferred.empty:
                cand = preferred
            control_runs = cand["Run"].map(clean).tolist()
            control_note = "proposed same-stage WT 3D7/3D7-G7 background; confirm from paper"
            confidence = "medium"
            review = "yes"
            review_priority = "medium"
            review_reason = append_reason(review_reason, "PfRrp6-DD background/control requires confirmation")

        if mutant == "PfRrp6-FKBP" and condition == "Shld1-":
            # Shld1- is the matched control/background for Shld1+.
            sub.at[idx, "background_or_control_1"] = "control for PfRrp6-FKBP Shld1+"
            review = "no"
            review_priority = "low"

        elif control_runs:
            sub.at[idx, "assigned_control1"] = ";".join(control_runs)
            sub.at[idx, "background_or_control_1"] = control_note

        elif not is_control(mutant):
            review = "yes"
            review_priority = "high"
            review_reason = append_reason(review_reason, f"No obvious control found for {mutant} {condition}".strip())

        sub.at[idx, "curation_confidence"] = confidence
        sub.at[idx, "needs_human_review"] = review
        sub.at[idx, "review_priority"] = review_priority
        sub.at[idx, "review_reason"] = review_reason

    return sub


def append_reason(existing, new):
    existing = clean(existing)
    new = clean(new)
    if not existing:
        return new
    if new in existing:
        return existing
    return existing + "; " + new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--sheet", default="Sheet")
    parser.add_argument("--assign-controls", action="store_true")
    args = parser.parse_args()

    pmid = clean(args.pmid)

    print(f"\n=== Populating master copy from BioSample metadata for PMID {pmid} ===")

    biosample_file = CACHE / f"PMID_{pmid}_biosample_attributes.tsv"
    if not biosample_file.exists():
        raise FileNotFoundError(f"Missing BioSample cache: {biosample_file}. Run script 03 first.")

    all_sheets = pd.read_excel(MASTER, sheet_name=None, dtype=str)
    master = all_sheets[args.sheet].fillna("")
    master.columns = [str(c).strip() for c in master.columns]

    bio = pd.read_csv(biosample_file, sep="\t", dtype=str).fillna("")

    pmid_col = find_col(master, ["PMID", "PubMed ID", "pubmed_id"])
    biosample_col = find_col(master, ["BioSample", "BioSample ID", "biosample"])

    if pmid_col is None:
        raise ValueError("Could not find PMID column.")
    if biosample_col is None:
        raise ValueError("Could not find BioSample column.")

    for col in [
        "Cell_Cycle_Stage", "Life_Stage", "Target", "Strain", "Substrain",
        "Mutant", "Condition1", "Condition2", "Condition3",
        "background_or_control_1", "background_or_control_2",
        "Notes", "replicate_number", "assigned_control1", "assigned_control2",
        *EXTRA_COLUMNS,
    ]:
        ensure_col(master, col)

    master["_pmid_norm"] = master[pmid_col].map(clean)
    master["_biosample_norm"] = master[biosample_col].map(clean)

    bio["_biosample_norm"] = bio["BioSample"].map(clean)

    bio_lookup = {
        row["_biosample_norm"]: row
        for _, row in bio.iterrows()
        if clean(row.get("_biosample_norm", ""))
    }

    mask = master["_pmid_norm"] == pmid
    target_indices = master.index[mask].tolist()

    populated = 0
    missing_bio = 0

    for idx in target_indices:
        bs = clean(master.at[idx, "_biosample_norm"])
        brow = bio_lookup.get(bs)

        if brow is None or clean(brow.get("fetch_status", "")) != "ok":
            missing_bio += 1
            master.at[idx, "needs_human_review"] = "yes"
            master.at[idx, "review_priority"] = "high"
            master.at[idx, "review_reason"] = append_reason(
                master.at[idx, "review_reason"],
                "BioSample metadata unavailable"
            )
            continue

        title = get_first(brow, ["biosample_title"])
        source_name = get_first(brow, ["biosample_attr__source_name"])
        stage_raw = get_first(brow, [
            "biosample_attr__development_stage",
            "biosample_attr__developmental_stage",
            "biosample_attr__dev_stage",
            "biosample_attr__Stage",
            "biosample_attr__stage",
        ])
        strain_raw = get_first(brow, ["biosample_attr__strain"])
        genotype_raw = get_first(brow, ["biosample_attr__genotype", "biosample_attr__mutant"])
        condition_raw = get_first(brow, [
            "biosample_attr__condition",
            "biosample_attr__Condition",
            "biosample_attr__treatment",
            "biosample_attr__Treatment",
        ])

        stage = normalize_stage(stage_raw)
        strain = normalize_strain(strain_raw, source_name, title)
        substrain = infer_substrain(source_name, genotype_raw, title)
        parsed = parse_genotype(genotype_raw, source_name, title)

        # If BioSample has an explicit condition field, use it unless genotype parsing
        # already found a more specific perturbation condition.
        if condition_raw and not parsed["Condition1"]:
            parsed["Condition1"] = normalize_condition(condition_raw)

        replicate = infer_replicate(title, source_name)

        master.at[idx, "Cell_Cycle_Stage"] = stage
        master.at[idx, "Life_Stage"] = "asexual blood stage" if stage in {"Ring", "Trophozoite", "Schizont"} else ""
        master.at[idx, "Target"] = parsed["Target"]
        master.at[idx, "Strain"] = strain
        master.at[idx, "Substrain"] = substrain
        master.at[idx, "Mutant"] = parsed["Mutant"]
        master.at[idx, "Condition1"] = parsed["Condition1"]
        master.at[idx, "Condition2"] = parsed["Condition2"]
        master.at[idx, "Condition3"] = parsed["Condition3"]
        master.at[idx, "replicate_number"] = replicate

        # Keep raw BioSample source text in Notes for traceability without overwriting paper-level note later.
        master.at[idx, "Notes"] = source_name

        master.at[idx, "curation_source"] = "BioSample metadata"
        master.at[idx, "curation_confidence"] = parsed["parse_confidence"]
        master.at[idx, "curation_evidence"] = (
            f"BioSample={bs}; title={title}; source_name={source_name}; "
            f"development_stage={stage_raw}; strain={strain_raw}; genotype={genotype_raw}; condition={condition_raw}"
        )

        needs_review = "no"
        review_priority = "low"
        review_reason = ""

        if parsed["parse_confidence"] != "high":
            needs_review = "yes"
            review_priority = "medium"
            review_reason = append_reason(review_reason, parsed["parse_note"])

        required_fields = [
            ("Cell_Cycle_Stage", stage),
            ("Strain", strain),
        ]

        # Mutant is required only for genotype/perturbation-style rows.
        # For condition-only studies, Mutant can be blank and Condition1 carries the biology.
        if genotype_raw and not parsed["Mutant"]:
            required_fields.append(("Mutant", parsed["Mutant"]))

        for field_name, field_value in required_fields:
            if not clean(field_value):
                needs_review = "yes"
                review_priority = "high"
                review_reason = append_reason(review_reason, f"Missing {field_name}")

        if not genotype_raw and parsed["Condition1"]:
            master.at[idx, "curation_note"] = "No genotype/mutant BioSample field; condition-based row"
            if needs_review != "yes":
                review_priority = "low"

        master.at[idx, "needs_human_review"] = needs_review
        master.at[idx, "review_priority"] = review_priority
        master.at[idx, "review_reason"] = review_reason

        populated += 1

    # Assign controls only within target PMID rows, if requested.
    if args.assign_controls:
        sub = master.loc[target_indices].copy()
        sub = assign_controls_for_subset(sub)
        for col in sub.columns:
            master.loc[target_indices, col] = sub[col]

    # Remove helper columns before writing
    master = master.drop(columns=["_pmid_norm", "_biosample_norm"], errors="ignore")
    all_sheets[args.sheet] = master

    out_xlsx = OUT / f"rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_{pmid}.xlsx"
    out_subset = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        for sheet_name, df in all_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

    # Save subset only for inspection
    filled_subset = master[master[pmid_col].map(clean) == pmid].copy()
    filled_subset.to_csv(out_subset, sep="\t", index=False)

    print("\nSummary:")
    print(f"Rows for PMID: {len(target_indices)}")
    print(f"Rows populated from BioSample: {populated}")
    print(f"Rows missing BioSample metadata: {missing_bio}")

    print("\nReview counts:")
    print(filled_subset["needs_human_review"].value_counts(dropna=False).to_string())

    print("\nConfidence counts:")
    print(filled_subset["curation_confidence"].value_counts(dropna=False).to_string())

    print("\nWrote:")
    print(out_xlsx)
    print(out_subset)
    print("\nOpen with:")
    print(f"open {out_xlsx}")


if __name__ == "__main__":
    main()
