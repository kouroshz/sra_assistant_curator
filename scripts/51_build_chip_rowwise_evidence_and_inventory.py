#!/usr/bin/env python3
"""
Build ChIP rowwise evidence and inventory tables.

This is ChIP-specific and read-only with respect to the master sheet.

Inputs:
  data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx

Outputs:
  outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/
    chip_rowwise_evidence.tsv
    chip_group_inventory_by_paper_bioproject.tsv
    chip_target_inventory.tsv
    chip_control_qc_by_group.tsv
    chip_groups_for_policy_review.tsv
    CHIP_ROWWISE_EVIDENCE_REPORT.md

Important ChIP assumptions:
  - paper_link is treated as the publication/PMID field.
  - Target is ChIP target / antibody / mark / factor.
  - background_sample + assigned_control1/2 are the main background/control fields.
  - Target=Input or Target blank with input/control evidence is a background/control row, not a biological target.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import re
import pandas as pd


IN_XLSX = Path("data/plasmodium_chip_metadata_public_and_Manish_replicates_2025-03-30_V10.xlsx")
SHEET = "Sheet1"
OUT = Path("outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence")
OUT.mkdir(parents=True, exist_ok=True)


CHIP_COLS = {
    "run": "Run",
    "bioproject": "BioProject",
    "biosample": "Biosample",
    "pmid": "paper_link",
    "target": "Target",
    "background_sample": "background_sample",
    "assigned_control1": "assigned_control1",
    "assigned_control2": "assigned_control2",
    "stage_primary": "Cell_Cycle_Stage",
    "stage_secondary": "Life_Stage",
    "strain": "Strain",
    "substrain": "Substrain",
    "condition1": "Condition1",
    "condition2": "Condition2",
    "condition3": "Condition3",
    "replicate": "replicate_number",
    "notes": "Notes",
    "raw_metadata_col1": "raw_metadata_col1",
    "raw_metadata_col2": "raw_metadata_col2",
    "raw_metadata_col3": "raw_metadata_col3",
    "last_author": "last_author",
}


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def norm_text(x: str) -> str:
    return re.sub(r"\s+", " ", clean(x))


def norm_key(x: str) -> str:
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", "_", x)
    return x.strip("_")


def short_hash(*parts: str, n: int = 10) -> str:
    s = "||".join(clean(p) for p in parts)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def split_controls(x: str) -> list[str]:
    x = clean(x)
    if not x:
        return []
    parts = re.split(r"[;,|]\s*|\s+", x)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in {"nan", "none", "na"}]


def target_type(target: str, background_sample: str, raw_joined: str) -> str:
    t = clean(target)
    tl = t.lower()
    bg = clean(background_sample).lower()
    raw = clean(raw_joined).lower()
    combined = " ".join([tl, bg, raw])

    # Background/control-like rows.
    if tl in {"input", "input_dna", "input dna", "control", "igg", "mock", "background"}:
        return "background_control"
    if not t and re.search(r"\b(input|igg|mock|control|background)\b", combined):
        return "background_control"

    if not t:
        return "unknown_blank_target"

    # Epitope tags that are not the biological factor by themselves.
    if tl in {"ha", "gfp", "myc", "flag", "ty", "ty1", "v5", "3xha", "3xflag"}:
        return "epitope_tag_only"

    # Histone marks and variants.
    if re.match(r"^h[1-4](k|ac|\.|$)", tl) or re.search(r"h[234]k\d+|h3k\d+|h2a|h2b|h3|h4", tl):
        if re.search(r"me\d|ac|ub|ph|k\d+", tl):
            return "histone_modification"
        if re.search(r"h2a\.z|h2b\.z|h3\.3|h3core|h3_core", tl):
            return "histone_variant_or_core"
        return "histone_or_histone_related"

    # Common TF/chromatin factor naming.
    if re.search(r"\b(ap2|pfap2|bdp|morc|hp1|sir2|gcn5|iswi|hdac|hdp|hmgb|taf|arp|brd|bromodomain|znf|myb|myst)\b", tl):
        return "tf_or_chromatin_factor"

    # Some targets are gene-like names or constructs.
    if re.search(r"pf3d7|pf[a-z0-9_-]+|gdv|var|glm", tl):
        return "candidate_factor_or_locus"

    return "other_target"


def is_background_control_row(target: str, background_sample: str, raw_joined: str) -> bool:
    tt = target_type(target, background_sample, raw_joined)
    return tt == "background_control"


def make_compact_evidence(row: pd.Series, present_cols: dict[str, str]) -> str:
    fields = []
    for logical, col in present_cols.items():
        val = clean(row.get(col, ""))
        if val:
            fields.append(f"{logical}={val}")
    return " | ".join(fields)


def main():
    if not IN_XLSX.exists():
        raise SystemExit(f"Missing input file: {IN_XLSX}")

    df = pd.read_excel(IN_XLSX, sheet_name=SHEET, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]

    missing = [v for v in CHIP_COLS.values() if v not in df.columns]
    if missing:
        print("WARNING: missing expected columns:")
        for m in missing:
            print("  -", m)

    present = {k: v for k, v in CHIP_COLS.items() if v in df.columns}

    required = ["run", "bioproject"]
    for r in required:
        if r not in present:
            raise SystemExit(f"Required column missing: {CHIP_COLS[r]}")

    # Normalize core fields.
    out = pd.DataFrame()
    out["source_row_id"] = [
        f"CHIP{i+1:06d}_{short_hash(row.get(present.get('run',''), ''), row.get(present.get('biosample',''), ''), row.get(present.get('bioproject',''), ''))}"
        for i, row in df.iterrows()
    ]

    for logical, col in present.items():
        out[logical] = df[col].map(clean)

    # Ensure all expected logical columns exist.
    for logical in CHIP_COLS:
        if logical not in out.columns:
            out[logical] = ""

    # Publication key.
    out["publication_key"] = out["pmid"]
    out["has_publication_key"] = out["publication_key"].map(lambda x: clean(x) != "")

    # Raw joined evidence for classifiers.
    raw_cols = [c for c in ["raw_metadata_col1", "raw_metadata_col2", "raw_metadata_col3", "notes"] if c in out.columns]
    out["raw_metadata_joined"] = out[raw_cols].agg(" | ".join, axis=1) if raw_cols else ""

    out["target_clean"] = out["target"].map(norm_text)
    out["target_key"] = out["target_clean"].map(norm_key)
    out["target_type"] = [
        target_type(t, bg, raw)
        for t, bg, raw in zip(out["target"], out["background_sample"], out["raw_metadata_joined"])
    ]
    out["is_background_control_row"] = [
        is_background_control_row(t, bg, raw)
        for t, bg, raw in zip(out["target"], out["background_sample"], out["raw_metadata_joined"])
    ]

    out["chip_role"] = out.apply(
        lambda r: "background_control" if r["is_background_control_row"] else "chip_ip",
        axis=1,
    )

    # Stage/strain/condition keys.
    out["stage_combined"] = (
        out["stage_primary"].where(out["stage_primary"].str.strip() != "", out["stage_secondary"])
    )
    out["stage_key"] = out["stage_combined"].map(norm_key)
    out["strain_context"] = out.apply(
        lambda r: "; ".join([x for x in [r["strain"], r["substrain"]] if clean(x)]),
        axis=1,
    )
    out["strain_key"] = out["strain_context"].map(norm_key)
    out["condition_context"] = out.apply(
        lambda r: "; ".join([x for x in [r["condition1"], r["condition2"], r["condition3"]] if clean(x)]),
        axis=1,
    )
    out["condition_key"] = out["condition_context"].map(norm_key)

    # Control parsing and validation.
    run_set = set(out["run"])
    out["assigned_control1_list"] = out["assigned_control1"].map(lambda x: ";".join(split_controls(x)))
    out["assigned_control2_list"] = out["assigned_control2"].map(lambda x: ";".join(split_controls(x)))
    out["assigned_control_all"] = out.apply(
        lambda r: ";".join(split_controls(r["assigned_control1"]) + split_controls(r["assigned_control2"])),
        axis=1,
    )

    def control_present_list(ctrls: str) -> str:
        vals = split_controls(ctrls)
        if not vals:
            return ""
        return ";".join([f"{c}:{'present' if c in run_set else 'missing'}" for c in vals])

    out["assigned_control_presence"] = out["assigned_control_all"].map(control_present_list)
    out["n_assigned_controls"] = out["assigned_control_all"].map(lambda x: len(split_controls(x)))
    out["n_missing_assigned_controls"] = out["assigned_control_all"].map(
        lambda x: sum(1 for c in split_controls(x) if c not in run_set)
    )

    # Compact evidence.
    compact_cols = {
        "Run": "run",
        "BioProject": "bioproject",
        "Biosample": "biosample",
        "paper_link": "pmid",
        "Target": "target",
        "background_sample": "background_sample",
        "assigned_control1": "assigned_control1",
        "assigned_control2": "assigned_control2",
        "Strain": "strain",
        "Substrain": "substrain",
        "Cell_Cycle_Stage": "stage_primary",
        "Life_Stage": "stage_secondary",
        "Condition1": "condition1",
        "Condition2": "condition2",
        "Condition3": "condition3",
        "replicate_number": "replicate",
        "last_author": "last_author",
        "Notes": "notes",
    }
    compact_present = {k: CHIP_COLS[v] for k, v in compact_cols.items() if v in CHIP_COLS and CHIP_COLS[v] in df.columns}
    # flip to use actual original row
    out["chip_public_metadata_evidence_compact"] = [
        make_compact_evidence(df.loc[i], {k: col for k, col in compact_present.items()})
        for i in df.index
    ]

    # Save rowwise evidence.
    rowwise_path = OUT / "chip_rowwise_evidence.tsv"
    out.to_csv(rowwise_path, sep="\t", index=False)

    # Group inventory by publication/BioProject.
    group_keys = ["publication_key", "bioproject"]
    group = (
        out.groupby(group_keys, dropna=False)
        .agg(
            n_rows=("source_row_id", "count"),
            n_runs=("run", "nunique"),
            n_chip_ip_rows=("chip_role", lambda s: int((s == "chip_ip").sum())),
            n_background_control_rows=("chip_role", lambda s: int((s == "background_control").sum())),
            n_unique_targets=("target_key", lambda s: int(s[s != ""].nunique())),
            targets=("target_clean", lambda s: "; ".join(sorted(set([x for x in s if clean(x)])))[:1000]),
            target_types=("target_type", lambda s: "; ".join(sorted(set(s)))),
            n_rows_with_assigned_control=("n_assigned_controls", lambda s: int((s.astype(int) > 0).sum())),
            n_rows_with_missing_assigned_control=("n_missing_assigned_controls", lambda s: int((s.astype(int) > 0).sum())),
            stages=("stage_combined", lambda s: "; ".join(sorted(set([x for x in s if clean(x)])))[:1000]),
            strains=("strain_context", lambda s: "; ".join(sorted(set([x for x in s if clean(x)])))[:1000]),
            conditions=("condition_context", lambda s: "; ".join(sorted(set([x for x in s if clean(x)])))[:1000]),
            last_authors=("last_author", lambda s: "; ".join(sorted(set([x for x in s if clean(x)])))[:1000]),
        )
        .reset_index()
        .sort_values(["n_rows"], ascending=False)
    )
    group_path = OUT / "chip_group_inventory_by_paper_bioproject.tsv"
    group.to_csv(group_path, sep="\t", index=False)

    # Target inventory.
    target_inv = (
        out.groupby(["target_clean", "target_key", "target_type"], dropna=False)
        .agg(
            n_rows=("source_row_id", "count"),
            n_bioprojects=("bioproject", "nunique"),
            n_publication_keys=("publication_key", lambda s: int(s[s != ""].nunique())),
            example_bioprojects=("bioproject", lambda s: "; ".join(sorted(set([x for x in s if clean(x)]))[:10])),
        )
        .reset_index()
        .sort_values("n_rows", ascending=False)
    )
    target_path = OUT / "chip_target_inventory.tsv"
    target_inv.to_csv(target_path, sep="\t", index=False)

    # Control QC by group.
    control_qc = group[
        [
            "publication_key", "bioproject", "n_rows", "n_chip_ip_rows",
            "n_background_control_rows", "n_rows_with_assigned_control",
            "n_rows_with_missing_assigned_control", "n_unique_targets",
            "targets", "target_types"
        ]
    ].copy()
    control_qc["control_qc_status"] = control_qc.apply(
        lambda r:
            "missing_assigned_control_runs" if int(r["n_rows_with_missing_assigned_control"]) > 0 else
            "no_background_rows" if int(r["n_background_control_rows"]) == 0 and int(r["n_chip_ip_rows"]) > 0 else
            "no_assigned_controls" if int(r["n_rows_with_assigned_control"]) == 0 and int(r["n_chip_ip_rows"]) > 0 else
            "has_background_and_assigned_controls",
        axis=1,
    )
    control_qc_path = OUT / "chip_control_qc_by_group.tsv"
    control_qc.to_csv(control_qc_path, sep="\t", index=False)

    # Policy review groups.
    policy = control_qc.copy()
    policy["policy_reason"] = ""
    policy.loc[policy["publication_key"].astype(str).str.strip() == "", "policy_reason"] += "missing_publication_key;"
    policy.loc[policy["control_qc_status"] == "missing_assigned_control_runs", "policy_reason"] += "assigned_control_run_missing_from_sheet;"
    policy.loc[policy["control_qc_status"] == "no_background_rows", "policy_reason"] += "no_background_control_rows;"
    policy.loc[policy["n_unique_targets"].astype(int) == 0, "policy_reason"] += "no_nonblank_targets;"
    policy = policy[policy["policy_reason"].astype(str).str.strip() != ""].copy()
    policy_path = OUT / "chip_groups_for_policy_review.tsv"
    policy.to_csv(policy_path, sep="\t", index=False)

    # Report.
    report = []
    report.append("# ChIP Rowwise Evidence and Inventory Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append(f"Input: `{IN_XLSX}`")
    report.append("")
    report.append("## Basic counts")
    report.append("")
    report.append(f"- rows/runs: {len(out)}")
    report.append(f"- unique runs: {out['run'].nunique()}")
    report.append(f"- unique BioProjects: {out['bioproject'].replace('', pd.NA).dropna().nunique()}")
    report.append(f"- rows with publication_key/paper_link: {int(out['has_publication_key'].sum())}")
    report.append(f"- unique publication_key/paper_link values: {out.loc[out['publication_key']!='', 'publication_key'].nunique()}")
    report.append(f"- nonblank Target rows: {int((out['target_clean']!='').sum())}")
    report.append(f"- blank Target rows: {int((out['target_clean']=='').sum())}")
    report.append(f"- background/control rows by classifier: {int(out['is_background_control_row'].sum())}")
    report.append(f"- ChIP/IP rows by classifier: {int((out['chip_role']=='chip_ip').sum())}")
    report.append(f"- rows with assigned controls: {int((out['n_assigned_controls'].astype(int)>0).sum())}")
    report.append(f"- rows with missing assigned control runs: {int((out['n_missing_assigned_controls'].astype(int)>0).sum())}")
    report.append("")
    report.append("## Target type counts")
    report.append("")
    for k, v in out["target_type"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Control QC status by group")
    report.append("")
    for k, v in control_qc["control_qc_status"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Largest ChIP groups")
    report.append("")
    for _, r in group.head(20).iterrows():
        pub = r["publication_key"] if clean(r["publication_key"]) else "<no paper_link>"
        report.append(f"- {pub} / {r['bioproject']}: {r['n_rows']} rows; targets={r['targets'][:200]}")
    report.append("")
    report.append("## Policy-review groups")
    report.append("")
    report.append(f"- groups needing policy review: {len(policy)}")
    for _, r in policy.head(25).iterrows():
        pub = r["publication_key"] if clean(r["publication_key"]) else "<no paper_link>"
        report.append(f"- {pub} / {r['bioproject']}: {r['policy_reason']} ({r['n_rows']} rows)")
    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [rowwise_path, group_path, target_path, control_qc_path, policy_path]:
        report.append(f"- `{p}`")
    report_path = OUT / "CHIP_ROWWISE_EVIDENCE_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", rowwise_path)
    print("Wrote:", group_path)
    print("Wrote:", target_path)
    print("Wrote:", control_qc_path)
    print("Wrote:", policy_path)
    print("Wrote:", report_path)
    print()
    print("Basic counts:")
    print(pd.DataFrame([{
        "n_rows": len(out),
        "n_unique_runs": out["run"].nunique(),
        "n_unique_bioprojects": out["bioproject"].replace("", pd.NA).dropna().nunique(),
        "n_rows_with_paper_link": int(out["has_publication_key"].sum()),
        "n_unique_paper_link": out.loc[out["publication_key"] != "", "publication_key"].nunique(),
        "n_nonblank_target_rows": int((out["target_clean"] != "").sum()),
        "n_blank_target_rows": int((out["target_clean"] == "").sum()),
        "n_background_control_rows": int(out["is_background_control_row"].sum()),
        "n_chip_ip_rows": int((out["chip_role"] == "chip_ip").sum()),
        "n_rows_with_assigned_controls": int((out["n_assigned_controls"].astype(int) > 0).sum()),
        "n_rows_with_missing_assigned_controls": int((out["n_missing_assigned_controls"].astype(int) > 0).sum()),
    }]).to_string(index=False))
    print()
    print("Target type counts:")
    print(out["target_type"].value_counts().to_string())
    print()
    print("Control QC status counts:")
    print(control_qc["control_qc_status"].value_counts().to_string())


if __name__ == "__main__":
    main()
