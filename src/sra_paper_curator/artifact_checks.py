"""Helpers for detecting whether local generated artifacts are available."""

from __future__ import annotations

from pathlib import Path


RNA_WORKBOOK_GLOBS = [
    "outputs/04_AGENTIC_AI_ASSIST/curator_share/trusted_rna_*/curator_review_*.xlsx",
    "outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_*.xlsx",
]

CHIP_WORKBOOK_POINTER = "outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt"
CHIP_WORKBOOK_GLOB = "outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_v5_*.xlsx"

REQUIRED_RELEASE_SOURCE_FILES = [
    "outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES_CLEAN.md",
    "outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv",
    "outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_CLEAN.md",
    "outputs/06_CHIP_AI_ASSIST/23_study_summaries/chip_ai_study_summaries_clean.tsv",
    "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv",
    "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv",
    "outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md",
    "outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md",
    "outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md",
]


def any_glob(root: str | Path, patterns: list[str]) -> bool:
    root = Path(root)
    return any(list(root.glob(pattern)) for pattern in patterns)


def missing_release_sources(root: str | Path = ".") -> list[str]:
    root = Path(root)
    missing = []

    if not any_glob(root, RNA_WORKBOOK_GLOBS):
        missing.append("RNA curator workbook matching one of: " + ", ".join(RNA_WORKBOOK_GLOBS))

    chip_pointer = root / CHIP_WORKBOOK_POINTER
    chip_glob_hits = list(root.glob(CHIP_WORKBOOK_GLOB))
    if not chip_pointer.exists() and not chip_glob_hits:
        missing.append(
            f"ChIP curator workbook pointer `{CHIP_WORKBOOK_POINTER}` "
            f"or workbook matching `{CHIP_WORKBOOK_GLOB}`"
        )

    for rel in REQUIRED_RELEASE_SOURCE_FILES:
        if not (root / rel).exists():
            missing.append(rel)

    return missing


def release_sources_available(root: str | Path = ".") -> bool:
    return len(missing_release_sources(root)) == 0
