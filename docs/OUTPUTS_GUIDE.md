# Outputs Guide

Generated files live under outputs/.

## Folder meanings

### 00_FINAL_CURATOR_PACKAGE

Files intended for sharing with curators.

Main handoff file:

    curator_package.zip

### 01_CURRENT_DRAFT_TABLES

Current pipeline-generated draft tables.

These are not curator-final.

Important file:

    all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

This is the current rowwise draft populated table.

### 02_QC_SUMMARIES

Run status, PDF status, PMID lists, Codex coverage, and organization plans.

### 03_PER_PMID_INTERMEDIATES

Per-PMID audit/debug files.

Use this if one PMID needs investigation.

### 04_CODEX_ASSIST

Optional Codex notes, prompts, and logs.

Codex notes are assistive only.

### 05_LOGS

Batch run logs.

### 06_ARCHIVE_OLD

Old/stale/incomplete outputs retained for safety.

### 07_FINAL_CURATOR_APPROVED_MASTER

Reserved for final rowwise master outputs after curator review and merge-back.

## Important distinction

01_CURRENT_DRAFT_TABLES is not the final curated master.

The final curated master is produced only after curator decisions are merged back into the rowwise draft.
