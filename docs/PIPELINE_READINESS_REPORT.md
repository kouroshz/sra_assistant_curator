# Pipeline Readiness Report

Generated: 2026-06-04T19:46:03

This report summarizes whether the current branch is ready for controlled use and further refactoring.

## Git state

- branch: `main`
- latest commit: `c13a16a Merge pull request #1 from kouroshz/production-reorg`
- working tree: clean

## Required tracked files

- PASS `README.md`
- PASS `docs/ACTIVE_WORKFLOW_MAP.md`
- PASS `docs/PRODUCTION_REORG_PLAN.md`
- PASS `docs/GOLDEN_OUTPUTS.md`
- PASS `scripts/02_create_clean_final_release.py`
- PASS `scripts/03_qc_final_release.py`
- PASS `scripts/04_pipeline_readiness_report.py`
- PASS `workflows/run_workflow_step.py`
- PASS `workflows/steps.tsv`
- PASS `configs/default.yaml`
- PASS `tests/test_golden_outputs.py`

## Local generated artifact availability

- PASS generated release source artifacts are available.

## Final release QC

- PASS `scripts/03_qc_final_release.py`

Final release QC output excerpt:

    PASS: no forbidden raw JSON/PDF/env/key-like files found.
    
    ## Content checks
    
    - ChIP markdown PMID blocks: 42
    - RNA markdown PMID blocks: 69
    - ChIP study summary TSV rows: 42
    - RNA study summary TSV rows: 69
    - ChIP rowwise review rows: 733
    - ChIP target-control map rows: 490
    
    ## Zip check
    
    PASS: zip opens and contains 16 files.
    
    ## Final verdict
    
    PASS
    
    The final curator release folder is complete and curator-facing.

## Golden-output regression tests

- PASS `tests/test_golden_outputs.py`

Test output excerpt:

    test_ai_step_requires_execute_ai (__main__.TestGoldenOutputs.test_ai_step_requires_execute_ai) ... ok
    test_expected_row_counts (__main__.TestGoldenOutputs.test_expected_row_counts) ... ok
    test_final_release_required_files_exist (__main__.TestGoldenOutputs.test_final_release_required_files_exist) ... ok
    test_latest_pointer_and_zip (__main__.TestGoldenOutputs.test_latest_pointer_and_zip) ... ok
    test_markdown_summary_counts (__main__.TestGoldenOutputs.test_markdown_summary_counts) ... ok
    test_no_forbidden_files_in_release (__main__.TestGoldenOutputs.test_no_forbidden_files_in_release) ... ok
    test_workflow_runner_dry_run_default (__main__.TestGoldenOutputs.test_workflow_runner_dry_run_default) ... ok
    
    ----------------------------------------------------------------------
    Ran 7 tests in 0.202s
    
    OK

## Workflow wrapper safety

- PASS non-AI step defaults to dry-run
- PASS AI-capable step refuses execution without --execute-ai

## Clean final release

- PASS latest release pointer exists: `results/LATEST_FINAL_CURATOR_RELEASE.txt`
  - `results/final_curator_release`
  - `results/final_curator_release_20260604_194603.zip`

## Remaining technical debt

The current pipeline is usable and protected by regression checks, but further end-to-end rerun testing is still needed.

Remaining cleanup:

1. Move more shared helpers into `src/sra_paper_curator/`.
2. Replace legacy numbered scripts with stable workflow names.
3. Add developer-facing documentation for publication resolution, AI prompt contracts, validation, and repairs.
4. Add smaller unit tests for validators and ChIP target-control logic.
5. Run controlled end-to-end rerun tests from raw/local inputs.

## Final verdict

PASS

The current branch has a clean final release, passing release QC, passing golden-output tests, and safe default behavior for AI-capable steps.

It is ready for controlled internal use and for the next refactoring/testing phase.