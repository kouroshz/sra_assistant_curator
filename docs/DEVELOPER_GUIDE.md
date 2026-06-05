# Developer Guide

This guide explains how to work on the SRA Paper Curator repository without breaking the current production workflow.

---

## Core development rule

Do not break the working pipeline.

Recommended pattern:

1. Make a small change.
2. Run the check suite.
3. Commit only after tests pass.
4. Avoid moving active workflow scripts unless wrapper parity tests exist.
5. Keep AI/API execution off by default.

---

## Environment

Create the conda environment:

    conda env create -f environment.yml
    conda activate sra_paper_curator

The environment uses Python 3.11.

---

## Validation commands

Fresh clone or repo-level smoke check:

    python scripts/05_run_all_checks.py

Artifact-backed validation on a machine with generated outputs:

    python scripts/05_run_all_checks.py --with-artifacts

Pipeline readiness report:

    python scripts/04_pipeline_readiness_report.py

---

## Production wrapper

Workflow steps are defined in:

    workflows/steps.tsv

List steps:

    python workflows/run_workflow_step.py --list

Show one step:

    python workflows/run_workflow_step.py --step 90

Run a non-AI step:

    python workflows/run_workflow_step.py --step 90 --execute

Run an AI-capable step:

    AGENTIC_AI_ENABLE_API=1 python workflows/run_workflow_step.py --step 33 --execute --execute-ai

---

## AI safety

AI/API execution requires all of:

    --execute
    --execute-ai
    AGENTIC_AI_ENABLE_API=1

Without these, AI-capable workflow steps refuse execution.

---

## Golden outputs

See:

    docs/GOLDEN_OUTPUTS.md
    tests/test_golden_outputs.py

Current expected values:

    RNA study summaries: 69
    ChIP study summaries: 42
    ChIP rowwise review rows: 733
    ChIP target-control map rows: 490

These are regression checks, not biological claims.

---

## Shared package code

Reusable production utilities live in:

    src/sra_paper_curator/

Current modules:

    artifact_checks.py
    command_utils.py
    file_utils.py

Future extraction candidates:

- workflow map loading
- validation helper functions
- release QC constants
- ChIP target-control utilities
- publication-resolution helpers

---

## What not to commit

Do not commit:

    outputs/
    results/
    local_scratch/
    .env
    API keys
    raw PDFs
    raw AI JSON files
    bulky generated intermediates

---

## Documentation map

Useful documentation:

    README.md
    docs/REVIEWER_GUIDE.md
    docs/CURATOR_GUIDE.md
    docs/ACTIVE_WORKFLOW_MAP.md
    docs/PRODUCTION_REORG_PLAN.md
    docs/PIPELINE_READINESS_REPORT.md
    workflows/README.md

---

## Next development phase

The next high-value phase is controlled end-to-end rerun testing:

1. deterministic rerun without AI
2. regeneration of packets and evidence tables
3. final release regeneration
4. comparison to golden outputs
5. small controlled AI rerun only after deterministic checks pass
