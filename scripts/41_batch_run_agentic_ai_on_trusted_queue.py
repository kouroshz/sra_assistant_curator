#!/usr/bin/env python3
"""
Batch runner for trusted PMID-linked RNA-seq paper/BioProject packets.

Default behavior is DRY-RUN ONLY. Use --execute to call the API runner.

This script intentionally does NOT read any manual/gold-standard curation files.
Gold standards should be used only later for independent verification.

Typical first use:

  python scripts/41_batch_run_agentic_ai_on_trusted_queue.py \
    --packet-id PMID_32487761__BIOPROJECT_PRJNA550429

Then, when ready to actually run:

  set -a; source .env; set +a
  python scripts/41_batch_run_agentic_ai_on_trusted_queue.py \
    --packet-id PMID_32487761__BIOPROJECT_PRJNA550429 \
    --execute --force

Top-10 stage:

  python scripts/41_batch_run_agentic_ai_on_trusted_queue.py \
    --include-actions run_ai_first,run_ai_pilot \
    --limit 10 \
    --execute
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for dry-run use
    load_dotenv = None


DEFAULT_QUEUE_CANDIDATES = [
    "outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv",
    "outputs/02_QC_SUMMARIES/trusted_assay_aware_ai_queue.tsv",
]

DEFAULT_SUGGESTIONS_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
DEFAULT_VALIDATION_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/validation")
DEFAULT_PACKET_TABLES_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")
DEFAULT_BATCH_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/batch_runs")

SCRIPT_39 = Path("scripts/39_run_agentic_ai_on_paper_packet.py")
SCRIPT_40 = Path("scripts/40_validate_ai_curation_output.py")

PACKET_ID_RE = re.compile(r"PMID_[^_]+__BIOPROJECT_[A-Za-z0-9_.-]+")


# -----------------------------
# Small utilities
# -----------------------------

def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Find repo root by walking upward until scripts/39 exists, else cwd."""
    cur = (start or Path.cwd()).resolve()
    for path in [cur, *cur.parents]:
        if (path / SCRIPT_39).exists() and (path / SCRIPT_40).exists():
            return path
    return cur


def read_tsv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing TSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]


def write_tsv(path: Path, rows: List[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def first_existing_path(root: Path, candidates: Sequence[str]) -> Path:
    for c in candidates:
        p = root / c
        if p.exists():
            return p
    joined = "\n  ".join(candidates)
    raise FileNotFoundError(f"None of the expected queue files exists:\n  {joined}")


def pick_column(rows: Sequence[Dict[str, str]], candidates: Sequence[str]) -> Optional[str]:
    if not rows:
        return None
    cols = set(rows[0].keys())
    for c in candidates:
        if c in cols:
            return c
    lower_map = {c.lower(): c for c in cols}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def clean_string(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def infer_packet_id(row: Dict[str, str]) -> str:
    packet_col_candidates = [
        "packet_id",
        "paper_packet_id",
        "packet_key",
        "packet_name",
        "pmid_bioproject_packet",
    ]
    for col in packet_col_candidates:
        if col in row and clean_string(row[col]):
            value = clean_string(row[col])
            m = PACKET_ID_RE.search(value)
            return m.group(0) if m else value

    # Some tables may have a JSON path or rowwise TSV path that contains packet_id.
    for value in row.values():
        m = PACKET_ID_RE.search(clean_string(value))
        if m:
            return m.group(0)

    pmid = clean_string(row.get("pmid") or row.get("PMID") or row.get("PubMed_ID") or row.get("PubMedId"))
    bioproject = clean_string(row.get("bioproject") or row.get("BioProject") or row.get("BioProject_ID") or row.get("BioProject ID"))
    if pmid and bioproject:
        return f"PMID_{pmid}__BIOPROJECT_{bioproject}"

    raise ValueError(f"Could not infer packet_id from row columns: {sorted(row.keys())}")


def parse_int_like(value: Any, default: int = 0) -> int:
    s = clean_string(value)
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def parse_float_like(value: Any, default: float = 0.0) -> float:
    s = clean_string(value)
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def latest_file(pattern: str) -> Optional[Path]:
    files = [Path(p) for p in sorted(Path().glob(pattern))]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def latest_ai_json(root: Path, suggestions_dir: Path, packet_id: str) -> Optional[Path]:
    base = root / suggestions_dir / packet_id
    candidates = list(base.glob(f"{packet_id}.ai_curation.*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def latest_validation_summary(root: Path, validation_dir: Path, packet_id: str) -> Optional[Path]:
    base = root / validation_dir
    candidates = list(base.glob(f"{packet_id}.*.validation_summary.tsv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_validation_summary(path: Optional[Path]) -> Dict[str, str]:
    """Read validator summary TSV.

    The validator currently writes a vertical metric/value table, e.g.

        metric                  value
        n_fail                  0
        n_warn                  14
        validation_status       WARN

    Older/future versions may write a normal one-row summary with columns
    like validation_status, n_fail, n_warn. Support both formats.
    """
    if path is None or not path.exists():
        return {}
    rows = read_tsv(path)
    if not rows:
        return {}

    cols = set(rows[0].keys())

    # Current validator format: one metric per row.
    if {"metric", "value"}.issubset(cols):
        out: Dict[str, str] = {}
        for row in rows:
            key = clean_string(row.get("metric"))
            if not key:
                continue
            out[key] = clean_string(row.get("value"))
        return out

    # Fallback: normal single-row wide summary.
    return rows[0]


def validation_status_from_summary(summary: Dict[str, str]) -> Tuple[str, int, int]:
    status = clean_string(
        summary.get("validation_status")
        or summary.get("status")
        or summary.get("validator_status")
    )
    n_fail = parse_int_like(summary.get("n_fail") or summary.get("fail") or summary.get("fails"), 0)
    n_warn = parse_int_like(summary.get("n_warn") or summary.get("warn") or summary.get("warnings"), 0)
    return status, n_fail, n_warn


def safe_rel(root: Path, path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, float]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    runtime = time.time() - start
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    return proc.returncode, runtime


def get_packet_metadata(row: Dict[str, str], packet_id: str) -> Dict[str, str]:
    pmid = clean_string(row.get("pmid") or row.get("PMID"))
    bioproject = clean_string(row.get("bioproject") or row.get("BioProject") or row.get("BioProject_ID"))

    if not pmid or not bioproject:
        m = re.match(r"PMID_([^_]+)__BIOPROJECT_(.+)", packet_id)
        if m:
            pmid = pmid or m.group(1)
            bioproject = bioproject or m.group(2)

    n_rows = clean_string(row.get("n_rows") or row.get("row_count") or row.get("n_packet_rows"))
    assay_class = clean_string(row.get("assay_class") or row.get("assay_aware_assay_class") or row.get("assay_type"))
    action = clean_string(
        row.get("assay_aware_recommended_action")
        or row.get("recommended_action")
        or row.get("ai_recommended_action")
    )
    priority = clean_string(row.get("ai_priority_score") or row.get("priority_score") or row.get("priority"))

    return {
        "pmid": pmid,
        "bioproject": bioproject,
        "n_rows": n_rows,
        "assay_class": assay_class,
        "recommended_action": action,
        "priority": priority,
    }


# -----------------------------
# Queue selection
# -----------------------------

def select_queue_rows(
    rows: List[Dict[str, str]],
    *,
    packet_ids: Sequence[str],
    include_actions: Sequence[str],
    limit: int,
) -> List[Dict[str, str]]:
    if packet_ids:
        wanted = set(packet_ids)
        selected: List[Dict[str, str]] = []
        seen = set()
        for row in rows:
            pid = infer_packet_id(row)
            if pid in wanted:
                new_row = dict(row)
                new_row["packet_id"] = pid
                selected.append(new_row)
                seen.add(pid)
        # Allow explicitly requested packet IDs not present in queue; script 39 may still find packet JSON.
        for pid in packet_ids:
            if pid not in seen:
                selected.append({"packet_id": pid})
        return selected

    include = {a.strip() for a in include_actions if a.strip()}
    action_cols = [
        "assay_aware_recommended_action",
        "recommended_action",
        "ai_recommended_action",
        "action",
    ]
    action_col = pick_column(rows, action_cols)

    selected = []
    for row in rows:
        pid = infer_packet_id(row)
        action = clean_string(row.get(action_col, "")) if action_col else ""
        if include and "all" not in include and action not in include:
            continue
        new_row = dict(row)
        new_row["packet_id"] = pid
        selected.append(new_row)

    # If a priority-like score exists, sort descending; otherwise keep file order.
    priority_col = pick_column(selected, ["ai_priority_score", "priority_score", "priority"])
    if priority_col:
        selected.sort(key=lambda r: parse_float_like(r.get(priority_col), 0.0), reverse=True)

    if limit and limit > 0:
        selected = selected[:limit]
    return selected


# -----------------------------
# Main processing
# -----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Batch-run script 39 on trusted RNA paper packets and validate each output with script 40.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--queue", default="", help="Trusted queue TSV. If omitted, known default locations are tried.")
    p.add_argument(
        "--packet-id",
        action="append",
        default=[],
        help="Explicit packet ID to run, e.g. PMID_32487761__BIOPROJECT_PRJNA550429. Can be repeated.",
    )
    p.add_argument(
        "--include-actions",
        default="run_ai_first,run_ai_pilot",
        help="Comma-separated queue actions to include, or 'all'. Ignored when --packet-id is used.",
    )
    p.add_argument("--limit", type=int, default=10, help="Maximum packets to select when not using --packet-id. Use 0 for no limit.")
    p.add_argument("--execute", action="store_true", help="Actually run script 39 and script 40. Without this, dry-run only.")
    p.add_argument("--force", action="store_true", help="Re-run even if latest validation summary is PASS.")
    p.add_argument("--stop-after-failures", type=int, default=2, help="Stop batch after this many FAIL/error packets. Use 0 to disable.")
    p.add_argument("--ai-runner", default=str(SCRIPT_39), help="Path to script 39.")
    p.add_argument("--validator", default=str(SCRIPT_40), help="Path to script 40.")
    p.add_argument("--suggestions-dir", default=str(DEFAULT_SUGGESTIONS_DIR), help="AI suggestion output directory.")
    p.add_argument("--validation-dir", default=str(DEFAULT_VALIDATION_DIR), help="Validation output directory.")
    p.add_argument("--packet-tables-dir", default=str(DEFAULT_PACKET_TABLES_DIR), help="Packet rowwise TSV directory.")
    p.add_argument("--batch-dir", default=str(DEFAULT_BATCH_DIR), help="Batch logs/summary directory.")
    p.add_argument("--summary-name", default="", help="Optional output summary filename.")
    p.add_argument("--python", default=sys.executable, help="Python executable to call child scripts.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_repo_root()
    if load_dotenv is not None:
        load_dotenv(root / ".env")

    queue_path = Path(args.queue) if args.queue else first_existing_path(root, DEFAULT_QUEUE_CANDIDATES)
    if not queue_path.is_absolute():
        queue_path = root / queue_path

    rows = read_tsv(queue_path)
    include_actions = [x.strip() for x in args.include_actions.split(",") if x.strip()]
    selected = select_queue_rows(
        rows,
        packet_ids=args.packet_id,
        include_actions=include_actions,
        limit=args.limit,
    )

    if args.execute:
        if os.environ.get("AGENTIC_AI_ENABLE_API", "") != "1":
            raise SystemExit("Refusing --execute: AGENTIC_AI_ENABLE_API must be set to 1 before any batch output or API runner launch.")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("Refusing --execute: OPENAI_API_KEY is not set. The key value was not printed.")

    stamp = now_stamp()
    batch_dir = root / Path(args.batch_dir) / stamp
    batch_dir.mkdir(parents=True, exist_ok=True)

    summary_name = args.summary_name or f"batch_ai_run.{stamp}.summary.tsv"
    summary_path = batch_dir / summary_name

    ai_runner = root / Path(args.ai_runner)
    validator = root / Path(args.validator)
    suggestions_dir = Path(args.suggestions_dir)
    validation_dir = Path(args.validation_dir)
    packet_tables_dir = Path(args.packet_tables_dir)

    if not ai_runner.exists():
        raise FileNotFoundError(f"Missing AI runner: {ai_runner}")
    if not validator.exists():
        raise FileNotFoundError(f"Missing validator: {validator}")

    print(f"Repo root: {root}")
    print(f"Queue: {safe_rel(root, queue_path)}")
    print(f"Selected packets: {len(selected)}")
    print(f"Batch dir: {safe_rel(root, batch_dir)}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    summary_rows: List[Dict[str, Any]] = []
    n_bad = 0

    for i, row in enumerate(selected, start=1):
        packet_id = infer_packet_id(row)
        meta = get_packet_metadata(row, packet_id)
        latest_summary_before = latest_validation_summary(root, validation_dir, packet_id)
        latest_status_before, latest_fail_before, latest_warn_before = validation_status_from_summary(
            read_validation_summary(latest_summary_before)
        )

        base_record: Dict[str, Any] = {
            "batch_timestamp": stamp,
            "batch_index": i,
            "packet_id": packet_id,
            **meta,
            "mode": "execute" if args.execute else "dry_run",
            "preexisting_validation_status": latest_status_before,
            "preexisting_n_fail": latest_fail_before,
            "preexisting_n_warn": latest_warn_before,
            "skipped": "",
            "skip_reason": "",
            "runner_returncode": "",
            "validator_returncode": "",
            "runtime_ai_seconds": "",
            "runtime_validation_seconds": "",
            "ai_json_path": "",
            "validation_summary_path": "",
            "validation_status": "",
            "n_fail": "",
            "n_warn": "",
            "stdout_log": "",
            "stderr_log": "",
            "error_message": "",
        }

        if latest_status_before.upper() == "PASS" and not args.force:
            base_record.update(
                {
                    "skipped": "yes",
                    "skip_reason": "latest_validation_PASS_use_--force_to_rerun",
                    "validation_summary_path": safe_rel(root, latest_summary_before),
                    "validation_status": latest_status_before,
                    "n_fail": latest_fail_before,
                    "n_warn": latest_warn_before,
                }
            )
            print(f"[{i}/{len(selected)}] SKIP PASS: {packet_id}")
            summary_rows.append(base_record)
            continue

        if not args.execute:
            cmd = [args.python, str(SCRIPT_39), "--packet-id", packet_id]
            packet_tsv = root / packet_tables_dir / f"{packet_id}.rowwise_evidence.tsv"
            base_record.update(
                {
                    "skipped": "yes",
                    "skip_reason": "dry_run",
                    "error_message": "Would run: " + " ".join(shlex.quote(c) for c in cmd)
                    + f" ; then validate {safe_rel(root, packet_tsv)} against latest AI JSON.",
                }
            )
            print(f"[{i}/{len(selected)}] DRY-RUN: {packet_id}")
            summary_rows.append(base_record)
            continue

        print(f"[{i}/{len(selected)}] RUN: {packet_id}")
        per_packet_log_dir = batch_dir / packet_id
        per_packet_log_dir.mkdir(parents=True, exist_ok=True)

        runner_stdout = per_packet_log_dir / "script39.stdout.txt"
        runner_stderr = per_packet_log_dir / "script39.stderr.txt"
        validator_stdout = per_packet_log_dir / "script40.stdout.txt"
        validator_stderr = per_packet_log_dir / "script40.stderr.txt"

        ai_cmd = [args.python, str(SCRIPT_39), "--packet-id", packet_id]
        rc_ai, runtime_ai = run_cmd(
            ai_cmd,
            cwd=root,
            stdout_path=runner_stdout,
            stderr_path=runner_stderr,
            env=os.environ.copy(),
        )
        base_record.update(
            {
                "runner_returncode": rc_ai,
                "runtime_ai_seconds": f"{runtime_ai:.2f}",
                "stdout_log": safe_rel(root, runner_stdout),
                "stderr_log": safe_rel(root, runner_stderr),
            }
        )

        if rc_ai != 0:
            base_record.update({"validation_status": "ERROR", "error_message": "script39_failed"})
            print(f"    ERROR script39 returncode={rc_ai}; see {safe_rel(root, runner_stderr)}")
            summary_rows.append(base_record)
            n_bad += 1
            if args.stop_after_failures and n_bad >= args.stop_after_failures:
                print(f"Stopping after {n_bad} failures/errors.")
                break
            continue

        ai_json = latest_ai_json(root, suggestions_dir, packet_id)
        if ai_json is None:
            base_record.update({"validation_status": "ERROR", "error_message": "no_ai_json_found_after_script39"})
            print("    ERROR: no AI JSON found after script39.")
            summary_rows.append(base_record)
            n_bad += 1
            if args.stop_after_failures and n_bad >= args.stop_after_failures:
                print(f"Stopping after {n_bad} failures/errors.")
                break
            continue

        packet_tsv = root / packet_tables_dir / f"{packet_id}.rowwise_evidence.tsv"
        if not packet_tsv.exists():
            base_record.update(
                {
                    "ai_json_path": safe_rel(root, ai_json),
                    "validation_status": "ERROR",
                    "error_message": f"missing_packet_tsv:{safe_rel(root, packet_tsv)}",
                }
            )
            print(f"    ERROR: missing packet TSV {safe_rel(root, packet_tsv)}")
            summary_rows.append(base_record)
            n_bad += 1
            if args.stop_after_failures and n_bad >= args.stop_after_failures:
                print(f"Stopping after {n_bad} failures/errors.")
                break
            continue

        val_cmd = [
            args.python,
            str(SCRIPT_40),
            "--packet-tsv",
            str(packet_tsv),
            "--ai-json",
            str(ai_json),
        ]
        rc_val, runtime_val = run_cmd(
            val_cmd,
            cwd=root,
            stdout_path=validator_stdout,
            stderr_path=validator_stderr,
            env=os.environ.copy(),
        )
        latest_summary_after = latest_validation_summary(root, validation_dir, packet_id)
        val_summary = read_validation_summary(latest_summary_after)
        status, n_fail, n_warn = validation_status_from_summary(val_summary)
        if not status:
            status = "ERROR" if rc_val != 0 else "UNKNOWN"

        base_record.update(
            {
                "validator_returncode": rc_val,
                "runtime_validation_seconds": f"{runtime_val:.2f}",
                "ai_json_path": safe_rel(root, ai_json),
                "validation_summary_path": safe_rel(root, latest_summary_after),
                "validation_status": status,
                "n_fail": n_fail,
                "n_warn": n_warn,
            }
        )

        # Append validator logs to log columns if runner was OK.
        base_record["stdout_log"] = f"{base_record['stdout_log']};{safe_rel(root, validator_stdout)}"
        base_record["stderr_log"] = f"{base_record['stderr_log']};{safe_rel(root, validator_stderr)}"

        if rc_val != 0:
            base_record["error_message"] = "script40_failed"

        if str(status).upper() in {"FAIL", "ERROR"} or rc_val != 0:
            n_bad += 1

        print(f"    VALIDATION: {status} fail={n_fail} warn={n_warn}")
        summary_rows.append(base_record)

        if args.stop_after_failures and n_bad >= args.stop_after_failures:
            print(f"Stopping after {n_bad} failures/errors.")
            break

    fieldnames = [
        "batch_timestamp",
        "batch_index",
        "packet_id",
        "pmid",
        "bioproject",
        "n_rows",
        "assay_class",
        "recommended_action",
        "priority",
        "mode",
        "preexisting_validation_status",
        "preexisting_n_fail",
        "preexisting_n_warn",
        "skipped",
        "skip_reason",
        "runner_returncode",
        "validator_returncode",
        "runtime_ai_seconds",
        "runtime_validation_seconds",
        "ai_json_path",
        "validation_summary_path",
        "validation_status",
        "n_fail",
        "n_warn",
        "stdout_log",
        "stderr_log",
        "error_message",
    ]
    write_tsv(summary_path, summary_rows, fieldnames)
    print(f"Summary written: {safe_rel(root, summary_path)}")

    # Exit nonzero only in execute mode if a child errored/failed validation.
    if args.execute and n_bad > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
