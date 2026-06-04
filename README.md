# SRA Paper Curator

Curator-assist pipeline for converting public SRA/GEO sequencing metadata and paper context into reviewable, analysis-ready RNA-seq and ChIP-seq curator workbooks.

The current use case is Plasmodium public-data curation for downstream gene-regulatory-network analysis. The pipeline helps identify paper-linked BioProjects, build paper/BioProject packets, optionally run AI-assisted paper/metadata review, validate outputs deterministically, and package curator-facing Excel/Markdown/TSV deliverables.

## Current status

This repository currently contains a working RNA and ChIP curator-assist pipeline plus a production wrapper layer.

The working legacy scripts are still in `scripts/`.

The production-facing wrapper and maps are in:

- `workflows/`
- `configs/`
- `docs/`

The clean final curator-facing release is generated in:

- `results/final_curator_release/`
- `results/final_curator_release_<timestamp>.zip`

Generated outputs are intentionally ignored by Git.

## Core safety rules

1. AI/API execution is off by default.
2. NCBI/PubMed/SRA public metadata fetching is deterministic public-data retrieval, not AI.
3. Deterministic validation and repair are separate from AI.
4. AI outputs are curator aids only.
5. Curator-final columns in Excel files are authoritative.
6. Final release folders exclude raw PDFs, raw AI JSONs, `.env`, API keys, and bulky intermediates.

## Repository layout

- `scripts/`  
  Current working legacy scripts. These are being wrapped and gradually refactored.

- `workflows/`  
  Production-facing workflow map and safe wrapper runner.

- `configs/`  
  Default configuration. AI is disabled by default.

- `docs/`  
  Workflow maps, reorganization plan, and technical documentation.

- `results/final_curator_release/`  
  Clean final curator-facing release folder generated from validated outputs.

- `outputs/`  
  Intermediate/generated working outputs. Ignored by Git.

## Workflow concept

The pipeline follows this logic:

1. Prepare rowwise metadata evidence.
2. Resolve PMID/BioProject/paper links.
3. Locate or download paper/PDF context.
4. Build paper/BioProject packets.
5. Optionally run AI on packet text and metadata.
6. Validate AI output deterministically.
7. Apply safe deterministic repairs only when row coverage is exact.
8. Build curator-facing Excel/Markdown/TSV files.
9. Package a clean final release.
10. QC the release.

## What is a packet?

A packet is the core review unit:

    one PMID + one BioProject

A packet contains:

- rowwise SRA/BioSample metadata evidence
- paper context
- AI curation output, if AI was run
- deterministic validation/QC results

For RNA, the packet asks:

- What are the biological sample groups?
- What are the major comparisons?
- Is the metadata sufficient for count/DE-ready downstream analysis?

For ChIP, the packet also asks:

- Which rows are target IP?
- Which rows are input, IgG, mock, or background controls?
- Which target rows map to which control rows?
- Is the packet peak-calling ready?

## Clean final release

To create the clean final release folder:

    python scripts/02_create_clean_final_release.py

To QC the final release:

    python scripts/03_qc_final_release.py

Expected current release QC:

- RNA study summaries: 69
- ChIP study summaries: 42
- ChIP rowwise review rows: 733
- ChIP target-control map rows: 490
- no raw JSON/PDF/env/key-like files
- zip opens cleanly

The latest release pointer is:

    results/LATEST_FINAL_CURATOR_RELEASE.txt

## Workflow wrapper usage

List all workflow steps:

    python workflows/run_workflow_step.py --list

Show a step without running it:

    python workflows/run_workflow_step.py --step 90

Dry-run is the default.

Run a non-AI step:

    python workflows/run_workflow_step.py --step 90 --execute

Run an AI-capable step only when explicitly intended:

    AGENTIC_AI_ENABLE_API=1 python workflows/run_workflow_step.py --step 33 --execute --execute-ai

The wrapper refuses to run AI-capable steps unless both `--execute-ai` and `AGENTIC_AI_ENABLE_API=1` are present.

## Important current workflow documents

- `docs/ACTIVE_WORKFLOW_MAP.md`  
  Current successful RNA/ChIP script sequence, grouped by function.

- `docs/PRODUCTION_REORG_PLAN.md`  
  Reorganization plan toward publication-quality GitHub structure.

- `workflows/steps.tsv`  
  Machine-readable workflow step map.

## Curator-facing outputs

Final RNA files include:

- `RNA/RNA_curator_review.xlsx`
- `RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md`
- `RNA/rna_ai_study_summaries_clean.tsv`

Final ChIP files include:

- `ChIP/ChIP_curator_review.xlsx`
- `ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md`
- `ChIP/chip_ai_study_summaries_clean.tsv`
- `ChIP/chip_rowwise_review.tsv`
- `ChIP/chip_target_control_map_review.tsv`

QC reports are in:

- `QC/`

## ChIP-specific review focus

Curators should prioritize:

1. `Curator_Triage` sheet in the Excel workbook.
2. Paper/study summaries.
3. ChIP target-control/background mapping.
4. Low-confidence or HIGH_REVIEW rows.
5. Ambiguous stage/condition/strain labels.
6. Large AP2 packets and shared-input control logic.

## Development roadmap

The current production-reorg branch has begun the cleanup process.

Completed:

- frozen working pipeline state
- active script map
- safe workflow wrapper
- clean final release builder
- final release QC

Next planned steps:

1. Add golden-output tests.
2. Move shared logic into `src/sra_paper_curator/`.
3. Replace numbered legacy scripts with stable workflow names.
4. Move old scripts into `legacy_scripts/` only after wrapper parity tests pass.
5. Add full developer and curator guides.
6. Create publication-quality GitHub documentation.

## Trust model

This is a curator-assist pipeline, not an autonomous truth engine.

The AI can summarize papers and suggest sample labels, but deterministic validators enforce structural correctness:

- every source row must be covered
- no missing or duplicate source rows
- sample maps must partition rows correctly
- ChIP target/control relationships are surfaced for review
- repairs are allowed only when source-row coverage is exact
- repairs write audit trails

Final biological correctness still requires curator review.

## Fresh clone versus artifact-backed checks

A fresh Git clone does not contain generated `outputs/` or `results/` artifacts.

For a fresh clone smoke check, run:

    python scripts/05_run_all_checks.py

This verifies the code, workflow wrapper, and AI safety guard.

For the full artifact-backed production check on a machine that already has generated outputs, run:

    python scripts/05_run_all_checks.py --with-artifacts
