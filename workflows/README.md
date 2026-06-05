# Workflow Wrapper

This folder contains the production-facing workflow map and safe runner for the SRA Paper Curator pipeline.

The wrapper provides a stable interface around the active workflow scripts in scripts/.

---

## Files

    workflows/steps.tsv
    workflows/final_outputs.tsv
    workflows/run_workflow_step.py

Purpose:

- steps.tsv: machine-readable workflow step map
- final_outputs.tsv: expected final output map
- run_workflow_step.py: dry-run-first execution wrapper

---

## List workflow steps

    python workflows/run_workflow_step.py --list

---

## Show one step without running it

    python workflows/run_workflow_step.py --step 90

All workflow steps are dry-run by default.

---

## Execute a non-AI step

    python workflows/run_workflow_step.py --step 90 --execute

---

## Execute an AI-capable step

AI/API execution requires explicit opt-in:

    AGENTIC_AI_ENABLE_API=1 python workflows/run_workflow_step.py --step 33 --execute --execute-ai

The runner refuses to execute AI-capable steps unless both are present:

    --execute-ai
    AGENTIC_AI_ENABLE_API=1

---

## Validation

Fresh-clone smoke check:

    python scripts/05_run_all_checks.py

Artifact-backed production check:

    python scripts/05_run_all_checks.py --with-artifacts

Readiness report:

    python scripts/04_pipeline_readiness_report.py

---

## Design principle

The wrapper is intentionally conservative:

- dry-run by default
- AI off by default
- script purpose and inputs/outputs visible before execution
- active workflow scripts preserved until refactoring has parity tests
