#!/usr/bin/env python3
"""
Finalize/report trusted PMID-linked RNA AI-curation phase.

This does not modify AI outputs.
It summarizes:
  - trusted RNA packet validation status
  - held packets
  - semantic red-flag burden
  - latest curator Excel
  - production notes for downstream GRN/curator review
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd


ROOT = Path(".")
BASE = Path("outputs/04_AGENTIC_AI_ASSIST")
DEEP = BASE / "deep_qc"
CURATOR = BASE / "curator_excel"
QUEUE = BASE / "trusted_ai_queue" / "trusted_assay_aware_ai_queue.tsv"
INV = DEEP / "ai_packet_status_inventory.tsv"
SEMANTIC = DEEP / "semantic_red_flags.tsv"
HELD = DEEP / "held_packets_for_policy_review.tsv"


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def latest_file(pattern: str) -> Path | None:
    files = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def value_counts_md(series: pd.Series) -> str:
    if series.empty:
        return "- none"
    vc = series.value_counts(dropna=False)
    return "\n".join([f"- {idx}: {val}" for idx, val in vc.items()])


def df_to_markdown_simple(df: pd.DataFrame) -> str:
    """Minimal markdown table writer; avoids optional pandas/tabulate dependency."""
    if df.empty:
        return "- none"

    cols = list(df.columns)
    lines = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")

    for _, row in df.iterrows():
        vals = []
        for c in cols:
            x = str(row.get(c, ""))
            x = x.replace("|", "\\|").replace("\n", " ")
            vals.append(x)
        lines.append("| " + " | ".join(vals) + " |")

    return "\n".join(lines)


def main():
    DEEP.mkdir(parents=True, exist_ok=True)

    queue = read_tsv(QUEUE)
    inv = read_tsv(INV)
    semantic = read_tsv(SEMANTIC)

    if queue.empty:
        raise SystemExit(f"Missing or empty queue: {QUEUE}")
    if inv.empty:
        raise SystemExit(f"Missing or empty inventory: {INV}")

    # Merge queue with status.
    keep_inv = [c for c in ["packet_id", "latest_validation_status"] if c in inv.columns]
    merged = queue.merge(inv[keep_inv], on="packet_id", how="left")
    merged["latest_validation_status"] = (
        merged.get("latest_validation_status", "")
        .replace("", "NO_VALIDATION")
        .fillna("NO_VALIDATION")
    )

    if "n_rows" in merged.columns:
        merged["n_rows_num"] = pd.to_numeric(merged["n_rows"], errors="coerce").fillna(0).astype(int)
    else:
        merged["n_rows"] = ""
        merged["n_rows_num"] = 0

    if "recommended_action" not in merged.columns:
        merged["recommended_action"] = ""

    # Held/non-pass packets.
    held = merged[merged["latest_validation_status"] != "PASS"].copy()
    held_cols = [
        "packet_id", "pmid", "bioproject", "n_rows",
        "assay_class", "recommended_action", "latest_validation_status"
    ]
    held_cols = [c for c in held_cols if c in held.columns]

    held_out = DEEP / "held_packets_for_policy_review.tsv"
    held[held_cols].to_csv(held_out, sep="\t", index=False)

    # Main packet status output.
    status_cols = [
        "packet_id", "pmid", "bioproject", "n_rows",
        "assay_class", "recommended_action", "latest_validation_status"
    ]
    status_cols = [c for c in status_cols if c in merged.columns]
    status_out = DEEP / "trusted_rna_ai_phase_packet_status.tsv"
    merged[status_cols].to_csv(status_out, sep="\t", index=False)

    # Semantic counts.
    if not semantic.empty and "severity" in semantic.columns:
        semantic_severity = semantic["severity"].value_counts().to_dict()
    else:
        semantic_severity = {}

    if not semantic.empty and "semantic_flag" in semantic.columns:
        semantic_type = semantic["semantic_flag"].value_counts().to_dict()
    else:
        semantic_type = {}

    high_medium = 0
    if not semantic.empty and "severity" in semantic.columns:
        high_medium = int(semantic["severity"].isin(["HIGH", "MEDIUM"]).sum())

    latest_excel = latest_file("outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_*.xlsx")

    # Try to read workbook sheet sizes.
    excel_sheet_counts = []
    if latest_excel is not None:
        try:
            xls = pd.ExcelFile(latest_excel)
            for sheet in xls.sheet_names:
                try:
                    n = len(pd.read_excel(latest_excel, sheet_name=sheet))
                    excel_sheet_counts.append((sheet, n))
                except Exception:
                    excel_sheet_counts.append((sheet, "unreadable"))
        except Exception:
            excel_sheet_counts.append(("ERROR_READING_WORKBOOK", "unreadable"))

    report = DEEP / "TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md"

    status_counts = merged["latest_validation_status"].value_counts().to_dict()
    action_status = (
        merged.groupby(["recommended_action", "latest_validation_status"])
        .size()
        .reset_index(name="n")
        .sort_values(["latest_validation_status", "recommended_action"])
    )

    lines = []
    lines.append("# Trusted PMID-linked RNA AI-curation Phase Completion Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Executive status")
    lines.append("")
    lines.append(f"- Trusted RNA packets inspected: {len(merged)}")
    for k, v in status_counts.items():
        lines.append(f"- {k}: {v}")
    lines.append(f"- Semantic HIGH/MEDIUM flags among PASS packets: {high_medium}")
    lines.append(f"- Held packets requiring policy review: {len(held)}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "The main AI-actionable trusted PMID-linked RNA queue is complete if PASS=69 "
        "and the only NO_VALIDATION records are intentionally held packets. "
        "AI outputs remain suggestions only; curator final columns are authoritative."
    )
    lines.append("")
    lines.append(
        "Rows with REVIEW flags should remain visible to curators and should not be "
        "silently treated as final high-confidence GRN-ready annotations."
    )
    lines.append("")
    lines.append("## Validation status by recommended action")
    lines.append("")
    if action_status.empty:
        lines.append("- none")
    else:
        lines.append(df_to_markdown_simple(action_status))
    lines.append("")
    lines.append("## Held packets")
    lines.append("")
    if held.empty:
        lines.append("No held packets.")
    else:
        lines.append(df_to_markdown_simple(held[held_cols]))
    lines.append("")
    lines.append("## Semantic red-flag summary")
    lines.append("")
    lines.append("### By severity")
    lines.append("")
    if semantic_severity:
        for k, v in semantic_severity.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("### By flag type")
    lines.append("")
    if semantic_type:
        for k, v in semantic_type.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Latest curator workbook")
    lines.append("")
    if latest_excel is None:
        lines.append("- No curator workbook found.")
    else:
        lines.append(f"- {latest_excel}")
        if excel_sheet_counts:
            lines.append("")
            lines.append("| sheet | rows |")
            lines.append("|---|---:|")
            for sheet, n in excel_sheet_counts:
                lines.append(f"| {sheet} | {n} |")
    lines.append("")
    lines.append("## Files written by this report")
    lines.append("")
    lines.append(f"- `{status_out}`")
    lines.append(f"- `{held_out}`")
    lines.append(f"- `{report}`")
    lines.append("")
    lines.append("## Production notes")
    lines.append("")
    lines.append("- Do not commit API keys, `.env`, large data files, raw PDFs, or large generated output folders.")
    lines.append("- Keep scripts, README/runbooks, QC summaries, and small manifests under version control.")
    lines.append("- Patch or replace `41d_batch_run_trusted_queue_auto_chunked.py` before postdoc rerun.")
    lines.append("- Future default actionable queue classes should include `run_ai_first`, `run_ai_pilot`, and `run_ai`.")
    lines.append("- Future default large-packet threshold should be 100 rows unless stress testing suggests otherwise.")
    lines.append("- ChIP curation must remain separate and use ChIP-specific control/background validation.")
    lines.append("")

    report.write_text("\n".join(lines))

    print("Wrote:", status_out)
    print("Wrote:", held_out)
    print("Wrote:", report)
    print()
    print("Status counts:")
    print(merged["latest_validation_status"].value_counts().to_string())
    print()
    print("Held packets:")
    if held.empty:
        print("None")
    else:
        print(held[held_cols].to_string(index=False))
    print()
    print("Latest Excel:", latest_excel)


if __name__ == "__main__":
    main()
