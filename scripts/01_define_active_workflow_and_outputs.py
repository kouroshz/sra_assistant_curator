#!/usr/bin/env python3
"""
Define the current active workflow map and final output map.

This is manually curated from the successful RNA/ChIP run.
It is non-destructive.

Outputs:
  outputs/00_REORG_AUDIT/ACTIVE_SCRIPT_MAP.tsv
  outputs/00_REORG_AUDIT/FINAL_OUTPUT_MAP.tsv
  docs/ACTIVE_WORKFLOW_MAP.md
"""

from pathlib import Path
from datetime import datetime
import csv

OUT = Path("outputs/00_REORG_AUDIT")
OUT.mkdir(parents=True, exist_ok=True)
DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)


ACTIVE = [
    # ------------------------------------------------------------------
    # Shared / RNA foundation
    # ------------------------------------------------------------------
    {
        "step": "00",
        "assay": "shared",
        "script": "scripts/28_add_stable_ids_to_master.py",
        "production_name": "01_prepare_rowwise_master.py",
        "api": "no",
        "status": "active_for_RNA_foundation",
        "purpose": "Add stable source_row_id and curation_group_id to the RNA master metadata without modifying the original Excel.",
        "main_inputs": "RNA master Excel",
        "main_outputs": "outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv",
    },
    {
        "step": "01",
        "assay": "shared/RNA",
        "script": "scripts/33_fetch_public_sra_biosample_metadata.py",
        "production_name": "02_fetch_public_metadata.py",
        "api": "NCBI only; no OpenAI",
        "status": "active_for_RNA_public_metadata",
        "purpose": "Fetch/cache SRA RunInfo and BioSample XML metadata for runs.",
        "main_inputs": "rowwise stable-ID table",
        "main_outputs": "data/sra_runinfo_cache; data/biosample_cache",
    },
    {
        "step": "02",
        "assay": "shared/RNA",
        "script": "scripts/34_build_rowwise_public_metadata_evidence.py",
        "production_name": "03_build_rowwise_public_evidence.py",
        "api": "no",
        "status": "active_for_RNA_public_metadata",
        "purpose": "Convert cached SRA/BioSample metadata into compact rowwise evidence for AI/curator review.",
        "main_inputs": "rowwise stable-ID table; SRA/BioSample cache",
        "main_outputs": "rowwise public metadata evidence TSV",
    },
    {
        "step": "03",
        "assay": "shared/RNA",
        "script": "scripts/35_make_paper_level_ai_packets.py",
        "production_name": "04_build_paper_packets.py",
        "api": "no",
        "status": "active_for_RNA_packets",
        "purpose": "Create PMID/BioProject packet JSONs and sidecar rowwise TSVs.",
        "main_inputs": "rowwise public metadata evidence; paper/PDF context",
        "main_outputs": "paper packet JSONs and rowwise sidecar TSVs",
    },
    {
        "step": "04",
        "assay": "shared/RNA",
        "script": "scripts/37_resolve_publication_links_for_packets.py",
        "production_name": "05_resolve_publications.py",
        "api": "NCBI only; no OpenAI",
        "status": "active_for_RNA_publication_resolution",
        "purpose": "Resolve or flag publication links for paper/BioProject packets using public metadata and NCBI/Entrez signals.",
        "main_inputs": "paper packets; BioProject/PMID metadata",
        "main_outputs": "trusted PMID packet tables and unresolved/held tables",
    },
    {
        "step": "05",
        "assay": "shared/RNA",
        "script": "scripts/38_make_trusted_assay_aware_ai_queue.py",
        "production_name": "06_make_ai_queue.py",
        "api": "no",
        "status": "active_for_RNA_ai_queue",
        "purpose": "Build trusted assay-aware AI queue; exclude or hold unsafe/no-PMID packets.",
        "main_inputs": "trusted PMID packets; rowwise metadata",
        "main_outputs": "AI priority queue",
    },
    {
        "step": "06",
        "assay": "shared/RNA/ChIP",
        "script": "scripts/39_run_agentic_ai_on_paper_packet.py",
        "production_name": "07_run_ai_on_packet_optional.py",
        "api": "OpenAI optional; disabled unless explicitly enabled",
        "status": "active_shared_ai_runner",
        "purpose": "Run AI on one packet: paper text + rowwise evidence -> study_summary, sample_map, rowwise_suggestions, readiness, warnings.",
        "main_inputs": "packet JSON; rowwise sidecar TSV; PDF/paper text",
        "main_outputs": "AI curation JSON",
    },
    {
        "step": "07",
        "assay": "RNA",
        "script": "scripts/41e_batch_run_trusted_queue_production.py",
        "production_name": "08_run_rna_ai_batch_optional.py",
        "api": "OpenAI optional; dry-run by default",
        "status": "active_RNA_ai_batch",
        "purpose": "Production-safe batch runner for trusted RNA packets; skips already PASS unless forced.",
        "main_inputs": "trusted RNA AI queue",
        "main_outputs": "RNA AI output directories",
    },
    {
        "step": "08",
        "assay": "RNA",
        "script": "scripts/40_validate_ai_curation_output.py",
        "production_name": "09_validate_rna_ai_output.py",
        "api": "no",
        "status": "active_RNA_validation",
        "purpose": "Validate one RNA AI JSON: rowwise coverage, source_row_id uniqueness, sample_map validity.",
        "main_inputs": "AI JSON; packet table",
        "main_outputs": "validation summary and issue tables",
    },
    {
        "step": "09",
        "assay": "RNA",
        "script": "scripts/48_rebuild_sample_map_from_rowwise.py",
        "production_name": "10_repair_rna_sample_map.py",
        "api": "no",
        "status": "active_RNA_safe_repair",
        "purpose": "Deterministically rebuild sample_map from rowwise_suggestions when rowwise coverage is exact.",
        "main_inputs": "AI JSON with valid rowwise_suggestions",
        "main_outputs": "repaired AI JSON plus audit",
    },
    {
        "step": "10",
        "assay": "RNA",
        "script": "scripts/43_deep_qc_ai_outputs.py",
        "production_name": "11_inventory_rna_ai_outputs.py",
        "api": "no",
        "status": "active_RNA_inventory",
        "purpose": "Inventory RNA AI outputs and select active validated PASS outputs.",
        "main_inputs": "RNA AI output folders; validation summaries",
        "main_outputs": "deep_qc inventory tables",
    },
    {
        "step": "11",
        "assay": "RNA",
        "script": "scripts/43c_semantic_red_flag_scan.py",
        "production_name": "12_scan_rna_semantic_flags.py",
        "api": "no",
        "status": "active_RNA_semantic_QC",
        "purpose": "Scan structurally PASS RNA outputs for low confidence, fallback, curator_check, or suspicious semantic patterns.",
        "main_inputs": "active PASS RNA AI JSONs",
        "main_outputs": "semantic red flag summary and row tables",
    },
    {
        "step": "12",
        "assay": "RNA",
        "script": "scripts/47_extract_ai_study_summaries.py",
        "production_name": "13_extract_rna_study_summaries.py",
        "api": "no",
        "status": "active_RNA_summary_export",
        "purpose": "Extract study_summary and warnings from active validated RNA AI JSONs.",
        "main_inputs": "active PASS RNA AI JSONs",
        "main_outputs": "ai_study_summaries.tsv",
    },
    {
        "step": "13",
        "assay": "RNA",
        "script": "scripts/47b_clean_ai_study_summary_table.py",
        "production_name": "14_clean_rna_study_summaries.py",
        "api": "no",
        "status": "active_RNA_summary_cleanup",
        "purpose": "Clean RNA study summaries and separate curator warnings from technical/chunking warnings.",
        "main_inputs": "ai_study_summaries.tsv",
        "main_outputs": "AI_STUDY_SUMMARIES_CLEAN.md; ai_study_summaries_clean.tsv",
    },
    {
        "step": "14",
        "assay": "RNA",
        "script": "scripts/42_build_curator_excel_from_ai_outputs.py",
        "production_name": "15_build_rna_curator_workbook.py",
        "api": "no",
        "status": "active_RNA_curator_excel",
        "purpose": "Build RNA curator-facing Excel workbook from active PASS AI outputs and QC summaries.",
        "main_inputs": "active RNA inventory; study summaries; semantic QC",
        "main_outputs": "RNA curator Excel workbook",
    },
    {
        "step": "15",
        "assay": "RNA",
        "script": "scripts/49_finalize_trusted_rna_ai_phase.py",
        "production_name": "16_finalize_rna_curator_release.py",
        "api": "no",
        "status": "active_RNA_finalization",
        "purpose": "Finalize trusted RNA phase, held packets, red flags, and share package summary.",
        "main_inputs": "RNA curator Excel; deep QC tables",
        "main_outputs": "TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md; trusted RNA share folder",
    },

    # ------------------------------------------------------------------
    # ChIP-specific pipeline
    # ------------------------------------------------------------------
    {
        "step": "20",
        "assay": "ChIP",
        "script": "scripts/50_inspect_chip_master.py",
        "production_name": "20_inspect_chip_input.py",
        "api": "no",
        "status": "active_ChIP_inspection",
        "purpose": "Inspect ChIP master metadata columns, factor tags, PMIDs, BioProjects, and basic structure.",
        "main_inputs": "ChIP master Excel",
        "main_outputs": "CHIP_MASTER_INSPECTION_REPORT.md",
    },
    {
        "step": "21",
        "assay": "ChIP",
        "script": "scripts/51_build_chip_rowwise_evidence_and_inventory.py",
        "production_name": "21_build_chip_rowwise_evidence.py",
        "api": "no",
        "status": "active_ChIP_rowwise_evidence",
        "purpose": "Build ChIP rowwise evidence table with stable source_row_id, target, role hints, stage/strain/condition, and public metadata fields.",
        "main_inputs": "ChIP master Excel",
        "main_outputs": "chip_rowwise_evidence.tsv; inventory/report",
    },
    {
        "step": "22",
        "assay": "ChIP",
        "script": "scripts/52_make_chip_ai_queue_and_control_policy.py",
        "production_name": "22_build_chip_queue_and_control_policy.py",
        "api": "no",
        "status": "active_ChIP_policy_queue",
        "purpose": "Create ChIP group/control policy and candidate queue; identify target/control structure before AI.",
        "main_inputs": "chip_rowwise_evidence.tsv",
        "main_outputs": "chip_group_control_policy.tsv; chip_ai_candidate_queue.tsv",
    },
    {
        "step": "23",
        "assay": "ChIP",
        "script": "scripts/53a_fetch_chip_sra_runinfo_publication_signals.py",
        "production_name": "23_fetch_chip_public_metadata.py",
        "api": "NCBI only; no OpenAI",
        "status": "active_ChIP_publication_resolution",
        "purpose": "Fetch ChIP SRA RunInfo/public metadata and extract publication signals.",
        "main_inputs": "chip_rowwise_evidence.tsv",
        "main_outputs": "ChIP public metadata and publication signal tables",
    },
    {
        "step": "24",
        "assay": "ChIP",
        "script": "scripts/53b_resolve_chip_publications_via_entrez_links.py",
        "production_name": "24_resolve_chip_publications.py",
        "api": "NCBI only; no OpenAI",
        "status": "active_ChIP_publication_resolution",
        "purpose": "Resolve BioProject -> PMID links using Entrez links/searches and confidence-scored suggestions.",
        "main_inputs": "ChIP public metadata publication signals",
        "main_outputs": "Entrez publication-resolution table",
    },
    {
        "step": "25",
        "assay": "ChIP",
        "script": "scripts/54_curate_chip_publication_backfills.py",
        "production_name": "25_curate_chip_publication_backfills.py",
        "api": "no",
        "status": "active_ChIP_publication_resolution",
        "purpose": "Apply deterministic/manual backfill decisions for missing/wrong PMID links without modifying master Excel.",
        "main_inputs": "Entrez publication-resolution table",
        "main_outputs": "curated BioProject->PMID backfill table; rowwise evidence with resolved publication",
    },
    {
        "step": "26",
        "assay": "ChIP",
        "script": "scripts/55_make_chip_resolved_publication_queue.py",
        "production_name": "26_make_chip_resolved_publication_queue.py",
        "api": "no",
        "status": "active_ChIP_publication_queue",
        "purpose": "Build resolved-publication ChIP queue and PMID download manifest.",
        "main_inputs": "curated backfill table; rowwise evidence with resolved publication",
        "main_outputs": "chip_resolved_publication_queue.tsv; chip_pmid_download_manifest.tsv",
    },
    {
        "step": "27",
        "assay": "ChIP",
        "script": "scripts/56_prepare_chip_pdf_download_manifest.py",
        "production_name": "27_prepare_chip_paper_downloads.py",
        "api": "no",
        "status": "active_ChIP_paper_preparation",
        "purpose": "Prepare ChIP PMID manifest for open-access PDF downloader.",
        "main_inputs": "chip_pmid_download_manifest.tsv",
        "main_outputs": "PDF download manifest for scripts/15_download_open_access_pdfs.py",
    },
    {
        "step": "28",
        "assay": "shared",
        "script": "scripts/15_download_open_access_pdfs.py",
        "production_name": "28_download_open_access_papers_optional.py",
        "api": "public web/NCBI/PMC; no OpenAI",
        "status": "active_shared_paper_download",
        "purpose": "Download open-access papers/PDFs where possible.",
        "main_inputs": "PMID download manifest",
        "main_outputs": "PDF/text cache and download status table",
    },
    {
        "step": "29",
        "assay": "ChIP",
        "script": "scripts/57_build_chip_paper_availability_and_ai_readiness.py",
        "production_name": "29_build_chip_ai_readiness.py",
        "api": "no",
        "status": "active_ChIP_ai_readiness",
        "purpose": "Merge resolved ChIP queue with PDF availability and define AI-ready packets.",
        "main_inputs": "resolved publication queue; PDF download status",
        "main_outputs": "chip_paper_availability_review.tsv; chip_ai_ready_queue.tsv",
    },
    {
        "step": "30",
        "assay": "ChIP",
        "script": "scripts/58_make_chip_ai_packets_from_ready_queue.py",
        "production_name": "30_build_chip_ai_packets.py",
        "api": "no",
        "status": "active_ChIP_packet_build",
        "purpose": "Build ChIP AI packet JSONs and rowwise sidecar TSVs using the shared packet format.",
        "main_inputs": "chip_ai_ready_queue.tsv; paper text/PDF; rowwise evidence",
        "main_outputs": "chip_ai_packet_queue.tsv; packet JSONs; packet rowwise TSVs",
    },
    {
        "step": "31",
        "assay": "ChIP",
        "script": "scripts/59_preflight_qc_chip_ai_packets.py",
        "production_name": "31_preflight_chip_ai_packets.py",
        "api": "no",
        "status": "active_ChIP_preflight_QC",
        "purpose": "Check packet JSON/sidecar/PDF existence, row counts, source_row_id uniqueness, and control flags before AI.",
        "main_inputs": "chip_ai_packet_queue.tsv",
        "main_outputs": "CHIP_AI_PACKET_PREFLIGHT_QC_REPORT.md; problem rows",
    },
    {
        "step": "32",
        "assay": "ChIP",
        "script": "scripts/59b_patch_chip_packet_control_roles.py",
        "production_name": "32_patch_chip_prelim_control_roles.py",
        "api": "no",
        "status": "active_ChIP_pre_ai_patch",
        "purpose": "Patch deterministic preliminary ChIP roles where metadata target labels conflict with background/input role evidence.",
        "main_inputs": "chip packet JSONs and packet rowwise tables",
        "main_outputs": "patched packet JSON/tables and audit",
    },
    {
        "step": "33",
        "assay": "ChIP",
        "script": "scripts/62_batch_run_chip_small_packets_production.py",
        "production_name": "33_run_chip_ai_small_packets_optional.py",
        "api": "OpenAI optional; dry-run by default",
        "status": "active_ChIP_ai_batch",
        "purpose": "Run AI on small ChIP packets; validate; optionally repair sample_map; summarize final status.",
        "main_inputs": "chip_ai_packet_queue.tsv",
        "main_outputs": "small-packet ChIP AI output directories and batch results",
    },
    {
        "step": "34",
        "assay": "ChIP",
        "script": "scripts/63_prepare_chip_chunked_packet.py",
        "production_name": "34_prepare_large_chip_packet_chunks.py",
        "api": "no",
        "status": "active_ChIP_chunking",
        "purpose": "Split one large ChIP packet into target-centered chunks without losing row coverage.",
        "main_inputs": "large parent packet JSON/table",
        "main_outputs": "chunk packet JSONs, chunk tables, chunk queue",
    },
    {
        "step": "35",
        "assay": "ChIP",
        "script": "scripts/64_merge_chip_chunk_outputs.py",
        "production_name": "35_merge_large_chip_packet_chunks.py",
        "api": "no",
        "status": "active_ChIP_chunk_merge",
        "purpose": "Merge validated chunk-level rowwise_suggestions into parent AI JSON; verify parent source_row_id coverage.",
        "main_inputs": "validated chunk AI JSONs; parent packet table",
        "main_outputs": "merged parent AI JSON and audit",
    },
    {
        "step": "36",
        "assay": "ChIP",
        "script": "scripts/60_validate_chip_ai_output.py",
        "production_name": "36_validate_chip_ai_output.py",
        "api": "no",
        "status": "active_ChIP_validation",
        "purpose": "Validate ChIP AI JSON: rowwise coverage, sample_map partitioning, role consistency, target-control readiness.",
        "main_inputs": "ChIP AI JSON; packet table",
        "main_outputs": "validation summary, validation issues, validation report",
    },
    {
        "step": "37",
        "assay": "ChIP",
        "script": "scripts/60b_rebuild_chip_sample_map_from_rowwise.py",
        "production_name": "37_repair_chip_sample_map.py",
        "api": "no",
        "status": "active_ChIP_safe_repair",
        "purpose": "Deterministically rebuild ChIP sample_map from rowwise_suggestions when rowwise coverage is exact.",
        "main_inputs": "AI JSON with complete rowwise_suggestions",
        "main_outputs": "samplemap_rebuilt AI JSON and audit",
    },
    {
        "step": "38",
        "assay": "ChIP",
        "script": "scripts/66_patch_chip_rowwise_roles_from_prelim.py",
        "production_name": "38_patch_chip_rowwise_roles.py",
        "api": "no",
        "status": "active_ChIP_safe_repair",
        "purpose": "Patch AI rowwise role labels from deterministic packet-table prelim roles when coverage is exact and mismatches are role-only.",
        "main_inputs": "AI JSON; packet table",
        "main_outputs": "role-patched AI JSON and patch audit",
    },
    {
        "step": "39",
        "assay": "ChIP",
        "script": "scripts/61_inventory_chip_ai_outputs.py",
        "production_name": "39_inventory_chip_ai_outputs.py",
        "api": "no",
        "status": "active_ChIP_inventory",
        "purpose": "Find latest raw/repaired ChIP AI JSON per packet; merge validation summaries; select active validated outputs.",
        "main_inputs": "ChIP AI output dirs; validation summaries",
        "main_outputs": "chip_ai_active_validated_outputs.tsv; inventory report",
    },
    {
        "step": "40",
        "assay": "ChIP",
        "script": "scripts/67_finalize_chip_ai_phase.py",
        "production_name": "40_finalize_chip_ai_phase.py",
        "api": "no",
        "status": "active_ChIP_final_QC",
        "purpose": "Finalize ChIP AI phase and export rowwise review and target-control map review tables.",
        "main_inputs": "active validated ChIP AI outputs",
        "main_outputs": "CHIP_AI_PHASE_COMPLETION_REPORT.md; chip_rowwise_review.tsv; chip_target_control_map_review.tsv",
    },
    {
        "step": "41",
        "assay": "ChIP",
        "script": "scripts/68e_finalize_chip_curator_excel_v5.py",
        "production_name": "41_build_chip_curator_workbook.py",
        "api": "no",
        "status": "active_ChIP_curator_excel",
        "purpose": "Build final ChIP curator Excel with paper summaries, triage, color coding, problem rows, target-control map, and rowwise review.",
        "main_inputs": "active ChIP inventory; final QC tables",
        "main_outputs": "latest ChIP curator Excel workbook",
    },
    {
        "step": "42",
        "assay": "ChIP",
        "script": "scripts/71_export_chip_curator_companion_files.py",
        "production_name": "42_export_chip_companion_files.py",
        "api": "no",
        "status": "active_ChIP_companion_exports",
        "purpose": "Export standalone ChIP TSV/MD companion files from the final workbook.",
        "main_inputs": "latest ChIP curator Excel workbook",
        "main_outputs": "outputs/06_CHIP_AI_ASSIST/22_curator_share_files",
    },
    {
        "step": "43",
        "assay": "ChIP",
        "script": "scripts/72c_final_qc_chip_study_summaries.py",
        "production_name": "43_clean_chip_study_summaries.py",
        "api": "no",
        "status": "active_ChIP_summary_cleanup",
        "purpose": "Final cleanup of ChIP study summaries: remove chunk/pipeline artifacts from curator-facing text.",
        "main_inputs": "chip_ai_study_summaries_clean.tsv/md",
        "main_outputs": "CHIP_AI_STUDY_SUMMARIES_CLEAN.md; FINAL_QC report",
    },

    # ------------------------------------------------------------------
    # Shared final bundle
    # ------------------------------------------------------------------
    {
        "step": "90",
        "assay": "shared",
        "script": "scripts/70_package_curator_share_bundle.py",
        "production_name": "90_package_curator_release.py",
        "api": "no",
        "status": "active_final_packaging",
        "purpose": "Package final RNA + ChIP curator-facing files into one folder and zip; excludes raw PDFs, .env, raw AI JSONs, and bulky intermediates.",
        "main_inputs": "latest RNA and ChIP curator outputs",
        "main_outputs": "outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>.zip",
    },
]


FINAL_OUTPUTS = [
    {
        "category": "final_bundle",
        "path": "outputs/99_CURATOR_SHARE_BUNDLES/LATEST_CURATOR_SHARE_BUNDLE.txt",
        "keep": "yes",
        "purpose": "Pointer to latest final curator release folder and zip.",
    },
    {
        "category": "final_bundle",
        "path": "outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>.zip",
        "keep": "yes",
        "purpose": "Single shareable package for Shalini/curators/postdocs.",
    },
    {
        "category": "RNA_final",
        "path": "outputs/04_AGENTIC_AI_ASSIST/curator_share/trusted_rna_<timestamp>/curator_review_<timestamp>.xlsx",
        "keep": "yes",
        "purpose": "Final RNA curator review workbook.",
    },
    {
        "category": "RNA_final",
        "path": "outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES_CLEAN.md",
        "keep": "yes",
        "purpose": "RNA whole-paper AI study summaries, cleaned.",
    },
    {
        "category": "RNA_final",
        "path": "outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md",
        "keep": "yes",
        "purpose": "RNA phase completion/QC report.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt",
        "keep": "yes",
        "purpose": "Pointer to latest final ChIP curator Excel workbook.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_v5_<timestamp>.xlsx",
        "keep": "yes",
        "purpose": "Final ChIP curator review workbook.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md",
        "keep": "yes",
        "purpose": "ChIP AI phase completion/QC report.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv",
        "keep": "yes",
        "purpose": "Final ChIP rowwise review table for curators/app/downstream.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv",
        "keep": "yes",
        "purpose": "Final ChIP target-control map review table.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_CLEAN.md",
        "keep": "yes",
        "purpose": "Final ChIP whole-paper AI study summaries, cleaned.",
    },
    {
        "category": "ChIP_final",
        "path": "outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md",
        "keep": "yes",
        "purpose": "Final ChIP summary cleanup QC.",
    },
]


def write_tsv(rows, path):
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_md():
    lines = []
    lines.append("# Active Workflow Map")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("This document defines the currently successful RNA/ChIP curator-assist pipeline before production refactoring.")
    lines.append("")
    lines.append("Important: this is a map of the current working workflow, not the final desired repository organization.")
    lines.append("")
    lines.append("## Core policy")
    lines.append("")
    lines.append("- API/AI execution is optional and must remain off by default.")
    lines.append("- NCBI/PubMed/SRA fetching is deterministic public metadata retrieval, not AI.")
    lines.append("- Deterministic validators and repairs are separate from AI.")
    lines.append("- AI suggestions are curator aids only; curator-final columns are authoritative.")
    lines.append("- Final products should be collected into one release folder and zip.")
    lines.append("")
    lines.append("## Active scripts by step")
    lines.append("")

    current_assay = None
    for r in ACTIVE:
        if r["assay"] != current_assay:
            current_assay = r["assay"]
            lines.append(f"### {current_assay}")
            lines.append("")
        lines.append(f"#### Step {r['step']}: `{r['production_name']}`")
        lines.append("")
        lines.append(f"- Current script: `{r['script']}`")
        lines.append(f"- API status: {r['api']}")
        lines.append(f"- Current status: {r['status']}")
        lines.append(f"- Purpose: {r['purpose']}")
        lines.append(f"- Main inputs: {r['main_inputs']}")
        lines.append(f"- Main outputs: {r['main_outputs']}")
        lines.append("")

    lines.append("## Final output map")
    lines.append("")
    for r in FINAL_OUTPUTS:
        lines.append(f"- `{r['path']}`")
        lines.append(f"  - category: {r['category']}")
        lines.append(f"  - keep: {r['keep']}")
        lines.append(f"  - purpose: {r['purpose']}")
    lines.append("")
    lines.append("## Refactoring implication")
    lines.append("")
    lines.append("The next production step is to create clean workflow wrappers using the production_name values above, while leaving legacy scripts in place.")
    lines.append("Only after wrapper parity tests pass should legacy scripts be moved into legacy_scripts/.")

    (DOCS / "ACTIVE_WORKFLOW_MAP.md").write_text("\n".join(lines))


def main():
    write_tsv(ACTIVE, OUT / "ACTIVE_SCRIPT_MAP.tsv")
    write_tsv(FINAL_OUTPUTS, OUT / "FINAL_OUTPUT_MAP.tsv")
    write_md()

    print("Wrote:")
    print(" -", OUT / "ACTIVE_SCRIPT_MAP.tsv")
    print(" -", OUT / "FINAL_OUTPUT_MAP.tsv")
    print(" -", DOCS / "ACTIVE_WORKFLOW_MAP.md")


if __name__ == "__main__":
    main()
