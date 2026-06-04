#!/usr/bin/env python3
"""
Final QC cleanup for ChIP AI study summaries.

Fixes:
- Removes chunk-level language from curator-facing summaries.
- Moves pipeline/repair/audit language out of curator warnings.
- Gives the large AP2 merged packet a clean parent-level warning.
- Rewrites CHIP_AI_STUDY_SUMMARIES_CLEAN.md in final RNA-style format.
"""

from pathlib import Path
from datetime import datetime
import pandas as pd

OUT = Path("outputs/06_CHIP_AI_ASSIST/23_study_summaries")
TSV = OUT / "chip_ai_study_summaries_clean.tsv"
MD = OUT / "CHIP_AI_STUDY_SUMMARIES_CLEAN.md"
QC = OUT / "CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md"

AP2_PARENT = "PMID_35288749__BIOPROJECT_PRJNA765872"


def clean(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "<na>", "null"}:
        return ""
    return s


def split_items(x):
    x = clean(x)
    if not x:
        return []
    return [p.strip() for p in x.split("|") if p.strip()]


def join_items(items):
    out = []
    seen = set()
    for item in items:
        item = clean(item)
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            out.append(item)
            seen.add(key)
    return " | ".join(out)


def is_pipeline_artifact(item):
    s = item.lower()
    bad_phrases = [
        "sample_map was deterministically rebuilt",
        "validation found duplicate",
        "rowwise_suggestions were complete",
        "this json was merged",
        "sample_map was intentionally cleared",
        "must be rebuilt deterministically",
        "chunk-level",
        "merged from chunk",
    ]
    return any(p in s for p in bad_phrases)


def clean_curator_warnings(row):
    packet_id = clean(row.get("packet_id", ""))
    items = split_items(row.get("curator_warnings", ""))

    # Drop pipeline/audit artifacts from curator-facing warnings.
    items = [x for x in items if not is_pipeline_artifact(x)]

    # For the large AP2 merged parent, remove chunk-specific phrasing and replace
    # with clean parent-level warnings.
    if packet_id == AP2_PARENT:
        items = [
            x for x in items
            if "this chunk" not in x.lower()
            and "30-row chunk" not in x.lower()
            and "27 runs" not in x.lower()
        ]

        parent_items = [
            "Large ApiAP2 ChIP-seq parent packet generated from target-centered chunked AI outputs and merged back to the full BioProject-level packet.",
            "Curators should review target-control/input relationships carefully because inputs are reused as shared backgrounds across multiple ApiAP2 target IPs.",
            "The paper includes RNA-seq/knockout analyses, but this manifest is the ChIP-like target-enrichment subset only.",
            "IgG/mock/untagged controls mentioned in the paper are not represented as sequencing rows in this manifest; available controls are primarily input/background rows.",
            "AP2-O2/AP2-exp-related ring-stage ambiguity was preserved for curator review rather than forced into a final label.",
        ]

        items = parent_items + items

    return join_items(items)


def clean_technical_warnings(row):
    packet_id = clean(row.get("packet_id", ""))
    cur_items = split_items(row.get("curator_warnings", ""))
    tech_items = split_items(row.get("technical_warnings", ""))

    # Move pipeline/audit artifacts to technical warnings if they are present.
    moved = [x for x in cur_items if is_pipeline_artifact(x)]

    if packet_id == AP2_PARENT:
        moved.append(
            "Large AP2 packet was processed by target-centered chunking and merged; final parent-level rowwise coverage was structurally validated before workbook export."
        )

    items = tech_items + moved
    if not items:
        return "none"
    return join_items(items)


def write_markdown(df):
    lines = []
    lines.append("# ChIP AI Study Summaries, Cleaned")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"PASS packets summarized: {len(df)}")
    lines.append("")
    lines.append("These are AI-generated whole-paper/study summaries extracted directly from validated ChIP AI JSON outputs.")
    lines.append("They are curator aids only; curator corrections/comments are authoritative.")
    lines.append("")
    lines.append("## Per-packet summaries")
    lines.append("")

    for _, r in df.iterrows():
        lines.append(f"## {clean(r['packet_id'])}")
        lines.append("")
        lines.append(f"- PMID: {clean(r['pmid'])}")
        lines.append(f"- BioProject: {clean(r['bioproject'])}")
        lines.append(f"- Assay class: {clean(r['assay_class'])}")
        lines.append(f"- Peak-calling readiness: {clean(r['chip_peak_calling_ready'])}")
        lines.append(f"- Targets: {clean(r['targets'])}")
        lines.append(f"- Organism/strain: {clean(r['organism_strain'])}")
        lines.append(f"- Summary: {clean(r['summary'])}")
        lines.append(f"- Study goal: {clean(r['study_goal'])}")
        lines.append(f"- Main axes: {clean(r['main_axes'])}")
        lines.append(f"- Paper evidence locations: {clean(r['paper_evidence_locations'])}")
        lines.append(f"- Curator warnings: {clean(r['curator_warnings']) or 'none'}")
        lines.append(f"- Technical warnings: {clean(r['technical_warnings']) or 'none'}")
        lines.append("")

    MD.write_text("\n".join(lines))


def main():
    if not TSV.exists():
        raise SystemExit(f"Missing TSV: {TSV}")

    df = pd.read_csv(TSV, sep="\t", dtype=str).fillna("")

    # Clean warnings.
    df["curator_warnings"] = df.apply(clean_curator_warnings, axis=1)
    df["technical_warnings"] = df.apply(clean_technical_warnings, axis=1)

    # Write cleaned TSV and MD.
    df.to_csv(TSV, sep="\t", index=False)
    write_markdown(df)

    # QC counts.
    md_text = MD.read_text()
    n_chunk = md_text.lower().count("this chunk")
    n_pipeline_curator = sum(
        is_pipeline_artifact(x)
        for vals in df["curator_warnings"].map(split_items)
        for x in vals
    )
    n_pipeline_technical = sum(
        is_pipeline_artifact(x)
        for vals in df["technical_warnings"].map(split_items)
        for x in vals
    )

    qc = []
    qc.append("# Final ChIP Study Summary QC")
    qc.append("")
    qc.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    qc.append("")
    qc.append(f"- packets: {len(df)}")
    qc.append(f"- occurrences of 'this chunk' in final MD: {n_chunk}")
    qc.append(f"- pipeline/audit artifacts remaining in curator warnings: {n_pipeline_curator}")
    qc.append(f"- pipeline/audit artifacts retained in technical warnings: {n_pipeline_technical}")
    qc.append("")
    qc.append("## Interpretation")
    qc.append("")
    if n_chunk == 0 and n_pipeline_curator == 0:
        qc.append("PASS: final study-summary markdown is curator-facing.")
    else:
        qc.append("REVIEW: remaining chunk/pipeline language should be checked before handoff.")

    QC.write_text("\n".join(qc))

    print("Wrote:", TSV)
    print("Wrote:", MD)
    print("Wrote:", QC)
    print()
    print(QC.read_text())


if __name__ == "__main__":
    main()
