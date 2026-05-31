# Outputs

Generated outputs are not tracked by Git, except this README and empty folder placeholders.

## Folder guide

### 00_FINAL_CURATOR_PACKAGE

Files to share with curators.

Main file:

    curator_package.zip

Main workbook inside the package:

    curator_group_level_review_index_FOR_REVIEW.xlsx

### 01_CURRENT_DRAFT_TABLES

Current pipeline-generated draft tables.

Important rowwise draft:

    all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

This is not curator-final. It is the current rowwise draft that will later receive curator-approved corrections.

### 02_QC_SUMMARIES

Run status, PDF status, candidate PMID lists, Codex coverage, and organization plans.

### 03_PER_PMID_INTERMEDIATES

Per-PMID intermediate files for audit/debugging.

### 04_CODEX_ASSIST

Optional Codex notes, prompts, and logs.

Codex notes are assistive only, not authoritative.

### 05_LOGS

Batch pipeline logs.

### 06_ARCHIVE_OLD

Old/stale/incomplete outputs retained for safety.

### 07_FINAL_CURATOR_APPROVED_MASTER

Reserved for final rowwise curator-approved metadata tables after merge-back.

Expected future files:

    all_pmids_agent_filled_master_rows_with_paper_context_CURATOR_FINAL.tsv
    rna_seq_metadata_v1_2026-05-05.curator_final.xlsx
    curator_mergeback_audit.tsv
    curator_mergeback_summary.tsv
