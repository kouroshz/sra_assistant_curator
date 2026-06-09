# Curator Workflow Overview

This workflow starts from two local Excel manifests, but those workbooks are not treated as the final evidence layer. They are the starting manifests for a reproducible RNA and ChIP curator-assist pipeline.

## Evidence Layers

1. Input Excel manifests provide starting rows, run accessions, study labels, and existing human annotations.
2. SRA RunInfo and BioSample cache files are rebuilt as an auditable public metadata layer.
3. Deterministic rules create reproducible first-pass annotations, grouping, publication links, control hints, and packet queues.
4. Paper/PDF context is used to interpret study design, controls, perturbations, omics, and ambiguous cases.
5. Optional AI runs propose curator-facing corrections, warnings, and study summaries.

AI output is never authoritative. It is a review aid. Human curator decisions and curator-final workbook columns remain authoritative.

## RNA Focus

For RNA studies, the key curation distinction is whether a study is primarily:

- contrast or perturbation design, such as mutant/control, drug/vehicle, knockdown/control, or temperature shift;
- expression/time-course/atlas design, where stage, strain, and timepoint classification matter more than a single treatment comparison.

RNA AI packets should confirm study design, stage, strain/genotype, treatment/control logic, and whether paper evidence supports the proposed grouping.

## ChIP Focus

For ChIP-like assays, the central object is target/input/background matching. Curators should review:

- target IP rows;
- input/background rows;
- IgG/mock/untagged controls where present;
- reused shared backgrounds;
- whether a physical antibody IP also functions analytically as a background/reference.

Some ChIP rows can have different physical and analytical roles. For example, an H3core antibody IP can be physically an IP sample while analytically serving as a chromatin normalization or reference background for another histone mark. Those cases should be flagged for curator review rather than collapsed into a single role.

## Release Modes

Final packages can be:

- `full`: matches the current full golden expected coverage.
- `pilot`: intentionally limited AI run for smoke testing.
- `partial`: structurally valid curator-facing release with incomplete AI coverage.

Partial releases should not be presented as complete golden releases. They are useful for review, debugging, and incremental curation.
