# Quickstart

This guide is for someone reproducing the pipeline locally.

## 1. Clone repo

    git clone https://github.com/kouroshz/sra_assistant_curator.git
    cd sra_assistant_curator

## 2. Create conda environment

    conda env create -f environment.yml
    conda activate sra_paper_curator

If the environment already exists:

    conda activate sra_paper_curator

## 3. Add local input files

These files are required locally but are not tracked by Git.

Main master workbook:

    data/rna_seq_metadata_v1_2026-05-05.xlsx

Paper PDFs:

    papers/*.pdf

Recommended PDF naming:

    <PMID>_<short_title>.pdf

Example:

    papers/31737630_TRIBE_Uncovers_RNA_Targets_of_Rrp6.pdf

## 4. Confirm candidate PMIDs

    python scripts/06_list_pmid_candidates.py

Output:

    outputs/pmid_candidates.tsv

## 5. Run deterministic batch pipeline

    python scripts/16_run_batch_curator_pipeline.py \
      --email YOUR_EMAIL_HERE \
      --with-paper \
      --make-review \
      --sort rows_asc

This creates per-PMID populated rows, paper context files, and review workbooks.

## 6. Create group-level curator review table

    python scripts/19_make_group_level_curator_index.py

This collapses SRR-level rows into biological/sample-group rows.

## 7. Freeze current rowwise draft

    python scripts/26_freeze_current_outputs.py

Main current rowwise draft:

    outputs/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

After organization, this moves to:

    outputs/01_CURRENT_DRAFT_TABLES/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

## 8. Organize outputs

Preview first:

    python scripts/27_organize_outputs.py

Apply:

    python scripts/27_organize_outputs.py --apply

## 9. Curator package

The files to share with curators are in:

    outputs/00_FINAL_CURATOR_PACKAGE/

Main zip:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package.zip

Main workbook inside the package:

    curator_group_level_review_index_FOR_REVIEW.xlsx

Special case:

    PMID_30320226_single_cell_collapsed_review.xlsx

## 10. Optional Codex assist

Codex is optional.

Run selected PMIDs:

    ./scripts/24_run_codex_curator_assist_selected.sh "31737630,32552779"

Merge Codex notes:

    python scripts/25_merge_codex_curator_assist.py

Codex notes are assistive only.

## 11. Final master creation

Not yet fully implemented.

Planned final step:

    curator review decisions
        + current rowwise draft
        -> final rowwise curator-approved master table

See:

    docs/MERGE_BACK_PLAN.md
