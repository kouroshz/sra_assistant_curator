# Trusted PMID-linked RNA AI-curation Phase Completion Report

Generated: 2026-06-02T21:38:13

## Executive status

- Trusted RNA packets inspected: 71
- PASS: 69
- NO_VALIDATION: 2
- Semantic HIGH/MEDIUM flags among PASS packets: 0
- Held packets requiring policy review: 2

## Interpretation

The main AI-actionable trusted PMID-linked RNA queue is complete if PASS=69 and the only NO_VALIDATION records are intentionally held packets. AI outputs remain suggestions only; curator final columns are authoritative.

Rows with REVIEW flags should remain visible to curators and should not be silently treated as final high-confidence GRN-ready annotations.

## Validation status by recommended action

| recommended_action | latest_validation_status | n |
| --- | --- | --- |
| defer | NO_VALIDATION | 1 |
| skip_or_low_priority | NO_VALIDATION | 1 |
| run_ai | PASS | 69 |

## Held packets

| packet_id | pmid | bioproject | n_rows | assay_class | recommended_action | latest_validation_status |
| --- | --- | --- | --- | --- | --- | --- |
| PMID_35637187__BIOPROJECT_PRJNA690786 | 35637187 | PRJNA690786 | 468 | rna_seq_expression_or_timecourse | skip_or_low_priority | NO_VALIDATION |
| PMID_39242698__BIOPROJECT_PRJNA994684 | 39242698 | PRJNA994684 | 8 | rna_seq_expression_or_timecourse | defer | NO_VALIDATION |

## Semantic red-flag summary

### By severity

- REVIEW: 315

### By flag type

- rowwise_review_flag_not_ok: 142
- low_confidence_ai_suggestion: 74
- metadata_stage_conflict_ai_matches_one_source: 57
- deterministic_fallback_row: 42

## Latest curator workbook

- outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_20260602_213023.xlsx

| sheet | rows |
|---|---:|
| README | 5 |
| Study_Review | 69 |
| Sample_Map_Review | 553 |
| Problem_Rows | 199 |
| Rowwise_Review | 2440 |

## Files written by this report

- `outputs/04_AGENTIC_AI_ASSIST/deep_qc/trusted_rna_ai_phase_packet_status.tsv`
- `outputs/04_AGENTIC_AI_ASSIST/deep_qc/held_packets_for_policy_review.tsv`
- `outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md`

## Production notes

- Do not commit API keys, `.env`, large data files, raw PDFs, or large generated output folders.
- Keep scripts, README/runbooks, QC summaries, and small manifests under version control.
- Patch or replace `41d_batch_run_trusted_queue_auto_chunked.py` before postdoc rerun.
- Future default actionable queue classes should include `run_ai_first`, `run_ai_pilot`, and `run_ai`.
- Future default large-packet threshold should be 100 rows unless stress testing suggests otherwise.
- ChIP curation must remain separate and use ChIP-specific control/background validation.
