#!/usr/bin/env python3

"""
Rank paper/BioProject packets for optional agentic AI curation.

This script does NOT call an API.

It creates a priority queue that:
  - prioritizes packets where paper-reading AI is likely useful
  - flags well-based / single-cell uniform packets as low-value or skip
  - gives human curators a ranked review list
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


DEFAULT_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv")
DEFAULT_OUT = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/paper_packet_ai_priority_summary.tsv")


SINGLE_CELL_PATTERNS = [
    r"\bsinglecell\b",
    r"\bsingle[-_ ]cell\b",
    r"\bscRNA\b",
    r"\bwell\b",
    r"\bplate\b",
    r"\bcell_\d+\b",
    r"\bsinglecell_\d+\b",
]


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def detect_single_cell_like(packet: dict, table_path: Path) -> dict:
    """
    Detect packets where many rows are individual single-cell/well records.
    These are often low-value for paper-reading AI if biology is uniform.
    """
    flags = []
    evidence_hits = 0
    total_checked = 0
    unique_title_ratio = None
    unique_sample_ratio = None

    text_parts = []

    # JSON-level sample label groups.
    for group in packet.get("sample_label_groups", [])[:200]:
        text_parts.append(str(group.get("sample_signature", "")))
        for counts in group.get("evidence_counts", {}).values():
            for d in counts[:20]:
                text_parts.append(str(d.get("value", "")))

    # Sidecar table, focused columns.
    if table_path.exists():
        try:
            x = pd.read_csv(table_path, sep="\t", dtype=str)
            n = len(x)

            for col in ["biosample_title", "sra_SampleName", "SampleName", "sra_LibraryName", "LibraryName"]:
                if col in x.columns:
                    vals = [clean(v) for v in x[col] if clean(v)]
                    total_checked += len(vals)
                    text_parts.extend(vals[:500])

            if n > 0 and "biosample_title" in x.columns:
                unique_title_ratio = x["biosample_title"].map(clean).replace("", pd.NA).nunique(dropna=True) / n
            if n > 0 and "sra_SampleName" in x.columns:
                unique_sample_ratio = x["sra_SampleName"].map(clean).replace("", pd.NA).nunique(dropna=True) / n

        except Exception as e:
            flags.append(f"sidecar_read_error:{type(e).__name__}:{e}")

    combined = " ".join(text_parts)

    for pat in SINGLE_CELL_PATTERNS:
        hits = len(re.findall(pat, combined, flags=re.IGNORECASE))
        evidence_hits += hits

    is_single_cell_like = evidence_hits > 0
    is_well_uniform = False

    # Strong single-cell/well signature: many rows, mostly unique sample names/titles,
    # and singlecell/well text appears.
    n_rows = int(packet.get("unit", {}).get("n_rows", 0) or 0)
    if is_single_cell_like and n_rows >= 50:
        if (unique_title_ratio is not None and unique_title_ratio >= 0.8) or (
            unique_sample_ratio is not None and unique_sample_ratio >= 0.8
        ):
            is_well_uniform = True

    return {
        "single_cell_like": is_single_cell_like,
        "well_or_single_cell_uniform": is_well_uniform,
        "single_cell_pattern_hits": evidence_hits,
        "unique_biosample_title_ratio": unique_title_ratio,
        "unique_sample_name_ratio": unique_sample_ratio,
        "single_cell_detection_flags": ";".join(flags),
    }


def classify_and_score(row: pd.Series, packet: dict, single: dict) -> dict:
    n_rows = int(row.get("n_rows", 0) or 0)
    n_need = int(row.get("n_rows_needing_ai", 0) or 0)
    n_stage = int(row.get("n_rows_with_stage_evidence", 0) or 0)
    n_pert = int(row.get("n_rows_with_perturbation_evidence", 0) or 0)
    n_ctrl = int(row.get("n_rows_with_control_evidence", 0) or 0)
    has_pdf = int(row.get("paper_pdf_count", 0) or 0) > 0

    reasons = []

    score = 0

    if has_pdf:
        score += 30
        reasons.append("pdf_available")
    else:
        score -= 20
        reasons.append("no_pdf")

    # More rows needing AI means more potential payoff, but cap it.
    score += min(30, n_need / 10)
    if n_need > 0:
        reasons.append(f"{n_need}_rows_need_ai")

    # AI is particularly useful when condition/control logic is missing or mixed.
    if n_rows > 0:
        frac_need = n_need / n_rows
        frac_pert = n_pert / n_rows
        frac_ctrl = n_ctrl / n_rows
        frac_stage = n_stage / n_rows
    else:
        frac_need = frac_pert = frac_ctrl = frac_stage = 0

    if frac_need >= 0.75:
        score += 10
        reasons.append("most_rows_need_ai")
    if frac_pert > 0 and frac_pert < 1:
        score += 8
        reasons.append("mixed_perturbation_evidence")
    if frac_ctrl > 0 and frac_ctrl < 1:
        score += 8
        reasons.append("mixed_control_evidence")
    if frac_stage > 0 and frac_stage < 1:
        score += 5
        reasons.append("mixed_stage_evidence")

    # Large single-cell/well uniform packets are usually poor API value:
    # many rows, repeated biology, individual-cell labels.
    action = "run_ai"
    tier = "medium"

    if single["well_or_single_cell_uniform"]:
        score -= 50
        reasons.append("well_based_or_single_cell_uniform_low_api_value")
        action = "skip_or_low_priority"
        tier = "skip_single_cell_well_uniform"

    # If no PDF and no perturb/control signal, deprioritize.
    if not has_pdf and n_pert == 0 and n_ctrl == 0:
        score -= 15
        reasons.append("no_pdf_and_no_condition_control_signal")

    # If the packet is small and has no PDF, likely not worth first-pass AI.
    if not has_pdf and n_rows <= 5:
        score -= 10
        reasons.append("small_no_pdf_packet")

    if action != "skip_or_low_priority":
        if score >= 55:
            tier = "high"
            action = "run_ai"
        elif score >= 30:
            tier = "medium"
            action = "run_ai"
        elif score >= 10:
            tier = "low"
            action = "optional_low_priority_ai"
        else:
            tier = "defer"
            action = "defer"

    # Human curator priority is not identical to AI priority.
    if tier == "high":
        curator_priority = "high"
    elif tier == "skip_single_cell_well_uniform":
        curator_priority = "low_random_qc"
    elif n_ctrl > 0 or n_pert > 0:
        curator_priority = "medium"
    else:
        curator_priority = "low"

    return {
        "ai_priority_score": round(float(score), 2),
        "ai_priority_tier": tier,
        "recommended_action": action,
        "curator_review_priority": curator_priority,
        "priority_reasons": ";".join(reasons),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    if not args.index.exists():
        raise FileNotFoundError(f"Missing paper packet index: {args.index}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    idx = pd.read_csv(args.index, sep="\t", dtype=str)

    rows = []
    for _, row in idx.iterrows():
        packet_json = Path(clean(row.get("packet_json", "")))
        table_path = Path(clean(row.get("rowwise_evidence_tsv", "")))

        packet = {}
        if packet_json.exists():
            try:
                packet = json.loads(packet_json.read_text())
            except Exception as e:
                packet = {"packet_load_error": f"{type(e).__name__}:{e}"}

        single = detect_single_cell_like(packet, table_path)
        rank = classify_and_score(row, packet, single)

        outrow = row.to_dict()
        outrow.update(single)
        outrow.update(rank)
        rows.append(outrow)

    out = pd.DataFrame(rows)

    sort_cols = ["recommended_action", "ai_priority_score", "n_rows"]
    out = out.sort_values(
        by=["recommended_action", "ai_priority_score", "n_rows"],
        ascending=[True, False, False],
    )

    # Put run_ai before skip/defer manually by categorical order.
    order = {"run_ai": 0, "optional_low_priority_ai": 1, "skip_or_low_priority": 2, "defer": 3}
    out["_action_order"] = out["recommended_action"].map(order).fillna(9)
    out = out.sort_values(["_action_order", "ai_priority_score", "n_rows"], ascending=[True, False, False])
    out = out.drop(columns=["_action_order"])

    out.to_csv(args.out, sep="\t", index=False)

    summary = []
    summary.append({"metric": "n_packets", "value": len(out)})
    for col in ["recommended_action", "ai_priority_tier", "curator_review_priority"]:
        counts = out[col].value_counts(dropna=False)
        for k, v in counts.items():
            summary.append({"metric": f"{col}:{k}", "value": int(v)})

    summary.append({"metric": "n_single_cell_like", "value": int(out["single_cell_like"].astype(bool).sum())})
    summary.append({"metric": "n_well_or_single_cell_uniform", "value": int(out["well_or_single_cell_uniform"].astype(bool).sum())})
    summary.append({"metric": "output_priority_queue", "value": str(args.out)})

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote priority queue: {args.out}")
    print(f"Wrote summary:        {args.summary}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
