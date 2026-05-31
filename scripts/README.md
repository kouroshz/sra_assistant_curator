# Scripts

Scripts are numbered roughly by pipeline order.

## Core deterministic pipeline

- 01_filter_master_by_pmid.py
- 02_fetch_sra_runinfo_for_master_rows.py
- 03_fetch_biosample_metadata_for_master_rows.py
- 04_populate_master_from_biosample.py
- 06_list_pmid_candidates.py
- 07_extract_paper_context.py
- 08_apply_paper_context_to_master.py
- 09_make_curator_review_view.py
- 14_add_curator_condition_fields.py
- 15_download_open_access_pdfs.py
- 16_run_batch_curator_pipeline.py
- 17_apply_special_pmid_handling.py
- 18_make_curator_review_index.py
- 19_make_group_level_curator_index.py
- 20_make_spotcheck_workbook.py

## PMID-specific deterministic patches

- 21_patch_pmid_31737630_dis3.py
- 22_patch_pmid_34365503_timepoints.py
- 23_patch_pmid_32552779_arp4_glcn.py

## Optional Codex assist

- 24_run_codex_curator_assist_selected.sh
- 25_merge_codex_curator_assist.py

## Output organization

- 26_freeze_current_outputs.py
- 27_organize_outputs.py

## Planned

- 28_apply_curator_review_to_rowwise_table.py
