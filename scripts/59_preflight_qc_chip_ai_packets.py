#!/usr/bin/env python3
"""
Preflight QC for ChIP AI packets before API calls.

Checks:
  - packet queue exists
  - each packet JSON exists and parses
  - each rowwise sidecar table exists
  - PDF path exists
  - table row count matches queue n_rows
  - source_row_id is unique and nonblank
  - required ChIP columns are present
  - one and only one large/chunked candidate is expected
  - curator-facing fields are preserved

Writes:
  outputs/06_CHIP_AI_ASSIST/10_preflight_qc/
    chip_ai_packet_preflight_qc.tsv
    chip_ai_packet_preflight_problem_rows.tsv
    CHIP_AI_PACKET_PREFLIGHT_QC_REPORT.md
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import pandas as pd


IN_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/10_preflight_qc")
OUT.mkdir(parents=True, exist_ok=True)


REQUIRED_QUEUE_COLS = [
    "packet_id",
    "pmid",
    "bioproject",
    "n_rows",
    "pdf_path",
    "packet_json",
    "packet_table",
    "assay_class",
    "assay_aware_recommended_action",
    "assay_aware_curator_priority",
]

REQUIRED_TABLE_COLS = [
    "source_row_id",
    "Run",
    "BioSample",
    "PMID",
    "BioProject",
    "Target",
    "target_clean",
    "target_type",
    "chip_role",
    "background_sample",
    "assigned_control1",
    "assigned_control2",
    "stage_combined",
    "strain_context",
    "condition_context",
    "public_metadata_evidence_compact",
]


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def add_issue(issues, packet_id, severity, check, message):
    issues.append({
        "packet_id": packet_id,
        "severity": severity,
        "check": check,
        "message": message,
    })


def main():
    if not IN_QUEUE.exists():
        raise SystemExit(f"Missing queue: {IN_QUEUE}")

    q = pd.read_csv(IN_QUEUE, sep="\t", dtype=str).fillna("")

    issues = []
    rows = []

    # Queue-level column checks.
    for c in REQUIRED_QUEUE_COLS:
        if c not in q.columns:
            add_issue(issues, "<queue>", "FAIL", "missing_queue_column", c)

    if issues:
        problems = pd.DataFrame(issues)
        problems.to_csv(OUT / "chip_ai_packet_preflight_problem_rows.tsv", sep="\t", index=False)
        raise SystemExit("Queue missing required columns; see problem rows.")

    for _, r in q.iterrows():
        packet_id = clean(r["packet_id"])
        packet_json = Path(clean(r["packet_json"]))
        packet_table = Path(clean(r["packet_table"]))
        pdf_path = Path(clean(r["pdf_path"]))
        expected_n = int(float(clean(r["n_rows"]) or 0))

        status = {
            "packet_id": packet_id,
            "pmid": clean(r["pmid"]),
            "bioproject": clean(r["bioproject"]),
            "expected_n_rows": expected_n,
            "actual_n_rows": "",
            "packet_json_exists": packet_json.exists(),
            "packet_table_exists": packet_table.exists(),
            "pdf_exists": pdf_path.exists(),
            "source_row_id_unique": "",
            "source_row_id_nonblank": "",
            "n_missing_required_table_cols": "",
            "n_blank_target_rows": "",
            "n_background_control_rows": "",
            "n_chip_ip_rows": "",
            "recommended_action": clean(r["assay_aware_recommended_action"]),
            "curator_priority": clean(r["assay_aware_curator_priority"]),
            "preflight_status": "PASS",
        }

        if not packet_json.exists():
            add_issue(issues, packet_id, "FAIL", "missing_packet_json", str(packet_json))
            status["preflight_status"] = "FAIL"
        else:
            try:
                obj = json.loads(packet_json.read_text())
                if obj.get("packet_id") != packet_id:
                    add_issue(
                        issues, packet_id, "FAIL", "packet_id_mismatch_json",
                        f"queue={packet_id}; json={obj.get('packet_id')}"
                    )
                    status["preflight_status"] = "FAIL"

                sidecar = clean(obj.get("sidecar_rowwise_evidence_table", ""))
                if sidecar and Path(sidecar) != packet_table:
                    add_issue(
                        issues, packet_id, "WARN", "sidecar_path_differs_from_queue",
                        f"json={sidecar}; queue={packet_table}"
                    )
            except Exception as e:
                add_issue(issues, packet_id, "FAIL", "packet_json_parse_error", str(e))
                status["preflight_status"] = "FAIL"

        if not packet_table.exists():
            add_issue(issues, packet_id, "FAIL", "missing_packet_table", str(packet_table))
            status["preflight_status"] = "FAIL"
        else:
            try:
                t = pd.read_csv(packet_table, sep="\t", dtype=str).fillna("")
                actual_n = len(t)
                status["actual_n_rows"] = actual_n

                if actual_n != expected_n:
                    add_issue(
                        issues, packet_id, "FAIL", "n_rows_mismatch",
                        f"queue={expected_n}; table={actual_n}"
                    )
                    status["preflight_status"] = "FAIL"

                missing_cols = [c for c in REQUIRED_TABLE_COLS if c not in t.columns]
                status["n_missing_required_table_cols"] = len(missing_cols)
                if missing_cols:
                    add_issue(
                        issues, packet_id, "FAIL", "missing_required_table_columns",
                        ";".join(missing_cols)
                    )
                    status["preflight_status"] = "FAIL"

                if "source_row_id" in t.columns:
                    source_ids = t["source_row_id"].map(clean)
                    nonblank = bool((source_ids != "").all())
                    unique = bool(source_ids.is_unique)
                    status["source_row_id_nonblank"] = nonblank
                    status["source_row_id_unique"] = unique

                    if not nonblank:
                        add_issue(issues, packet_id, "FAIL", "blank_source_row_id", "source_row_id contains blanks")
                        status["preflight_status"] = "FAIL"
                    if not unique:
                        add_issue(issues, packet_id, "FAIL", "duplicate_source_row_id", "source_row_id not unique")
                        status["preflight_status"] = "FAIL"

                if "target_clean" in t.columns:
                    status["n_blank_target_rows"] = int((t["target_clean"].map(clean) == "").sum())

                if "chip_role" in t.columns:
                    status["n_background_control_rows"] = int((t["chip_role"].map(clean) == "background_control").sum())
                    status["n_chip_ip_rows"] = int((t["chip_role"].map(clean) == "chip_ip").sum())

                    if int(status["n_chip_ip_rows"]) == 0:
                        add_issue(issues, packet_id, "WARN", "no_chip_ip_rows", "No chip_ip rows detected.")
                    if int(status["n_background_control_rows"]) == 0:
                        add_issue(issues, packet_id, "REVIEW", "no_background_control_rows", "No background_control rows detected; AI/curator should check controls.")

            except Exception as e:
                add_issue(issues, packet_id, "FAIL", "packet_table_read_error", str(e))
                status["preflight_status"] = "FAIL"

        if not pdf_path.exists():
            add_issue(issues, packet_id, "FAIL", "missing_pdf", str(pdf_path))
            status["preflight_status"] = "FAIL"

        rows.append(status)

    qc = pd.DataFrame(rows)
    problems = pd.DataFrame(issues)

    # Overall sanity check: one chunked candidate expected from current queue.
    n_chunked = int((qc["recommended_action"] == "run_chip_ai_chunked").sum())
    if n_chunked != 1:
        add_issue(
            issues, "<queue>", "WARN", "unexpected_chunked_candidate_count",
            f"Expected 1 chunked candidate based on current queue, observed {n_chunked}"
        )
        problems = pd.DataFrame(issues)

    qc_path = OUT / "chip_ai_packet_preflight_qc.tsv"
    problem_path = OUT / "chip_ai_packet_preflight_problem_rows.tsv"
    report_path = OUT / "CHIP_AI_PACKET_PREFLIGHT_QC_REPORT.md"

    qc.to_csv(qc_path, sep="\t", index=False)
    problems.to_csv(problem_path, sep="\t", index=False)

    n_fail_packets = int((qc["preflight_status"] == "FAIL").sum())
    n_pass_packets = int((qc["preflight_status"] == "PASS").sum())

    report = []
    report.append("# ChIP AI Packet Preflight QC Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- packets checked: {len(qc)}")
    report.append(f"- PASS packets: {n_pass_packets}")
    report.append(f"- FAIL packets: {n_fail_packets}")
    report.append(f"- problem rows / flags: {len(problems)}")
    report.append(f"- chunked candidates: {n_chunked}")
    report.append("")
    report.append("## Issue counts")
    report.append("")
    if problems.empty:
        report.append("- none")
    else:
        for (sev, check), n in problems.groupby(["severity", "check"]).size().items():
            report.append(f"- {sev} / {check}: {n}")
    report.append("")
    report.append("## Files written")
    report.append("")
    report.append(f"- `{qc_path}`")
    report.append(f"- `{problem_path}`")

    report_path.write_text("\n".join(report))

    print("Wrote:", qc_path)
    print("Wrote:", problem_path)
    print("Wrote:", report_path)
    print()
    print("Summary:")
    print(pd.DataFrame([{
        "packets_checked": len(qc),
        "pass_packets": n_pass_packets,
        "fail_packets": n_fail_packets,
        "problem_rows": len(problems),
        "chunked_candidates": n_chunked,
    }]).to_string(index=False))
    print()
    print("Issue counts:")
    if problems.empty:
        print("None")
    else:
        print(problems.groupby(["severity", "check"]).size().reset_index(name="n").to_string(index=False))


if __name__ == "__main__":
    main()
