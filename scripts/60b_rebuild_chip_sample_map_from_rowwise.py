#!/usr/bin/env python3
"""
Deterministically rebuild ChIP sample_map from rowwise_suggestions.

Use only when:
  - rowwise_suggestions cover every source_row_id exactly once
  - sample_map has duplicate/missing source_row_ids
  - rowwise_suggestions are otherwise structurally valid

This preserves the AI rowwise calls as the source of truth and rebuilds sample_map
as a true partition of the packet table.

Outputs a repaired AI JSON with suffix:
  .ai_curation_samplemap_rebuilt.<timestamp>.json
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import argparse
import json
import pandas as pd


DEFAULT_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
DEFAULT_AI_DIR = Path("outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_actual")


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def most_common(vals, default="unknown"):
    vals = [clean(v) for v in vals if clean(v)]
    if not vals:
        return default
    return Counter(vals).most_common(1)[0][0]


def unique_join(vals, max_len=500):
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    return "; ".join(xs)[:max_len]


def find_latest_ai_json(ai_dir: Path, packet_id: str) -> Path:
    packet_dir = ai_dir / packet_id
    hits = sorted(packet_dir.glob(f"{packet_id}.ai_curation.*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        raise SystemExit(f"No AI JSON found in {packet_dir}")
    return hits[0]


def infer_ready_status(role, bg):
    role_l = clean(role).lower()
    bg_l = clean(bg).lower()
    if role_l == "target_ip":
        if bg_l and bg_l not in {"unknown", "not_applicable", "none", "na", "n/a"}:
            return "peak_calling_ready"
        return "peak_calling_not_ready"
    if role_l in {"input", "igg", "untagged_control", "mock", "control_sample"}:
        return "peak_calling_ready"
    return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--ai-json", default="")
    ap.add_argument("--ai-dir", default=str(DEFAULT_AI_DIR))
    ap.add_argument("--queue", default=str(DEFAULT_QUEUE))
    args = ap.parse_args()

    packet_id = args.packet_id
    ai_json = Path(args.ai_json) if args.ai_json else find_latest_ai_json(Path(args.ai_dir), packet_id)
    queue = pd.read_csv(args.queue, sep="\t", dtype=str).fillna("")

    qq = queue[queue["packet_id"] == packet_id]
    if qq.empty:
        raise SystemExit(f"Packet not found in queue: {packet_id}")

    table_path = Path(clean(qq.iloc[0]["packet_table"]))
    table = pd.read_csv(table_path, sep="\t", dtype=str).fillna("")

    obj = json.loads(ai_json.read_text())

    expected_ids = list(table["source_row_id"].map(clean))
    expected_set = set(expected_ids)
    run_by_id = dict(zip(table["source_row_id"].map(clean), table["Run"].map(clean)))

    rowwise = obj.get("rowwise_suggestions", [])
    rw_ids = [clean(r.get("source_row_id", "")) for r in rowwise]

    if len(rowwise) != len(expected_ids):
        raise SystemExit(f"Cannot repair: rowwise count mismatch: expected {len(expected_ids)}, observed {len(rowwise)}")

    if set(rw_ids) != expected_set:
        missing = sorted(expected_set - set(rw_ids))
        extra = sorted(set(rw_ids) - expected_set)
        raise SystemExit(f"Cannot repair: rowwise source_row_id set mismatch. missing={missing}; extra={extra}")

    dup = [sid for sid, n in Counter(rw_ids).items() if n > 1]
    if dup:
        raise SystemExit(f"Cannot repair: duplicate rowwise source_row_id values: {dup[:20]}")

    # Preserve existing sample_map metadata when class_id exists, but replace membership.
    old_sm_by_id = {
        clean(sm.get("sample_class_id", "")): sm
        for sm in obj.get("sample_map", [])
        if clean(sm.get("sample_class_id", ""))
    }

    grouped = defaultdict(list)
    for r in rowwise:
        scid = clean(r.get("sample_class_id", ""))
        if not scid:
            raise SystemExit("Cannot repair: rowwise suggestion missing sample_class_id")
        grouped[scid].append(r)

    rebuilt = []
    for scid, rows in grouped.items():
        ids = [clean(r["source_row_id"]) for r in rows]
        runs = [run_by_id.get(sid, clean(r.get("Run", ""))) for sid, r in zip(ids, rows)]

        role = most_common([r.get("suggested_sample_role", "") for r in rows])
        target = most_common([r.get("suggested_target_or_antibody_or_tag", "") for r in rows], "not_applicable_or_unknown")
        stage = most_common([r.get("suggested_stage_timepoint", "") for r in rows])
        strain = most_common([r.get("suggested_strain", "") for r in rows])
        condition = most_common([r.get("suggested_condition", "") for r in rows])
        treatment = most_common([r.get("suggested_perturbation_or_treatment", "") for r in rows], "unknown")
        bg = most_common([r.get("suggested_comparator_or_background", "") for r in rows], "unknown")
        conf = most_common([r.get("suggestion_confidence", "") for r in rows], "medium")
        flags = sorted(set(clean(r.get("review_flag", "")) for r in rows if clean(r.get("review_flag", "")) and clean(r.get("review_flag", "")) != "ok"))

        sm = dict(old_sm_by_id.get(scid, {}))
        sm["sample_class_id"] = scid
        sm["sample_class_description"] = sm.get(
            "sample_class_description",
            f"{role} sample class for target={target}, stage={stage}, strain={strain}, condition={condition}"
        )
        sm["matched_source_row_ids"] = ids
        sm["matched_run_ids"] = runs
        sm["n_rows_matched"] = len(ids)
        sm["assay_type"] = sm.get("assay_type", "ChIP-like target enrichment")
        sm["strain"] = strain
        sm["stage_or_timepoint"] = stage
        sm["condition"] = condition
        sm["perturbation_or_treatment"] = treatment
        sm["target_or_antibody_or_tag"] = target
        sm["replicate_logic"] = sm.get("replicate_logic", "biological or technical replicates inferred from rowwise runs")
        sm["sample_role"] = role
        sm["suggested_comparator_or_background_class_id"] = bg
        sm["analysis_ready_status"] = infer_ready_status(role, bg)
        sm["blocker_reason"] = "none" if sm["analysis_ready_status"] == "peak_calling_ready" else "missing_or_unclear_background"
        sm["confidence"] = conf
        sm["evidence"] = unique_join([r.get("suggestion_evidence", "") for r in rows], 700)
        sm["curator_check_priority"] = "high" if flags else sm.get("curator_check_priority", "medium")
        sm["warning_flags"] = flags

        rebuilt.append(sm)

    obj["sample_map"] = rebuilt
    obj.setdefault("global_warnings", [])
    obj["global_warnings"].append(
        "sample_map was deterministically rebuilt from rowwise_suggestions after validation found duplicate sample_map source_row_ids; rowwise_suggestions were complete and unique."
    )

    obj.setdefault("repair_audit", [])
    obj["repair_audit"].append({
        "repair_type": "rebuild_sample_map_from_rowwise_suggestions",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_ai_json": str(ai_json),
        "packet_table": str(table_path),
        "reason": "sample_map_duplicate_source_row_id",
        "rowwise_suggestions_complete_unique": True,
        "n_sample_map_entries_before": len(old_sm_by_id),
        "n_sample_map_entries_after": len(rebuilt),
        "n_rows": len(expected_ids),
    })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = ai_json.name

    # Robust output naming. Do not overwrite inputs with nonstandard filenames
    # such as ai_curation_rowwise_role_patched.*.json.
    if ".ai_curation_samplemap_rebuilt." in name:
        out_name = name.replace(".json", f".rerun_{ts}.json")
    elif ".ai_curation." in name:
        out_name = name.replace(".ai_curation.", ".ai_curation_samplemap_rebuilt.")
    else:
        out_name = name.replace(".json", f".samplemap_rebuilt.{ts}.json")

    out = ai_json.with_name(out_name)
    out.write_text(json.dumps(obj, indent=2))

    print("Wrote repaired JSON:", out)
    print("sample_map entries before:", len(old_sm_by_id))
    print("sample_map entries after:", len(rebuilt))
    print("rows covered:", sum(len(sm["matched_source_row_ids"]) for sm in rebuilt))


if __name__ == "__main__":
    main()
