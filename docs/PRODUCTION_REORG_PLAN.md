# Production Reorganization Plan

Goal: convert the current working RNA/ChIP curator-assist pipeline into a publication-quality, reproducible, GitHub-ready workflow.

## Core principles

1. Do not break the working pipeline.
2. Preserve legacy scripts until clean wrappers and parity checks exist.
3. API/AI execution must be off by default.
4. Final curator-facing products must live in one intuitive release folder.
5. RNA and ChIP should share common infrastructure where possible.
6. ChIP-specific logic must remain explicit: target IP, input/IgG/background, target-control mapping, peak-calling readiness.
7. Every deterministic repair must be audited.
8. Curator-facing outputs must be separated from technical intermediate outputs.

## Target workflow sequence

00_preflight
- Check environment, inputs, paths, and API state.
- No API calls.

01_prepare_inputs
- Read input Excel metadata.
- Standardize columns.
- Create rowwise evidence tables.

02_resolve_publications
- Resolve PMID/BioProject links.
- Use provided metadata, SRA/NCBI signals, Entrez links, paper titles, and backfill rules.
- Produce auditable publication-resolution tables.

03_prepare_papers
- Locate/download papers where possible.
- Create paper availability/readiness tables.

04_build_packets
- Build PMID + BioProject packets.
- Packet = metadata rows + paper context + source evidence.

05_run_ai_optional
- Dry-run by default.
- Requires explicit --execute-ai.
- Produces AI JSON with study_summary, sample_map, rowwise_suggestions, readiness, warnings.

06_validate_and_repair
- Deterministic validation.
- Row coverage.
- Missing/duplicate/extra rows.
- Sample-map validity.
- ChIP target-control mapping.
- Safe deterministic repair only when source-row coverage is exact.

07_finalize_curator_outputs
- Build curator Excel files.
- Build clean study summaries.
- Build review-flag summaries.
- Build final TSVs for app/downstream use.

08_package_release
- Copy only final curator-facing products into one release folder.
- Zip release folder.
- No raw PDFs, API keys, raw AI JSONs, or bulky intermediates.

## Target repository structure

sra_paper_curator/
├── README.md
├── pyproject.toml
├── .env.example
├── configs/
├── src/sra_paper_curator/
├── workflows/
├── legacy_scripts/
├── tests/
├── docs/
└── results/final_curator_release/

## Immediate reorganization phases

Phase 1: inventory and audit current repo.
Phase 2: define active vs superseded scripts.
Phase 3: create clean workflow wrappers around current scripts.
Phase 4: create golden-output tests.
Phase 5: move reusable logic into src/.
Phase 6: move legacy scripts aside only after parity checks pass.
Phase 7: clean final output folders and docs.
