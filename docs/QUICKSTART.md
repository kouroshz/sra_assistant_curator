# Quickstart

This guide is for reproducing the pipeline locally.

## 1. Clone the repo

    git clone https://github.com/kouroshz/sra_assistant_curator.git
    cd sra_assistant_curator

## 2. Create the conda environment

    conda env create -f environment.yml
    conda activate sra_paper_curator

If the environment already exists:

    conda activate sra_paper_curator

## 3. Place local input files

The repo does not track raw data files, PDFs, or generated outputs.

### Master workbook

Place the master workbook here:

    data/rna_seq_metadata_v1_2026-05-05.xlsx

This file is required.

### Papers/PDFs

Place paper PDFs here:

    papers/

Recommended naming:

    <PMID>_<short_title>.pdf

Example:

    papers/31737630_TRIBE_Uncovers_RNA_Targets_of_Rrp6.pdf

PDFs are not committed to Git.

## 4. Create/check the PMID list

Run:

    python scripts/06_list_pmid_candidates.py

This summarizes candidate PMIDs, row counts, BioProjects, library strategies, and PDF status.

Useful outputs may include:

    outputs/pmid_candidates.tsv
    outputs/pmids_needing_pdfs.tsv

## 5. Get papers/PDFs

There are two options.

### Option A: open-access PDF downloader

The repository includes an open-access PDF downloader:

    python scripts/15_download_open_access_pdfs.py \
      --pmids-file outputs/pmids_needing_pdfs.tsv \
      --email YOUR_EMAIL_HERE \
      --sleep 1.0

This tries open-access routes such as PubMed/PMC/Europe PMC/publisher PDF links where available.

It will not find every PDF. Some papers still need manual download.

Downloaded PDFs are placed in:

    papers/

### Option B: manual download

Manually download PDFs, including through institutional access if needed, and place them in:

    papers/

Use filenames that start with the PMID when possible:

    papers/<PMID>_<short_title>.pdf

Example:

    papers/37833314_Extracellular_vesicles.pdf

## 6. Run the deterministic pipeline

    python scripts/16_run_batch_curator_pipeline.py \
      --email YOUR_EMAIL_HERE \
      --with-paper \
      --make-review \
      --sort rows_asc

This creates per-PMID rowwise outputs and curator review workbooks.

## 7. Create group-level curator review table

    python scripts/19_make_group_level_curator_index.py

This collapses SRR-level rows into biological/sample-group rows.

The resulting workbook is the main curator-facing table.

## 8. Freeze the current rowwise draft

    python scripts/26_freeze_current_outputs.py

This creates the current all-PMID rowwise draft table:

    outputs/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

After organization, it will be in:

    outputs/01_CURRENT_DRAFT_TABLES/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

## 9. Organize outputs

Preview organization:

    python scripts/27_organize_outputs.py

Apply organization:

    python scripts/27_organize_outputs.py --apply

## 10. Find the curator package

Curator package:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package.zip

Main curator workbook inside the package:

    curator_group_level_review_index_FOR_REVIEW.xlsx

Special single-cell collapsed workbook:

    PMID_30320226_single_cell_collapsed_review.xlsx

## 11. Optional Codex assist

Codex is optional.

Run selected PMIDs:

    ./scripts/24_run_codex_curator_assist_selected.sh "31737630,32552779"

Merge Codex notes:

    python scripts/25_merge_codex_curator_assist.py

Codex notes are assistive only. Human curators make final decisions.

## 12. Final master creation

The final rowwise curator-approved master is created after curator review.

Planned final logic:

    current rowwise draft
        + curator group-level decisions
        -> final rowwise curator-approved master

Expected future folder:

    outputs/07_FINAL_CURATOR_APPROVED_MASTER/

See:

    docs/MERGE_BACK_PLAN.md
