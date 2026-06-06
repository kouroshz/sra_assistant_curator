#!/usr/bin/env python3
"""
Production-facing workflow step runner.

This is a conservative wrapper around the current legacy scripts.

Default:
  list/show/dry-run only.
  no script execution unless --execute is passed.
  AI/API steps require --execute, --execute-ai, and AGENTIC_AI_ENABLE_API=1.
"""

from pathlib import Path
import argparse
import csv
from datetime import datetime
import os
import subprocess
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for dry-run use
    load_dotenv = None

STEP_MAP = Path("workflows/steps.tsv")

AI_KEYWORDS = [
    "OpenAI optional",
    "disabled unless explicitly enabled",
    "dry-run by default",
]


def read_steps():
    if not STEP_MAP.exists():
        raise SystemExit(f"Missing workflow map: {STEP_MAP}")
    with open(STEP_MAP, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def is_ai_step(row):
    api = row.get("api", "")
    return any(k.lower() in api.lower() for k in AI_KEYWORDS)


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def command_for(row, extra_args=None):
    cmd = [sys.executable, str(Path(row["script"]))]
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def format_command(cmd):
    return " ".join(cmd)


def print_step(row):
    print(f"Step {row['step']}: {row['production_name']}")
    print(f"  assay:        {row['assay']}")
    print(f"  script:       {row['script']}")
    print(f"  api:          {row['api']}")
    print(f"  status:       {row['status']}")
    print(f"  purpose:      {row['purpose']}")
    print(f"  main inputs:  {row['main_inputs']}")
    print(f"  main outputs: {row['main_outputs']}")


def ai_refusal(extra=""):
    msg = (
        "Refusing to execute AI-capable step. Required: "
        "--execute --execute-ai and AGENTIC_AI_ENABLE_API=1."
    )
    if extra:
        msg += f" {extra}"
    return msg


def validate_ai_permission(rows, execute_ai):
    ai_rows = [r for r in rows if is_ai_step(r)]
    if not ai_rows:
        return
    if not execute_ai:
        steps = ", ".join(r["step"] for r in ai_rows)
        raise SystemExit(ai_refusal(f"AI-capable step(s): {steps}."))
    if os.environ.get("AGENTIC_AI_ENABLE_API") != "1":
        steps = ", ".join(r["step"] for r in ai_rows)
        raise SystemExit(ai_refusal(f"AGENTIC_AI_ENABLE_API is not set to 1. AI-capable step(s): {steps}."))


def get_step(rows, step):
    matches = [r for r in rows if r["step"] == str(step)]
    if not matches:
        raise SystemExit(f"No workflow step found for: {step}")
    return matches[0]


def get_range(rows, start, end):
    step_to_index = {r["step"]: i for i, r in enumerate(rows)}
    if str(start) not in step_to_index:
        raise SystemExit(f"No workflow step found for --continue-from: {start}")
    if str(end) not in step_to_index:
        raise SystemExit(f"No workflow step found for --through: {end}")
    i0 = step_to_index[str(start)]
    i1 = step_to_index[str(end)]
    if i0 > i1:
        raise SystemExit(f"Invalid range: --continue-from {start} occurs after --through {end}")
    return rows[i0:i1 + 1]


def run_one(row, *, execute, execute_ai, extra_args=None):
    print_step(row)
    print()

    script = Path(row["script"])
    if not script.exists():
        raise SystemExit(f"Workflow step {row['step']} references missing script: {script}")

    cmd = command_for(row, extra_args=extra_args)
    print("Command:")
    print("  " + format_command(cmd))
    print()

    if not execute:
        print("DRY-RUN only. Add --execute to run.")
        return

    validate_ai_permission([row], execute_ai)

    start = timestamp()
    print(f"START {start} step {row['step']} {row['production_name']}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        end = timestamp()
        print(f"FAILED {end} step {row['step']} returncode={e.returncode}")
        raise SystemExit(e.returncode)
    end = timestamp()
    print(f"COMPLETE {end} step {row['step']} {row['production_name']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="List all workflow steps.")
    ap.add_argument("--step", help="Step number to show or run.")
    ap.add_argument("--continue-from", dest="continue_from", help="First workflow step in a deterministic range.")
    ap.add_argument("--through", help="Last workflow step in a deterministic range.")
    ap.add_argument("--execute", action="store_true", help="Actually execute the legacy script.")
    ap.add_argument("--execute-ai", action="store_true", help="Permit AI/API execution for AI steps.")
    ap.add_argument("--extra-args", nargs=argparse.REMAINDER, help="Additional args passed to legacy script.")
    args = ap.parse_args()

    if load_dotenv is not None:
        load_dotenv(Path(".env"))

    rows = read_steps()

    if args.list:
        print("step\tassay\tproduction_name\tlegacy_script\tapi")
        for r in rows:
            print(f"{r['step']}\t{r['assay']}\t{r['production_name']}\t{r['script']}\t{r['api']}")
        return

    range_requested = bool(args.continue_from or args.through)
    if range_requested:
        if args.step:
            ap.error("Use either --step or --continue-from/--through, not both.")
        if not args.continue_from or not args.through:
            ap.error("Range mode requires both --continue-from START and --through END.")
        if args.extra_args:
            ap.error("--extra-args is only supported with --step, not range mode.")
        selected = get_range(rows, args.continue_from, args.through)
        validate_ai_permission(selected, args.execute_ai)
        print(f"Workflow range: {selected[0]['step']} through {selected[-1]['step']}")
        print(f"Steps selected: {len(selected)}")
        print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
        print()
        for i, row in enumerate(selected, start=1):
            print("=" * 80)
            print(f"Range item {i}/{len(selected)}")
            run_one(row, execute=args.execute, execute_ai=args.execute_ai)
            print()
        print(f"Range complete: {selected[0]['step']} through {selected[-1]['step']}")
        return

    if not args.step:
        ap.error("Use --list, --step STEP, or --continue-from START --through END")

    row = get_step(rows, args.step)
    run_one(row, execute=args.execute, execute_ai=args.execute_ai, extra_args=args.extra_args)


if __name__ == "__main__":
    main()
