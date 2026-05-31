# Curator App Specification

The app should be a human-facing interface over the group-level curator table.

## Input tables

The app should read:

- curator_group_level_review_index_FOR_REVIEW.xlsx
- selected_codex_curator_assist_summary.xlsx, optional
- paper/context snippets if available, optional

## Key field

Each group row should have a stable:

    curation_group_id

This ID must also exist in the rowwise draft table.

## What curators see

For each group:

- PMID
- Title
- n_rows
- n_runs
- n_biosamples
- Life_Stage
- Cell_Cycle_Stage
- Strain
- Substrain
- Target
- Mutant
- Condition1
- Condition2
- Condition3
- experimental_factor
- control_role
- assigned controls
- curator_condition_note
- review_reason
- Codex notes if available

## What curators submit

The app should write a decision table, not edit the master directly:

- curation_group_id
- curator_review_status
- curator_reviewer
- curator_note
- corrected_Life_Stage
- corrected_Cell_Cycle_Stage
- corrected_Strain
- corrected_Substrain
- corrected_Target
- corrected_Mutant
- corrected_Condition1
- corrected_Condition2
- corrected_Condition3
- corrected_experimental_factor
- corrected_control_role
- curator_final_decision
- review_timestamp

Recommended statuses:

- PASS
- MINOR_CORRECTION
- MAJOR_CORRECTION
- NEEDS_PAPER_REVIEW
- SPECIAL_HANDLING_NEEDED
- EXCLUDE

## Important rule

The app should update a curator decision table. A controlled merge-back script should generate the final rowwise master.

Do not directly overwrite the original master workbook.
