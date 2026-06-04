#!/usr/bin/env python3
"""
Build ChIP paper availability and AI-readiness tables.

Purpose:
  - Merge ChIP resolved-publication queue with PDF download status.
  - Identify which PMID/BioProject groups can proceed to AI with full PDFs.
  - Flag AP2/factor-priority groups missing PDFs.
  - Produce curator-facing and pipeline-facing readiness tables.

Inputs:
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_resolved_publication_group_queue.tsv
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_resolved_publication_rowwise.tsv
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_pmid_download_manifest.tsv
  outputs/06_CHIP_AI_ASSIST/07_papers/chip_pdf_download_status.tsv
  outputs/06_CHIP_AI_ASSIST/07_papers/chip_pmids_still_needing_manual_pdf_download.tsv

Outputs:
  outputs/06_CHIP_AI_ASSIST/08_paper_availability/
    chip_paper_availability_by_pmid.tsv
    chip_ai_readiness_by_bioproject.tsv
    chip_ai_ready_with_pdf_queue.tsv
    chip_ai_missing_pdf_priority_queue.tsv
    chip_curator_paper_availability_review.tsv
    CHIP_PAPER_AVAILABILITY_AND_AI_READINESS_REPORT.md
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd
import re


BASE_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue")
BASE_PAPERS = Path("outputs/06_CHIP_AI_ASSIST/07_papers")
OUT = Path("outputs/06_CHIP_AI_ASSIST/08_paper_availability")
OUT.mkdir(parents=True, exist_ok=True)

IN_GROUP = BASE_QUEUE / "chip_resolved_publication_group_queue.tsv"
IN_ROWWISE = BASE_QUEUE / "chip_resolved_publication_rowwise.tsv"
IN_PMID_MANIFEST = BASE_QUEUE / "chip_pmid_download_manifest.tsv"
IN_DL_STATUS = BASE_PAPERS / "chip_pdf_download_status.tsv"
IN_MISSING = BASE_PAPERS / "chip_pmids_still_needing_manual_pdf_download.tsv"


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def is_true(x) -> bool:
    return clean(x).lower() in {"true", "1", "yes"}


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def status_has_pdf(status: str, pdf_path: str) -> bool:
    status = clean(status)
    pdf_path = clean(pdf_path)
    return bool(pdf_path) and status in {
        "already_exists",
        "downloaded_europepmc_render",
        "downloaded_unpaywall_best",
        "downloaded_pmc_pdf",
        "downloaded_ncbi_pmc_pdf",
        "downloaded_openalex",
        "downloaded_url",
    }


def main():
    for p in [IN_GROUP, IN_ROWWISE, IN_PMID_MANIFEST, IN_DL_STATUS]:
        if not p.exists():
            raise SystemExit(f"Missing input: {p}")

    group = pd.read_csv(IN_GROUP, sep="\t", dtype=str).fillna("")
    rowwise = pd.read_csv(IN_ROWWISE, sep="\t", dtype=str).fillna("")
    pmids = pd.read_csv(IN_PMID_MANIFEST, sep="\t", dtype=str).fillna("")
    dl = pd.read_csv(IN_DL_STATUS, sep="\t", dtype=str).fillna("")

    missing = pd.read_csv(IN_MISSING, sep="\t", dtype=str).fillna("") if IN_MISSING.exists() else pd.DataFrame()

    # Normalize PMID column names.
    if "PMID" in dl.columns and "pmid" not in dl.columns:
        dl["pmid"] = dl["PMID"]
    if "PMID" in pmids.columns and "pmid" not in pmids.columns:
        pmids["pmid"] = pmids["PMID"]

    for c in ["pmid", "status", "pdf_path", "title", "doi", "pmcid", "message"]:
        if c not in dl.columns:
            dl[c] = ""

    dl["pmid"] = dl["pmid"].map(clean)
    dl["pdf_available"] = [
        status_has_pdf(s, p)
        for s, p in zip(dl["status"], dl["pdf_path"])
    ]

    # Build paper availability by PMID.
    paper = pmids.merge(
        dl[["pmid", "status", "pdf_path", "source", "doi", "pmcid", "message", "pdf_available"]],
        on="pmid",
        how="left",
    )

    for c in ["status", "pdf_path", "pdf_available"]:
        if c not in paper.columns:
            paper[c] = ""

    paper["pdf_available"] = paper["pdf_available"].map(lambda x: is_true(x) if isinstance(x, str) else bool(x))
    paper["paper_availability_status"] = paper.apply(
        lambda r:
            "pdf_available" if bool(r["pdf_available"]) else
            "manual_pdf_needed_high_ap2" if clean(r.get("download_priority", "")) == "high_ap2" else
            "manual_pdf_needed_standard",
        axis=1,
    )

    paper["curator_paper_status"] = ""
    paper["curator_notes"] = ""
    paper["manual_pdf_path"] = ""

    paper_path = OUT / "chip_paper_availability_by_pmid.tsv"
    paper.to_csv(paper_path, sep="\t", index=False)

    # Merge paper availability back to BioProject group queue.
    for c in ["resolved_paper_link_pmid", "bioproject", "is_ap2_group", "n_rows", "targets", "recommended_action"]:
        if c not in group.columns:
            group[c] = ""

    group["pmid"] = group["resolved_paper_link_pmid"].map(clean)

    g = group.merge(
        paper[[
            "pmid", "pdf_available", "paper_availability_status", "pdf_path",
            "status", "source", "doi", "pmcid", "message"
        ]],
        on="pmid",
        how="left",
    )

    g["pdf_available"] = g["pdf_available"].map(lambda x: is_true(x) if isinstance(x, str) else bool(x))

    def ai_readiness(row):
        if bool(row["pdf_available"]):
            return "ready_for_chip_ai_with_pdf"
        if is_true(row.get("is_ap2_group", "")):
            return "hold_or_run_with_abstract_missing_ap2_pdf"
        return "hold_missing_pdf_standard"

    g["chip_ai_readiness"] = g.apply(ai_readiness, axis=1)
    g["curator_publication_check"] = ""
    g["curator_assay_check"] = ""
    g["curator_target_control_check"] = ""
    g["curator_notes"] = ""

    g = g.sort_values(
        ["chip_ai_readiness", "is_ap2_group", "priority"],
        ascending=[True, False, False],
    )

    readiness_path = OUT / "chip_ai_readiness_by_bioproject.tsv"
    g.to_csv(readiness_path, sep="\t", index=False)

    ready = g[g["chip_ai_readiness"] == "ready_for_chip_ai_with_pdf"].copy()
    missing_priority = g[g["chip_ai_readiness"].isin([
        "hold_or_run_with_abstract_missing_ap2_pdf",
        "hold_missing_pdf_standard",
    ])].copy()

    ready_path = OUT / "chip_ai_ready_with_pdf_queue.tsv"
    missing_path = OUT / "chip_ai_missing_pdf_priority_queue.tsv"

    ready.to_csv(ready_path, sep="\t", index=False)
    missing_priority.to_csv(missing_path, sep="\t", index=False)

    # Curator-facing review table: one row per PMID.
    cur_cols = [
        "pmid", "paper_availability_status", "download_priority", "title",
        "bioprojects", "n_bioprojects", "is_ap2_group", "total_rows",
        "targets", "target_types", "pdf_path", "doi", "pmcid",
        "status", "message", "manual_pdf_path",
        "curator_paper_status", "curator_notes",
    ]
    cur_cols = [c for c in cur_cols if c in paper.columns]
    curator = paper[cur_cols].copy()

    curator_path = OUT / "chip_curator_paper_availability_review.tsv"
    curator.to_csv(curator_path, sep="\t", index=False)

    # Report.
    n_pmid = len(paper)
    n_pdf = int(paper["pdf_available"].sum())
    n_missing = n_pmid - n_pdf
    n_high_ap2_missing = int((paper["paper_availability_status"] == "manual_pdf_needed_high_ap2").sum())
    n_ready_groups = len(ready)
    n_missing_groups = len(missing_priority)

    report = []
    report.append("# ChIP Paper Availability and AI Readiness Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Paper availability")
    report.append("")
    report.append(f"- unique PMIDs: {n_pmid}")
    report.append(f"- PDFs available: {n_pdf}")
    report.append(f"- PDFs missing/manual needed: {n_missing}")
    report.append(f"- missing high-priority AP2 PDFs: {n_high_ap2_missing}")
    report.append("")
    report.append("## BioProject AI readiness")
    report.append("")
    report.append(f"- BioProject groups ready for ChIP AI with PDF: {n_ready_groups}")
    report.append(f"- BioProject groups held/missing PDF: {n_missing_groups}")
    report.append("")
    report.append("## Readiness counts")
    report.append("")
    for k, v in g["chip_ai_readiness"].value_counts().items():
        report.append(f"- {k}: {v}")

    report.append("")
    report.append("## Missing high-priority AP2 PDFs")
    report.append("")
    miss_ap2 = paper[paper["paper_availability_status"] == "manual_pdf_needed_high_ap2"].copy()
    if miss_ap2.empty:
        report.append("- none")
    else:
        for _, r in miss_ap2.iterrows():
            report.append(
                f"- PMID {r['pmid']}: {r.get('title','')} "
                f"targets={str(r.get('targets',''))[:180]}"
            )

    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [paper_path, readiness_path, ready_path, missing_path, curator_path]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_PAPER_AVAILABILITY_AND_AI_READINESS_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", paper_path)
    print("Wrote:", readiness_path)
    print("Wrote:", ready_path)
    print("Wrote:", missing_path)
    print("Wrote:", curator_path)
    print("Wrote:", report_path)
    print()
    print("Summary:")
    print(pd.DataFrame([{
        "unique_pmids": n_pmid,
        "pdfs_available": n_pdf,
        "pdfs_missing": n_missing,
        "missing_high_ap2_pdfs": n_high_ap2_missing,
        "groups_ready_with_pdf": n_ready_groups,
        "groups_missing_pdf": n_missing_groups,
    }]).to_string(index=False))
    print()
    print("Readiness counts:")
    print(g["chip_ai_readiness"].value_counts().to_string())


if __name__ == "__main__":
    main()
