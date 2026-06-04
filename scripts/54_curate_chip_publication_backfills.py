#!/usr/bin/env python3
"""
Curate ChIP publication backfill suggestions.

This script does NOT modify the master sheet.

It takes Entrez publication-resolution output and creates:
  1. a curated BioProject -> PMID backfill decision table
  2. a rowwise ChIP table with resolved publication fields
  3. AP2-focused publication-resolution table
  4. accepted/manual/rejected/unresolved split tables
  5. a report

Important manual rule currently encoded:
  - Reject PRJNA994684 -> PMID 39242698 because PMID 39242698 is a yak gut virome paper,
    not a Plasmodium ChIP/MORC paper.

Inputs:
  outputs/06_CHIP_AI_ASSIST/04_publication_resolution/chip_entrez_publication_resolution_by_bioproject.tsv
  outputs/06_CHIP_AI_ASSIST/04_publication_resolution/chip_publication_backfill_suggestions.tsv
  outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_rowwise_evidence_sra_enriched.tsv

Outputs:
  outputs/06_CHIP_AI_ASSIST/05_publication_backfill_curated/
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re
import pandas as pd


IN_RES = Path("outputs/06_CHIP_AI_ASSIST/04_publication_resolution/chip_entrez_publication_resolution_by_bioproject.tsv")
IN_BACKFILL = Path("outputs/06_CHIP_AI_ASSIST/04_publication_resolution/chip_publication_backfill_suggestions.tsv")
IN_ROWWISE = Path("outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_rowwise_evidence_sra_enriched.tsv")

OUT = Path("outputs/06_CHIP_AI_ASSIST/05_publication_backfill_curated")
OUT.mkdir(parents=True, exist_ok=True)


BAD_BACKFILLS = {
    ("PRJNA994684", "39242698"): "reject_bad_match_yak_virome_not_plasmodium_chip",
}


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def has_direct_ncbi_route(routes: str) -> bool:
    r = clean(routes)
    direct = [
        "existing_paper_link",
        "bioproject_elink_pubmed",
        "sra_elink_by_bioproject",
        "gds_elink_by_geo_tokens",
        "sra_elink_by_sra_tokens",
    ]
    return any(x in r for x in direct)


def is_target_search_only(routes: str) -> bool:
    vals = [x.strip() for x in clean(routes).split(";") if x.strip()]
    return vals == ["pubmed_search_targets"]


def classify(row: pd.Series) -> tuple[str, str, str]:
    """
    Return:
      publication_backfill_status
      resolved_paper_link_pmid
      publication_qc_note
    """
    bp = clean(row.get("bioproject", ""))
    suggested = clean(row.get("suggested_paper_link_pmid", ""))
    top = clean(row.get("top_candidate_pmid", ""))
    conf = clean(row.get("resolution_confidence", ""))
    routes = clean(row.get("top_candidate_routes", ""))
    title = clean(row.get("top_candidate_title", ""))

    pmid = suggested if suggested else top

    if (bp, pmid) in BAD_BACKFILLS:
        return (
            "reject_bad_match",
            "",
            BAD_BACKFILLS[(bp, pmid)] + f"; candidate_title={title}"
        )

    if conf == "none" or not is_pmid(pmid):
        return (
            "unresolved_no_pmid",
            "",
            "No candidate PMID found by current NCBI/GEO/PubMed resolution."
        )

    if is_target_search_only(routes):
        if conf in {"medium_high", "high", "existing_or_very_high"}:
            return (
                "manual_check_target_search_only",
                pmid,
                "Candidate found only by target/PubMed search; needs paper-level check before acceptance."
            )
        else:
            return (
                "unresolved_low_confidence_target_search",
                "",
                "Low-confidence target-search-only candidate; do not backfill automatically."
            )

    if conf in {"existing_or_very_high", "high"} and has_direct_ncbi_route(routes):
        if "existing_paper_link" in routes:
            return (
                "keep_or_accept_existing_validated",
                pmid,
                "Existing or direct NCBI-linked PMID validated by resolver."
            )
        return (
            "accept_backfill_high_confidence",
            pmid,
            "Accepted high-confidence backfill from direct NCBI/GEO/SRA/BioProject evidence."
        )

    if conf == "medium_high" and has_direct_ncbi_route(routes):
        return (
            "accept_backfill_medium_high_direct",
            pmid,
            "Accepted medium-high direct NCBI/GEO/SRA/BioProject evidence; still worth spot-checking."
        )

    if conf in {"medium", "low", "very_low"}:
        return (
            "manual_check_low_or_medium_confidence",
            pmid if is_pmid(pmid) else "",
            f"Confidence={conf}; manual check required before master-sheet backfill."
        )

    return (
        "manual_check_uncategorized",
        pmid if is_pmid(pmid) else "",
        "Uncategorized resolver state; manual review required."
    )


def main():
    for p in [IN_RES, IN_ROWWISE]:
        if not p.exists():
            raise SystemExit(f"Missing input: {p}")

    res = pd.read_csv(IN_RES, sep="\t", dtype=str).fillna("")
    rowwise = pd.read_csv(IN_ROWWISE, sep="\t", dtype=str).fillna("")

    required = ["bioproject", "resolution_confidence", "top_candidate_pmid", "top_candidate_routes", "top_candidate_title"]
    for c in required:
        if c not in res.columns:
            res[c] = ""

    if "suggested_paper_link_pmid" not in res.columns:
        res["suggested_paper_link_pmid"] = ""

    decisions = res.copy()

    classified = decisions.apply(classify, axis=1, result_type="expand")
    decisions["publication_backfill_status"] = classified[0]
    decisions["resolved_paper_link_pmid"] = classified[1]
    decisions["publication_qc_note"] = classified[2]

    decisions["is_accepted_for_intermediate"] = decisions["publication_backfill_status"].isin([
        "keep_or_accept_existing_validated",
        "accept_backfill_high_confidence",
        "accept_backfill_medium_high_direct",
    ])

    decisions["needs_manual_publication_review"] = decisions["publication_backfill_status"].isin([
        "manual_check_target_search_only",
        "manual_check_low_or_medium_confidence",
        "manual_check_uncategorized",
    ])

    decisions["is_rejected_publication_match"] = decisions["publication_backfill_status"].eq("reject_bad_match")
    decisions["is_unresolved_publication"] = decisions["publication_backfill_status"].str.startswith("unresolved")

    # Write curated decision tables.
    curated_path = OUT / "chip_publication_backfill_curated.tsv"
    decisions.to_csv(curated_path, sep="\t", index=False)

    accepted = decisions[decisions["is_accepted_for_intermediate"]].copy()
    manual = decisions[decisions["needs_manual_publication_review"]].copy()
    rejected = decisions[decisions["is_rejected_publication_match"]].copy()
    unresolved = decisions[decisions["is_unresolved_publication"]].copy()

    accepted_path = OUT / "chip_publication_backfill_ACCEPTED.tsv"
    manual_path = OUT / "chip_publication_backfill_MANUAL_CHECK.tsv"
    rejected_path = OUT / "chip_publication_backfill_REJECTED.tsv"
    unresolved_path = OUT / "chip_publication_backfill_UNRESOLVED.tsv"

    accepted.to_csv(accepted_path, sep="\t", index=False)
    manual.to_csv(manual_path, sep="\t", index=False)
    rejected.to_csv(rejected_path, sep="\t", index=False)
    unresolved.to_csv(unresolved_path, sep="\t", index=False)

    # AP2 subset.
    if "is_ap2_group" in decisions.columns:
        ap2 = decisions[decisions["is_ap2_group"].astype(str).str.lower().isin(["true", "1", "yes"])].copy()
    else:
        ap2 = decisions.iloc[0:0].copy()

    ap2_path = OUT / "chip_ap2_publication_backfill_curated.tsv"
    ap2.to_csv(ap2_path, sep="\t", index=False)

    # Build rowwise publication-enriched table.
    keep_cols = [
        "bioproject",
        "publication_backfill_status",
        "resolved_paper_link_pmid",
        "publication_qc_note",
        "resolution_confidence",
        "suggested_paper_link_pmid",
        "top_candidate_pmid",
        "top_candidate_routes",
        "top_candidate_title",
        "is_accepted_for_intermediate",
        "needs_manual_publication_review",
        "is_rejected_publication_match",
        "is_unresolved_publication",
    ]
    keep_cols = [c for c in keep_cols if c in decisions.columns]

    row_enriched = rowwise.merge(decisions[keep_cols], on="bioproject", how="left")

    # Do not overwrite original publication_key. Add resolved/intermediate fields.
    if "publication_key" not in row_enriched.columns:
        row_enriched["publication_key"] = ""

    row_enriched["original_paper_link"] = row_enriched["publication_key"]
    row_enriched["intermediate_resolved_paper_link"] = row_enriched["resolved_paper_link_pmid"].fillna("")
    row_enriched["publication_resolution_source"] = row_enriched["publication_backfill_status"].fillna("not_processed")

    row_enriched_path = OUT / "chip_rowwise_evidence_publication_enriched.tsv"
    row_enriched.to_csv(row_enriched_path, sep="\t", index=False)

    # Group-level table for next queue construction.
    group_cols = [
        "bioproject", "n_rows", "n_ap2_rows", "targets", "target_types",
        "publication_backfill_status", "resolved_paper_link_pmid",
        "resolution_confidence", "top_candidate_routes", "top_candidate_title",
        "publication_qc_note", "is_accepted_for_intermediate",
        "needs_manual_publication_review",
        "is_rejected_publication_match", "is_unresolved_publication"
    ]
    group_cols = [c for c in group_cols if c in decisions.columns]
    group_path = OUT / "chip_group_publication_enriched_inventory.tsv"
    decisions[group_cols].to_csv(group_path, sep="\t", index=False)

    # Report.
    report = []
    report.append("# ChIP Curated Publication Backfill Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- BioProjects evaluated: {len(decisions)}")
    report.append(f"- accepted for intermediate backfill: {len(accepted)}")
    report.append(f"- manual-check publication candidates: {len(manual)}")
    report.append(f"- rejected publication matches: {len(rejected)}")
    report.append(f"- unresolved: {len(unresolved)}")
    report.append(f"- AP2 BioProjects: {len(ap2)}")
    if len(ap2):
        report.append(f"- AP2 accepted: {int(ap2['is_accepted_for_intermediate'].sum())}")
        report.append(f"- AP2 manual-check: {int(ap2['needs_manual_publication_review'].sum())}")
        report.append(f"- AP2 unresolved: {int(ap2['is_unresolved_publication'].sum())}")
    report.append("")
    report.append("## Status counts")
    report.append("")
    for k, v in decisions["publication_backfill_status"].value_counts().items():
        report.append(f"- {k}: {v}")

    report.append("")
    report.append("## Rejected matches")
    report.append("")
    if rejected.empty:
        report.append("- none")
    else:
        for _, r in rejected.iterrows():
            report.append(
                f"- {r['bioproject']} candidate PMID {r.get('top_candidate_pmid','')} rejected: "
                f"{r['publication_qc_note']}"
            )

    report.append("")
    report.append("## AP2 publication status")
    report.append("")
    if ap2.empty:
        report.append("- none")
    else:
        for _, r in ap2.iterrows():
            report.append(
                f"- {r['bioproject']}: targets={str(r.get('targets',''))[:160]}; "
                f"status={r['publication_backfill_status']}; "
                f"resolved PMID={r['resolved_paper_link_pmid']}; "
                f"title={str(r.get('top_candidate_title',''))[:180]}"
            )

    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [
        curated_path,
        accepted_path,
        manual_path,
        rejected_path,
        unresolved_path,
        ap2_path,
        row_enriched_path,
        group_path,
    ]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_CURATED_PUBLICATION_BACKFILL_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", curated_path)
    print("Wrote:", accepted_path)
    print("Wrote:", manual_path)
    print("Wrote:", rejected_path)
    print("Wrote:", unresolved_path)
    print("Wrote:", ap2_path)
    print("Wrote:", row_enriched_path)
    print("Wrote:", group_path)
    print("Wrote:", report_path)
    print()
    print("Publication backfill status counts:")
    print(decisions["publication_backfill_status"].value_counts().to_string())
    print()
    print("Rejected matches:")
    if rejected.empty:
        print("None")
    else:
        show = ["bioproject", "top_candidate_pmid", "top_candidate_title", "publication_qc_note"]
        print(rejected[show].to_string(index=False))
    print()
    print("AP2 curated publication status:")
    show = [
        "bioproject", "n_rows", "n_ap2_rows", "targets",
        "publication_backfill_status", "resolved_paper_link_pmid",
        "resolution_confidence", "top_candidate_title"
    ]
    show = [c for c in show if c in ap2.columns]
    print(ap2[show].to_string(index=False))


if __name__ == "__main__":
    main()
