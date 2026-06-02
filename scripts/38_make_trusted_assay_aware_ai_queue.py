#!/usr/bin/env python3

"""
Create a trusted, assay-aware AI/curator queue.

This script does NOT call an API.

Inputs:
  outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv
  outputs/02_QC_SUMMARIES/trusted_assay_aware_ai_queue_summary.tsv

Policy:
  - No-PMID packets are excluded from this queue.
  - This queue is for high-confidence publication-linked datasets only.
  - AI is optional and should assist human curators, not overwrite final fields.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DEFAULT_TRUSTED = Path("outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv")
DEFAULT_PRIORITY = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv")
DEFAULT_EVIDENCE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv")
DEFAULT_OUT = Path("outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/trusted_assay_aware_ai_queue_summary.tsv")


CHIP_LIKE_PATTERNS = [
    r"\bChIP\b",
    r"\bChIP[- ]seq\b",
    r"\bCUT&RUN\b",
    r"\bCUT&Tag\b",
    r"\bCUT\s*and\s*RUN\b",
    r"\bchromatin immunoprecipitation\b",
    r"\bIP\b",
    r"\binput\b",
    r"\bIgG\b",
    r"\bantibody\b",
    r"\bHA\b",
    r"\bFLAG\b",
    r"\bGFP\b",
    r"\bmyc\b",
]

RNA_PATTERNS = [
    r"\bRNA[- ]seq\b",
    r"\bRNA Seq\b",
    r"\btranscriptome\b",
    r"\bmRNA\b",
    r"\bribo[- ]?seq\b",
    r"\bTRIBE\b",
]

PERTURBATION_PATTERNS = [
    r"\bKD\b",
    r"\bknockdown\b",
    r"\bKO\b",
    r"\bknockout\b",
    r"\bglmS\b",
    r"\bGlcN\b",
    r"\bglucosamine\b",
    r"\bmutant\b",
    r"\bconditional\b",
    r"\bdrug\b",
    r"\btreatment\b",
    r"\btreated\b",
    r"\buntreated\b",
    r"\bvehicle\b",
    r"\boverexpression\b",
    r"\bOE\b",
    r"\binduced\b",
    r"\brepressed\b",
]

CONTROL_PATTERNS = [
    r"\bWT\b",
    r"\bwild[- ]type\b",
    r"\bcontrol\b",
    r"\buntreated\b",
    r"\bvehicle\b",
    r"\binput\b",
    r"\bIgG\b",
    r"\bmock\b",
    r"\buntagged\b",
]

SINGLE_CELL_PATTERNS = [
    r"\bsinglecell\b",
    r"\bsingle[-_ ]cell\b",
    r"\bscRNA\b",
    r"\bwell\b",
    r"\bplate\b",
]


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def boolish(x) -> bool:
    return str(x).strip().lower() in {"true", "1", "yes", "y"}


def count_pattern_hits(text: str, patterns: list[str]) -> int:
    if not text:
        return 0
    return sum(len(re.findall(p, text, flags=re.IGNORECASE)) for p in patterns)


def normalize_pmid(x) -> str:
    s = clean(x)
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s


def evidence_for_packet(evidence: pd.DataFrame, pmid: str, bioproject: str) -> pd.DataFrame:
    pmid = normalize_pmid(pmid)
    bioproject = clean(bioproject)
    if "PMID" not in evidence.columns or "BioProject" not in evidence.columns:
        return pd.DataFrame()
    tmp = evidence.copy()
    tmp["_pmid_norm"] = tmp["PMID"].map(normalize_pmid)
    return tmp[(tmp["_pmid_norm"] == pmid) & (tmp["BioProject"].map(clean) == bioproject)].copy()


def compact_text_from_rows(g: pd.DataFrame, max_rows: int = 400) -> str:
    cols = [
        "LibraryStrategy",
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
        "biosample_attr_treatment",
        "biosample_attr_condition",
        "biosample_attr_target",
        "biosample_attr_antibody",
        "detected_assay_target_terms",
        "detected_perturbation_terms",
        "detected_control_terms",
        "public_metadata_evidence_compact",
    ]
    cols = [c for c in cols if c in g.columns]
    if g.empty or not cols:
        return ""
    return " ".join(
        g[cols].head(max_rows).fillna("").astype(str).agg(" | ".join, axis=1).tolist()
    )


def classify_assay(row: pd.Series, g: pd.DataFrame) -> dict:
    text = compact_text_from_rows(g)
    library_strategies = sorted(set(clean(x) for x in g.get("LibraryStrategy", pd.Series(dtype=str)) if clean(x)))
    strategy_text = " ".join(library_strategies)

    chip_hits = count_pattern_hits(strategy_text + " " + text, CHIP_LIKE_PATTERNS)
    rna_hits = count_pattern_hits(strategy_text + " " + text, RNA_PATTERNS)
    perturb_hits = count_pattern_hits(text, PERTURBATION_PATTERNS)
    control_hits = count_pattern_hits(text, CONTROL_PATTERNS)
    single_cell_hits = count_pattern_hits(text, SINGLE_CELL_PATTERNS)

    library_strategy_joined = ";".join(library_strategies)

    # LibraryStrategy is a strong clue when present.
    strategy_lower = strategy_text.lower()
    has_chip_strategy = "chip-seq" in strategy_lower or "chip seq" in strategy_lower
    has_rna_strategy = "rna-seq" in strategy_lower or "rna seq" in strategy_lower

    n_rows = len(g)
    n_pert = int(pd.to_numeric(row.get("n_rows_with_perturbation_evidence", 0), errors="coerce") or 0)
    n_ctrl = int(pd.to_numeric(row.get("n_rows_with_control_evidence", 0), errors="coerce") or 0)
    n_need = int(pd.to_numeric(row.get("n_rows_needing_ai", 0), errors="coerce") or 0)

    # LibraryStrategy is the strongest packet-level assay evidence.
    # Paper text may mention ChIP/CUT&RUN even when this BioProject packet contains RNA-seq only.
    if has_rna_strategy and not has_chip_strategy:
        if perturb_hits > 0 or n_pert > 0 or n_ctrl > 0:
            assay_class = "rna_seq_contrast_or_perturbation"
        else:
            assay_class = "rna_seq_expression_or_timecourse"
    elif has_chip_strategy and not has_rna_strategy:
        assay_class = "chip_like_target_enrichment"
    elif has_chip_strategy and has_rna_strategy:
        assay_class = "mixed_or_ambiguous"
    elif chip_hits >= 5 and not has_rna_strategy:
        assay_class = "chip_like_target_enrichment"
    elif rna_hits > 0:
        if perturb_hits > 0 or n_pert > 0 or n_ctrl > 0:
            assay_class = "rna_seq_contrast_or_perturbation"
        else:
            assay_class = "rna_seq_expression_or_timecourse"
    elif chip_hits > 0 and rna_hits > 0:
        assay_class = "mixed_or_ambiguous"
    else:
        assay_class = "other_or_unknown"

    if assay_class == "chip_like_target_enrichment":
        main_ai_task = "Identify target/antibody/tag, classify sample role, assign matched background/control, and determine peak-calling readiness."
        required_outputs = "target;antibody_or_tag;sample_role;background_control;control_match_level;peak_calling_ready;blocker_reason"
    elif assay_class == "rna_seq_contrast_or_perturbation":
        main_ai_task = "Infer sample map, perturbation/treatment classes, matched controls/comparators, replicates, and DEG readiness."
        required_outputs = "condition;perturbation;treatment;stage_timepoint;replicate;comparator_group;deg_ready;blocker_reason"
    elif assay_class == "rna_seq_expression_or_timecourse":
        main_ai_task = "Infer sample map, stage/timepoint/strain/replicate annotations, and expression-atlas/time-course usefulness."
        required_outputs = "stage_timepoint;strain;sample_type;replicate;expression_usefulness;warnings"
    elif assay_class == "mixed_or_ambiguous":
        main_ai_task = "Resolve assay classes and split packet into assay-specific sample maps before rowwise curation."
        required_outputs = "assay_split;sample_map;row_assignment;warnings"
    else:
        main_ai_task = "Determine assay type and whether the dataset is useful for trusted curation."
        required_outputs = "assay_type;sample_map;analysis_readiness;warnings"

    # Readiness heuristics before AI.
    if assay_class == "chip_like_target_enrichment":
        if n_ctrl > 0:
            pre_ai_readiness = "potentially_peak_calling_ready_needs_background_validation"
        else:
            pre_ai_readiness = "not_peak_calling_ready_until_background_found"
    elif assay_class == "rna_seq_contrast_or_perturbation":
        if n_ctrl > 0 or control_hits > 0:
            pre_ai_readiness = "potentially_deg_ready_needs_comparator_validation"
        else:
            pre_ai_readiness = "not_deg_ready_until_control_or_comparator_found"
    elif assay_class == "rna_seq_expression_or_timecourse":
        pre_ai_readiness = "expression_or_timecourse_useful_if_stage_strain_clear"
    else:
        pre_ai_readiness = "unknown_needs_assay_classification"

    return {
        "assay_class": assay_class,
        "library_strategies_detected": library_strategy_joined,
        "chip_like_signal_hits": chip_hits,
        "rna_signal_hits": rna_hits,
        "perturbation_signal_hits": perturb_hits,
        "control_signal_hits": control_hits,
        "single_cell_signal_hits": single_cell_hits,
        "main_ai_task": main_ai_task,
        "assay_specific_required_outputs": required_outputs,
        "pre_ai_analysis_readiness": pre_ai_readiness,
    }


def score_assay_aware(row: pd.Series, assay: dict) -> dict:
    base = float(pd.to_numeric(row.get("ai_priority_score", 0), errors="coerce") or 0)
    n_rows = int(pd.to_numeric(row.get("n_rows", 0), errors="coerce") or 0)
    n_need = int(pd.to_numeric(row.get("n_rows_needing_ai", 0), errors="coerce") or 0)
    has_pdf = int(pd.to_numeric(row.get("paper_pdf_count", 0), errors="coerce") or 0) > 0
    original_action = clean(row.get("recommended_action", ""))

    score = base
    reasons = [clean(row.get("priority_reasons", ""))] if clean(row.get("priority_reasons", "")) else []

    assay_class = assay["assay_class"]

    if not has_pdf:
        score -= 50
        reasons.append("trusted_but_no_local_pdf_defer_until_pdf_available")

    if assay_class == "chip_like_target_enrichment":
        score += 20
        reasons.append("chip_like_background_is_analysis_critical")
        if assay["control_signal_hits"] == 0:
            score += 10
            reasons.append("chip_like_missing_control_signal_high_value_for_ai")
    elif assay_class == "rna_seq_contrast_or_perturbation":
        score += 15
        reasons.append("rna_perturbation_comparator_logic_high_value_for_ai")
        if assay["control_signal_hits"] == 0:
            score += 8
            reasons.append("rna_perturbation_missing_control_signal")
    elif assay_class == "rna_seq_expression_or_timecourse":
        score -= 5
        reasons.append("expression_timecourse_lower_priority_than_contrast_or_chip")
    elif assay_class == "mixed_or_ambiguous":
        score += 15
        reasons.append("mixed_assay_packet_needs_split")
    else:
        score -= 5
        reasons.append("unknown_assay_lower_priority")

    # Well-based single-cell expression-only should stay low priority.
    if boolish(row.get("well_or_single_cell_uniform", False)):
        score -= 100
        reasons.append("well_or_single_cell_uniform_quarantine_from_api_batch")

    if score >= 65:
        tier = "high"
        action = "run_ai_first"
    elif score >= 40:
        tier = "medium"
        action = "run_ai_pilot"
    elif score >= 20:
        tier = "low"
        action = "optional_later"
    else:
        tier = "defer"
        action = "defer"

    if boolish(row.get("well_or_single_cell_uniform", False)):
        tier = "skip_single_cell_well_uniform"
        action = "skip_or_random_qc_only"

    # Curator priority.
    if assay_class == "chip_like_target_enrichment" and action.startswith("run_ai"):
        curator_priority = "high"
    elif assay_class == "rna_seq_contrast_or_perturbation" and action.startswith("run_ai"):
        curator_priority = "high"
    elif action == "run_ai_pilot":
        curator_priority = "medium"
    elif action == "skip_or_random_qc_only":
        curator_priority = "low_random_qc"
    else:
        curator_priority = "low"

    return {
        "assay_aware_priority_score": round(score, 2),
        "assay_aware_priority_tier": tier,
        "assay_aware_recommended_action": action,
        "assay_aware_curator_priority": curator_priority,
        "assay_aware_priority_reasons": ";".join([r for r in reasons if r]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trusted", type=Path, default=DEFAULT_TRUSTED)
    parser.add_argument("--priority", type=Path, default=DEFAULT_PRIORITY)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    if not args.trusted.exists():
        raise FileNotFoundError(f"Missing trusted packets table: {args.trusted}")
    if not args.priority.exists():
        raise FileNotFoundError(f"Missing AI priority queue: {args.priority}")
    if not args.evidence.exists():
        raise FileNotFoundError(f"Missing rowwise evidence table: {args.evidence}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    trusted = pd.read_csv(args.trusted, sep="\t", dtype=str).fillna("")
    priority = pd.read_csv(args.priority, sep="\t", dtype=str).fillna("")
    evidence = pd.read_csv(args.evidence, sep="\t", dtype=str).fillna("")

    # Merge trusted publication gate with existing priority fields.
    merged = trusted.merge(
        priority,
        on="packet_id",
        how="left",
        suffixes=("", "_priority"),
    )

    rows = []
    for _, row in merged.iterrows():
        pmid = row.get("pmid", "")
        bioproject = row.get("bioproject", "")

        g = evidence_for_packet(evidence, pmid, bioproject)
        assay = classify_assay(row, g)
        rank = score_assay_aware(row, assay)

        outrow = row.to_dict()
        outrow.update({
            "trusted_publication_gate": "trusted_pmid_present",
            "trusted_row_count_check": len(g),
        })
        outrow.update(assay)
        outrow.update(rank)
        rows.append(outrow)

    out = pd.DataFrame(rows)

    order = {
        "run_ai_first": 0,
        "run_ai_pilot": 1,
        "optional_later": 2,
        "skip_or_random_qc_only": 3,
        "defer": 4,
    }
    out["_order"] = out["assay_aware_recommended_action"].map(order).fillna(9)
    out = out.sort_values(
        ["_order", "assay_aware_priority_score", "n_rows"],
        ascending=[True, False, False],
    ).drop(columns=["_order"])

    out.to_csv(args.out, sep="\t", index=False)

    summary = []
    summary.append({"metric": "n_trusted_packets", "value": len(out)})
    summary.append({"metric": "n_trusted_rows", "value": int(pd.to_numeric(out["n_rows"], errors="coerce").fillna(0).sum())})

    for col in [
        "assay_class",
        "assay_aware_recommended_action",
        "assay_aware_priority_tier",
        "assay_aware_curator_priority",
        "pre_ai_analysis_readiness",
    ]:
        counts = out[col].value_counts(dropna=False)
        for k, v in counts.items():
            summary.append({"metric": f"{col}:{k}", "value": int(v)})

    summary.append({"metric": "output_queue", "value": str(args.out)})
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote trusted assay-aware queue: {args.out}")
    print(f"Wrote summary: {args.summary}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
