#!/usr/bin/env python3
"""
QC the clean final curator release folder.

This script is read-only.
It does not call APIs.
It verifies that results/final_curator_release/ contains only expected curator-facing products.
"""

from pathlib import Path
from datetime import datetime
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sra_paper_curator.file_utils import (
    count_tsv_rows,
    count_text_marker,
    find_forbidden_files,
)


RELEASE_ROOT = Path("results/final_curator_release")
LATEST_POINTER = Path("results/LATEST_FINAL_CURATOR_RELEASE.txt")
REPORT = Path("results/final_curator_release/QC/FINAL_RELEASE_QC_REPORT.md")


REQUIRED_FILES = [
    "README.md",
    "MANIFEST.tsv",
    "RNA/RNA_curator_review.xlsx",
    "RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md",
    "RNA/rna_ai_study_summaries_clean.tsv",
    "ChIP/ChIP_curator_review.xlsx",
    "ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md",
    "ChIP/chip_ai_study_summaries_clean.tsv",
    "ChIP/chip_rowwise_review.tsv",
    "ChIP/chip_target_control_map_review.tsv",
    "QC/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md",
    "QC/CHIP_AI_PHASE_COMPLETION_REPORT.md",
    "QC/CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md",
    "docs/ACTIVE_WORKFLOW_MAP.md",
    "docs/PRODUCTION_REORG_PLAN.md",
]


EXPECTED_COUNTS = {
    "rna_markdown_blocks": 70,
    "rna_study_summary_rows": 70,
    "chip_markdown_blocks": 43,
    "chip_study_summary_rows": 43,
    "chip_rowwise_rows": 737,
    "chip_target_control_rows": 492,
}


FORBIDDEN_SUFFIXES = [
    ".json",
    ".pdf",
    ".env",
    ".key",
    ".pem",
]


FORBIDDEN_NAME_PARTS = [
    "openai",
    "api_key",
    "raw_ai",
    "packet_json",
    "pdf",
]


def file_nonempty(path):
    return path.exists() and path.is_file() and path.stat().st_size > 0


def main():
    lines = []
    problems = []

    lines.append("# Final Release QC Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Release root: `{RELEASE_ROOT}`")
    lines.append("")

    if not RELEASE_ROOT.exists():
        problems.append(f"Missing release folder: {RELEASE_ROOT}")

    if not LATEST_POINTER.exists():
        problems.append(f"Missing latest pointer: {LATEST_POINTER}")
        zip_path = None
    else:
        pointer_lines = LATEST_POINTER.read_text().strip().splitlines()
        zip_path = Path(pointer_lines[1]) if len(pointer_lines) > 1 else None
        if not pointer_lines or Path(pointer_lines[0]) != RELEASE_ROOT:
            problems.append("Latest pointer first line does not point to results/final_curator_release")
        if zip_path is None or not zip_path.exists():
            problems.append("Latest pointer zip path is missing or invalid")

    lines.append("## Required files")
    lines.append("")

    for rel in REQUIRED_FILES:
        p = RELEASE_ROOT / rel
        ok = file_nonempty(p)
        lines.append(f"- {'PASS' if ok else 'FAIL'} `{rel}`")
        if not ok:
            problems.append(f"Missing or empty required file: {rel}")

    lines.append("")
    lines.append("## Forbidden file scan")
    lines.append("")

    forbidden_hits = find_forbidden_files(
        RELEASE_ROOT,
        FORBIDDEN_SUFFIXES,
        FORBIDDEN_NAME_PARTS,
    )

    if forbidden_hits:
        lines.append("FAIL: forbidden/suspicious files found:")
        for h in sorted(set(forbidden_hits)):
            lines.append(f"- `{h}`")
            problems.append(f"Forbidden/suspicious file in release: {h}")
    else:
        lines.append("PASS: no forbidden raw JSON/PDF/env/key-like files found.")

    lines.append("")
    lines.append("## Content checks")
    lines.append("")

    chip_md = RELEASE_ROOT / "ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md"
    rna_md = RELEASE_ROOT / "RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md"
    chip_tsv = RELEASE_ROOT / "ChIP/chip_ai_study_summaries_clean.tsv"
    rna_tsv = RELEASE_ROOT / "RNA/rna_ai_study_summaries_clean.tsv"
    chip_rowwise = RELEASE_ROOT / "ChIP/chip_rowwise_review.tsv"
    chip_tc = RELEASE_ROOT / "ChIP/chip_target_control_map_review.tsv"

    chip_md_blocks = count_text_marker(chip_md, "## PMID_")
    rna_md_blocks = count_text_marker(rna_md, "## PMID_")
    chip_tsv_rows = count_tsv_rows(chip_tsv)
    rna_tsv_rows = count_tsv_rows(rna_tsv)
    chip_rowwise_rows = count_tsv_rows(chip_rowwise)
    chip_tc_rows = count_tsv_rows(chip_tc)

    lines.append(f"- ChIP markdown PMID blocks: {chip_md_blocks}")
    lines.append(f"- RNA markdown PMID blocks: {rna_md_blocks}")
    lines.append(f"- ChIP study summary TSV rows: {chip_tsv_rows}")
    lines.append(f"- RNA study summary TSV rows: {rna_tsv_rows}")
    lines.append(f"- ChIP rowwise review rows: {chip_rowwise_rows}")
    lines.append(f"- ChIP target-control map rows: {chip_tc_rows}")

    if rna_md_blocks != EXPECTED_COUNTS["rna_markdown_blocks"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['rna_markdown_blocks']} RNA markdown PMID blocks; observed {rna_md_blocks}"
        )
    if rna_tsv_rows != EXPECTED_COUNTS["rna_study_summary_rows"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['rna_study_summary_rows']} RNA study summary TSV rows; observed {rna_tsv_rows}"
        )
    if chip_md_blocks != EXPECTED_COUNTS["chip_markdown_blocks"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['chip_markdown_blocks']} ChIP markdown PMID blocks; observed {chip_md_blocks}"
        )
    if chip_tsv_rows != EXPECTED_COUNTS["chip_study_summary_rows"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['chip_study_summary_rows']} ChIP study summary TSV rows; observed {chip_tsv_rows}"
        )
    if chip_rowwise_rows != EXPECTED_COUNTS["chip_rowwise_rows"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['chip_rowwise_rows']} ChIP rowwise rows; observed {chip_rowwise_rows}"
        )
    if chip_tc_rows != EXPECTED_COUNTS["chip_target_control_rows"]:
        problems.append(
            f"Expected {EXPECTED_COUNTS['chip_target_control_rows']} ChIP target-control rows; observed {chip_tc_rows}"
        )

    lines.append("")
    lines.append("## Zip check")
    lines.append("")

    if zip_path and zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as z:
                bad = z.testzip()
                names = z.namelist()
            if bad:
                lines.append(f"FAIL: zip has bad member: {bad}")
                problems.append(f"Zip test failed at member: {bad}")
            else:
                lines.append(f"PASS: zip opens and contains {len(names)} files.")
        except Exception as e:
            lines.append(f"FAIL: zip could not be read: {e}")
            problems.append(f"Zip unreadable: {e}")
    else:
        lines.append("FAIL: zip path unavailable.")
        problems.append("Zip path unavailable")

    lines.append("")
    lines.append("## Final verdict")
    lines.append("")

    if problems:
        lines.append("FAIL")
        lines.append("")
        for p in problems:
            lines.append(f"- {p}")
    else:
        lines.append("PASS")
        lines.append("")
        lines.append("The final curator release folder is complete and curator-facing.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))

    print(REPORT)
    print("")
    print("\n".join(lines))

    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
