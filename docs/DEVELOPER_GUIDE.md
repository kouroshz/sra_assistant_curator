# Developer Guide

This repository currently contains a working legacy RNA/ChIP curator-assist pipeline plus a production-facing wrapper layer.

## Current development principle

Do not break the working legacy pipeline.

Refactoring should proceed in small steps:

1. Add or move shared helper logic into `src/sra_paper_curator/`.
2. Update only production-layer scripts first.
3. Run the full check suite.
4. Commit only after tests pass.
5. Move legacy scripts only after wrapper parity checks exist.

## One-command validation

Run:

    python scripts/05_run_all_checks.py

This checks:

- Python files compile
- final release can be rebuilt
- final release QC passes
- golden-output regression tests pass
- workflow runner defaults to dry-run
- AI-capable workflow step refuses unsafe execution

## Golden outputs

See:

    docs/GOLDEN_OUTPUTS.md

Current expected values:

- RNA study summaries: 69
- ChIP study summaries: 42
- ChIP rowwise review rows: 733
- ChIP target-control map rows: 490

These are regression checks, not biological claims.

## Production wrapper

Workflow steps are defined in:

    workflows/steps.tsv

Run:

    python workflows/run_workflow_step.py --list

Show a step without running it:

    python workflows/run_workflow_step.py --step 90

All workflow steps are dry-run by default.

## AI safety

AI/API execution must be explicit.

An AI-capable step requires:

    --execute
    --execute-ai
    AGENTIC_AI_ENABLE_API=1

Without these, the wrapper refuses execution.

## Refactoring map

Current active workflow documentation:

    docs/ACTIVE_WORKFLOW_MAP.md

Production reorganization plan:

    docs/PRODUCTION_REORG_PLAN.md

## What not to commit

Do not commit generated outputs:

- `outputs/`
- `results/`
- raw PDFs
- raw AI JSON files
- `.env`
- API keys
- local scratch files

## Current production package

Shared utilities currently live in:

    src/sra_paper_curator/file_utils.py
    src/sra_paper_curator/command_utils.py

The next reasonable extractions are:

- workflow map loading
- release QC constants
- validation helper functions
- ChIP target-control utilities
