# Current Pipeline Status and Strategy

## Project goal

The goal is to build a curated public-data processing manifest for Plasmodium functional genomics.

The endpoint is not a cleaned spreadsheet for its own sake. The endpoint is a rowwise/runwise manifest where each FASTQ/SRA run has enough reliable metadata for downstream processing, comparison, peak calling, differential expression, and eventually functional regulatory network construction.

The final manifest should support questions such as:

- What sample/run is this?
- What assay is it?
- What stage/timepoint/strain/condition does it represent?
- Is it experimental, control, input, IgG, WT, untreated, vehicle, or unknown?
- What is the matched comparator/background/control?
- Is it ready for downstream processing?

## Strategic framing

The core object must remain rowwise/runwise.

Group-level summaries can be useful for batching, QC, paper-level reasoning, and curator review, but they should not become the main final curation object. The pipeline ultimately needs one usable row per source row / Run / FASTQ-level sample.

Curators cannot manually inspect thousands of lines one by one. The intended workflow is:

1. Deterministic metadata enrichment from public sources.
2. Compact evidence construction per row.
3. Paper/BioProject-level agentic AI assistance.
4. Human review of sample maps, low-confidence rows, and random QC rows.
5. Controlled merge-back into the final rowwise manifest.

## Work completed so far

### 1. Repository and project cleanup

The repository was reset around the new master workbook:

- data/rna_seq_metadata_2026-05-05_original.xlsx

Old Codex language was replaced with agentic AI terminology. Legacy Codex scripts were moved into scripts/legacy.

The project now treats API-based curation as optional and disabled by default. Users can run the deterministic pipeline without API access. API users provide their own token locally through .env.

### 2. Stable row and group identifiers

Script added:

- scripts/28_add_stable_ids_to_master.py

This adds:

- source_row_id
- source_row_number
- curation_group_id
- curation_group_size

The special single-cell/well-level PMID 30320226 is excluded from the normal workflow and routed separately.

Stable-ID summary:

- Original rows before exclusion: 8,642
- Excluded special PMID 30320226 rows: 2,310
- Normal rowwise workflow rows: 6,332
- Unique source_row_id values: 6,332
- Initial curation groups: 170
- Unique Run IDs: 6,280
- Duplicate Run rows: 52

### 3. Group-level curator scaffold

Script added:

- scripts/29_make_group_level_curator_review.py

This creates a group-level review workbook with stable IDs.

Current interpretation: this table is useful as a scaffold and batching/QC object, but it should not be treated as the final curation object. Some groups are too coarse because key biological fields in the master are blank.

### 4. Agentic AI input packet scaffold

Script added:

- scripts/30_make_agentic_ai_input_packets.py

This created initial group-level JSON packets for future AI curation.

Packet summary:

- Total packets: 170
- Packets with matched PDF candidates: 76
- Packets without PDF candidates: 94

Current interpretation: useful early scaffold, but the better direction is paper/BioProject-level packets built from rowwise public metadata evidence.

### 5. Optional API setup and pilot

Scripts/docs added:

- scripts/31_test_openai_api.py
- scripts/32_run_agentic_ai_on_packet.py
- docs/API_ASSIST_OPTIONAL_SETUP.md
- requirements-ai.txt
- .env.example

API curation is optional and disabled by default. It requires:

- AGENTIC_AI_ENABLE_API=1
- OPENAI_API_KEY supplied locally by the user

A single-packet API pilot was successfully run. The model produced a useful structured suggestion and correctly flagged ambiguity when a packet likely mixed multiple experimental comparisons.

Important lesson from the pilot: the AI should not only summarize a coarse group. It should help infer paper-level sample maps and rowwise annotations.

### 6. Deterministic SRA/BioSample metadata fetch

Script added:

- scripts/33_fetch_public_sra_biosample_metadata.py

This fetches and caches public SRA RunInfo and BioSample XML metadata.

The full run completed successfully.

Fetch outcome:

- Status OK records: 10,304
- Cached records: 1,019
- SRA RunInfo cache files: 6,280
- BioSample XML cache files: 5,043

This means the public metadata cache now covers the normal workflow scale.

### 7. Rowwise public metadata evidence table

Script added:

- scripts/34_build_rowwise_public_metadata_evidence.py

This parses the SRA/BioSample caches and creates a compact rowwise evidence table:

- outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv

Evidence summary:

- Rowwise records: 6,332
- Rows with SRA cache: 6,332
- Rows with BioSample cache: 6,332
- SRA SampleName available: 6,332 rows
- SRA ScientificName available: 6,332 rows
- SRA LibraryName available: 4,038 rows
- BioSample title available: 6,332 rows

Biological signal recovered:

- Strain evidence: 6,332 rows
- Stage/timepoint evidence: 3,772 rows, about 59.6 percent
- Condition/perturbation evidence: 2,316 rows, about 36.6 percent
- BioSample isolate: 2,278 rows, about 36.0 percent
- BioSample strain: 1,974 rows, about 31.2 percent
- BioSample genotype: 1,403 rows, about 22.2 percent
- Detected perturbation terms: 1,150 rows, about 18.2 percent
- Detected control terms: 649 rows, about 10.3 percent
- Rows still needing AI for at least one major missing component: 4,322 rows

## Interpretation of the metadata scraping

The deterministic NCBI/SRA/BioSample enrichment was highly useful.

It turns the problem from blind metadata cleanup into targeted paper-reading and sample-map inference.

Examples of useful recovered evidence include:

- P.falciparum_3D7_RNAseq_5hpi
- P.falciparum_3D7_RNAseq_10hpi
- ring
- early trophozoite
- schizont
- GlcN treated replicate
- untreated replicate
- DHFR-TS-GFP_glmS integrant GlcN treated replicate
- isolate, strain, genotype, developmental stage, treatment, and BioSample title fields

This evidence should reduce API token use and improve AI accuracy because the model can reason over compact rowwise evidence rather than raw noisy metadata alone.

## Revised AI strategy

The agentic AI should not be the first reader of everything.

The better design is:

1. Use deterministic public metadata scraping first.
2. Build compact rowwise evidence.
3. Build paper/BioProject-level AI packets.
4. Ask AI to infer sample maps and rowwise annotations.
5. Ask AI to flag ambiguity, confidence, and evidence pointers.
6. Let human curators approve/edit final values.

The AI should produce:

- Paper/BioProject summary
- Inferred sample map
- Rowwise annotation suggestions
- Low-confidence row list
- Suggested control/background relationships
- Evidence pointers for curator checking
- Warnings where sample mapping is ambiguous

The AI should not overwrite the master sheet or final curator fields.

## Curator-facing design principle

Avoid a large number of visible ai_* columns.

Curators should see compact, useful columns such as:

- source_row_id
- Run
- BioSample
- PMID
- BioProject
- current parsed values
- assistant suggested values
- assistant confidence
- assistant evidence
- assistant flags
- curator final values
- curator note

Detailed AI outputs can live as sidecar JSON/TSV files.

Curators should mainly review:

1. Paper-level summaries.
2. Inferred sample maps.
3. Low-confidence rows.
4. Stratified random QC rows.
5. Full rowwise manifest only when needed.

## Recommended next technical step

Build paper/BioProject-level AI packets from:

- outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv

New script to add:

- scripts/35_make_paper_level_ai_packets.py

Each packet should represent one PMID/BioProject or BioProject-only unit and contain:

- all rowwise public metadata evidence for that unit
- matched paper PDF path if available
- compact SRA/BioSample evidence
- current metadata fields
- requested output schema for sample_map and rowwise_suggestions

This replaces the earlier coarse curation_group packet model as the main AI input.

## Current best workflow summary

Master workbook
→ exclude special single-cell case
→ add stable source_row_id
→ fetch SRA/BioSample public metadata
→ build rowwise public metadata evidence table
→ build paper/BioProject-level AI packets
→ optional agentic AI paper-reading/sample-map inference
→ human curator review
→ final rowwise processing manifest
