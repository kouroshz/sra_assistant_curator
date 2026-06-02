#!/usr/bin/env python3
"""
Auto-dispatch batch runner for trusted RNA AI packets.

Small/moderate packets:
  -> scripts/41_batch_run_agentic_ai_on_trusted_queue.py

Large packets:
  -> scripts/41c_run_agentic_ai_chunked_large_packet.py

This keeps the original one-shot batch runner stable, while using chunked mode
when row count is too large for reliable one-shot JSON output.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_QUEUE = Path("outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv")
DEFAULT_VALIDATION_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/validation")
DEFAULT_BATCH_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/batch_runs_auto_chunked")

SCRIPT_41 = Path("scripts/41_batch_run_agentic_ai_on_trusted_queue.py")
SCRIPT_41C = Path("scripts/41c_run_agentic_ai_chunked_large_packet.py")

PACKET_ID_RE = re.compile(r"PMID_[^_]+__BIOPROJECT_[A-Za-z0-9_.-]+")


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def clean(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def parse_int(x: Any, default: int = 0) -> int:
    s = clean(x)
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def parse_float(x: Any, default: float = 0.0) -> float:
    s = clean(x)
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return [
            {k: (v if v is not None else "") for k, v in row.items()}
            for row in csv.DictReader(f, delimiter="\t")
        ]


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def infer_packet_id(row: dict[str, str]) -> str:
    for c in ["packet_id", "paper_packet_id", "packet_key", "packet_name"]:
        if clean(row.get(c)):
            m = PACKET_ID_RE.search(clean(row[c]))
            return m.group(0) if m else clean(row[c])

    for v in row.values():
        m = PACKET_ID_RE.search(clean(v))
        if m:
            return m.group(0)

    pmid = clean(row.get("pmid") or row.get("PMID"))
    bioproject = clean(row.get("bioproject") or row.get("BioProject") or row.get("BioProject_ID"))
    if pmid and bioproject:
        return f"PMID_{pmid}__BIOPROJECT_{bioproject}"

    raise ValueError(f"Could not infer packet_id from row: {row}")


def latest_validation_summary(packet_id: str) -> Path | None:
    # Standard one-shot validator output:
    #   PACKET.TIMESTAMP.validation_summary.tsv
    # Chunked validator output:
    #   PACKET_chunked_merged_completed.TIMESTAMP.validation_summary.tsv
    # So use a broad prefix match.
    files = sorted(
        DEFAULT_VALIDATION_DIR.glob(f"{packet_id}*.validation_summary.tsv"),
        key=lambda p: p.stat().st_mtime,
    )
    return files[-1] if files else None


def parse_metric_value_summary(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    rows = read_tsv(path)
    if not rows:
        return {}

    # Validator summaries are metric/value vertical tables.
    if {"metric", "value"}.issubset(rows[0].keys()):
        return {clean(r.get("metric")): clean(r.get("value")) for r in rows if clean(r.get("metric"))}

    # Tolerate normal wide TSV.
    return rows[0]


def validation_status(packet_id: str) -> tuple[str, int, int, str]:
    p = latest_validation_summary(packet_id)
    s = parse_metric_value_summary(p)
    status = clean(s.get("validation_status") or s.get("status"))
    n_fail = parse_int(s.get("n_fail") or s.get("fail"), 0)
    n_warn = parse_int(s.get("n_warn") or s.get("warn"), 0)
    return status, n_fail, n_warn, str(p) if p else ""


def select_rows(
    rows: list[dict[str, str]],
    include_actions: set[str],
    limit: int,
    force: bool = False,
) -> list[dict[str, str]]:
    out = []
    for row in rows:
        action = clean(
            row.get("assay_aware_recommended_action")
            or row.get("recommended_action")
            or row.get("ai_recommended_action")
        )
        if include_actions and "all" not in include_actions and action not in include_actions:
            continue

        new = dict(row)
        new["packet_id"] = infer_packet_id(row)
        out.append(new)

    out.sort(
        key=lambda r: parse_float(
            r.get("assay_aware_priority_score") or r.get("ai_priority_score") or r.get("priority"),
            0.0,
        ),
        reverse=True,
    )

    # By default, --limit counts actionable packets, not already-PASS packets.
    # With --force, PASS packets remain actionable and can be rerun.
    actionable = []
    skipped_pass = []
    for r in out:
        status, _, _, _ = validation_status(r["packet_id"])
        if status.upper() == "PASS" and not force:
            skipped_pass.append(r)
        else:
            actionable.append(r)

    if limit > 0:
        actionable = actionable[:limit]

    # Keep skipped PASS rows after actionable rows for visibility in the summary.
    return actionable + skipped_pass[:20]


def run_cmd(cmd: list[str], stdout_path: Path, stderr_path: Path) -> tuple[int, float]:
    start = dt.datetime.now()
    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    runtime = (dt.datetime.now() - start).total_seconds()
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    return proc.returncode, runtime


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    ap.add_argument("--include-actions", default="run_ai_first,run_ai_pilot")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--large-threshold", type=int, default=150)
    ap.add_argument("--chunk-size", type=int, default=60)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    if not args.queue.exists():
        raise FileNotFoundError(args.queue)
    if not SCRIPT_41.exists():
        raise FileNotFoundError(SCRIPT_41)
    if not SCRIPT_41C.exists():
        raise FileNotFoundError(SCRIPT_41C)

    stamp = now_stamp()
    batch_dir = DEFAULT_BATCH_DIR / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)

    include_actions = {x.strip() for x in args.include_actions.split(",") if x.strip()}
    rows = read_tsv(args.queue)
    selected = select_rows(rows, include_actions, args.limit, force=args.force)

    print(f"Queue: {args.queue}")
    print(f"Selected packets: {len(selected)}")
    print(f"Batch dir: {batch_dir}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print(f"Large threshold: n_rows > {args.large_threshold}")
    print(f"Chunk size: {args.chunk_size}")

    summary = []

    for i, row in enumerate(selected, start=1):
        packet_id = row["packet_id"]
        n_rows = parse_int(row.get("n_rows") or row.get("row_count") or row.get("n_packet_rows"), 0)
        action = clean(row.get("assay_aware_recommended_action") or row.get("recommended_action"))
        priority = clean(row.get("assay_aware_priority_score") or row.get("ai_priority_score") or row.get("priority"))

        pre_status, pre_fail, pre_warn, pre_summary = validation_status(packet_id)

        use_chunked = n_rows > args.large_threshold
        method = "chunked_41c" if use_chunked else "one_shot_41"

        record = {
            "batch_timestamp": stamp,
            "batch_index": i,
            "packet_id": packet_id,
            "pmid": clean(row.get("pmid") or row.get("PMID")),
            "bioproject": clean(row.get("bioproject") or row.get("BioProject") or row.get("BioProject_ID")),
            "n_rows": n_rows,
            "recommended_action": action,
            "priority": priority,
            "method": method,
            "mode": "execute" if args.execute else "dry_run",
            "preexisting_validation_status": pre_status,
            "preexisting_n_fail": pre_fail,
            "preexisting_n_warn": pre_warn,
            "preexisting_validation_summary": pre_summary,
            "skipped": "",
            "skip_reason": "",
            "returncode": "",
            "runtime_seconds": "",
            "post_validation_status": "",
            "post_n_fail": "",
            "post_n_warn": "",
            "post_validation_summary": "",
            "stdout_log": "",
            "stderr_log": "",
        }

        if pre_status.upper() == "PASS" and not args.force:
            print(f"[{i}/{len(selected)}] SKIP PASS: {packet_id}")
            record.update({
                "skipped": "yes",
                "skip_reason": "latest_validation_PASS_use_--force_to_rerun",
                "post_validation_status": pre_status,
                "post_n_fail": pre_fail,
                "post_n_warn": pre_warn,
                "post_validation_summary": pre_summary,
            })
            summary.append(record)
            continue

        if not args.execute:
            print(f"[{i}/{len(selected)}] DRY-RUN {method}: {packet_id} n_rows={n_rows}")
            record.update({
                "skipped": "yes",
                "skip_reason": "dry_run",
            })
            summary.append(record)
            continue

        log_dir = batch_dir / packet_id
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = log_dir / "stdout.txt"
        stderr_log = log_dir / "stderr.txt"

        if use_chunked:
            cmd = [
                args.python,
                str(SCRIPT_41C),
                "--packet-id",
                packet_id,
                "--chunk-size",
                str(args.chunk_size),
            ]
        else:
            cmd = [
                args.python,
                str(SCRIPT_41),
                "--packet-id",
                packet_id,
                "--execute",
                "--force",
            ]

        print(f"[{i}/{len(selected)}] RUN {method}: {packet_id} n_rows={n_rows}")
        rc, runtime = run_cmd(cmd, stdout_log, stderr_log)

        post_status, post_fail, post_warn, post_summary = validation_status(packet_id)

        record.update({
            "returncode": rc,
            "runtime_seconds": f"{runtime:.2f}",
            "post_validation_status": post_status,
            "post_n_fail": post_fail,
            "post_n_warn": post_warn,
            "post_validation_summary": post_summary,
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
        })

        print(f"    VALIDATION: {post_status} fail={post_fail} warn={post_warn} rc={rc}")
        summary.append(record)

    fieldnames = [
        "batch_timestamp", "batch_index", "packet_id", "pmid", "bioproject",
        "n_rows", "recommended_action", "priority", "method", "mode",
        "preexisting_validation_status", "preexisting_n_fail", "preexisting_n_warn",
        "preexisting_validation_summary", "skipped", "skip_reason",
        "returncode", "runtime_seconds",
        "post_validation_status", "post_n_fail", "post_n_warn",
        "post_validation_summary", "stdout_log", "stderr_log",
    ]

    out = batch_dir / f"batch_auto_chunked.{stamp}.summary.tsv"
    write_tsv(out, summary, fieldnames)
    print(f"\nSummary written: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
