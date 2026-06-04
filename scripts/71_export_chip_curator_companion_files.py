#!/usr/bin/env python3
"""
Export curator-facing ChIP companion files from the latest ChIP curator workbook.

Purpose:
  - Make ChIP as shareable as RNA.
  - Provide standalone TSV and MD files for Paper_Summaries, Curator_Triage,
    Study_Review, Problem_Rows, Target_Control_Map_Review, etc.
  - Copy the latest ChIP Excel into the same folder.
  - No API required.

Output:
  outputs/06_CHIP_AI_ASSIST/22_curator_share_files/
"""

from pathlib import Path
from datetime import datetime
import shutil
import hashlib
import pandas as pd

LATEST_XLSX = Path("outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt")
OUT = Path("outputs/06_CHIP_AI_ASSIST/22_curator_share_files")


def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def size_human(path):
    n = path.stat().st_size
    for unit in ["B", "K", "M", "G"]:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}T"


def df_to_md_table(df, max_rows=80, max_col_width=140):
    if df is None or df.empty:
        return "_No rows._\n"

    d = df.head(max_rows).copy()

    def esc(x):
        x = clean(x).replace("\n", " ")
        if len(x) > max_col_width:
            x = x[:max_col_width - 3] + "..."
        return x.replace("|", "\\|")

    cols = list(d.columns)
    lines = []
    lines.append("| " + " | ".join(esc(c) for c in cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for _, row in d.iterrows():
        lines.append("| " + " | ".join(esc(row[c]) for c in cols) + " |")

    if len(df) > max_rows:
        lines.append("")
        lines.append(f"_Showing first {max_rows} of {len(df)} rows._")

    return "\n".join(lines) + "\n"


def write_sheet_files(sheets, sheet_name, prefix, md_cols=None, max_md_rows=80):
    if sheet_name not in sheets:
        return []

    df = sheets[sheet_name].fillna("")
    paths = []

    tsv = OUT / f"{prefix}.tsv"
    df.to_csv(tsv, sep="\t", index=False)
    paths.append(tsv)

    md = OUT / f"{prefix}.md"
    md_df = df
    if md_cols:
        md_cols = [c for c in md_cols if c in df.columns]
        if md_cols:
            md_df = df[md_cols].copy()

    md.write_text(
        f"# {sheet_name}\n\n"
        f"Rows: {len(df)}\n\n"
        + df_to_md_table(md_df, max_rows=max_md_rows)
    )
    paths.append(md)

    return paths


def main():
    if not LATEST_XLSX.exists():
        raise SystemExit(f"Missing latest pointer: {LATEST_XLSX}")

    xlsx = Path(LATEST_XLSX.read_text().strip())
    if not xlsx.exists():
        raise SystemExit(f"Latest ChIP workbook not found: {xlsx}")

    OUT.mkdir(parents=True, exist_ok=True)

    # Clear old exported share files, but keep folder.
    for p in OUT.glob("*"):
        if p.is_file():
            p.unlink()

    # Copy workbook.
    copied_xlsx = OUT / "ChIP_curator_review.xlsx"
    shutil.copy2(xlsx, copied_xlsx)

    sheets = pd.read_excel(xlsx, sheet_name=None, dtype=str)
    sheets = {k: v.fillna("") for k, v in sheets.items()}

    written = [copied_xlsx]

    # Core curator-facing exports.
    written += write_sheet_files(
        sheets,
        "Paper_Summaries",
        "ChIP_Paper_Summaries",
        md_cols=[
            "packet_id", "pmid", "bioproject", "targets",
            "chip_peak_calling_ready",
            "one_sentence_summary", "study_goal", "organism_strain",
            "main_comparisons_or_sample_axes",
            "paper_evidence_locations",
            "curator_warnings_clean",
            "technical_warnings_clean",
        ],
        max_md_rows=80,
    )

    written += write_sheet_files(
        sheets,
        "Curator_Triage",
        "ChIP_Curator_Triage",
        md_cols=[
            "triage_type", "priority", "packet_id", "pmid",
            "what_to_review", "suggested_sheet",
        ],
        max_md_rows=120,
    )

    written += write_sheet_files(
        sheets,
        "Study_Review",
        "ChIP_Study_Review",
        md_cols=[
            "curator_priority", "curator_focus_summary",
            "packet_id", "pmid", "bioproject",
            "one_sentence_summary", "study_goal",
            "chip_peak_calling_ready",
            "n_low_confidence_rows", "n_review_flag_rows",
            "n_target_ip_missing_background",
        ],
        max_md_rows=80,
    )

    written += write_sheet_files(
        sheets,
        "Problem_Rows",
        "ChIP_Problem_Rows",
        md_cols=[
            "problem_severity", "problem_flags", "problem_messages",
            "curator_action_hint", "packet_id", "pmid", "Run",
            "target_clean", "suggested_sample_role",
            "suggestion_confidence", "review_flag",
        ],
        max_md_rows=120,
    )

    written += write_sheet_files(
        sheets,
        "Target_Control_Map_Review",
        "ChIP_Target_Control_Map_Review",
        md_cols=[
            "packet_id", "pmid", "target_Run", "target_clean",
            "suggested_target_or_antibody_or_tag",
            "target_stage", "target_strain", "target_condition",
            "target_confidence", "ai_background_or_comparator",
            "prelim_matched_background_run_ids",
            "resolved_control_source_row_ids",
            "resolved_control_roles",
            "resolved_control_confidence",
            "target_control_match_status",
        ],
        max_md_rows=120,
    )

    written += write_sheet_files(
        sheets,
        "Metadata_Gaps",
        "ChIP_Metadata_Gaps",
        md_cols=[
            "problem_severity", "problem_flags", "problem_messages",
            "curator_action_hint", "packet_id", "pmid", "Run",
            "target_clean", "stage", "condition",
            "suggestion_confidence", "review_flag",
        ],
        max_md_rows=120,
    )

    # Large technical TSVs useful for Shrey/app integration, but MD limited.
    written += write_sheet_files(
        sheets,
        "Rowwise_Review",
        "ChIP_Rowwise_Review",
        md_cols=[
            "packet_id", "pmid", "source_row_id", "Run",
            "target_clean", "suggested_sample_role",
            "suggested_target_or_antibody_or_tag",
            "suggested_stage_timepoint", "suggested_condition",
            "suggestion_confidence", "review_flag",
        ],
        max_md_rows=80,
    )

    written += write_sheet_files(
        sheets,
        "Sample_Map_Review",
        "ChIP_Sample_Map_Review",
        md_cols=[
            "packet_id", "pmid", "sample_class_id", "sample_role",
            "target_or_antibody_or_tag", "stage_or_timepoint",
            "strain", "condition", "n_rows_matched",
            "confidence", "analysis_ready_status",
        ],
        max_md_rows=80,
    )

    # Completion report if available.
    completion = Path("outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md")
    if completion.exists():
        dst = OUT / "CHIP_AI_PHASE_COMPLETION_REPORT.md"
        shutil.copy2(completion, dst)
        written.append(dst)

    # Inventory/report if available.
    inv_report = Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/CHIP_AI_OUTPUT_INVENTORY_REPORT.md")
    if inv_report.exists():
        dst = OUT / "CHIP_AI_OUTPUT_INVENTORY_REPORT.md"
        shutil.copy2(inv_report, dst)
        written.append(dst)

    # Bundle README
    readme = OUT / "README_FOR_CURATORS.md"
    readme.write_text(f"""# ChIP curator review files

Generated: {datetime.now().isoformat(timespec='seconds')}

Main file:
- ChIP_curator_review.xlsx

Start here:
1. ChIP_Curator_Triage.md / Curator_Triage sheet
2. ChIP_Paper_Summaries.md / Paper_Summaries sheet
3. ChIP_Study_Review.md / Study_Review sheet
4. ChIP_Target_Control_Map_Review.tsv / Target_Control_Map_Review sheet
5. ChIP_Problem_Rows.md / Problem_Rows sheet

Important:
- AI suggestions are not final.
- Curator columns in the Excel workbook are authoritative.
- For ChIP, target-control/input/background relationships are central.
- Shared input controls are expected and are not automatically duplicate errors.
- Metadata_Gaps are lower-priority unknown condition/stage items unless needed for downstream harmonization.

Current status:
- ChIP packets: 42/42 active validated PASS.
- Rowwise review rows: 733.
- Target-control map rows: 490.
- Peak-calling readiness: 30 yes, 11 partial, 1 no.
""")
    written.append(readme)

    # Manifest.
    manifest_rows = []
    for p in sorted(set(written)):
        if p.exists():
            manifest_rows.append({
                "file": p.name,
                "path": str(p),
                "size": size_human(p),
                "sha256": sha256(p),
            })

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = OUT / "MANIFEST.tsv"
    manifest.to_csv(manifest_path, sep="\t", index=False)

    latest = OUT / "LATEST_CHIP_CURATOR_SHARE_FOLDER.txt"
    latest.write_text(str(OUT) + "\n")

    print("Wrote ChIP curator companion files to:", OUT)
    print()
    print(manifest.to_string(index=False))


if __name__ == "__main__":
    main()
