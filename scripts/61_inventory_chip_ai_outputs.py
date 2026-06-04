#!/usr/bin/env python3
"""
Inventory ChIP AI outputs across pilot/batch directories.

Purpose:
  - Find latest raw and repaired AI JSON per packet.
  - Prefer repaired JSON as active when present.
  - Merge validation summaries.
  - Produce a clean active-output inventory for downstream QC/housekeeping/Excel.

Inputs:
  outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv
  outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_actual/
  outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_batch_actual/
  outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation/

Outputs:
  outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/
    chip_ai_output_inventory.tsv
    chip_ai_active_validated_outputs.tsv
    CHIP_AI_OUTPUT_INVENTORY_REPORT.md
"""

from pathlib import Path
from datetime import datetime
import pandas as pd
import re


QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
AI_DIRS = [
    Path("outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_actual"),
    Path("outputs/06_CHIP_AI_ASSIST/12_chip_ai_pilot_batch_actual"),
    Path("outputs/06_CHIP_AI_ASSIST/15_chip_ai_batch_small_actual"),
    Path("outputs/06_CHIP_AI_ASSIST/18_chip_ai_chunk_merged"),
]
VALIDATION_DIR = Path("outputs/06_CHIP_AI_ASSIST/13_chip_ai_validation")
OUT = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory")
OUT.mkdir(parents=True, exist_ok=True)


def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def latest(paths):
    paths = [p for p in paths if p.exists()]
    if not paths:
        return ""
    return str(sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[0])


def find_outputs(packet_id):
    raw_jsons = []
    repaired_jsons = []
    raw_responses = []
    prompts = []
    audits = []

    for d in AI_DIRS:
        pd_dir = d / packet_id
        if not pd_dir.exists():
            continue

        raw_jsons.extend(pd_dir.glob(f"{packet_id}.ai_curation.*.json"))
        repaired_jsons.extend(pd_dir.glob(f"{packet_id}.ai_curation_samplemap_rebuilt.*.json"))
        raw_responses.extend(pd_dir.glob(f"{packet_id}.raw_response.*.txt"))
        prompts.extend(pd_dir.glob(f"{packet_id}.prompt.*.txt"))
        audits.extend(pd_dir.glob(f"{packet_id}.audit.*.json"))

    latest_raw = latest(raw_jsons)
    latest_repaired = latest(repaired_jsons)
    active = latest_repaired if latest_repaired else latest_raw

    return {
        "latest_raw_ai_json": latest_raw,
        "latest_repaired_ai_json": latest_repaired,
        "active_ai_json": active,
        "has_raw_ai_json": bool(latest_raw),
        "has_repaired_ai_json": bool(latest_repaired),
        "active_json_type": "repaired" if latest_repaired else ("raw" if latest_raw else ""),
        "latest_raw_response": latest(raw_responses),
        "latest_prompt": latest(prompts),
        "latest_audit": latest(audits),
    }


def read_validation(packet_id):
    p = VALIDATION_DIR / f"{packet_id}.chip_ai_validation_summary.tsv"
    if not p.exists():
        return {
            "validation_status": "NO_VALIDATION",
            "validation_summary_path": "",
            "expected_rows": "",
            "rowwise_suggestions": "",
            "sample_map_entries": "",
            "chip_peak_calling_ready": "",
            "n_fail": "",
            "n_warn": "",
            "n_review": "",
            "n_issues_total": "",
        }

    df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
    if df.empty:
        return {
            "validation_status": "NO_VALIDATION_EMPTY",
            "validation_summary_path": str(p),
            "expected_rows": "",
            "rowwise_suggestions": "",
            "sample_map_entries": "",
            "chip_peak_calling_ready": "",
            "n_fail": "",
            "n_warn": "",
            "n_review": "",
            "n_issues_total": "",
        }

    r = df.iloc[0].to_dict()
    return {
        "validation_status": clean(r.get("validation_status", "")),
        "validation_summary_path": str(p),
        "expected_rows": clean(r.get("expected_rows", "")),
        "rowwise_suggestions": clean(r.get("rowwise_suggestions", "")),
        "sample_map_entries": clean(r.get("sample_map_entries", "")),
        "chip_peak_calling_ready": clean(r.get("chip_peak_calling_ready", "")),
        "n_fail": clean(r.get("n_fail", "")),
        "n_warn": clean(r.get("n_warn", "")),
        "n_review": clean(r.get("n_review", "")),
        "n_issues_total": clean(r.get("n_issues_total", "")),
    }


def main():
    if not QUEUE.exists():
        raise SystemExit(f"Missing queue: {QUEUE}")

    q = pd.read_csv(QUEUE, sep="\t", dtype=str).fillna("")

    rows = []
    for _, r in q.iterrows():
        packet_id = clean(r["packet_id"])
        out = find_outputs(packet_id)
        val = read_validation(packet_id)

        row = {
            "packet_id": packet_id,
            "pmid": clean(r.get("pmid", "")),
            "bioproject": clean(r.get("bioproject", "")),
            "n_rows": clean(r.get("n_rows", "")),
            "targets": clean(r.get("targets", "")),
            "target_types": clean(r.get("target_types", "")),
            "assay_aware_curator_priority": clean(r.get("assay_aware_curator_priority", "")),
            "assay_aware_recommended_action": clean(r.get("assay_aware_recommended_action", "")),
            "packet_json": clean(r.get("packet_json", "")),
            "packet_table": clean(r.get("packet_table", "")),
            **out,
            **val,
        }
        rows.append(row)

    inv = pd.DataFrame(rows)

    def action_status(row):
        if not row["active_ai_json"]:
            return "not_run"
        if row["validation_status"] == "PASS":
            return "active_validated_pass"
        if row["validation_status"].startswith("FAIL"):
            return "ran_validation_failed"
        if row["validation_status"].startswith("NO_VALIDATION"):
            return "ran_needs_validation"
        return "ran_check_status"

    inv["chip_ai_output_status"] = inv.apply(action_status, axis=1)

    inv_path = OUT / "chip_ai_output_inventory.tsv"
    active_path = OUT / "chip_ai_active_validated_outputs.tsv"

    inv.to_csv(inv_path, sep="\t", index=False)
    active = inv[inv["chip_ai_output_status"] == "active_validated_pass"].copy()
    active.to_csv(active_path, sep="\t", index=False)

    report = []
    report.append("# ChIP AI Output Inventory Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- packets in queue: {len(inv)}")
    report.append(f"- packets with AI output: {int((inv['active_ai_json'] != '').sum())}")
    report.append(f"- packets with repaired AI output: {int(inv['has_repaired_ai_json'].sum())}")
    report.append(f"- active validated PASS packets: {len(active)}")
    report.append("")
    report.append("## Output status counts")
    report.append("")
    for k, v in inv["chip_ai_output_status"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Active validated packets")
    report.append("")
    if active.empty:
        report.append("- none")
    else:
        for _, r in active.iterrows():
            report.append(
                f"- {r['packet_id']}: rows={r['n_rows']}; "
                f"peak_ready={r['chip_peak_calling_ready']}; "
                f"json_type={r['active_json_type']}; "
                f"targets={str(r['targets'])[:160]}"
            )
    report.append("")
    report.append("## Files written")
    report.append("")
    report.append(f"- `{inv_path}`")
    report.append(f"- `{active_path}`")

    report_path = OUT / "CHIP_AI_OUTPUT_INVENTORY_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", inv_path)
    print("Wrote:", active_path)
    print("Wrote:", report_path)
    print()
    print("Status counts:")
    print(inv["chip_ai_output_status"].value_counts().to_string())
    print()
    print("Active validated outputs:")
    if active.empty:
        print("None")
    else:
        show = [
            "packet_id", "n_rows", "validation_status", "active_json_type",
            "chip_peak_calling_ready", "n_fail", "n_warn", "n_review"
        ]
        print(active[show].to_string(index=False))


if __name__ == "__main__":
    main()
