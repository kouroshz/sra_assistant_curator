# Workflow

## Purpose

This project builds curator-facing metadata review tables from a master RNA-seq/SRA/PubMed metadata sheet.

The endpoint is a rowwise curator-approved master-like table, but curator review happens at the biological/sample-group level.

## Inputs

Required local files, not tracked by Git:

- data/rna_seq_metadata_v1_2026-05-05.xlsx
- papers/*.pdf

Tracked config files:

- data/pmid_corrections.tsv
- data/special_pmid_handling.tsv

Generated caches, not tracked by Git:

- data/biosample_cache/
- data/sra_runinfo_cache/
- data/geo_cache/

## Deterministic pipeline

Run candidate listing:

    python scripts/06_list_pmid_candidates.py

Run full batch pipeline:

    python scripts/16_run_batch_curator_pipeline.py \
      --email YOUR_EMAIL_HERE \
      --with-paper \
      --make-review \
      --sort rows_asc

Generate group-level review index:

    python scripts/19_make_group_level_curator_index.py

Generate current rowwise draft and manifest:

    python scripts/26_freeze_current_outputs.py

Organize outputs:

    python scripts/27_organize_outputs.py
    python scripts/27_organize_outputs.py --apply

## Curator package

Curators should receive:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package.zip

Main curator workbook:

    curator_group_level_review_index_FOR_REVIEW.xlsx

Special single-cell case:

    PMID_30320226_single_cell_collapsed_review.xlsx

## Curator review

Curators fill the left-side curator columns:

- curator_review_status
- curator_reviewer
- curator_note
- corrected_* fields
- curator_final_decision

The review table is group-level, not SRR-level.

## Merge-back

After review, curator corrections should be merged back into the rowwise draft table to create the final approved rowwise metadata table.

This requires a stable curation_group_id shared by:

- rowwise draft table
- group-level curator table
- curator/app decision table

See docs/MERGE_BACK_PLAN.md.
