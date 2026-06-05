#!/usr/bin/env python3
"""
Non-mutating readiness check for a fresh RNA/ChIP curator rerun.

This script prints local environment, input-file, cache, paper, API-guard, and
workflow-map status. It does not call external APIs and does not write outputs.

Exit behavior:
  - exits 0 after printing PASS/REVIEW so it can be used in smoke checks
  - REVIEW means a human should address missing local inputs, missing imports, dirty
    working tree, or workflow-map issues before a publication-quality rerun
"""

from __future__ import annotations

import csv
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_STEPS = ROOT / "workflows/steps.tsv"

REQUIRED_INPUTS = [
    ROOT / "data/rna_seq_metadata_2026-05-05_original.xlsx",
    ROOT / "data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx",
]

CACHE_DIRS = [
    ROOT / "data/sra_runinfo_cache",
    ROOT / "data/biosample_cache",
]

IMPORT_CHECKS = [
    ("pandas", ["pandas"]),
    ("openpyxl", ["openpyxl"]),
    ("xlsxwriter", ["xlsxwriter"]),
    ("openai", ["openai"]),
    ("pypdf_or_PyPDF2", ["pypdf", "PyPDF2"]),
]


def run_git(args: list[str]) -> str:
    try:
        p = subprocess.run(
            ["git"] + args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return p.stdout.strip()
    except Exception:
        return ""


def import_available(names: list[str]) -> bool:
    return any(importlib.util.find_spec(name) is not None for name in names)


def count_files(path: Path, pattern: str = "*") -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return sum(1 for p in path.glob(pattern) if p.is_file())


def workflow_status() -> tuple[bool, list[str], int]:
    if not WORKFLOW_STEPS.exists():
        return False, [f"missing workflow map: {WORKFLOW_STEPS}"], 0
    missing = []
    n_rows = 0
    try:
        with WORKFLOW_STEPS.open(newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                n_rows += 1
                script = row.get("script", "")
                if not script:
                    missing.append(f"step {row.get('step', '')}: empty script field")
                    continue
                if not (ROOT / script).exists():
                    missing.append(f"step {row.get('step', '')}: {script}")
    except Exception as e:
        return False, [f"workflow map parse error: {type(e).__name__}: {e}"], n_rows
    return True, missing, n_rows


def yn(ok: bool) -> str:
    return "PASS" if ok else "REVIEW"


def main() -> None:
    review_reasons = []

    print("# Rerun Readiness Check")
    print("")
    print(f"Repo path: {ROOT}")
    print(f"Current branch: {run_git(['branch', '--show-current']) or 'unknown'}")

    status = run_git(["status", "--short"])
    clean = not bool(status)
    print(f"Git cleanliness: {yn(clean)} {'clean' if clean else 'dirty'}")
    if not clean:
        review_reasons.append("working tree has uncommitted changes")
        for line in status.splitlines()[:20]:
            print(f"  {line}")
        if len(status.splitlines()) > 20:
            print(f"  ... {len(status.splitlines()) - 20} more")
    print("")

    print("## Python and imports")
    print(f"Python executable: {sys.executable}")
    for label, modules in IMPORT_CHECKS:
        ok = import_available(modules)
        print(f"- {yn(ok)} import {label}")
        if not ok:
            review_reasons.append(f"missing Python import: {label}")
    print("")

    print("## Required local input workbooks")
    for path in REQUIRED_INPUTS:
        ok = path.exists() and path.is_file()
        size = f" ({path.stat().st_size} bytes)" if ok else ""
        print(f"- {yn(ok)} {path.relative_to(ROOT)}{size}")
        if not ok:
            review_reasons.append(f"missing required input workbook: {path.relative_to(ROOT)}")
    print("")

    print("## Local caches and papers")
    for path in CACHE_DIRS:
        if path.exists():
            print(f"- PASS {path.relative_to(ROOT)}: {count_files(path)} files")
        else:
            print(f"- REVIEW {path.relative_to(ROOT)}: directory not present")
    papers = ROOT / "papers"
    if papers.exists():
        print(f"- PASS papers/: {count_files(papers, '*.pdf')} PDFs")
    else:
        print("- REVIEW papers/: directory not present")
    print("")

    print("## API guard status")
    api_enabled = os.environ.get("AGENTIC_AI_ENABLE_API") == "1"
    key_set = bool(os.environ.get("OPENAI_API_KEY"))
    print(f"- AGENTIC_AI_ENABLE_API == 1: {'yes' if api_enabled else 'no'}")
    print(f"- OPENAI_API_KEY set: {'yes' if key_set else 'no'}")
    print("  API calls remain off unless workflow commands are explicitly run with --execute --execute-ai and API guards enabled.")
    print("")

    print("## Workflow map")
    parsed, missing, n_rows = workflow_status()
    print(f"- {yn(parsed)} parse workflows/steps.tsv ({n_rows} steps)")
    if not parsed:
        review_reasons.append("workflow map did not parse")
    if missing:
        print("- REVIEW missing referenced scripts:")
        review_reasons.append("workflow map references missing scripts")
        for item in missing:
            print(f"  - {item}")
    else:
        print("- PASS all referenced workflow scripts exist")
    print("")

    print("## Final verdict")
    if review_reasons:
        print("REVIEW")
        for reason in review_reasons:
            print(f"- {reason}")
    else:
        print("PASS")


if __name__ == "__main__":
    main()
