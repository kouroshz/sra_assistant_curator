# SRA Paper Curator

A curator-assistance workflow for turning public SRA/GEO metadata plus paper context into reviewer-facing RNA-seq and ChIP-seq curation outputs for Plasmodium sequencing studies.

The workflow is built around deterministic metadata processing, validation, audit trails, and human curator review. AI can optionally assist with paper interpretation, but it is off by default and never bypasses deterministic checks.

## What You Need

Required local workbooks:

```text
data/rna_seq_metadata_2026-05-05_original.xlsx
data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

These workbooks, generated outputs, downloaded papers, caches, API JSONs, final Excel workbooks, and release zips are intentionally not committed.

Optional local inputs:

- `papers/*.pdf` for paper-aware AI review
- `data/sra_runinfo_cache/` and `data/biosample_cache/` to speed reruns
- `.env` copied from `.env.example` for local NCBI/OpenAI configuration

Do not replace the tracked `papers/` directory with a symlink. Copy PDFs into it or symlink individual PDF files inside it.

## What It Produces

Final curator-facing outputs are packaged under:

```text
results/final_curator_release/
```

Key outputs:

```text
results/final_curator_release/RNA/RNA_curator_review.xlsx
results/final_curator_release/ChIP/ChIP_curator_review.xlsx
results/final_curator_release/RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md
results/final_curator_release/ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md
results/final_curator_release/RNA/rna_ai_study_summaries_clean.tsv
results/final_curator_release/ChIP/chip_ai_study_summaries_clean.tsv
results/final_curator_release/QC/FINAL_RELEASE_QC_REPORT.md
results/final_curator_release_*.zip
```

To find current outputs:

```bash
python scripts/90_show_curator_outputs.py
```

## Deterministic Vs Optional AI

Deterministic steps:

- build stable rowwise evidence
- fetch/cache public SRA/BioSample/Entrez metadata
- resolve publication links
- prepare paper/PDF manifests
- build AI-ready queues and packets
- validate AI outputs structurally
- build curator workbooks, summaries, QC reports, and final release bundles

Optional AI steps:

- RNA AI packet/batch review
- ChIP AI packet/batch review

AI/API execution requires explicit opt-in with `--execute --execute-ai` and `AGENTIC_AI_ENABLE_API=1`. `OPENAI_API_KEY` is needed only for real AI runs.

## Quick Start

Create or update the environment:

```bash
# First-time setup
conda env create -f environment.yml
conda activate sra_paper_curator

# To update an existing environment later
conda env update -n sra_paper_curator -f environment.yml --prune
```

Place or symlink the input workbooks:

```bash
mkdir -p data
ln -s /absolute/path/to/rna_seq_metadata_2026-05-05_original.xlsx data/rna_seq_metadata_2026-05-05_original.xlsx
ln -s /absolute/path/to/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

Create local config:

```bash
cp .env.example .env
```

Set `NCBI_EMAIL` in `.env` for public metadata and paper-download steps. Keep `AGENTIC_AI_ENABLE_API=0` unless intentionally running AI.

Run readiness and smoke checks:

```bash
python scripts/06_rerun_readiness_check.py
python scripts/05_run_all_checks.py
```

Run RNA deterministic setup to the AI boundary:

```bash
python workflows/run_workflow_step.py --continue-from 00 --through 05 --execute
```

No-papers mode is supported through RNA Step 05; the trusted queue builds, but packets defer when `paper_pdf_count=0`.

Run ChIP deterministic setup to the AI boundary:

```bash
python workflows/run_workflow_step.py --continue-from 20 --through 32 --execute
```

After AI/post-AI validation and finalization have completed, or when inspecting an existing generated release, find or package curator outputs:

```bash
python scripts/90_show_curator_outputs.py
python workflows/run_workflow_step.py --step 90 --execute
```

## Full Rerun With API

API is off by default. Never commit `.env`.

For intentional AI-enabled runs:

```bash
cp .env.example .env
```

Edit `.env` locally:

```text
OPENAI_API_KEY=your-local-key
AGENTIC_AI_ENABLE_API=1
```

Then use workflow commands with both `--execute` and `--execute-ai`.

RNA AI steps:

```text
06  one-packet AI runner
07  RNA trusted batch AI runner
```

ChIP AI step:

```text
33  ChIP small-packet AI batch runner
```

Examples:

```bash
python workflows/run_workflow_step.py --step 07 --execute --execute-ai
python workflows/run_workflow_step.py --step 33 --execute --execute-ai
```

After AI JSONs exist, continue the deterministic validation, repair, inventory, workbook, summary, and release-generation steps. See `docs/RERUN_VALIDATION.md` for the full RNA and ChIP command sequence, including ChIP chunked-packet handling.

## Key Commands

List workflow steps:

```bash
python workflows/run_workflow_step.py --list
```

Dry-run one step:

```bash
python workflows/run_workflow_step.py --step 28
```

Run a deterministic range:

```bash
python workflows/run_workflow_step.py --continue-from 20 --through 32 --execute
```

Package final outputs:

```bash
python workflows/run_workflow_step.py --step 90 --execute
```

Show final output paths:

```bash
python scripts/90_show_curator_outputs.py --with-open-command
```

## Documentation

- `docs/LOCAL_INPUTS.md`: required local files, papers directory rules, cache notes
- `docs/RERUN_VALIDATION.md`: practical rerun procedure and validation checkpoints
- `docs/API_ASSIST_OPTIONAL_SETUP.md`: optional API setup details
- `workflows/steps.tsv`: authoritative workflow step map
- `docs/CURATOR_GUIDE.md`: curator-facing review notes
- `docs/GOLDEN_OUTPUTS.md`: regression-count expectations

## Repository Layout

```text
configs/
data/            local inputs and caches; most files ignored
docs/
legacy_scripts/
outputs/         generated; ignored
papers/          local PDFs; ignored except placeholders
results/         final release artifacts; ignored
scripts/
src/sra_paper_curator/
tests/
workflows/
```

## Safety Model

- No OpenAI calls are made by default.
- Workflow execution is dry-run by default.
- AI-capable steps require `--execute --execute-ai` plus `AGENTIC_AI_ENABLE_API=1`.
- API keys and `.env` are ignored by Git.
- Final packaging excludes raw PDFs, `.env`, keys, raw AI JSONs, and bulky intermediates.
- Curator Excel formatting scripts should not be edited during rerun validation.

Human curator review remains authoritative.
