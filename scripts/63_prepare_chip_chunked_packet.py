#!/usr/bin/env python3
"""
Prepare chunked ChIP AI packet JSONs/tables for one large packet.

No API calls.

Strategy:
  - Read original packet JSON/table.
  - Partition source rows exactly once.
  - Prefer not to split biological groups: role + target + stage + condition.
  - Write chunk packet tables and JSONs.
  - Write chunk queue and plan.
  - Chunk outputs can later be run with the existing AI runner.

Default target:
  PMID_35288749__BIOPROJECT_PRJNA765872
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import pandas as pd


QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets")


def clean(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def safe_slug(x, max_len=90):
    x = clean(x)
    x = re.sub(r"[^A-Za-z0-9._-]+", "_", x).strip("_")
    return x[:max_len]


def join_unique(vals, max_len=500):
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    return "; ".join(xs)[:max_len]


def make_group_key(row):
    # Target-centered chunking:
    # Keep all rows for the same target/factor together when possible.
    # Stage/condition should stay inside the target chunk rather than splitting the same AP2
    # across multiple chunks. Control reuse is handled later by Target_Control_Map.
    target = clean(row.get("target_clean", row.get("Target", ""))) or "unknown_target"
    return f"{target}"


def split_large_group(df, max_rows):
    chunks = []
    for i in range(0, len(df), max_rows):
        chunks.append(df.iloc[i:i + max_rows].copy())
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", default="PMID_35288749__BIOPROJECT_PRJNA765872")
    ap.add_argument("--queue", default=str(QUEUE))
    ap.add_argument("--chunk-size", type=int, default=45)
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()

    packet_id = args.packet_id
    queue = pd.read_csv(args.queue, sep="\t", dtype=str).fillna("")

    row = queue[queue["packet_id"] == packet_id]
    if row.empty:
        raise SystemExit(f"Packet not found in queue: {packet_id}")

    row = row.iloc[0]
    packet_json = Path(clean(row["packet_json"]))
    packet_table = Path(clean(row["packet_table"]))

    if not packet_json.exists():
        raise SystemExit(f"Missing packet JSON: {packet_json}")
    if not packet_table.exists():
        raise SystemExit(f"Missing packet table: {packet_table}")

    obj = json.loads(packet_json.read_text())
    table = pd.read_csv(packet_table, sep="\t", dtype=str).fillna("")

    if "source_row_id" not in table.columns:
        raise SystemExit("Packet table lacks source_row_id")

    if not table["source_row_id"].map(clean).is_unique:
        raise SystemExit("source_row_id is not unique in original packet table")

    out = Path(args.out_dir) / packet_id
    json_dir = out / "chunk_json"
    table_dir = out / "chunk_tables"
    json_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)

    table["chunk_group_key"] = table.apply(make_group_key, axis=1)

    group_rows = []
    groups = []
    for key, g in table.groupby("chunk_group_key", dropna=False):
        g = g.copy()
        group_rows.append({
            "chunk_group_key": key,
            "n_rows": len(g),
            "roles": join_unique(g.get("sample_role_prelim", "")),
            "targets": join_unique(g.get("target_clean", g.get("Target", ""))),
            "stages": join_unique(g.get("stage_combined", "")),
            "conditions": join_unique(g.get("condition_context", "")),
            "runs": join_unique(g.get("Run", ""), 1000),
        })

        if len(g) > args.chunk_size:
            groups.extend(split_large_group(g, args.chunk_size))
        else:
            groups.append(g)

    # Greedy bin packing of groups into chunks by ROW COUNT, not number of groups.
    groups = sorted(groups, key=len, reverse=True)
    chunks = []  # each item: {"parts": [DataFrame], "n_rows": int}

    for g in groups:
        placed = False

        # Prefer existing chunks with room, smallest remaining capacity after placement.
        candidate_indices = []
        for i, ch in enumerate(chunks):
            projected = ch["n_rows"] + len(g)
            if projected <= args.chunk_size:
                candidate_indices.append((args.chunk_size - projected, i))

        if candidate_indices:
            _, best_i = sorted(candidate_indices)[0]
            chunks[best_i]["parts"].append(g)
            chunks[best_i]["n_rows"] += len(g)
            placed = True

        if not placed:
            chunks.append({"parts": [g], "n_rows": len(g)})

    # Convert to list-of-parts for downstream code.
    chunks = [ch["parts"] for ch in chunks]

    chunk_queue_rows = []
    chunk_plan_rows = []
    assigned_ids = []

    for idx, parts in enumerate(chunks, start=1):
        chunk_table = pd.concat(parts, axis=0).copy()
        chunk_table = chunk_table.sort_values(["chunk_group_key", "source_row_id"])
        assigned_ids.extend(chunk_table["source_row_id"].map(clean).tolist())

        chunk_packet_id = f"{packet_id}__CHUNK_{idx:03d}"
        chunk_table_path = table_dir / f"{chunk_packet_id}.rowwise_evidence.tsv"
        chunk_json_path = json_dir / f"{chunk_packet_id}.json"

        chunk_table.to_csv(chunk_table_path, sep="\t", index=False)

        chunk_obj = dict(obj)
        chunk_obj["packet_id"] = chunk_packet_id
        chunk_obj["parent_packet_id"] = packet_id
        chunk_obj["sidecar_rowwise_evidence_table"] = str(chunk_table_path)
        chunk_obj.setdefault("chip_context", {})
        chunk_obj["chip_context"] = dict(chunk_obj["chip_context"])
        chunk_obj["chip_context"]["chunking"] = {
            "is_chunk": True,
            "parent_packet_id": packet_id,
            "chunk_index": idx,
            "n_chunks": len(chunks),
            "n_rows_in_chunk": len(chunk_table),
            "rule": "partition original source rows exactly once; group by preliminary role, target, stage, condition where possible",
        }
        chunk_obj["sample_label_groups"] = []

        chunk_json_path.write_text(json.dumps(chunk_obj, indent=2))

        chunk_queue_rows.append({
            **row.to_dict(),
            "packet_id": chunk_packet_id,
            "parent_packet_id": packet_id,
            "n_rows": len(chunk_table),
            "packet_json": str(chunk_json_path),
            "packet_table": str(chunk_table_path),
            "assay_aware_recommended_action": "run_chip_ai_chunk",
        })

        chunk_plan_rows.append({
            "parent_packet_id": packet_id,
            "chunk_packet_id": chunk_packet_id,
            "chunk_index": idx,
            "n_rows": len(chunk_table),
            "roles": join_unique(chunk_table.get("sample_role_prelim", "")),
            "targets": join_unique(chunk_table.get("target_clean", chunk_table.get("Target", "")), 1000),
            "stages": join_unique(chunk_table.get("stage_combined", "")),
            "conditions": join_unique(chunk_table.get("condition_context", "")),
            "n_groups": chunk_table["chunk_group_key"].nunique(),
            "chunk_json": str(chunk_json_path),
            "chunk_table": str(chunk_table_path),
        })

    assigned_set = set(assigned_ids)
    expected_set = set(table["source_row_id"].map(clean))

    missing = sorted(expected_set - assigned_set)
    extra = sorted(assigned_set - expected_set)
    duplicates = sorted([sid for sid, n in pd.Series(assigned_ids).value_counts().items() if n > 1])

    chunk_queue = pd.DataFrame(chunk_queue_rows)
    chunk_plan = pd.DataFrame(chunk_plan_rows)
    group_df = pd.DataFrame(group_rows)

    chunk_queue_path = out / f"{packet_id}.chunk_queue.tsv"
    chunk_plan_path = out / f"{packet_id}.chunk_plan.tsv"
    group_path = out / f"{packet_id}.chunk_groups.tsv"

    chunk_queue.to_csv(chunk_queue_path, sep="\t", index=False)
    chunk_plan.to_csv(chunk_plan_path, sep="\t", index=False)
    group_df.to_csv(group_path, sep="\t", index=False)

    report = []
    report.append("# ChIP Chunked Packet Preparation Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append(f"- parent packet: {packet_id}")
    report.append(f"- parent rows: {len(table)}")
    report.append(f"- chunk size target: {args.chunk_size}")
    report.append(f"- chunks created: {len(chunk_plan)}")
    report.append(f"- assigned rows: {len(assigned_ids)}")
    report.append(f"- unique assigned rows: {len(assigned_set)}")
    report.append(f"- missing rows: {len(missing)}")
    report.append(f"- extra rows: {len(extra)}")
    report.append(f"- duplicate assigned rows: {len(duplicates)}")
    report.append("")
    report.append("## Chunk plan")
    report.append("")
    for _, r in chunk_plan.iterrows():
        report.append(
            f"- {r['chunk_packet_id']}: rows={r['n_rows']}; "
            f"groups={r['n_groups']}; roles={r['roles']}; targets={str(r['targets'])[:180]}"
        )
    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [chunk_queue_path, chunk_plan_path, group_path, json_dir, table_dir]:
        report.append(f"- `{p}`")

    report_path = out / f"{packet_id}.CHIP_CHUNK_PREP_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", chunk_queue_path)
    print("Wrote:", chunk_plan_path)
    print("Wrote:", group_path)
    print("Wrote:", report_path)
    print()
    print(pd.DataFrame([{
        "parent_packet_id": packet_id,
        "parent_rows": len(table),
        "chunks": len(chunk_plan),
        "assigned_rows": len(assigned_ids),
        "unique_assigned_rows": len(assigned_set),
        "missing": len(missing),
        "extra": len(extra),
        "duplicates": len(duplicates),
    }]).to_string(index=False))
    print()
    print(chunk_plan[["chunk_packet_id", "n_rows", "roles", "targets", "n_groups"]].to_string(index=False))

    if missing or extra or duplicates:
        raise SystemExit("Chunk assignment is not a clean partition.")


if __name__ == "__main__":
    main()
