#!/usr/bin/env python3
"""
Chunked AI runner for large paper packets.

Design:
  - Run script 39 on rowwise chunks.
  - Collect only valid rowwise_suggestions.
  - Ignore AI sample_map for final merged large-packet output.
  - Build sample_map deterministically from merged rowwise_suggestions.
  - If AI misses rows, add deterministic low-confidence fallback suggestions
    marked curator_check / low_confidence.
  - Validate merged output with script 40.

This prevents large-packet failures caused by:
  - incomplete long JSON rowwise output
  - duplicated sample_map entries
  - hallucinated placeholder source_row_ids
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_PACKET_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_json")
DEFAULT_PACKET_TABLES_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")
DEFAULT_TMP_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/chunked_packet_tmp")
DEFAULT_OUT_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
DEFAULT_VALIDATION_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/validation")

SCRIPT_39 = Path("scripts/39_run_agentic_ai_on_paper_packet.py")
SCRIPT_40 = Path("scripts/40_validate_ai_curation_output.py")


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def clean(x) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def safe_list(x) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [clean(v) for v in x if clean(v)]
    if isinstance(x, str):
        return [clean(x)] if clean(x) else []
    return [clean(x)] if clean(x) else []


def sanitize_class_id(x: str, default: str = "unresolved_sample") -> str:
    s = clean(x)
    if not s:
        s = default
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or default


def run(cmd: list[str], cwd: Path) -> None:
    print("\nRUN:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with return code {proc.returncode}: {' '.join(cmd)}")


def latest_ai_json(packet_id: str) -> Path:
    folder = DEFAULT_OUT_DIR / packet_id
    files = sorted(folder.glob(f"{packet_id}.ai_curation.*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No AI JSON found for {packet_id} in {folder}")
    return files[-1]


def row_evidence_text(row: pd.Series) -> str:
    cols = [
        "Run", "BioSample", "LibraryName", "SampleName",
        "sra_LibraryName", "sra_SampleName", "biosample_title",
        "biosample_attr_sample_name", "biosample_attr_submitter_id",
        "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_genotype", "biosample_attr_treatment",
        "biosample_attr_condition", "biosample_attr_developmental_stage",
        "biosample_attr_dev_stage", "biosample_attr_life_stage",
        "public_metadata_evidence_compact",
    ]
    parts = []
    for c in cols:
        if c in row.index and clean(row.get(c, "")):
            parts.append(f"{c}={clean(row.get(c, ''))}")
    return " | ".join(parts)


def guess_stage(row: pd.Series) -> str:
    txt = row_evidence_text(row).lower()
    stage_terms = [
        "ring", "trophozoite", "schizont", "gametocyte",
        "sporozoite", "oocyst", "ookinete", "merozoite",
        "liver", "blood", "asexual", "sexual"
    ]
    hits = [t for t in stage_terms if re.search(rf"\b{re.escape(t)}s?\b", txt)]
    return ";".join(hits) if hits else "unknown"


def guess_strain(row: pd.Series) -> str:
    for c in [
        "biosample_attr_strain", "biosample_attr_isolate",
        "detected_strain_terms", "sra_SampleName", "biosample_title",
        "SampleName", "LibraryName"
    ]:
        if c in row.index and clean(row.get(c, "")):
            val = clean(row.get(c, ""))
            if len(val) <= 120:
                return val
    return "unknown"


def fallback_rowwise(row: pd.Series) -> dict:
    sid = clean(row.get("source_row_id", ""))
    run = clean(row.get("Run", ""))

    stage = guess_stage(row)
    strain = guess_strain(row)

    label_seed = (
        clean(row.get("biosample_title", ""))
        or clean(row.get("sra_SampleName", ""))
        or clean(row.get("SampleName", ""))
        or clean(row.get("LibraryName", ""))
        or sid
    )
    class_id = "fallback_" + sanitize_class_id(label_seed)

    return {
        "source_row_id": sid,
        "Run": run,
        "sample_class_id": class_id,
        "suggested_assay_type": clean(row.get("LibraryStrategy", "")) or "RNA-Seq",
        "suggested_stage_timepoint": stage,
        "suggested_strain": strain,
        "suggested_condition": clean(row.get("biosample_attr_condition", "")) or "unknown",
        "suggested_perturbation_or_treatment": clean(row.get("biosample_attr_treatment", "")) or "unknown",
        "suggested_target_or_antibody_or_tag": "not_applicable_or_unknown",
        "suggested_sample_role": "expression_sample",
        "suggested_comparator_or_background": "unknown",
        "suggestion_confidence": "low",
        "suggestion_evidence": "DETERMINISTIC FALLBACK because AI chunk missed this row. Curator should review. " + row_evidence_text(row)[:800],
        "review_flag": "curator_check",
    }


def build_deterministic_sample_map(rowwise: list[dict], packet_df: pd.DataFrame) -> list[dict]:
    packet_by_sid = {
        clean(r["source_row_id"]): r
        for _, r in packet_df.fillna("").astype(str).iterrows()
        if clean(r.get("source_row_id", ""))
    }

    by_class: dict[str, dict] = {}

    for rw in rowwise:
        sid = clean(rw.get("source_row_id", ""))
        if not sid or sid not in packet_by_sid:
            continue

        cid = sanitize_class_id(rw.get("sample_class_id", ""), default="unknown_sample_class")

        if cid not in by_class:
            by_class[cid] = {
                "sample_class_id": cid,
                "sample_class_description": f"Deterministic class built from rowwise_suggestions: {cid}",
                "matched_source_row_ids": [],
                "matched_run_ids": [],
                "n_rows_matched": 0,
                "assay_type": clean(rw.get("suggested_assay_type", "")) or "RNA-Seq",
                "strain": clean(rw.get("suggested_strain", "")) or "unknown",
                "stage_or_timepoint": clean(rw.get("suggested_stage_timepoint", "")) or "unknown",
                "condition": clean(rw.get("suggested_condition", "")) or "unknown",
                "perturbation_or_treatment": clean(rw.get("suggested_perturbation_or_treatment", "")) or "unknown",
                "target_or_antibody_or_tag": clean(rw.get("suggested_target_or_antibody_or_tag", "")) or "not_applicable_or_unknown",
                "replicate_logic": "unknown_or_inferred_rowwise",
                "sample_role": clean(rw.get("suggested_sample_role", "")) or "unknown",
                "suggested_comparator_or_background_class_id": clean(rw.get("suggested_comparator_or_background", "")) or "unknown",
                "analysis_ready_status": "unknown",
                "blocker_reason": "none",
                "confidence": clean(rw.get("suggestion_confidence", "")) or "medium",
                "evidence": clean(rw.get("suggestion_evidence", ""))[:1000],
                "curator_check_priority": "medium",
                "warning_flags": [
                    "sample_map_built_deterministically_from_rowwise_suggestions"
                ],
            }

        by_class[cid]["matched_source_row_ids"].append(sid)
        by_class[cid]["matched_run_ids"].append(clean(rw.get("Run", "")))

        if clean(rw.get("review_flag", "")) != "ok":
            by_class[cid]["curator_check_priority"] = "high"
        if clean(rw.get("suggestion_confidence", "")).lower() == "low":
            by_class[cid]["confidence"] = "low"
            if "contains_low_confidence_or_fallback_rows" not in by_class[cid]["warning_flags"]:
                by_class[cid]["warning_flags"].append("contains_low_confidence_or_fallback_rows")

    out = []
    for cid, sm in by_class.items():
        seen = set()
        ids = []
        for sid in sm["matched_source_row_ids"]:
            if sid not in seen:
                seen.add(sid)
                ids.append(sid)

        seen = set()
        runs = []
        for r in sm["matched_run_ids"]:
            if r and r not in seen:
                seen.add(r)
                runs.append(r)

        sm["matched_source_row_ids"] = ids
        sm["matched_run_ids"] = runs
        sm["n_rows_matched"] = len(ids)
        out.append(sm)

    out.sort(key=lambda x: x["sample_class_id"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--chunk-size", type=int, default=60)
    ap.add_argument("--max-pdf-chars", type=int, default=120000)
    ap.add_argument("--max-rowwise-chars", type=int, default=100000)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    root = Path.cwd()
    packet_id = args.packet_id
    stamp = now_stamp()

    packet_json = DEFAULT_PACKET_DIR / f"{packet_id}.json"
    packet_tsv = DEFAULT_PACKET_TABLES_DIR / f"{packet_id}.rowwise_evidence.tsv"

    if not packet_json.exists():
        raise FileNotFoundError(packet_json)
    if not packet_tsv.exists():
        raise FileNotFoundError(packet_tsv)

    packet = json.loads(packet_json.read_text())
    df = pd.read_csv(packet_tsv, sep="\t", dtype=str).fillna("")

    tmp_base = DEFAULT_TMP_DIR / packet_id / stamp
    tmp_packet_dir = tmp_base / "packet_json"
    tmp_table_dir = tmp_base / "packet_tables"
    tmp_packet_dir.mkdir(parents=True, exist_ok=True)
    tmp_table_dir.mkdir(parents=True, exist_ok=True)

    print(f"Packet: {packet_id}")
    print(f"Rows: {len(df)}")
    print(f"Chunk size: {args.chunk_size}")
    print(f"Temporary chunk dir: {tmp_base}")

    valid_packet_ids = set(df["source_row_id"].astype(str))
    packet_by_sid = {r["source_row_id"]: r for _, r in df.iterrows()}

    n_chunks = (len(df) + args.chunk_size - 1) // args.chunk_size
    chunk_jsons = []

    for idx in range(n_chunks):
        start = idx * args.chunk_size
        end = min((idx + 1) * args.chunk_size, len(df))
        chunk_df = df.iloc[start:end].copy()
        chunk_id = f"{packet_id}__CHUNK_{idx+1:03d}_OF_{n_chunks:03d}"

        chunk_tsv = tmp_table_dir / f"{chunk_id}.rowwise_evidence.tsv"
        chunk_packet_json = tmp_packet_dir / f"{chunk_id}.json"

        chunk_df.to_csv(chunk_tsv, sep="\t", index=False)

        chunk_packet = copy.deepcopy(packet)
        chunk_packet["packet_id"] = chunk_id
        chunk_packet["parent_packet_id"] = packet_id
        chunk_packet["chunk_index"] = idx + 1
        chunk_packet["chunk_n"] = n_chunks
        chunk_packet["sidecar_rowwise_evidence_table"] = str(chunk_tsv)
        chunk_packet["chunk_note"] = (
            f"This is chunk {idx+1} of {n_chunks} from parent packet {packet_id}. "
            "Return suggestions only for rows in this chunk. "
            "Do not use placeholder source_row_id values."
        )
        chunk_packet_json.write_text(json.dumps(chunk_packet, indent=2))

        print(f"\n=== Chunk {idx+1}/{n_chunks}: rows {start+1}-{end}; {chunk_id} ===")

        run([
            args.python,
            str(SCRIPT_39),
            "--packet-json",
            str(chunk_packet_json),
            "--max-pdf-chars",
            str(args.max_pdf_chars),
            "--max-rowwise-rows",
            str(args.chunk_size + 10),
            "--max-rowwise-chars",
            str(args.max_rowwise_chars),
        ], cwd=root)

        chunk_ai = latest_ai_json(chunk_id)
        print(f"Chunk AI: {chunk_ai}")
        chunk_jsons.append(chunk_ai)

    merged_seed = None
    all_rowwise = []
    all_global_warnings = []
    invalid_rowwise_ids = []
    duplicate_rowwise_ids = []

    for p in chunk_jsons:
        obj = json.loads(p.read_text())

        if merged_seed is None:
            merged_seed = copy.deepcopy(obj)

        all_global_warnings.extend(safe_list(obj.get("global_warnings")))

        for rw in obj.get("rowwise_suggestions", []) or []:
            sid = clean(rw.get("source_row_id", ""))
            if sid not in valid_packet_ids:
                invalid_rowwise_ids.append(sid)
                continue
            all_rowwise.append(rw)

    # De-duplicate rowwise by source_row_id, preserving first AI suggestion.
    seen = set()
    rowwise_dedup = []
    rowwise_origin = {}

    for rw in all_rowwise:
        sid = clean(rw.get("source_row_id", ""))
        if sid in seen:
            duplicate_rowwise_ids.append(sid)
            continue
        seen.add(sid)
        rowwise_dedup.append(rw)
        rowwise_origin[sid] = "ai_chunk"

    missing_ids = [sid for sid in df["source_row_id"].astype(str).tolist() if sid not in seen]

    fallback_rows = []
    for sid in missing_ids:
        fallback = fallback_rowwise(packet_by_sid[sid])
        fallback_rows.append(fallback)
        rowwise_dedup.append(fallback)
        rowwise_origin[sid] = "deterministic_fallback"

    # Sort rowwise suggestions back into packet order.
    order = {sid: i for i, sid in enumerate(df["source_row_id"].astype(str).tolist())}
    rowwise_dedup.sort(key=lambda rw: order.get(clean(rw.get("source_row_id", "")), 10**12))

    sample_map = build_deterministic_sample_map(rowwise_dedup, df)

    if merged_seed is None:
        merged_seed = {}

    merged = copy.deepcopy(merged_seed)
    merged["packet_id"] = packet_id
    merged["pmid"] = str(packet.get("paper_context", {}).get("pmid", merged.get("pmid", "")) or merged.get("pmid", ""))
    merged["bioproject"] = str(packet.get("paper_context", {}).get("bioproject", merged.get("bioproject", "")) or merged.get("bioproject", ""))
    merged["ai_review_status"] = "reviewed_chunked_with_deterministic_completion"
    merged["sample_map"] = sample_map
    merged["rowwise_suggestions"] = rowwise_dedup

    warnings = sorted(set(all_global_warnings + [
        f"AI output was generated in {n_chunks} rowwise chunks and merged deterministically.",
        "For this large packet, final sample_map was built deterministically from rowwise_suggestions, not taken directly from AI chunk sample_maps.",
        f"n_deterministic_fallback_rowwise_suggestions={len(fallback_rows)}",
        f"n_invalid_ai_rowwise_source_ids_ignored={len(invalid_rowwise_ids)}",
        f"n_duplicate_ai_rowwise_source_ids_ignored={len(duplicate_rowwise_ids)}",
    ]))
    merged["global_warnings"] = warnings

    merged["chunked_generation_audit"] = {
        "parent_packet_id": packet_id,
        "timestamp": stamp,
        "chunk_size": args.chunk_size,
        "n_chunks": n_chunks,
        "chunk_ai_jsons": [str(p) for p in chunk_jsons],
        "n_packet_rows": len(df),
        "n_ai_rowwise_valid_unique": len(rowwise_dedup) - len(fallback_rows),
        "n_deterministic_fallback_rowwise_suggestions": len(fallback_rows),
        "n_invalid_ai_rowwise_source_ids_ignored": len(invalid_rowwise_ids),
        "invalid_ai_rowwise_source_ids_ignored": invalid_rowwise_ids[:200],
        "n_duplicate_ai_rowwise_source_ids_ignored": len(duplicate_rowwise_ids),
        "duplicate_ai_rowwise_source_ids_ignored": duplicate_rowwise_ids[:200],
        "n_merged_rowwise_suggestions": len(rowwise_dedup),
        "n_merged_sample_map_entries": len(sample_map),
    }

    out_dir = DEFAULT_OUT_DIR / packet_id
    out_dir.mkdir(parents=True, exist_ok=True)

    merged_json = out_dir / f"{packet_id}.ai_curation_chunked_merged_completed.{stamp}.json"
    merged_json.write_text(json.dumps(merged, indent=2))

    qc_rows = []
    for sid in df["source_row_id"].astype(str).tolist():
        qc_rows.append({
            "source_row_id": sid,
            "Run": clean(packet_by_sid[sid].get("Run", "")),
            "rowwise_origin": rowwise_origin.get(sid, "missing_unexpected"),
        })
    qc_tsv = out_dir / f"{packet_id}.chunked_rowwise_origin_qc.{stamp}.tsv"
    pd.DataFrame(qc_rows).to_csv(qc_tsv, sep="\t", index=False)

    print("\nMerged completed AI JSON:")
    print(merged_json)
    print("\nRowwise origin QC:")
    print(qc_tsv)
    print(f"\nFallback rows added: {len(fallback_rows)}")

    run([
        args.python,
        str(SCRIPT_40),
        "--packet-tsv",
        str(packet_tsv),
        "--ai-json",
        str(merged_json),
    ], cwd=root)


if __name__ == "__main__":
    main()
