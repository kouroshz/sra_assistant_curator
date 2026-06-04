# Curator Guide

This guide explains the final curator-facing files.

The clean release is generated in:

    results/final_curator_release/

The latest release pointer is:

    results/LATEST_FINAL_CURATOR_RELEASE.txt

## Start here

Open:

    RNA/RNA_curator_review.xlsx
    ChIP/ChIP_curator_review.xlsx

Also read:

    RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md
    ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md

## Important principle

AI suggestions are not final.

Curator-final columns in the Excel files are authoritative.

## RNA review focus

For RNA packets, review:

1. Study/paper summary.
2. Biological sample groups.
3. Stage, strain, condition, treatment, timepoint.
4. Major comparisons.
5. Low-confidence or review-flagged rows.
6. Any held or policy-review packets.

## ChIP review focus

For ChIP packets, review:

1. Study/paper summary.
2. Target IP rows.
3. Input, IgG, mock, untagged, or background rows.
4. Target-control/background mapping.
5. Peak-calling readiness.
6. Shared input controls.
7. Low-confidence or HIGH_REVIEW rows.
8. Ambiguous stage, strain, condition, or target labels.

## What feedback to provide

For each issue, curators should ideally provide:

- packet ID
- source row ID or SRR run
- current suggested value
- corrected value
- short rationale
- whether the correction should become a deterministic rule

## How feedback improves the pipeline

Curator feedback can be used to:

- update deterministic metadata rules
- improve target/control mapping
- improve confidence flags
- add special-case BioProject/PMID policies
- improve future AI prompt instructions
- strengthen validation tests
