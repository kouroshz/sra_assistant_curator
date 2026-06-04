#!/usr/bin/env python3
"""
Patch ChIP AI rowwise roles using deterministic packet-table prelim roles.

Use only when:
  - rowwise_suggestions cover every source_row_id exactly once
  - failures are missing/unknown/control_sample role mismatches
  - packet table has sample_role_prelim / chip_role_for_ai / matched_background_run_ids_prelim

This does NOT invent missing rowwise rows.
It only patches role/target/background fields for existing rowwise objects.
"""

from pathlib import Path
from datetime import datetime
import argparse
import json
import re
import pandas as pd


def clean(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def norm(x):
    return clean(x).lower().replace("-", "_").replace(" ", "_")


def safe_slug(x):
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", "_", x).strip("_")
    return x or "unknown"


def first_nonblank(*xs):
    for x in xs:
        x = clean(x)
        if x:
            return x
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-id", required=True)
    ap.add_argument("--ai-json", required=True)
    ap.add_argument("--queue", required=True)
    args = ap.parse_args()

    packet_id = args.packet_id
    ai_json = Path(args.ai_json)

    q = pd.read_csv(args.queue, sep="\t", dtype=str).fillna("")
    qq = q[q["packet_id"] == packet_id]
    if qq.empty:
        raise SystemExit(f"Packet not found in queue: {packet_id}")

    table_path = Path(clean(qq.iloc[0]["packet_table"]))
    table = pd.read_csv(table_path, sep="\t", dtype=str).fillna("")
    obj = json.loads(ai_json.read_text())

    rw = obj.get("rowwise_suggestions", []) or []
    expected_ids = set(table["source_row_id"].map(clean))
    observed_ids = [clean(r.get("source_row_id", "")) for r in rw]

    if set(observed_ids) != expected_ids or len(observed_ids) != len(expected_ids):
        raise SystemExit(
            f"Refusing role patch: rowwise coverage is not exact. "
            f"expected={len(expected_ids)} observed={len(observed_ids)} "
            f"missing={len(expected_ids - set(observed_ids))} extra={len(set(observed_ids) - expected_ids)}"
        )

    table_by_id = {clean(r["source_row_id"]): r for _, r in table.iterrows()}

    patched = []
    patch_counts = {
        "input_control_sample_to_input": 0,
        "unknown_blank_to_target_ip": 0,
        "target_or_background_filled": 0,
        "stage_strain_condition_filled": 0,
    }

    for r in rw:
        sid = clean(r.get("source_row_id", ""))
        t = table_by_id[sid]

        prelim_role = norm(t.get("sample_role_prelim", ""))
        ai_role = norm(r.get("suggested_sample_role", ""))

        row_patches = []

        target = first_nonblank(t.get("target_clean", ""), t.get("Target", ""))
        stage = clean(t.get("stage_combined", ""))
        strain = clean(t.get("strain_context", ""))
        condition = clean(t.get("condition_context", ""))
        bg = first_nonblank(
            t.get("matched_background_run_ids_prelim", ""),
            t.get("assigned_control1", ""),
            t.get("assigned_control2", ""),
            t.get("background_sample", ""),
        )

        if prelim_role == "input" and ai_role in {"control_sample", "unknown", ""}:
            r["suggested_sample_role"] = "input"
            r["suggested_target_or_antibody_or_tag"] = "not_applicable_or_unknown"
            r["suggested_comparator_or_background"] = "not_applicable"
            patch_counts["input_control_sample_to_input"] += 1
            row_patches.append(f"role:{ai_role or 'blank'}->input")

        elif prelim_role == "target_ip" and ai_role in {"unknown", "", "control_sample"}:
            r["suggested_sample_role"] = "target_ip"
            r["suggested_target_or_antibody_or_tag"] = target or "unknown"
            r["suggested_comparator_or_background"] = bg or "unknown"
            patch_counts["unknown_blank_to_target_ip"] += 1
            row_patches.append(f"role:{ai_role or 'blank'}->target_ip")

        # Fill missing/unknown target/background for target_ip rows from deterministic table.
        if norm(r.get("suggested_sample_role", "")) == "target_ip":
            if norm(r.get("suggested_target_or_antibody_or_tag", "")) in {"", "unknown"} and target:
                r["suggested_target_or_antibody_or_tag"] = target
                patch_counts["target_or_background_filled"] += 1
                row_patches.append("target_filled_from_table")

            if norm(r.get("suggested_comparator_or_background", "")) in {"", "unknown", "not_applicable", "na", "n_a"} and bg:
                r["suggested_comparator_or_background"] = bg
                patch_counts["target_or_background_filled"] += 1
                row_patches.append("background_filled_from_table")

        # Fill basic context if AI left it vague.
        if norm(r.get("suggested_stage_timepoint", "")) in {"", "unknown"} and stage:
            r["suggested_stage_timepoint"] = stage
            patch_counts["stage_strain_condition_filled"] += 1
            row_patches.append("stage_filled_from_table")

        if norm(r.get("suggested_strain", "")) in {"", "unknown"} and strain:
            r["suggested_strain"] = strain
            patch_counts["stage_strain_condition_filled"] += 1
            row_patches.append("strain_filled_from_table")

        if norm(r.get("suggested_condition", "")) in {"", "unknown"} and condition:
            r["suggested_condition"] = condition
            patch_counts["stage_strain_condition_filled"] += 1
            row_patches.append("condition_filled_from_table")

        # Stabilize class id after role patch.
        if row_patches:
            role = norm(r.get("suggested_sample_role", "")) or prelim_role or "unknown"
            scid = "_".join([
                safe_slug(r.get("suggested_target_or_antibody_or_tag", target)),
                safe_slug(r.get("suggested_stage_timepoint", stage)),
                safe_slug(r.get("suggested_strain", strain)),
                role,
            ])
            r["sample_class_id"] = scid
            r["suggestion_confidence"] = "medium"
            r["review_flag"] = "curator_check"
            old_ev = clean(r.get("suggestion_evidence", ""))
            r["suggestion_evidence"] = (
                old_ev + " | " if old_ev else ""
            ) + "Deterministic role patch from packet table: " + "; ".join(row_patches)

            patched.append({
                "source_row_id": sid,
                "Run": clean(t.get("Run", "")),
                "prelim_role": prelim_role,
                "original_ai_role": ai_role,
                "patched_ai_role": norm(r.get("suggested_sample_role", "")),
                "patches": "; ".join(row_patches),
            })

    obj["rowwise_suggestions"] = rw
    obj.setdefault("repair_audit", [])
    obj["repair_audit"].append({
        "repair_type": "patch_rowwise_roles_from_deterministic_prelim_table",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_ai_json": str(ai_json),
        "packet_table": str(table_path),
        "packet_id": packet_id,
        "patch_counts": patch_counts,
        "n_patched_rows": len(patched),
        "safety_rule": "Only applied because rowwise source_row_id coverage was exact; no rows invented.",
    })

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = ai_json.with_name(f"{packet_id}.ai_curation_rowwise_role_patched.{ts}.json")
    out_json.write_text(json.dumps(obj, indent=2))

    patch_tsv = ai_json.with_name(f"{packet_id}.rowwise_role_patch_audit.{ts}.tsv")
    pd.DataFrame(patched).to_csv(patch_tsv, sep="\t", index=False)

    print("Wrote patched JSON:", out_json)
    print("Wrote patch audit:", patch_tsv)
    print("Patch counts:", patch_counts)
    print("Patched rows:", len(patched))


if __name__ == "__main__":
    main()
