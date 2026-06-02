#!/usr/bin/env python3

"""
Create compact input packets for the future API-based agentic AI curator.

This script does NOT call an API.
This script does NOT modify metadata.
This script only prepares per-curation-group JSON packets that contain:
  - stable IDs
  - current parsed metadata
  - run/BioSample identifiers
  - compact row examples
  - paper PDF candidates
  - explicit AI output schema

Later, an API-based paper-reading assistant can use these packets to populate
ai_* suggestion fields and reduce human curator burden.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_ROWWISE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv")
DEFAULT_GROUP_REVIEW = Path("outputs/01_CURRENT_DRAFT_TABLES/curator_group_level_review_WITH_STABLE_IDS.tsv")
DEFAULT_PAPERS_DIR = Path("papers")
DEFAULT_OUT_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/input_packets/group_packets")
DEFAULT_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/input_packets/agentic_ai_packet_index.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/agentic_ai_packet_summary.tsv")


METADATA_COLUMNS_TO_COLLAPSE = [
    "PMID",
    "BioProject",
    "LibraryStrategy",
    "Title",
    "study_title",
    "paper_title",
    "organism",
    "Cell_Cycle_Stage",
    "Life_Stage",
    "Target",
    "Strain",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "background_sample",
    "replicate_number",
    "assay_type",
    "LibraryLayout",
    "LibrarySelection",
    "LibrarySource",
    "Platform",
    "Instrument",
]


ROW_EXAMPLE_COLUMNS = [
    "source_row_id",
    "source_row_number",
    "Run",
    "BioSample",
    "BioProject",
    "PMID",
    "LibraryStrategy",
    "Title",
    "Cell_Cycle_Stage",
    "Life_Stage",
    "Target",
    "Strain",
    "Mutant",
    "Condition1",
    "Condition2",
    "Condition3",
    "background_sample",
    "replicate_number",
    "download_path",
]


AI_OUTPUT_SCHEMA = {
    "curation_group_id": "string",
    "ai_review_status": "reviewed | insufficient_evidence | skipped | error",
    "ai_assay_type_suggestion": "RNA-seq | ChIP-seq | CUT&RUN | CUT&Tag | ATAC-seq | other | unknown",
    "ai_target_suggestion": "target gene/protein/antibody if relevant; blank if RNA-seq without target",
    "ai_stage_timepoint_suggestion": "life stage, cell-cycle stage, developmental stage, timepoint, or unknown",
    "ai_strain_suggestion": "parasite strain/substrain/line if recoverable",
    "ai_mutant_or_perturbation_suggestion": "genetic perturbation, knockdown, knockout, overexpression, drug, condition, or blank",
    "ai_condition_suggestion": "treatment, vehicle, untreated, timepoint condition, environmental condition, or blank",
    "ai_control_background_suggestion": "likely control/background relationship in plain language",
    "ai_control_background_type": "input | IgG | WT | untreated | vehicle | untagged | matched stage control | no suitable control | unknown",
    "ai_candidate_control_group_ids": "list of candidate curation_group_id values if inferable from packet/index context",
    "ai_candidate_control_run_ids": "list of candidate Run IDs if inferable",
    "ai_evidence_summary": "concise evidence-based explanation",
    "ai_paper_evidence_quote_or_location": "short quote or section/table/figure location from paper, if available",
    "ai_sra_biosample_evidence": "metadata evidence from SRA/BioSample/sample title",
    "ai_confidence": "high | medium | low",
    "ai_warning_flags": "list of warnings, ambiguities, conflicts, missing paper, missing metadata, etc.",
}


AI_TASK = """
You are assisting human curators who are building a public Plasmodium processing manifest.

Your job is to read the paper context, SRA/BioSample metadata, and current parsed fields,
then suggest corrected metadata for the sample group.

Focus on reducing curator burden:
- identify assay type
- identify target/antibody if ChIP/CUT&RUN/CUT&Tag-like
- identify stage/timepoint/life-cycle state
- identify strain/substrain
- identify perturbation/mutant/treatment/condition
- determine whether this group is experimental, control, input, IgG, WT, vehicle, untreated, or unknown
- suggest likely matched background/control groups if evidence supports it

Do not overwrite human curator fields.
Do not invent facts.
If evidence is weak or conflicting, mark low confidence and explain the ambiguity.
Return structured JSON matching the provided output schema.
""".strip()


def clean_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def unique_values(series, max_items=30):
    vals = sorted(set(clean_value(v) for v in series if clean_value(v)))
    if len(vals) > max_items:
        return vals[:max_items] + [f"... [{len(vals)} unique total]"]
    return vals


def safe_filename(s: str) -> str:
    keep = []
    for ch in str(s):
        if ch.isalnum() or ch in {"_", "-", "."}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)


def find_paper_candidates(papers_dir: Path, pmids: list[str]) -> list[str]:
    if not papers_dir.exists():
        return []

    candidates = []
    all_pdfs = list(papers_dir.glob("*.pdf"))

    for pmid in pmids:
        if not pmid:
            continue
        for pdf in all_pdfs:
            name = pdf.name.lower()
            if pmid.lower() in name:
                candidates.append(str(pdf))

    # Also include PDFs whose stem contains PMID-like tokens only if exact PMID matched above.
    return sorted(set(candidates))


def records_for_examples(g: pd.DataFrame, columns: list[str], max_rows: int) -> list[dict]:
    cols = [c for c in columns if c in g.columns]
    subset = g[cols].head(max_rows).copy()
    subset = subset.fillna("")
    return subset.to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rowwise", type=Path, default=DEFAULT_ROWWISE)
    parser.add_argument("--group-review", type=Path, default=DEFAULT_GROUP_REVIEW)
    parser.add_argument("--papers-dir", type=Path, default=DEFAULT_PAPERS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--max-row-examples", type=int, default=12)
    args = parser.parse_args()

    if not args.rowwise.exists():
        raise FileNotFoundError(f"Missing rowwise stable-ID table: {args.rowwise}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    rowwise = pd.read_csv(args.rowwise, sep="\t", dtype=str)

    group_review = None
    if args.group_review.exists():
        group_review = pd.read_csv(args.group_review, sep="\t", dtype=str)
        group_review = group_review.set_index("curation_group_id", drop=False)

    index_rows = []

    for group_id, g in rowwise.groupby("curation_group_id", dropna=False):
        pmids = unique_values(g["PMID"], max_items=10) if "PMID" in g.columns else []
        pmids_clean = [p for p in pmids if not p.startswith("...")]
        paper_candidates = find_paper_candidates(args.papers_dir, pmids_clean)

        current_metadata = {}
        for col in METADATA_COLUMNS_TO_COLLAPSE:
            if col in g.columns:
                current_metadata[col] = unique_values(g[col])

        identifiers = {
            "curation_group_id": group_id,
            "n_source_rows": int(len(g)),
            "source_row_ids": unique_values(g["source_row_id"], max_items=50),
            "source_row_numbers": unique_values(g["source_row_number"], max_items=50),
            "runs": unique_values(g["Run"], max_items=80) if "Run" in g.columns else [],
            "biosamples": unique_values(g["BioSample"], max_items=80) if "BioSample" in g.columns else [],
            "pmids": pmids,
            "bioprojects": unique_values(g["BioProject"], max_items=20) if "BioProject" in g.columns else [],
        }

        packet = {
            "packet_version": "2026-06-01.v1",
            "curation_group_id": group_id,
            "purpose": "Input packet for future API-based agentic AI metadata curation.",
            "important_policy": {
                "do_not_modify_master": True,
                "ai_fields_are_suggestions_only": True,
                "human_curator_makes_final_decision": True,
            },
            "identifiers": identifiers,
            "paper_context": {
                "papers_dir": str(args.papers_dir),
                "paper_pdf_candidates": paper_candidates,
                "paper_pdf_count": len(paper_candidates),
                "note": "PDF text is not extracted here. Future AI step should read available papers and cite evidence/locations.",
            },
            "current_parsed_metadata": current_metadata,
            "row_examples": records_for_examples(g, ROW_EXAMPLE_COLUMNS, args.max_row_examples),
            "group_review_row": (
                group_review.loc[group_id].fillna("").to_dict()
                if group_review is not None and group_id in group_review.index
                else {}
            ),
            "ai_task": AI_TASK,
            "ai_output_schema": AI_OUTPUT_SCHEMA,
        }

        pmid_tag = "_".join(pmids_clean[:3]) if pmids_clean else "noPMID"
        packet_name = f"{safe_filename(group_id)}__PMID_{safe_filename(pmid_tag)}.json"
        packet_path = args.out_dir / packet_name

        with open(packet_path, "w") as fh:
            json.dump(packet, fh, indent=2, sort_keys=False)

        index_rows.append({
            "curation_group_id": group_id,
            "packet_path": str(packet_path),
            "n_source_rows": len(g),
            "n_runs": g["Run"].nunique(dropna=True) if "Run" in g.columns else "",
            "pmids": ";".join(pmids),
            "bioprojects": ";".join(unique_values(g["BioProject"], max_items=10)) if "BioProject" in g.columns else "",
            "library_strategy": ";".join(unique_values(g["LibraryStrategy"], max_items=10)) if "LibraryStrategy" in g.columns else "",
            "paper_pdf_count": len(paper_candidates),
            "paper_pdf_candidates": ";".join(paper_candidates),
        })

    index = pd.DataFrame(index_rows).sort_values(
        ["paper_pdf_count", "n_source_rows"],
        ascending=[False, False],
    )
    index.to_csv(args.index, sep="\t", index=False)

    summary = pd.DataFrame([
        {"metric": "rowwise_input", "value": str(args.rowwise)},
        {"metric": "group_review_input", "value": str(args.group_review)},
        {"metric": "papers_dir", "value": str(args.papers_dir)},
        {"metric": "n_packets", "value": len(index)},
        {"metric": "n_packets_with_pdf_candidates", "value": int((index["paper_pdf_count"] > 0).sum())},
        {"metric": "n_packets_without_pdf_candidates", "value": int((index["paper_pdf_count"] == 0).sum())},
        {"metric": "packet_index", "value": str(args.index)},
        {"metric": "packet_dir", "value": str(args.out_dir)},
    ])
    summary.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote packet index: {args.index}")
    print(f"Wrote packet dir:   {args.out_dir}")
    print(f"Wrote summary:      {args.summary}")
    print(f"Packets: {len(index)}")
    print(f"Packets with PDF candidates: {int((index['paper_pdf_count'] > 0).sum())}")
    print(f"Packets without PDF candidates: {int((index['paper_pdf_count'] == 0).sum())}")


if __name__ == "__main__":
    main()
