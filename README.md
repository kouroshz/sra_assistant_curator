# SRA Assistant Curator

A reproducible pipeline for turning a master RNA-seq/SRA/PubMed metadata sheet into curator-facing review tables and, after curator review, a rowwise curator-approved master table.

## What this repo does

The pipeline starts from a master metadata workbook and local paper PDFs, then:

1. extracts PMID/SRA/BioSample metadata,
2. adds paper/PDF context,
3. creates a rowwise draft metadata table,
4. collapses SRR-level rows into biological/sample-group review rows,
5. creates a curator-facing review workbook,
6. later merges curator decisions back into a final rowwise master table.

## Main concept

Curators should not edit the original master sheet directly.

Instead:

    master workbook
        -> rowwise pipeline draft
        -> group-level curator review table
        -> curator/app decisions
        -> final rowwise curator-approved master

## Quick start

Create the conda environment:

    conda env create -f environment.yml
    conda activate sra_paper_curator

Add local input files, which are not tracked by Git:

    data/rna_seq_metadata_v1_2026-05-05.xlsx
    papers/*.pdf

Run the deterministic pipeline:

    python scripts/06_list_pmid_candidates.py

    python scripts/16_run_batch_curator_pipeline.py \
      --email YOUR_EMAIL_HERE \
      --with-paper \
      --make-review \
      --sort rows_asc

    python scripts/19_make_group_level_curator_index.py
    python scripts/26_freeze_current_outputs.py
    python scripts/27_organize_outputs.py --apply

The curator package will be under:

    outputs/00_FINAL_CURATOR_PACKAGE/

The main curator workbook is:

    curator_group_level_review_index_FOR_REVIEW.xlsx

## Important output folders

    outputs/00_FINAL_CURATOR_PACKAGE
        Files to share with curators.

    outputs/01_CURRENT_DRAFT_TABLES
        Current pipeline-generated draft tables, not curator-final.

    outputs/02_QC_SUMMARIES
        Run status, PDF status, PMID lists, Codex coverage, and QC files.

    outputs/03_PER_PMID_INTERMEDIATES
        Per-PMID audit/debug files.

    outputs/04_CODEX_ASSIST
        Optional Codex-generated curator notes.

    outputs/07_FINAL_CURATOR_APPROVED_MASTER
        Final rowwise outputs after curator review and merge-back.

## More detailed guides

Start here:

- `docs/QUICKSTART.md` — exact commands to reproduce.
- `docs/PIPELINE_OVERVIEW.md` — what each major script does.
- `docs/CURATOR_WORKFLOW.md` — how curator review and merge-back should work.
- `docs/OUTPUTS_GUIDE.md` — what each output folder means.
- `docs/CURATOR_APP_SPEC.md` — guidance for building/updating a curator app.
- `docs/MERGE_BACK_PLAN.md` — plan for final rowwise master generation.

## Optional Codex/LLM assist

Codex notes are optional and assistive only. They should not overwrite metadata. Human curators make final decisions.

See:

    docs/CODEX_ASSIST.md

## Current development status

The deterministic curator package workflow is working.

The next planned step is to add stable `curation_group_id` values and implement the merge-back script that applies curator decisions to the rowwise draft table.
