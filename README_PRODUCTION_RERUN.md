# SRA Paper Curator: Production Rerun Guide

This repository supports AI-assisted curation of public Plasmodium RNA-seq and ChIP/CUT&RUN/CUT&Tag metadata for downstream GRN construction.

The goal is not to replace human curation. The goal is to produce structured, validated curator-review workbooks that save curator time while preserving provenance, QC, and auditability.

Current validated milestone:

- RNA trusted PMID-linked AI curation completed.
- ChIP AI curation completed.
- ChIP: 42/42 packets active validated PASS.
- ChIP final curator workbook generated.
- RNA final curator workbook generated.

See:

- docs/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md
- docs/CHIP_AI_PHASE_COMPLETION_REPORT.md
- docs/HANDOFF_SUMMARY.md
- docs/POSTDOC_RERUN_RUNBOOK.md

## 0. Setup

Activate the conda environment:

    conda activate sra_paper_curator
    cd ~/work/Parasites/code/sra_paper_curator

Do not commit .env, API keys, raw PDFs, or bulky generated outputs.

The pipeline should support two modes:

1. Dry-run / validation-only mode
   - Does not require API access.

2. API execution mode
   - Requires a local .env file with API credentials.
   - Requires explicit --execute flags.

Example local .env:

    OPENAI_API_KEY=...

Load only when needed:

    set -a
    source .env
    set +a

## 1. Key input files

Expected main metadata files:

    data/rna_seq_metadata_2026-05-05_original.xlsx
    data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx

RNA and ChIP should be treated separately. ChIP requires special handling of target-IP rows, input/background/IgG rows, and target-control mappings.

## 2. RNA production checkpoint

The RNA phase has already produced:

    outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md
    outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_20260602_213023.xlsx

To regenerate the RNA final phase report/workbook from existing validated outputs:

    python scripts/49_finalize_trusted_rna_ai_phase.py

Expected RNA status from the current run:

- Trusted RNA packets inspected: 71
- PASS: 69
- NO_VALIDATION held by policy: 2
- Semantic HIGH/MEDIUM flags among PASS packets: 0

Held RNA packets are intentional policy-review cases, not pipeline failures.

## 3. ChIP production workflow

Inspect ChIP master:

    python scripts/50_inspect_chip_master.py

Build ChIP rowwise evidence and inventory:

    python scripts/51_build_chip_rowwise_evidence_and_inventory.py

Build ChIP AI queue and control policy:

    python scripts/52_make_chip_ai_queue_and_control_policy.py

Resolve publications / PMID backfills:

    python scripts/53a_fetch_chip_sra_runinfo_publication_signals.py
    python scripts/53b_resolve_chip_publications_via_entrez_links.py
    python scripts/54_curate_chip_publication_backfills.py
    python scripts/55_make_chip_resolved_publication_queue.py

Prepare paper/PDF readiness:

    python scripts/56_prepare_chip_pdf_download_manifest.py
    python scripts/57_build_chip_paper_availability_and_ai_readiness.py

Build ChIP AI packets:

    python scripts/58_make_chip_ai_packets_from_ready_queue.py

Preflight QC:

    python scripts/59_preflight_qc_chip_ai_packets.py
    python scripts/59b_patch_chip_packet_control_roles.py

Important ChIP rules:

- Input/background/IgG/control rows are usually separate FASTQ/SRR rows.
- Target-IP rows may point to controls through assigned_control1, assigned_control2, or background-related columns.
- Shared input controls are biologically expected.
- Shared controls should be represented in Target_Control_Map, not by duplicating sample_map membership.

## 4. ChIP AI execution

Dry-run small packets first:

    python scripts/62_batch_run_chip_small_packets_production.py --limit 10

Execute only after inspecting the dry run:

    set -a
    source .env
    set +a

    python scripts/62_batch_run_chip_small_packets_production.py --limit 10 --execute

The runner performs:

- AI run
- structural validation
- deterministic sample_map rebuild if rowwise coverage is exact
- revalidation
- inventory refresh

Repeat controlled batches until all non-chunked packets pass.

## 5. ChIP validation and repair principles

Validate one packet:

    python scripts/60_validate_chip_ai_output.py --packet-id PACKET_ID --ai-dir OUTPUT_DIR --queue QUEUE_TSV

Rebuild sample_map:

    python scripts/60b_rebuild_chip_sample_map_from_rowwise.py --packet-id PACKET_ID --ai-json AI_JSON --queue QUEUE_TSV

Safe repair rule:

- If rowwise_suggestions cover every source_row_id exactly once, sample_map can be rebuilt deterministically.
- If rowwise rows are missing, duplicated, or extra, do not invent rows. Rerun or inspect.
- If role mismatches are localized and deterministic metadata is clearly correct, use an audited role patch.

Role patch script:

    python scripts/66_patch_chip_rowwise_roles_from_prelim.py --packet-id PACKET_ID --ai-json AI_JSON --queue QUEUE_TSV

## 6. Large AP2 ChIP landscape packet

Large packet:

    PMID_35288749__BIOPROJECT_PRJNA765872

Use target-centered chunking:

    PARENT=PMID_35288749__BIOPROJECT_PRJNA765872

    python scripts/63_prepare_chip_chunked_packet.py --packet-id "$PARENT" --chunk-size 30

Inspect:

    cat outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets/${PARENT}/${PARENT}.CHIP_CHUNK_PREP_REPORT.md
    column -t -s $'\t' outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets/${PARENT}/${PARENT}.chunk_plan.tsv

Required:

- assigned rows = 144
- unique assigned rows = 144
- missing = 0
- extra = 0
- duplicates = 0
- each target appears in exactly one chunk

Run chunks:

    CHUNK_QUEUE=outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets/${PARENT}/${PARENT}.chunk_queue.tsv
    CHUNK_OUT=outputs/06_CHIP_AI_ASSIST/17_chip_ai_chunk_actual_targetcentered_size30

    set -a
    source .env
    set +a

    python scripts/62_batch_run_chip_small_packets_production.py \
      --queue "$CHUNK_QUEUE" \
      --inventory /tmp/nonexistent_chip_chunk_inventory_targetcentered_size30.tsv \
      --out-dir "$CHUNK_OUT" \
      --limit 20 \
      --execute

Merge chunks only after all chunks pass:

    python scripts/64_merge_chip_chunk_outputs.py \
      --parent-packet-id "$PARENT" \
      --chunk-queue "$CHUNK_QUEUE" \
      --chunk-out-dir "$CHUNK_OUT"

Rebuild parent sample_map:

    MERGED_JSON=$(find outputs/06_CHIP_AI_ASSIST/18_chip_ai_chunk_merged/${PARENT} -name "${PARENT}.ai_curation.chunk_merged.*.json" -type f | sort | tail -1)

    python scripts/60b_rebuild_chip_sample_map_from_rowwise.py \
      --packet-id "$PARENT" \
      --ai-json "$MERGED_JSON" \
      --queue outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv

Validate parent:

    REBUILT_JSON=$(find outputs/06_CHIP_AI_ASSIST/18_chip_ai_chunk_merged/${PARENT} -name "${PARENT}.ai_curation_samplemap_rebuilt.chunk_merged.*.json" -type f | sort | tail -1)

    python scripts/60_validate_chip_ai_output.py \
      --packet-id "$PARENT" \
      --ai-json "$REBUILT_JSON" \
      --queue outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv

Expected current result:

- expected_rows = 144
- rowwise_suggestions = 144
- sample_map_entries = 94
- validation_status = PASS
- n_fail = 0
- n_warn = 0

## 7. ChIP inventory, completion report, and Excel workbook

Refresh ChIP inventory:

    python scripts/61_inventory_chip_ai_outputs.py

Expected current result:

- packets in queue: 42
- active validated PASS packets: 42
- not_run: 0
- failed: 0

Finalize ChIP:

    python scripts/67_finalize_chip_ai_phase.py

Build curator Excel:

    python scripts/68_build_chip_curator_excel.py

Current final ChIP outputs:

    outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md
    outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv
    outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv
    outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_20260603_211441.xlsx

Current ChIP completion status:

- ChIP packets inspected: 42
- Active validated PASS packets: 42
- Repaired active outputs: 11
- Rowwise review rows: 733
- Target-control map rows: 490
- Peak-calling readiness yes: 30
- Peak-calling readiness partial: 11
- Peak-calling readiness no: 1

## 8. Postdoc handoff inventory

Generate handoff summary:

    python scripts/69_postdoc_handoff_inventory.py

Outputs:

    outputs/99_POSTDOC_HANDOFF/HANDOFF_SUMMARY.md
    outputs/99_POSTDOC_HANDOFF/POSTDOC_RERUN_RUNBOOK.md
    outputs/99_POSTDOC_HANDOFF/key_outputs_inventory.tsv
    outputs/99_POSTDOC_HANDOFF/directory_size_inventory.tsv
    outputs/99_POSTDOC_HANDOFF/git_status.txt

## 9. Git / version control policy

Commit:

- scripts/
- docs/
- README_PRODUCTION_RERUN.md
- .gitignore
- small reports/runbooks copied into docs/

Do not commit:

- .env
- API keys
- papers/
- outputs/
- large generated folders
- raw PDFs
- temporary zips
- local_scratch/

Recommended commit commands:

    git add README_PRODUCTION_RERUN.md
    git add docs/
    git add scripts/
    git add .gitignore

    git status
    git diff --cached --stat

    git commit -m "Add production rerun guide and ChIP AI curation pipeline"

Push only after checking that no secret or bulky file is staged.

## 10. Curator-facing interpretation

Curators should use final Excel workbooks, not raw AI JSONs.

For ChIP, the most important sheets are:

- README
- Study_Review
- Target_Control_Map_Review
- Problem_Rows
- Rowwise_Review
- Sample_Map_Review
- Packet_Status

Recommended curator workflow:

1. Start with README.
2. Review packet/study-level status in Study_Review.
3. Review Problem_Rows.
4. For ChIP, prioritize Target_Control_Map_Review.
5. Spot-check Rowwise_Review.
6. Use curator columns for corrections/comments.
7. Treat AI fields as suggestions, not authoritative final annotations.
