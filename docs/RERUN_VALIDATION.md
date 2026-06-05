# Rerun Validation Guide

This guide is for a new publication/reviewer user running the RNA + ChIP curator workflow from local input workbooks. Commands are shown from the repository root.

## Recipe-Based Path

For routine reruns, start with named recipes:

```bash
python workflows/run_recipe.py list
python workflows/run_recipe.py rna-prep --execute
python workflows/run_recipe.py chip-prep --execute
python workflows/run_recipe.py show-outputs
```

`rna-prep` builds RNA metadata and paper packets up to the AI queue. `chip-prep` builds ChIP publication links, downloads available papers, builds AI packets, and preflights them. Final Excel/Markdown outputs require completed AI/post-AI validation/finalization or an existing generated release.

The detailed step numbers below are retained for auditability and exact rerun control. Internal step namespaces are:

```text
00-15  RNA and shared RNA preparation/validation/finalization
20-43  ChIP preparation/AI validation/finalization
90+    release and output helper steps
```

## 1. Create The Environment

```bash
conda env create -f environment.yml
conda activate sra_paper_curator
python scripts/06_rerun_readiness_check.py
```

The readiness check is non-mutating. A `REVIEW` verdict is expected until the required local workbooks are placed under `data/`.

## 2. Place Local Input Workbooks

Required paths:

```text
data/rna_seq_metadata_2026-05-05_original.xlsx
data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

See `docs/LOCAL_INPUTS.md` for copy and symlink examples.

## 3. Optional Cache And Paper Preparation

Public metadata and paper-download steps use NCBI/E-utilities. Set a local contact email before larger reruns:

```bash
cp .env.example .env
```

Then edit `.env` locally:

```text
NCBI_EMAIL=you@example.org
NCBI_TOOL=sra_paper_curator
NCBI_API_KEY=
```

`NCBI_API_KEY` is optional. `OPENAI_API_KEY` is only needed for AI steps, and `AGENTIC_AI_ENABLE_API` should stay `0` unless intentionally running AI.

Metadata caches are optional but speed up reruns:

```text
data/sra_runinfo_cache/
data/biosample_cache/
```

Papers are not committed. Prepare local paper PDFs/text under:

```text
papers/
```

Do not replace the `papers/` directory itself with a symlink. Keep the tracked placeholder files:

```text
papers/.gitkeep
papers/README_PAPERS.md
```

Preferred options:

1. Copy PDFs into `papers/`.
2. Symlink individual PDF files into `papers/`.

Example:

```bash
mkdir -p papers
ln -s /absolute/path/to/paper_pdfs/*.pdf papers/
```

If testing with no papers, leave `papers/` as-is with only the placeholder files.

RNA packet construction can run without PDFs, but real AI execution should wait until papers are downloaded or prepared. The deterministic priority queue records local PDF availability.

## 4. Inspect Workflow Steps

```bash
python workflows/run_workflow_step.py --list
python workflows/run_workflow_step.py --step 04b
```

Dry-run output shows the current script, API status, inputs, outputs, and command.

## 5. RNA Deterministic Rerun Through Step 05

Run deterministic RNA setup and queue construction:

```bash
python workflows/run_workflow_step.py --continue-from 00 --through 05 --execute
```

Important generated products include:

```text
outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv
outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv
outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv
outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv
outputs/02_QC_SUMMARIES/held_or_unresolved_pmid_packets.tsv
outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv
outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv
```

Step 01 uses public NCBI/SRA/BioSample metadata and may use local caches. It does not call OpenAI.

No-papers mode is supported through RNA Step 05. The trusted queue builds, but all packets defer because `paper_pdf_count=0`.

## 6. RNA AI Boundary

AI is optional and off by default. Deterministic reruns do not need API configuration.

For real AI-assisted steps, use exported environment variables or a local `.env` copied from the safe example:

```bash
cp .env.example .env
```

Fill `OPENAI_API_KEY` locally in `.env`. `OPENAI_MODEL` and `OPENAI_SMALL_MODEL` are optional local overrides. Keep `AGENTIC_AI_ENABLE_API=0` until intentionally running API-enabled steps, then set `AGENTIC_AI_ENABLE_API=1` for that run. Never commit `.env`.

RNA AI-related steps:

```text
06 shared one-packet AI runner
07 RNA trusted batch AI runner
```

AI-capable workflow execution requires:

```bash
AGENTIC_AI_ENABLE_API=1 \
python workflows/run_workflow_step.py --step 07 --execute --execute-ai
```

The workflow wrapper refuses AI-capable execution without `--execute --execute-ai` and `AGENTIC_AI_ENABLE_API=1`. Batch runners also refuse `--execute` without `OPENAI_API_KEY`. The key can come from `.env` or exported shell variables and is never printed.

## 7. Post-AI Deterministic RNA Steps

After AI JSONs exist, continue deterministic validation, repair, inventory, semantic review, summaries, and curator workbook generation:

```bash
python workflows/run_workflow_step.py --continue-from 08 --through 15 --execute
```

Do not edit curator-facing Excel formatting logic during rerun validation.

## 8. ChIP Deterministic Steps And AI Boundary

ChIP deterministic preparation starts at step 20:

```bash
python workflows/run_workflow_step.py --continue-from 20 --through 32 --execute
```

Step 28 may download open-access papers using public web/NCBI/PMC routes; it is not an OpenAI step. By default, Step 28 uses the ChIP manifest prepared by Step 27:

```text
outputs/06_CHIP_AI_ASSIST/07_papers/chip_pmids_needing_pdfs_for_downloader.tsv
```

With that manifest, Step 28 writes the ChIP-specific files consumed by Step 29:

```text
outputs/06_CHIP_AI_ASSIST/07_papers/chip_pdf_download_status.tsv
outputs/06_CHIP_AI_ASSIST/07_papers/chip_pmids_still_needing_manual_pdf_download.tsv
```

To use a different PMID download manifest, keep the workflow wrapper and pass an explicit override:

```bash
python workflows/run_workflow_step.py --step 28 --execute --extra-args --pmids-file path/to/pmids.tsv
```

`no_open_access_pdf_found` is not fatal. It is recorded as missing/manual paper status and carried forward into paper availability review. Groups with no PMID or unresolved publication remain held or excluded from AI-ready queues so paper-aware AI is limited to publication-linked data.

ChIP AI starts at step 33 and has the same API boundary:

```bash
AGENTIC_AI_ENABLE_API=1 \
python workflows/run_workflow_step.py --step 33 --execute --execute-ai
```

Post-AI ChIP validation, repair, inventory, final QC, workbook generation, and companion exports run through steps 36-43.

## 9. Final Release Packaging

After RNA and ChIP curator outputs are available:

```bash
python workflows/run_workflow_step.py --step 90 --execute
python scripts/03_qc_final_release.py
```

The final package excludes raw PDFs, `.env`, keys, raw AI JSONs, and bulky intermediates.

## 10. Finding The Final Outputs

Print the current curator-facing output locations:

```bash
python scripts/90_show_curator_outputs.py
```

The expected final release paths are:

```text
results/final_curator_release/RNA/RNA_curator_review.xlsx
results/final_curator_release/ChIP/ChIP_curator_review.xlsx
results/final_curator_release/RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md
results/final_curator_release/ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md
```

The same release folder also contains clean summary TSVs, QC reports, a manifest, and release README.

## 11. Sanity Counts From Current Production State

These are regression sanity checks from the current production artifacts, not biological claims:

```text
RNA study summary PMID blocks: 69
RNA study summary TSV rows: 69
ChIP study summary PMID blocks: 42
ChIP study summary TSV rows: 42
ChIP rowwise review rows: 733
ChIP target-control map rows: 490
Golden-output tests: 7 passing tests
```

Counts may legitimately change after a fresh rerun if input workbooks, paper availability, or curation policy changes. Any change should be explained in the rerun notes.

## 12. Final Validation Commands

```bash
python scripts/05_run_all_checks.py
python scripts/04_pipeline_readiness_report.py
python workflows/run_workflow_step.py --list
```

In a fresh clone without generated outputs, artifact-backed checks are skipped. On a production machine with generated artifacts, the checks also validate the final release and golden-output counts.
