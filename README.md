# SRA Assistant Curator

A reproducible pipeline for converting a master RNA-seq/SRA/PubMed metadata workbook into curator-facing review tables and, after review, a rowwise curator-approved master table.

## Purpose

This project helps curate SRA-linked RNA-seq metadata from papers.

The pipeline:

1. reads a master metadata workbook,
2. fetches SRA RunInfo and BioSample metadata,
3. extracts paper/PDF context,
4. creates a rowwise draft metadata table,
5. collapses SRR-level rows into biological/sample-group review rows,
6. creates a curator-facing workbook,
7. later merges curator decisions back into a final rowwise master table.

## Key idea

Curators should not edit the original master workbook directly.

Instead:

    master workbook
        -> pipeline rowwise draft
        -> group-level curator review workbook
        -> curator/app decisions
        -> final rowwise curator-approved master

## What is tracked by Git

Tracked:

- scripts/
- docs/
- environment.yml
- README.md
- data/pmid_corrections.tsv
- data/special_pmid_handling.tsv
- data/README_DATA.md
- papers/README_PAPERS.md
- outputs/README_OUTPUTS.md
- empty output-folder placeholders

Not tracked:

- master Excel workbook
- PDFs
- SRA/BioSample caches
- generated outputs
- curator packages
- agentic AI logs/notes
- local credentials or API keys

## Required local input files

Place the master workbook here:

    data/rna_seq_metadata_2026-05-05_original.xlsx

Place paper PDFs here:

    papers/

Recommended PDF naming:

    <PMID>_<short_title>.pdf

Example:

    papers/31737630_TRIBE_Uncovers_RNA_Targets_of_Rrp6.pdf

PDFs are local-only and are not committed to Git.

## Setup

Create the conda environment:

    conda env create -f environment.yml
    conda activate sra_paper_curator

If the environment already exists:

    conda activate sra_paper_curator

## Reproduce the deterministic curator package

Step 1: list candidate PMIDs and check metadata/PDF status.

    python scripts/06_list_pmid_candidates.py

Step 2: optional open-access PDF download.

    python scripts/15_download_open_access_pdfs.py \
      --pmids-file outputs/pmids_needing_pdfs.tsv \
      --email YOUR_EMAIL_HERE \
      --sleep 1.0

This downloader tries open-access routes such as PubMed/PMC/Europe PMC/publisher links where available. It will not retrieve every paper. Any remaining PDFs can be downloaded manually, including through institutional access, and placed in papers/.

Step 3: run the deterministic batch pipeline.

    python scripts/16_run_batch_curator_pipeline.py \
      --email YOUR_EMAIL_HERE \
      --with-paper \
      --make-review \
      --sort rows_asc

Step 4: create the group-level curator review table.

    python scripts/19_make_group_level_curator_index.py

Step 5: freeze the current rowwise draft table.

    python scripts/26_freeze_current_outputs.py

Step 6: organize outputs.

Preview first:

    python scripts/27_organize_outputs.py

Apply:

    python scripts/27_organize_outputs.py --apply

## Main outputs

Curator package:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package.zip

Main curator workbook:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package/curator_group_level_review_index_FOR_REVIEW.xlsx

Current rowwise draft table:

    outputs/01_CURRENT_DRAFT_TABLES/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

Special single-cell collapsed workbook:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package/PMID_30320226_single_cell_collapsed_review.xlsx

## Optional agentic AI assist

agentic AI can generate conservative curator-assist notes. These are optional and not authoritative.

Run selected PMIDs:

    ./scripts/24_run_agentic_ai_curator_assist_selected.sh "31737630,32552779"

Merge agentic AI notes:

    python scripts/25_merge_agentic_ai_curator_assist.py

agentic AI notes should help curators identify ambiguities, but they do not replace human review.

## Output folder guide

    outputs/00_FINAL_CURATOR_PACKAGE
        Files to share with curators.

    outputs/01_CURRENT_DRAFT_TABLES
        Current pipeline-generated draft tables. Not curator-final.

    outputs/02_QC_SUMMARIES
        Run status, PDF status, PMID lists, agentic AI coverage, and QC files.

    outputs/03_PER_PMID_INTERMEDIATES
        Per-PMID audit/debug files.

    outputs/04_AGENTIC_AI_ASSIST
        Optional agentic AI-generated notes, prompts, and logs.

    outputs/05_LOGS
        Batch pipeline logs.

    outputs/06_ARCHIVE_OLD
        Old/stale/incomplete outputs retained for safety.

    outputs/07_FINAL_CURATOR_APPROVED_MASTER
        Reserved for final rowwise curator-approved metadata after merge-back.

## More detailed guides

- docs/QUICKSTART.md
- docs/PIPELINE_OVERVIEW.md
- docs/OUTPUTS_GUIDE.md
- docs/CURATOR_WORKFLOW.md
- docs/CURATOR_APP_SPEC.md
- docs/MERGE_BACK_PLAN.md
- docs/AGENTIC_AI_ASSIST.md

## Current development status

The deterministic pipeline and curator-package workflow are working.

The next planned engineering step is to add stable curation_group_id values and implement the merge-back script that applies curator decisions to the rowwise draft table.
