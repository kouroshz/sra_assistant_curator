#!/usr/bin/env python3

"""
Create paper/BioProject-level input packets for the optional agentic AI curator.

This script does NOT call an API.
It prepares token-aware packet JSON files plus sidecar rowwise TSV files.

Input:
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_json/*.json
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables/*.rowwise_evidence.tsv
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv
  outputs/02_QC_SUMMARIES/paper_packet_summary.tsv

Design:
  - One packet per PMID + BioProject when PMID exists.
  - One packet per noPMID + BioProject otherwise.
  - JSON includes compact unit summary, evidence summaries, sample-label groups, and output schema.
  - Full rowwise evidence for that unit is written to a sidecar TSV.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


DEFAULT_EVIDENCE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv")
DEFAULT_PAPERS_DIR = Path("papers")
DEFAULT_JSON_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_json")
DEFAULT_TABLE_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")
DEFAULT_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/paper_packet_summary.tsv")


ROWWISE_KEEP_COLUMNS = [
    "source_row_id",
    "source_row_number",
    "Run",
    "BioSample",
    "PMID",
    "BioProject",
    "LibraryStrategy",
    "LibraryName",
    "SampleName",
    "ScientificName",
    "sra_LibraryName",
    "sra_SampleName",
    "sra_ScientificName",
    "biosample_title",
    "biosample_taxonomy_name",
    "biosample_attr_sample_name",
    "biosample_attr_submitter_id",
    "biosample_attr_isolate",
    "biosample_attr_strain",
    "biosample_attr_genotype",
    "biosample_attr_phenotype",
    "biosample_attr_disease",
    "biosample_attr_sampling_site",
    "biosample_attr_developmental_stage",
    "biosample_attr_dev_stage",
    "biosample_attr_life_stage",
    "biosample_attr_treatment",
    "biosample_attr_condition",
    "biosample_attr_target",
    "biosample_attr_antibody",
    "biosample_attr_arrayexpress_developmentalstage",
    "detected_stage_terms",
    "detected_strain_terms",
    "detected_control_terms",
    "detected_perturbation_terms",
    "detected_assay_target_terms",
    "has_stage_evidence",
    "has_strain_evidence",
    "has_condition_evidence",
    "needs_ai",
    "public_metadata_evidence_compact",
]


SAMPLE_LABEL_COLUMNS = [
    "LibraryName",
    "SampleName",
    "sra_LibraryName",
    "sra_SampleName",
    "biosample_title",
    "biosample_attr_sample_name",
    "biosample_attr_submitter_id",
    "biosample_attr_isolate",
    "biosample_attr_strain",
    "biosample_attr_genotype",
    "biosample_attr_developmental_stage",
    "biosample_attr_dev_stage",
    "biosample_attr_life_stage",
    "biosample_attr_treatment",
    "biosample_attr_condition",
    "biosample_attr_arrayexpress_developmentalstage",
    "detected_stage_terms",
    "detected_strain_terms",
    "detected_control_terms",
    "detected_perturbation_terms",
]


AI_TASK = """
You are assisting human curators building a rowwise Plasmodium public-data processing manifest.

Your job is to use the paper, rowwise public metadata evidence, and sample labels to infer a sample map and rowwise metadata suggestions.

Important principles:
- The final object is rowwise/runwise, not group-level only.
- Do not overwrite master data.
- Do not invent facts.
- Use "unknown" when evidence is missing.
- Flag ambiguity clearly.
- Keep evidence pointers concise and checkable.
- Prefer sample-map rules/patterns that can be applied to many rows.
- Mark low-confidence rows for human review.
""".strip()


AI_OUTPUT_SCHEMA = {
    "packet_id": "string",
    "pmid": "string or noPMID",
    "bioproject": "string",
    "ai_review_status": "reviewed | insufficient_evidence | skipped | error",
    "paper_summary": {
        "study_goal": "short string",
        "assays": ["RNA-seq | ChIP-seq | CUT&RUN | CUT&Tag | ATAC-seq | other | unknown"],
        "organism_strain_summary": "short string",
        "main_comparisons": ["short strings"],
        "important_warnings": ["short strings"],
    },
    "sample_map": [
        {
            "sample_class_id": "stable short label assigned by AI",
            "sample_label_pattern": "human-readable pattern in LibraryName/SampleName/BioSample title",
            "matched_run_ids": ["Run IDs or empty if rule-based only"],
            "matched_source_row_ids": ["source_row_id values or empty if too many"],
            "assay_type": "string",
            "strain": "string or unknown",
            "stage_or_timepoint": "string or unknown",
            "mutant_or_perturbation": "string or unknown",
            "condition": "string or unknown",
            "replicate_logic": "string or unknown",
            "is_control_or_background": "yes | no | unknown",
            "control_background_type": "input | IgG | WT | untreated | vehicle | untagged | matched stage control | no suitable control | unknown",
            "likely_comparator_sample_class_id": "string or unknown",
            "evidence": "short paper/SRA/BioSample evidence pointer",
            "confidence": "high | medium | low",
            "warning_flags": ["short strings"],
        }
    ],
    "rowwise_suggestion_policy": {
        "should_generate_full_rowwise_table": "yes | no",
        "reason": "short string",
        "recommended_next_step": "short string",
    },
    "low_confidence_rows": [
        {
            "source_row_id": "string",
            "Run": "string",
            "reason": "short string",
            "suggested_curator_check": "short string",
        }
    ],
    "global_warnings": ["short strings"],
}


def clean_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def normalize_pmid(x) -> str:
    s = clean_value(x)
    if not s:
        return "noPMID"
    # Handle Excel/pandas float-like PMIDs: 35637187.0
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s if s else "noPMID"


def safe_filename(s: str) -> str:
    s = str(s)
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def unique_nonempty(series, max_items=50):
    vals = sorted(set(clean_value(x) for x in series if clean_value(x)))
    if len(vals) > max_items:
        return vals[:max_items] + [f"... [{len(vals)} unique total]"]
    return vals


def collapse_counts(series, max_items=30):
    vals = [clean_value(x) for x in series if clean_value(x)]
    if not vals:
        return []
    counts = pd.Series(vals).value_counts()
    out = []
    for k, v in counts.head(max_items).items():
        out.append({"value": k, "n": int(v)})
    if len(counts) > max_items:
        out.append({"value": f"... [{len(counts)} unique total]", "n": None})
    return out


def find_pdf_candidates(papers_dir: Path, pmid: str) -> list[str]:
    if pmid == "noPMID" or not papers_dir.exists():
        return []
    hits = []
    for pdf in papers_dir.glob("*.pdf"):
        if pmid in pdf.name:
            hits.append(str(pdf))
    return sorted(hits)


def make_packet_id(pmid: str, bioproject: str) -> str:
    return f"PMID_{safe_filename(pmid)}__BIOPROJECT_{safe_filename(bioproject)}"


def build_sample_label_groups(g: pd.DataFrame, max_groups=80) -> list[dict]:
    cols = [c for c in SAMPLE_LABEL_COLUMNS if c in g.columns]

    if not cols:
        return []

    # Signature based on the most informative public metadata fields.
    sig_cols = [
        c for c in [
            "sra_LibraryName",
            "sra_SampleName",
            "biosample_title",
            "biosample_attr_sample_name",
            "biosample_attr_submitter_id",
            "biosample_attr_isolate",
            "biosample_attr_strain",
            "biosample_attr_genotype",
            "biosample_attr_developmental_stage",
            "biosample_attr_dev_stage",
            "biosample_attr_treatment",
            "detected_stage_terms",
            "detected_perturbation_terms",
            "detected_control_terms",
        ]
        if c in g.columns
    ]

    if not sig_cols:
        sig_cols = cols[:5]

    tmp = g.copy()
    tmp["_sample_signature"] = tmp[sig_cols].fillna("").astype(str).agg(" || ".join, axis=1)

    rows = []
    grouped = tmp.groupby("_sample_signature", dropna=False)
    for i, (sig, sg) in enumerate(grouped, start=1):
        if i > max_groups:
            rows.append({
                "sample_signature": f"... [{grouped.ngroups} total signature groups]",
                "n_rows": None,
                "runs": [],
                "source_row_ids": [],
                "evidence_counts": {},
            })
            break

        evidence_counts = {}
        for c in cols:
            vals = collapse_counts(sg[c], max_items=10)
            if vals:
                evidence_counts[c] = vals

        rows.append({
            "sample_signature": sig[:1000],
            "n_rows": int(len(sg)),
            "runs": unique_nonempty(sg["Run"], max_items=30) if "Run" in sg.columns else [],
            "source_row_ids": unique_nonempty(sg["source_row_id"], max_items=30) if "source_row_id" in sg.columns else [],
            "evidence_counts": evidence_counts,
        })

    rows = sorted(rows, key=lambda x: (x["n_rows"] is not None, x["n_rows"] or 0), reverse=True)
    return rows


def make_unit_summary(g: pd.DataFrame, pmid: str, bioproject: str) -> dict:
    def nunique(col):
        return int(g[col].map(clean_value).replace("", pd.NA).nunique(dropna=True)) if col in g.columns else 0

    def nonempty(col):
        return int(g[col].map(clean_value).astype(bool).sum()) if col in g.columns else 0

    return {
        "pmid": pmid,
        "bioproject": bioproject,
        "n_rows": int(len(g)),
        "n_runs": nunique("Run"),
        "n_biosamples": nunique("BioSample"),
        "library_strategies": unique_nonempty(g["LibraryStrategy"], max_items=20) if "LibraryStrategy" in g.columns else [],
        "n_rows_with_stage_evidence": nonempty("detected_stage_terms"),
        "n_rows_with_strain_evidence": nonempty("detected_strain_terms"),
        "n_rows_with_perturbation_evidence": nonempty("detected_perturbation_terms"),
        "n_rows_with_control_evidence": nonempty("detected_control_terms"),
        "n_rows_needing_ai": int(g["needs_ai"].astype(str).str.lower().eq("true").sum()) if "needs_ai" in g.columns else None,
        "top_library_names": collapse_counts(g["sra_LibraryName"], max_items=20) if "sra_LibraryName" in g.columns else [],
        "top_biosample_titles": collapse_counts(g["biosample_title"], max_items=20) if "biosample_title" in g.columns else [],
        "top_sample_names": collapse_counts(g["sra_SampleName"], max_items=20) if "sra_SampleName" in g.columns else [],
        "detected_stage_terms": collapse_counts(g["detected_stage_terms"], max_items=20) if "detected_stage_terms" in g.columns else [],
        "detected_perturbation_terms": collapse_counts(g["detected_perturbation_terms"], max_items=20) if "detected_perturbation_terms" in g.columns else [],
        "detected_control_terms": collapse_counts(g["detected_control_terms"], max_items=20) if "detected_control_terms" in g.columns else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--papers-dir", type=Path, default=DEFAULT_PAPERS_DIR)
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_JSON_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--max-json-row-examples", type=int, default=30)
    args = parser.parse_args()

    if not args.evidence.exists():
        raise FileNotFoundError(f"Missing rowwise public metadata evidence table: {args.evidence}")

    args.json_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.evidence, sep="\t", dtype=str)
    df["packet_pmid"] = df["PMID"].map(normalize_pmid) if "PMID" in df.columns else "noPMID"
    df["packet_bioproject"] = df["BioProject"].map(lambda x: clean_value(x) or "noBioProject")

    keep_cols = [c for c in ROWWISE_KEEP_COLUMNS if c in df.columns]

    index_rows = []
    for (pmid, bioproject), g in df.groupby(["packet_pmid", "packet_bioproject"], dropna=False):
        packet_id = make_packet_id(pmid, bioproject)
        json_path = args.json_dir / f"{packet_id}.json"
        table_path = args.table_dir / f"{packet_id}.rowwise_evidence.tsv"

        # Sidecar full rowwise evidence table for this paper/BioProject unit.
        g_out = g[keep_cols].copy()
        g_out.to_csv(table_path, sep="\t", index=False)

        pdf_candidates = find_pdf_candidates(args.papers_dir, pmid)
        unit_summary = make_unit_summary(g, pmid, bioproject)
        sample_label_groups = build_sample_label_groups(g)

        # Include only a small row preview in JSON; full rowwise evidence is in sidecar TSV.
        row_examples = g_out.head(args.max_json_row_examples).fillna("").to_dict(orient="records")

        packet = {
            "packet_version": "2026-06-02.paper_level.v1",
            "packet_id": packet_id,
            "purpose": "Paper/BioProject-level packet for optional agentic AI sample-map inference.",
            "important_policy": {
                "api_optional": True,
                "do_not_modify_master": True,
                "ai_outputs_are_suggestions_only": True,
                "human_curator_makes_final_decision": True,
                "final_object_is_rowwise_manifest": True,
            },
            "unit": unit_summary,
            "paper_context": {
                "papers_dir": str(args.papers_dir),
                "paper_pdf_candidates": pdf_candidates,
                "paper_pdf_count": len(pdf_candidates),
                "note": "Future AI script should read PDF text if available and combine it with the sidecar rowwise evidence table.",
            },
            "sidecar_rowwise_evidence_table": str(table_path),
            "rowwise_evidence_preview": row_examples,
            "sample_label_groups": sample_label_groups,
            "ai_task": AI_TASK,
            "ai_output_schema": AI_OUTPUT_SCHEMA,
        }

        json_path.write_text(json.dumps(packet, indent=2))

        index_rows.append({
            "packet_id": packet_id,
            "pmid": pmid,
            "bioproject": bioproject,
            "packet_json": str(json_path),
            "rowwise_evidence_tsv": str(table_path),
            "n_rows": len(g),
            "n_runs": g["Run"].nunique(dropna=True) if "Run" in g.columns else "",
            "n_biosamples": g["BioSample"].nunique(dropna=True) if "BioSample" in g.columns else "",
            "n_rows_needing_ai": unit_summary["n_rows_needing_ai"],
            "n_rows_with_stage_evidence": unit_summary["n_rows_with_stage_evidence"],
            "n_rows_with_perturbation_evidence": unit_summary["n_rows_with_perturbation_evidence"],
            "n_rows_with_control_evidence": unit_summary["n_rows_with_control_evidence"],
            "paper_pdf_count": len(pdf_candidates),
            "paper_pdf_candidates": ";".join(pdf_candidates),
        })

    index = pd.DataFrame(index_rows).sort_values(
        ["paper_pdf_count", "n_rows_needing_ai", "n_rows"],
        ascending=[False, False, False],
    )
    index.to_csv(args.index, sep="\t", index=False)

    summary = pd.DataFrame([
        {"metric": "input_evidence_table", "value": str(args.evidence)},
        {"metric": "n_rowwise_rows", "value": len(df)},
        {"metric": "n_paper_packets", "value": len(index)},
        {"metric": "n_packets_with_pdf", "value": int((index["paper_pdf_count"] > 0).sum())},
        {"metric": "n_packets_without_pdf", "value": int((index["paper_pdf_count"] == 0).sum())},
        {"metric": "n_total_rows_needing_ai", "value": int(index["n_rows_needing_ai"].fillna(0).sum())},
        {"metric": "packet_index", "value": str(args.index)},
        {"metric": "packet_json_dir", "value": str(args.json_dir)},
        {"metric": "packet_table_dir", "value": str(args.table_dir)},
    ])
    summary.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote packet index: {args.index}")
    print(f"Wrote packet JSON dir: {args.json_dir}")
    print(f"Wrote packet table dir: {args.table_dir}")
    print(f"Wrote summary: {args.summary}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
