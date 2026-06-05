#!/usr/bin/env python3
"""
Production-safe trusted RNA AI batch runner.

Key production rules:
  - Default actionable classes: run_ai_first, run_ai_pilot, run_ai.
  - Excludes PASS packets unless --force is used.
  - Applies --limit AFTER filtering already-PASS packets.
  - Dry-run by default. Use --execute to actually run API calls.
  - Uses chunked runner for packets with n_rows > --large-threshold.
  - Keeps defer / skip_or_low_priority out unless explicitly included.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for dry-run use
    load_dotenv = None


QUEUE_DEFAULT = Path("outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv")
INV_DEFAULT = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_packet_status_inventory.tsv")
OUT_BASE = Path("outputs/04_AGENTIC_AI_ASSIST/batch_runs_production")


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def parse_csv_arg(x: str) -> set[str]:
    return {v.strip() for v in str(x).split(",") if v.strip()}


def latest_validation(packet_id: str) -> dict:
    val_dir = Path("outputs/04_AGENTIC_AI_ASSIST/validation")
    files = sorted(val_dir.glob(f"{packet_id}*validation_summary.tsv"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {
            "post_validation_status": "NO_VALIDATION",
            "post_n_fail": "",
            "post_n_warn": "",
            "post_validation_summary": "",
        }

    p = files[-1]
    try:
        df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
        d = dict(zip(df["metric"], df["value"]))
        return {
            "post_validation_status": d.get("validation_status", "UNKNOWN"),
            "post_n_fail": d.get("n_fail", ""),
            "post_n_warn": d.get("n_warn", ""),
            "post_validation_summary": str(p),
        }
    except Exception as e:
        return {
            "post_validation_status": "SUMMARY_READ_ERROR",
            "post_n_fail": "",
            "post_n_warn": "",
            "post_validation_summary": str(p),
            "error_message": str(e),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, default=QUEUE_DEFAULT)
    ap.add_argument("--inventory", type=Path, default=INV_DEFAULT)
    ap.add_argument("--include-actions", default="run_ai_first,run_ai_pilot,run_ai")
    ap.add_argument("--packet-id", action="append", default=[], help="Run/select specific packet_id. Can be repeated.")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--large-threshold", type=int, default=100)
    ap.add_argument("--chunk-size", type=int, default=60)
    ap.add_argument("--execute", action="store_true", help="Actually run API calls. Default is dry-run.")
    ap.add_argument("--force", action="store_true", help="Include/rerun PASS packets.")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    if load_dotenv is not None:
        load_dotenv(Path(".env"))

    if args.execute:
        if os.environ.get("AGENTIC_AI_ENABLE_API") != "1":
            raise SystemExit("Refusing --execute: AGENTIC_AI_ENABLE_API must be set to 1 before any packet selection or API runner launch.")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("Refusing --execute: OPENAI_API_KEY is not set. The key value was not printed.")

    queue = read_tsv(args.queue)
    if queue.empty:
        raise SystemExit(f"Missing or empty queue: {args.queue}")

    inv = read_tsv(args.inventory)
    if inv.empty:
        inv = pd.DataFrame({"packet_id": [], "latest_validation_status": []})

    if "packet_id" not in queue.columns:
        raise SystemExit("Queue is missing packet_id column.")

    queue = queue.copy()
    queue["_queue_order"] = range(len(queue))

    keep_cols = [c for c in ["packet_id", "latest_validation_status"] if c in inv.columns]
    if keep_cols:
        df = queue.merge(inv[keep_cols], on="packet_id", how="left")
    else:
        df = queue.copy()
        df["latest_validation_status"] = "NO_VALIDATION"

    df["latest_validation_status"] = (
        df["latest_validation_status"]
        .replace("", "NO_VALIDATION")
        .fillna("NO_VALIDATION")
    )

    if "recommended_action" not in df.columns:
        df["recommended_action"] = ""

    if "n_rows" not in df.columns:
        df["n_rows"] = "0"
    df["n_rows_num"] = pd.to_numeric(df["n_rows"], errors="coerce").fillna(0).astype(int)

    include_actions = parse_csv_arg(args.include_actions)

    if args.packet_id:
        selected = df[df["packet_id"].isin(args.packet_id)].copy()
    else:
        selected = df[df["recommended_action"].isin(include_actions)].copy()
        if not args.force:
            selected = selected[selected["latest_validation_status"] != "PASS"].copy()
        selected = selected.sort_values("_queue_order").head(args.limit)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = OUT_BASE / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    print(f"Queue: {args.queue}")
    print(f"Inventory: {args.inventory}")
    print(f"Selected packets: {len(selected)}")
    print(f"Batch dir: {batch_dir}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"Included actions: {','.join(sorted(include_actions))}")
    print(f"Large threshold: n_rows > {args.large_threshold}")
    print(f"Chunk size: {args.chunk_size}")

    for i, (_, r) in enumerate(selected.iterrows(), start=1):
        packet = r["packet_id"]
        n_rows = int(r["n_rows_num"])
        method = "chunked_41c" if n_rows > args.large_threshold else "one_shot_41"

        row = {
            "batch_timestamp": stamp,
            "batch_index": i,
            "packet_id": packet,
            "pmid": r.get("pmid", ""),
            "bioproject": r.get("bioproject", ""),
            "n_rows": n_rows,
            "recommended_action": r.get("recommended_action", ""),
            "pre_validation_status": r.get("latest_validation_status", ""),
            "method": method,
            "mode": "execute" if args.execute else "dry-run",
            "returncode": "",
            "error_message": "",
        }

        print()
        print(f"[{i}/{len(selected)}] {('RUN' if args.execute else 'DRY-RUN')} {method}: {packet} n_rows={n_rows}")

        if args.execute:
            if method == "chunked_41c":
                cmd = [
                    args.python,
                    "scripts/41c_run_agentic_ai_chunked_large_packet.py",
                    "--packet-id", packet,
                    "--chunk-size", str(args.chunk_size),
                ]
            else:
                cmd = [
                    args.python,
                    "scripts/41_batch_run_agentic_ai_on_trusted_queue.py",
                    "--packet-id", packet,
                    "--execute",
                ]
                if args.force:
                    cmd.append("--force")

            packet_dir = batch_dir / packet
            packet_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = packet_dir / "stdout.txt"
            stderr_path = packet_dir / "stderr.txt"

            with stdout_path.open("w") as out, stderr_path.open("w") as err:
                proc = subprocess.run(cmd, stdout=out, stderr=err, text=True)

            row["returncode"] = proc.returncode
            row["stdout_log"] = str(stdout_path)
            row["stderr_log"] = str(stderr_path)

            if proc.returncode != 0:
                row["error_message"] = f"runner_failed_returncode_{proc.returncode}"

            row.update(latest_validation(packet))
            print(
                f"    VALIDATION: {row.get('post_validation_status','')} "
                f"fail={row.get('post_n_fail','')} warn={row.get('post_n_warn','')}"
            )
        else:
            row.update({
                "post_validation_status": "",
                "post_n_fail": "",
                "post_n_warn": "",
                "post_validation_summary": "",
            })

        rows.append(row)

    summary = pd.DataFrame(rows)
    out_path = batch_dir / f"batch_production.{stamp}.summary.tsv"
    summary.to_csv(out_path, sep="\t", index=False)

    print()
    print("Summary written:", out_path)


if __name__ == "__main__":
    main()
