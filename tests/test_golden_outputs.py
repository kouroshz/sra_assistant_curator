#!/usr/bin/env python3
"""
Golden-output regression checks for the curator-assist pipeline.

These tests are intentionally high-level. They verify that the current
working RNA/ChIP pipeline still produces the expected final release products.

Run:

    python tests/test_golden_outputs.py

or, if pytest is installed:

    pytest tests/test_golden_outputs.py
"""

from pathlib import Path
import csv
import os
import subprocess
import sys
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "results/final_curator_release"
LATEST_POINTER = ROOT / "results/LATEST_FINAL_CURATOR_RELEASE.txt"


EXPECTED = {
    "rna_study_summary_rows": 69,
    "chip_study_summary_rows": 42,
    "chip_rowwise_rows": 733,
    "chip_target_control_rows": 490,
}


def run_cmd(args, expect_ok=True, env=None):
    env_full = os.environ.copy()
    if env:
        env_full.update(env)

    p = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env_full,
    )

    if expect_ok and p.returncode != 0:
        raise AssertionError(
            "Command failed with code "
            + str(p.returncode)
            + "\nCommand: "
            + " ".join(args)
            + "\nOutput:\n"
            + p.stdout
        )

    return p


def count_tsv_rows(path):
    with open(path, newline="", errors="ignore") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return max(len(rows) - 1, 0)


def count_marker(path, marker):
    return path.read_text(errors="ignore").count(marker)


class TestGoldenOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_cmd([sys.executable, "scripts/02_create_clean_final_release.py"])
        run_cmd([sys.executable, "scripts/03_qc_final_release.py"])

    def test_final_release_required_files_exist(self):
        required = [
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
        ]

        for rel in required:
            p = RELEASE_ROOT / rel
            self.assertTrue(p.exists(), f"Missing required release file: {rel}")
            self.assertGreater(p.stat().st_size, 0, f"Empty required release file: {rel}")

    def test_expected_row_counts(self):
        self.assertEqual(
            count_tsv_rows(RELEASE_ROOT / "RNA/rna_ai_study_summaries_clean.tsv"),
            EXPECTED["rna_study_summary_rows"],
        )
        self.assertEqual(
            count_tsv_rows(RELEASE_ROOT / "ChIP/chip_ai_study_summaries_clean.tsv"),
            EXPECTED["chip_study_summary_rows"],
        )
        self.assertEqual(
            count_tsv_rows(RELEASE_ROOT / "ChIP/chip_rowwise_review.tsv"),
            EXPECTED["chip_rowwise_rows"],
        )
        self.assertEqual(
            count_tsv_rows(RELEASE_ROOT / "ChIP/chip_target_control_map_review.tsv"),
            EXPECTED["chip_target_control_rows"],
        )

    def test_markdown_summary_counts(self):
        self.assertEqual(
            count_marker(RELEASE_ROOT / "ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md", "## PMID_"),
            EXPECTED["chip_study_summary_rows"],
        )
        self.assertEqual(
            count_marker(RELEASE_ROOT / "RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md", "## PMID_"),
            EXPECTED["rna_study_summary_rows"],
        )

    def test_no_forbidden_files_in_release(self):
        forbidden_suffixes = [".json", ".pdf", ".env", ".key", ".pem"]
        forbidden_name_parts = ["openai", "api_key", "raw_ai", "packet_json"]

        hits = []
        for p in RELEASE_ROOT.rglob("*"):
            if not p.is_file():
                continue
            name = p.name.lower()
            if any(name.endswith(s) for s in forbidden_suffixes):
                hits.append(str(p))
            if any(part in name for part in forbidden_name_parts):
                hits.append(str(p))

        self.assertEqual(hits, [])

    def test_latest_pointer_and_zip(self):
        self.assertTrue(LATEST_POINTER.exists(), "Missing latest release pointer")

        lines = LATEST_POINTER.read_text().strip().splitlines()
        self.assertGreaterEqual(len(lines), 2)

        release_dir = ROOT / lines[0]
        zip_path = ROOT / lines[1]

        self.assertTrue(release_dir.exists(), f"Release dir missing: {release_dir}")
        self.assertTrue(zip_path.exists(), f"Release zip missing: {zip_path}")

        with zipfile.ZipFile(zip_path) as z:
            self.assertIsNone(z.testzip())
            self.assertGreater(len(z.namelist()), 0)

    def test_workflow_runner_dry_run_default(self):
        p = run_cmd([sys.executable, "workflows/run_workflow_step.py", "--step", "90"])
        self.assertIn("DRY-RUN only", p.stdout)

    def test_ai_step_requires_execute_ai(self):
        p = run_cmd(
            [sys.executable, "workflows/run_workflow_step.py", "--step", "33", "--execute"],
            expect_ok=False,
            env={"AGENTIC_AI_ENABLE_API": ""},
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Refusing to execute AI-capable step", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
