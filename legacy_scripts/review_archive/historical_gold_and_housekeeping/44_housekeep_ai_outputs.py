#!/usr/bin/env python3
"""
Housekeeping planner for AI curation outputs.

Default is DRY-RUN:
  - builds a manifest of active vs superseded/intermediate files
  - proposes archive moves
  - does NOT move or delete anything

With --execute:
  - moves proposed archive files into:
      outputs/04_AGENTIC_AI_ASSIST/_archive_superseded_ai_outputs/<timestamp>/
  - preserves relative paths
  - writes the same manifest

It never deletes files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


DEEP_QC = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")
PACKET_INV = DEEP_QC / "ai_packet_status_inventory.tsv"
AI_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
ARCHIVE_ROOT = Path("outputs/04_AGENTIC_AI_ASSIST/_archive_superseded_ai_outputs")
HOUSEKEEP_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/housekeeping")


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
        return {clean(r["metric"]): clean(r["value"]) for _, r in df.iterrows() if clean(r.get("metric", ""))}
    return {c: clean(df.iloc[0].get(c, "")) for c in df.columns}


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def norm_path(x) -> str:
    """
    Normalize paths for comparison.

    Validation summaries may store absolute paths while file inventory walks
    relative repo paths. Compare resolved paths to avoid archiving active files.
    """
    if x is None:
        return ""
    pp = Path(str(x))
    try:
        return str(pp.resolve())
    except Exception:
        return str(pp)


def classify_file(path: Path) -> str:
    name = path.name
    parent = path.parent.name

    if "__CHUNK_" in parent or "__CHUNK_" in name:
        return "chunk_intermediate"

    if ".ai_curation_semantic_stage_corrected." in name:
        return "semantic_stage_corrected_ai_json"

    if ".ai_curation_samplemap_biokey_rebuilt." in name:
        return "samplemap_biokey_rebuilt_ai_json"

    if ".ai_curation_samplemap_rebuilt." in name:
        return "samplemap_rebuilt_ai_json"

    if ".ai_curation_samplemap_completed." in name:
        return "samplemap_completed_ai_json"

    if ".ai_curation_chunked_merged_completed." in name:
        return "chunked_merged_completed_ai_json"

    if ".ai_curation_chunked_merged." in name:
        return "chunked_merged_incomplete_or_superseded_ai_json"

    if ".ai_curation." in name and name.endswith(".json"):
        return "one_shot_ai_json"

    if ".raw_response." in name:
        return "raw_response"

    if ".prompt." in name:
        return "prompt"

    if ".audit." in name:
        return "audit"

    if "chunked_rowwise_origin_qc" in name:
        return "chunked_origin_qc"

    if "fallback_rows_for_curator_review" in name:
        return "fallback_review_table"

    return "other"


def extract_timestamp_from_name(name: str) -> str:
    m = re.search(r"(20\d{6}_\d{6})", name)
    return m.group(1) if m else ""


def packet_id_from_path(path: Path) -> str:
    # In this folder structure, immediate child of AI_DIR is usually packet_id.
    try:
        rel = path.relative_to(AI_DIR)
        return rel.parts[0] if rel.parts else ""
    except Exception:
        return ""


def build_active_ai_map() -> dict[str, str]:
    if not PACKET_INV.exists():
        raise FileNotFoundError(f"Missing {PACKET_INV}; run scripts/43_deep_qc_ai_outputs.py first.")

    inv = read_tsv(PACKET_INV)
    active = {}

    for _, row in inv.iterrows():
        packet_id = clean(row.get("packet_id", ""))
        status = clean(row.get("latest_validation_status", ""))
        summary_path = Path(clean(row.get("latest_validation_summary", "")))

        if not packet_id or status != "PASS" or not summary_path.exists():
            continue

        summary = metric_value_tsv(summary_path)
        ai_json = clean(summary.get("ai_json", ""))

        if ai_json:
            active[packet_id] = norm_path(ai_json)

    return active


def related_active_files(active_ai_json: Path) -> set[str]:
    """
    Keep active AI JSON and nearby prompt/raw/audit files with same timestamp if present.
    Also keep explicitly generated QC helper tables for active chunked outputs.
    """
    keep = {norm_path(active_ai_json)}

    ts = extract_timestamp_from_name(active_ai_json.name)
    folder = active_ai_json.parent

    if ts and folder.exists():
        for p in folder.iterdir():
            if ts in p.name:
                keep.add(norm_path(p))

    # For chunked final outputs, keep origin/fallback QC tables in packet folder.
    for p in folder.glob("*chunked_rowwise_origin_qc*.tsv"):
        keep.add(norm_path(p))
    for p in folder.glob("*fallback_rows_for_curator_review.tsv"):
        keep.add(norm_path(p))

    return keep


def build_manifest() -> pd.DataFrame:
    active_map = build_active_ai_map()

    active_files = set()
    for packet_id, ai_json in active_map.items():
        active_files.update(related_active_files(Path(ai_json)))

    rows = []

    for path in sorted(AI_DIR.glob("**/*")):
        if not path.is_file():
            continue

        packet_id = packet_id_from_path(path)
        fclass = classify_file(path)
        path_str = str(path)
        path_norm = norm_path(path)

        is_active = path_norm in active_files
        is_active_ai_json = active_map.get(packet_id, "") == path_norm

        proposed_action = "KEEP"
        reason = "active_or_noncleanup_file"

        if is_active_ai_json:
            proposed_action = "KEEP_ACTIVE_VALIDATED_AI_JSON"
            reason = "latest_PASS_validation_points_to_this_ai_json"
        elif is_active:
            proposed_action = "KEEP_ACTIVE_ASSOCIATED_FILE"
            reason = "associated_with_latest_active_ai_output_or_qc"
        elif fclass == "chunk_intermediate":
            proposed_action = "ARCHIVE_SUPERSEDED"
            reason = "chunk_intermediate_output_not_final"
        elif fclass in {
            "one_shot_ai_json",
            "chunked_merged_incomplete_or_superseded_ai_json",
            "samplemap_completed_ai_json",
            "samplemap_rebuilt_ai_json",
            "samplemap_biokey_rebuilt_ai_json",
            "semantic_stage_corrected_ai_json",
            "chunked_merged_completed_ai_json",
        }:
            if packet_id in active_map:
                proposed_action = "ARCHIVE_SUPERSEDED"
                reason = "packet_has_different_latest_PASS_ai_json"
            else:
                proposed_action = "KEEP_UNVALIDATED_OR_ATTENTION"
                reason = "no_latest_PASS_output_for_packet"
        elif fclass in {"raw_response", "prompt", "audit"}:
            if packet_id in active_map:
                proposed_action = "ARCHIVE_SUPERSEDED"
                reason = "prompt_raw_audit_not_associated_with_latest_active_output"
            else:
                proposed_action = "KEEP_UNVALIDATED_OR_ATTENTION"
                reason = "packet_not_yet_latest_PASS"
        else:
            proposed_action = "KEEP"
            reason = "not_an_ai_output_cleanup_target"

        rows.append({
            "packet_id": packet_id,
            "path": path_str,
            "file_class": fclass,
            "size_bytes": path.stat().st_size,
            "modified_time": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            "active_ai_json_for_packet": active_map.get(packet_id, ""),
            "is_active_file": is_active,
            "proposed_action": proposed_action,
            "reason": reason,
        })

    return pd.DataFrame(rows)


def execute_archive(manifest: pd.DataFrame, archive_dir: Path) -> pd.DataFrame:
    archive_dir.mkdir(parents=True, exist_ok=True)

    updated = manifest.copy()
    updated["archive_path"] = ""
    updated["move_status"] = ""

    targets = updated[updated["proposed_action"] == "ARCHIVE_SUPERSEDED"].copy()

    for idx, row in targets.iterrows():
        src = Path(row["path"])
        if not src.exists() or not src.is_file():
            updated.loc[idx, "move_status"] = "missing_source"
            continue

        rel = src.relative_to(AI_DIR)
        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            updated.loc[idx, "move_status"] = "destination_exists_skipped"
            updated.loc[idx, "archive_path"] = str(dest)
            continue

        shutil.move(str(src), str(dest))
        updated.loc[idx, "move_status"] = "moved"
        updated.loc[idx, "archive_path"] = str(dest)

    return updated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Actually move ARCHIVE_SUPERSEDED files.")
    args = ap.parse_args()

    HOUSEKEEP_DIR.mkdir(parents=True, exist_ok=True)

    stamp = timestamp()
    manifest = build_manifest()

    dry_path = HOUSEKEEP_DIR / f"housekeeping_manifest.{stamp}.tsv"
    manifest.to_csv(dry_path, sep="\t", index=False)

    archive_dir = ARCHIVE_ROOT / stamp

    if args.execute:
        executed = execute_archive(manifest, archive_dir)
        exec_path = HOUSEKEEP_DIR / f"housekeeping_manifest_executed.{stamp}.tsv"
        executed.to_csv(exec_path, sep="\t", index=False)
        out_path = exec_path
    else:
        out_path = dry_path

    print("Housekeeping mode:", "EXECUTE" if args.execute else "DRY-RUN")
    print("Manifest:", out_path)
    if args.execute:
        print("Archive dir:", archive_dir)

    print()
    print("Proposed actions:")
    print(manifest["proposed_action"].value_counts().to_string())

    print()
    print("By file class and action:")
    print(
        manifest.groupby(["file_class", "proposed_action"])
        .size()
        .reset_index(name="n")
        .to_string(index=False)
    )

    print()
    print("Archive candidates:")
    cols = ["packet_id", "file_class", "proposed_action", "reason", "path"]
    x = manifest[manifest["proposed_action"] == "ARCHIVE_SUPERSEDED"][cols]
    if x.empty:
        print("None")
    else:
        print(x.head(80).to_string(index=False))


if __name__ == "__main__":
    main()
