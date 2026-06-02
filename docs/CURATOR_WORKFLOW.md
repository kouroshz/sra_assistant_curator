# Curator Workflow

## Goal

The final product is a rowwise curator-approved metadata table.

Curators should review biological/sample groups, not thousands of SRR rows.

## Why group-level review?

Many SRR rows represent replicates, lanes, or technical subdivisions of the same biological/sample group.

The pipeline collapses SRR-level rows into group-level rows to reduce curator burden.

## Main curator workbook

Curators should use:

    curator_group_level_review_index_FOR_REVIEW.xlsx

This file is included in:

    outputs/00_FINAL_CURATOR_PACKAGE/curator_package.zip

## Special case

PMID 30320226 is a single-cell/well-level dataset.

Curators should use:

    PMID_30320226_single_cell_collapsed_review.xlsx

They should not manually review 2310 SRR rows for this PMID.

## What curators fill

Curators should fill the left-side review columns:

- curator_review_status
- curator_reviewer
- curator_note
- corrected_* fields only when correction is needed
- curator_final_decision

Recommended statuses:

- PASS
- MINOR_CORRECTION
- MAJOR_CORRECTION
- NEEDS_PAPER_REVIEW
- SPECIAL_HANDLING_NEEDED
- EXCLUDE

## What curators should not do

Curators should not edit the original master workbook directly.

Curators should not overwrite pipeline columns unless using the designated corrected_* fields.

## Optional agentic AI notes

agentic AI notes may help identify ambiguous controls, condition labels, or special cases.

They are assistive only.

Human curators make final decisions.

## Future app workflow

A curator app should:

1. read the group-level review table,
2. display paper/context/agentic AI evidence,
3. collect curator decisions,
4. write a curator decision table,
5. trigger or support merge-back into a final rowwise master table.

The app should not directly overwrite the original master workbook.
