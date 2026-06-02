#!/usr/bin/env python3
"""
Semantic red-flag scan for structurally PASS AI-curated packets.

Read-only. Does not modify AI outputs.

This is not a validator replacement. It produces curator-facing review flags:
  - fallback rows
  - low confidence / curator_check rows
  - treatment contradictions or suspicious treatment labels
  - stage mismatch between detected metadata terms and AI suggested stage
  - strain/background tokens not preserved in AI suggestion
  - HbAA/HbAS host-context rows needing review

Outputs:
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_red_flags.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/semantic_red_flag_summary_by_packet.tsv
  outputs/04_AGENTIC_AI_ASSIST/deep_qc/SEMANTIC_RED_FLAG_SUMMARY.md
"""

from __future__ import annotations

import json
import re
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


def contains(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def row_text(row: pd.Series) -> str:
    cols = [
        "source_row_id", "Run", "BioSample",
        "LibraryName", "SampleName", "sra_LibraryName", "sra_SampleName",
        "biosample_title",
        "biosample_attr_sample_name", "biosample_attr_submitter_id",
        "biosample_attr_isolate", "biosample_attr_strain",
        "biosample_attr_genotype", "biosample_attr_treatment",
        "biosample_attr_condition", "biosample_attr_developmental_stage",
        "biosample_attr_dev_stage", "biosample_attr_life_stage",
        "detected_stage_terms", "detected_strain_terms",
        "detected_perturbation_terms", "detected_control_terms",
    ]
    return " | ".join(clean(row.get(c, "")) for c in cols if c in row.index)


def ai_text(row: pd.Series) -> str:
    cols = [
        "sample_class_id",
        "suggested_stage_timepoint",
        "suggested_strain",
        "suggested_condition",
        "suggested_perturbation_or_treatment",
        "suggested_sample_role",
        "suggested_comparator_or_background",
    ]
    return " | ".join(clean(row.get(c, "")) for c in cols if c in row.index)


def stage_tokens_from_text(text: str) -> set[str]:
    token_patterns = {
        "ring": r"\bring\b",
        "trophozoite": r"\btroph|trophozoite\b",
        "schizont": r"\bschi|schizont\b",
        "gametocyte": r"\bgametocyte\b",
        "oocyst": r"\boocyst\b",
        "ookinete": r"\bookinete\b",
        "sporozoite": r"\bsporozoite\b",
        "merozoite": r"\bmerozoite\b",
        "liver": r"\bliver\b",
    }
    out = set()
    for token, pat in token_patterns.items():
        if contains(pat, text):
            out.add(token)
    return out


def strain_tokens_from_text(text: str) -> set[str]:
    # Conservative, common tokens only. This is review-oriented, not exhaustive.
    token_patterns = {
        "3D7": r"\b3D7\b",
        "NF54": r"\bNF54\b",
        "PB104": r"\bPB104\b|\bpB104\b|\bpb104\b",
        "K1": r"\bK1\b",
        "Dd2": r"\bDd2\b|\bDD2\b",
        "W2": r"\bW2\b",
        "7G8": r"\b7G8\b",
        "FCR3": r"\bFCR3\b",
        "HB3": r"\bHB3\b",
    }
    out = set()
    for token, pat in token_patterns.items():
        if contains(pat, text):
            out.add(token)
    return out


def add_flag(flags, severity, flag, message):
    flags.append({
        "severity": severity,
        "semantic_flag": flag,
        "message": message,
    })


def scan_row(row: pd.Series) -> list[dict]:
    flags = []
    rt = row_text(row)
    at = ai_text(row)

    rt_low = rt.lower()
    at_low = at.lower()

    if clean(row.get("rowwise_origin", "")) == "deterministic_fallback":
        add_flag(flags, "REVIEW", "deterministic_fallback_row",
                 "Row was completed deterministically after AI missed it.")

    if clean(row.get("suggestion_confidence", "")).lower() == "low":
        add_flag(flags, "REVIEW", "low_confidence_ai_suggestion",
                 "AI/fallback confidence is low.")

    if clean(row.get("review_flag", "")) and clean(row.get("review_flag", "")) != "ok":
        add_flag(flags, "REVIEW", "rowwise_review_flag_not_ok",
                 f"review_flag={clean(row.get('review_flag', ''))}")

    # Treatment / control contradictions.
    row_nodrug = contains(r"\b(no[-_ ]?drug|nodrug|untreated|vehicle|blank[-_ ]?control|ctrl)\b", rt)
    row_dha = contains(r"\b(DHA|dihydroartemisinin|dihydroartemisin)\b", rt)
    row_btz = contains(r"\b(BTZ|bortezomib)\b", rt)

    ai_dha = contains(r"\b(DHA|dihydroartemisinin|dihydroartemisin)\b", at)
    ai_btz = contains(r"\b(BTZ|bortezomib)\b", at)
    ai_treated = contains(r"\bdrug treated\b|\bdrug-treated\b", at)
    ai_nodrug = contains(r"\b(no[-_ ]?drug|nodrug|untreated|vehicle|none)\b", at)

    if row_nodrug and (ai_dha or ai_btz or ai_treated):
        add_flag(flags, "HIGH", "possible_control_labeled_treated",
                 "Row evidence suggests no-drug/control but AI text suggests treatment.")

    if row_dha and (ai_btz or ai_nodrug):
        add_flag(flags, "HIGH", "possible_dha_label_conflict",
                 "Row evidence suggests DHA but AI text suggests BTZ or no-drug.")

    if row_btz and (ai_dha or ai_nodrug):
        add_flag(flags, "HIGH", "possible_btz_label_conflict",
                 "Row evidence suggests BTZ but AI text suggests DHA or no-drug.")

    # Stage mismatch, conservative.
    row_stage = stage_tokens_from_text(rt)
    ai_stage = stage_tokens_from_text(clean(row.get("suggested_stage_timepoint", "")))

    if row_stage and ai_stage:
        # If both have a clear stage and there is no overlap, flag.
        if row_stage.isdisjoint(ai_stage):
            add_flag(flags, "MEDIUM", "possible_stage_mismatch",
                     f"row_stage={sorted(row_stage)} ai_stage={sorted(ai_stage)}")
    elif row_stage and clean(row.get("suggested_stage_timepoint", "")).lower() in {"unknown", ""}:
        add_flag(flags, "REVIEW", "stage_in_metadata_but_ai_unknown",
                 f"row_stage={sorted(row_stage)} but AI stage is unknown/blank.")

    # Strain/background preservation.
    row_strains = strain_tokens_from_text(rt)
    ai_strains = strain_tokens_from_text(clean(row.get("suggested_strain", "")) + " " + clean(row.get("sample_class_id", "")))

    if row_strains and ai_strains and row_strains.isdisjoint(ai_strains):
        add_flag(flags, "MEDIUM", "possible_strain_mismatch",
                 f"row_strain={sorted(row_strains)} ai_strain={sorted(ai_strains)}")
    elif row_strains and clean(row.get("suggested_strain", "")).lower() in {"unknown", ""}:
        add_flag(flags, "REVIEW", "strain_in_metadata_but_ai_unknown",
                 f"row_strain={sorted(row_strains)} but AI strain is unknown/blank.")

    # HbAA/HbAS host context review.
    row_hbaa = contains(r"\bHbAA\b|\bHBAA\b", rt)
    row_hbas = contains(r"\bHbAS\b|\bHBAS\b", rt)
    ai_hbaa = contains(r"\bHbAA\b|\bHBAA\b", at)
    ai_hbas = contains(r"\bHbAS\b|\bHBAS\b", at)

    if row_hbaa and not ai_hbaa:
        add_flag(flags, "REVIEW", "hbaa_context_not_preserved_in_ai",
                 "Row evidence contains HbAA, but AI text does not clearly preserve HbAA.")
    if row_hbas and not ai_hbas:
        add_flag(flags, "REVIEW", "hbas_context_not_preserved_in_ai",
                 "Row evidence contains HbAS, but AI text does not clearly preserve HbAS.")

    return flags


def main():
    if not PACKET_INV.exists():
        raise FileNotFoundError("Run scripts/43_deep_qc_ai_outputs.py first.")

    inv = read_tsv(PACKET_INV)
    pass_packets = inv[inv["latest_validation_status"] == "PASS"].copy()

    all_flags = []
    packet_summaries = []

    for _, pktrow in pass_packets.iterrows():
        packet_id = clean(pktrow["packet_id"])
        summary_path = Path(clean(pktrow.get("latest_validation_summary", "")))
        summary = metric_value_tsv(summary_path)

        ai_json = Path(clean(summary.get("ai_json", "")))
        packet_tsv = Path(clean(summary.get("packet_tsv", "")))

        if not ai_json.exists() or not packet_tsv.exists():
            continue

        obj = json.loads(ai_json.read_text())
        rowwise = pd.DataFrame(obj.get("rowwise_suggestions", []) or []).fillna("")
        pkt = read_tsv(packet_tsv)
        if rowwise.empty or pkt.empty:
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

        meta_cols = [c for c in pkt.columns if c in [
            "source_row_id", "Run", "BioSample",
            "LibraryName", "SampleName", "sra_LibraryName", "sra_SampleName",
            "biosample_title",
            "biosample_attr_sample_name", "biosample_attr_submitter_id",
            "biosample_attr_isolate", "biosample_attr_strain",
            "biosample_attr_genotype", "biosample_attr_treatment",
            "biosample_attr_condition", "biosample_attr_developmental_stage",
            "biosample_attr_dev_stage", "biosample_attr_life_stage",
            "detected_stage_terms", "detected_strain_terms",
            "detected_perturbation_terms", "detected_control_terms",
        ]]

        merged = rowwise.merge(
            pkt[meta_cols],
            on=["source_row_id", "Run"],
            how="left",
            suffixes=("", "_packet"),
        )

        n_rows = len(merged)
        n_flagged_rows = 0

        for _, row in merged.iterrows():
            flags = scan_row(row)
            if flags:
                n_flagged_rows += 1

            for f in flags:
                all_flags.append({
                    "packet_id": packet_id,
                    "pmid": clean(pktrow.get("pmid", "")),
                    "bioproject": clean(pktrow.get("bioproject", "")),
                    "Run": clean(row.get("Run", "")),
                    "source_row_id": clean(row.get("source_row_id", "")),
                    "BioSample": clean(row.get("BioSample", "")),
                    "biosample_title": clean(row.get("biosample_title", "")),
                    "detected_stage_terms": clean(row.get("detected_stage_terms", "")),
                    "detected_strain_terms": clean(row.get("detected_strain_terms", "")),
                    "suggested_stage_timepoint": clean(row.get("suggested_stage_timepoint", "")),
                    "suggested_strain": clean(row.get("suggested_strain", "")),
                    "suggested_condition": clean(row.get("suggested_condition", "")),
                    "suggested_perturbation_or_treatment": clean(row.get("suggested_perturbation_or_treatment", "")),
                    "suggested_sample_role": clean(row.get("suggested_sample_role", "")),
                    "suggestion_confidence": clean(row.get("suggestion_confidence", "")),
                    "review_flag": clean(row.get("review_flag", "")),
                    "rowwise_origin": clean(row.get("rowwise_origin", "")),
                    "severity": f["severity"],
                    "semantic_flag": f["semantic_flag"],
                    "message": f["message"],
                    "suggestion_evidence": clean(row.get("suggestion_evidence", "")),
                    "ai_json": str(ai_json),
                })

        packet_summaries.append({
            "packet_id": packet_id,
            "pmid": clean(pktrow.get("pmid", "")),
            "bioproject": clean(pktrow.get("bioproject", "")),
            "n_rows_scanned": n_rows,
            "n_rows_with_any_flag": n_flagged_rows,
            "n_flags_total": sum(1 for x in all_flags if x["packet_id"] == packet_id),
            "n_high_flags": sum(1 for x in all_flags if x["packet_id"] == packet_id and x["severity"] == "HIGH"),
            "n_medium_flags": sum(1 for x in all_flags if x["packet_id"] == packet_id and x["severity"] == "MEDIUM"),
            "n_review_flags": sum(1 for x in all_flags if x["packet_id"] == packet_id and x["severity"] == "REVIEW"),
        })

    flags_df = pd.DataFrame(all_flags)
    summary_df = pd.DataFrame(packet_summaries)

    flags_path = DEEP_QC / "semantic_red_flags.tsv"
    summary_path = DEEP_QC / "semantic_red_flag_summary_by_packet.tsv"

    flags_df.to_csv(flags_path, sep="\t", index=False)
    summary_df.to_csv(summary_path, sep="\t", index=False)

    md = []
    md.append("# Semantic Red-Flag Summary")
    md.append("")
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append(f"PASS packets scanned: {len(pass_packets)}")
    md.append(f"Rows with flags: {summary_df['n_rows_with_any_flag'].sum() if not summary_df.empty else 0}")
    md.append(f"Total flags: {len(flags_df)}")
    md.append("")
    if not flags_df.empty:
        md.append("## Flags by severity")
        md.append("")
        for k, v in flags_df["severity"].value_counts().items():
            md.append(f"- {k}: {v}")
        md.append("")
        md.append("## Flags by type")
        md.append("")
        for k, v in flags_df["semantic_flag"].value_counts().items():
            md.append(f"- {k}: {v}")
    else:
        md.append("No semantic red flags found.")
    md.append("")
    md.append("Interpretation: HIGH/MEDIUM/REVIEW flags are curator-review aids, not automatic failures.")
    md_path = DEEP_QC / "SEMANTIC_RED_FLAG_SUMMARY.md"
    md_path.write_text("\n".join(md))

    print("Wrote:", flags_path)
    print("Wrote:", summary_path)
    print("Wrote:", md_path)
    print()
    print(md_path.read_text())


if __name__ == "__main__":
    main()
