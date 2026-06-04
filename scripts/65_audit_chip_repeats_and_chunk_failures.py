#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import json
import pandas as pd

PARENT = "PMID_35288749__BIOPROJECT_PRJNA765872"
MAIN_QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
CHUNK_QUEUE = Path(f"outputs/06_CHIP_AI_ASSIST/16_chip_ai_chunked_packets/{PARENT}/{PARENT}.chunk_queue.tsv")
CHUNK_OUT = Path("outputs/06_CHIP_AI_ASSIST/17_chip_ai_chunk_actual_size30")
OUT = Path("outputs/06_CHIP_AI_ASSIST/19_chip_chunk_diagnostics")
OUT.mkdir(parents=True, exist_ok=True)

def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

def latest_json(packet_id):
    d = CHUNK_OUT / packet_id
    hits = sorted(
        list(d.glob(f"{packet_id}.ai_curation_samplemap_rebuilt.*.json")) +
        list(d.glob(f"{packet_id}.ai_curation.*.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return hits[0] if hits else None

main_q = pd.read_csv(MAIN_QUEUE, sep="\t", dtype=str).fillna("")
parent_row = main_q[main_q["packet_id"] == PARENT].iloc[0]
parent_table = pd.read_csv(parent_row["packet_table"], sep="\t", dtype=str).fillna("")

rows = []

# Source-level repeats.
for col in ["source_row_id", "Run", "BioSample"]:
    if col in parent_table.columns:
        vc = parent_table[col].map(clean).value_counts()
        for val, n in vc.items():
            if val and n > 1:
                subset = parent_table[parent_table[col].map(clean) == val]
                rows.append({
                    "level": "parent_source_table",
                    "object": col,
                    "value": val,
                    "n": n,
                    "issue": "repeated_source_value",
                    "details": "; ".join(subset.get("source_row_id", pd.Series()).map(clean).tolist()[:20]),
                })

# Target/control reuse candidates.
for col in ["matched_background_run_ids_prelim", "assigned_control1", "assigned_control2"]:
    if col in parent_table.columns:
        expanded = []
        for _, r in parent_table.iterrows():
            sid = clean(r.get("source_row_id", ""))
            val = clean(r.get(col, ""))
            if not val:
                continue
            for part in val.replace("|", ";").replace(",", ";").split(";"):
                part = clean(part)
                if part:
                    expanded.append((part, sid))
        counts = Counter(x for x, _ in expanded)
        for run, n in counts.items():
            if n > 1:
                sids = [sid for x, sid in expanded if x == run]
                rows.append({
                    "level": "parent_source_table",
                    "object": col,
                    "value": run,
                    "n": n,
                    "issue": "control_reused_by_multiple_target_rows",
                    "details": "; ".join(sids[:30]),
                })

# Chunk output mismatches.
if CHUNK_QUEUE.exists():
    cq = pd.read_csv(CHUNK_QUEUE, sep="\t", dtype=str).fillna("")
    for _, r in cq.iterrows():
        pid = clean(r["packet_id"])
        t = pd.read_csv(r["packet_table"], sep="\t", dtype=str).fillna("")
        expected = set(t["source_row_id"].map(clean))
        p = latest_json(pid)
        if not p:
            rows.append({
                "level": "chunk_ai_output",
                "object": pid,
                "value": "",
                "n": 0,
                "issue": "missing_ai_json",
                "details": "",
            })
            continue
        obj = json.loads(p.read_text())
        rw = obj.get("rowwise_suggestions", []) or []
        ids = [clean(x.get("source_row_id", "")) for x in rw]
        observed = set(ids)
        extras = sorted(observed - expected)
        missing = sorted(expected - observed)
        dups = sorted([sid for sid, n in Counter(ids).items() if sid and n > 1])
        rows.append({
            "level": "chunk_ai_output",
            "object": pid,
            "value": str(p),
            "n": len(rw),
            "issue": "rowwise_coverage_summary",
            "details": f"expected={len(expected)} observed={len(rw)} missing={len(missing)} extra={len(extras)} duplicates={len(dups)}",
        })
        for sid in missing:
            rows.append({"level":"chunk_ai_output","object":pid,"value":sid,"n":1,"issue":"missing_source_row_id","details":""})
        for sid in extras:
            rows.append({"level":"chunk_ai_output","object":pid,"value":sid,"n":1,"issue":"extra_source_row_id","details":""})
        for sid in dups:
            rows.append({"level":"chunk_ai_output","object":pid,"value":sid,"n":ids.count(sid),"issue":"duplicate_ai_rowwise_source_row_id","details":""})

df = pd.DataFrame(rows)
out = OUT / f"{PARENT}.repeat_and_chunk_failure_audit.tsv"
df.to_csv(out, sep="\t", index=False)

print("Wrote:", out)
if df.empty:
    print("No repeats/mismatches found.")
else:
    print(df.groupby(["level", "issue"]).size().reset_index(name="n").to_string(index=False))
