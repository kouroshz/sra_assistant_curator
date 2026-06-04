#!/usr/bin/env python3
"""
Prepare ChIP PMID manifest for the existing open-access PDF downloader.

Reuses:
  scripts/15_download_open_access_pdfs.py

Reads:
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_pmid_download_manifest.tsv

Writes:
  outputs/06_CHIP_AI_ASSIST/07_papers/
    chip_pmids_needing_pdfs_for_downloader.tsv
    chip_paper_download_manifest_curator_facing.tsv
    CHIP_PDF_DOWNLOAD_PREP_REPORT.md

Notes:
  - The existing downloader expects a column named PMID.
  - This script keeps ChIP-specific provenance and curator-facing context.
  - It does not download anything itself.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd
import re

IN = Path("outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_pmid_download_manifest.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/07_papers")
PAPERS = Path("papers")
OUT.mkdir(parents=True, exist_ok=True)
PAPERS.mkdir(exist_ok=True)


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def existing_pdf_for_pmid(pmid: str) -> str:
    hits = sorted(PAPERS.glob(f"*{pmid}*.pdf"))
    return str(hits[0]) if hits else ""


def main():
    if not IN.exists():
        raise SystemExit(f"Missing input: {IN}")

    df = pd.read_csv(IN, sep="\t", dtype=str).fillna("")

    if "pmid" not in df.columns:
        raise SystemExit("Expected column 'pmid' in chip_pmid_download_manifest.tsv")

    df["PMID"] = df["pmid"].map(clean)
    df = df[df["PMID"].map(is_pmid)].copy()

    df["existing_pdf_path"] = df["PMID"].map(existing_pdf_for_pmid)
    df["pdf_already_present"] = df["existing_pdf_path"].map(lambda x: clean(x) != "")

    # Downloader-compatible file. Extra columns are okay; downloader only needs PMID.
    downloader_cols = [
        "PMID",
        "download_priority",
        "title",
        "bioprojects",
        "n_bioprojects",
        "is_ap2_group",
        "total_rows",
        "targets",
        "target_types",
        "resolution_confidences",
        "publication_backfill_statuses",
        "existing_pdf_path",
    ]
    downloader_cols = [c for c in downloader_cols if c in df.columns]

    downloader_path = OUT / "chip_pmids_needing_pdfs_for_downloader.tsv"
    df[downloader_cols].to_csv(downloader_path, sep="\t", index=False)

    # Curator-facing manifest with review fields.
    cur = df.copy()
    cur["curator_paper_status"] = ""
    cur["curator_notes"] = ""
    cur["paper_relevance_check"] = ""
    cur["paper_assay_check"] = ""
    cur["paper_target_check"] = ""

    curator_cols = [
        "PMID",
        "download_priority",
        "title",
        "bioprojects",
        "n_bioprojects",
        "is_ap2_group",
        "total_rows",
        "targets",
        "target_types",
        "resolution_confidences",
        "publication_backfill_statuses",
        "pdf_already_present",
        "existing_pdf_path",
        "curator_paper_status",
        "paper_relevance_check",
        "paper_assay_check",
        "paper_target_check",
        "curator_notes",
    ]
    curator_cols = [c for c in curator_cols if c in cur.columns]

    curator_path = OUT / "chip_paper_download_manifest_curator_facing.tsv"
    cur[curator_cols].to_csv(curator_path, sep="\t", index=False)

    report = []
    report.append("# ChIP PDF Download Preparation Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- unique PMIDs in manifest: {len(df)}")
    report.append(f"- high-priority AP2 PMIDs: {int((df.get('download_priority','') == 'high_ap2').sum()) if 'download_priority' in df.columns else 0}")
    report.append(f"- PDFs already present in `papers/`: {int(df['pdf_already_present'].sum())}")
    report.append(f"- PDFs needing download/manual retrieval: {int((~df['pdf_already_present']).sum())}")
    report.append("")
    report.append("## Files written")
    report.append("")
    report.append(f"- `{downloader_path}`")
    report.append(f"- `{curator_path}`")
    report.append("")
    report.append("## Next command")
    report.append("")
    report.append("```bash")
    report.append("python scripts/15_download_open_access_pdfs.py \\")
    report.append(f"  --pmids-file {downloader_path} \\")
    report.append('  --email "$NCBI_EMAIL" \\')
    report.append("  --sleep 1.0")
    report.append("```")

    report_path = OUT / "CHIP_PDF_DOWNLOAD_PREP_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", downloader_path)
    print("Wrote:", curator_path)
    print("Wrote:", report_path)
    print()
    print("Summary:")
    print(pd.DataFrame([{
        "unique_pmids": len(df),
        "high_ap2_pmids": int((df.get("download_priority", "") == "high_ap2").sum()) if "download_priority" in df.columns else 0,
        "pdfs_already_present": int(df["pdf_already_present"].sum()),
        "pdfs_need_download": int((~df["pdf_already_present"]).sum()),
    }]).to_string(index=False))


if __name__ == "__main__":
    main()
