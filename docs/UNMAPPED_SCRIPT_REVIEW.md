# Unmapped Script Review

Generated: 2026-06-04T19:22:29

This is a non-destructive classification of scripts not currently in `workflows/steps.tsv` and not production infrastructure.

Do not move these automatically. Use this report to decide what should be archived next.

## Summary


## Categories

- ACTIVE_DEPENDENCY_KEEP: helper dependency used by active production workflow scripts.
- SUPPORT_UTILITY_KEEP_REVIEW: support/diagnostic utility; keep for now, rename later.
- KEEP_REVIEW_STRONG_CODE_REFERENCE: referenced by non-legacy tracked files; do not move without inspection.
- SCRATCH_OR_INSPECTION_CANDIDATE: likely exploratory/inspection/debug; candidate for archive.
- HISTORICAL_ARCHIVE_CANDIDATE: likely old prototype/pilot/versioned script; candidate for archive.
- POSSIBLE_QC_UTILITY_REVIEW: may contain reusable validation/QC logic.
- POSSIBLE_PAPER_PUBLICATION_UTILITY_REVIEW: may contain paper/PMID/PDF logic.
- POSSIBLE_AI_UTILITY_REVIEW: may contain AI prompt/run logic.
- MANUAL_REVIEW: unclear.
