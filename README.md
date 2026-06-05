# SRA Paper Curator

Curator-assist workflow for converting public SRA/GEO sequencing metadata and paper context into reviewable RNA-seq and ChIP-seq curation workbooks.

The current motivating use case is public Plasmodium RNA-seq and ChIP-seq metadata curation for downstream gene-regulatory-network analysis.

Core principle:

AI may assist paper and metadata interpretation, but deterministic validation, audit trails, and human curator review remain authoritative.

Required local input workbooks for a fresh rerun:

    data/rna_seq_metadata_2026-05-05_original.xlsx
    data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx

Generated outputs, caches, downloaded papers, AI JSONs, and curator Excel files are not committed.

Detailed local input and rerun instructions:

- `docs/LOCAL_INPUTS.md`
- `docs/RERUN_VALIDATION.md`

---

## Current status

This repository contains a working RNA/ChIP curator-assist workflow with:

- production-facing workflow wrappers
- deterministic public metadata enrichment
- optional AI-assisted paper/metadata review
- deterministic AI-output validation
- curator-facing Excel, Markdown, and TSV release generation
- release QC
- golden-output regression checks
- fresh-clone smoke checks
- archived legacy/prototype scripts

Main production checkpoint:

    v1.3-main-merged-artifact-pass

At this checkpoint:

- fresh-clone smoke checks pass
- local artifact-backed production checks pass
- AI/API execution is off by default
- generated outputs are excluded from Git
- legacy/prototype scripts are archived under legacy_scripts/

---

## Installation

Create the conda environment:

    conda env create -f environment.yml
    conda activate sra_paper_curator

The environment is defined in environment.yml and currently includes:

    python=3.11
    pandas
    openpyxl
    xlsxwriter
    numpy
    pyyaml
    tqdm
    rich
    pydantic
    openai
    python-dotenv
    pypdf

The OpenAI-related packages are installed for optional AI-assisted steps. AI/API calls are not made by default.

---

## Fresh-clone smoke test

A fresh clone does not contain generated outputs/ or results/ artifacts.

Run:

    python scripts/05_run_all_checks.py
    python scripts/04_pipeline_readiness_report.py

Expected result:

    PASS: repo smoke checks passed.

In a fresh clone, artifact-backed checks are skipped because generated output files are absent. This is expected.

The smoke test verifies that:

- production Python files compile
- the workflow wrapper is available
- non-AI workflow steps default to dry-run
- AI-capable workflow steps refuse execution unless explicitly enabled

---

## Artifact-backed production validation

On a working machine that already contains generated outputs/ artifacts, run:

    python scripts/05_run_all_checks.py --with-artifacts
    python scripts/04_pipeline_readiness_report.py

This performs full production validation:

- compiles production Python files
- rebuilds the clean final curator release
- runs final release QC
- runs golden-output regression tests
- confirms workflow dry-run safety
- confirms AI execution guard behavior

Expected result:

    PASS: all production checks passed.

---

## Repository layout

    .
    README.md
    environment.yml
    pyproject.toml
    configs/
    workflows/
    scripts/
    src/sra_paper_curator/
    tests/
    docs/
    legacy_scripts/
    outputs/     generated, ignored by Git
    results/     generated, ignored by Git

Important files:

    workflows/steps.tsv
    workflows/run_workflow_step.py
    scripts/02_create_clean_final_release.py
    scripts/03_qc_final_release.py
    scripts/04_pipeline_readiness_report.py
    scripts/05_run_all_checks.py
    docs/ACTIVE_WORKFLOW_MAP.md
    docs/CURATOR_GUIDE.md
    docs/DEVELOPER_GUIDE.md
    docs/GOLDEN_OUTPUTS.md
    docs/LOCAL_INPUTS.md
    docs/RERUN_VALIDATION.md
    docs/PIPELINE_READINESS_REPORT.md

---

## Workflow overview

The workflow has five conceptual layers.

### 1. Input and rowwise evidence

The pipeline starts from RNA and ChIP metadata workbooks, then creates rowwise evidence tables with stable IDs and public metadata evidence from SRA/BioSample.

Core actions:

- assign stable row IDs
- fetch/cache public SRA RunInfo and BioSample metadata
- build rowwise evidence tables
- preserve source-row provenance

### 2. Publication and packet construction

Rows are grouped into paper/BioProject review units.

Core actions:

- resolve PMID/BioProject links
- write trusted and held publication packet tables
- build deterministic paper-packet priority queue
- identify paper availability
- build paper/BioProject packets
- prepare packet-level metadata and sidecar rowwise evidence

Key generated products:

    outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv
    outputs/02_QC_SUMMARIES/held_or_unresolved_pmid_packets.tsv
    outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_ai_priority_queue.tsv

`papers/` is a local working directory and is not committed. Paper packets can be built before PDFs are available, but real AI-assisted curation should only be run after papers/PDF text are downloaded or otherwise prepared; otherwise the queue and downstream checks should report missing local paper context.

### 3. Optional AI-assisted curation

AI-assisted steps are optional and disabled by default.

Core actions:

- read packet metadata and paper text
- suggest biological sample labels
- summarize paper/study context
- identify RNA sample groups or ChIP target/control relationships

AI output is never treated as final truth.

### 4. Deterministic validation and repair

Validation is deterministic and separate from AI.

Core checks include:

- every source row is covered exactly once
- no duplicate or missing source rows
- sample maps reference valid rows
- ChIP target/control relationships are surfaced for review
- repairs are applied only when source-row coverage is exact
- repair audit trails are written

### 5. Curator-facing release generation

Validated outputs are converted into human-facing deliverables:

- Excel review workbooks
- paper/study summary Markdown files
- companion TSV tables
- QC reports
- final release manifest and zip

---

## Workflow wrapper usage

Workflow steps are listed in:

    workflows/steps.tsv

List all workflow steps:

    python workflows/run_workflow_step.py --list

Show one step without running it:

    python workflows/run_workflow_step.py --step 90

Dry-run a deterministic range:

    python workflows/run_workflow_step.py --continue-from 00 --through 05

Execute a deterministic non-AI range:

    python workflows/run_workflow_step.py --continue-from 00 --through 05 --execute

Run a non-AI step:

    python workflows/run_workflow_step.py --step 90 --execute

Run an AI-capable step:

    AGENTIC_AI_ENABLE_API=1 python workflows/run_workflow_step.py --step 33 --execute --execute-ai

The wrapper refuses AI-capable execution unless both are present:

    --execute-ai
    AGENTIC_AI_ENABLE_API=1

Batch AI runners also require `OPENAI_API_KEY` when `--execute` is used. The key is never printed.

---

## Optional API configuration

Deterministic reruns do not need OpenAI API access.

Real AI-assisted steps require either exported environment variables or a local `.env` file that is never committed:

    cp .env.example .env

Then edit `.env` locally:

    OPENAI_API_KEY=your-local-key
    OPENAI_MODEL=optional-model
    OPENAI_SMALL_MODEL=optional-small-model

Keep API execution disabled until you intentionally run an AI step:

    AGENTIC_AI_ENABLE_API=0

Set `AGENTIC_AI_ENABLE_API=1` only for deliberate API-enabled runs. Never commit `.env`.

---

## AI/API safety model

Default behavior is safe:

- no OpenAI/API calls are made by default
- workflow steps are dry-run by default
- AI-capable steps require explicit opt-in
- .env and API keys are excluded from Git
- final release packaging excludes raw AI JSON, raw PDFs, .env files, keys, and bulky intermediates

This makes the repository safe for fresh clones, reviewer inspection, and postdoc handoff.

---

## Final curator release

Create the clean final release:

    python scripts/02_create_clean_final_release.py

Run release QC:

    python scripts/03_qc_final_release.py

Generated release folder:

    results/final_curator_release/

Latest release pointer:

    results/LATEST_FINAL_CURATOR_RELEASE.txt

Generated release artifacts are ignored by Git.

---

## Curator-facing outputs

Final RNA files include:

    RNA/RNA_curator_review.xlsx
    RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md
    RNA/rna_ai_study_summaries_clean.tsv

Final ChIP files include:

    ChIP/ChIP_curator_review.xlsx
    ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md
    ChIP/chip_ai_study_summaries_clean.tsv
    ChIP/chip_rowwise_review.tsv
    ChIP/chip_target_control_map_review.tsv

Curators should start with:

    docs/CURATOR_GUIDE.md
    results/final_curator_release/README.md

---

## Golden-output checks

Golden-output regression checks are defined in:

    tests/test_golden_outputs.py
    docs/GOLDEN_OUTPUTS.md

Current expected release counts:

    RNA study summaries: 69
    ChIP study summaries: 42
    ChIP rowwise review rows: 733
    ChIP target-control map rows: 490

These are regression checks for the current known-good output state. They are not biological claims.

---

## What is a packet?

A packet is the core review unit:

    one PMID plus one BioProject

A packet contains:

- rowwise SRA/BioSample metadata evidence
- paper context
- AI curation output, if AI was run
- deterministic validation/QC results

For RNA, a packet asks:

- What are the biological sample groups?
- What are the major comparisons?
- Are stage, strain, treatment, timepoint, and condition labels clear?
- Is the metadata sufficient for count/DE-ready downstream analysis?

For ChIP, a packet also asks:

- Which rows are target IP?
- Which rows are input, IgG, mock, untagged, or background controls?
- Which target rows map to which control rows?
- Is the packet peak-calling ready?

---

## Trust and review model

This is a curator-assist pipeline, not an autonomous truth engine.

AI can:

- summarize papers
- suggest sample labels
- suggest ChIP target/control relationships
- flag ambiguous metadata

AI cannot:

- make final biological decisions
- bypass deterministic validation
- overwrite curator-final decisions
- run unless explicitly enabled

Deterministic validators enforce structural correctness:

- every source row must be covered
- no missing or duplicate source rows
- sample maps must partition rows correctly
- ChIP target/control relationships are surfaced for review
- repairs are allowed only under explicit safety rules
- repairs write audit trails

Final biological correctness still requires curator review.

---

## Data and generated artifacts

This repository does not commit generated working outputs.

Ignored/generated paths include:

    outputs/
    results/
    local_scratch/
    .env
    raw PDFs
    raw AI JSON files
    API keys

This keeps GitHub lightweight and safe.

To reproduce artifact-backed checks, use a working checkout that contains the generated outputs/ directory or rerun the workflow to regenerate it.

---

## Documentation map

Recommended starting points:

    README.md
    docs/REVIEWER_GUIDE.md
    docs/CURATOR_GUIDE.md
    docs/DEVELOPER_GUIDE.md
    docs/ACTIVE_WORKFLOW_MAP.md
    docs/GOLDEN_OUTPUTS.md
    docs/PIPELINE_READINESS_REPORT.md
    workflows/README.md

---

## Reviewer quickstart

    conda env create -f environment.yml
    conda activate sra_paper_curator
    python scripts/05_run_all_checks.py
    python scripts/04_pipeline_readiness_report.py

This should pass in a fresh clone and explain that artifact-backed checks are skipped unless generated outputs are present.

For full artifact-backed validation on the production machine:

    python scripts/05_run_all_checks.py --with-artifacts

---

## Known limitations

The current repository is production-organized and validated against existing generated artifacts, but a full controlled end-to-end rerun from raw/local inputs remains the next validation phase.

The next phase should test:

- deterministic rerun without AI
- packet regeneration
- release regeneration
- comparison to current golden outputs
- optional AI execution on a small controlled subset

---

## License

License/status is currently internal research prototype; formal license TBD.
