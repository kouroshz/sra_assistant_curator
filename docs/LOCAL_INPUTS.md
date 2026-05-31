# Local Inputs

This repo is code-first. Large or copyrighted files are not stored in Git.

## Required local files

### Master workbook

Put here:

    data/rna_seq_metadata_v1_2026-05-05.xlsx

### Paper PDFs

Put here:

    papers/

Use filenames beginning with PMID when possible:

    <PMID>_<short_title>.pdf

## Optional caches

These folders are generated automatically or shared locally:

    data/biosample_cache/
    data/sra_runinfo_cache/
    data/geo_cache/

They are not required to clone the repo, but they make reruns faster.

## Sharing with team members

Recommended approach:

1. Share the GitHub repo for code and documentation.
2. Share the master workbook separately.
3. Share PDFs separately, or let users run the open-access downloader.
4. Keep generated outputs local unless intentionally sharing a curator package.

## Open-access PDF downloader

Run after PMID/PDF status files exist:

    python scripts/15_download_open_access_pdfs.py \
      --pmids-file outputs/pmids_needing_pdfs.tsv \
      --email YOUR_EMAIL_HERE \
      --sleep 1.0

Manually download any remaining PDFs and place them in papers/.
