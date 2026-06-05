#!/usr/bin/env python3
"""
Build the deterministic paper-packet AI priority queue.

This script does not call an API.

Inputs:
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv (optional)
  papers/ (optional local PDF directory)

Output:
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv

Scoring policy is intentionally simple and deterministic:
  - local PDFs increase priority because paper context is available
  - packets with rows needing AI receive priority
  - perturbation/control ambiguity receives priority
  - obvious single-cell/well/plate-like packets are deprioritized for routine API batches

The score is not intended to reproduce historical scores. It is a stable triage signal
for building the downstream trusted assay-aware queue.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DEFAULT_PACKET_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv")
DEFAULT_EVIDENCE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv")
DEFAULT_PAPERS_DIR = Path("papers")
DEFAULT_OUT = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv")

OUTPUT_COLUMNS = [
    "packet_id",
    "pmid",
    "bioproject",
    "packet_json",
    "rowwise_evidence_tsv",
    "n_rows",
    "n_runs",
    "n_biosamples",
    "n_rows_needing_ai",
    "n_rows_with_stage_evidence",
    "n_rows_with_perturbation_evidence",
    "n_rows_with_control_evidence",
    "paper_pdf_count",
    "paper_pdf_candidates",
    "single_cell_like",
    "well_or_single_cell_uniform",
    "single_cell_pattern_hits",
    "unique_biosample_title_ratio",
    "unique_sample_name_ratio",
    "single_cell_detection_flags",
    "ai_priority_score",
    "ai_priority_tier",
    "recommended_action",
    "curator_review_priority",
    "priority_reasons",
]

TEXT_COLUMNS = [
    "LibraryName",
    "SampleName",
    "sra_LibraryName",
    "sra_SampleName",
    "biosample_title",
    "biosample_attr_sample_name",
    "biosample_attr_submitter_id",
    "biosample_attr_genotype",
    "biosample_attr_treatment",
    "biosample_attr_condition",
    "detected_stage_terms",
    "detected_control_terms",
    "detected_perturbation_terms",
    "public_metadata_evidence_compact",
]

SINGLE_CELL_PATTERNS = [
    r"\bsingle[-_ ]?cell\b",
    r"\bscRNA\b",
    r"\bwell\b",
    r"\bplate\b",
    r"\b96[-_ ]?well\b",
    r"\b384[-_ ]?well\b",
    r"\bcell[_ -]?barcode\b",
]


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def int_value(x) -> int:
    try:
        return int(float(clean(x) or "0"))
    except Exception:
        return 0


def boolish(x) -> bool:
    return str(x).strip().lower() in {"true", "1", "yes", "y"}


def ratio_unique(series: pd.Series) -> float:
    vals = [clean(x) for x in series if clean(x)]
    if not vals:
        return 0.0
    return round(len(set(vals)) / len(vals), 4)


def packet_evidence(row: pd.Series) -> pd.DataFrame:
    path = Path(clean(row.get("rowwise_evidence_tsv", "")))
    if path.exists():
        return pd.read_csv(path, sep="\t", dtype=str).fillna("")
    return pd.DataFrame()


def fallback_evidence(evidence: pd.DataFrame, pmid: str, bioproject: str) -> pd.DataFrame:
    if evidence.empty or "PMID" not in evidence.columns or "BioProject" not in evidence.columns:
        return pd.DataFrame()
    return evidence[
        (evidence["PMID"].map(clean) == clean(pmid))
        & (evidence["BioProject"].map(clean) == clean(bioproject))
    ].copy()


def find_pdf_candidates(papers_dir: Path, pmid: str, existing: str) -> list[str]:
    candidates = [clean(x) for x in str(existing).split(";") if clean(x)]
    if papers_dir.exists() and clean(pmid):
        for pdf in papers_dir.glob("*.pdf"):
            if clean(pmid) in pdf.name and str(pdf) not in candidates:
                candidates.append(str(pdf))
    return sorted(candidates)


def combined_text(g: pd.DataFrame, max_rows: int = 500) -> str:
    if g.empty:
        return ""
    cols = [c for c in TEXT_COLUMNS if c in g.columns]
    if not cols:
        return ""
    return " ".join(g[cols].head(max_rows).fillna("").astype(str).agg(" | ".join, axis=1).tolist())


def single_cell_flags(g: pd.DataFrame) -> tuple[bool, bool, int, str]:
    text = combined_text(g)
    hits = []
    for pat in SINGLE_CELL_PATTERNS:
        n = len(re.findall(pat, text, flags=re.IGNORECASE))
        if n:
            hits.append(f"{pat}:{n}")
    hit_count = sum(int(x.rsplit(":", 1)[1]) for x in hits)

    title_ratio = ratio_unique(g["biosample_title"]) if "biosample_title" in g.columns else 0.0
    sample_ratio = ratio_unique(g["SampleName"]) if "SampleName" in g.columns else 0.0
    n_rows = len(g)

    single_cell_like = hit_count > 0
    well_uniform = False
    if n_rows >= 24 and (title_ratio > 0.9 or sample_ratio > 0.9) and hit_count > 0:
        well_uniform = True

    flags = ";".join(hits)
    if well_uniform:
        flags = ";".join([x for x in [flags, "high_unique_label_ratio_with_single_cell_or_well_terms"] if x])
    return single_cell_like, well_uniform, hit_count, flags


def choose_score(row: dict) -> tuple[float, str, str, str, str]:
    score = 0.0
    reasons = []

    n_rows = int_value(row["n_rows"])
    n_need = int_value(row["n_rows_needing_ai"])
    n_pert = int_value(row["n_rows_with_perturbation_evidence"])
    n_ctrl = int_value(row["n_rows_with_control_evidence"])
    pdf_count = int_value(row["paper_pdf_count"])
    single_cell_like = boolish(row["single_cell_like"])
    well_uniform = boolish(row["well_or_single_cell_uniform"])

    if pdf_count > 0:
        score += 30
        reasons.append("local_pdf_available")
    else:
        score -= 20
        reasons.append("no_local_pdf")

    if n_need:
        score += min(30, 5 + n_need * 0.15)
        reasons.append("rows_need_ai")

    if n_pert:
        score += min(20, 5 + n_pert * 0.2)
        reasons.append("perturbation_evidence")

    if n_ctrl:
        score += min(15, 4 + n_ctrl * 0.15)
        reasons.append("control_evidence")
    elif n_pert:
        score += 8
        reasons.append("perturbation_without_control_signal")

    if n_rows >= 100:
        score += 5
        reasons.append("large_packet")

    if single_cell_like:
        score -= 25
        reasons.append("single_cell_or_well_terms")

    if well_uniform:
        score -= 75
        reasons.append("well_or_single_cell_uniform")

    if well_uniform:
        tier = "skip_single_cell_well_uniform"
        action = "skip_or_low_priority"
        curator = "low_random_qc"
    elif score >= 55:
        tier = "high"
        action = "run_ai_first"
        curator = "high"
    elif score >= 30:
        tier = "medium"
        action = "run_ai_pilot"
        curator = "medium"
    elif score >= 10:
        tier = "low"
        action = "optional_later"
        curator = "low"
    else:
        tier = "defer"
        action = "defer_until_paper_or_manual_review"
        curator = "low"

    return round(score, 2), tier, action, curator, ";".join(reasons)


def build_row(row: pd.Series, g: pd.DataFrame, papers_dir: Path) -> dict:
    out = {c: clean(row.get(c, "")) for c in OUTPUT_COLUMNS}

    if g.empty:
        g = pd.DataFrame()

    pdfs = find_pdf_candidates(papers_dir, out["pmid"], out["paper_pdf_candidates"])

    if g.empty:
        n_rows = int_value(out["n_rows"])
        n_runs = int_value(out["n_runs"])
        n_biosamples = int_value(out["n_biosamples"])
        n_need = int_value(out["n_rows_needing_ai"])
        n_stage = int_value(out["n_rows_with_stage_evidence"])
        n_pert = int_value(out["n_rows_with_perturbation_evidence"])
        n_ctrl = int_value(out["n_rows_with_control_evidence"])
        title_ratio = 0.0
        sample_ratio = 0.0
        single_like, well_uniform, single_hits, single_flags = False, False, 0, ""
    else:
        n_rows = len(g)
        n_runs = g["Run"].map(clean).astype(bool).sum() if "Run" in g.columns else int_value(out["n_runs"])
        n_biosamples = g["BioSample"].map(clean).nunique() if "BioSample" in g.columns else int_value(out["n_biosamples"])
        n_need = g["needs_ai"].map(boolish).sum() if "needs_ai" in g.columns else int_value(out["n_rows_needing_ai"])
        n_stage = g["has_stage_evidence"].map(boolish).sum() if "has_stage_evidence" in g.columns else int_value(out["n_rows_with_stage_evidence"])
        n_pert = g["detected_perturbation_terms"].map(clean).astype(bool).sum() if "detected_perturbation_terms" in g.columns else int_value(out["n_rows_with_perturbation_evidence"])
        n_ctrl = g["detected_control_terms"].map(clean).astype(bool).sum() if "detected_control_terms" in g.columns else int_value(out["n_rows_with_control_evidence"])
        title_ratio = ratio_unique(g["biosample_title"]) if "biosample_title" in g.columns else 0.0
        sample_ratio = ratio_unique(g["SampleName"]) if "SampleName" in g.columns else 0.0
        single_like, well_uniform, single_hits, single_flags = single_cell_flags(g)

    out.update({
        "n_rows": str(n_rows),
        "n_runs": str(n_runs),
        "n_biosamples": str(n_biosamples),
        "n_rows_needing_ai": str(n_need),
        "n_rows_with_stage_evidence": str(n_stage),
        "n_rows_with_perturbation_evidence": str(n_pert),
        "n_rows_with_control_evidence": str(n_ctrl),
        "paper_pdf_count": str(len(pdfs)),
        "paper_pdf_candidates": ";".join(pdfs),
        "single_cell_like": "yes" if single_like else "no",
        "well_or_single_cell_uniform": "yes" if well_uniform else "no",
        "single_cell_pattern_hits": str(single_hits),
        "unique_biosample_title_ratio": str(title_ratio),
        "unique_sample_name_ratio": str(sample_ratio),
        "single_cell_detection_flags": single_flags,
    })

    score, tier, action, curator, reasons = choose_score(out)
    out.update({
        "ai_priority_score": str(score),
        "ai_priority_tier": tier,
        "recommended_action": action,
        "curator_review_priority": curator,
        "priority_reasons": reasons,
    })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-index", type=Path, default=DEFAULT_PACKET_INDEX)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--papers-dir", type=Path, default=DEFAULT_PAPERS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.packet_index.exists():
        raise FileNotFoundError(f"Missing paper packet index: {args.packet_index}")

    idx = pd.read_csv(args.packet_index, sep="\t", dtype=str).fillna("")
    evidence = pd.DataFrame()
    if args.evidence.exists():
        evidence = pd.read_csv(args.evidence, sep="\t", dtype=str).fillna("")

    rows = []
    for _, r in idx.iterrows():
        g = packet_evidence(r)
        if g.empty and not evidence.empty:
            g = fallback_evidence(evidence, r.get("pmid", ""), r.get("bioproject", ""))
        rows.append(build_row(r, g, args.papers_dir))

    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    out["_sort_score"] = pd.to_numeric(out["ai_priority_score"], errors="coerce").fillna(0)
    out = out.sort_values(["_sort_score", "n_rows"], ascending=[False, False]).drop(columns=["_sort_score"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, sep="\t", index=False)

    print(f"Wrote paper packet AI priority queue: {args.out}")
    print(f"Rows: {len(out)}")
    if not args.papers_dir.exists():
        print(f"WARNING: papers directory not found: {args.papers_dir}")


if __name__ == "__main__":
    main()
