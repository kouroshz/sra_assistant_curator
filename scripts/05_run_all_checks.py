#!/usr/bin/env python3
"""
Run production sanity checks.

Default behavior:
- In a fresh clone without generated outputs, runs repo smoke checks only.
- Artifact-backed final release checks run only when --with-artifacts is supplied.

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
    "scripts/64_merge_chip_chunk_outputs.py",
    "scripts/68e_finalize_chip_curator_excel_v5.py",
    "scripts/72c_final_qc_chip_study_summaries.py",
    "scripts/90_show_curator_outputs.py",
    "workflows/run_recipe.py",
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

    run([
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('dl','scripts/15_download_open_access_pdfs.py'); "
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "status, missing=m.output_paths_for_manifest(m.CHIP_PMID_MANIFEST); "
            "assert str(status).endswith('outputs/06_CHIP_AI_ASSIST/07_papers/chip_pdf_download_status.tsv'); "
            "assert str(missing).endswith('outputs/06_CHIP_AI_ASSIST/07_papers/chip_pmids_still_needing_manual_pdf_download.tsv')"
        ),
    ])

    run([
        sys.executable,
        "-c",
        (
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('rr','workflows/run_recipe.py'); "
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "cmd=m.build_commands(m.RECIPES['rna-ai'], execute=True, execute_ai=True)[0]; "
            "assert '--extra-args' in cmd and cmd[-1] == '--execute'; "
            "cmd=m.build_commands(m.RECIPES['chip-ai'], execute=True, execute_ai=True)[0]; "
            "assert '--extra-args' in cmd and cmd[-1] == '--execute'"
        ),
    ])

    run([
        sys.executable,
        "-c",
        (
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('m','scripts/64_merge_chip_chunk_outputs.py'); "
            "mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "assert hasattr(mod, 'infer_chunk_queue'); assert hasattr(mod, 'infer_parent_packet_id')"
        ),
    ])

    run([
        sys.executable,
        "-c",
        (
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('w','scripts/68e_finalize_chip_curator_excel_v5.py'); "
            "mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "assert hasattr(mod, 'build_base_workbook_from_final_qc')"
        ),
    ])

    run([
        sys.executable,
        "-c",
        (
            "import importlib.util; "
            "spec=importlib.util.spec_from_file_location('s','scripts/72c_final_qc_chip_study_summaries.py'); "
            "mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
            "assert hasattr(mod, 'ensure_input_tsv'); "
            "assert hasattr(mod, 'normalize_rows'); "
            "assert 'assay_class' in mod.NORMALIZED_COLUMNS"
        ),
    ])

    run([
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "from dotenv import load_dotenv; "
            "load_dotenv(Path('.env')); "
            "print('dotenv load check: ok (secrets not printed)')"
        ),
    ])

    run([sys.executable, "scripts/06_rerun_readiness_check.py"])

    dry = run([sys.executable, "workflows/run_workflow_step.py", "--step", "90"])
    if "DRY-RUN only" not in dry.stdout:
        raise SystemExit("FAILED: workflow step 90 did not default to dry-run")

    recipes = run([sys.executable, "workflows/run_recipe.py", "list"])
    if "rna-prep" not in recipes.stdout or "chip-prep" not in recipes.stdout:
        raise SystemExit("FAILED: recipe list did not include expected recipes")

    rna_recipe = run([sys.executable, "workflows/run_recipe.py", "rna-prep"])
    if "Range complete: 00 through 05" not in rna_recipe.stdout:
        raise SystemExit("FAILED: rna-prep recipe dry-run did not complete")

    chip_recipe = run([sys.executable, "workflows/run_recipe.py", "chip-prep"])
    if "Range complete: 20 through 32" not in chip_recipe.stdout:
        raise SystemExit("FAILED: chip-prep recipe dry-run did not complete")

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

    if args.repo_only or not args.with_artifacts:
        print("")
        print("SKIP: artifact-backed release checks were not run.")
        if not have_artifacts:
            print("Reason: generated outputs are not present in this checkout.")
        else:
            print("Reason: --with-artifacts was not supplied.")
        print("")
        print("This is expected for routine repo smoke checks; outputs/results are ignored in fresh clones.")
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
