#!/usr/bin/env python3
"""
Clean AI study summaries by separating curator-relevant warnings from technical/chunking warnings.

Input:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries.tsv

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES_CLEAN.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


DEEP_QC = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")
INFILE = DEEP_QC / "ai_study_summaries.tsv"
OUT_TSV = DEEP_QC / "ai_study_summaries_clean.tsv"
OUT_MD = DEEP_QC / "AI_STUDY_SUMMARIES_CLEAN.md"


TECH_PATTERNS = [
    r"\bchunk\b",
    r"\bchunks\b",
    r"generated in \d+ rowwise chunks",
    r"n_deterministic_fallback",
    r"n_duplicate_ai_rowwise",
    r"n_invalid_ai_rowwise",
    r"source_row_id",
    r"prompt evidence",
    r"prompt chunk",
    r"provided excerpt",
    r"rowwise evidence table is the source of truth",
    r"sample_map",
    r"deterministically completed",
    r"deterministic",
    r"validation",
    r"partitioned exactly once",
    r"assigned exactly once",
    r"full packet",
    r"visible samples",
    r"zero-row classes",
    r"Run-to-source_row_id",
]

CURATOR_IMPORTANT_PATTERNS = [
    r"do not relabel",
    r"do not infer",
    r"not a perturbation",
    r"not experimental treatments",
    r"reference genome",
    r"biological strain",
    r"strain",
    r"stage",
    r"control",
    r"comparator",
    r"DEG",
    r"ChIP",
    r"RNA",
    r"curator",
    r"verify",
    r"confirmation",
    r"inconsistent",
    r"typo",
    r"naming variant",
    r"mapped to",
    r"field isolate",
    r"natural isolate",
]


def clean(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def split_warning_text(text: str) -> list[str]:
    text = clean(text)
    if not text:
        return []
    # Current extractor joined warnings with " | ".
    parts = [p.strip() for p in text.split(" | ") if p.strip()]
    return parts


def matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def classify_warning(w: str) -> str:
    """
    Classify warning into:
      curator_warning: biologically meaningful for curator
      technical_warning: chunking/fallback/pipeline mechanics
      mixed_warning: contains both curator and technical signals
    """
    is_tech = matches_any(TECH_PATTERNS, w)
    is_curator = matches_any(CURATOR_IMPORTANT_PATTERNS, w)

    if is_tech and is_curator:
        return "mixed_warning"
    if is_tech:
        return "technical_warning"
    return "curator_warning"


def main():
    if not INFILE.exists():
        raise FileNotFoundError(f"Missing {INFILE}. Run scripts/47_extract_ai_study_summaries.py first.")

    df = pd.read_csv(INFILE, sep="\t", dtype=str).fillna("")

    rows = []
    for _, row in df.iterrows():
        warnings = split_warning_text(row.get("global_warnings", ""))

        curator = []
        technical = []
        mixed = []

        for w in warnings:
            cls = classify_warning(w)
            if cls == "curator_warning":
                curator.append(w)
            elif cls == "technical_warning":
                technical.append(w)
            else:
                mixed.append(w)

        # Mixed warnings are kept in curator-facing notes, but also counted as technical/mixed.
        curator_display = curator + mixed

        new = row.to_dict()
        new["curator_warnings_clean"] = " | ".join(curator_display)
        new["technical_warnings_clean"] = " | ".join(technical)
        new["mixed_warnings_clean"] = " | ".join(mixed)
        new["n_curator_warnings_clean"] = len(curator_display)
        new["n_technical_warnings_clean"] = len(technical)
        new["n_mixed_warnings_clean"] = len(mixed)
        rows.append(new)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_TSV, sep="\t", index=False)

    md = []
    md.append("# AI Study Summaries, Cleaned")
    md.append("")
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append(f"Packets summarized: {len(out)}")
    md.append("")
    md.append("Technical/chunking warnings are separated from curator-facing biological warnings.")
    md.append("")

    for _, r in out.sort_values(["pmid", "bioproject"]).iterrows():
        md.append(f"## {r.get('packet_id', '')}")
        md.append("")
        md.append(f"- PMID: {r.get('pmid', '')}")
        md.append(f"- BioProject: {r.get('bioproject', '')}")
        md.append(f"- Assay class: {r.get('assay_class_confirmed', '')}")
        md.append(f"- Assays: {r.get('assay_types', '')}")
        md.append(f"- Organism/strain: {r.get('organism_strain', '')}")
        md.append(f"- Summary: {r.get('one_sentence_summary', '')}")
        md.append(f"- Study goal: {r.get('study_goal', '')}")
        md.append(f"- Main axes: {r.get('main_comparisons_or_sample_axes', '')}")

        cur = clean(r.get("curator_warnings_clean", ""))
        tech = clean(r.get("technical_warnings_clean", ""))

        if cur:
            md.append(f"- Curator warnings: {cur}")
        else:
            md.append("- Curator warnings: none")

        if tech:
            md.append(f"- Technical warnings: {tech}")
        else:
            md.append("- Technical warnings: none")

        md.append("")

    OUT_MD.write_text("\n".join(md))

    print("Wrote:", OUT_TSV)
    print("Wrote:", OUT_MD)
    print()
    print("Warning counts:")
    cols = [
        "packet_id",
        "n_curator_warnings_clean",
        "n_technical_warnings_clean",
        "n_mixed_warnings_clean",
    ]
    print(out[cols].to_string(index=False))


if __name__ == "__main__":
    main()
