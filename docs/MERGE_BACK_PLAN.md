# Merge-Back Plan

## Goal

Create a final rowwise, curator-approved metadata table.

## Inputs

Current rowwise draft:

    outputs/01_CURRENT_DRAFT_TABLES/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv

Curator decision table or reviewed workbook:

    curator_group_review_decisions.tsv

or:

    curator_group_level_review_index_FOR_REVIEW.xlsx

## Required key

Both rowwise and groupwise tables must contain:

    curation_group_id

## Logic

For each curator-reviewed group:

1. Identify all rowwise records with the same curation_group_id.
2. For each nonempty corrected_* field, update the corresponding rowwise metadata field.
3. Preserve original pipeline values in audit columns.
4. Add curator provenance:
   - curator_reviewer
   - curator_review_status
   - curator_note
   - curator_final_decision
   - review_timestamp
5. Write an audit log.

## Outputs

Final outputs should be written to:

    outputs/07_FINAL_CURATOR_APPROVED_MASTER/

Expected files:

    all_pmids_agent_filled_master_rows_with_paper_context_CURATOR_FINAL.tsv
    rna_seq_metadata_v1_2026-05-05.curator_final.xlsx
    curator_mergeback_audit.tsv
    curator_mergeback_summary.tsv

## Safety rule

The original master workbook is never overwritten.

A new final workbook is created.
