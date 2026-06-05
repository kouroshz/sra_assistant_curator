# Local Inputs

This repository intentionally does not commit raw curator input workbooks, generated outputs, downloaded papers, metadata caches, AI JSONs, or final curator Excel files.

## Required Workbooks

Place these files exactly at the following paths before a full fresh rerun:

```text
data/rna_seq_metadata_2026-05-05_original.xlsx
data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

These are the local source workbooks used by the RNA and ChIP branches of the workflow. The pipeline creates derived TSVs and curator workbooks from them; do not edit the original workbooks as part of the pipeline.

## Optional Reference Files

If you have local gold-standard or review-reference workbooks from prior curator rounds, keep them in `data/` or a local-only folder and document their provenance in your lab notes. They are useful for manual comparison, but they are not required for the deterministic rerun path described in `docs/RERUN_VALIDATION.md`.

Do not commit reference workbooks unless the team has explicitly decided they are safe, licensed, and small enough for the repository.

## Copy Or Symlink Inputs

Copy:

```bash
mkdir -p data
cp /path/to/rna_seq_metadata_2026-05-05_original.xlsx data/
cp /path/to/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx data/
```

Symlink:

```bash
mkdir -p data
ln -s /path/to/rna_seq_metadata_2026-05-05_original.xlsx data/rna_seq_metadata_2026-05-05_original.xlsx
ln -s /path/to/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx
```

Symlinks are convenient on a shared workstation, but copied files are easier to archive with a rerun record.

## Local Generated Directories

These directories are local/generated and are not committed:

```text
outputs/
results/
papers/
data/sra_runinfo_cache/
data/biosample_cache/
```

`papers/` should contain downloaded or manually prepared paper PDFs/text before real AI-assisted curation. Deterministic packet construction can run without papers, but AI review quality depends on paper context.

## Preflight Check

Run:

```bash
python scripts/06_rerun_readiness_check.py
```

The script reports input workbook presence, cache and paper counts, Python import availability, workflow map status, and API guard state without printing secrets or writing outputs.
