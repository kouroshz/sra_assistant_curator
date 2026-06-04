# Script Cleanup Plan

Generated: 2026-06-04T18:20:40

This is a non-destructive cleanup inventory.

Do not move active workflow scripts yet.

## Summary

- ACTIVE_WORKFLOW: 41
- PRODUCTION_INFRA: 7
- SUPERSEDED_CANDIDATE: 6
- UNMAPPED_REVIEW: 40

## Cleanup policy

1. Keep `ACTIVE_WORKFLOW` scripts in place until clean wrappers fully replace them.
2. Keep `PRODUCTION_INFRA` scripts in place.
3. Move only `SUPERSEDED_CANDIDATE` scripts first.
4. Do not move `UNMAPPED_REVIEW` scripts until manually inspected.
5. Run `python scripts/05_run_all_checks.py` after every move.

## Scripts by category

### ACTIVE_WORKFLOW

- `scripts/15_download_open_access_pdfs.py`
  - Used by workflows/steps.tsv
- `scripts/28_add_stable_ids_to_master.py`
  - Used by workflows/steps.tsv
  - doc: Add stable row and curation-group IDs to the master metadata workbook.  This script does NOT overwrite the master sheet. It creates a rowwise draft table with:   - source_row_number   - source_row_id   - curation_group_id   - curation_group_size  The goal is to support safe curator review and later 
- `scripts/33_fetch_public_sra_biosample_metadata.py`
  - Used by workflows/steps.tsv
  - doc: Fetch/cache public SRA RunInfo and BioSample XML metadata.  This script is deterministic and does NOT call OpenAI.  Inputs:   outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv  Caches:   data/sra_runinfo_cache/<Run>.csv   data/biosample_cache/<BioSample>.xml  Summary:   outputs/02_Q
- `scripts/34_build_rowwise_public_metadata_evidence.py`
  - Used by workflows/steps.tsv
  - doc: Build a compact rowwise public-metadata evidence table from cached SRA RunInfo and BioSample XML files.  This script is deterministic and does NOT call OpenAI.  Inputs:   outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv   data/sra_runinfo_cache/*.csv   data/biosample_cache/*.xml  O
- `scripts/35_make_paper_level_ai_packets.py`
  - Used by workflows/steps.tsv
  - doc: Create paper/BioProject-level input packets for the optional agentic AI curator.  This script does NOT call an API. It prepares token-aware packet JSON files plus sidecar rowwise TSV files.  Input:   outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv  Outputs:   outputs/04_AGENTIC_
- `scripts/37_resolve_publication_links_for_packets.py`
  - Used by workflows/steps.tsv
  - doc: Resolve or flag publication links for paper/BioProject packets.  This script does NOT call OpenAI.  Purpose:   - Treat missing PMID as a gating QC issue.   - Try deterministic/public resolution before AI.   - Mark unresolved BioProjects as publication_unresolved_hold.  Inputs:   outputs/04_AGENTIC_A
- `scripts/38_make_trusted_assay_aware_ai_queue.py`
  - Used by workflows/steps.tsv
  - doc: Create a trusted, assay-aware AI/curator queue.  This script does NOT call an API.  Inputs:   outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv   outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv   outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv  Outpu
- `scripts/39_run_agentic_ai_on_paper_packet.py`
  - Used by workflows/steps.tsv
  - doc: Run optional API-based agentic curation on ONE trusted paper/BioProject packet.  This script:   - requires AGENTIC_AI_ENABLE_API=1 unless --dry-run   - reads one paper-level packet JSON   - reads its sidecar rowwise evidence TSV   - reads matched PDF text if available   - adds assay-aware task conte
- `scripts/40_validate_ai_curation_output.py`
  - Used by workflows/steps.tsv
  - doc: Validate one AI curation JSON against its packet rowwise evidence table.  This script does NOT call an API.  It checks:   - rowwise_suggestions cover each packet row exactly once   - sample_map source_row_ids are valid   - sample_map duplicate/missing coverage   - obvious treatment contradictions:  
- `scripts/41e_batch_run_trusted_queue_production.py`
  - Used by workflows/steps.tsv
  - doc: Production-safe trusted RNA AI batch runner.  Key production rules:   - Default actionable classes: run_ai_first, run_ai_pilot, run_ai.   - Excludes PASS packets unless --force is used.   - Applies --limit AFTER filtering already-PASS packets.   - Dry-run by default. Use --execute to actually run AP
- `scripts/42_build_curator_excel_from_ai_outputs.py`
  - Used by workflows/steps.tsv
  - doc: Build human-friendly curator Excel workbook from active PASS AI outputs.  Inputs:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_packet_status_inventory.tsv   outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv   outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_red_flags.tsv   latest PASS vali
- `scripts/43_deep_qc_ai_outputs.py`
  - Used by workflows/steps.tsv
  - doc: Deep QC inventory for agentic AI curation outputs.  Read-only. Does not modify or delete anything.  Outputs:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/     ai_packet_status_inventory.tsv     ai_output_file_inventory.tsv     latest_validation_issue_summary.tsv     chunked_fallback_summary.tsv     supers
- `scripts/43c_semantic_red_flag_scan.py`
  - Used by workflows/steps.tsv
  - doc: Semantic red-flag scan for structurally PASS AI-curated packets.  Read-only. Does not modify AI outputs.  This is not a validator replacement. It produces curator-facing review flags:   - fallback rows   - low confidence / curator_check rows   - treatment contradictions or suspicious treatment label
- `scripts/47_extract_ai_study_summaries.py`
  - Used by workflows/steps.tsv
  - doc: Extract study_summary and global_warnings from active validated AI curation JSONs.  Read-only. Does not modify AI outputs.  Inputs:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_packet_status_inventory.tsv   latest PASS validation summaries   active AI JSONs  Outputs:   outputs/04_AGENTIC_AI_ASSIST/deep
- `scripts/47b_clean_ai_study_summary_table.py`
  - Used by workflows/steps.tsv
  - doc: Clean AI study summaries by separating curator-relevant warnings from technical/chunking warnings.  Input:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries.tsv  Outputs:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv   outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMA
- `scripts/48_rebuild_sample_map_from_rowwise.py`
  - Used by workflows/steps.tsv
  - doc: Rebuild sample_map deterministically from rowwise_suggestions for one AI curation JSON.  Use when validator reports:   sample_map_missing_source_row_id   sample_map_duplicate_source_row_id  This does not change rowwise_suggestions. It only rebuilds sample_map so that each rowwise source_row_id appea
- `scripts/49_finalize_trusted_rna_ai_phase.py`
  - Used by workflows/steps.tsv
  - doc: Finalize/report trusted PMID-linked RNA AI-curation phase.  This does not modify AI outputs. It summarizes:   - trusted RNA packet validation status   - held packets   - semantic red-flag burden   - latest curator Excel   - production notes for downstream GRN/curator review
- `scripts/50_inspect_chip_master.py`
  - Used by workflows/steps.tsv
  - doc: Inspect Plasmodium ChIP metadata master sheet before building ChIP AI pipeline.  This is read-only. It writes small summary tables/reports to:   outputs/06_CHIP_AI_ASSIST/00_inspect/
- `scripts/51_build_chip_rowwise_evidence_and_inventory.py`
  - Used by workflows/steps.tsv
  - doc: Build ChIP rowwise evidence and inventory tables.  This is ChIP-specific and read-only with respect to the master sheet.  Inputs:   data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx  Outputs:   outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/     chip_rowwise_evidence.tsv 
- `scripts/52_make_chip_ai_queue_and_control_policy.py`
  - Used by workflows/steps.tsv
  - doc: Make ChIP AI candidate queue and improved control-policy table.  Reads:   outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv  Writes:   outputs/06_CHIP_AI_ASSIST/02_chip_ai_queue/     chip_group_control_policy.tsv     chip_ai_candidate_queue.tsv     chip_initial_paperlinked_pilo
- `scripts/53a_fetch_chip_sra_runinfo_publication_signals.py`
  - Used by workflows/steps.tsv
  - doc: Fetch NCBI/SRA RunInfo for ChIP runs and extract publication signals.  This is the first ChIP publication-resolution step.  Reads:   outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv  Writes:   outputs/06_CHIP_AI_ASSIST/03_public_metadata/     chip_sra_runinfo.tsv     chip_roww
- `scripts/53b_resolve_chip_publications_via_entrez_links.py`
  - Used by workflows/steps.tsv
  - doc: Resolve ChIP BioProject publication links using Entrez links/searches.  This follows the RNA strategy:   public metadata -> publication candidates -> confidence-scored backfill suggestions.  Reads:   outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_publication_signal_by_bioproject.tsv   outputs/06_
- `scripts/54_curate_chip_publication_backfills.py`
  - Used by workflows/steps.tsv
  - doc: Curate ChIP publication backfill suggestions.  This script does NOT modify the master sheet.  It takes Entrez publication-resolution output and creates:   1. a curated BioProject -> PMID backfill decision table   2. a rowwise ChIP table with resolved publication fields   3. AP2-focused publication-r
- `scripts/55_make_chip_resolved_publication_queue.py`
  - Used by workflows/steps.tsv
  - doc: Build resolved-publication ChIP queue and PMID download manifest.  This script does NOT modify the master sheet and does NOT run AI.  Inputs:   outputs/06_CHIP_AI_ASSIST/05_publication_backfill_curated/     chip_rowwise_evidence_publication_enriched.tsv     chip_group_publication_enriched_inventory.
- `scripts/56_prepare_chip_pdf_download_manifest.py`
  - Used by workflows/steps.tsv
  - doc: Prepare ChIP PMID manifest for the existing open-access PDF downloader.  Reuses:   scripts/15_download_open_access_pdfs.py  Reads:   outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_pmid_download_manifest.tsv  Writes:   outputs/06_CHIP_AI_ASSIST/07_papers/     chip_pmids_needing_pdfs_for
- `scripts/57_build_chip_paper_availability_and_ai_readiness.py`
  - Used by workflows/steps.tsv
  - doc: Build ChIP paper availability and AI-readiness tables.  Purpose:   - Merge ChIP resolved-publication queue with PDF download status.   - Identify which PMID/BioProject groups can proceed to AI with full PDFs.   - Flag AP2/factor-priority groups missing PDFs.   - Produce curator-facing and pipeline-f
- `scripts/58_make_chip_ai_packets_from_ready_queue.py`
  - Used by workflows/steps.tsv
  - doc: Build ChIP AI packet JSON + rowwise sidecar TSVs from ready-with-PDF queue.  This adapts the RNA packet structure so existing script   scripts/39_run_agentic_ai_on_paper_packet.py can be reused with --packet-json and --queue.  No API calls are made here.  Inputs:   outputs/06_CHIP_AI_ASSIST/08_paper
- `scripts/59_preflight_qc_chip_ai_packets.py`
  - Used by workflows/steps.tsv
  - doc: Preflight QC for ChIP AI packets before API calls.  Checks:   - packet queue exists   - each packet JSON exists and parses   - each rowwise sidecar table exists   - PDF path exists   - table row count matches queue n_rows   - source_row_id is unique and nonblank   - required ChIP columns are present
- `scripts/59b_patch_chip_packet_control_roles.py`
  - Used by workflows/steps.tsv
  - doc: Patch ChIP AI packet tables/JSONs with deterministic preliminary sample roles.  Why:   Some ChIP rows have Target set to a factor/mark but background_sample=input.   Those rows are biologically input/background rows, even if earlier chip_role=chip_ip.   We preserve original chip_role but add explici
- `scripts/60_validate_chip_ai_output.py`
  - Used by workflows/steps.tsv
  - doc: Validate one ChIP AI-curation output against its packet table.  Checks:   - AI JSON parses   - packet_id matches   - rowwise_suggestions covers every source_row_id exactly once   - sample_map partitions every source_row_id exactly once   - rowwise Run values match packet table   - AI sample roles ma
- `scripts/60b_rebuild_chip_sample_map_from_rowwise.py`
  - Used by workflows/steps.tsv
  - doc: Deterministically rebuild ChIP sample_map from rowwise_suggestions.  Use only when:   - rowwise_suggestions cover every source_row_id exactly once   - sample_map has duplicate/missing source_row_ids   - rowwise_suggestions are otherwise structurally valid  This preserves the AI rowwise calls as the 
- `scripts/61_inventory_chip_ai_outputs.py`
  - Used by workflows/steps.tsv
  - doc: Inventory ChIP AI outputs across pilot/batch directories.  Purpose:   - Find latest raw and repaired AI JSON per packet.   - Prefer repaired JSON as active when present.   - Merge validation summaries.   - Produce a clean active-output inventory for downstream QC/housekeeping/Excel.  Inputs:   outpu
- `scripts/62_batch_run_chip_small_packets_production.py`
  - Used by workflows/steps.tsv
  - doc: Production runner for small ChIP AI packets.  Default behavior is DRY-RUN. Use --execute to actually call the API.  Workflow per packet:   1. Run scripts/39_run_agentic_ai_on_paper_packet.py   2. Validate with scripts/60_validate_chip_ai_output.py   3. If validation FAILs, attempt deterministic samp
- `scripts/63_prepare_chip_chunked_packet.py`
  - Used by workflows/steps.tsv
  - doc: Prepare chunked ChIP AI packet JSONs/tables for one large packet.  No API calls.  Strategy:   - Read original packet JSON/table.   - Partition source rows exactly once.   - Prefer not to split biological groups: role + target + stage + condition.   - Write chunk packet tables and JSONs.   - Write ch
- `scripts/64_merge_chip_chunk_outputs.py`
  - Used by workflows/steps.tsv
  - doc: Merge validated ChIP chunk AI outputs into one parent AI JSON.  This script:   - reads chunk queue   - chooses repaired JSON if available, otherwise raw AI JSON   - concatenates rowwise_suggestions   - verifies source_row_id coverage against the parent packet table   - writes a merged parent AI JSON
- `scripts/66_patch_chip_rowwise_roles_from_prelim.py`
  - Used by workflows/steps.tsv
  - doc: Patch ChIP AI rowwise roles using deterministic packet-table prelim roles.  Use only when:   - rowwise_suggestions cover every source_row_id exactly once   - failures are missing/unknown/control_sample role mismatches   - packet table has sample_role_prelim / chip_role_for_ai / matched_background_ru
- `scripts/67_finalize_chip_ai_phase.py`
  - Used by workflows/steps.tsv
- `scripts/68e_finalize_chip_curator_excel_v5.py`
  - Used by workflows/steps.tsv
  - doc: Final ChIP curator workbook polish.  Goals: - Add RNA-style paper/study summaries. - Add Paper_Summaries sheet. - Add direct visible color fills, not only conditional formatting. - Preserve V4 triage/problem aggregation. - Avoid Excel structured tables to prevent repair warnings.
- `scripts/70_package_curator_share_bundle.py`
  - Used by workflows/steps.tsv
  - doc: Package final curator-facing RNA + ChIP files into one shareable folder and zip.  This script does not run AI. It does not require an API token. It does not include raw PDFs, .env, raw AI JSONs, or bulky intermediate output folders.  Outputs:   outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<
- `scripts/71_export_chip_curator_companion_files.py`
  - Used by workflows/steps.tsv
  - doc: Export curator-facing ChIP companion files from the latest ChIP curator workbook.  Purpose:   - Make ChIP as shareable as RNA.   - Provide standalone TSV and MD files for Paper_Summaries, Curator_Triage,     Study_Review, Problem_Rows, Target_Control_Map_Review, etc.   - Copy the latest ChIP Excel i
- `scripts/72c_final_qc_chip_study_summaries.py`
  - Used by workflows/steps.tsv
  - doc: Final QC cleanup for ChIP AI study summaries.  Fixes: - Removes chunk-level language from curator-facing summaries. - Moves pipeline/repair/audit language out of curator warnings. - Gives the large AP2 merged packet a clean parent-level warning. - Rewrites CHIP_AI_STUDY_SUMMARIES_CLEAN.md in final R

### PRODUCTION_INFRA

- `scripts/00_audit_current_pipeline_for_reorg.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Audit current SRA curator pipeline before production reorganization.  This script is non-destructive. It does not call APIs. It does not modify existing outputs except writing audit reports.  Outputs:   outputs/00_REORG_AUDIT/current_pipeline_script_inventory.tsv   outputs/00_REORG_AUDIT/output_fold
- `scripts/01_define_active_workflow_and_outputs.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Define the current active workflow map and final output map.  This is manually curated from the successful RNA/ChIP run. It is non-destructive.  Outputs:   outputs/00_REORG_AUDIT/ACTIVE_SCRIPT_MAP.tsv   outputs/00_REORG_AUDIT/FINAL_OUTPUT_MAP.tsv   docs/ACTIVE_WORKFLOW_MAP.md
- `scripts/02_create_clean_final_release.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Create a clean final curator release folder.  Non-destructive: - reads existing final outputs - copies selected final files into results/final_curator_release/ - writes README + MANIFEST - creates a zip  No API calls. No modification of source outputs.
- `scripts/03_qc_final_release.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: QC the clean final curator release folder.  This script is read-only. It does not call APIs. It verifies that results/final_curator_release/ contains only expected curator-facing products.
- `scripts/04_pipeline_readiness_report.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Generate a publication-readiness report for the curator pipeline.  This script: - does not call APIs - runs final release QC - runs golden-output tests - checks workflow/docs/scripts exist - checks AI execution safety behavior - writes docs/PIPELINE_READINESS_REPORT.md
- `scripts/05_run_all_checks.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Run the production sanity-check suite.  This is the one-command local validation entry point.  It does not call APIs. It does not require OpenAI keys. It only regenerates ignored release artifacts under results/. It does not modify tracked documentation.  Checks: - production Python files compile - 
- `scripts/06_script_cleanup_inventory.py`
  - Production wrapper/QC/reorg infrastructure
  - doc: Create a script cleanup inventory before moving legacy files.  Non-destructive: - reads scripts/*.py - reads workflows/steps.tsv - classifies scripts as active workflow, production infrastructure, superseded candidate, or unmapped review - writes docs/SCRIPT_CLEANUP_INVENTORY.tsv - writes docs/SCRIP

### SUPERSEDED_CANDIDATE

- `scripts/68_build_chip_curator_excel.py`
  - Superseded by scripts/68e_finalize_chip_curator_excel_v5.py
- `scripts/68b_build_chip_curator_excel_v2.py`
  - Superseded by scripts/68e_finalize_chip_curator_excel_v5.py
  - doc: Build a more curator-facing ChIP review workbook.  This improves the first ChIP workbook by mirroring the RNA curator-facing logic:  - richer Study_Review - richer Rowwise_Review with source metadata - Target_Control_Map_Review includes confidence, review flags, evidence, and resolved control rows -
- `scripts/68c_polish_chip_curator_excel_v3.py`
  - Superseded by scripts/68e_finalize_chip_curator_excel_v5.py
  - doc: Polish ChIP curator workbook to be closer to RNA curator-facing style.  Input:   latest workbook pointed to by:     outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt  Output:   outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_v3_<timestamp>.xlsx  No API required
- `scripts/68d_polish_chip_curator_excel_v4.py`
  - Superseded by scripts/68e_finalize_chip_curator_excel_v5.py
  - doc: Final curator-facing polish for ChIP workbook.  Main goals: - Make Problem_Rows match RNA style: one row per source row, aggregated flags/messages. - Preserve original detailed issue rows in Problem_Details. - Flag target-control rows where AI names a background class but no concrete control source 
- `scripts/72_export_chip_study_summaries_clean.py`
  - Superseded by scripts/72c_final_qc_chip_study_summaries.py
  - doc: Export ChIP whole-paper AI study summaries, RNA-style.  This reads the active validated ChIP AI JSONs directly and extracts the `study_summary` dict from each JSON.  Outputs:   outputs/06_CHIP_AI_ASSIST/23_study_summaries/     CHIP_AI_STUDY_SUMMARIES_CLEAN.md     chip_ai_study_summaries_clean.tsv   
- `scripts/72b_qc_and_export_chip_study_summaries_rna_style.py`
  - Superseded by scripts/72c_final_qc_chip_study_summaries.py
  - doc: QC and export ChIP study summaries in RNA-style format.  This fixes the previous ChIP markdown problem: - removes always-empty sections like "Main findings: Not specified" - writes compact one-packet-per-block summaries like RNA - writes a QC report showing missing/non-informative fields - keeps TSV

### UNMAPPED_REVIEW

- `scripts/01_filter_master_by_pmid.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/02_fetch_sra_runinfo_for_master_rows.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/03_fetch_biosample_metadata_for_master_rows.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/04_populate_master_from_biosample.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/05_evaluate_against_gold_standard.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/06_list_pmid_candidates.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/07_extract_paper_context.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/08_apply_paper_context_to_master.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/09_make_curator_review_view.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/10_make_llm_packet.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/11_llm_curator_assist.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/12_add_llm_to_curator_review.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/13_add_control_group_columns.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/14_add_curator_condition_fields.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/16_run_batch_curator_pipeline.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/17_apply_special_pmid_handling.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/18_make_curator_review_index.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/19_make_group_level_curator_index.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/20_make_spotcheck_workbook.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/21_patch_pmid_31737630_dis3.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/22_patch_pmid_34365503_timepoints.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/23_patch_pmid_32552779_arp4_glcn.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/26_freeze_current_outputs.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/27_organize_outputs.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/29_make_group_level_curator_review.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Create a group-level curator review workbook from the stable-ID rowwise table.  This script does NOT call AI and does NOT modify the master sheet. It prepares a human/agent-ready curator table.  Input:   outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv  Outputs:   outputs/00_FINAL_
- `scripts/30_make_agentic_ai_input_packets.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Create compact input packets for the future API-based agentic AI curator.  This script does NOT call an API. This script does NOT modify metadata. This script only prepares per-curation-group JSON packets that contain:   - stable IDs   - current parsed metadata   - run/BioSample identifiers   - comp
- `scripts/31_test_openai_api.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/32_run_agentic_ai_on_packet.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Run the optional API-based agentic curator on ONE input packet.  This is intentionally single-packet only for pilot testing.  Safety:   - API disabled by default unless AGENTIC_AI_ENABLE_API=1   - does not modify master workbook   - does not modify group-level curator table   - writes suggestions on
- `scripts/36_rank_paper_packets_for_ai.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Rank paper/BioProject packets for optional agentic AI curation.  This script does NOT call an API.  It creates a priority queue that:   - prioritizes packets where paper-reading AI is likely useful   - flags well-based / single-cell uniform packets as low-value or skip   - gives human curators a ran
- `scripts/41_batch_run_agentic_ai_on_trusted_queue.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Batch runner for trusted PMID-linked RNA-seq paper/BioProject packets.  Default behavior is DRY-RUN ONLY. Use --execute to call the API runner.  This script intentionally does NOT read any manual/gold-standard curation files. Gold standards should be used only later for independent verification.  Ty
- `scripts/41b_compare_ai_to_manual_gold_pilot.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Independent gold-standard overlap check for one AI curation pilot.  This script is intentionally POST HOC. It must NOT be called by the AI runner and must NOT be used for training/prompt fitting. It compares an already-produced AI curation JSON against a manual curated workbook, limited to overlappi
- `scripts/41c_run_agentic_ai_chunked_large_packet.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Chunked AI runner for large paper packets.  Design:   - Run script 39 on rowwise chunks.   - Collect only valid rowwise_suggestions.   - Ignore AI sample_map for final merged large-packet output.   - Build sample_map deterministically from merged rowwise_suggestions.   - If AI misses rows, add deter
- `scripts/41d_batch_run_trusted_queue_auto_chunked.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Auto-dispatch batch runner for trusted RNA AI packets.  Small/moderate packets:   -> scripts/41_batch_run_agentic_ai_on_trusted_queue.py  Large packets:   -> scripts/41c_run_agentic_ai_chunked_large_packet.py  This keeps the original one-shot batch runner stable, while using chunked mode when row co
- `scripts/43b_semantic_spotcheck_pass_packets.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Semantic spot-check table for PASS AI-curated packets.  Read-only. Does not modify outputs.  Creates:   outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_spotcheck_rows.tsv   outputs/04_AGENTIC_AI_ASSIST/deep_qc/SEMANTIC_SPOTCHECK_SUMMARY.md
- `scripts/44_housekeep_ai_outputs.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Housekeeping planner for AI curation outputs.  Default is DRY-RUN:   - builds a manifest of active vs superseded/intermediate files   - proposes archive moves   - does NOT move or delete anything  With --execute:   - moves proposed archive files into:       outputs/04_AGENTIC_AI_ASSIST/_archive_supe
- `scripts/45_find_rna_chip_overlap_bioqc_candidates.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Find candidate papers/BioProjects for biological QC across RNA and ChIP master sheets.  Read-only.  Outputs:   outputs/05_BIOLOGICAL_QC/rna_chip_overlap_candidates.tsv
- `scripts/48b_rebuild_sample_map_from_rowwise_biokey.py`
  - Not in active workflow map; review before moving/deleting
  - doc: Rebuild sample_map deterministically from rowwise_suggestions, but split heterogeneous sample_class_id groups by biological rowwise fields.  Use when:   - rowwise_suggestions cover every packet row exactly once   - sample_map has missing/duplicate source_row_id values   - sample_class_id may be too 
- `scripts/65_audit_chip_repeats_and_chunk_failures.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/69_postdoc_handoff_inventory.py`
  - Not in active workflow map; review before moving/deleting
- `scripts/run_curator_pipeline.py`
  - Not in active workflow map; review before moving/deleting
