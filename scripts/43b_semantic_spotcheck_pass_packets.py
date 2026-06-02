#!/usr/bin/env python3
"""
Semantic spot-check table for PASS AI-curated packets.

Read-only. Does not modify outputs.

Creates:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_spotcheck_rows.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/SEMANTIC_SPOTCHECK_SUMMARY.md
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pandas as pd


DEEP_QC = Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc")
PACKET_INV = DEEP_QC / "ai_packet_status_inventory.tsv"
AI_DIR = Path("outputs/04_AGENTIC_AI_ASSIST/api_paper_suggestions")


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
        return {
            clean(r["metric"]): clean(r["value"])
            for _, r in df.iterrows()
            if clean(r.get("metric", ""))
        }
    return {c: clean(df.iloc[0].get(c, "")) for c in df.columns}


def latest_origin_qc(packet_id: str) -> pd.DataFrame:
    folder = AI_DIR / packet_id
    files = sorted(
        folder.glob(f"{packet_id}.chunked_rowwise_origin_qc.*.tsv"),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return pd.DataFrame(columns=["source_row_id", "Run", "rowwise_origin"])
    return read_tsv(files[-1])


def pick_rows(rowdf: pd.DataFrame, rows_per_packet: int = 8) -> pd.DataFrame:
    """
    Prioritize rows likely to reveal semantic problems:
      fallback rows
      curator_check / low_confidence / ambiguous rows
      then deterministic evenly spaced examples
    """
    if rowdf.empty:
        return rowdf

    chosen = []

    def take(mask, reason, max_n):
        x = rowdf[mask].copy()
        if x.empty:
            return
        x = x.head(max_n).copy()
        x["spotcheck_reason"] = reason
        chosen.append(x)

    take(rowdf.get("rowwise_origin", "") == "deterministic_fallback",
         "deterministic_fallback", 5)

    take(rowdf.get("review_flag", "").isin(["curator_check", "low_confidence", "ambiguous"]),
         "curator_or_low_confidence_flag", 5)

    take(rowdf.get("suggestion_confidence", "").str.lower().eq("low"),
         "low_confidence", 5)

    if chosen:
        picked = pd.concat(chosen, ignore_index=True)
        seen = set()
        keep_rows = []
        for _, r in picked.iterrows():
            sid = clean(r.get("source_row_id", ""))
            if sid and sid not in seen:
                seen.add(sid)
                keep_rows.append(r)
        picked = pd.DataFrame(keep_rows)
    else:
        picked = pd.DataFrame()

    remaining_n = max(0, rows_per_packet - len(picked))
    if remaining_n > 0:
        already = set(picked["source_row_id"]) if not picked.empty and "source_row_id" in picked.columns else set()
        rest = rowdf[~rowdf["source_row_id"].isin(already)].copy()

        if len(rest) <= remaining_n:
            extra = rest.copy()
        else:
            # deterministic evenly spaced sample
            idx = [round(i * (len(rest) - 1) / max(1, remaining_n - 1)) for i in range(remaining_n)]
            extra = rest.iloc[idx].copy()

        extra["spotcheck_reason"] = "even_spaced_sample"
        picked = pd.concat([picked, extra], ignore_index=True)

    return picked.head(rows_per_packet)


def main() -> None:
    if not PACKET_INV.exists():
        raise FileNotFoundError(f"Run scripts/43_deep_qc_ai_outputs.py first. Missing: {PACKET_INV}")

    inv = read_tsv(PACKET_INV)
    pass_packets = inv[inv["latest_validation_status"] == "PASS"].copy()

    all_rows = []

    for _, pktrow in pass_packets.iterrows():
        packet_id = clean(pktrow["packet_id"])
        summary_path = Path(clean(pktrow.get("latest_validation_summary", "")))
        summary = metric_value_tsv(summary_path)

        ai_json = Path(clean(summary.get("ai_json", "")))
        packet_tsv = Path(clean(summary.get("packet_tsv", "")))

        if not ai_json.exists() or not packet_tsv.exists():
            continue

        try:
            obj = json.loads(ai_json.read_text())
        except Exception as e:
            print(f"WARNING: could not read AI JSON for {packet_id}: {e}")
            continue

        pkt = read_tsv(packet_tsv)
        rowwise = pd.DataFrame(obj.get("rowwise_suggestions", []) or []).fillna("")
        if pkt.empty or rowwise.empty:
            continue

        origin = latest_origin_qc(packet_id)
        if not origin.empty:
            rowwise = rowwise.merge(
                origin[["source_row_id", "Run", "rowwise_origin"]],
                on=["source_row_id", "Run"],
                how="left",
            )
        else:
            rowwise["rowwise_origin"] = "ai_one_shot_or_repaired"

        meta_cols = [c for c in [
            "source_row_id", "Run", "BioSample",
            "LibraryName", "SampleName",
            "sra_LibraryName", "sra_SampleName",
            "biosample_title",
            "biosample_attr_strain",
            "biosample_attr_genotype",
            "biosample_attr_treatment",
            "biosample_attr_condition",
            "detected_stage_terms",
            "detected_strain_terms",
            "detected_perturbation_terms",
            "detected_control_terms",
        ] if c in pkt.columns]

        merged = rowwise.merge(
            pkt[meta_cols],
            on=["source_row_id", "Run"],
            how="left",
            suffixes=("", "_packet"),
        )

        picked = pick_rows(merged, rows_per_packet=8)
        if picked.empty:
            continue

        picked.insert(0, "packet_id", packet_id)
        picked.insert(1, "pmid", clean(pktrow.get("pmid", "")))
        picked.insert(2, "bioproject", clean(pktrow.get("bioproject", "")))
        picked.insert(3, "ai_json", str(ai_json))

        all_rows.append(picked)

    if all_rows:
        out = pd.concat(all_rows, ignore_index=True)
    else:
        out = pd.DataFrame()

    desired = [c for c in [
        "packet_id", "pmid", "bioproject", "spotcheck_reason",
        "rowwise_origin",
        "source_row_id", "Run", "BioSample",
        "biosample_title", "sra_SampleName", "sra_LibraryName",
        "biosample_attr_strain", "biosample_attr_genotype",
        "biosample_attr_treatment", "biosample_attr_condition",
        "detected_stage_terms", "detected_strain_terms",
        "detected_perturbation_terms", "detected_control_terms",
        "sample_class_id",
        "suggested_assay_type",
        "suggested_stage_timepoint",
        "suggested_strain",
        "suggested_condition",
        "suggested_perturbation_or_treatment",
        "suggested_sample_role",
        "suggested_comparator_or_background",
        "suggestion_confidence",
        "review_flag",
        "suggestion_evidence",
        "ai_json",
    ] if c in out.columns]

    out = out[desired] if not out.empty else out
    out_path = DEEP_QC / "semantic_spotcheck_rows.tsv"
    out.to_csv(out_path, sep="\t", index=False)

    md = []
    md.append("# Semantic Spot-check Summary")
    md.append("")
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append(f"PASS packets sampled: {len(pass_packets)}")
    md.append(f"Spot-check rows written: {len(out)}")
    md.append("")
    if not out.empty:
        md.append("## Rows by spotcheck reason")
        md.append("")
        for k, v in out["spotcheck_reason"].value_counts().items():
            md.append(f"- {k}: {v}")
        md.append("")
        md.append("## Rows by rowwise origin")
        md.append("")
        for k, v in out["rowwise_origin"].fillna("").replace("", "unknown").value_counts().items():
            md.append(f"- {k}: {v}")
    md.append("")
    md.append("Interpretation: this table is for human semantic review. Structural PASS is already handled by validator.")
    (DEEP_QC / "SEMANTIC_SPOTCHECK_SUMMARY.md").write_text("\n".join(md))

    print("Wrote:", out_path)
    print("Wrote:", DEEP_QC / "SEMANTIC_SPOTCHECK_SUMMARY.md")
    print()
    print((DEEP_QC / "SEMANTIC_SPOTCHECK_SUMMARY.md").read_text())


if __name__ == "__main__":
    main()
