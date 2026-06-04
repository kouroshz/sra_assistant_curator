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
import os
import subprocess
import sys

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


def print_step(row):
    print(f"Step {row['step']}: {row['production_name']}")
    print(f"  assay:        {row['assay']}")
    print(f"  legacy:       {row['script']}")
    print(f"  api:          {row['api']}")
    print(f"  status:       {row['status']}")
    print(f"  purpose:      {row['purpose']}")
    print(f"  main inputs:  {row['main_inputs']}")
    print(f"  main outputs: {row['main_outputs']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="List all workflow steps.")
    ap.add_argument("--step", help="Step number to show or run.")
    ap.add_argument("--execute", action="store_true", help="Actually execute the legacy script.")
    ap.add_argument("--execute-ai", action="store_true", help="Permit AI/API execution for AI steps.")
    ap.add_argument("--extra-args", nargs=argparse.REMAINDER, help="Additional args passed to legacy script.")
    args = ap.parse_args()

    rows = read_steps()

    if args.list:
        print("step\tassay\tproduction_name\tlegacy_script\tapi")
        for r in rows:
            print(f"{r['step']}\t{r['assay']}\t{r['production_name']}\t{r['script']}\t{r['api']}")
        return

    if not args.step:
        ap.error("Use --list or --step STEP")

    matches = [r for r in rows if r["step"] == str(args.step)]
    if not matches:
        raise SystemExit(f"No workflow step found for: {args.step}")

    row = matches[0]
    print_step(row)
    print()

    script = Path(row["script"])
    if not script.exists():
        raise SystemExit(f"Legacy script does not exist: {script}")

    cmd = [sys.executable, str(script)]
    if args.extra_args:
        cmd.extend(args.extra_args)

    print("Command:")
    print("  " + " ".join(cmd))
    print()

    if not args.execute:
        print("DRY-RUN only. Add --execute to run.")
        return

    if is_ai_step(row):
        if not args.execute_ai:
            raise SystemExit("Refusing to execute AI-capable step without --execute-ai.")
        if os.environ.get("AGENTIC_AI_ENABLE_API") != "1":
            raise SystemExit("Refusing to execute AI-capable step because AGENTIC_AI_ENABLE_API is not set to 1.")

    print("Executing...")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
