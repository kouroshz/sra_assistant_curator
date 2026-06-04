#!/usr/bin/env python3
"""
Build resolved-publication ChIP queue and PMID download manifest.

This script does NOT modify the master sheet and does NOT run AI.

Inputs:
  outputs/06_CHIP_AI_ASSIST/05_publication_backfill_curated/
    chip_rowwise_evidence_publication_enriched.tsv
    chip_group_publication_enriched_inventory.tsv
    chip_publication_backfill_curated.tsv

Outputs:
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/
    chip_resolved_publication_group_queue.tsv
    chip_resolved_publication_rowwise.tsv
    chip_resolved_ap2_group_queue.tsv
    chip_manual_publication_review_queue.tsv
    chip_unresolved_publication_queue.tsv
    chip_rejected_publication_matches.tsv
    chip_pmid_download_manifest.tsv
    CHIP_RESOLVED_PUBLICATION_QUEUE_REPORT.md
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd
import re


BASE = Path("outputs/06_CHIP_AI_ASSIST/05_publication_backfill_curated")
IN_ROWWISE = BASE / "chip_rowwise_evidence_publication_enriched.tsv"
IN_GROUP = BASE / "chip_group_publication_enriched_inventory.tsv"
IN_CURATED = BASE / "chip_publication_backfill_curated.tsv"

OUT = Path("outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue")
OUT.mkdir(parents=True, exist_ok=True)


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def is_true(x) -> bool:
    return clean(x).lower() in {"true", "1", "yes"}


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def join_unique(vals, max_len=1500):
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    return "; ".join(xs)[:max_len]


def main():
    for p in [IN_ROWWISE, IN_GROUP, IN_CURATED]:
        if not p.exists():
            raise SystemExit(f"Missing input: {p}")

    rowwise = pd.read_csv(IN_ROWWISE, sep="\t", dtype=str).fillna("")
    group = pd.read_csv(IN_GROUP, sep="\t", dtype=str).fillna("")
    curated = pd.read_csv(IN_CURATED, sep="\t", dtype=str).fillna("")

    # Ensure expected fields.
    for c in [
        "bioproject", "resolved_paper_link_pmid", "publication_backfill_status",
        "is_accepted_for_intermediate", "needs_manual_publication_review",
        "is_rejected_publication_match", "is_unresolved_publication",
        "targets", "target_types", "n_rows", "n_ap2_rows", "top_candidate_title",
        "resolution_confidence", "top_candidate_routes", "publication_qc_note"
    ]:
        if c not in curated.columns:
            curated[c] = ""

    # Derive AP2 group flag.
    curated["n_ap2_rows_num"] = pd.to_numeric(curated["n_ap2_rows"], errors="coerce").fillna(0).astype(int)
    curated["is_ap2_group"] = curated["n_ap2_rows_num"] > 0

    # Accepted groups for intermediate ChIP AI queue.
    accepted = curated[curated["is_accepted_for_intermediate"].map(is_true)].copy()

    # Add queue action.
    accepted["n_rows_num"] = pd.to_numeric(accepted["n_rows"], errors="coerce").fillna(0).astype(int)

    def action(row):
        n = int(row["n_rows_num"])
        if n > 100:
            return "run_chip_ai_chunked"
        return "run_chip_ai"

    def priority(row):
        score = 0
        if bool(row["is_ap2_group"]):
            score += 50
        if clean(row["resolution_confidence"]) in {"existing_or_very_high", "high"}:
            score += 20
        if "tf_or_chromatin_factor" in clean(row["target_types"]):
            score += 15
        if "histone_modification" in clean(row["target_types"]):
            score += 5
        score += min(int(row["n_rows_num"]), 100) / 10.0
        return round(score, 1)

    accepted["recommended_action"] = accepted.apply(action, axis=1)
    accepted["priority"] = accepted.apply(priority, axis=1)
    accepted["curation_scope"] = accepted["is_ap2_group"].map(lambda x: "AP2_or_factor_priority" if x else "resolved_non_ap2_chip")

    accepted = accepted.sort_values(["is_ap2_group", "priority", "n_rows_num"], ascending=[False, False, False])

    # Rowwise accepted table.
    accepted_bps = set(accepted["bioproject"].map(clean))
    rowwise_resolved = rowwise[rowwise["bioproject"].map(clean).isin(accepted_bps)].copy()

    # AP2 accepted.
    ap2 = accepted[accepted["is_ap2_group"]].copy()

    # Manual/unresolved/rejected tables.
    manual = curated[curated["needs_manual_publication_review"].map(is_true)].copy()
    unresolved = curated[curated["is_unresolved_publication"].map(is_true)].copy()
    rejected = curated[curated["is_rejected_publication_match"].map(is_true)].copy()

    # PMID download manifest: accepted only for now.
    pmid_rows = []
    for _, r in accepted.iterrows():
        pmid = clean(r["resolved_paper_link_pmid"])
        if not is_pmid(pmid):
            continue
        pmid_rows.append({
            "pmid": pmid,
            "bioproject": clean(r["bioproject"]),
            "is_ap2_group": bool(r["is_ap2_group"]),
            "n_rows": clean(r["n_rows"]),
            "targets": clean(r["targets"]),
            "target_types": clean(r["target_types"]),
            "resolution_confidence": clean(r["resolution_confidence"]),
            "publication_backfill_status": clean(r["publication_backfill_status"]),
            "title": clean(r["top_candidate_title"]),
            "download_priority": "high_ap2" if bool(r["is_ap2_group"]) else "standard_resolved_chip",
        })

    pmid_manifest = pd.DataFrame(pmid_rows)
    if not pmid_manifest.empty:
        # Multiple BioProjects may share a PMID. Keep one row per PMID but preserve all BioProjects/targets.
        pmid_manifest = (
            pmid_manifest.groupby("pmid", dropna=False)
            .agg(
                bioprojects=("bioproject", join_unique),
                n_bioprojects=("bioproject", "nunique"),
                is_ap2_group=("is_ap2_group", "max"),
                total_rows=("n_rows", lambda s: sum(pd.to_numeric(s, errors="coerce").fillna(0).astype(int))),
                targets=("targets", join_unique),
                target_types=("target_types", join_unique),
                resolution_confidences=("resolution_confidence", join_unique),
                publication_backfill_statuses=("publication_backfill_status", join_unique),
                title=("title", "first"),
                download_priority=("download_priority", lambda s: "high_ap2" if "high_ap2" in set(s) else "standard_resolved_chip"),
            )
            .reset_index()
            .sort_values(["download_priority", "total_rows"], ascending=[True, False])
        )

    # Write files.
    group_queue_path = OUT / "chip_resolved_publication_group_queue.tsv"
    rowwise_path = OUT / "chip_resolved_publication_rowwise.tsv"
    ap2_path = OUT / "chip_resolved_ap2_group_queue.tsv"
    manual_path = OUT / "chip_manual_publication_review_queue.tsv"
    unresolved_path = OUT / "chip_unresolved_publication_queue.tsv"
    rejected_path = OUT / "chip_rejected_publication_matches.tsv"
    pmid_path = OUT / "chip_pmid_download_manifest.tsv"

    accepted.to_csv(group_queue_path, sep="\t", index=False)
    rowwise_resolved.to_csv(rowwise_path, sep="\t", index=False)
    ap2.to_csv(ap2_path, sep="\t", index=False)
    manual.to_csv(manual_path, sep="\t", index=False)
    unresolved.to_csv(unresolved_path, sep="\t", index=False)
    rejected.to_csv(rejected_path, sep="\t", index=False)
    pmid_manifest.to_csv(pmid_path, sep="\t", index=False)

    # Report.
    report = []
    report.append("# ChIP Resolved Publication Queue Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- accepted BioProjects for intermediate ChIP queue: {len(accepted)}")
    report.append(f"- accepted AP2/factor-priority BioProjects: {len(ap2)}")
    report.append(f"- rowwise ChIP rows in accepted queue: {len(rowwise_resolved)}")
    report.append(f"- manual publication-review groups: {len(manual)}")
    report.append(f"- unresolved publication groups: {len(unresolved)}")
    report.append(f"- rejected publication matches: {len(rejected)}")
    report.append(f"- unique PMIDs for paper download: {len(pmid_manifest)}")
    report.append("")
    report.append("## Recommended actions in accepted queue")
    report.append("")
    if accepted.empty:
        report.append("- none")
    else:
        for k, v in accepted["recommended_action"].value_counts().items():
            report.append(f"- {k}: {v}")

    report.append("")
    report.append("## AP2/factor-priority accepted queue")
    report.append("")
    if ap2.empty:
        report.append("- none")
    else:
        for _, r in ap2.iterrows():
            report.append(
                f"- {r['bioproject']} -> PMID {r['resolved_paper_link_pmid']}: "
                f"{r['n_rows']} rows; targets={str(r['targets'])[:180]}; "
                f"action={r['recommended_action']}; priority={r['priority']}; "
                f"title={str(r['top_candidate_title'])[:180]}"
            )

    report.append("")
    report.append("## Manual publication-review groups")
    report.append("")
    if manual.empty:
        report.append("- none")
    else:
        for _, r in manual.iterrows():
            report.append(
                f"- {r['bioproject']} candidate PMID {r.get('resolved_paper_link_pmid','')}: "
                f"{r.get('targets','')[:160]}; reason={r.get('publication_qc_note','')[:180]}"
            )

    report.append("")
    report.append("## Rejected publication matches")
    report.append("")
    if rejected.empty:
        report.append("- none")
    else:
        for _, r in rejected.iterrows():
            report.append(
                f"- {r['bioproject']}: {r.get('top_candidate_pmid','')} rejected; "
                f"{r.get('publication_qc_note','')[:220]}"
            )

    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [
        group_queue_path,
        rowwise_path,
        ap2_path,
        manual_path,
        unresolved_path,
        rejected_path,
        pmid_path,
    ]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_RESOLVED_PUBLICATION_QUEUE_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", group_queue_path)
    print("Wrote:", rowwise_path)
    print("Wrote:", ap2_path)
    print("Wrote:", manual_path)
    print("Wrote:", unresolved_path)
    print("Wrote:", rejected_path)
    print("Wrote:", pmid_path)
    print("Wrote:", report_path)
    print()
    print("Summary:")
    print(pd.DataFrame([{
        "accepted_groups": len(accepted),
        "accepted_ap2_groups": len(ap2),
        "accepted_rowwise_rows": len(rowwise_resolved),
        "manual_review_groups": len(manual),
        "unresolved_groups": len(unresolved),
        "rejected_groups": len(rejected),
        "unique_pmids_for_download": len(pmid_manifest),
    }]).to_string(index=False))
    print()
    print("Accepted AP2 queue:")
    show = [
        "bioproject", "n_rows", "n_ap2_rows", "targets",
        "resolved_paper_link_pmid", "recommended_action", "priority",
        "top_candidate_title"
    ]
    show = [c for c in show if c in ap2.columns]
    print(ap2[show].to_string(index=False))


if __name__ == "__main__":
    main()
