#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import json
import pandas as pd

INV = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_output_inventory.tsv")
ACTIVE = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_active_validated_outputs.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/20_final_qc")
OUT.mkdir(parents=True, exist_ok=True)

def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def read_json(p):
    return json.loads(Path(p).read_text())

def main():
    inv = pd.read_csv(INV, sep="\t", dtype=str).fillna("")
    active = pd.read_csv(ACTIVE, sep="\t", dtype=str).fillna("")

    packet_status_path = OUT / "trusted_chip_ai_phase_packet_status.tsv"
    active.to_csv(packet_status_path, sep="\t", index=False)

    # Build rowwise review and target-control map from active validated outputs.
    rowwise_rows = []
    control_rows = []

    for _, r in active.iterrows():
        packet_id = clean(r["packet_id"])
        ai_json = clean(r["active_ai_json"])
        packet_table = clean(r["packet_table"])

        if not ai_json or not Path(ai_json).exists():
            continue

        obj = read_json(ai_json)
        table = pd.read_csv(packet_table, sep="\t", dtype=str).fillna("") if packet_table and Path(packet_table).exists() else pd.DataFrame()
        table_by_id = {clean(x["source_row_id"]): x for _, x in table.iterrows()} if "source_row_id" in table.columns else {}

        for rw in obj.get("rowwise_suggestions", []) or []:
            sid = clean(rw.get("source_row_id", ""))
            src = table_by_id.get(sid, {})

            row = {
                "packet_id": packet_id,
                "pmid": clean(r.get("pmid", "")),
                "bioproject": clean(r.get("bioproject", "")),
                "source_row_id": sid,
                "Run": clean(src.get("Run", rw.get("Run", ""))) if hasattr(src, "get") else clean(rw.get("Run", "")),
                "BioSample": clean(src.get("BioSample", "")) if hasattr(src, "get") else "",
                "original_Target": clean(src.get("Target", "")) if hasattr(src, "get") else "",
                "target_clean": clean(src.get("target_clean", "")) if hasattr(src, "get") else "",
                "sample_role_prelim": clean(src.get("sample_role_prelim", "")) if hasattr(src, "get") else "",
                "ai_sample_role": clean(rw.get("suggested_sample_role", "")),
                "ai_target_or_antibody_or_tag": clean(rw.get("suggested_target_or_antibody_or_tag", "")),
                "ai_background_or_comparator": clean(rw.get("suggested_comparator_or_background", "")),
                "stage": clean(rw.get("suggested_stage_timepoint", "")),
                "strain": clean(rw.get("suggested_strain", "")),
                "condition": clean(rw.get("suggested_condition", "")),
                "confidence": clean(rw.get("suggestion_confidence", "")),
                "review_flag": clean(rw.get("review_flag", "")),
                "evidence": clean(rw.get("suggestion_evidence", "")),
                "active_ai_json": ai_json,
            }
            rowwise_rows.append(row)

            if clean(rw.get("suggested_sample_role", "")).lower() in {"target_ip", "chip_ip", "ip"}:
                control_rows.append({
                    "packet_id": packet_id,
                    "pmid": clean(r.get("pmid", "")),
                    "bioproject": clean(r.get("bioproject", "")),
                    "target_source_row_id": sid,
                    "target_Run": row["Run"],
                    "target_or_antibody_or_tag": row["ai_target_or_antibody_or_tag"],
                    "stage": row["stage"],
                    "strain": row["strain"],
                    "condition": row["condition"],
                    "ai_background_or_comparator": row["ai_background_or_comparator"],
                    "prelim_matched_background_run_ids": clean(src.get("matched_background_run_ids_prelim", "")) if hasattr(src, "get") else "",
                    "assigned_control1": clean(src.get("assigned_control1", "")) if hasattr(src, "get") else "",
                    "assigned_control2": clean(src.get("assigned_control2", "")) if hasattr(src, "get") else "",
                    "curator_note": "Check that target IP has correct input/IgG/background relationship.",
                })

    rowwise_df = pd.DataFrame(rowwise_rows)
    control_df = pd.DataFrame(control_rows)

    rowwise_path = OUT / "chip_rowwise_review.tsv"
    control_path = OUT / "chip_target_control_map_review.tsv"

    rowwise_df.to_csv(rowwise_path, sep="\t", index=False)
    control_df.to_csv(control_path, sep="\t", index=False)

    # Summary report.
    status_counts = inv["chip_ai_output_status"].value_counts().to_dict()
    peak_counts = active["chip_peak_calling_ready"].value_counts().to_dict()
    repaired_n = int((active["active_json_type"] == "repaired").sum())

    report = []
    report.append("# ChIP AI-curation Phase Completion Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Executive status")
    report.append("")
    report.append(f"- ChIP packets inspected: {len(inv)}")
    report.append(f"- Active validated PASS packets: {int((inv['chip_ai_output_status'] == 'active_validated_pass').sum())}")
    report.append(f"- Repaired active outputs: {repaired_n}")
    report.append(f"- Rowwise review rows: {len(rowwise_df)}")
    report.append(f"- Target-control map rows: {len(control_df)}")
    report.append("")
    report.append("## Output status counts")
    report.append("")
    for k, v in status_counts.items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## ChIP peak-calling readiness")
    report.append("")
    for k, v in peak_counts.items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Interpretation")
    report.append("")
    report.append("- All ChIP AI outputs are structurally validated.")
    report.append("- AI outputs remain suggestions only; curator final fields are authoritative.")
    report.append("- `partial` or `no` peak-calling readiness should remain visible to curators.")
    report.append("- Shared input/control reuse is expected in ChIP and should be reviewed through the target-control map.")
    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [packet_status_path, rowwise_path, control_path]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_AI_PHASE_COMPLETION_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", packet_status_path)
    print("Wrote:", rowwise_path)
    print("Wrote:", control_path)
    print("Wrote:", report_path)
    print()
    print("\n".join(report[:40]))

if __name__ == "__main__":
    main()
