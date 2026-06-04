#!/usr/bin/env python3
"""
Generate a publication-readiness report for the curator pipeline.

This script:
- does not call APIs
- runs final release QC
- runs golden-output tests
- checks workflow/docs/scripts exist
- checks AI execution safety behavior
- writes docs/PIPELINE_READINESS_REPORT.md
"""

from pathlib import Path
from datetime import datetime
import subprocess
import sys


ROOT = Path(".")
REPORT = Path("docs/PIPELINE_READINESS_REPORT.md")


REQUIRED_DOCS = [
    "README.md",
    "docs/ACTIVE_WORKFLOW_MAP.md",
    "docs/PRODUCTION_REORG_PLAN.md",
    "docs/GOLDEN_OUTPUTS.md",
]

REQUIRED_SCRIPTS = [
    "scripts/02_create_clean_final_release.py",
    "scripts/03_qc_final_release.py",
    "scripts/04_pipeline_readiness_report.py",
    "workflows/run_workflow_step.py",
    "workflows/steps.tsv",
    "configs/default.yaml",
    "tests/test_golden_outputs.py",
]


def run_cmd(cmd, allow_fail=False):
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\n\nOutput:\n"
            + p.stdout
        )
    return p.returncode, p.stdout.strip()


def pass_fail(ok):
    return "PASS" if ok else "FAIL"


def file_exists_nonempty(path):
    p = Path(path)
    return p.exists() and p.is_file() and p.stat().st_size > 0


def main():
    lines = []
    problems = []

    lines.append("# Pipeline Readiness Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("This report summarizes whether the current production-reorg branch is ready for controlled use and further refactoring.")
    lines.append("")

    # Git state
    _, branch = run_cmd(["git", "branch", "--show-current"], allow_fail=True)
    _, commit = run_cmd(["git", "log", "-1", "--oneline"], allow_fail=True)
    _, status = run_cmd(["git", "status", "--short"], allow_fail=True)

    lines.append("## Git state")
    lines.append("")
    lines.append(f"- branch: `{branch}`")
    lines.append(f"- latest commit: `{commit}`")
    if status:
        lines.append("- working tree: DIRTY")
        lines.append("")
        lines.append("Uncommitted changes:")
        lines.append("")
        for s in status.splitlines():
            lines.append(f"- `{s}`")
        problems.append("Working tree has uncommitted changes.")
    else:
        lines.append("- working tree: clean")
    lines.append("")

    # Required files
    lines.append("## Required tracked files")
    lines.append("")
    for path in REQUIRED_DOCS + REQUIRED_SCRIPTS:
        ok = file_exists_nonempty(path)
        lines.append(f"- {pass_fail(ok)} `{path}`")
        if not ok:
            problems.append(f"Missing or empty required file: {path}")
    lines.append("")

    # Final release QC
    lines.append("## Final release QC")
    lines.append("")
    qc_code, qc_out = run_cmd([sys.executable, "scripts/03_qc_final_release.py"], allow_fail=True)
    if qc_code == 0:
        lines.append("- PASS `scripts/03_qc_final_release.py`")
    else:
        lines.append("- FAIL `scripts/03_qc_final_release.py`")
        problems.append("Final release QC failed.")
    lines.append("")
    lines.append("Final release QC output excerpt:")
    lines.append("")
    for line in qc_out.splitlines()[-20:]:
        lines.append(f"    {line}")
    lines.append("")

    # Golden tests
    lines.append("## Golden-output regression tests")
    lines.append("")
    test_code, test_out = run_cmd([sys.executable, "tests/test_golden_outputs.py"], allow_fail=True)
    if test_code == 0:
        lines.append("- PASS `tests/test_golden_outputs.py`")
    else:
        lines.append("- FAIL `tests/test_golden_outputs.py`")
        problems.append("Golden-output tests failed.")
    lines.append("")
    lines.append("Test output excerpt:")
    lines.append("")
    for line in test_out.splitlines()[-20:]:
        lines.append(f"    {line}")
    lines.append("")

    # Workflow wrapper safety
    lines.append("## Workflow wrapper safety")
    lines.append("")

    dry_code, dry_out = run_cmd([sys.executable, "workflows/run_workflow_step.py", "--step", "90"], allow_fail=True)
    dry_ok = dry_code == 0 and "DRY-RUN only" in dry_out
    lines.append(f"- {pass_fail(dry_ok)} non-AI step defaults to dry-run")
    if not dry_ok:
        problems.append("Workflow step 90 did not default to dry-run.")

    ai_code, ai_out = run_cmd([sys.executable, "workflows/run_workflow_step.py", "--step", "33", "--execute"], allow_fail=True)
    ai_ok = ai_code != 0 and "Refusing to execute AI-capable step" in ai_out
    lines.append(f"- {pass_fail(ai_ok)} AI-capable step refuses execution without --execute-ai")
    if not ai_ok:
        problems.append("AI-capable workflow step did not refuse unsafe execution.")

    lines.append("")

    # Final release presence
    lines.append("## Clean final release")
    lines.append("")
    release_pointer = Path("results/LATEST_FINAL_CURATOR_RELEASE.txt")
    if release_pointer.exists():
        pointer_lines = release_pointer.read_text().strip().splitlines()
        lines.append(f"- PASS latest release pointer exists: `{release_pointer}`")
        for item in pointer_lines:
            lines.append(f"  - `{item}`")
    else:
        lines.append(f"- FAIL latest release pointer missing: `{release_pointer}`")
        problems.append("Latest final release pointer is missing.")
    lines.append("")

    # Technical debt
    lines.append("## Remaining technical debt")
    lines.append("")
    lines.append("The current pipeline is usable and protected by regression checks, but it is not fully publication-quality yet.")
    lines.append("")
    lines.append("Remaining cleanup:")
    lines.append("")
    lines.append("1. Move shared helpers into `src/sra_paper_curator/`.")
    lines.append("2. Replace legacy numbered scripts with stable workflow names.")
    lines.append("3. Move superseded scripts into `legacy_scripts/` only after parity checks pass.")
    lines.append("4. Add developer-facing documentation for publication resolution, AI prompt contracts, validation, and repairs.")
    lines.append("5. Add smaller unit tests for validators and ChIP target-control logic.")
    lines.append("6. Add CI or a single reproducibility command for local validation.")
    lines.append("")

    # Verdict
    lines.append("## Final verdict")
    lines.append("")
    if problems:
        lines.append("FAIL / REVIEW")
        lines.append("")
        for p in problems:
            lines.append(f"- {p}")
    else:
        lines.append("PASS")
        lines.append("")
        lines.append("The current production-reorg branch has a clean final release, passing release QC, passing golden-output tests, and safe default behavior for AI-capable steps.")
        lines.append("")
        lines.append("It is ready for controlled internal use and for the next refactoring phase.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))

    print(REPORT)
    print("")
    print("\n".join(lines))

    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
