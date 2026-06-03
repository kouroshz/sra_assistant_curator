#!/usr/bin/env python3
"""
Rebuild sample_map deterministically from rowwise_suggestions for one AI curation JSON.

Use when validator reports:
  sample_map_missing_source_row_id
  sample_map_duplicate_source_row_id

This does not change rowwise_suggestions. It only rebuilds sample_map so that
each rowwise source_row_id appears exactly once in sample_map.
"""

from __future__ import annotations

import argparse
import json
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

    if not ai_json.exists():
        raise FileNotFoundError(ai_json)
    if not packet_tsv.exists():
        raise FileNotFoundError(packet_tsv)

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

    grouped = defaultdict(list)
    for r in rowwise:
        cid = clean(r.get("sample_class_id", "")) or "unknown_sample_class"
        grouped[cid].append(r)

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

        warning_flags = ["sample_map_rebuilt_deterministically_from_rowwise_suggestions"]
        if review_priority_from_rows(rows) == "high":
            warning_flags.append("contains_low_confidence_or_curator_check_rows")

        new_sample_map.append({
            "sample_class_id": cid,
            "sample_class_description": f"Deterministically rebuilt from rowwise_suggestions for class {cid}.",
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
        f"sample_map was deterministically rebuilt from rowwise_suggestions; "
        f"old_sample_map_entries={len(old_sample_map)}, new_sample_map_entries={len(new_sample_map)}."
    )
    obj["global_warnings"] = list(dict.fromkeys(warnings))

    obj["sample_map_rebuild_audit"] = {
        "source_ai_json": str(ai_json),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "reason": "Validator reported missing/duplicate sample_map source_row_id values, while rowwise_suggestions covered all packet rows exactly once.",
        "n_packet_rows": len(packet_ids),
        "n_rowwise_suggestions": len(rowwise),
        "old_sample_map_entries": len(old_sample_map),
        "new_sample_map_entries": len(new_sample_map),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ai_json.parent / f"{packet_id}.ai_curation_samplemap_rebuilt.{stamp}.json"
    out.write_text(json.dumps(obj, indent=2))

    print("Input AI:", ai_json)
    print("Output AI:", out)
    print("Packet rows:", len(packet_ids))
    print("Rowwise suggestions:", len(rowwise))
    print("Old sample_map entries:", len(old_sample_map))
    print("New sample_map entries:", len(new_sample_map))


if __name__ == "__main__":
    main()
