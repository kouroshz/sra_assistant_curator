#!/usr/bin/env python3
"""
Build ChIP AI packet JSON + rowwise sidecar TSVs from ready-with-PDF queue.

This adapts the RNA packet structure so existing script
  scripts/39_run_agentic_ai_on_paper_packet.py
can be reused with --packet-json and --queue.

No API calls are made here.

Inputs:
  outputs/06_CHIP_AI_ASSIST/08_paper_availability/chip_ai_ready_with_pdf_queue.tsv
  outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_resolved_publication_rowwise.tsv

Outputs:
  outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/
    packet_json/
    packet_tables/
    chip_ai_packet_queue.tsv
    CHIP_AI_PACKET_BUILD_REPORT.md
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import re
import pandas as pd


IN_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/08_paper_availability/chip_ai_ready_with_pdf_queue.tsv")
IN_ROWWISE = Path("outputs/06_CHIP_AI_ASSIST/06_resolved_publication_queue/chip_resolved_publication_rowwise.tsv")

OUT = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets")
OUT_JSON = OUT / "packet_json"
OUT_TABLES = OUT / "packet_tables"
OUT_JSON.mkdir(parents=True, exist_ok=True)
OUT_TABLES.mkdir(parents=True, exist_ok=True)


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def safe_slug(x: str, max_len: int = 90) -> str:
    x = clean(x)
    x = re.sub(r"[^A-Za-z0-9._-]+", "_", x).strip("_")
    return x[:max_len]


def join_unique(vals, max_len=1500):
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    return "; ".join(xs)[:max_len]


def make_packet_id(pmid: str, bioproject: str) -> str:
    return f"PMID_{safe_slug(pmid)}__BIOPROJECT_{safe_slug(bioproject)}"


def make_public_metadata_compact(row: pd.Series) -> str:
    fields = [
        ("Run", "Run"),
        ("BioSample", "BioSample"),
        ("BioProject", "BioProject"),
        ("PMID", "PMID"),
        ("Target", "Target"),
        ("target_type", "target_type"),
        ("chip_role", "chip_role"),
        ("background_sample", "background_sample"),
        ("assigned_control1", "assigned_control1"),
        ("assigned_control2", "assigned_control2"),
        ("stage", "stage_combined"),
        ("strain", "strain_context"),
        ("condition", "condition_context"),
        ("replicate", "replicate"),
        ("raw_metadata", "raw_metadata_joined"),
    ]
    parts = []
    for label, col in fields:
        val = clean(row.get(col, ""))
        if val:
            parts.append(f"{label}={val}")
    return " | ".join(parts)


def summarize_groups(x: pd.DataFrame) -> list[dict]:
    group_cols = ["target_clean", "chip_role", "stage_combined", "strain_context", "condition_context"]
    for c in group_cols:
        if c not in x.columns:
            x[c] = ""

    rows = []
    for keys, g in x.groupby(group_cols, dropna=False):
        target, role, stage, strain, condition = keys
        rows.append({
            "target_or_antibody_or_tag": clean(target),
            "chip_role": clean(role),
            "stage_or_timepoint": clean(stage),
            "strain": clean(strain),
            "condition": clean(condition),
            "n_rows": int(len(g)),
            "runs": list(g["Run"].head(15)),
            "source_row_ids": list(g["source_row_id"].head(15)),
        })

    rows = sorted(rows, key=lambda d: (-d["n_rows"], d["target_or_antibody_or_tag"], d["chip_role"]))
    return rows[:100]


def main():
    for p in [IN_QUEUE, IN_ROWWISE]:
        if not p.exists():
            raise SystemExit(f"Missing input: {p}")

    queue = pd.read_csv(IN_QUEUE, sep="\t", dtype=str).fillna("")
    rowwise = pd.read_csv(IN_ROWWISE, sep="\t", dtype=str).fillna("")

    # Normalize rowwise aliases expected by existing AI runner.
    alias_map = {
        "run": "Run",
        "biosample": "BioSample",
        "bioproject": "BioProject",
        "intermediate_resolved_paper_link": "PMID",
        "target": "Target",
    }

    for old, new in alias_map.items():
        if old in rowwise.columns and new not in rowwise.columns:
            rowwise[new] = rowwise[old]

    # If PMID alias is still absent, use resolved_paper_link_pmid.
    if "PMID" not in rowwise.columns:
        rowwise["PMID"] = rowwise.get("resolved_paper_link_pmid", "")

    for c in ["Run", "BioSample", "BioProject", "PMID", "Target"]:
        if c not in rowwise.columns:
            rowwise[c] = ""

    # Add ChIP-specific columns with names likely to survive compacting and validation.
    for c in [
        "target_clean", "target_type", "chip_role", "background_sample",
        "assigned_control1", "assigned_control2", "stage_combined",
        "strain_context", "condition_context", "replicate",
        "raw_metadata_joined", "source_row_id"
    ]:
        if c not in rowwise.columns:
            rowwise[c] = ""

    rowwise["LibraryStrategy"] = "ChIP-like target enrichment"
    rowwise["biosample_attr_target"] = rowwise["Target"]
    rowwise["biosample_attr_antibody"] = rowwise["Target"]
    rowwise["biosample_attr_developmental_stage"] = rowwise["stage_combined"]
    rowwise["biosample_attr_strain"] = rowwise["strain_context"]
    rowwise["biosample_attr_condition"] = rowwise["condition_context"]
    rowwise["detected_assay_target_terms"] = rowwise["target_clean"]
    rowwise["detected_control_terms"] = rowwise.apply(
        lambda r: "; ".join(
            x for x in [
                clean(r.get("background_sample", "")),
                clean(r.get("assigned_control1", "")),
                clean(r.get("assigned_control2", "")),
                clean(r.get("chip_role", "")),
            ] if x
        ),
        axis=1,
    )
    rowwise["public_metadata_evidence_compact"] = rowwise.apply(make_public_metadata_compact, axis=1)

    packet_rows = []
    packet_json_paths = []
    packet_table_paths = []

    for _, q in queue.iterrows():
        pmid = clean(q.get("resolved_paper_link_pmid", q.get("pmid", "")))
        bioproject = clean(q.get("bioproject", ""))
        if not pmid or not bioproject:
            continue

        packet_id = make_packet_id(pmid, bioproject)
        pdf_path = clean(q.get("pdf_path", ""))

        x = rowwise[
            (rowwise["BioProject"].map(clean) == bioproject)
            & (rowwise["PMID"].map(clean) == pmid)
        ].copy()

        # Fallback: sometimes PMID is blank in rowwise but BioProject is enough after queue filtering.
        if x.empty:
            x = rowwise[rowwise["BioProject"].map(clean) == bioproject].copy()
            x["PMID"] = pmid

        if x.empty:
            print(f"WARNING: no rowwise rows for {packet_id}")
            continue

        # Stable column order for sidecar table.
        preferred_cols = [
            "source_row_id", "Run", "BioSample", "PMID", "BioProject",
            "LibraryStrategy",
            "Target", "target_clean", "target_type", "chip_role",
            "background_sample", "assigned_control1", "assigned_control2",
            "stage_combined", "strain_context", "condition_context", "replicate",
            "biosample_attr_target", "biosample_attr_antibody",
            "biosample_attr_developmental_stage",
            "biosample_attr_strain", "biosample_attr_condition",
            "detected_assay_target_terms", "detected_control_terms",
            "public_metadata_evidence_compact",
            "raw_metadata_joined",
            "chip_public_metadata_evidence_compact",
            "publication_backfill_status",
            "publication_qc_note",
            "publication_resolution_source",
        ]
        cols = [c for c in preferred_cols if c in x.columns]
        extra_cols = [c for c in x.columns if c not in cols]
        table = x[cols + extra_cols].copy()

        table_path = OUT_TABLES / f"{packet_id}.rowwise_evidence.tsv"
        table.to_csv(table_path, sep="\t", index=False)

        sample_groups = summarize_groups(table)

        packet = {
            "packet_version": "chip_ai_packet_v1",
            "packet_id": packet_id,
            "unit": {
                "unit_type": "PMID_BioProject_ChIP_group",
                "pmid": pmid,
                "bioproject": bioproject,
                "assay_family": "ChIP_like_target_enrichment",
            },
            "paper_context": {
                "pmid": pmid,
                "title": clean(q.get("top_candidate_title", "")),
                "paper_pdf_candidates": [pdf_path] if pdf_path else [],
                "pdf_available": clean(q.get("pdf_available", "")),
                "publication_backfill_status": clean(q.get("publication_backfill_status", "")),
                "publication_qc_note": clean(q.get("publication_qc_note", "")),
            },
            "sidecar_rowwise_evidence_table": str(table_path),
            "sample_label_groups": sample_groups,
            "chip_context": {
                "n_rows": int(len(table)),
                "targets": clean(q.get("targets", "")),
                "target_types": clean(q.get("target_types", "")),
                "is_ap2_group": clean(q.get("is_ap2_group", "")),
                "curation_scope": clean(q.get("curation_scope", "")),
                "recommended_action": clean(q.get("recommended_action", "")),
                "priority": clean(q.get("priority", "")),
                "curator_facing_principle": (
                    "AI suggestions are draft annotations. Curator final fields are authoritative. "
                    "Target/background/control relationships must remain visible and reviewable."
                ),
            },
        }

        packet_path = OUT_JSON / f"{packet_id}.json"
        packet_path.write_text(json.dumps(packet, indent=2))

        packet_rows.append({
            "packet_id": packet_id,
            "pmid": pmid,
            "bioproject": bioproject,
            "n_rows": len(table),
            "paper_pdf_count": 1 if pdf_path else 0,
            "pdf_path": pdf_path,
            "assay_class": "chip_like_target_enrichment",
            "pre_ai_analysis_readiness": "ready_for_chip_ai_with_pdf",
            "main_ai_task": (
                "Use paper and rowwise metadata to verify ChIP/CUT&RUN/CUT&Tag target, "
                "antibody/tag, sample role, matched background/input/IgG/untagged controls, "
                "stage/strain/condition, and peak-calling readiness."
            ),
            "assay_specific_required_outputs": (
                "study_summary; sample_map with target_ip/input/IgG/untagged/mock roles; "
                "rowwise_suggestions for every source_row_id; target/background/control QC; "
                "chip_peak_calling_ready status; curator warning flags."
            ),
            "assay_aware_priority_tier": clean(q.get("curation_scope", "")),
            "assay_aware_recommended_action": clean(q.get("recommended_action", "")),
            "assay_aware_curator_priority": "high" if clean(q.get("is_ap2_group", "")).lower() == "true" else "medium",
            "priority": clean(q.get("priority", "")),
            "targets": clean(q.get("targets", "")),
            "target_types": clean(q.get("target_types", "")),
            "packet_json": str(packet_path),
            "packet_table": str(table_path),
        })
        packet_json_paths.append(packet_path)
        packet_table_paths.append(table_path)

    qout = pd.DataFrame(packet_rows)
    qout_path = OUT / "chip_ai_packet_queue.tsv"
    qout.to_csv(qout_path, sep="\t", index=False)

    report = []
    report.append("# ChIP AI Packet Build Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- packets built: {len(qout)}")
    report.append(f"- packet JSON dir: `{OUT_JSON}`")
    report.append(f"- packet table dir: `{OUT_TABLES}`")
    if len(qout):
        report.append(f"- total rowwise rows in packets: {int(qout['n_rows'].astype(int).sum())}")
        report.append(f"- AP2/factor-priority packets: {int((qout['assay_aware_curator_priority'] == 'high').sum())}")
        report.append(f"- chunked candidates: {int((qout['assay_aware_recommended_action'] == 'run_chip_ai_chunked').sum())}")
    report.append("")
    report.append("## Built packets")
    report.append("")
    for _, r in qout.iterrows():
        report.append(
            f"- {r['packet_id']}: {r['n_rows']} rows; "
            f"priority={r['assay_aware_curator_priority']}; "
            f"action={r['assay_aware_recommended_action']}; "
            f"targets={str(r['targets'])[:180]}"
        )
    report.append("")
    report.append("## Files written")
    report.append("")
    report.append(f"- `{qout_path}`")
    report.append(f"- `{OUT_JSON}`")
    report.append(f"- `{OUT_TABLES}`")

    report_path = OUT / "CHIP_AI_PACKET_BUILD_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", qout_path)
    print("Wrote:", report_path)
    print("Packet JSON dir:", OUT_JSON)
    print("Packet table dir:", OUT_TABLES)
    print()
    print("Summary:")
    if len(qout):
        print(pd.DataFrame([{
            "packets_built": len(qout),
            "total_rows": int(qout["n_rows"].astype(int).sum()),
            "high_priority_ap2_packets": int((qout["assay_aware_curator_priority"] == "high").sum()),
            "chunked_candidates": int((qout["assay_aware_recommended_action"] == "run_chip_ai_chunked").sum()),
        }]).to_string(index=False))
    else:
        print("No packets built.")


if __name__ == "__main__":
    main()
