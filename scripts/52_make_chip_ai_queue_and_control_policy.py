#!/usr/bin/env python3
"""
Make ChIP AI candidate queue and improved control-policy table.

Reads:
  outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv

Writes:
  outputs/06_CHIP_AI_ASSIST/02_chip_ai_queue/
    chip_group_control_policy.tsv
    chip_ai_candidate_queue.tsv
    chip_initial_paperlinked_pilot_queue.tsv
    chip_publication_resolution_needed.tsv
    CHIP_AI_QUEUE_REPORT.md

Important:
  - ChIP AI should initially run only on paper-linked groups.
  - Missing paper_link is a publication-resolution issue, not necessarily biological failure.
  - Assigned controls are primary control evidence even when background rows are not classified as Input/IgG.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import pandas as pd


IN = Path("outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/02_chip_ai_queue")
OUT.mkdir(parents=True, exist_ok=True)


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def join_unique(vals, max_len=1200) -> str:
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    s = "; ".join(xs)
    return s[:max_len]


def bool_count(s, val=True) -> int:
    return int((s.astype(str).str.lower().isin(["true", "1", "yes"]) == val).sum())


def main():
    if not IN.exists():
        raise SystemExit(f"Missing input: {IN}")

    df = pd.read_csv(IN, sep="\t", dtype=str).fillna("")

    # Ensure numeric columns.
    for c in ["n_assigned_controls", "n_missing_assigned_controls"]:
        if c not in df.columns:
            df[c] = "0"
        df[c + "_num"] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # Required expected columns.
    for c in [
        "source_row_id", "run", "bioproject", "publication_key", "target_clean",
        "target_type", "chip_role", "stage_combined", "strain_context",
        "condition_context", "assigned_control_all", "n_assigned_controls_num",
        "n_missing_assigned_controls_num"
    ]:
        if c not in df.columns:
            df[c] = ""

    group = (
        df.groupby(["publication_key", "bioproject"], dropna=False)
        .agg(
            n_rows=("source_row_id", "count"),
            n_runs=("run", "nunique"),
            n_chip_ip_rows=("chip_role", lambda s: int((s == "chip_ip").sum())),
            n_background_control_rows=("chip_role", lambda s: int((s == "background_control").sum())),
            n_rows_with_assigned_controls=("n_assigned_controls_num", lambda s: int((s > 0).sum())),
            n_rows_with_missing_assigned_controls=("n_missing_assigned_controls_num", lambda s: int((s > 0).sum())),
            n_unique_targets=("target_clean", lambda s: int(pd.Series([x for x in s if clean(x)]).nunique())),
            targets=("target_clean", join_unique),
            target_types=("target_type", join_unique),
            stages=("stage_combined", join_unique),
            strains=("strain_context", join_unique),
            conditions=("condition_context", join_unique),
            last_authors=("last_author", join_unique if "last_author" in df.columns else lambda s: ""),
            example_runs=("run", lambda s: "; ".join(list(s.head(10)))),
        )
        .reset_index()
    )

    group["has_publication_key"] = group["publication_key"].astype(str).str.strip() != ""

    def control_status(r):
        n_chip = int(r["n_chip_ip_rows"])
        n_bg = int(r["n_background_control_rows"])
        n_assigned = int(r["n_rows_with_assigned_controls"])
        n_missing = int(r["n_rows_with_missing_assigned_controls"])

        if n_missing > 0:
            return "assigned_control_run_missing_from_sheet"
        if n_chip == 0 and n_bg > 0:
            return "background_only_or_no_chip_ip"
        if n_assigned > 0 and n_bg > 0:
            return "assigned_controls_plus_background_rows"
        if n_assigned > 0 and n_bg == 0:
            return "assigned_controls_present_no_background_label"
        if n_assigned == 0 and n_bg > 0:
            return "background_rows_present_no_assigned_controls"
        if n_assigned == 0 and n_bg == 0 and n_chip > 0:
            return "no_control_evidence"
        return "unclear"

    group["chip_control_policy_status"] = group.apply(control_status, axis=1)

    def action(r):
        has_pub = bool(r["has_publication_key"])
        n_rows = int(r["n_rows"])
        n_targets = int(r["n_unique_targets"])
        n_chip = int(r["n_chip_ip_rows"])
        status = r["chip_control_policy_status"]

        if not has_pub:
            return "defer_resolve_publication"
        if n_chip == 0:
            return "defer_background_only_or_no_chip_ip"
        if n_targets == 0:
            return "defer_no_target"
        if n_rows > 100:
            return "run_chip_ai_chunked_pilot"
        if status == "assigned_control_run_missing_from_sheet":
            return "defer_control_integrity_issue"
        # Paper-linked groups with no obvious controls may still be useful for AI
        # because AI can inspect paper context and flag missing controls.
        return "run_chip_ai_pilot"

    group["recommended_action"] = group.apply(action, axis=1)

    def priority(r):
        score = 0
        if r["recommended_action"] == "run_chip_ai_pilot":
            score += 50
        if r["recommended_action"] == "run_chip_ai_chunked_pilot":
            score += 45
        if r["has_publication_key"]:
            score += 20
        if int(r["n_rows_with_assigned_controls"]) > 0:
            score += 10
        if int(r["n_background_control_rows"]) > 0:
            score += 5
        if "tf_or_chromatin_factor" in r["target_types"]:
            score += 5
        if "histone_modification" in r["target_types"]:
            score += 3
        score += min(int(r["n_rows"]), 50) / 10.0
        return round(score, 1)

    group["priority"] = group.apply(priority, axis=1)

    # Sort for actionability.
    group = group.sort_values(
        ["recommended_action", "priority", "n_rows"],
        ascending=[True, False, False]
    )

    control_policy_path = OUT / "chip_group_control_policy.tsv"
    group.to_csv(control_policy_path, sep="\t", index=False)

    candidate = group[group["recommended_action"].isin(["run_chip_ai_pilot", "run_chip_ai_chunked_pilot"])].copy()
    candidate = candidate.sort_values(["priority", "n_rows"], ascending=[False, False])

    candidate_path = OUT / "chip_ai_candidate_queue.tsv"
    candidate.to_csv(candidate_path, sep="\t", index=False)

    pilot = candidate.head(10).copy()
    pilot_path = OUT / "chip_initial_paperlinked_pilot_queue.tsv"
    pilot.to_csv(pilot_path, sep="\t", index=False)

    pub_needed = group[group["recommended_action"] == "defer_resolve_publication"].copy()
    pub_needed = pub_needed.sort_values(["n_rows", "n_unique_targets"], ascending=[False, False])

    pub_needed_path = OUT / "chip_publication_resolution_needed.tsv"
    pub_needed.to_csv(pub_needed_path, sep="\t", index=False)

    # Report.
    report = []
    report.append("# ChIP AI Queue and Control Policy Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append(f"Input: `{IN}`")
    report.append("")
    report.append("## Group counts")
    report.append("")
    report.append(f"- total ChIP groups: {len(group)}")
    report.append(f"- paper-linked groups: {int(group['has_publication_key'].sum())}")
    report.append(f"- groups needing publication resolution: {len(pub_needed)}")
    report.append(f"- AI candidate groups: {len(candidate)}")
    report.append(f"- initial pilot groups: {len(pilot)}")
    report.append("")
    report.append("## Recommended actions")
    report.append("")
    for k, v in group["recommended_action"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Improved control-policy status")
    report.append("")
    for k, v in group["chip_control_policy_status"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Initial paper-linked ChIP AI pilot queue")
    report.append("")
    if pilot.empty:
        report.append("- none")
    else:
        for _, r in pilot.iterrows():
            report.append(
                f"- PMID/paper_link {r['publication_key']} / {r['bioproject']}: "
                f"{r['n_rows']} rows; targets={r['targets'][:180]}; "
                f"control_status={r['chip_control_policy_status']}; priority={r['priority']}"
            )
    report.append("")
    report.append("## Largest groups needing publication resolution")
    report.append("")
    for _, r in pub_needed.head(25).iterrows():
        report.append(
            f"- {r['bioproject']}: {r['n_rows']} rows; "
            f"targets={r['targets'][:180]}; "
            f"control_status={r['chip_control_policy_status']}"
        )
    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [control_policy_path, candidate_path, pilot_path, pub_needed_path]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_AI_QUEUE_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", control_policy_path)
    print("Wrote:", candidate_path)
    print("Wrote:", pilot_path)
    print("Wrote:", pub_needed_path)
    print("Wrote:", report_path)
    print()
    print("Recommended actions:")
    print(group["recommended_action"].value_counts().to_string())
    print()
    print("Control-policy status:")
    print(group["chip_control_policy_status"].value_counts().to_string())
    print()
    print("Initial pilot queue:")
    cols = [
        "publication_key", "bioproject", "n_rows", "n_chip_ip_rows",
        "n_background_control_rows", "n_rows_with_assigned_controls",
        "n_unique_targets", "targets", "chip_control_policy_status",
        "recommended_action", "priority"
    ]
    print(pilot[cols].to_string(index=False))


if __name__ == "__main__":
    main()
