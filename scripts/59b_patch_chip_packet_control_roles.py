#!/usr/bin/env python3
"""
Patch ChIP AI packet tables/JSONs with deterministic preliminary sample roles.

Why:
  Some ChIP rows have Target set to a factor/mark but background_sample=input.
  Those rows are biologically input/background rows, even if earlier chip_role=chip_ip.
  We preserve original chip_role but add explicit:
    - sample_role_prelim
    - chip_role_original
    - chip_role_for_ai
    - is_background_or_control_for_ai
    - matched_background_run_ids_prelim

Also appends these fields into detected_control_terms and
public_metadata_evidence_compact so the existing AI prompt compacting logic sees them.

Inputs:
  outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv
  packet_tables/*.rowwise_evidence.tsv
  packet_json/*.json

Outputs:
  updated packet tables and packet JSONs in place
  outputs/06_CHIP_AI_ASSIST/10_preflight_qc/chip_packet_control_role_patch_report.tsv
"""

from pathlib import Path
from datetime import datetime
import json
import re
import pandas as pd

QUEUE = Path("outputs/06_CHIP_AI_ASSIST/09_chip_ai_packets/chip_ai_packet_queue.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/10_preflight_qc")
OUT.mkdir(parents=True, exist_ok=True)

def clean(x):
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s

def split_runs(x):
    x = clean(x)
    if not x:
        return []
    return [p for p in re.split(r"[;,|]\s*|\s+", x) if p and p.lower() not in {"none", "na", "nan"}]

def prelim_role(row):
    target = clean(row.get("Target", row.get("target_clean", ""))).lower()
    target_clean = clean(row.get("target_clean", "")).lower()
    bg = clean(row.get("background_sample", "")).lower()

    raw = " ".join([
        target, target_clean, bg,
        clean(row.get("raw_metadata_joined", "")).lower(),
        clean(row.get("public_metadata_evidence_compact", "")).lower(),
    ])

    # Important: underscores occur frequently in sample names, e.g. 10h_OFF_Input.
    # Regex word boundaries do not split on underscores, so normalize separators first.
    raw_tokens = re.sub(r"[^a-z0-9]+", " ", raw.replace("_", " ")).lower()
    toks = set(raw_tokens.split())

    if "igg" in toks or re.search(r"\bigg\b", raw_tokens):
        return "IgG"

    if (
        "input" in toks
        or "inputdna" in toks
        or "input" in bg
        or re.search(r"(^|[^a-z0-9])input([^a-z0-9]|$)", raw_tokens)
    ):
        return "input"

    if "untagged" in toks or "parental" in toks or "no tag" in raw_tokens:
        return "untagged_control"

    if "mock" in toks:
        return "mock"

    if target in {"control", "background"} or bg in {"control", "background"}:
        return "control_sample"

    return "target_ip"

def control_type(role):
    if role == "input":
        return "input"
    if role == "IgG":
        return "IgG"
    if role == "untagged_control":
        return "untagged_control"
    if role == "mock":
        return "mock"
    if role == "control_sample":
        return "control"
    return ""

def append_term(existing, *terms):
    xs = []
    for x in [existing, *terms]:
        x = clean(x)
        if not x:
            continue
        for part in x.split(";"):
            part = clean(part)
            if part and part not in xs:
                xs.append(part)
    return "; ".join(xs)

def append_compact(existing, additions):
    existing = clean(existing)
    add = " | ".join(f"{k}={v}" for k, v in additions.items() if clean(v))
    if existing and add:
        return existing + " | " + add
    return existing or add

def regenerate_sample_groups(t):
    group_cols = [
        "target_clean", "sample_role_prelim",
        "stage_combined", "strain_context", "condition_context"
    ]
    for c in group_cols:
        if c not in t.columns:
            t[c] = ""

    groups = []
    for keys, g in t.groupby(group_cols, dropna=False):
        target, role, stage, strain, condition = [clean(x) for x in keys]
        groups.append({
            "target_or_antibody_or_tag": target,
            "sample_role_prelim": role,
            "chip_role_for_ai": role,
            "stage_or_timepoint": stage,
            "strain": strain,
            "condition": condition,
            "n_rows": int(len(g)),
            "runs": list(g["Run"].head(25)) if "Run" in g.columns else [],
            "source_row_ids": list(g["source_row_id"].head(25)) if "source_row_id" in g.columns else [],
        })
    return sorted(groups, key=lambda d: (-d["n_rows"], d["sample_role_prelim"], d["target_or_antibody_or_tag"]))

def main():
    if not QUEUE.exists():
        raise SystemExit(f"Missing queue: {QUEUE}")

    q = pd.read_csv(QUEUE, sep="\t", dtype=str).fillna("")
    report = []

    for _, row in q.iterrows():
        packet_id = clean(row["packet_id"])
        table_path = Path(clean(row["packet_table"]))
        json_path = Path(clean(row["packet_json"]))

        if not table_path.exists():
            report.append({"packet_id": packet_id, "status": "missing_table"})
            continue
        if not json_path.exists():
            report.append({"packet_id": packet_id, "status": "missing_json"})
            continue

        t = pd.read_csv(table_path, sep="\t", dtype=str).fillna("")

        if "chip_role_original" not in t.columns:
            t["chip_role_original"] = t.get("chip_role", "")

        roles = [prelim_role(r) for _, r in t.iterrows()]
        t["sample_role_prelim"] = roles
        t["chip_role_for_ai"] = roles
        t["control_type_prelim"] = [control_type(r) for r in roles]
        t["is_background_or_control_for_ai"] = [
            "true" if r in {"input", "IgG", "untagged_control", "mock", "control_sample"} else "false"
            for r in roles
        ]

        bg_runs = []
        for _, r in t.iterrows():
            role = clean(r["sample_role_prelim"])
            if role == "target_ip":
                runs = split_runs(r.get("assigned_control1", "")) + split_runs(r.get("assigned_control2", ""))
                bg_runs.append(";".join(runs))
            else:
                bg_runs.append("")
        t["matched_background_run_ids_prelim"] = bg_runs

        # Make sure existing prompt compacting sees the new role info.
        if "detected_control_terms" not in t.columns:
            t["detected_control_terms"] = ""

        t["detected_control_terms"] = [
            append_term(
                old,
                f"sample_role_prelim={role}",
                f"control_type_prelim={ct}" if ct else "",
                f"matched_background_run_ids_prelim={mb}" if mb else "",
                f"background_sample={clean(bg)}" if clean(bg) else "",
            )
            for old, role, ct, mb, bg in zip(
                t["detected_control_terms"],
                t["sample_role_prelim"],
                t["control_type_prelim"],
                t["matched_background_run_ids_prelim"],
                t.get("background_sample", [""] * len(t)),
            )
        ]

        if "public_metadata_evidence_compact" not in t.columns:
            t["public_metadata_evidence_compact"] = ""

        t["public_metadata_evidence_compact"] = [
            append_compact(old, {
                "sample_role_prelim": role,
                "chip_role_for_ai": role,
                "control_type_prelim": ct,
                "matched_background_run_ids_prelim": mb,
            })
            for old, role, ct, mb in zip(
                t["public_metadata_evidence_compact"],
                t["sample_role_prelim"],
                t["control_type_prelim"],
                t["matched_background_run_ids_prelim"],
            )
        ]

        t.to_csv(table_path, sep="\t", index=False)

        obj = json.loads(json_path.read_text())
        obj["sample_label_groups"] = regenerate_sample_groups(t)
        obj.setdefault("chip_context", {})
        obj["chip_context"]["control_role_patch"] = {
            "applied": True,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rule": "background_sample/input/IgG/mock/untagged evidence creates sample_role_prelim independent of Target text",
            "n_target_ip": int((t["sample_role_prelim"] == "target_ip").sum()),
            "n_input": int((t["sample_role_prelim"] == "input").sum()),
            "n_IgG": int((t["sample_role_prelim"] == "IgG").sum()),
            "n_other_control": int(t["sample_role_prelim"].isin(["untagged_control", "mock", "control_sample"]).sum()),
        }
        json_path.write_text(json.dumps(obj, indent=2))

        report.append({
            "packet_id": packet_id,
            "status": "patched",
            "n_rows": len(t),
            "n_target_ip": int((t["sample_role_prelim"] == "target_ip").sum()),
            "n_input": int((t["sample_role_prelim"] == "input").sum()),
            "n_IgG": int((t["sample_role_prelim"] == "IgG").sum()),
            "n_other_control": int(t["sample_role_prelim"].isin(["untagged_control", "mock", "control_sample"]).sum()),
        })

    rep = pd.DataFrame(report)
    out = OUT / "chip_packet_control_role_patch_report.tsv"
    rep.to_csv(out, sep="\t", index=False)

    print("Wrote:", out)
    print()
    print(rep.to_string(index=False))

if __name__ == "__main__":
    main()
