#!/usr/bin/env python3
"""
Deep QC inventory for agentic AI curation outputs.

Read-only. Does not modify or delete anything.

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/
    ai_packet_status_inventory.tsv
    ai_output_file_inventory.tsv
    latest_validation_issue_summary.tsv
    chunked_fallback_summary.tsv
    superseded_or_attention_outputs.tsv
    DEEP_QC_SUMMARY.md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


QUEUE = Path("outputs/04_AGENTIC_AI_ASSIST/trusted_ai_queue/trusted_assay_aware_ai_queue.tsv")
PACKET_TABLES = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")
AI_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
VALIDATION_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/validation")
OUTDIR = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")


PACKET_RE = re.compile(r"(PMID_[^_]+__BIOPROJECT_[A-Za-z0-9_.-]+)")


def clean(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def parse_int(x: Any, default: int = 0) -> int:
    s = clean(x)
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def read_tsv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep="\t", dtype=str).fillna("")


def metric_value_tsv_to_dict(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
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


def infer_packet_id_from_path(path: Path) -> str:
    m = PACKET_RE.search(str(path))
    return m.group(1) if m else ""


def validation_files_for_packet(packet_id: str) -> list[Path]:
    return sorted(
        VALIDATION_DIR.glob(f"{packet_id}*.validation_summary.tsv"),
        key=lambda p: p.stat().st_mtime,
    )


def latest_validation_for_packet(packet_id: str) -> tuple[Path | None, dict[str, str]]:
    files = validation_files_for_packet(packet_id)
    if not files:
        return None, {}
    p = files[-1]
    return p, metric_value_tsv_to_dict(p)


def validation_issue_file_for_summary(summary_path: Path | None) -> Path | None:
    if summary_path is None:
        return None
    candidate = Path(str(summary_path).replace(".validation_summary.tsv", ".validation_issues.tsv"))
    return candidate if candidate.exists() else None


def classify_ai_json(path: Path) -> str:
    name = path.name
    parent = path.parent.name
    if "__CHUNK_" in parent or "__CHUNK_" in name:
        return "chunk_intermediate"
    if "semantic_stage_corrected" in name:
        return "semantic_stage_corrected"
    if "samplemap_biokey_rebuilt" in name:
        return "samplemap_biokey_rebuilt"
    if "samplemap_rebuilt" in name:
        return "samplemap_rebuilt"
    if "samplemap_completed" in name:
        return "samplemap_completed"
    if "chunked_merged_completed" in name:
        return "chunked_merged_completed"
    if "chunked_merged" in name:
        return "chunked_merged"
    if ".ai_curation." in name:
        return "one_shot"
    return "other"


def safe_load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_json_load_error": str(e)}


def summarize_ai_json(path: Path) -> dict[str, Any]:
    packet_id = infer_packet_id_from_path(path)
    obj = safe_load_json(path)
    audit = obj.get("chunked_generation_audit", {}) if isinstance(obj, dict) else {}

    rowwise = obj.get("rowwise_suggestions", []) if isinstance(obj, dict) else []
    sample_map = obj.get("sample_map", []) if isinstance(obj, dict) else []

    return {
        "packet_id": packet_id,
        "ai_json_path": str(path),
        "ai_output_type": classify_ai_json(path),
        "modified_time": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "json_load_error": clean(obj.get("_json_load_error", "")) if isinstance(obj, dict) else "not_dict",
        "ai_review_status": clean(obj.get("ai_review_status", "")) if isinstance(obj, dict) else "",
        "assay_class_confirmed": clean(obj.get("assay_class_confirmed", "")) if isinstance(obj, dict) else "",
        "n_rowwise_suggestions_in_json": len(rowwise) if isinstance(rowwise, list) else "",
        "n_sample_map_entries_in_json": len(sample_map) if isinstance(sample_map, list) else "",
        "n_global_warnings": len(obj.get("global_warnings", []) or []) if isinstance(obj, dict) else "",
        "chunk_size": audit.get("chunk_size", ""),
        "n_chunks": audit.get("n_chunks", ""),
        "n_packet_rows_audit": audit.get("n_packet_rows", ""),
        "n_ai_rowwise_valid_unique": audit.get("n_ai_rowwise_valid_unique", ""),
        "n_deterministic_fallback_rowwise_suggestions": audit.get("n_deterministic_fallback_rowwise_suggestions", ""),
        "n_invalid_ai_rowwise_source_ids_ignored": audit.get("n_invalid_ai_rowwise_source_ids_ignored", ""),
        "n_duplicate_ai_rowwise_source_ids_ignored": audit.get("n_duplicate_ai_rowwise_source_ids_ignored", ""),
    }


def build_packet_inventory(queue: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, q in queue.iterrows():
        packet_id = clean(q.get("packet_id", ""))
        if not packet_id:
            continue

        packet_tsv = PACKET_TABLES / f"{packet_id}.rowwise_evidence.tsv"
        packet_rows = ""
        if packet_tsv.exists():
            try:
                packet_rows = len(read_tsv(packet_tsv))
            except Exception:
                packet_rows = "read_error"

        val_path, val = latest_validation_for_packet(packet_id)
        issue_path = validation_issue_file_for_summary(val_path)

        # Count AI JSONs under the packet folder.
        packet_ai_dir = AI_DIR / packet_id
        ai_jsons = sorted(packet_ai_dir.glob("*.json")) if packet_ai_dir.exists() else []
        ai_curation_jsons = [p for p in ai_jsons if ".ai_curation" in p.name]

        rows.append({
            "packet_id": packet_id,
            "pmid": clean(q.get("pmid", "")),
            "bioproject": clean(q.get("bioproject", "")),
            "queue_n_rows": clean(q.get("n_rows", "")),
            "packet_tsv_n_rows": packet_rows,
            "assay_class": clean(q.get("assay_class", "")),
            "recommended_action": clean(q.get("assay_aware_recommended_action", "")),
            "priority_score": clean(q.get("assay_aware_priority_score", "")),
            "latest_validation_status": clean(val.get("validation_status", "")),
            "latest_n_fail": parse_int(val.get("n_fail", 0)),
            "latest_n_warn": parse_int(val.get("n_warn", 0)),
            "latest_n_packet_rows": clean(val.get("n_packet_rows", "")),
            "latest_n_rowwise_suggestions": clean(val.get("n_rowwise_suggestions", "")),
            "latest_n_sample_map_entries": clean(val.get("n_sample_map_entries", "")),
            "latest_validation_summary": str(val_path) if val_path else "",
            "latest_validation_issues": str(issue_path) if issue_path else "",
            "n_validation_summaries": len(validation_files_for_packet(packet_id)),
            "n_ai_jsons_in_packet_folder": len(ai_jsons),
            "n_ai_curation_jsons_in_packet_folder": len(ai_curation_jsons),
            "packet_tsv_exists": packet_tsv.exists(),
        })

    return pd.DataFrame(rows)


def build_ai_output_inventory() -> pd.DataFrame:
    rows = []
    if not AI_DIR.exists():
        return pd.DataFrame()

    for path in sorted(AI_DIR.glob("**/*.json")):
        # Skip audit files; this inventory is for AI curation JSONs.
        if ".audit." in path.name:
            continue
        if ".ai_curation" not in path.name:
            continue
        rows.append(summarize_ai_json(path))

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["packet_id", "modified_time", "ai_output_type"])
    return out


def build_latest_issue_summary(packet_inventory: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, r in packet_inventory.iterrows():
        packet_id = clean(r.get("packet_id", ""))
        issue_path_str = clean(r.get("latest_validation_issues", ""))
        if not issue_path_str:
            continue

        issue_path = Path(issue_path_str)
        if not issue_path.exists() or not issue_path.is_file():
            continue

        issues = read_tsv(issue_path)
        if issues.empty:
            continue

        if not {"severity", "check"}.issubset(issues.columns):
            continue

        grouped = (
            issues.groupby(["severity", "check"])
            .size()
            .reset_index(name="n")
            .sort_values(["severity", "check"])
        )

        for _, g in grouped.iterrows():
            rows.append({
                "packet_id": packet_id,
                "latest_validation_status": clean(r.get("latest_validation_status", "")),
                "severity": clean(g["severity"]),
                "check": clean(g["check"]),
                "n": int(g["n"]),
                "issue_file": str(issue_path),
            })

    return pd.DataFrame(rows)


def build_chunked_fallback_summary(ai_inventory: pd.DataFrame) -> pd.DataFrame:
    if ai_inventory.empty:
        return pd.DataFrame()

    x = ai_inventory[
        ai_inventory["ai_output_type"].isin([
            "chunked_merged_completed",
            "chunked_merged",
            "semantic_stage_corrected",
            "samplemap_completed",
        ])
    ].copy()

    if x.empty:
        return pd.DataFrame()

    rows = []
    for _, r in x.iterrows():
        packet_id = clean(r["packet_id"])
        packet_ai_dir = AI_DIR / packet_id
        origin_files = sorted(
            packet_ai_dir.glob(f"{packet_id}.chunked_rowwise_origin_qc.*.tsv"),
            key=lambda p: p.stat().st_mtime,
        )

        origin_path = origin_files[-1] if origin_files else None
        n_ai_chunk = ""
        n_fallback_origin = ""

        if origin_path is not None:
            odf = read_tsv(origin_path)
            if "rowwise_origin" in odf.columns:
                counts = odf["rowwise_origin"].value_counts().to_dict()
                n_ai_chunk = counts.get("ai_chunk", 0)
                n_fallback_origin = counts.get("deterministic_fallback", 0)

        # Only report entries that actually have chunk/fallback audit information.
        has_fallback_info = any([
            clean(r.get("n_packet_rows_audit", "")),
            clean(r.get("n_ai_rowwise_valid_unique", "")),
            clean(r.get("n_deterministic_fallback_rowwise_suggestions", "")),
            origin_path is not None,
            clean(n_ai_chunk),
            clean(n_fallback_origin),
        ])

        if not has_fallback_info:
            continue

        rows.append({
            "packet_id": packet_id,
            "ai_json_path": clean(r["ai_json_path"]),
            "n_packet_rows_audit": clean(r.get("n_packet_rows_audit", "")),
            "n_ai_rowwise_valid_unique_audit": clean(r.get("n_ai_rowwise_valid_unique", "")),
            "n_deterministic_fallback_audit": clean(r.get("n_deterministic_fallback_rowwise_suggestions", "")),
            "n_invalid_ai_rowwise_source_ids_ignored": clean(r.get("n_invalid_ai_rowwise_source_ids_ignored", "")),
            "n_duplicate_ai_rowwise_source_ids_ignored": clean(r.get("n_duplicate_ai_rowwise_source_ids_ignored", "")),
            "origin_qc_path": str(origin_path) if origin_path else "",
            "n_ai_chunk_origin_qc": n_ai_chunk,
            "n_deterministic_fallback_origin_qc": n_fallback_origin,
        })

    return pd.DataFrame(rows)


def build_attention_outputs(ai_inventory: pd.DataFrame, packet_inventory: pd.DataFrame) -> pd.DataFrame:
    rows = []

    if ai_inventory.empty:
        return pd.DataFrame()

    latest_ai_by_packet = {}
    for packet_id, g in ai_inventory.groupby("packet_id"):
        # Latest modified AI curation JSON per packet.
        gg = g.sort_values("modified_time")
        latest_ai_by_packet[packet_id] = clean(gg.iloc[-1]["ai_json_path"])

    latest_status = {
        clean(r["packet_id"]): clean(r.get("latest_validation_status", ""))
        for _, r in packet_inventory.iterrows()
    }

    for _, r in ai_inventory.iterrows():
        packet_id = clean(r["packet_id"])
        path = clean(r["ai_json_path"])
        reasons = []

        if path != latest_ai_by_packet.get(packet_id, ""):
            reasons.append("superseded_not_latest_ai_json")

        if clean(r.get("json_load_error", "")):
            reasons.append("json_load_error")

        if clean(r.get("ai_output_type", "")) == "chunk_intermediate":
            reasons.append("chunk_intermediate_not_final_output")

        if "known_bad" in path.lower() or "quarantine" in path.lower():
            reasons.append("already_in_known_bad_or_quarantine_path")

        # If latest validation is PASS, old one-shot/chunked failures are attention but not active.
        if latest_status.get(packet_id) == "PASS" and path != latest_ai_by_packet.get(packet_id, ""):
            reasons.append("packet_has_later_PASS_output")

        if reasons:
            rows.append({
                "packet_id": packet_id,
                "ai_json_path": path,
                "ai_output_type": clean(r.get("ai_output_type", "")),
                "modified_time": clean(r.get("modified_time", "")),
                "attention_reasons": ";".join(sorted(set(reasons))),
            })

    return pd.DataFrame(rows)


def write_summary_md(
    packet_inventory: pd.DataFrame,
    ai_inventory: pd.DataFrame,
    issue_summary: pd.DataFrame,
    chunk_summary: pd.DataFrame,
    attention: pd.DataFrame,
    out: Path,
) -> None:
    lines = []
    lines.append("# Deep QC Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    n_packets = len(packet_inventory)
    lines.append("## Packet validation status")
    lines.append("")
    lines.append(f"Trusted queue packets inspected: {n_packets}")
    lines.append("")

    if not packet_inventory.empty:
        vc = packet_inventory["latest_validation_status"].replace("", "NO_VALIDATION").value_counts()
        for k, v in vc.items():
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## AI output files")
    lines.append("")
    lines.append(f"AI curation JSON files found: {len(ai_inventory)}")
    if not ai_inventory.empty:
        vc = ai_inventory["ai_output_type"].value_counts()
        for k, v in vc.items():
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Latest validation issues")
    lines.append("")
    if issue_summary.empty:
        lines.append("No latest validation issues found.")
    else:
        x = (
            issue_summary.groupby(["severity", "check"])["n"]
            .sum()
            .reset_index()
            .sort_values(["severity", "check"])
        )
        for _, r in x.iterrows():
            lines.append(f"- {r['severity']} / {r['check']}: {int(r['n'])}")
    lines.append("")

    lines.append("## Chunked/fallback outputs")
    lines.append("")
    if chunk_summary.empty:
        lines.append("No chunked merged outputs found.")
    else:
        for _, r in chunk_summary.iterrows():
            lines.append(
                f"- {r['packet_id']}: fallback={r.get('n_deterministic_fallback_origin_qc', '')}, "
                f"AI_rows={r.get('n_ai_chunk_origin_qc', '')}"
            )
    lines.append("")

    lines.append("## Files needing attention")
    lines.append("")
    lines.append(f"Attention/superseded output records: {len(attention)}")
    lines.append("")
    lines.append("Interpretation: this is a file inventory only. Do not delete anything based on this alone.")
    lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=OUTDIR)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    if not QUEUE.exists():
        raise FileNotFoundError(f"Missing queue: {QUEUE}")

    queue = read_tsv(QUEUE)

    packet_inventory = build_packet_inventory(queue)
    ai_inventory = build_ai_output_inventory()
    issue_summary = build_latest_issue_summary(packet_inventory)
    chunk_summary = build_chunked_fallback_summary(ai_inventory)
    attention = build_attention_outputs(ai_inventory, packet_inventory)

    packet_inventory.to_csv(args.outdir / "ai_packet_status_inventory.tsv", sep="\t", index=False)
    ai_inventory.to_csv(args.outdir / "ai_output_file_inventory.tsv", sep="\t", index=False)
    issue_summary.to_csv(args.outdir / "latest_validation_issue_summary.tsv", sep="\t", index=False)
    chunk_summary.to_csv(args.outdir / "chunked_fallback_summary.tsv", sep="\t", index=False)
    attention.to_csv(args.outdir / "superseded_or_attention_outputs.tsv", sep="\t", index=False)

    write_summary_md(
        packet_inventory,
        ai_inventory,
        issue_summary,
        chunk_summary,
        attention,
        args.outdir / "DEEP_QC_SUMMARY.md",
    )

    print("Wrote deep QC outputs to:", args.outdir)
    print()
    print("Validation status counts:")
    if not packet_inventory.empty:
        print(packet_inventory["latest_validation_status"].replace("", "NO_VALIDATION").value_counts().to_string())
    print()
    print("AI output type counts:")
    if not ai_inventory.empty:
        print(ai_inventory["ai_output_type"].value_counts().to_string())
    print()
    print("Latest issue summary:")
    if issue_summary.empty:
        print("No latest validation issues.")
    else:
        print(issue_summary.groupby(["severity", "check"])["n"].sum().reset_index().to_string(index=False))
    print()
    print("Chunked fallback summary:")
    if chunk_summary.empty:
        print("No chunked merged outputs.")
    else:
        print(chunk_summary.to_string(index=False))


if __name__ == "__main__":
    main()
