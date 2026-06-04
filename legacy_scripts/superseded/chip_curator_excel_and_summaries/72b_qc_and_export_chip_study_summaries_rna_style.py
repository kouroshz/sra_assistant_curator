#!/usr/bin/env python3
"""
QC and export ChIP study summaries in RNA-style format.

This fixes the previous ChIP markdown problem:
- removes always-empty sections like "Main findings: Not specified"
- writes compact one-packet-per-block summaries like RNA
- writes a QC report showing missing/non-informative fields
- keeps TSV for Shrey/app use

No API required.
"""

from pathlib import Path
from datetime import datetime
from collections import Counter
import json
import pandas as pd

ACTIVE = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_active_validated_outputs.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/23_study_summaries")
OUT.mkdir(parents=True, exist_ok=True)


def clean(x):
    if x is None:
        return ""
    if isinstance(x, list):
        return " | ".join(clean(v) for v in x if clean(v))
    if isinstance(x, dict):
        return " | ".join(f"{k}: {clean(v)}" for k, v in x.items() if clean(v))
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    if s.lower() in {"nan", "none", "<na>", "null"}:
        return ""
    return s


def get_any(d, aliases):
    if not isinstance(d, dict):
        return ""
    for a in aliases:
        v = clean(d.get(a, ""))
        if v:
            return v
    return ""


def read_json(path):
    return json.loads(Path(path).read_text())


def compact_list(x):
    if isinstance(x, list):
        return " | ".join(clean(v) for v in x if clean(v))
    return clean(x)


def extract_row(inv_row):
    ai_json = Path(clean(inv_row.get("active_ai_json", "")))
    obj = read_json(ai_json)

    ss = obj.get("study_summary", {})
    if not isinstance(ss, dict):
        ss = {}

    ar = obj.get("analysis_readiness", {})
    if not isinstance(ar, dict):
        ar = {}

    summary = get_any(ss, [
        "summary",
        "one_sentence_summary",
        "concise_summary",
        "paper_summary",
        "study_summary",
    ])

    goal = get_any(ss, [
        "study_goal",
        "goal",
        "biological_question",
        "main_question",
        "paper_goal",
    ])

    organism = get_any(ss, [
        "organism_strain",
        "organism_or_strain",
        "organism",
        "strain",
        "parasite_strain",
    ])

    axes = get_any(ss, [
        "main_comparisons_or_sample_axes",
        "main_comparisons",
        "sample_axes",
        "experimental_axes",
        "comparison_axes",
    ])

    evidence = get_any(ss, [
        "paper_evidence_locations",
        "evidence_locations",
        "relevant_figures_methods",
        "figures_methods",
        "where_in_paper",
    ])

    curator_warnings = (
        get_any(ss, ["curator_warnings", "curator_warnings_clean", "warnings_for_curator"])
        or compact_list(obj.get("global_warnings", []))
    )

    technical_warnings = (
        get_any(ss, ["technical_warnings", "technical_warnings_clean"])
        or compact_list(ar.get("main_blockers", []))
    )

    # Optional fields: preserve in TSV/QC, but do not print if empty.
    main_findings = get_any(ss, ["main_findings", "key_findings", "major_findings"])
    data_types = get_any(ss, ["data_types_in_paper", "data_types", "assays", "sequencing_assays"])
    chip_relevance = get_any(ss, ["chip_specific_relevance", "chip_relevance", "assay_relevance"])
    sample_notes = get_any(ss, ["sample_interpretation_notes", "sample_notes", "metadata_interpretation_notes"])

    if not summary:
        targets = clean(inv_row.get("targets", ""))
        n_rows = clean(inv_row.get("n_rows", ""))
        readiness = clean(inv_row.get("chip_peak_calling_ready", ""))
        summary = f"ChIP-like target-enrichment packet with {n_rows} rows"
        if targets:
            summary += f" for targets {targets}"
        summary += f"; peak-calling readiness={readiness}."

    return {
        "packet_id": clean(inv_row.get("packet_id", "")),
        "pmid": clean(inv_row.get("pmid", obj.get("pmid", ""))),
        "bioproject": clean(inv_row.get("bioproject", obj.get("bioproject", ""))),
        "assay_class": clean(obj.get("assay_class_confirmed", "chip_like_target_enrichment")),
        "targets": clean(inv_row.get("targets", "")),
        "chip_peak_calling_ready": clean(inv_row.get("chip_peak_calling_ready", "")),
        "organism_strain": organism,
        "summary": summary,
        "study_goal": goal,
        "main_axes": axes,
        "paper_evidence_locations": evidence,
        "curator_warnings": curator_warnings,
        "technical_warnings": technical_warnings,
        "main_findings_optional": main_findings,
        "data_types_optional": data_types,
        "chip_relevance_optional": chip_relevance,
        "sample_notes_optional": sample_notes,
        "active_ai_json": str(ai_json),
    }


def write_rna_style_markdown(df, path):
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

        # Only print optional fields if actually useful.
        if clean(r.get("main_findings_optional", "")):
            lines.append(f"- Main findings: {clean(r['main_findings_optional'])}")
        if clean(r.get("data_types_optional", "")):
            lines.append(f"- Data types: {clean(r['data_types_optional'])}")
        if clean(r.get("chip_relevance_optional", "")):
            lines.append(f"- ChIP relevance: {clean(r['chip_relevance_optional'])}")
        if clean(r.get("sample_notes_optional", "")):
            lines.append(f"- Sample/metadata notes: {clean(r['sample_notes_optional'])}")

        lines.append(f"- Curator warnings: {clean(r['curator_warnings']) or 'none'}")
        lines.append(f"- Technical warnings: {clean(r['technical_warnings']) or 'none'}")
        lines.append("")

    path.write_text("\n".join(lines))


def write_qc(df, path):
    fields = [
        "summary",
        "study_goal",
        "organism_strain",
        "main_axes",
        "paper_evidence_locations",
        "curator_warnings",
        "technical_warnings",
        "main_findings_optional",
        "data_types_optional",
        "chip_relevance_optional",
        "sample_notes_optional",
    ]

    lines = []
    lines.append("# ChIP Study Summary QC")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Packets checked: {len(df)}")
    lines.append("")
    lines.append("## Field completeness")
    lines.append("")

    for f in fields:
        n_present = int((df[f].map(clean) != "").sum()) if f in df.columns else 0
        lines.append(f"- {f}: {n_present}/{len(df)} present")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- The ChIP summaries are now exported in RNA-style compact per-packet blocks.")
    lines.append("- Empty optional fields are not printed in the Markdown handoff file.")
    lines.append("- Missing optional fields are preserved in the TSV/QC report but should not clutter curator-facing Markdown.")
    lines.append("- This file is intended to save curator time by providing paper-level context before rowwise review.")
    lines.append("")

    path.write_text("\n".join(lines))


def main():
    active = pd.read_csv(ACTIVE, sep="\t", dtype=str).fillna("")

    rows = [extract_row(r) for _, r in active.iterrows()]
    df = pd.DataFrame(rows)

    df = df.sort_values(["pmid", "bioproject", "packet_id"])

    tsv = OUT / "chip_ai_study_summaries_clean.tsv"
    md = OUT / "CHIP_AI_STUDY_SUMMARIES_CLEAN.md"
    qc = OUT / "CHIP_AI_STUDY_SUMMARIES_QC.md"

    df.to_csv(tsv, sep="\t", index=False)
    write_rna_style_markdown(df, md)
    write_qc(df, qc)

    print("Wrote:", tsv)
    print("Wrote:", md)
    print("Wrote:", qc)
    print()
    print(f"Packets summarized: {len(df)}")
    print()
    print(Path(qc).read_text())


if __name__ == "__main__":
    main()
