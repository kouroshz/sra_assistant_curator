# ChIP metadata input note

The RNA-seq master workbook is transcriptomics-only:

- data/rna_seq_metadata_2026-05-05_original.xlsx

ChIP/CUT&RUN/CUT&Tag-like curation should not be inferred from the RNA-seq master. For ChIP annotation, target/background/control/replicate curation should use:

- data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx

Important distinction:

- RNA-seq curation focuses on sample identity, stage/timepoint, strain, perturbation/treatment, controls/comparators, and DEG or expression-readiness.
- ChIP-like curation focuses on target, antibody/tag, sample role, input/IgG/untagged/background assignment, replicate structure, and peak-calling readiness.

High-confidence rule:

- no publication/PMID link -> quarantine
- ChIP target sample without valid background/control -> not peak-calling-ready
