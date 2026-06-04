# Postdoc handoff: SRA paper curator production rerun

Generated: 2026-06-03T21:17:50

## Current milestone

RNA and ChIP AI-assisted curation have both reached structurally validated curator-review outputs.

ChIP status:
- 42/42 ChIP packets active validated PASS
- large AP2 landscape packet handled by target-centered chunking and merge
- final curator workbook generated

RNA status:
- trusted PMID-linked RNA AI phase completed earlier
- final curator workbook generated

## Core principle

The pipeline should be run in two modes:

1. Non-API / dry-run / validation-only mode
   - safe for setup, inspection, inventory, QC, and workbook rebuilding
   - should not require an API token

2. API execution mode
   - only when explicitly requested with flags such as --execute
   - requires .env / API token locally
   - API keys must never be committed

## Key curator-facing outputs

See:
- key_outputs_inventory.tsv

Most important:
- RNA curator Excel
- ChIP curator Excel
- ChIP target-control map TSV
- RNA and ChIP completion reports

## ChIP-specific production lessons

- ChIP controls/inputs/IgG are usually separate FASTQ/SRR rows.
- Target/IP rows may point to input/background rows through assigned_control columns.
- Shared input controls are expected and should be represented in Target_Control_Map, not by duplicating sample_map membership.
- sample_map must be a partition of source_row_id.
- If rowwise_suggestions cover all source_row_id exactly once, sample_map can be rebuilt deterministically.
- Missing rowwise_suggestions should not be invented.
- Large AP2 landscape packet must use target-centered chunking, then merge, then parent-level sample_map rebuild.

## Scripts added/updated recently

Important ChIP scripts:
- scripts/50_inspect_chip_master.py
- scripts/59b_patch_chip_packet_control_roles.py
- scripts/60_validate_chip_ai_output.py
- scripts/60b_rebuild_chip_sample_map_from_rowwise.py
- scripts/61_inventory_chip_ai_outputs.py
- scripts/62_batch_run_chip_small_packets_production.py
- scripts/63_prepare_chip_chunked_packet.py
- scripts/64_merge_chip_chunk_outputs.py
- scripts/65_audit_chip_repeats_and_chunk_failures.py
- scripts/66_patch_chip_rowwise_roles_from_prelim.py
- scripts/67_finalize_chip_ai_phase.py
- scripts/68_build_chip_curator_excel.py
- scripts/69_postdoc_handoff_inventory.py

## Before postdoc rerun

Recommended checks:
1. Confirm repo branch and clean git state.
2. Confirm input metadata files are present under data/.
3. Confirm .env exists only locally if API execution is needed.
4. Run inspection/preflight scripts before API execution.
5. Run API batches only with explicit --execute.
6. Validate after every batch.
7. Rebuild sample_map deterministically when rowwise coverage is exact.
8. Rebuild final Excel workbooks from validated active inventories.

## Do not commit

- .env or API tokens
- raw PDFs unless intentionally allowed
- bulky generated output folders
- temporary zip/context files
- cache files
