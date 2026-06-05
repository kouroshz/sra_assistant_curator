#!/usr/bin/env python3
"""
Print curator-facing output locations without modifying files.
"""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FINAL_RELEASE = RESULTS / "final_curator_release"

CURATOR_FILES = [
    ("RNA curator workbook", FINAL_RELEASE / "RNA/RNA_curator_review.xlsx"),
    ("ChIP curator workbook", FINAL_RELEASE / "ChIP/ChIP_curator_review.xlsx"),
    ("RNA study summaries Markdown", FINAL_RELEASE / "RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md"),
    ("ChIP study summaries Markdown", FINAL_RELEASE / "ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md"),
    ("RNA clean summary TSV", FINAL_RELEASE / "RNA/rna_ai_study_summaries_clean.tsv"),
    ("ChIP clean summary TSV", FINAL_RELEASE / "ChIP/chip_ai_study_summaries_clean.tsv"),
    ("Final QC report", FINAL_RELEASE / "QC/FINAL_RELEASE_QC_REPORT.md"),
]


def latest_zip() -> Path | None:
    zips = sorted(RESULTS.glob("final_curator_release_*.zip"), key=lambda p: p.stat().st_mtime)
    return zips[-1] if zips else None


def format_size(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_dir():
        return "directory"
    return f"{path.stat().st_size} bytes"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def print_item(label: str, path: Path) -> bool:
    exists = path.exists()
    status = "PASS" if exists else "MISSING"
    print(f"- {status} {label}: {rel(path)} ({format_size(path)})")
    return exists


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-open-command",
        action="store_true",
        help="Print macOS open commands for existing curator-facing files; do not run them.",
    )
    args = parser.parse_args()

    print("# Curator Output Locations")
    print("")

    have_release = print_item("latest final release folder", FINAL_RELEASE)
    zip_path = latest_zip()
    if zip_path:
        print_item("latest final release zip", zip_path)
    else:
        print("- MISSING latest final release zip: results/final_curator_release_*.zip (missing)")

    print("")
    print("## Curator-facing files")
    existing_files: list[Path] = []
    for label, path in CURATOR_FILES:
        if print_item(label, path):
            existing_files.append(path)

    if zip_path:
        existing_files.append(zip_path)

    if not have_release or len(existing_files) < len(CURATOR_FILES):
        print("")
        print("## Outputs not complete yet")
        print("Generate upstream curator outputs, then package the final release:")
        print("- RNA workbook and summaries: run workflow steps 08 through 15 after RNA AI JSONs exist.")
        print("- ChIP workbook and summaries: run workflow steps 36 through 43 after ChIP AI JSONs exist.")
        print("- Final share bundle and release folder: python workflows/run_workflow_step.py --step 90 --execute")

    if args.with_open_command and existing_files:
        print("")
        print("## macOS open commands")
        for path in existing_files:
            print(f"open {shlex.quote(str(path))}")


if __name__ == "__main__":
    main()
