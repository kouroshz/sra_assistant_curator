#!/usr/bin/env python3
"""
Rebuild sample_map deterministically from rowwise_suggestions, but split
heterogeneous sample_class_id groups by biological rowwise fields.

Use when:
  - rowwise_suggestions cover every packet row exactly once
  - sample_map has missing/duplicate source_row_id values
  - sample_class_id may be too broad and span multiple stages/timepoints

Output:
  <packet>.ai_curation_samplemap_biokey_rebuilt.<timestamp>.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd


AI_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
PACKET_TABLE_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")


def clean(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def safe_token(x: str, max_len: int = 40) -> str:
    s = clean(x).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:max_len].strip("_") or "unknown")


def most_common(values, default="unknown"):
    vals = [clean(v) for v in values if clean(v)]
    if not vals:
        return default
    return Counter(vals).most_common(1)[0][0]


def confidence_from_rows(rows):
    vals = [clean(r.get("suggestion_confidence", "")).lower() for r in rows]
    vals = [v for v in vals if v]
    if not vals:
        return "medium"
    if all(v == "high" for v in vals):
        return "high"
    if any(v == "low" for v in vals):
        return "low"
    return "medium"


def review_priority_from_rows(rows):
    flags = [clean(r.get("review_flag", "")).lower() for r in rows]
    conf = [clean(r.get("suggestion_confidence", "")).lower() for r in rows]
    if any(f and f != "ok" for f in flags) or any(c == "low" for c in conf):
        return "high"
    return "low"


def bio_tuple(r):
    return (
        clean(r.get("suggested_strain", "")),
        clean(r.get("suggested_stage_timepoint", "")),
        clean(r.get("suggested_condition", "")),
        clean(r.get("suggested_perturbation_or_treatment", "")),
        clean(r.get("suggested_sample_role", "")),
        clean(r.get("suggested_comparator_or_background", "")),
    )


def find_latest_ai(packet_id: str) -> Path:
    folder = AI_DIR / packet_id
    files = sorted(
        folder.glob(f"{packet_id}.ai_curation*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        raise FileNotFoundError(f"No AI curation JSONs found in {folder}")
    return files[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--ai-json", type=Path, default=None)
    args = ap.parse_args()

    packet_id = args.packet_id
    ai_json = args.ai_json or find_latest_ai(packet_id)
    packet_tsv = PACKET_TABLE_DIR / f"{packet_id}.rowwise_evidence.tsv"

    obj = json.loads(ai_json.read_text())
    pkt = pd.read_csv(packet_tsv, sep="\t", dtype=str).fillna("")

    packet_ids = set(pkt["source_row_id"])
    rowwise = obj.get("rowwise_suggestions", []) or []

    rw_ids = [clean(r.get("source_row_id", "")) for r in rowwise]
    rw_ids_set = set(rw_ids)

    missing_from_rowwise = packet_ids - rw_ids_set
    extra_in_rowwise = rw_ids_set - packet_ids
    duplicate_rowwise = [sid for sid, n in Counter(rw_ids).items() if sid and n > 1]

    if missing_from_rowwise or extra_in_rowwise or duplicate_rowwise:
        raise SystemExit(
            "Cannot rebuild sample_map safely because rowwise_suggestions are not exactly one-to-one with packet rows.\n"
            f"missing_from_rowwise={len(missing_from_rowwise)} "
            f"extra_in_rowwise={len(extra_in_rowwise)} "
            f"duplicate_rowwise={len(duplicate_rowwise)}"
        )

    original_groups = defaultdict(list)
    for r in rowwise:
        base = clean(r.get("sample_class_id", "")) or "unknown_sample_class"
        original_groups[base].append(r)

    heterogeneous_classes = {}
    for base, rows in original_groups.items():
        tuples = sorted(set(bio_tuple(r) for r in rows))
        if len(tuples) > 1:
            heterogeneous_classes[base] = tuples

    grouped = defaultdict(list)
    original_to_rebuilt = {}

    for r in rowwise:
        base = clean(r.get("sample_class_id", "")) or "unknown_sample_class"

        if base in heterogeneous_classes:
            strain, stage, condition, perturb, role, comparator = bio_tuple(r)
            new_cid = "__".join([
                safe_token(base),
                safe_token(strain),
                safe_token(stage),
                safe_token(condition),
                safe_token(perturb),
                safe_token(role),
            ])
        else:
            new_cid = base

        grouped[new_cid].append(r)
        original_to_rebuilt.setdefault(base, set()).add(new_cid)

    new_sample_map = []

    for cid, rows in sorted(grouped.items()):
        source_ids = [clean(r.get("source_row_id", "")) for r in rows]
        runs = [clean(r.get("Run", "")) for r in rows]

        evidence_parts = []
        for r in rows:
            ev = clean(r.get("suggestion_evidence", ""))
            if ev and ev not in evidence_parts:
                evidence_parts.append(ev)
            if len(evidence_parts) >= 4:
                break

        warning_flags = ["sample_map_rebuilt_deterministically_from_rowwise_biokey"]
        original_class_ids = sorted(set(clean(r.get("sample_class_id", "")) for r in rows if clean(r.get("sample_class_id", ""))))

        if any(base in heterogeneous_classes for base in original_class_ids):
            warning_flags.append("original_sample_class_split_by_biological_fields")

        if review_priority_from_rows(rows) == "high":
            warning_flags.append("contains_low_confidence_or_curator_check_rows")

        new_sample_map.append({
            "sample_class_id": cid,
            "sample_class_description": (
                "Deterministically rebuilt from rowwise_suggestions using biological key "
                "(strain, stage/timepoint, condition, perturbation, role). "
                f"Original AI class IDs: {';'.join(original_class_ids)}"
            ),
            "matched_source_row_ids": source_ids,
            "matched_run_ids": runs,
            "n_rows_matched": len(source_ids),
            "assay_type": most_common([r.get("suggested_assay_type", "") for r in rows], "RNA-Seq"),
            "strain": most_common([r.get("suggested_strain", "") for r in rows]),
            "stage_or_timepoint": most_common([r.get("suggested_stage_timepoint", "") for r in rows]),
            "condition": most_common([r.get("suggested_condition", "") for r in rows]),
            "perturbation_or_treatment": most_common([r.get("suggested_perturbation_or_treatment", "") for r in rows], "none"),
            "target_or_antibody_or_tag": most_common([r.get("suggested_target_or_antibody_or_tag", "") for r in rows], "not_applicable_or_unknown"),
            "replicate_logic": "derived from rowwise_suggestions; curator should review replicate structure if needed",
            "sample_role": most_common([r.get("suggested_sample_role", "") for r in rows], "expression_sample"),
            "suggested_comparator_or_background_class_id": most_common([r.get("suggested_comparator_or_background", "") for r in rows], "unknown"),
            "analysis_ready_status": "expression_ready",
            "blocker_reason": "none",
            "confidence": confidence_from_rows(rows),
            "evidence": " | ".join(evidence_parts),
            "curator_check_priority": review_priority_from_rows(rows),
            "warning_flags": warning_flags,
        })

    old_sample_map = obj.get("sample_map", []) or []
    obj["sample_map"] = new_sample_map

    warnings = obj.get("global_warnings", []) or []
    warnings.append(
        "sample_map was deterministically rebuilt from rowwise_suggestions using biological-key splitting; "
        f"old_sample_map_entries={len(old_sample_map)}, new_sample_map_entries={len(new_sample_map)}, "
        f"heterogeneous_original_sample_classes={len(heterogeneous_classes)}."
    )
    obj["global_warnings"] = list(dict.fromkeys(warnings))

    obj["sample_map_biokey_rebuild_audit"] = {
        "source_ai_json": str(ai_json),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "reason": "Validator reported sample_map missing/duplicate row IDs while rowwise_suggestions covered all packet rows exactly once.",
        "n_packet_rows": len(packet_ids),
        "n_rowwise_suggestions": len(rowwise),
        "old_sample_map_entries": len(old_sample_map),
        "new_sample_map_entries": len(new_sample_map),
        "n_original_sample_classes": len(original_groups),
        "n_heterogeneous_original_sample_classes_split": len(heterogeneous_classes),
        "heterogeneous_original_sample_classes": {
            k: [list(t) for t in v] for k, v in heterogeneous_classes.items()
        },
        "original_to_rebuilt_class_ids": {
            k: sorted(v) for k, v in original_to_rebuilt.items()
        },
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ai_json.parent / f"{packet_id}.ai_curation_samplemap_biokey_rebuilt.{stamp}.json"
    out.write_text(json.dumps(obj, indent=2))

    print("Input AI:", ai_json)
    print("Output AI:", out)
    print("Packet rows:", len(packet_ids))
    print("Rowwise suggestions:", len(rowwise))
    print("Old sample_map entries:", len(old_sample_map))
    print("New sample_map entries:", len(new_sample_map))
    print("Original sample classes:", len(original_groups))
    print("Heterogeneous original classes split:", len(heterogeneous_classes))
    if heterogeneous_classes:
        print("\nHeterogeneous classes:")
        for k, v in heterogeneous_classes.items():
            print(" -", k, "=>", len(v), "biological groups")


if __name__ == "__main__":
    main()
