#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import json
import pandas as pd

OUTDIR = Path("outputs/06_CHIP_AI_ASSIST/21_curator_excel")
OUTDIR.mkdir(parents=True, exist_ok=True)

FINAL = Path("outputs/06_CHIP_AI_ASSIST/20_final_qc")
ACTIVE = FINAL / "trusted_chip_ai_phase_packet_status.tsv"
ROWWISE = FINAL / "chip_rowwise_review.tsv"
TARGET_CONTROL = FINAL / "chip_target_control_map_review.tsv"
REPORT = FINAL / "CHIP_AI_PHASE_COMPLETION_REPORT.md"

def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def short_json(x, max_len=1000):
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False)[:max_len]
    return clean(x)[:max_len]

def read_ai_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}

def build_readme():
    rows = [
        {
            "section": "Purpose",
            "note": "This workbook contains AI-assisted ChIP/CUT&RUN/CUT&Tag metadata suggestions for curator review. AI suggestions are not final; curator fields/comments are authoritative."
        },
        {
            "section": "Recommended workflow",
            "note": "Start with Study_Review to understand each packet/study. Then inspect Problem_Rows. Then use Target_Control_Map_Review to verify target-IP to input/IgG/background relationships. Finally spot-check Rowwise_Review and Sample_Map_Review."
        },
        {
            "section": "Target_Control_Map_Review",
            "note": "Central ChIP sheet. Each target/IP row should be checked against its matched background/input/IgG controls. Shared input controls are expected in ChIP and are not duplicates by themselves."
        },
        {
            "section": "Peak readiness",
            "note": "yes = structurally ready; partial/no = keep visible for curator review because controls/backgrounds/roles may need interpretation."
        },
        {
            "section": "Curator fields",
            "note": "Use curator_decision, curator_corrected_value, and curator_comment columns for changes. Do not overwrite source or AI evidence columns."
        },
    ]
    return pd.DataFrame(rows)

def build_study_review(active):
    rows = []
    for _, r in active.iterrows():
        obj = read_ai_json(clean(r.get("active_ai_json", "")))
        ar = obj.get("analysis_readiness", {}) or {}

        rows.append({
            "packet_id": clean(r.get("packet_id", "")),
            "pmid": clean(r.get("pmid", "")),
            "bioproject": clean(r.get("bioproject", "")),
            "n_rows": clean(r.get("n_rows", "")),
            "targets": clean(r.get("targets", "")),
            "target_types": clean(r.get("target_types", "")),
            "validation_status": clean(r.get("validation_status", "")),
            "chip_peak_calling_ready": clean(r.get("chip_peak_calling_ready", "")),
            "active_json_type": clean(r.get("active_json_type", "")),
            "ai_review_status": clean(obj.get("ai_review_status", "")),
            "assay_class_confirmed": clean(obj.get("assay_class_confirmed", "")),
            "main_blockers": short_json(ar.get("main_blockers", "")),
            "global_warnings": short_json(obj.get("global_warnings", "")),
            "active_ai_json": clean(r.get("active_ai_json", "")),
            "curator_decision": "",
            "curator_comment": "",
        })
    return pd.DataFrame(rows)

def build_sample_map(active):
    rows = []
    for _, r in active.iterrows():
        packet_id = clean(r.get("packet_id", ""))
        obj = read_ai_json(clean(r.get("active_ai_json", "")))
        for sm in obj.get("sample_map", []) or []:
            rows.append({
                "packet_id": packet_id,
                "pmid": clean(r.get("pmid", "")),
                "bioproject": clean(r.get("bioproject", "")),
                "sample_class_id": clean(sm.get("sample_class_id", "")),
                "sample_role": clean(sm.get("sample_role", "")),
                "target_or_antibody_or_tag": clean(sm.get("target_or_antibody_or_tag", "")),
                "stage_or_timepoint": clean(sm.get("stage_or_timepoint", "")),
                "strain": clean(sm.get("strain", "")),
                "condition": clean(sm.get("condition", "")),
                "perturbation_or_treatment": clean(sm.get("perturbation_or_treatment", "")),
                "n_rows_matched": clean(sm.get("n_rows_matched", "")),
                "matched_source_row_ids": short_json(sm.get("matched_source_row_ids", "")),
                "matched_run_ids": short_json(sm.get("matched_run_ids", "")),
                "suggested_comparator_or_background_class_id": clean(sm.get("suggested_comparator_or_background_class_id", "")),
                "analysis_ready_status": clean(sm.get("analysis_ready_status", "")),
                "blocker_reason": clean(sm.get("blocker_reason", "")),
                "confidence": clean(sm.get("confidence", "")),
                "warning_flags": short_json(sm.get("warning_flags", "")),
                "evidence": clean(sm.get("evidence", "")),
                "curator_decision": "",
                "curator_corrected_value": "",
                "curator_comment": "",
            })
    return pd.DataFrame(rows)

def build_problem_rows(active, rowwise, target_control):
    problems = []

    if not active.empty:
        for _, r in active.iterrows():
            if clean(r.get("chip_peak_calling_ready", "")).lower() in {"partial", "no", "unknown"}:
                problems.append({
                    "problem_type": "packet_peak_calling_readiness",
                    "packet_id": clean(r.get("packet_id", "")),
                    "source_row_id": "",
                    "Run": "",
                    "severity": "REVIEW",
                    "message": f"chip_peak_calling_ready={clean(r.get('chip_peak_calling_ready', ''))}",
                    "curator_comment": "",
                })

    if not rowwise.empty:
        for _, r in rowwise.iterrows():
            flag = clean(r.get("review_flag", ""))
            conf = clean(r.get("confidence", "")).lower()
            role = clean(r.get("ai_sample_role", "")).lower()
            if flag not in {"", "ok"} or conf in {"low", "unknown"} or role in {"unknown", ""}:
                problems.append({
                    "problem_type": "rowwise_review_flag_or_low_confidence",
                    "packet_id": clean(r.get("packet_id", "")),
                    "source_row_id": clean(r.get("source_row_id", "")),
                    "Run": clean(r.get("Run", "")),
                    "severity": "REVIEW",
                    "message": f"review_flag={flag}; confidence={conf}; role={role}",
                    "curator_comment": "",
                })

    if not target_control.empty:
        for _, r in target_control.iterrows():
            bg = clean(r.get("ai_background_or_comparator", "")).lower()
            prelim = clean(r.get("prelim_matched_background_run_ids", ""))
            if bg in {"", "unknown", "not_applicable", "none"} and prelim == "":
                problems.append({
                    "problem_type": "target_ip_missing_background",
                    "packet_id": clean(r.get("packet_id", "")),
                    "source_row_id": clean(r.get("target_source_row_id", "")),
                    "Run": clean(r.get("target_Run", "")),
                    "severity": "REVIEW",
                    "message": "Target/IP row may lack clear background/input/IgG mapping.",
                    "curator_comment": "",
                })

    return pd.DataFrame(problems)

def autosize_and_filter(writer, sheets):
    wb = writer.book
    for sheet_name, df in sheets.items():
        ws = wb[sheet_name]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = max([len(str(col_name))] + [len(str(x)) for x in df[col_name].head(200).fillna("")])
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max(max_len + 2, 10), 60)

def main():
    active = pd.read_csv(ACTIVE, sep="\t", dtype=str).fillna("")
    rowwise = pd.read_csv(ROWWISE, sep="\t", dtype=str).fillna("")
    target_control = pd.read_csv(TARGET_CONTROL, sep="\t", dtype=str).fillna("")

    readme = build_readme()
    study = build_study_review(active)
    sample_map = build_sample_map(active)
    problems = build_problem_rows(active, rowwise, target_control)

    # Add curator columns to rowwise and target-control sheets.
    for df in [rowwise, target_control]:
        for c in ["curator_decision", "curator_corrected_value", "curator_comment"]:
            if c not in df.columns:
                df[c] = ""

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTDIR / f"chip_curator_review_{ts}.xlsx"

    sheets = {
        "README": readme,
        "Study_Review": study,
        "Sample_Map_Review": sample_map,
        "Target_Control_Map_Review": target_control,
        "Problem_Rows": problems,
        "Rowwise_Review": rowwise,
        "Packet_Status": active,
    }

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            # Excel sheet names max 31 chars
            df.to_excel(writer, sheet_name=name[:31], index=False)
        autosize_and_filter(writer, {k[:31]: v for k, v in sheets.items()})

    latest = OUTDIR / "LATEST_CHIP_CURATOR_REVIEW.txt"
    latest.write_text(str(out) + "\n")

    print("Wrote:", out)
    print("Wrote:", latest)
    print()
    for name, df in sheets.items():
        print(f"{name}: {len(df)} rows")

if __name__ == "__main__":
    main()
