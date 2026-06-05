#!/usr/bin/env python3
"""
Run production sanity checks.

Default behavior:
- In a fresh clone without generated outputs, runs repo smoke checks only.
- In a local working tree with generated outputs, also runs artifact-backed release checks.

Use:
    python scripts/05_run_all_checks.py
    python scripts/05_run_all_checks.py --repo-only
    python scripts/05_run_all_checks.py --with-artifacts

No API calls.
No OpenAI key required.
"""

from pathlib import Path
import argparse
import csv
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sra_paper_curator.artifact_checks import missing_release_sources


PYTHON_FILES_TO_COMPILE = [
    "src/sra_paper_curator/__init__.py",
    "src/sra_paper_curator/file_utils.py",
    "src/sra_paper_curator/command_utils.py",
    "src/sra_paper_curator/artifact_checks.py",
    "scripts/02_create_clean_final_release.py",
    "scripts/03_qc_final_release.py",
    "scripts/04_pipeline_readiness_report.py",
    "scripts/05_run_all_checks.py",
    "scripts/06_rerun_readiness_check.py",
    "scripts/06_script_cleanup_inventory.py",
    "scripts/07_classify_unmapped_scripts.py",
    "scripts/15_download_open_access_pdfs.py",
    "scripts/36_build_paper_packet_ai_priority_queue.py",
    "scripts/41_batch_run_agentic_ai_on_trusted_queue.py",
    "scripts/41e_batch_run_trusted_queue_production.py",
    "scripts/62_batch_run_chip_small_packets_production.py",
    "workflows/run_workflow_step.py",
    "tests/test_golden_outputs.py",
]


def run(cmd, *, expect_ok=True, env=None):
    env_full = os.environ.copy()
    if env:
        env_full.update(env)

    print("")
    print("=== RUN ===")
    print(" ".join(cmd))

    p = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env_full,
    )

    print(p.stdout)

    if expect_ok and p.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd)}")

    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-only",
        action="store_true",
        help="Run only checks that should pass in a fresh clone without generated outputs.",
    )
    parser.add_argument(
        "--with-artifacts",
        action="store_true",
        help="Require local generated outputs and run release/golden-output checks.",
    )
    args = parser.parse_args()

    if args.repo_only and args.with_artifacts:
        raise SystemExit("Use only one of --repo-only or --with-artifacts.")

    print("# Running SRA curator production checks")

    run([sys.executable, "-m", "py_compile"] + PYTHON_FILES_TO_COMPILE)

    missing_workflow_scripts = []
    with open(ROOT / "workflows/steps.tsv", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            script = row.get("script", "")
            if script and not (ROOT / script).exists():
                missing_workflow_scripts.append(f"step {row.get('step', '')}: {script}")
    if missing_workflow_scripts:
        print("")
        print("FAILED: workflow map references missing scripts.")
        for item in missing_workflow_scripts:
            print("  - " + item)
        raise SystemExit(1)

    run([sys.executable, "scripts/06_rerun_readiness_check.py"])

    dry = run([sys.executable, "workflows/run_workflow_step.py", "--step", "90"])
    if "DRY-RUN only" not in dry.stdout:
        raise SystemExit("FAILED: workflow step 90 did not default to dry-run")

    unsafe_ai = run(
        [sys.executable, "workflows/run_workflow_step.py", "--step", "33", "--execute"],
        expect_ok=False,
        env={"AGENTIC_AI_ENABLE_API": ""},
    )
    if unsafe_ai.returncode == 0 or "Refusing to execute AI-capable step" not in unsafe_ai.stdout:
        raise SystemExit("FAILED: AI step did not refuse unsafe execution")

    missing = missing_release_sources(ROOT)
    have_artifacts = len(missing) == 0

    if args.with_artifacts and not have_artifacts:
        print("")
        print("FAILED: --with-artifacts was requested, but generated release source artifacts are missing.")
        print("")
        for item in missing:
            print("  - " + item)
        raise SystemExit(1)

    if args.repo_only or not have_artifacts:
        print("")
        print("SKIP: artifact-backed release checks were not run.")
        print("Reason: generated outputs are not present in this checkout.")
        print("")
        print("This is expected in a fresh Git clone because outputs/results are ignored.")
        print("To run full artifact-backed checks on the production machine, use:")
        print("")
        print("  python scripts/05_run_all_checks.py --with-artifacts")
        print("")
        print("PASS: repo smoke checks passed.")
        return

    run([sys.executable, "scripts/02_create_clean_final_release.py"])
    run([sys.executable, "scripts/03_qc_final_release.py"])
    run([sys.executable, "tests/test_golden_outputs.py"])

    print("")
    print("PASS: all production checks passed.")


if __name__ == "__main__":
    main()
