# Active Workflow Map

Generated: 2026-06-04T17:32:06

This document defines the currently successful RNA/ChIP curator-assist pipeline before production refactoring.

Important: this is a map of the current working workflow, not the final desired repository organization.

## Core policy

- API/AI execution is optional and must remain off by default.
- NCBI/PubMed/SRA fetching is deterministic public metadata retrieval, not AI.
- Deterministic validators and repairs are separate from AI.
- AI suggestions are curator aids only; curator-final columns are authoritative.
- Final products should be collected into one release folder and zip.

## Active scripts by step

### shared

#### Step 00: `01_prepare_rowwise_master.py`

- Current script: `scripts/28_add_stable_ids_to_master.py`
- API status: no
- Current status: active_for_RNA_foundation
- Purpose: Add stable source_row_id and curation_group_id to the RNA master metadata without modifying the original Excel.
- Main inputs: RNA master Excel
- Main outputs: outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv

### shared/RNA

#### Step 01: `02_fetch_public_metadata.py`

- Current script: `scripts/33_fetch_public_sra_biosample_metadata.py`
- API status: NCBI only; no OpenAI
- Current status: active_for_RNA_public_metadata
- Purpose: Fetch/cache SRA RunInfo and BioSample XML metadata for runs.
- Main inputs: rowwise stable-ID table
- Main outputs: data/sra_runinfo_cache; data/biosample_cache

#### Step 02: `03_build_rowwise_public_evidence.py`

- Current script: `scripts/34_build_rowwise_public_metadata_evidence.py`
- API status: no
- Current status: active_for_RNA_public_metadata
- Purpose: Convert cached SRA/BioSample metadata into compact rowwise evidence for AI/curator review.
- Main inputs: rowwise stable-ID table; SRA/BioSample cache
- Main outputs: rowwise public metadata evidence TSV

#### Step 03: `04_build_paper_packets.py`

- Current script: `scripts/35_make_paper_level_ai_packets.py`
- API status: no
- Current status: active_for_RNA_packets
- Purpose: Create PMID/BioProject packet JSONs and sidecar rowwise TSVs.
- Main inputs: rowwise public metadata evidence; paper/PDF context
- Main outputs: paper packet JSONs and rowwise sidecar TSVs

#### Step 04: `05_resolve_publications.py`

- Current script: `scripts/37_resolve_publication_links_for_packets.py`
- API status: NCBI only; no OpenAI
- Current status: active_for_RNA_publication_resolution
- Purpose: Resolve or flag publication links for paper/BioProject packets using public metadata and NCBI/Entrez signals.
- Main inputs: paper packets; BioProject/PMID metadata
- Main outputs: trusted PMID packet tables and unresolved/held tables

#### Step 05: `06_make_ai_queue.py`

- Current script: `scripts/38_make_trusted_assay_aware_ai_queue.py`
- API status: no
- Current status: active_for_RNA_ai_queue
- Purpose: Build trusted assay-aware AI queue; exclude or hold unsafe/no-PMID packets.
- Main inputs: trusted PMID packets; rowwise metadata
- Main outputs: AI priority queue

### shared/RNA/ChIP

#### Step 06: `07_run_ai_on_packet_optional.py`

- Current script: `scripts/39_run_agentic_ai_on_paper_packet.py`
- API status: OpenAI optional; disabled unless explicitly enabled
- Current status: active_shared_ai_runner
- Purpose: Run AI on one packet: paper text + rowwise evidence -> study_summary, sample_map, rowwise_suggestions, readiness, warnings.
- Main inputs: packet JSON; rowwise sidecar TSV; PDF/paper text
- Main outputs: AI curation JSON

### RNA

#### Step 07: `08_run_rna_ai_batch_optional.py`

- Current script: `scripts/41e_batch_run_trusted_queue_production.py`
- API status: OpenAI optional; dry-run by default
- Current status: active_RNA_ai_batch
- Purpose: Production-safe batch runner for trusted RNA packets; skips already PASS unless forced.
- Main inputs: trusted RNA AI queue
- Main outputs: RNA AI output directories

#### Step 08: `09_validate_rna_ai_output.py`

- Current script: `scripts/40_validate_ai_curation_output.py`
- API status: no
- Current status: active_RNA_validation
- Purpose: Validate one RNA AI JSON: rowwise coverage, source_row_id uniqueness, sample_map validity.
- Main inputs: AI JSON; packet table
- Main outputs: validation summary and issue tables

#### Step 09: `10_repair_rna_sample_map.py`

- Current script: `scripts/48_rebuild_sample_map_from_rowwise.py`
- API status: no
- Current status: active_RNA_safe_repair
- Purpose: Deterministically rebuild sample_map from rowwise_suggestions when rowwise coverage is exact.
- Main inputs: AI JSON with valid rowwise_suggestions
- Main outputs: repaired AI JSON plus audit

#### Step 10: `11_inventory_rna_ai_outputs.py`

- Current script: `scripts/43_deep_qc_ai_outputs.py`
- API status: no
- Current status: active_RNA_inventory
- Purpose: Inventory RNA AI outputs and select active validated PASS outputs.
- Main inputs: RNA AI output folders; validation summaries
- Main outputs: deep_qc inventory tables

#### Step 11: `12_scan_rna_semantic_flags.py`

- Current script: `scripts/43c_semantic_red_flag_scan.py`
- API status: no
- Current status: active_RNA_semantic_QC
- Purpose: Scan structurally PASS RNA outputs for low confidence, fallback, curator_check, or suspicious semantic patterns.
- Main inputs: active PASS RNA AI JSONs
- Main outputs: semantic red flag summary and row tables

#### Step 12: `13_extract_rna_study_summaries.py`

- Current script: `scripts/47_extract_ai_study_summaries.py`
- API status: no
- Current status: active_RNA_summary_export
- Purpose: Extract study_summary and warnings from active validated RNA AI JSONs.
- Main inputs: active PASS RNA AI JSONs
- Main outputs: ai_study_summaries.tsv

#### Step 13: `14_clean_rna_study_summaries.py`

- Current script: `scripts/47b_clean_ai_study_summary_table.py`
- API status: no
- Current status: active_RNA_summary_cleanup
- Purpose: Clean RNA study summaries and separate curator warnings from technical/chunking warnings.
- Main inputs: ai_study_summaries.tsv
- Main outputs: AI_STUDY_SUMMARIES_CLEAN.md; ai_study_summaries_clean.tsv

#### Step 14: `15_build_rna_curator_workbook.py`

- Current script: `scripts/42_build_curator_excel_from_ai_outputs.py`
- API status: no
- Current status: active_RNA_curator_excel
- Purpose: Build RNA curator-facing Excel workbook from active PASS AI outputs and QC summaries.
- Main inputs: active RNA inventory; study summaries; semantic QC
- Main outputs: RNA curator Excel workbook

#### Step 15: `16_finalize_rna_curator_release.py`

- Current script: `scripts/49_finalize_trusted_rna_ai_phase.py`
- API status: no
- Current status: active_RNA_finalization
- Purpose: Finalize trusted RNA phase, held packets, red flags, and share package summary.
- Main inputs: RNA curator Excel; deep QC tables
- Main outputs: TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md; trusted RNA share folder

### ChIP

#### Step 20: `20_inspect_chip_input.py`

- Current script: `scripts/50_inspect_chip_master.py`
- API status: no
- Current status: active_ChIP_inspection
- Purpose: Inspect ChIP master metadata columns, factor tags, PMIDs, BioProjects, and basic structure.
- Main inputs: ChIP master Excel
- Main outputs: CHIP_MASTER_INSPECTION_REPORT.md

#### Step 21: `21_build_chip_rowwise_evidence.py`

- Current script: `scripts/51_build_chip_rowwise_evidence_and_inventory.py`
- API status: no
- Current status: active_ChIP_rowwise_evidence
- Purpose: Build ChIP rowwise evidence table with stable source_row_id, target, role hints, stage/strain/condition, and public metadata fields.
- Main inputs: ChIP master Excel
- Main outputs: chip_rowwise_evidence.tsv; inventory/report

#### Step 22: `22_build_chip_queue_and_control_policy.py`

- Current script: `scripts/52_make_chip_ai_queue_and_control_policy.py`
- API status: no
- Current status: active_ChIP_policy_queue
- Purpose: Create ChIP group/control policy and candidate queue; identify target/control structure before AI.
- Main inputs: chip_rowwise_evidence.tsv
- Main outputs: chip_group_control_policy.tsv; chip_ai_candidate_queue.tsv

#### Step 23: `23_fetch_chip_public_metadata.py`

- Current script: `scripts/53a_fetch_chip_sra_runinfo_publication_signals.py`
- API status: NCBI only; no OpenAI
- Current status: active_ChIP_publication_resolution
- Purpose: Fetch ChIP SRA RunInfo/public metadata and extract publication signals.
- Main inputs: chip_rowwise_evidence.tsv
- Main outputs: ChIP public metadata and publication signal tables

#### Step 24: `24_resolve_chip_publications.py`

- Current script: `scripts/53b_resolve_chip_publications_via_entrez_links.py`
- API status: NCBI only; no OpenAI
- Current status: active_ChIP_publication_resolution
- Purpose: Resolve BioProject -> PMID links using Entrez links/searches and confidence-scored suggestions.
- Main inputs: ChIP public metadata publication signals
- Main outputs: Entrez publication-resolution table

#### Step 25: `25_curate_chip_publication_backfills.py`

- Current script: `scripts/54_curate_chip_publication_backfills.py`
- API status: no
- Current status: active_ChIP_publication_resolution
- Purpose: Apply deterministic/manual backfill decisions for missing/wrong PMID links without modifying master Excel.
- Main inputs: Entrez publication-resolution table
- Main outputs: curated BioProject->PMID backfill table; rowwise evidence with resolved publication

#### Step 26: `26_make_chip_resolved_publication_queue.py`

- Current script: `scripts/55_make_chip_resolved_publication_queue.py`
- API status: no
- Current status: active_ChIP_publication_queue
- Purpose: Build resolved-publication ChIP queue and PMID download manifest.
- Main inputs: curated backfill table; rowwise evidence with resolved publication
- Main outputs: chip_resolved_publication_queue.tsv; chip_pmid_download_manifest.tsv

#### Step 27: `27_prepare_chip_paper_downloads.py`

- Current script: `scripts/56_prepare_chip_pdf_download_manifest.py`
- API status: no
- Current status: active_ChIP_paper_preparation
- Purpose: Prepare ChIP PMID manifest for open-access PDF downloader.
- Main inputs: chip_pmid_download_manifest.tsv
- Main outputs: PDF download manifest for scripts/15_download_open_access_pdfs.py

### shared

#### Step 28: `28_download_open_access_papers_optional.py`

- Current script: `scripts/15_download_open_access_pdfs.py`
- API status: public web/NCBI/PMC; no OpenAI
- Current status: active_shared_paper_download
- Purpose: Download open-access papers/PDFs where possible.
- Main inputs: PMID download manifest
- Main outputs: PDF/text cache and download status table

### ChIP

#### Step 29: `29_build_chip_ai_readiness.py`

- Current script: `scripts/57_build_chip_paper_availability_and_ai_readiness.py`
- API status: no
- Current status: active_ChIP_ai_readiness
- Purpose: Merge resolved ChIP queue with PDF availability and define AI-ready packets.
- Main inputs: resolved publication queue; PDF download status
- Main outputs: chip_paper_availability_review.tsv; chip_ai_ready_queue.tsv

#### Step 30: `30_build_chip_ai_packets.py`

- Current script: `scripts/58_make_chip_ai_packets_from_ready_queue.py`
- API status: no
- Current status: active_ChIP_packet_build
- Purpose: Build ChIP AI packet JSONs and rowwise sidecar TSVs using the shared packet format.
- Main inputs: chip_ai_ready_queue.tsv; paper text/PDF; rowwise evidence
- Main outputs: chip_ai_packet_queue.tsv; packet JSONs; packet rowwise TSVs

#### Step 31: `31_preflight_chip_ai_packets.py`

- Current script: `scripts/59_preflight_qc_chip_ai_packets.py`
- API status: no
- Current status: active_ChIP_preflight_QC
- Purpose: Check packet JSON/sidecar/PDF existence, row counts, source_row_id uniqueness, and control flags before AI.
- Main inputs: chip_ai_packet_queue.tsv
- Main outputs: CHIP_AI_PACKET_PREFLIGHT_QC_REPORT.md; problem rows

#### Step 32: `32_patch_chip_prelim_control_roles.py`

- Current script: `scripts/59b_patch_chip_packet_control_roles.py`
- API status: no
- Current status: active_ChIP_pre_ai_patch
- Purpose: Patch deterministic preliminary ChIP roles where metadata target labels conflict with background/input role evidence.
- Main inputs: chip packet JSONs and packet rowwise tables
- Main outputs: patched packet JSON/tables and audit

#### Step 33: `33_run_chip_ai_small_packets_optional.py`

- Current script: `scripts/62_batch_run_chip_small_packets_production.py`
- API status: OpenAI optional; dry-run by default
- Current status: active_ChIP_ai_batch
- Purpose: Run AI on small ChIP packets; validate; optionally repair sample_map; summarize final status.
- Main inputs: chip_ai_packet_queue.tsv
- Main outputs: small-packet ChIP AI output directories and batch results

#### Step 34: `34_prepare_large_chip_packet_chunks.py`

- Current script: `scripts/63_prepare_chip_chunked_packet.py`
- API status: no
- Current status: active_ChIP_chunking
- Purpose: Split one large ChIP packet into target-centered chunks without losing row coverage.
- Main inputs: large parent packet JSON/table
- Main outputs: chunk packet JSONs, chunk tables, chunk queue

#### Step 35: `35_merge_large_chip_packet_chunks.py`

- Current script: `scripts/64_merge_chip_chunk_outputs.py`
- API status: no
- Current status: active_ChIP_chunk_merge
- Purpose: Merge validated chunk-level rowwise_suggestions into parent AI JSON; verify parent source_row_id coverage.
- Main inputs: validated chunk AI JSONs; parent packet table
- Main outputs: merged parent AI JSON and audit

#### Step 36: `36_validate_chip_ai_output.py`

- Current script: `scripts/60_validate_chip_ai_output.py`
- API status: no
- Current status: active_ChIP_validation
- Purpose: Validate ChIP AI JSON: rowwise coverage, sample_map partitioning, role consistency, target-control readiness.
- Main inputs: ChIP AI JSON; packet table
- Main outputs: validation summary, validation issues, validation report

#### Step 37: `37_repair_chip_sample_map.py`

- Current script: `scripts/60b_rebuild_chip_sample_map_from_rowwise.py`
- API status: no
- Current status: active_ChIP_safe_repair
- Purpose: Deterministically rebuild ChIP sample_map from rowwise_suggestions when rowwise coverage is exact.
- Main inputs: AI JSON with complete rowwise_suggestions
- Main outputs: samplemap_rebuilt AI JSON and audit

#### Step 38: `38_patch_chip_rowwise_roles.py`

- Current script: `scripts/66_patch_chip_rowwise_roles_from_prelim.py`
- API status: no
- Current status: active_ChIP_safe_repair
- Purpose: Patch AI rowwise role labels from deterministic packet-table prelim roles when coverage is exact and mismatches are role-only.
- Main inputs: AI JSON; packet table
- Main outputs: role-patched AI JSON and patch audit

#### Step 39: `39_inventory_chip_ai_outputs.py`

- Current script: `scripts/61_inventory_chip_ai_outputs.py`
- API status: no
- Current status: active_ChIP_inventory
- Purpose: Find latest raw/repaired ChIP AI JSON per packet; merge validation summaries; select active validated outputs.
- Main inputs: ChIP AI output dirs; validation summaries
- Main outputs: chip_ai_active_validated_outputs.tsv; inventory report

#### Step 40: `40_finalize_chip_ai_phase.py`

- Current script: `scripts/67_finalize_chip_ai_phase.py`
- API status: no
- Current status: active_ChIP_final_QC
- Purpose: Finalize ChIP AI phase and export rowwise review and target-control map review tables.
- Main inputs: active validated ChIP AI outputs
- Main outputs: CHIP_AI_PHASE_COMPLETION_REPORT.md; chip_rowwise_review.tsv; chip_target_control_map_review.tsv

#### Step 41: `41_build_chip_curator_workbook.py`

- Current script: `scripts/68e_finalize_chip_curator_excel_v5.py`
- API status: no
- Current status: active_ChIP_curator_excel
- Purpose: Build final ChIP curator Excel with paper summaries, triage, color coding, problem rows, target-control map, and rowwise review.
- Main inputs: active ChIP inventory; final QC tables
- Main outputs: latest ChIP curator Excel workbook

#### Step 42: `42_export_chip_companion_files.py`

- Current script: `scripts/71_export_chip_curator_companion_files.py`
- API status: no
- Current status: active_ChIP_companion_exports
- Purpose: Export standalone ChIP TSV/MD companion files from the final workbook.
- Main inputs: latest ChIP curator Excel workbook
- Main outputs: outputs/06_CHIP_AI_ASSIST/22_curator_share_files

#### Step 43: `43_clean_chip_study_summaries.py`

- Current script: `scripts/72c_final_qc_chip_study_summaries.py`
- API status: no
- Current status: active_ChIP_summary_cleanup
- Purpose: Final cleanup of ChIP study summaries: remove chunk/pipeline artifacts from curator-facing text.
- Main inputs: chip_ai_study_summaries_clean.tsv/md
- Main outputs: CHIP_AI_STUDY_SUMMARIES_CLEAN.md; FINAL_QC report

### shared

#### Step 90: `90_package_curator_release.py`

- Current script: `scripts/70_package_curator_share_bundle.py`
- API status: no
- Current status: active_final_packaging
- Purpose: Package final RNA + ChIP curator-facing files into one folder and zip; excludes raw PDFs, .env, raw AI JSONs, and bulky intermediates.
- Main inputs: latest RNA and ChIP curator outputs
- Main outputs: outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>.zip

## Final output map

- `outputs/99_CURATOR_SHARE_BUNDLES/LATEST_CURATOR_SHARE_BUNDLE.txt`
  - category: final_bundle
  - keep: yes
  - purpose: Pointer to latest final curator release folder and zip.
- `outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>.zip`
  - category: final_bundle
  - keep: yes
  - purpose: Single shareable package for Shalini/curators/postdocs.
- `outputs/04_AGENTIC_AI_ASSIST/curator_share/trusted_rna_<timestamp>/curator_review_<timestamp>.xlsx`
  - category: RNA_final
  - keep: yes
  - purpose: Final RNA curator review workbook.
- `outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES_CLEAN.md`
  - category: RNA_final
  - keep: yes
  - purpose: RNA whole-paper AI study summaries, cleaned.
- `outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md`
  - category: RNA_final
  - keep: yes
  - purpose: RNA phase completion/QC report.
- `outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt`
  - category: ChIP_final
  - keep: yes
  - purpose: Pointer to latest final ChIP curator Excel workbook.
- `outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_v5_<timestamp>.xlsx`
  - category: ChIP_final
  - keep: yes
  - purpose: Final ChIP curator review workbook.
- `outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md`
  - category: ChIP_final
  - keep: yes
  - purpose: ChIP AI phase completion/QC report.
- `outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv`
  - category: ChIP_final
  - keep: yes
  - purpose: Final ChIP rowwise review table for curators/app/downstream.
- `outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv`
  - category: ChIP_final
  - keep: yes
  - purpose: Final ChIP target-control map review table.
- `outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_CLEAN.md`
  - category: ChIP_final
  - keep: yes
  - purpose: Final ChIP whole-paper AI study summaries, cleaned.
- `outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md`
  - category: ChIP_final
  - keep: yes
  - purpose: Final ChIP summary cleanup QC.

## Refactoring implication

The next production step is to create clean workflow wrappers using the production_name values above, while leaving legacy scripts in place.
Only after wrapper parity tests pass should legacy scripts be moved into legacy_scripts/.