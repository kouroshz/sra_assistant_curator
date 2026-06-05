#!/usr/bin/env python3
"""
Production runner for small ChIP AI packets.

Default behavior is DRY-RUN. Use --execute to actually call the API.

Workflow per packet:
  1. Run scripts/39_run_agentic_ai_on_paper_packet.py
  2. Validate with scripts/60_validate_chip_ai_output.py
  3. If validation FAILs, attempt deterministic sample_map rebuild with scripts/60b...
  4. Validate repaired JSON
  5. Refresh inventory with scripts/61_inventory_chip_ai_outputs.py

This intentionally excludes chunked packets by default.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import os
import subprocess
import sys
import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for dry-run use
    load_dotenv = None


QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
INVENTORY = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_output_inventory.tsv")
VALIDATION_DIR = Path("outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation")
DEFAULT_OUTDIR = Path("outputs/06_CHIP_AI_ASSIST/15_chip_ai_batch_small_actual")
BATCH_BASE = Path("outputs/06_CHIP_AI_ASSIST/15_chip_ai_batch_runs")


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def run_cmd(cmd, execute=True):
    print("+", " ".join(str(x) for x in cmd), flush=True)
    if execute:
        return subprocess.run(cmd, check=False)
    return None


def read_validation_status(packet_id: str) -> str:
    p = VALIDATION_DIR / f"{packet_id}.chip_ai_validation_summary.tsv"
    if not p.exists():
        return "NO_VALIDATION"
    df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
    if df.empty:
        return "NO_VALIDATION_EMPTY"
    return clean(df.loc[0, "validation_status"])


def latest_repaired_json(outdir: Path, packet_id: str) -> str:
    packet_dir = outdir / packet_id
    hits = sorted(
        packet_dir.glob(f"{packet_id}.ai_curation_samplemap_rebuilt.*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return str(hits[0]) if hits else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(QUEUE))
    ap.add_argument("--inventory", default=str(INVENTORY))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--priority", default="", help="Optional priority filter: high, medium")
    ap.add_argument("--include-chunked", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--max-pdf-chars", type=int, default=120000)
    ap.add_argument("--max-rowwise-rows", type=int, default=250)
    ap.add_argument("--max-rowwise-chars", type=int, default=100000)
    args = ap.parse_args()

    if load_dotenv is not None:
        load_dotenv(Path(".env"))

    if args.execute:
        if os.environ.get("AGENTIC_AI_ENABLE_API") != "1":
            raise SystemExit("Refusing --execute: AGENTIC_AI_ENABLE_API must be set to 1 before any batch output or API runner launch.")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("Refusing --execute: OPENAI_API_KEY is not set. The key value was not printed.")

    queue_path = Path(args.queue)
    inventory_path = Path(args.inventory)
    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not queue_path.exists():
        raise SystemExit(f"Missing queue: {queue_path}")

    q = pd.read_csv(queue_path, sep="\t", dtype=str).fillna("")

    if inventory_path.exists():
        inv = pd.read_csv(inventory_path, sep="\t", dtype=str).fillna("")
        q = q.merge(
            inv[["packet_id", "chip_ai_output_status", "validation_status"]],
            on="packet_id",
            how="left",
        )
    else:
        q["chip_ai_output_status"] = ""
        q["validation_status"] = ""

    q["chip_ai_output_status"] = q["chip_ai_output_status"].fillna("")
    q["validation_status"] = q["validation_status"].fillna("")
    q["n_rows_num"] = pd.to_numeric(q["n_rows"], errors="coerce").fillna(0).astype(int)
    q["priority_num"] = pd.to_numeric(q["priority"], errors="coerce").fillna(0)

    todo = q[q["chip_ai_output_status"] != "active_validated_pass"].copy()

    if not args.include_chunked:
        todo = todo[todo["assay_aware_recommended_action"] != "run_chip_ai_chunked"].copy()

    if args.priority:
        todo = todo[todo["assay_aware_curator_priority"] == args.priority].copy()

    todo = todo.sort_values(
        ["assay_aware_curator_priority", "priority_num", "n_rows_num"],
        ascending=[True, False, False],
    )

    if args.limit > 0:
        todo = todo.head(args.limit).copy()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = BATCH_BASE / ts
    batch_dir.mkdir(parents=True, exist_ok=True)

    selected_path = batch_dir / f"chip_batch_small_selected.{ts}.tsv"
    todo.to_csv(selected_path, sep="\t", index=False)

    print("Queue:", queue_path)
    print("Inventory:", inventory_path)
    print("Selected packets:", len(todo))
    print("Mode:", "EXECUTE" if args.execute else "DRY-RUN")
    print("Include chunked:", args.include_chunked)
    print("Priority filter:", args.priority or "<none>")
    print("Out dir:", outdir)
    print("Selected table:", selected_path)
    print()

    if todo.empty:
        return

    results = []

    for _, r in todo.iterrows():
        packet_id = clean(r["packet_id"])
        pktjson = clean(r["packet_json"])

        print()
        print("==============================")
        print("Packet:", packet_id)
        print("==============================")

        result = {
            "packet_id": packet_id,
            "n_rows": clean(r.get("n_rows", "")),
            "priority": clean(r.get("assay_aware_curator_priority", "")),
            "recommended_action": clean(r.get("assay_aware_recommended_action", "")),
            "run_status": "dry_run_only" if not args.execute else "started",
            "validation_before_repair": "",
            "repair_attempted": "false",
            "validation_after_repair": "",
            "final_status": "",
        }

        cmd_run = [
            sys.executable,
            "scripts/39_run_agentic_ai_on_paper_packet.py",
            "--packet-json", pktjson,
            "--queue", str(queue_path),
            "--out-dir", str(outdir),
            "--max-pdf-chars", str(args.max_pdf_chars),
            "--max-rowwise-rows", str(args.max_rowwise_rows),
            "--max-rowwise-chars", str(args.max_rowwise_chars),
        ]

        proc = run_cmd(cmd_run, execute=args.execute)
        if args.execute and proc.returncode != 0:
            result["run_status"] = f"ai_run_failed_returncode_{proc.returncode}"
            result["final_status"] = "FAIL_AI_RUN"
            results.append(result)
            continue

        if not args.execute:
            results.append(result)
            continue

        result["run_status"] = "ai_run_complete"

        cmd_val = [
            sys.executable,
            "scripts/60_validate_chip_ai_output.py",
            "--packet-id", packet_id,
            "--ai-dir", str(outdir),
            "--queue", str(queue_path),
        ]
        proc = run_cmd(cmd_val, execute=True)
        before = read_validation_status(packet_id)
        result["validation_before_repair"] = before

        if before == "PASS":
            result["final_status"] = "PASS"
            results.append(result)
            continue

        result["repair_attempted"] = "true"

        cmd_repair = [
            sys.executable,
            "scripts/60b_rebuild_chip_sample_map_from_rowwise.py",
            "--packet-id", packet_id,
            "--ai-dir", str(outdir),
            "--queue", str(queue_path),
        ]
        proc = run_cmd(cmd_repair, execute=True)

        if proc.returncode != 0:
            result["final_status"] = "FAIL_REPAIR"
            results.append(result)
            continue

        repaired_json = latest_repaired_json(outdir, packet_id)
        if not repaired_json:
            result["final_status"] = "FAIL_REPAIRED_JSON_MISSING"
            results.append(result)
            continue

        cmd_val_repaired = [
            sys.executable,
            "scripts/60_validate_chip_ai_output.py",
            "--packet-id", packet_id,
            "--ai-json", repaired_json,
            "--queue", str(queue_path),
        ]
        proc = run_cmd(cmd_val_repaired, execute=True)
        after = read_validation_status(packet_id)
        result["validation_after_repair"] = after
        result["final_status"] = after

        results.append(result)

    results_df = pd.DataFrame(results)
    results_path = batch_dir / f"chip_batch_small_results.{ts}.tsv"
    results_df.to_csv(results_path, sep="\t", index=False)

    print()
    print("Batch results written:", results_path)
    print(results_df.to_string(index=False))

    if args.execute:
        print()
        print("Refreshing inventory...")
        run_cmd([sys.executable, "scripts/61_inventory_chip_ai_outputs.py"], execute=True)


if __name__ == "__main__":
    main()
