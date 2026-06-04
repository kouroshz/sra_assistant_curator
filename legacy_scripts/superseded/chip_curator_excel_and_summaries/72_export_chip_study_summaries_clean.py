#!/usr/bin/env python3
"""
Export ChIP whole-paper AI study summaries, RNA-style.

This reads the active validated ChIP AI JSONs directly and extracts the
`study_summary` dict from each JSON.

Outputs:
  outputs/06_CHIP_AI_ASSIST/23_study_summaries/
    CHIP_AI_STUDY_SUMMARIES_CLEAN.md
    chip_ai_study_summaries_clean.tsv
    CHIP_STUDY_SUMMARY_KEY_INVENTORY.tsv

No API required.
"""

from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
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


def first_nonblank(*vals):
    for v in vals:
        v = clean(v)
        if v:
            return v
    return ""


def get_any(d, aliases):
    if not isinstance(d, dict):
        return ""
    for a in aliases:
        if a in d and clean(d[a]):
            return clean(d[a])
    return ""


def safe_json(x):
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except Exception:
        return clean(x)


def read_json(path):
    return json.loads(Path(path).read_text())


def compact_warning_list(x):
    if isinstance(x, list):
        return " | ".join(clean(v) for v in x if clean(v))
    return clean(x)


def extract_summary_row(inv_row):
    packet_id = clean(inv_row.get("packet_id", ""))
    ai_json = Path(clean(inv_row.get("active_ai_json", "")))

    obj = read_json(ai_json)
    ss = obj.get("study_summary", {})
    if not isinstance(ss, dict):
        ss = {}

    ar = obj.get("analysis_readiness", {})
    if not isinstance(ar, dict):
        ar = {}

    # Flexible aliases because ChIP/RNA prompt versions may name fields slightly differently.
    one_sentence = get_any(ss, [
        "one_sentence_summary",
        "summary",
        "concise_summary",
        "paper_summary",
        "study_summary",
    ])

    study_goal = get_any(ss, [
        "study_goal",
        "goal",
        "biological_question",
        "main_question",
        "paper_goal",
    ])

    organism_strain = get_any(ss, [
        "organism_strain",
        "organism_or_strain",
        "organism",
        "strain",
        "parasite_strain",
    ])

    main_findings = get_any(ss, [
        "main_findings",
        "key_findings",
        "major_findings",
        "paper_main_findings",
        "biological_findings",
    ])

    main_axes = get_any(ss, [
        "main_comparisons_or_sample_axes",
        "main_comparisons",
        "sample_axes",
        "experimental_axes",
        "comparison_axes",
    ])

    data_types = get_any(ss, [
        "data_types_in_paper",
        "data_types",
        "assays",
        "experimental_assays",
        "sequencing_assays",
    ])

    chip_relevance = get_any(ss, [
        "chip_relevance",
        "chip_specific_relevance",
        "chIP_specific_relevance",
        "target_enrichment_relevance",
        "assay_relevance",
    ])

    evidence_locations = get_any(ss, [
        "paper_evidence_locations",
        "evidence_locations",
        "relevant_figures_methods",
        "figures_methods",
        "where_in_paper",
    ])

    sample_notes = get_any(ss, [
        "sample_interpretation_notes",
        "sample_notes",
        "metadata_interpretation_notes",
        "curation_notes",
    ])

    curator_warnings = first_nonblank(
        get_any(ss, ["curator_warnings", "curator_warnings_clean", "warnings_for_curator"]),
        compact_warning_list(obj.get("global_warnings", [])),
    )

    technical_warnings = first_nonblank(
        get_any(ss, ["technical_warnings", "technical_warnings_clean"]),
        compact_warning_list(ar.get("main_blockers", [])),
    )

    # Fallbacks for older JSONs.
    if not one_sentence:
        targets = clean(inv_row.get("targets", ""))
        n_rows = clean(inv_row.get("n_rows", ""))
        peak = clean(inv_row.get("chip_peak_calling_ready", ""))
        one_sentence = (
            f"ChIP-like target-enrichment packet with {n_rows} rows"
            + (f" for targets {targets}" if targets else "")
            + f"; peak-calling readiness={peak}."
        )

    row = {
        "packet_id": packet_id,
        "pmid": clean(inv_row.get("pmid", obj.get("pmid", ""))),
        "bioproject": clean(inv_row.get("bioproject", obj.get("bioproject", ""))),
        "assay_class_confirmed": clean(obj.get("assay_class_confirmed", "")),
        "chip_peak_calling_ready": clean(inv_row.get("chip_peak_calling_ready", "")),
        "n_rows": clean(inv_row.get("n_rows", "")),
        "targets": clean(inv_row.get("targets", "")),
        "target_types": clean(inv_row.get("target_types", "")),
        "one_sentence_summary": one_sentence,
        "study_goal": study_goal,
        "organism_strain": organism_strain,
        "main_findings": main_findings,
        "main_comparisons_or_sample_axes": main_axes,
        "data_types_in_paper": data_types,
        "chip_specific_relevance": chip_relevance,
        "paper_evidence_locations": evidence_locations,
        "sample_interpretation_notes": sample_notes,
        "curator_warnings_clean": curator_warnings,
        "technical_warnings_clean": technical_warnings,
        "active_ai_json": str(ai_json),
        "study_summary_json": safe_json(ss),
    }

    # Also preserve every study_summary key as a column.
    for k, v in ss.items():
        col = f"study_summary__{k}"
        row[col] = clean(v)

    return row, list(ss.keys())


def write_markdown(df, path):
    lines = []
    lines.append("# ChIP AI Study Summaries, Cleaned")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Packets summarized: {len(df)}")
    lines.append("")
    lines.append("These are AI-generated whole-paper/study summaries extracted directly from each validated ChIP AI JSON `study_summary` field.")
    lines.append("AI summaries are curator aids only; curator corrections/comments are authoritative.")
    lines.append("")

    for _, r in df.iterrows():
        packet_id = clean(r.get("packet_id", ""))
        lines.append(f"## {packet_id}")
        lines.append("")
        lines.append(f"- PMID: {clean(r.get('pmid', ''))}")
        lines.append(f"- BioProject: {clean(r.get('bioproject', ''))}")
        lines.append(f"- Assay class: {clean(r.get('assay_class_confirmed', ''))}")
        lines.append(f"- Peak-calling readiness: {clean(r.get('chip_peak_calling_ready', ''))}")
        lines.append(f"- Targets: {clean(r.get('targets', ''))}")
        lines.append("")
        lines.append("### Whole-paper summary")
        lines.append("")
        lines.append(clean(r.get("one_sentence_summary", "")) or "No summary provided.")
        lines.append("")
        lines.append("### Study goal")
        lines.append("")
        lines.append(clean(r.get("study_goal", "")) or "No study goal provided.")
        lines.append("")
        lines.append("### Organism / strain")
        lines.append("")
        lines.append(clean(r.get("organism_strain", "")) or "Not specified.")
        lines.append("")
        lines.append("### Main findings")
        lines.append("")
        lines.append(clean(r.get("main_findings", "")) or "Not specified.")
        lines.append("")
        lines.append("### Main comparisons / sample axes")
        lines.append("")
        lines.append(clean(r.get("main_comparisons_or_sample_axes", "")) or "Not specified.")
        lines.append("")
        lines.append("### Data types in the paper")
        lines.append("")
        lines.append(clean(r.get("data_types_in_paper", "")) or "Not specified.")
        lines.append("")
        lines.append("### ChIP-specific relevance")
        lines.append("")
        lines.append(clean(r.get("chip_specific_relevance", "")) or "Not specified.")
        lines.append("")
        lines.append("### Paper evidence locations")
        lines.append("")
        lines.append(clean(r.get("paper_evidence_locations", "")) or "Not specified.")
        lines.append("")
        lines.append("### Sample / metadata interpretation notes")
        lines.append("")
        lines.append(clean(r.get("sample_interpretation_notes", "")) or "None.")
        lines.append("")
        lines.append("### Curator warnings")
        lines.append("")
        lines.append(clean(r.get("curator_warnings_clean", "")) or "None.")
        lines.append("")
        lines.append("### Technical warnings")
        lines.append("")
        lines.append(clean(r.get("technical_warnings_clean", "")) or "None.")
        lines.append("")

    path.write_text("\n".join(lines))


def main():
    active = pd.read_csv(ACTIVE, sep="\t", dtype=str).fillna("")

    rows = []
    key_counts = Counter()
    key_examples = defaultdict(str)

    for _, r in active.iterrows():
        row, keys = extract_summary_row(r)
        rows.append(row)
        for k in keys:
            key_counts[k] += 1
            if not key_examples[k]:
                key_examples[k] = row["packet_id"]

    df = pd.DataFrame(rows)

    sort_cols = [c for c in ["pmid", "bioproject", "packet_id"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    tsv = OUT / "chip_ai_study_summaries_clean.tsv"
    md = OUT / "CHIP_AI_STUDY_SUMMARIES_CLEAN.md"
    df.to_csv(tsv, sep="\t", index=False)
    write_markdown(df, md)

    key_inv = pd.DataFrame([
        {
            "study_summary_key": k,
            "n_packets_with_key": n,
            "example_packet_id": key_examples[k],
        }
        for k, n in key_counts.most_common()
    ])
    key_path = OUT / "CHIP_STUDY_SUMMARY_KEY_INVENTORY.tsv"
    key_inv.to_csv(key_path, sep="\t", index=False)

    print("Wrote:", tsv)
    print("Wrote:", md)
    print("Wrote:", key_path)
    print()
    print(f"Packets summarized: {len(df)}")
    print()
    print("Top study_summary keys:")
    print(key_inv.head(30).to_string(index=False))


if __name__ == "__main__":
    main()
