# Data Directory

This folder contains small tracked configuration files and local data files that are not tracked by Git.

## Tracked files

These are safe to keep in Git:

    pmid_corrections.tsv
    special_pmid_handling.tsv
    README_DATA.md

## Required local file

Place the master workbook here:

    data/rna_seq_metadata_2026-05-05_original.xlsx

This file is not tracked by Git.

## Generated local caches

The pipeline may create:

    data/biosample_cache/
    data/sra_runinfo_cache/
    data/geo_cache/

These are useful for reproducibility and speed, but they are generated/local files and are not tracked by Git.

## Other local files

Some workflows may use local SRA RunTable files, for example:

    *_SraRunTable.csv

These are not tracked by Git.

## Important note

The original master workbook should not be overwritten by curator review.

The final reviewed table should be written as a new output file after merge-back.
