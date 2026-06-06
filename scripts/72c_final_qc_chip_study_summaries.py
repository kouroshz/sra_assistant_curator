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
SHARE_TSV = Path("outputs/06_CHIP_AI_ASSIST/22_curator_share_files/ChIP_Paper_Summaries.tsv")

AP2_PARENT = "PMID_35288749__BIOPROJECT_PRJNA765872"

NORMALIZED_COLUMNS = [
    "packet_id",
    "pmid",
    "bioproject",
    "assay_class",
    "chip_peak_calling_ready",
    "targets",
    "organism_strain",
    "summary",
    "study_goal",
    "main_axes",
    "paper_evidence_locations",
    "curator_warnings",
    "technical_warnings",
    "active_ai_json",
]


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


def summary_heading(row):
    packet_id = clean(row.get("packet_id", ""))
    pmid = clean(row.get("pmid", ""))
    if packet_id.startswith("PMID_"):
        return packet_id
    if pmid:
        suffix = packet_id or "CHIP_PACKET"
        return f"PMID_{pmid}__{suffix}"
    return packet_id or "UNKNOWN_CHIP_PACKET"


def first_present(row, names, default=""):
    for name in names:
        value = clean(row.get(name, ""))
        if value:
            return value
    return default


def normalize_rows(src):
    rows = []
    for _, r in src.iterrows():
        rows.append({
            "packet_id": first_present(r, ["packet_id", "packet", "study_id"]),
            "pmid": first_present(r, ["pmid", "PMID"]),
            "bioproject": first_present(r, ["bioproject", "BioProject", "bio_project"]),
            "assay_class": first_present(r, ["assay_class"], "ChIP-like target enrichment"),
            "chip_peak_calling_ready": first_present(r, ["chip_peak_calling_ready", "peak_calling_ready"]),
            "targets": first_present(r, ["targets", "target", "factor_tags"]),
            "organism_strain": first_present(r, ["organism_strain", "strain", "organism"]),
            "summary": first_present(r, ["summary", "one_sentence_summary", "curator_summary"]),
            "study_goal": first_present(r, ["study_goal"]),
            "main_axes": first_present(r, ["main_axes", "main_comparisons_or_sample_axes"]),
            "paper_evidence_locations": first_present(r, ["paper_evidence_locations", "evidence_from_paper"]),
            "curator_warnings": first_present(r, ["curator_warnings", "curator_warnings_clean", "warnings"]),
            "technical_warnings": first_present(r, ["technical_warnings", "technical_warnings_clean"]),
            "active_ai_json": first_present(r, ["active_ai_json"]),
        })
    return pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)


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


def ensure_input_tsv():
    OUT.mkdir(parents=True, exist_ok=True)
    if TSV.exists():
        src_path = TSV
    elif SHARE_TSV.exists():
        src_path = SHARE_TSV
    else:
        raise SystemExit(
            f"Missing TSV: {TSV}. Also missing Step 42 export: {SHARE_TSV}. "
            "Run chip-finalize through Step 42 before Step 43."
        )

    src = pd.read_csv(src_path, sep="\t", dtype=str).fillna("")
    normalized = normalize_rows(src)
    normalized.to_csv(TSV, sep="\t", index=False)
    if src_path == SHARE_TSV:
        print(f"Created Step 43 input from Step 42 export: {TSV}")
    else:
        print(f"Normalized Step 43 input: {TSV}")


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
        lines.append(f"## {summary_heading(r)}")
        lines.append("")
        lines.append(f"- PMID: {clean(r.get('pmid', ''))}")
        lines.append(f"- BioProject: {clean(r.get('bioproject', ''))}")
        lines.append(f"- Assay class: {clean(r.get('assay_class', '')) or 'unknown'}")
        lines.append(f"- Peak-calling readiness: {clean(r.get('chip_peak_calling_ready', ''))}")
        lines.append(f"- Targets: {clean(r.get('targets', ''))}")
        lines.append(f"- Organism/strain: {clean(r.get('organism_strain', ''))}")
        lines.append(f"- Summary: {clean(r.get('summary', ''))}")
        lines.append(f"- Study goal: {clean(r.get('study_goal', ''))}")
        lines.append(f"- Main axes: {clean(r.get('main_axes', ''))}")
        lines.append(f"- Paper evidence locations: {clean(r.get('paper_evidence_locations', ''))}")
        lines.append(f"- Curator warnings: {clean(r.get('curator_warnings', '')) or 'none'}")
        lines.append(f"- Technical warnings: {clean(r.get('technical_warnings', '')) or 'none'}")
        lines.append("")

    MD.write_text("\n".join(lines))


def main():
    ensure_input_tsv()

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
