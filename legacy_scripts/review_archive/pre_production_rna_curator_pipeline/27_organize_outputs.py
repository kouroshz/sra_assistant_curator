#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
import argparse
import shutil
import pandas as pd
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

DESTS = {
    "final_package": OUT / "00_FINAL_CURATOR_PACKAGE",
    "final_tables": OUT / "01_CURRENT_DRAFT_TABLES",
    "qc": OUT / "02_QC_SUMMARIES",
    "per_pmid": OUT / "03_PER_PMID_INTERMEDIATES",
    "agentic_ai": OUT / "04_AGENTIC_AI_ASSIST",
    "logs": OUT / "05_LOGS",
    "archive": OUT / "06_ARCHIVE_OLD",
    "misc": OUT / "99_MISC_UNSORTED",
}

PMID_RE = re.compile(r"PMID_(\d+)")


def classify(path: Path):
    name = path.name
    rel = path.relative_to(OUT)

    # Do not move files already in organized folders.
    if rel.parts[0].startswith(("00_", "01_", "02_", "03_", "04_", "05_", "06_", "99_")):
        return None, None

    # Keep manifest files visible at top level for now.
    if name.startswith("OUTPUT_MANIFEST"):
        return None, None

    # Existing folders.
    if path.is_dir():
        if name == "curator_package":
            return "final_package", path.name
        if name in {"batch_logs"}:
            return "logs", path.name
        if name in {"agentic_ai_logs", "agentic_ai_prompts"}:
            return "agentic_ai", path.name
        if name.startswith("archive_"):
            return "archive", path.name
        return "misc", path.name

    # Final curator/package files.
    if name in {
        "curator_package.zip",
        "curator_group_level_review_index_FOR_REVIEW.xlsx",
        "PMID_30320226_single_cell_collapsed_review.xlsx",
        "README_CURATOR.md",
    }:
        return "final_package", name

    # Final/current tables.
    if name in {
        "all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv",
        "all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.summary.tsv",
        "curator_group_level_review_index.xlsx",
        "curator_group_level_review_index.tsv",
        "curator_review_index.xlsx",
        "curator_review_index.tsv",
        "selected_agentic_ai_curator_assist_summary.xlsx",
    }:
        return "final_tables", name

    # QC / status summaries.
    if name in {
        "all_pmids_agent_filled_master_rows_with_paper_context.tsv",
        "batch_curator_pipeline_status.tsv",
        "batch_curator_qc_summary.tsv",
        "master_pmid_metadata_coverage.tsv",
        "pdf_download_status.tsv",
        "pmid_candidates.tsv",
        "pmids_needing_pdfs.tsv",
        "pmids_still_needing_manual_pdf_download.tsv",
        "agentic_ai_complete_pmids.txt",
        "agentic_ai_missing_pmids.txt",
        "pmid_correction_pdf_to_download.tsv",
        "pmids_needing_manual_pdfs_after_oa_download.tsv",
    }:
        return "qc", name

    # agentic AI assist outputs.
    if "_agentic_ai_" in name:
        return "agentic_ai", name

    # Old API LLM files and review_with_llm are not core now.
    if "_llm_" in name or "_with_llm" in name:
        return "archive", f"old_api_llm/{name}"

    # Old full master-per-PMID xlsx are huge and redundant.
    if name.startswith("rna_seq_metadata_v1_2026-05-05.agent_filled_PMID_"):
        return "archive", f"old_full_pmid_workbooks/{name}"

    # Per-PMID intermediate outputs.
    m = PMID_RE.search(name)
    if m:
        pmid = m.group(1)
        return "per_pmid", f"PMID_{pmid}/{name}"

    # Spotcheck workbook is useful but not central.
    if name.startswith("spotcheck"):
        return "qc", name

    # Everything else.
    return "misc", name


def safe_dest(dest: Path):
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent

    i = 1
    while True:
        candidate = parent / f"{stem}.duplicate_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually move files. Default is dry run.")
    args = ap.parse_args()

    rows = []
    actions = []

    # include both files and selected directories directly under outputs/
    items = sorted([p for p in OUT.iterdir() if p.name not in {".DS_Store"}])

    for p in items:
        category, rel_dest = classify(p)
        if category is None:
            rows.append({
                "action": "keep_in_place",
                "category": "",
                "source": str(p.relative_to(OUT)),
                "destination": "",
                "size_bytes": p.stat().st_size if p.is_file() else "",
            })
            continue

        dest = DESTS[category] / rel_dest
        rows.append({
            "action": "move" if args.apply else "would_move",
            "category": category,
            "source": str(p.relative_to(OUT)),
            "destination": str(dest.relative_to(OUT)),
            "size_bytes": p.stat().st_size if p.is_file() else "",
        })
        actions.append((p, dest))

    plan = pd.DataFrame(rows)
    plan_file = OUT / ("OUTPUT_ORGANIZATION_APPLIED.tsv if args.apply else OUTPUT_ORGANIZATION_PLAN.tsv".split()[0])
    if args.apply:
        plan_file = OUT / "OUTPUT_ORGANIZATION_APPLIED.tsv"
    else:
        plan_file = OUT / "OUTPUT_ORGANIZATION_PLAN.tsv"

    plan.to_csv(plan_file, sep="\t", index=False)

    print("\n=== Output organization plan ===")
    print("Mode:", "APPLY / MOVE FILES" if args.apply else "DRY RUN / NO FILES MOVED")
    print("Plan:", plan_file)

    print("\nCounts by category/action:")
    print(plan.groupby(["action", "category"]).size().to_string())

    print("\nExample planned moves:")
    ex = plan[plan["action"].isin(["would_move", "move"])].head(40)
    print(ex[["source", "destination"]].to_string(index=False))

    if not args.apply:
        print("\nDry run only. To apply:")
        print("python scripts/27_organize_outputs.py --apply")
        return

    # Create destination folders.
    for d in DESTS.values():
        d.mkdir(parents=True, exist_ok=True)

    # Move files/directories.
    for src, dest in actions:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest = safe_dest(dest)
        shutil.move(str(src), str(dest))

    # Write README.
    readme = OUT / "README_OUTPUTS.md"
    readme.write_text(f"""# Organized outputs

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Folder guide

- `00_FINAL_CURATOR_PACKAGE/`
  Final curator-facing package and files to share.

- `01_CURRENT_DRAFT_TABLES/`
  Current row-level draft table and group-level review/index tables.

- `02_QC_SUMMARIES/`
  Pipeline status, PDF/download/candidate summaries, coverage reports, and complete/missing agentic AI PMID lists.

- `03_PER_PMID_INTERMEDIATES/`
  Per-PMID intermediate TSV/JSON/TXT/XLSX files used for audit/debugging.

- `04_AGENTIC_AI_ASSIST/`
  agentic AI prompts, logs, Markdown notes, and group suggestion TSVs.

- `05_LOGS/`
  Batch pipeline logs.

- `06_ARCHIVE_OLD/`
  Old prototype outputs, old API/LLM outputs, redundant full per-PMID workbooks, and previous archived experiments.

- `99_MISC_UNSORTED/`
  Anything not recognized by the organizer.

## Main curator file

Use:

`00_FINAL_CURATOR_PACKAGE/curator_package.zip`

or the workbook:

`00_FINAL_CURATOR_PACKAGE/curator_package/curator_group_level_review_index_FOR_REVIEW.xlsx`

## Main current row-level draft

`01_CURRENT_DRAFT_TABLES/all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv`

## Important note

The original master workbook is not the final reviewed master. Curators work in the FOR_REVIEW workbook. Later, curator decisions should be propagated back into a final master workbook.
""")

    print("\nMoved files and wrote:")
    print(readme)


if __name__ == "__main__":
    main()
