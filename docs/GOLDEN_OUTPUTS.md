# Golden Outputs

These are the current expected outputs for the working RNA/ChIP curator-assist pipeline.

These values are used as regression checks during production cleanup and refactoring.

## Current expected counts

RNA:
- study summaries: 69
- curator workbook exists
- semantic red-flag summary exists

ChIP:
- study summaries: 42
- rowwise review rows: 733
- target-control map rows: 490
- curator workbook exists
- study-summary final QC exists

Final release:
- `results/final_curator_release/` exists after running `scripts/02_create_clean_final_release.py`
- `results/LATEST_FINAL_CURATOR_RELEASE.txt` points to release folder and zip
- final release QC passes
- no raw AI JSON, PDF, `.env`, or key-like files are included

## Safety expectations

- Workflow runner defaults to dry-run.
- AI-capable workflow steps do not execute unless both `--execute-ai` and `AGENTIC_AI_ENABLE_API=1` are present.
- Generated outputs under `outputs/` and `results/` are not tracked by Git.
