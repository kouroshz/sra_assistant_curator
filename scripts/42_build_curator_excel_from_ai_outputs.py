#!/usr/bin/env python3
"""
Build human-friendly curator Excel workbook from active PASS AI outputs.

Inputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_packet_status_inventory.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_red_flags.tsv
  latest PASS validation summaries
  active AI JSONs
  packet rowwise evidence TSVs

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_<timestamp>.xlsx

Workbook sheets:
  1. README
  2. Study_Review
  3. Sample_Map_Review
  4. Rowwise_Review
  5. Problem_Rows
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

import pandas as pd


DEEP_QC = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")
PACKET_INV = DEEP_QC / "ai_packet_status_inventory.tsv"
STUDY_SUMMARIES = DEEP_QC / "ai_study_summaries_clean.tsv"
SEMANTIC_FLAGS = DEEP_QC / "semantic_red_flags.tsv"
OUTDIR = Path("outputs/04_AGENTIC_AI_ASSIST/curator_excel")


def clean(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def metric_value_tsv(path: Path) -> dict[str, str]:
    df = read_tsv(path)
    if df.empty:
        return {}
    if {"metric", "value"}.issubset(df.columns):
        return {
            clean(r["metric"]): clean(r["value"])
            for _, r in df.iterrows()
            if clean(r.get("metric", ""))
        }
    return {c: clean(df.iloc[0].get(c, "")) for c in df.columns}


def as_text(x) -> str:
    if x is None:
        return ""
    if isinstance(x, list):
        return " | ".join(clean(v) for v in x if clean(v))
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False)
    return clean(x)


def latest_pass_packets() -> pd.DataFrame:
    inv = read_tsv(PACKET_INV)
    if inv.empty:
        raise FileNotFoundError(f"Missing or empty {PACKET_INV}. Run QC scripts first.")
    return inv[inv["latest_validation_status"] == "PASS"].copy()


def active_ai_and_packet_tsv(pktrow: pd.Series) -> tuple[Path, Path]:
    summary_path = Path(clean(pktrow.get("latest_validation_summary", "")))
    val = metric_value_tsv(summary_path)
    ai_json = Path(clean(val.get("ai_json", "")))
    packet_tsv = Path(clean(val.get("packet_tsv", "")))
    return ai_json, packet_tsv


def load_study_review(pass_packets: pd.DataFrame) -> pd.DataFrame:
    summaries = read_tsv(STUDY_SUMMARIES)

    base_cols = [
        "packet_id", "pmid", "bioproject", "assay_class",
        "queue_n_rows", "latest_validation_status", "latest_n_fail",
        "latest_n_warn", "latest_n_rowwise_suggestions",
        "latest_n_sample_map_entries", "latest_validation_summary",
    ]
    base_cols = [c for c in base_cols if c in pass_packets.columns]
    base = pass_packets[base_cols].copy()

    if not summaries.empty:
        keep = [c for c in [
            "packet_id", "summary_status", "ai_review_status",
            "assay_class_confirmed", "one_sentence_summary", "study_goal",
            "organism_strain", "assay_types", "main_comparisons_or_sample_axes",
            "paper_evidence_locations", "curator_warnings_clean",
            "technical_warnings_clean", "n_curator_warnings_clean",
            "n_technical_warnings_clean", "n_sample_map_entries",
            "n_rowwise_suggestions", "ai_json",
        ] if c in summaries.columns]
        base = base.merge(summaries[keep], on="packet_id", how="left")

    base["curator_study_status"] = ""
    base["curator_study_notes"] = ""
    base["curator_ready_for_row_review"] = ""

    order = [c for c in [
        "packet_id", "pmid", "bioproject",
        "assay_class", "assay_class_confirmed", "assay_types",
        "queue_n_rows", "latest_validation_status",
        "one_sentence_summary", "study_goal", "organism_strain",
        "main_comparisons_or_sample_axes", "curator_warnings_clean",
        "technical_warnings_clean",
        "n_curator_warnings_clean", "n_technical_warnings_clean",
        "latest_n_rowwise_suggestions", "latest_n_sample_map_entries",
        "curator_study_status", "curator_ready_for_row_review",
        "curator_study_notes",
        "paper_evidence_locations", "ai_json", "latest_validation_summary",
    ] if c in base.columns]

    return base[order]


def build_sample_map_review(pass_packets: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, pktrow in pass_packets.iterrows():
        packet_id = clean(pktrow["packet_id"])
        ai_json, _ = active_ai_and_packet_tsv(pktrow)
        if not ai_json.exists():
            continue

        obj = json.loads(ai_json.read_text())

        for sm in obj.get("sample_map", []) or []:
            rows.append({
                "packet_id": packet_id,
                "pmid": clean(obj.get("pmid", "")) or clean(pktrow.get("pmid", "")),
                "bioproject": clean(obj.get("bioproject", "")) or clean(pktrow.get("bioproject", "")),
                "sample_class_id": clean(sm.get("sample_class_id", "")),
                "sample_class_description": clean(sm.get("sample_class_description", "")),
                "n_rows_matched": clean(sm.get("n_rows_matched", "")),
                "matched_run_ids": as_text(sm.get("matched_run_ids", [])),
                "assay_type": clean(sm.get("assay_type", "")),
                "strain": clean(sm.get("strain", "")),
                "stage_or_timepoint": clean(sm.get("stage_or_timepoint", "")),
                "condition": clean(sm.get("condition", "")),
                "perturbation_or_treatment": clean(sm.get("perturbation_or_treatment", "")),
                "target_or_antibody_or_tag": clean(sm.get("target_or_antibody_or_tag", "")),
                "sample_role": clean(sm.get("sample_role", "")),
                "suggested_comparator_or_background_class_id": clean(sm.get("suggested_comparator_or_background_class_id", "")),
                "analysis_ready_status": clean(sm.get("analysis_ready_status", "")),
                "confidence": clean(sm.get("confidence", "")),
                "curator_check_priority": clean(sm.get("curator_check_priority", "")),
                "warning_flags": as_text(sm.get("warning_flags", [])),
                "evidence": clean(sm.get("evidence", "")),
                "curator_final_sample_class_id": "",
                "curator_final_stage": "",
                "curator_final_strain": "",
                "curator_final_condition": "",
                "curator_final_treatment_or_perturbation": "",
                "curator_final_control_or_comparator": "",
                "curator_sample_status": "",
                "curator_notes": "",
                "ai_json": str(ai_json),
            })

    return pd.DataFrame(rows)


def build_rowwise_review(pass_packets: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, pktrow in pass_packets.iterrows():
        packet_id = clean(pktrow["packet_id"])
        ai_json, packet_tsv = active_ai_and_packet_tsv(pktrow)
        if not ai_json.exists() or not packet_tsv.exists():
            continue

        obj = json.loads(ai_json.read_text())
        pkt = read_tsv(packet_tsv)
        rowwise = pd.DataFrame(obj.get("rowwise_suggestions", []) or []).fillna("")
        if rowwise.empty:
            continue

        meta_cols = [c for c in [
            "source_row_id", "Run", "BioSample", "BioProject", "PMID", "Title",
            "SampleName", "LibraryName", "LibraryStrategy",
            "Cell_Cycle_Stage", "Life_Stage", "Target", "Strain", "Mutant",
            "Condition1", "Condition2", "Condition3",
            "background_or_control_1", "background_or_control_2",
            "raw_metadata_col1", "raw_metadata_col2", "raw_metadata_col3",
            "biosample_title", "biosample_attr_strain", "biosample_attr_genotype",
            "biosample_attr_treatment", "biosample_attr_condition",
            "detected_stage_terms", "detected_strain_terms",
            "detected_perturbation_terms", "detected_control_terms",
            "public_metadata_evidence_compact",
        ] if c in pkt.columns]

        merged = rowwise.merge(
            pkt[meta_cols],
            on=["source_row_id", "Run"],
            how="left",
            suffixes=("", "_master"),
        )

        merged.insert(0, "packet_id", packet_id)
        merged.insert(1, "pmid", clean(obj.get("pmid", "")) or clean(pktrow.get("pmid", "")))
        merged.insert(2, "bioproject", clean(obj.get("bioproject", "")) or clean(pktrow.get("bioproject", "")))
        merged["ai_json"] = str(ai_json)

        merged["curator_final_stage"] = ""
        merged["curator_final_strain"] = ""
        merged["curator_final_condition"] = ""
        merged["curator_final_treatment_or_perturbation"] = ""
        merged["curator_final_sample_role"] = ""
        merged["curator_final_control_or_comparator"] = ""
        merged["curator_row_status"] = ""
        merged["curator_notes"] = ""

        rows.append(merged)

    if not rows:
        return pd.DataFrame()

    out = pd.concat(rows, ignore_index=True)

    preferred = [c for c in [
        "packet_id", "pmid", "bioproject",
        "source_row_id", "Run", "BioSample",
        "SampleName", "LibraryName", "LibraryStrategy",
        "biosample_title",
        "Cell_Cycle_Stage", "Life_Stage", "Target", "Strain", "Mutant",
        "Condition1", "Condition2", "Condition3",
        "detected_stage_terms", "detected_strain_terms",
        "detected_perturbation_terms", "detected_control_terms",
        "sample_class_id",
        "suggested_assay_type", "suggested_stage_timepoint",
        "suggested_strain", "suggested_condition",
        "suggested_perturbation_or_treatment",
        "suggested_target_or_antibody_or_tag",
        "suggested_sample_role", "suggested_comparator_or_background",
        "suggestion_confidence", "review_flag", "suggestion_evidence",
        "curator_final_stage", "curator_final_strain",
        "curator_final_condition", "curator_final_treatment_or_perturbation",
        "curator_final_sample_role", "curator_final_control_or_comparator",
        "curator_row_status", "curator_notes",
        "public_metadata_evidence_compact",
        "ai_json",
    ] if c in out.columns]

    remaining = [c for c in out.columns if c not in preferred]
    return out[preferred + remaining]


def build_problem_rows(rowwise: pd.DataFrame) -> pd.DataFrame:
    """
    Curator-friendly problem sheet.

    One row per packet/source_row_id/Run, with combined problem flags.
    This avoids repeating the same row three times for:
      deterministic_fallback_row
      low_confidence_ai_suggestion
      rowwise_review_flag_not_ok
    """
    flags = read_tsv(SEMANTIC_FLAGS)
    records = {}

    def key_from_row(r):
        return (
            clean(r.get("packet_id", "")),
            clean(r.get("source_row_id", "")),
            clean(r.get("Run", "")),
        )

    def add_record(r, severity, flag, message):
        key = key_from_row(r)
        if not any(key):
            return

        rec = records.setdefault(key, {
            "packet_id": key[0],
            "source_row_id": key[1],
            "Run": key[2],
            "pmid": clean(r.get("pmid", "")),
            "bioproject": clean(r.get("bioproject", "")),
            "BioSample": clean(r.get("BioSample", "")),
            "biosample_title": clean(r.get("biosample_title", "")),
            "SampleName": clean(r.get("SampleName", "")),
            "LibraryName": clean(r.get("LibraryName", "")),
            "detected_stage_terms": clean(r.get("detected_stage_terms", "")),
            "detected_strain_terms": clean(r.get("detected_strain_terms", "")),
            "sample_class_id": clean(r.get("sample_class_id", "")),
            "suggested_stage_timepoint": clean(r.get("suggested_stage_timepoint", "")),
            "suggested_strain": clean(r.get("suggested_strain", "")),
            "suggested_condition": clean(r.get("suggested_condition", "")),
            "suggested_perturbation_or_treatment": clean(r.get("suggested_perturbation_or_treatment", "")),
            "suggestion_confidence": clean(r.get("suggestion_confidence", "")),
            "review_flag": clean(r.get("review_flag", "")),
            "suggestion_evidence": clean(r.get("suggestion_evidence", "")),
            "problem_severities": [],
            "problem_flags": [],
            "problem_messages": [],
            "curator_problem_status": "",
            "curator_final_stage": "",
            "curator_final_strain": "",
            "curator_final_condition": "",
            "curator_final_treatment_or_perturbation": "",
            "curator_problem_notes": "",
        })

        if severity and severity not in rec["problem_severities"]:
            rec["problem_severities"].append(severity)
        if flag and flag not in rec["problem_flags"]:
            rec["problem_flags"].append(flag)
        if message and message not in rec["problem_messages"]:
            rec["problem_messages"].append(message)

        # Fill missing context if later source has more.
        for col in [
            "pmid", "bioproject", "BioSample", "biosample_title", "SampleName",
            "LibraryName", "detected_stage_terms", "detected_strain_terms",
            "sample_class_id", "suggested_stage_timepoint", "suggested_strain",
            "suggested_condition", "suggested_perturbation_or_treatment",
            "suggestion_confidence", "review_flag", "suggestion_evidence",
        ]:
            if not rec.get(col) and clean(r.get(col, "")):
                rec[col] = clean(r.get(col, ""))

    # Add semantic flags.
    if not flags.empty:
        for _, r in flags.iterrows():
            add_record(
                r,
                clean(r.get("severity", "")),
                clean(r.get("semantic_flag", "")),
                clean(r.get("message", "")),
            )

    # Add low-confidence / review_flag rows from rowwise review.
    if not rowwise.empty:
        for _, r in rowwise.iterrows():
            review_flag = clean(r.get("review_flag", ""))
            confidence = clean(r.get("suggestion_confidence", "")).lower()

            if review_flag and review_flag != "ok":
                add_record(
                    r,
                    "REVIEW",
                    "rowwise_review_flag_not_ok",
                    f"review_flag={review_flag}",
                )

            if confidence == "low":
                add_record(
                    r,
                    "REVIEW",
                    "low_confidence_ai_suggestion",
                    "AI/fallback confidence is low.",
                )

    if not records:
        return pd.DataFrame()

    out = pd.DataFrame(records.values())

    for col in ["problem_severities", "problem_flags", "problem_messages"]:
        out[col] = out[col].map(lambda x: " | ".join(x) if isinstance(x, list) else clean(x))

    # Severity ordering for curator triage.
    severity_rank = {"HIGH": 1, "MEDIUM": 2, "REVIEW": 3}
    out["_rank"] = out["problem_severities"].map(
        lambda x: min([severity_rank.get(v.strip(), 9) for v in x.split("|")]) if x else 9
    )
    out = out.sort_values(["_rank", "packet_id", "Run"]).drop(columns=["_rank"])

    preferred = [c for c in [
        "packet_id", "pmid", "bioproject",
        "problem_severities", "problem_flags", "problem_messages",
        "Run", "source_row_id", "BioSample", "biosample_title",
        "SampleName", "LibraryName",
        "detected_stage_terms", "detected_strain_terms",
        "sample_class_id",
        "suggested_stage_timepoint", "suggested_strain",
        "suggested_condition", "suggested_perturbation_or_treatment",
        "suggestion_confidence", "review_flag", "suggestion_evidence",
        "curator_problem_status",
        "curator_final_stage", "curator_final_strain",
        "curator_final_condition", "curator_final_treatment_or_perturbation",
        "curator_problem_notes",
    ] if c in out.columns]

    return out[preferred]

def write_excel(
    readme: pd.DataFrame,
    study: pd.DataFrame,
    sample_map: pd.DataFrame,
    rowwise: pd.DataFrame,
    problems: pd.DataFrame,
    out_path: Path,
) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # Require xlsxwriter for polished curator workbook.
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        sheets = {
            "README": readme,
            "Study_Review": study,
            "Sample_Map_Review": sample_map,
            "Problem_Rows": problems,
            "Rowwise_Review": rowwise,
        }

        for sheet, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet, index=False)

        workbook = writer.book

        fmt_header = workbook.add_format({
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        fmt_subtle_header = workbook.add_format({
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#5B9BD5",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        fmt_wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
        fmt_yellow = workbook.add_format({"bg_color": "#FFF2CC", "text_wrap": True, "valign": "top"})
        fmt_problem = workbook.add_format({"bg_color": "#FCE4D6", "text_wrap": True, "valign": "top"})
        fmt_green = workbook.add_format({"bg_color": "#E2F0D9", "text_wrap": True, "valign": "top"})
        fmt_gray = workbook.add_format({"bg_color": "#F2F2F2", "text_wrap": True, "valign": "top"})
        fmt_readme_title = workbook.add_format({
            "bold": True, "font_size": 14, "font_color": "#1F4E78",
            "text_wrap": True, "valign": "top"
        })

        editable_status_values = ["approved", "needs_review", "corrected", "exclude", "uncertain"]
        yes_no_values = ["yes", "no", "needs_review"]

        # Column width rules by semantic role.
        def width_for(col, sheet_name):
            c = col.lower()

            if c in {"packet_id", "ai_json", "latest_validation_summary"}:
                return 26
            if c in {"pmid", "bioproject", "run", "biosample"}:
                return 14
            if "summary" in c or "goal" in c:
                return 46
            if "warning" in c or "message" in c or "evidence" in c or "notes" in c:
                return 48
            if "curator" in c:
                return 28
            if "sample_class" in c:
                return 30
            if "stage" in c or "strain" in c or "condition" in c or "treatment" in c:
                return 24
            if "title" in c or "description" in c:
                return 38
            if sheet_name == "README":
                return 42
            return 18

        def format_sheet(sheet_name, df, header_format):
            ws = writer.sheets[sheet_name]
            nrows = max(len(df), 1)
            ncols = max(len(df.columns), 1)

            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, nrows, ncols - 1)
            ws.set_zoom(85)

            # Headers
            for col_idx, col in enumerate(df.columns):
                ws.write(0, col_idx, col, header_format)

            # Column formatting
            for col_idx, col in enumerate(df.columns):
                c = col.lower()
                w = width_for(col, sheet_name)

                if c.startswith("curator_"):
                    fmt = fmt_yellow
                elif sheet_name == "Problem_Rows" and (
                    c.startswith("problem_") or c in {"suggestion_confidence", "review_flag"}
                ):
                    fmt = fmt_problem
                elif c in {"summary_status", "latest_validation_status", "ai_review_status"}:
                    fmt = fmt_green
                elif c in {"ai_json", "latest_validation_summary", "public_metadata_evidence_compact"}:
                    fmt = fmt_gray
                else:
                    fmt = fmt_wrap

                ws.set_column(col_idx, col_idx, w, fmt)

                # Hide very technical path/evidence columns unless they are curator-facing.
                if c in {"ai_json", "latest_validation_summary"}:
                    ws.set_column(col_idx, col_idx, w, fmt, {"hidden": True})

            # Row heights
            if sheet_name == "Study_Review":
                ws.set_default_row(72)
                ws.set_row(0, 42)
            elif sheet_name == "Sample_Map_Review":
                ws.set_default_row(54)
                ws.set_row(0, 42)
            elif sheet_name == "Problem_Rows":
                ws.set_default_row(60)
                ws.set_row(0, 42)
            elif sheet_name == "Rowwise_Review":
                ws.set_default_row(38)
                ws.set_row(0, 42)
            elif sheet_name == "README":
                ws.set_default_row(45)
                ws.set_row(0, 30)

            # Data validation on status-like columns.
            for col_idx, col in enumerate(df.columns):
                c = col.lower()
                if c.endswith("_status") or c == "curator_study_status":
                    ws.data_validation(1, col_idx, max(nrows, 5000), col_idx, {
                        "validate": "list",
                        "source": editable_status_values,
                    })
                if c == "curator_ready_for_row_review":
                    ws.data_validation(1, col_idx, max(nrows, 5000), col_idx, {
                        "validate": "list",
                        "source": yes_no_values,
                    })

            # Conditional formatting.
            for col_idx, col in enumerate(df.columns):
                c = col.lower()
                rng = (1, col_idx, max(nrows, 1), col_idx)

                if c in {"latest_validation_status", "summary_status"}:
                    ws.conditional_format(*rng, {
                        "type": "text",
                        "criteria": "containing",
                        "value": "PASS",
                        "format": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
                    })
                    ws.conditional_format(*rng, {
                        "type": "text",
                        "criteria": "containing",
                        "value": "ok",
                        "format": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
                    })

                if c in {"problem_severities", "review_flag", "suggestion_confidence"}:
                    ws.conditional_format(*rng, {
                        "type": "text",
                        "criteria": "containing",
                        "value": "HIGH",
                        "format": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"}),
                    })
                    ws.conditional_format(*rng, {
                        "type": "text",
                        "criteria": "containing",
                        "value": "low",
                        "format": workbook.add_format({"bg_color": "#FCE4D6", "font_color": "#9C6500"}),
                    })
                    ws.conditional_format(*rng, {
                        "type": "text",
                        "criteria": "containing",
                        "value": "curator_check",
                        "format": workbook.add_format({"bg_color": "#FCE4D6", "font_color": "#9C6500"}),
                    })

            # Sheet-specific conveniences.
            if sheet_name == "Study_Review":
                ws.freeze_panes(1, 3)
            elif sheet_name in {"Sample_Map_Review", "Problem_Rows", "Rowwise_Review"}:
                ws.freeze_panes(1, 6)

        # Apply formats.
        for sheet_name, df in sheets.items():
            header = fmt_header if sheet_name in {"Study_Review", "Problem_Rows"} else fmt_subtle_header
            format_sheet(sheet_name, df, header)

        # README polish.
        ws = writer.sheets["README"]
        ws.write(0, 0, "section", fmt_header)
        ws.write(0, 1, "description", fmt_header)
        ws.set_column(0, 0, 26, fmt_readme_title)
        ws.set_column(1, 1, 90, fmt_wrap)

        # Add note text at top of Study_Review by workbook comments where supported.
        # Simple and robust: no comments, just readable columns.

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    pass_packets = latest_pass_packets()

    study = load_study_review(pass_packets)
    sample_map = build_sample_map_review(pass_packets)
    rowwise = build_rowwise_review(pass_packets)
    problems = build_problem_rows(rowwise)

    readme = pd.DataFrame([
        {
            "section": "Purpose",
            "description": "Curator review workbook generated from validated AI curation outputs. AI fields are suggestions only; curator_final_* fields are authoritative."
        },
        {
            "section": "Recommended workflow",
            "description": "Review Study_Review first, then Sample_Map_Review, then Problem_Rows, then Rowwise_Review as needed."
        },
        {
            "section": "Current scope",
            "description": "Trusted PMID-linked RNA-seq packets with PASS validation. ChIP curation remains separate unless explicitly included in a future ChIP-specific builder."
        },
        {
            "section": "Generated",
            "description": datetime.now().isoformat(timespec="seconds")
        },
        {
            "section": "Sheets",
            "description": "Study_Review = paper-level summaries; Sample_Map_Review = biological sample classes; Rowwise_Review = one row per SRA run; Problem_Rows = fallback/low-confidence/semantic flags."
        },
    ])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or OUTDIR / f"curator_review_{stamp}.xlsx"

    write_excel(readme, study, sample_map, rowwise, problems, out_path)

    print("Wrote:", out_path)
    print("Study rows:", len(study))
    print("Sample map rows:", len(sample_map))
    print("Rowwise rows:", len(rowwise))
    print("Problem rows:", len(problems))


if __name__ == "__main__":
    main()
