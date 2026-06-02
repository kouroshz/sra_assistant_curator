#!/usr/bin/env python3
"""
Independent gold-standard overlap check for one AI curation pilot.

This script is intentionally POST HOC.
It must NOT be called by the AI runner and must NOT be used for training/prompt fitting.
It compares an already-produced AI curation JSON against a manual curated workbook,
limited to overlapping Run IDs only.

Designed first for:
  PMID_32487761__BIOPROJECT_PRJNA550429

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/gold_standard_verification/<packet_id>/
    <packet_id>.gold_overlap_comparison.<timestamp>.tsv
    <packet_id>.gold_only_runs.<timestamp>.tsv
    <packet_id>.packet_only_runs.<timestamp>.tsv
    <packet_id>.gold_overlap_summary.<timestamp>.tsv
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd


DEFAULT_PACKET_ID = "PMID_32487761__BIOPROJECT_PRJNA550429"
DEFAULT_AI_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")
DEFAULT_PACKET_TABLES_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/packet_tables")
DEFAULT_OUT_ROOT = Path("outputs/04_AGENTIC_AI_ASSIST/gold_standard_verification")

MANUAL_CANDIDATES = [
    Path("data/gold_standard/32487761_Manually_Curated.xlsx"),
    Path("data/gold_standard/32487761_Manually_Curated(1).xlsx"),
    Path("data/32487761_Manually_Curated.xlsx"),
    Path("data/32487761_Manually_Curated(1).xlsx"),
]


def clean(x: Any) -> str:
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def find_repo_root(start: Optional[Path] = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "scripts").exists() and (p / "outputs").exists():
            return p
    return cur


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def latest_ai_json(root: Path, packet_id: str, ai_dir: Path = DEFAULT_AI_DIR) -> Path:
    base = root / ai_dir / packet_id
    candidates = list(base.glob(f"{packet_id}.ai_curation.*.json"))
    if not candidates:
        raise FileNotFoundError(f"No AI JSON found under {base}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_ai_rowwise(ai_json: Path) -> pd.DataFrame:
    obj = json.loads(ai_json.read_text())
    rows = obj.get("rowwise_suggestions", []) or []
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"AI JSON has no rowwise_suggestions: {ai_json}")
    for col in ["Run", "source_row_id"]:
        if col not in df.columns:
            raise ValueError(f"AI rowwise_suggestions missing required column: {col}")
    df["Run"] = df["Run"].map(clean)

    # Add sample-map class-level text, useful for checking replicate/genotype labels.
    class_text: Dict[str, str] = {}
    for sm in obj.get("sample_map", []) or []:
        cid = clean(sm.get("sample_class_id", ""))
        if not cid:
            continue
        vals = []
        for k, v in sm.items():
            if isinstance(v, (str, int, float)):
                vals.append(f"{k}={v}")
            elif isinstance(v, list):
                vals.append(f"{k}={' | '.join(map(str, v[:20]))}")
        class_text[cid] = " ; ".join(vals)
    df["_sample_class_context"] = df.get("sample_class_id", pd.Series([""] * len(df))).map(lambda x: class_text.get(clean(x), ""))

    return df


def read_packet_tsv(packet_tsv: Optional[Path]) -> pd.DataFrame:
    if packet_tsv is None or not packet_tsv.exists():
        return pd.DataFrame()
    x = pd.read_csv(packet_tsv, sep="\t", dtype=str).fillna("")
    if "Run" in x.columns:
        x["Run"] = x["Run"].map(clean)
    return x


def normalize_stage(s: str) -> str:
    t = clean(s).lower()
    if re.search(r"\bring\b|\b_r\b|^r$", t):
        return "ring"
    if re.search(r"troph|\b_t\b|^t$", t):
        return "trophozoite"
    if re.search(r"schiz|\b_s\b|^s$", t):
        return "schizont"
    return t


def normalize_strain(s: str) -> str:
    t = clean(s).lower().replace("-", "").replace("_", "")
    if "3d7" in t:
        return "3d7"
    if "nf54" in t:
        return "nf54"
    return t


def norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean(s).lower())


def contains_label(text: str, label: str) -> bool:
    label = clean(label)
    if not label:
        return True
    return norm_token(label) in norm_token(text)


def infer_ai_text(row: pd.Series) -> str:
    keys = [
        "sample_class_id",
        "suggested_stage_timepoint",
        "suggested_strain",
        "suggested_condition",
        "suggested_perturbation_or_treatment",
        "suggested_sample_role",
        "suggested_comparator_or_background",
        "suggestion_evidence",
        "_sample_class_context",
    ]
    return " ; ".join(clean(row.get(k, "")) for k in keys if clean(row.get(k, "")))


def compare_bool(label: str, ok: bool, missing_ok: bool = True) -> str:
    if missing_ok and not clean(label):
        return "NA"
    return "yes" if ok else "no"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare an AI curation JSON to a manual gold workbook on overlapping Run IDs only."
    )
    parser.add_argument("--packet-id", default=DEFAULT_PACKET_ID)
    parser.add_argument("--manual-xlsx", type=Path, default=None, help="Manual curated workbook. If omitted, known local candidates are tried.")
    parser.add_argument("--ai-json", type=Path, default=None, help="AI JSON. If omitted, latest JSON for packet is used.")
    parser.add_argument("--packet-tsv", type=Path, default=None, help="Packet rowwise TSV. If omitted, default packet table path is used.")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = parser.parse_args()

    root = find_repo_root()
    packet_id = args.packet_id

    manual_path = args.manual_xlsx
    if manual_path is None:
        manual_path = first_existing([root / p for p in MANUAL_CANDIDATES])
    elif not manual_path.is_absolute():
        manual_path = root / manual_path
    if manual_path is None or not manual_path.exists():
        candidates = "\n  ".join(str(root / p) for p in MANUAL_CANDIDATES)
        raise FileNotFoundError(
            "Manual gold workbook not found. Provide --manual-xlsx. Tried:\n  " + candidates
        )

    ai_json = args.ai_json
    if ai_json is None:
        ai_json = latest_ai_json(root, packet_id)
    elif not ai_json.is_absolute():
        ai_json = root / ai_json
    if not ai_json.exists():
        raise FileNotFoundError(f"AI JSON not found: {ai_json}")

    packet_tsv = args.packet_tsv
    if packet_tsv is None:
        packet_tsv = root / DEFAULT_PACKET_TABLES_DIR / f"{packet_id}.rowwise_evidence.tsv"
    elif not packet_tsv.is_absolute():
        packet_tsv = root / packet_tsv

    stamp = now_stamp()
    outdir = root / args.out_root / packet_id
    outdir.mkdir(parents=True, exist_ok=True)

    gold = pd.read_excel(manual_path, dtype=str).fillna("")
    if "Run" not in gold.columns:
        raise ValueError("Manual workbook must contain a Run column")
    gold["Run"] = gold["Run"].map(clean)
    gold = gold[gold["Run"] != ""].copy()

    ai = read_ai_rowwise(ai_json)
    pkt = read_packet_tsv(packet_tsv)

    # One AI suggestion per Run is expected after validator PASS.
    ai_counts = ai["Run"].value_counts()
    duplicated_ai_runs = sorted(ai_counts[ai_counts > 1].index.tolist())

    merged = gold.merge(ai, on="Run", how="left", suffixes=("_gold", "_ai"))

    records = []
    for _, r in merged.iterrows():
        ai_text = infer_ai_text(r)
        gold_stage = clean(r.get("Cell_Cycle_Stage", ""))
        ai_stage = clean(r.get("suggested_stage_timepoint", ""))
        gold_strain = clean(r.get("Strain", ""))
        ai_strain = clean(r.get("suggested_strain", ""))
        gold_mutant = clean(r.get("Mutant", ""))
        gold_rep = clean(r.get("Replicates", ""))

        stage_match = normalize_stage(gold_stage) == normalize_stage(ai_stage) if gold_stage and ai_stage else False
        # Manual gold uses 3D7 broadly; AI may use 3D7-G7. Count those as matching.
        strain_match = normalize_strain(gold_strain) == normalize_strain(ai_strain) if gold_strain and ai_strain else False
        mutant_match = contains_label(ai_text, gold_mutant) if gold_mutant else True
        replicate_match = contains_label(ai_text, gold_rep) if gold_rep else True

        records.append({
            "Run": clean(r.get("Run", "")),
            "gold_BioSample": clean(r.get("BioSample", "")),
            "ai_source_row_id": clean(r.get("source_row_id", "")),
            "ai_sample_class_id": clean(r.get("sample_class_id", "")),
            "gold_stage": gold_stage,
            "ai_stage_timepoint": ai_stage,
            "stage_match": compare_bool(gold_stage, stage_match),
            "gold_strain": gold_strain,
            "ai_strain": ai_strain,
            "strain_match": compare_bool(gold_strain, strain_match),
            "gold_mutant": gold_mutant,
            "ai_condition": clean(r.get("suggested_condition", "")),
            "ai_perturbation_or_treatment": clean(r.get("suggested_perturbation_or_treatment", "")),
            "mutant_token_found_in_ai_text": compare_bool(gold_mutant, mutant_match),
            "gold_replicate": gold_rep,
            "replicate_token_found_in_ai_text": compare_bool(gold_rep, replicate_match),
            "ai_role": clean(r.get("suggested_sample_role", "")),
            "ai_confidence": clean(r.get("suggestion_confidence", "")),
            "ai_review_flag": clean(r.get("review_flag", "")),
            "ai_evidence": clean(r.get("suggestion_evidence", "")),
            "gold_raw_metadata_col1": clean(r.get("raw_metadata_col1", "")),
        })

    comp = pd.DataFrame(records)

    gold_runs = set(gold["Run"])
    ai_runs = set(ai["Run"])
    pkt_runs = set(pkt["Run"]) if not pkt.empty and "Run" in pkt.columns else set()

    gold_only = gold[~gold["Run"].isin(ai_runs)].copy()
    packet_only_runs = sorted((pkt_runs or ai_runs) - gold_runs)
    packet_only = pd.DataFrame({"Run": packet_only_runs})
    if not pkt.empty and "Run" in pkt.columns and len(packet_only):
        keep_cols = [c for c in ["Run", "source_row_id", "BioSample", "sra_SampleName", "sra_LibraryName", "biosample_title", "biosample_attr_sample_name", "biosample_attr_strain", "biosample_attr_genotype", "biosample_attr_treatment"] if c in pkt.columns]
        packet_only = packet_only.merge(pkt[keep_cols].drop_duplicates("Run"), on="Run", how="left")

    def count_yes(col: str) -> int:
        return int((comp[col] == "yes").sum()) if col in comp.columns else 0

    def count_no(col: str) -> int:
        return int((comp[col] == "no").sum()) if col in comp.columns else 0

    n_overlap = int(comp["ai_source_row_id"].map(lambda x: bool(clean(x))).sum()) if not comp.empty else 0
    n_gold = len(gold)
    n_gold_missing_ai = len(gold_only)

    key_no = (
        count_no("stage_match")
        + count_no("strain_match")
        + count_no("mutant_token_found_in_ai_text")
        + count_no("replicate_token_found_in_ai_text")
    )

    status = "PASS"
    if duplicated_ai_runs or n_gold_missing_ai or key_no:
        status = "WARN"

    summary_rows = [
        {"metric": "packet_id", "value": packet_id},
        {"metric": "manual_xlsx", "value": str(manual_path)},
        {"metric": "ai_json", "value": str(ai_json)},
        {"metric": "packet_tsv", "value": str(packet_tsv) if packet_tsv and packet_tsv.exists() else ""},
        {"metric": "n_gold_rows", "value": n_gold},
        {"metric": "n_ai_rowwise_suggestions", "value": len(ai)},
        {"metric": "n_packet_rows", "value": len(pkt) if not pkt.empty else "not_checked"},
        {"metric": "n_overlap_gold_runs_with_ai", "value": n_overlap},
        {"metric": "n_gold_runs_missing_from_ai", "value": n_gold_missing_ai},
        {"metric": "n_packet_or_ai_runs_not_in_gold", "value": len(packet_only)},
        {"metric": "n_ai_duplicate_Run_values", "value": len(duplicated_ai_runs)},
        {"metric": "stage_match_yes", "value": count_yes("stage_match")},
        {"metric": "stage_match_no", "value": count_no("stage_match")},
        {"metric": "strain_match_yes", "value": count_yes("strain_match")},
        {"metric": "strain_match_no", "value": count_no("strain_match")},
        {"metric": "mutant_token_found_yes", "value": count_yes("mutant_token_found_in_ai_text")},
        {"metric": "mutant_token_found_no", "value": count_no("mutant_token_found_in_ai_text")},
        {"metric": "replicate_token_found_yes", "value": count_yes("replicate_token_found_in_ai_text")},
        {"metric": "replicate_token_found_no", "value": count_no("replicate_token_found_in_ai_text")},
        {"metric": "gold_overlap_verification_status", "value": status},
        {"metric": "important_note", "value": "Manual gold is incomplete for this BioProject; packet/AI-only rows are reported but not treated as AI errors."},
    ]
    if duplicated_ai_runs:
        summary_rows.append({"metric": "duplicated_ai_Run_values", "value": ";".join(duplicated_ai_runs)})

    summary = pd.DataFrame(summary_rows)

    comp_path = outdir / f"{packet_id}.gold_overlap_comparison.{stamp}.tsv"
    gold_only_path = outdir / f"{packet_id}.gold_only_runs.{stamp}.tsv"
    packet_only_path = outdir / f"{packet_id}.packet_or_ai_only_runs_not_in_gold.{stamp}.tsv"
    summary_path = outdir / f"{packet_id}.gold_overlap_summary.{stamp}.tsv"

    comp.to_csv(comp_path, sep="\t", index=False)
    gold_only.to_csv(gold_only_path, sep="\t", index=False)
    packet_only.to_csv(packet_only_path, sep="\t", index=False)
    summary.to_csv(summary_path, sep="\t", index=False)

    print("\nGOLD OVERLAP SUMMARY")
    print(summary.to_string(index=False))
    print("\nWrote:")
    print(f"  {comp_path}")
    print(f"  {gold_only_path}")
    print(f"  {packet_only_path}")
    print(f"  {summary_path}")


if __name__ == "__main__":
    main()
