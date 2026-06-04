# Workflow wrappers

This folder defines the production-facing workflow sequence.

The current implementation is a wrapper layer around the legacy scripts in scripts/.
Legacy scripts are not deleted or moved until wrapper parity tests pass.

Core rule: API/AI execution is off by default.

List workflow steps:
    python workflows/run_workflow_step.py --list

Show one step:
    python workflows/run_workflow_step.py --step 41

Dry-run one step:
    python workflows/run_workflow_step.py --step 90

Execute one non-AI step:
    python workflows/run_workflow_step.py --step 90 --execute

Execute an AI step:
    AGENTIC_AI_ENABLE_API=1 python workflows/run_workflow_step.py --step 33 --execute --execute-ai

Use AI steps only after preflight/QC has passed.
