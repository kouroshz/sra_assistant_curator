# Unmapped Script Review

Generated: 2026-06-04T19:18:04

This is a non-destructive classification of scripts not currently in `workflows/steps.tsv` and not production infrastructure.

Do not move these automatically. Use this report to decide what should be archived next.

## Summary

- ACTIVE_DEPENDENCY_KEEP: 3
- KEEP_REVIEW_STRONG_CODE_REFERENCE: 4
- POSSIBLE_AI_UTILITY_REVIEW: 1
- POSSIBLE_PAPER_PUBLICATION_UTILITY_REVIEW: 1
- POSSIBLE_QC_UTILITY_REVIEW: 2
- SUPPORT_UTILITY_KEEP_REVIEW: 2

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

## ACTIVE_DEPENDENCY_KEEP

- `scripts/41_batch_run_agentic_ai_on_trusted_queue.py`
  - recommendation: Helper dependency used by active production RNA AI runner; keep in scripts for now.
  - strong references: 3
  - strongly referenced by: scripts/07_classify_unmapped_scripts.py | scripts/41d_batch_run_trusted_queue_auto_chunked.py | scripts/41e_batch_run_trusted_queue_production.py
  - weak legacy/doc references: 0
  - doc: Batch runner for trusted PMID-linked RNA-seq paper/BioProject packets.  Default behavior is DRY-RUN ONLY. Use --execute to call the API runner.  This script intentionally does NOT read any manual/gold-standard curation files. Gold standards should be used only later for independent verification.  Typical first use:    python scripts/41_batch_run_agentic_ai_on_trusted_queue.py     --packet-id PMID_32487761__BIOPROJECT_PRJNA550429  Then, when ready to actually run:    set -a; source .env; set +a  
- `scripts/41c_run_agentic_ai_chunked_large_packet.py`
  - recommendation: Helper dependency used by active production RNA AI runner; keep in scripts for now.
  - strong references: 3
  - strongly referenced by: scripts/07_classify_unmapped_scripts.py | scripts/41d_batch_run_trusted_queue_auto_chunked.py | scripts/41e_batch_run_trusted_queue_production.py
  - weak legacy/doc references: 0
  - doc: Chunked AI runner for large paper packets.  Design:   - Run script 39 on rowwise chunks.   - Collect only valid rowwise_suggestions.   - Ignore AI sample_map for final merged large-packet output.   - Build sample_map deterministically from merged rowwise_suggestions.   - If AI misses rows, add deterministic low-confidence fallback suggestions     marked curator_check / low_confidence.   - Validate merged output with script 40.  This prevents large-packet failures caused by:   - incomplete long J
- `scripts/41d_batch_run_trusted_queue_auto_chunked.py`
  - recommendation: Helper dependency used by active production RNA AI runner; keep in scripts for now.
  - strong references: 3
  - strongly referenced by: docs/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md | scripts/07_classify_unmapped_scripts.py | scripts/49_finalize_trusted_rna_ai_phase.py
  - weak legacy/doc references: 0
  - doc: Auto-dispatch batch runner for trusted RNA AI packets.  Small/moderate packets:   -> scripts/41_batch_run_agentic_ai_on_trusted_queue.py  Large packets:   -> scripts/41c_run_agentic_ai_chunked_large_packet.py  This keeps the original one-shot batch runner stable, while using chunked mode when row count is too large for reliable one-shot JSON output.

## KEEP_REVIEW_STRONG_CODE_REFERENCE

- `scripts/29_make_group_level_curator_review.py`
  - recommendation: Referenced by non-legacy tracked files; do not move without manual inspection.
  - strong references: 1
  - strongly referenced by: docs/CURRENT_PIPELINE_STATUS_AND_STRATEGY.md
  - weak legacy/doc references: 0
  - doc: Create a group-level curator review workbook from the stable-ID rowwise table.  This script does NOT call AI and does NOT modify the master sheet. It prepares a human/agent-ready curator table.  Input:   outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv  Outputs:   outputs/00_FINAL_CURATOR_PACKAGE/curator_group_level_review_WITH_STABLE_IDS.xlsx   outputs/01_CURRENT_DRAFT_TABLES/curator_group_level_review_WITH_STABLE_IDS.tsv   outputs/02_QC_SUMMARIES/group_level_curator_review_su
- `scripts/30_make_agentic_ai_input_packets.py`
  - recommendation: Referenced by non-legacy tracked files; do not move without manual inspection.
  - strong references: 1
  - strongly referenced by: docs/CURRENT_PIPELINE_STATUS_AND_STRATEGY.md
  - weak legacy/doc references: 0
  - doc: Create compact input packets for the future API-based agentic AI curator.  This script does NOT call an API. This script does NOT modify metadata. This script only prepares per-curation-group JSON packets that contain:   - stable IDs   - current parsed metadata   - run/BioSample identifiers   - compact row examples   - paper PDF candidates   - explicit AI output schema  Later, an API-based paper-reading assistant can use these packets to populate ai_* suggestion fields and reduce human curator b
- `scripts/31_test_openai_api.py`
  - recommendation: Referenced by non-legacy tracked files; do not move without manual inspection.
  - strong references: 2
  - strongly referenced by: docs/API_ASSIST_OPTIONAL_SETUP.md | docs/CURRENT_PIPELINE_STATUS_AND_STRATEGY.md
  - weak legacy/doc references: 0
- `scripts/32_run_agentic_ai_on_packet.py`
  - recommendation: Referenced by non-legacy tracked files; do not move without manual inspection.
  - strong references: 1
  - strongly referenced by: docs/CURRENT_PIPELINE_STATUS_AND_STRATEGY.md
  - weak legacy/doc references: 0
  - doc: Run the optional API-based agentic curator on ONE input packet.  This is intentionally single-packet only for pilot testing.  Safety:   - API disabled by default unless AGENTIC_AI_ENABLE_API=1   - does not modify master workbook   - does not modify group-level curator table   - writes suggestions only to outputs/04_AGENTIC_AI_ASSIST/

## POSSIBLE_AI_UTILITY_REVIEW

- `scripts/48b_rebuild_sample_map_from_rowwise_biokey.py`
  - recommendation: Looks AI/prompt-related; inspect before moving.
  - strong references: 0
  - weak legacy/doc references: 0
  - doc: Rebuild sample_map deterministically from rowwise_suggestions, but split heterogeneous sample_class_id groups by biological rowwise fields.  Use when:   - rowwise_suggestions cover every packet row exactly once   - sample_map has missing/duplicate source_row_id values   - sample_class_id may be too broad and span multiple stages/timepoints  Output:   <packet>.ai_curation_samplemap_biokey_rebuilt.<timestamp>.json

## POSSIBLE_PAPER_PUBLICATION_UTILITY_REVIEW

- `scripts/36_rank_paper_packets_for_ai.py`
  - recommendation: Looks related to paper/PDF/PMID/publication logic; inspect before moving.
  - strong references: 0
  - weak legacy/doc references: 0
  - doc: Rank paper/BioProject packets for optional agentic AI curation.  This script does NOT call an API.  It creates a priority queue that:   - prioritizes packets where paper-reading AI is likely useful   - flags well-based / single-cell uniform packets as low-value or skip   - gives human curators a ranked review list

## POSSIBLE_QC_UTILITY_REVIEW

- `scripts/43b_semantic_spotcheck_pass_packets.py`
  - recommendation: Looks like QC/validation/inventory logic; inspect before moving.
  - strong references: 0
  - weak legacy/doc references: 0
  - doc: Semantic spot-check table for PASS AI-curated packets.  Read-only. Does not modify outputs.  Creates:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_spotcheck_rows.tsv   outputs/04_AGENTIC_AI_ASSIST/deep_qc/SEMANTIC_SPOTCHECK_SUMMARY.md
- `scripts/45_find_rna_chip_overlap_bioqc_candidates.py`
  - recommendation: Looks like QC/validation/inventory logic; inspect before moving.
  - strong references: 0
  - weak legacy/doc references: 0
  - doc: Find candidate papers/BioProjects for biological QC across RNA and ChIP master sheets.  Read-only.  Outputs:   outputs/05_BIOLOGICAL_QC/rna_chip_overlap_candidates.tsv

## SUPPORT_UTILITY_KEEP_REVIEW

- `scripts/65_audit_chip_repeats_and_chunk_failures.py`
  - recommendation: Support/diagnostic utility referenced by current reorg/runbook infrastructure; keep for now, rename later.
  - strong references: 4
  - strongly referenced by: docs/POSTDOC_RERUN_RUNBOOK.md | scripts/00_audit_current_pipeline_for_reorg.py | scripts/07_classify_unmapped_scripts.py | scripts/69_postdoc_handoff_inventory.py
  - weak legacy/doc references: 0
- `scripts/69_postdoc_handoff_inventory.py`
  - recommendation: Support/diagnostic utility referenced by current reorg/runbook infrastructure; keep for now, rename later.
  - strong references: 3
  - strongly referenced by: docs/POSTDOC_RERUN_RUNBOOK.md | scripts/00_audit_current_pipeline_for_reorg.py | scripts/07_classify_unmapped_scripts.py
  - weak legacy/doc references: 0
