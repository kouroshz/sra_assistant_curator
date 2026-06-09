# Clean Rerun Handoff: SRA/RNA/ChIP Curator Workflow

## Purpose

This document is for reproducing the SRA/RNA/ChIP curator workflow from a clean clone, starting only from the two required input Excel files. It is intended for a postdoc who can both reproduce the run and debug issues if they arise.

The goal is to test whether a new user can clone the repository, create a clean environment, run deterministic RNA and ChIP preparation, optionally run AI-assisted packet review, finalize curator-facing RNA and ChIP outputs, package the final release, run QC, and report/debug any failures clearly.

This is both a software reproducibility test and a scientific curation test. The workflow supports annotation of public Plasmodium RNA-seq and ChIP-seq datasets for downstream biological use, including RNA comparator selection and ChIP target/background/control matching.

Human curator review remains authoritative. AI outputs are suggestions and must pass deterministic validation/QC before they enter curator-facing outputs.

---

## Conceptual Overview

The original Excel files are starting manifests, not final authority.

```text
Input Excel manifests
→ SRA RunInfo / BioSample / GEO / publication metadata caches
→ deterministic evidence extraction and rules
→ paper / PMID / BioProject packet construction
→ optional AI paper-design interpretation
→ validation and QC
→ curator-facing Excel/TSV/Markdown outputs
→ human curator review
```

The cache layer provides audit evidence such as Run accession, BioSample accession, BioProject, LibraryName, SampleName, ScientificName, BioSample title, BioSample attributes, strain/stage/condition/treatment hints, and ChIP target/input/IgG/control hints.

Deterministic rules are reproducible non-AI rules, regexes, dictionaries, and matching logic. For example: classify ChIP-Seq, detect input/IgG/background, extract timepoints such as `10hr` or `T10`, and suggest ChIP target-control pairings when BioProject/stage/condition match.

AI is used only after deterministic packet building. For RNA, AI interprets study goal, assay class, contrast/time-course structure, possible comparators, and curator warnings. For ChIP, AI interprets target IPs, input/IgG/background controls, target-control relationships, peak-calling readiness, and curator warnings. AI should not invent PMIDs, invent missing controls, or silently override curator judgment.

---

## Required Inputs

Place these files in `data/`:

```text
data/rna_seq_metadata_2026-05-05_original.xlsx
data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

No PDFs are required to start. The workflow can attempt to download open-access PDFs later.

---

## Clean Setup

```bash
cd /Users/<USER>/work/Playground
git clone https://github.com/kouroshz/sra_assistant_curator.git sra_assistant_curator_clean_rerun
cd sra_assistant_curator_clean_rerun
```

Create a local conda environment inside the clone:

```bash
conda env create --prefix "$PWD/env_clean_test" --file environment.yml
conda activate "$PWD/env_clean_test"
which python
python --version
python -c "import pandas, openpyxl; print('basic imports ok')"
```

Copy inputs:

```bash
mkdir -p data
cp /path/to/rna_seq_metadata_2026-05-05_original.xlsx data/
cp /path/to/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx data/
ls -lh data/*.xlsx
```

Create and load `.env`:

```bash
cp .env.example .env
# edit .env and set at least NCBI_EMAIL
# for AI runs also set OPENAI_API_KEY and AGENTIC_AI_ENABLE_API=1

set -a
source .env
set +a
```

---

## Initial Smoke Check

```bash
python workflows/run_recipe.py check
```

In a fresh clone without input workbooks, it may report `REVIEW` for missing input files and missing caches. That is expected until the two Excel files are copied into `data/`.

---

## Deterministic Preparation

```bash
python workflows/run_recipe.py rna-prep --execute
python workflows/run_recipe.py chip-prep --execute
```

RNA prep builds rowwise evidence, paper packets, publication-resolution tables, and the trusted AI queue.

ChIP prep inspects the ChIP workbook, builds ChIP rowwise evidence, resolves publications, downloads available papers, builds ChIP AI packets, runs preflight QC, and patches preliminary control roles.

The first clean NCBI metadata fetch can take a long time. Cached reruns should be much faster.

---

## Important Intermediate Outputs

RNA:

```text
outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv
outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv
outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv
outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv
outputs/02_QC_SUMMARIES/publication_resolution_by_packet.tsv
outputs/02_QC_SUMMARIES/trusted_pmid_packets.tsv
outputs/02_QC_SUMMARIES/held_or_unresolved_pmid_packets.tsv
```

ChIP:

```text
outputs/06_CHIP_AI_ASSIST/07_papers/chip_pdf_download_status.tsv
outputs/06_CHIP_AI_ASSIST/07_papers/chip_pmids_still_needing_manual_pdf_download.tsv
outputs/06_CHIP_AI_ASSIST/08_paper_availability/chip_ai_ready_with_pdf_queue.tsv
outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv
outputs/06_CHIP_AI_ASSIST/10_preflight_qc/chip_ai_packet_preflight_qc.tsv
```

Downloaded PDFs live in:

```text
papers/
```

---

## AI Runs

AI is guarded. It should not run unless all are true: `--execute`, `--execute-ai`, `AGENTIC_AI_ENABLE_API=1`, and `OPENAI_API_KEY` is set.

Pilot AI runs:

```bash
python workflows/run_recipe.py rna-ai --execute --execute-ai
python workflows/run_recipe.py chip-ai --execute --execute-ai
```

Full AI runs:

```bash
python workflows/run_recipe.py rna-ai-full --execute --execute-ai
python workflows/run_recipe.py chip-ai-full --execute --execute-ai
```

The full recipes should pass `--limit 0` to the underlying batch runners. In dry-run mode, confirm the displayed command communicates that this is a full run.

After AI runs, inspect inventories:

```bash
python scripts/43_deep_qc_ai_outputs.py
python scripts/61_inventory_chip_ai_outputs.py
```

---

## Finalization and Packaging

```bash
python workflows/run_recipe.py rna-finalize --execute
python workflows/run_recipe.py chip-finalize --execute
python workflows/run_recipe.py package --execute
python workflows/run_recipe.py show-outputs
```

Expected final release location:

```text
results/final_curator_release
results/final_curator_release_<timestamp>.zip
```

---

## Final QC

```bash
python scripts/05_run_all_checks.py --with-artifacts
```

Final QC can report:

```text
PASS     full release matches expected golden counts
PARTIAL  structurally valid curator-facing release, but incomplete coverage
FAIL     structural or required-file problem
```

Force strict full-release counts:

```bash
python scripts/03_qc_final_release.py --mode full
```

Allow partial structural QC:

```bash
python scripts/03_qc_final_release.py --mode partial
```

`show-outputs` should reflect the QC verdict, not only file existence.

---

## Known Clean-Test Reference Outcomes

The June 2026 clean test produced:

RNA:

```text
6,332 rowwise RNA rows
164 RNA paper packets
71 trusted PMID packets
93 held/unresolved packets
```

A pilot RNA AI run processed 10 packets and all 10 validated PASS. Many trusted RNA packets remained `NO_VALIDATION` because the default RNA AI recipe is a pilot/limited run.

ChIP:

```text
77 ChIP groups considered
65 had some PMID candidate
48 accepted/validated groups
4 manual-review groups
24 unresolved groups
1 rejected bad match
41 unique PMIDs for download
30 PDFs downloaded
11 PDFs still missing/manual-needed
```

ChIP AI built 37 packets. A full ChIP AI run produced 36 validated PASS packets and one biologically meaningful role/function ambiguity.

Important ambiguity:

```text
PMID_27555062__BIOPROJECT_PRJNA319006
```

The rows were H3core ChIP IP samples. Deterministic metadata labeled them as target IPs because physically they are antibody ChIP IP samples. AI labeled them as control/background because analytically H3core is used as a normalization/reference background for PfH3.3. Both interpretations are meaningful.

Preferred representation:

```text
physical_sample_role = target_ip
analysis_function = matched_background / reference_chromatin_control
curator_flag = role_function_conflict
```

This should not be treated as a mysterious hard failure.

---

## Debugging Guide

### Entrez / NCBI failures

If ChIP publication resolution reports `IncompleteRead`, `RemoteDisconnected`, `HTTP Error 500`, or malformed JSON, the workflow should retry and continue. Route-level failures should reduce evidence for that route, not kill the workflow.

Verify `.env` includes:

```text
NCBI_EMAIL=...
```

### AI row coverage failure

If validation reports:

```text
rowwise_missing_source_row_id
rowwise_duplicate_source_row_id
rowwise_count_mismatch
```

this is usually a retryable structural LLM-output problem. Rerun the specific packet and validate again.

### ChIP sample-map repair

If sample-map validation fails but rowwise suggestions are complete:

```bash
python scripts/60b_rebuild_chip_sample_map_from_rowwise.py   --packet-id PACKET_ID   --ai-dir outputs/06_CHIP_AI_ASSIST/15_chip_ai_batch_small_actual   --queue outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv
```

Then validate again.

### Biological role disagreement

If AI and deterministic metadata disagree on ChIP role, inspect carefully before forcing a patch.

Example:

```text
expected_prelim=target_ip
ai=control_sample
```

This may be a real biological role/function distinction, especially for antibody IPs used as normalization/background controls. Do not silently repair these. They should be visible to curators.

---

## What to Report Back

After the rerun, please report:

1. Git commit hash used.
2. Whether the conda environment was created cleanly.
3. Whether `check` passed.
4. RNA prep summary: rowwise rows, paper packets, trusted PMIDs, held/unresolved.
5. ChIP prep summary: groups considered, accepted/manual/unresolved/rejected, unique PMIDs, PDFs downloaded/missing, AI-ready packets.
6. AI run mode: pilot or full; RNA and ChIP packets attempted/PASS/failed/not-run.
7. Finalization status: RNA workbook, ChIP workbook, package.
8. Final QC verdict: PASS, PARTIAL, or FAIL.
9. Failed packets and exact validation issue rows.
10. Manual scientific judgment needed, especially ChIP target/background/control ambiguity.

---

## Minimum Success Criteria

A successful clean rerun should at least produce:

```text
results/final_curator_release/
results/final_curator_release_<timestamp>.zip
```

and `show-outputs` should correctly report release status.

For a pilot run, `PARTIAL` is acceptable if the release is structurally valid and clearly labeled partial.

For a full production run, `PASS` should be required.

---

## Recommended First Rerun Mode

Start with deterministic prep plus pilot AI:

```bash
python workflows/run_recipe.py check
python workflows/run_recipe.py rna-prep --execute
python workflows/run_recipe.py chip-prep --execute
python workflows/run_recipe.py rna-ai --execute --execute-ai
python workflows/run_recipe.py chip-ai --execute --execute-ai
python workflows/run_recipe.py rna-finalize --execute
python workflows/run_recipe.py chip-finalize --execute
python workflows/run_recipe.py package --execute
python scripts/05_run_all_checks.py --with-artifacts
python workflows/run_recipe.py show-outputs
```

Then, if pilot mode works, run full AI:

```bash
python workflows/run_recipe.py rna-ai-full --execute --execute-ai
python workflows/run_recipe.py chip-ai-full --execute --execute-ai
python workflows/run_recipe.py rna-finalize --execute
python workflows/run_recipe.py chip-finalize --execute
python workflows/run_recipe.py package --execute
python scripts/05_run_all_checks.py --with-artifacts
python workflows/run_recipe.py show-outputs
```
