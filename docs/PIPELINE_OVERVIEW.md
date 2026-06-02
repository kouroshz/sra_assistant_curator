# Pipeline Overview

This document explains the main scripts without going into implementation details.

## Core pipeline

### 01_filter_master_by_pmid.py

Filters the master workbook to one PMID.

### 02_fetch_sra_runinfo_for_master_rows.py

Fetches or reads cached SRA RunInfo for a PMID.

### 03_fetch_biosample_metadata_for_master_rows.py

Fetches or reads cached BioSample metadata.

### 04_populate_master_from_biosample.py

Adds metadata inferred from SRA/BioSample fields.

### 06_list_pmid_candidates.py

Summarizes PMIDs, row counts, BioProjects, and PDF status.

### 07_extract_paper_context.py

Extracts local paper text and evidence snippets.

### 08_apply_paper_context_to_master.py

Adds paper-derived context to the rowwise metadata table.

### 09_make_curator_review_view.py

Creates a PMID-level curator review workbook.

### 14_add_curator_condition_fields.py

Adds simplified curator-facing condition/control fields.

### 15_download_open_access_pdfs.py

Attempts open-access PDF download. Manual PDF placement is acceptable.

### 16_run_batch_curator_pipeline.py

Main batch runner. Runs the PMID-level workflow over many PMIDs.

### 17_apply_special_pmid_handling.py

Applies special handling rules.

Important special case:

    PMID 30320226

This is treated as a collapsed single-cell dataset rather than ordinary SRR-level curation.

### 18_make_curator_review_index.py

Creates a PMID-level technical index.

This is not the main curator-facing file.

### 19_make_group_level_curator_index.py

Creates the main group-level review table.

This is the most important curator-facing table.

### 20_make_spotcheck_workbook.py

Creates a small spot-check workbook for selected PMIDs.

## PMID-specific deterministic patches

These are explicit, conservative, documented special-case corrections.

### 21_patch_pmid_31737630_dis3.py

Handles PfDis3/DD/GlcN naming and control logic.

### 22_patch_pmid_34365503_timepoints.py

Moves D2/D4/D6/D8/D10 labels into developmental timepoint fields.

### 23_patch_pmid_32552779_arp4_glcn.py

Handles PfArp4/GlcN and WT GlcN control interpretation.

## Optional agentic AI assist

### 24_run_agentic_ai_curator_assist_selected.sh

Runs agentic AI for selected PMIDs and writes notes.

### 25_merge_agentic_ai_curator_assist.py

Combines agentic AI notes into one workbook.

agentic AI output is assistive only.

## Output management

### 26_freeze_current_outputs.py

Rebuilds the current all-PMID rowwise draft table and writes a manifest.

### 27_organize_outputs.py

Organizes generated files into readable output folders.

## Planned

### 28_apply_curator_review_to_rowwise_table.py

Planned merge-back script.

It will apply curator group-level corrections to the rowwise draft table and create the final curator-approved master table.
