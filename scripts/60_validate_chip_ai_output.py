#!/usr/bin/env python3
"""
Validate one ChIP AI-curation output against its packet table.

Checks:
  - AI JSON parses
  - packet_id matches
  - rowwise_suggestions covers every source_row_id exactly once
  - sample_map partitions every source_row_id exactly once
  - rowwise Run values match packet table
  - AI sample roles match deterministic sample_role_prelim
  - target_ip rows with matched background runs have non-empty suggested background
  - analysis_readiness has ChIP peak-calling status

Inputs:
  --packet-id
  --ai-dir
  --queue

Outputs:
  outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation/
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse
import json
import pandas as pd


DEFAULT_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
DEFAULT_AI_DIR = Path("outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_actual")
DEFAULT_OUT = Path("outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation")


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def canon_role(x: str) -> str:
    x = clean(x).lower()
    x = x.replace("-", "_").replace(" ", "_")
    if x in {"igg", "ig_g"}:
        return "igg"
    if x in {"input", "input_dna"}:
        return "input"
    if x in {"target_ip", "ip", "chip_ip", "chip"}:
        return "target_ip"
    if x in {"untagged", "untagged_control"}:
        return "untagged_control"
    if x in {"mock"}:
        return "mock"
    if x in {"control", "control_sample", "background_control"}:
        return "control_sample"
    if x in {"unknown", "not_applicable", "na", "none", ""}:
        return ""
    return x


def bad_bg_value(x: str) -> bool:
    x = clean(x).lower()
    return x in {"", "unknown", "not_applicable", "none", "na", "n/a"}


def add_issue(issues, severity, check, source_row_id="", message=""):
    issues.append({
        "severity": severity,
        "check": check,
        "source_row_id": source_row_id,
        "message": message,
    })


def find_latest_ai_json(ai_dir: Path, packet_id: str) -> Path:
    packet_dir = ai_dir / packet_id
    hits = sorted(packet_dir.glob(f"{packet_id}.ai_curation.*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not hits:
        raise SystemExit(f"No AI JSON found in {packet_dir}")
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--ai-json", default="")
    ap.add_argument("--ai-dir", default=str(DEFAULT_AI_DIR))
    ap.add_argument("--queue", default=str(DEFAULT_QUEUE))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    packet_id = args.packet_id
    ai_dir = Path(args.ai_dir)
    queue_path = Path(args.queue)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ai_json_path = Path(args.ai_json) if args.ai_json else find_latest_ai_json(ai_dir, packet_id)

    if not queue_path.exists():
        raise SystemExit(f"Missing queue: {queue_path}")

    q = pd.read_csv(queue_path, sep="\t", dtype=str).fillna("")
    qq = q[q["packet_id"] == packet_id]
    if qq.empty:
        raise SystemExit(f"Packet not found in queue: {packet_id}")

    packet_table_path = Path(clean(qq.iloc[0]["packet_table"]))
    if not packet_table_path.exists():
        raise SystemExit(f"Missing packet table: {packet_table_path}")

    table = pd.read_csv(packet_table_path, sep="\t", dtype=str).fillna("")
    obj = json.loads(ai_json_path.read_text())

    issues = []

    if obj.get("packet_id") != packet_id:
        add_issue(issues, "FAIL", "packet_id_mismatch", message=f"expected={packet_id}; observed={obj.get('packet_id')}")

    expected_ids = list(table["source_row_id"].map(clean))
    expected_set = set(expected_ids)
    expected_run = dict(zip(table["source_row_id"].map(clean), table["Run"].map(clean))) if "Run" in table.columns else {}
    expected_role = dict(zip(table["source_row_id"].map(clean), table["sample_role_prelim"].map(canon_role))) if "sample_role_prelim" in table.columns else {}
    expected_bg_runs = dict(zip(table["source_row_id"].map(clean), table["matched_background_run_ids_prelim"].map(clean))) if "matched_background_run_ids_prelim" in table.columns else {}

    # Rowwise suggestions coverage.
    rowwise = obj.get("rowwise_suggestions", [])
    rw_ids = [clean(r.get("source_row_id", "")) for r in rowwise]
    rw_set = set(rw_ids)
    rw_counts = Counter(rw_ids)

    if len(rowwise) != len(expected_ids):
        add_issue(issues, "FAIL", "rowwise_count_mismatch", message=f"expected={len(expected_ids)}; observed={len(rowwise)}")

    for sid in sorted(expected_set - rw_set):
        add_issue(issues, "FAIL", "rowwise_missing_source_row_id", sid, "Expected row missing from rowwise_suggestions")

    for sid in sorted(rw_set - expected_set):
        add_issue(issues, "FAIL", "rowwise_extra_source_row_id", sid, "AI produced row not in packet table")

    for sid, n in sorted(rw_counts.items()):
        if sid and n > 1:
            add_issue(issues, "FAIL", "rowwise_duplicate_source_row_id", sid, f"appears {n} times")

    # Rowwise role/run consistency.
    sample_class_ids_from_rowwise = set()
    for r in rowwise:
        sid = clean(r.get("source_row_id", ""))
        if not sid or sid not in expected_set:
            continue

        ai_run = clean(r.get("Run", ""))
        if sid in expected_run and ai_run and ai_run != expected_run[sid]:
            add_issue(issues, "FAIL", "rowwise_run_mismatch", sid, f"expected={expected_run[sid]}; observed={ai_run}")

        ai_role = canon_role(r.get("suggested_sample_role", ""))
        exp_role = expected_role.get(sid, "")

        if exp_role and ai_role and ai_role != exp_role:
            add_issue(issues, "FAIL", "sample_role_mismatch", sid, f"expected_prelim={exp_role}; ai={ai_role}")

        if exp_role and not ai_role:
            add_issue(issues, "FAIL", "missing_suggested_sample_role", sid, f"expected_prelim={exp_role}; ai blank")

        if exp_role == "target_ip" and expected_bg_runs.get(sid, ""):
            bg = clean(r.get("suggested_comparator_or_background", ""))
            if bad_bg_value(bg):
                add_issue(
                    issues, "WARN", "target_ip_missing_ai_background",
                    sid,
                    f"target_ip has matched_background_run_ids_prelim={expected_bg_runs[sid]} but AI background={bg}"
                )

        scid = clean(r.get("sample_class_id", ""))
        if scid:
            sample_class_ids_from_rowwise.add(scid)
        else:
            add_issue(issues, "FAIL", "rowwise_missing_sample_class_id", sid, "No sample_class_id in rowwise suggestion")

    # Sample map partition.
    sample_map = obj.get("sample_map", [])
    sm_ids = []
    sm_class_ids = set()
    for sm in sample_map:
        scid = clean(sm.get("sample_class_id", ""))
        if not scid:
            add_issue(issues, "FAIL", "sample_map_blank_class_id", message=str(sm)[:200])
        sm_class_ids.add(scid)

        ids = sm.get("matched_source_row_ids", []) or []
        if isinstance(ids, str):
            ids = [ids]
        ids = [clean(x) for x in ids if clean(x)]
        sm_ids.extend(ids)

        stated_n = sm.get("n_rows_matched", "")
        try:
            stated_n_int = int(float(stated_n))
            if stated_n_int != len(ids):
                add_issue(issues, "FAIL", "sample_map_n_rows_mismatch", message=f"{scid}: n_rows_matched={stated_n}; actual_ids={len(ids)}")
        except Exception:
            add_issue(issues, "WARN", "sample_map_n_rows_not_integer", message=f"{scid}: n_rows_matched={stated_n}")

    sm_set = set(sm_ids)
    sm_counts = Counter(sm_ids)

    for sid in sorted(expected_set - sm_set):
        add_issue(issues, "FAIL", "sample_map_missing_source_row_id", sid, "Expected row missing from sample_map partition")

    for sid in sorted(sm_set - expected_set):
        add_issue(issues, "FAIL", "sample_map_extra_source_row_id", sid, "sample_map contains row not in packet table")

    for sid, n in sorted(sm_counts.items()):
        if sid and n > 1:
            add_issue(issues, "FAIL", "sample_map_duplicate_source_row_id", sid, f"appears {n} times across sample_map")

    for scid in sorted(sample_class_ids_from_rowwise - sm_class_ids):
        add_issue(issues, "FAIL", "rowwise_sample_class_not_in_sample_map", message=scid)

    # Analysis readiness.
    ar = obj.get("analysis_readiness", {}) or {}
    peak_status = clean(ar.get("chip_peak_calling_ready", ""))
    if peak_status not in {"yes", "no", "partial", "not_applicable", "unknown"}:
        add_issue(issues, "FAIL", "invalid_chip_peak_calling_ready", message=f"observed={peak_status}")

    if obj.get("assay_class_confirmed") != "chip_like_target_enrichment":
        add_issue(issues, "WARN", "assay_class_not_chip_like", message=f"observed={obj.get('assay_class_confirmed')}")

    issues_df = pd.DataFrame(issues)
    fail_n = 0 if issues_df.empty else int((issues_df["severity"] == "FAIL").sum())
    warn_n = 0 if issues_df.empty else int((issues_df["severity"] == "WARN").sum())
    review_n = 0 if issues_df.empty else int((issues_df["severity"] == "REVIEW").sum())

    status = "PASS" if fail_n == 0 else "FAIL"

    summary = pd.DataFrame([{
        "packet_id": packet_id,
        "validation_status": status,
        "ai_json": str(ai_json_path),
        "packet_table": str(packet_table_path),
        "expected_rows": len(expected_ids),
        "rowwise_suggestions": len(rowwise),
        "sample_map_entries": len(sample_map),
        "chip_peak_calling_ready": peak_status,
        "n_fail": fail_n,
        "n_warn": warn_n,
        "n_review": review_n,
        "n_issues_total": len(issues_df),
    }])

    summary_path = out_dir / f"{packet_id}.chip_ai_validation_summary.tsv"
    issues_path = out_dir / f"{packet_id}.chip_ai_validation_issues.tsv"
    report_path = out_dir / f"{packet_id}.CHIP_AI_VALIDATION_REPORT.md"

    summary.to_csv(summary_path, sep="\t", index=False)
    issues_df.to_csv(issues_path, sep="\t", index=False)

    lines = []
    lines.append("# ChIP AI Validation Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for k, v in summary.iloc[0].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Issue counts")
    lines.append("")
    if issues_df.empty:
        lines.append("- none")
    else:
        for (sev, check), n in issues_df.groupby(["severity", "check"]).size().items():
            lines.append(f"- {sev} / {check}: {n}")

    lines.append("")
    lines.append("## Files written")
    lines.append("")
    lines.append(f"- `{summary_path}`")
    lines.append(f"- `{issues_path}`")

    report_path.write_text("\n".join(lines))

    print("Wrote:", summary_path)
    print("Wrote:", issues_path)
    print("Wrote:", report_path)
    print()
    print(summary.to_string(index=False))
    print()
    print("Issue counts:")
    if issues_df.empty:
        print("None")
    else:
        print(issues_df.groupby(["severity", "check"]).size().reset_index(name="n").to_string(index=False))


if __name__ == "__main__":
    main()
