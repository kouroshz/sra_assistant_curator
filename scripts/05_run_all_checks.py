#!/usr/bin/env python3
"""
Run the production sanity-check suite.

This is the one-command local validation entry point.

It does not call APIs.
It does not require OpenAI keys.
It only regenerates ignored release artifacts under results/.
It does not modify tracked documentation.

Checks:
- production Python files compile
- clean final release can be rebuilt
- final release QC passes
- golden-output regression tests pass
- workflow wrapper defaults to dry-run
- AI-capable workflow step refuses unsafe execution
"""

from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


PYTHON_FILES_TO_COMPILE = [
    "src/sra_paper_curator/__init__.py",
    "src/sra_paper_curator/file_utils.py",
    "src/sra_paper_curator/command_utils.py",
    "scripts/02_create_clean_final_release.py",
    "scripts/03_qc_final_release.py",
    "scripts/04_pipeline_readiness_report.py",
    "scripts/05_run_all_checks.py",
    "scripts/06_script_cleanup_inventory.py",
    "scripts/07_classify_unmapped_scripts.py",
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
    print("# Running SRA curator production checks")

    compile_cmd = [sys.executable, "-m", "py_compile"] + PYTHON_FILES_TO_COMPILE
    run(compile_cmd)

    run([sys.executable, "scripts/02_create_clean_final_release.py"])
    run([sys.executable, "scripts/03_qc_final_release.py"])
    run([sys.executable, "tests/test_golden_outputs.py"])

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

    print("")
    print("PASS: all production checks passed.")
    print("")
    print("Useful follow-up:")
    print("  python scripts/04_pipeline_readiness_report.py")
    print("  cat docs/PIPELINE_READINESS_REPORT.md")


if __name__ == "__main__":
    main()
