#!/usr/bin/env python3
"""
Merge validated ChIP chunk AI outputs into one parent AI JSON.

This script:
  - reads chunk queue
  - chooses repaired JSON if available, otherwise raw AI JSON
  - concatenates rowwise_suggestions
  - verifies source_row_id coverage against the parent packet table
  - writes a merged parent AI JSON

After this, run:
  scripts/60b_rebuild_chip_sample_map_from_rowwise.py
then:
  scripts/60_validate_chip_ai_output.py

The sample_map should be rebuilt at parent level, not trusted from chunk-local maps.
"""

from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse
import json
import subprocess
import sys
import pandas as pd


MAIN_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
DEFAULT_CHUNK_BASE = Path("outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets")
DEFAULT_VALIDATION_DIR = Path("outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation")


def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def latest_json(chunk_outdir: Path, packet_id: str) -> Path:
    d = chunk_outdir / packet_id

    # Prefer most curated/repaired outputs first.
    patterns = [
        f"{packet_id}.ai_curation_rowwise_role_patched.*.json",
        f"{packet_id}.ai_curation_samplemap_rebuilt.*.json",
        f"{packet_id}.ai_curation.*.json",
    ]

    for pat in patterns:
        hits = sorted(
            d.glob(pat),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if hits:
            return hits[0]

    raise SystemExit(f"No AI JSON found for chunk: {packet_id}")


def infer_chunk_queue() -> Path:
    hits = sorted(DEFAULT_CHUNK_BASE.glob("*/*.chunk_queue.tsv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        raise SystemExit(
            "Missing --chunk-queue and no default chunk queue found. "
            "Run Step 34 or provide --chunk-queue."
        )
    return hits[0]


def infer_parent_packet_id(chunk_queue_path: Path, chunk_queue: pd.DataFrame) -> str:
    if "parent_packet_id" in chunk_queue.columns:
        vals = sorted(set(chunk_queue["parent_packet_id"].map(clean)) - {""})
        if len(vals) == 1:
            return vals[0]
        if len(vals) > 1:
            raise SystemExit(f"Chunk queue has multiple parent_packet_id values: {vals}")

    name = chunk_queue_path.name
    suffix = ".chunk_queue.tsv"
    if name.endswith(suffix):
        return name[:-len(suffix)]
    raise SystemExit("Missing --parent-packet-id and could not infer it from chunk queue.")


def latest_rebuilt_json(outdir: Path, parent_packet_id: str) -> Path:
    hits = sorted(
        outdir.glob(f"{parent_packet_id}.ai_curation_samplemap_rebuilt.*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not hits:
        raise SystemExit(f"Sample-map rebuild did not produce expected JSON in {outdir}")
    return hits[0]


def summarize_peak_status(statuses):
    vals = [clean(x).lower() for x in statuses if clean(x)]
    if not vals:
        return "unknown"
    if "no" in vals:
        return "partial"
    if "partial" in vals:
        return "partial"
    if all(x == "yes" for x in vals):
        return "yes"
    return "partial"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent-packet-id", default="")
    ap.add_argument("--chunk-queue", default="")
    ap.add_argument("--chunk-out-dir", default="outputs/06_CHIP_AI_ASSIST/17_chip_ai_chunk_actual")
    ap.add_argument("--main-queue", default=str(MAIN_QUEUE))
    ap.add_argument("--out-dir", default="outputs/06_CHIP_AI_ASSIST/18_chip_ai_chunk_merged")
    ap.add_argument("--validation-out-dir", default=str(DEFAULT_VALIDATION_DIR))
    ap.add_argument("--skip-repair-and-validation", action="store_true")
    args = ap.parse_args()

    chunk_queue_path = Path(args.chunk_queue) if args.chunk_queue else infer_chunk_queue()
    chunk_queue = pd.read_csv(chunk_queue_path, sep="\t", dtype=str).fillna("")
    parent_packet_id = clean(args.parent_packet_id) or infer_parent_packet_id(chunk_queue_path, chunk_queue)
    main_queue = pd.read_csv(args.main_queue, sep="\t", dtype=str).fillna("")
    chunk_outdir = Path(args.chunk_out_dir)
    outdir = Path(args.out_dir) / parent_packet_id
    outdir.mkdir(parents=True, exist_ok=True)

    parent_row = main_queue[main_queue["packet_id"] == parent_packet_id]
    if parent_row.empty:
        raise SystemExit(f"Parent packet not found in main queue: {parent_packet_id}")

    parent_table_path = Path(clean(parent_row.iloc[0]["packet_table"]))
    parent_table = pd.read_csv(parent_table_path, sep="\t", dtype=str).fillna("")
    expected_ids = set(parent_table["source_row_id"].map(clean))

    all_rowwise = []
    chunk_summaries = []
    global_warnings = []
    peak_statuses = []
    active_chunk_jsons = []

    first_obj = None

    for _, r in chunk_queue.iterrows():
        chunk_id = clean(r["packet_id"])
        p = latest_json(chunk_outdir, chunk_id)
        active_chunk_jsons.append(str(p))

        obj = json.loads(p.read_text())
        if first_obj is None:
            first_obj = obj

        rowwise = obj.get("rowwise_suggestions", []) or []
        all_rowwise.extend(rowwise)

        ar = obj.get("analysis_readiness", {}) or {}
        peak_statuses.append(ar.get("chip_peak_calling_ready", ""))

        chunk_summaries.append({
            "chunk_packet_id": chunk_id,
            "active_chunk_json": str(p),
            "n_rowwise_suggestions": len(rowwise),
            "chip_peak_calling_ready": ar.get("chip_peak_calling_ready", ""),
            "main_blockers": ar.get("main_blockers", []),
        })

        for w in obj.get("global_warnings", []) or []:
            if w not in global_warnings:
                global_warnings.append(w)

    if first_obj is None:
        raise SystemExit("No chunk objects loaded.")

    rw_ids = [clean(r.get("source_row_id", "")) for r in all_rowwise]
    rw_set = set(rw_ids)

    missing = sorted(expected_ids - rw_set)
    extra = sorted(rw_set - expected_ids)
    dup = sorted([sid for sid, n in Counter(rw_ids).items() if sid and n > 1])

    if missing or extra or dup:
        print("missing:", missing[:20])
        print("extra:", extra[:20])
        print("duplicates:", dup[:20])
        raise SystemExit("Merged rowwise_suggestions are not a clean parent partition.")

    merged = dict(first_obj)
    merged["packet_id"] = parent_packet_id
    merged["merged_from_chunked_outputs"] = True
    merged["rowwise_suggestions"] = all_rowwise

    # sample_map from chunks is intentionally discarded; rebuild globally next.
    merged["sample_map"] = []
    merged["global_warnings"] = global_warnings + [
        "This JSON was merged from chunk-level ChIP AI outputs. sample_map was intentionally cleared and must be rebuilt deterministically from merged rowwise_suggestions."
    ]

    merged["chunk_merge_audit"] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "parent_packet_id": parent_packet_id,
        "chunk_queue": str(chunk_queue_path),
        "chunk_out_dir": str(chunk_outdir),
        "parent_table": str(parent_table_path),
        "active_chunk_jsons": active_chunk_jsons,
        "n_chunks": len(chunk_queue),
        "expected_parent_rows": len(expected_ids),
        "merged_rowwise_suggestions": len(all_rowwise),
        "unique_source_row_ids": len(rw_set),
        "missing_source_row_ids": 0,
        "extra_source_row_ids": 0,
        "duplicate_source_row_ids": 0,
        "chunk_summaries": chunk_summaries,
    }

    merged["analysis_readiness"] = {
        "chip_peak_calling_ready": summarize_peak_status(peak_statuses),
        "main_blockers": [],
        "chunk_level_peak_statuses": peak_statuses,
        "note": "Merged from chunk-level outputs; parent-level sample_map rebuilt deterministically in next step."
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = outdir / f"{parent_packet_id}.ai_curation.chunk_merged.{ts}.json"
    out_json.write_text(json.dumps(merged, indent=2))

    summary = pd.DataFrame([{
        "parent_packet_id": parent_packet_id,
        "n_chunks": len(chunk_queue),
        "expected_parent_rows": len(expected_ids),
        "merged_rowwise_suggestions": len(all_rowwise),
        "unique_source_row_ids": len(rw_set),
        "chip_peak_calling_ready": merged["analysis_readiness"]["chip_peak_calling_ready"],
        "merged_json": str(out_json),
    }])

    summary_path = outdir / f"{parent_packet_id}.chunk_merge_summary.tsv"
    summary.to_csv(summary_path, sep="\t", index=False)

    print("Wrote merged JSON:", out_json)
    print("Wrote summary:", summary_path)
    print()
    print(summary.to_string(index=False))

    if args.skip_repair_and_validation:
        return

    rebuild_cmd = [
        sys.executable,
        "scripts/60b_rebuild_chip_sample_map_from_rowwise.py",
        "--packet-id",
        parent_packet_id,
        "--ai-json",
        str(out_json),
        "--queue",
        args.main_queue,
    ]
    print()
    print("Rebuilding parent sample_map:")
    print("  " + " ".join(rebuild_cmd))
    subprocess.run(rebuild_cmd, check=True)

    repaired_json = latest_rebuilt_json(outdir, parent_packet_id)
    validate_cmd = [
        sys.executable,
        "scripts/60_validate_chip_ai_output.py",
        "--packet-id",
        parent_packet_id,
        "--ai-json",
        str(repaired_json),
        "--queue",
        args.main_queue,
        "--out-dir",
        args.validation_out_dir,
    ]
    print()
    print("Validating repaired parent JSON:")
    print("  " + " ".join(validate_cmd))
    subprocess.run(validate_cmd, check=True)


if __name__ == "__main__":
    main()
