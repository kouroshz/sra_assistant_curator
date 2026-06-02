#!/usr/bin/env python3

"""
Validate one AI curation JSON against its packet rowwise evidence table.

This script does NOT call an API.

It checks:
  - rowwise_suggestions cover each packet row exactly once
  - sample_map source_row_ids are valid
  - sample_map duplicate/missing coverage
  - obvious treatment contradictions:
      nodrug/control/ctrl rows should not be labeled DHA/BTZ/drug-treated
      DHA rows should not be labeled BTZ/no drug
      BTZ rows should not be labeled DHA/no drug
  - obvious strain contradictions:
      NF54 row evidence should not be suggested as PB104
      PB104 row evidence should not be suggested as NF54
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def row_text(row: pd.Series) -> str:
    """
    Row-specific evidence only.

    Do NOT include broad compact/detected fields here because they may contain
    packet/study-level terms or terms from nearby sample classes. This validator
    is meant to catch contradictions against the row's own labels.
    """
    cols = [
        "source_row_id", "Run", "BioSample",
        "sra_LibraryName", "sra_SampleName",
        "LibraryName", "SampleName",
        "biosample_title",
        "biosample_attr_sample_name",
        "biosample_attr_submitter_id",
        "biosample_attr_isolate",
        "biosample_attr_strain",
        "biosample_attr_genotype",
        "biosample_attr_treatment",
        "biosample_attr_condition",
    ]
    return " | ".join(clean(row.get(c, "")) for c in cols if c in row.index)


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def classify_row_from_evidence(text: str) -> dict:
    """
    Conservative row-level classification.

    A row can contain terms like "control" as part of generic metadata, so use
    this only as a contradiction screen, not as final curation.
    """
    evidence = {
        "is_nodrug_control": has(r"\b(no[-_ ]?drug|nodrug|untreated|vehicle|blank[-_ ]?control|ctrl)\b", text),
        "is_dha": has(r"\b(DHA|dihydroartemisinin|dihydroartemisin)\b", text),
        "is_btz": has(r"\b(BTZ|bortezomib)\b", text),
        "is_nf54": has(r"\bNF54\b", text),
        "is_pb104": has(r"\b(pB104|PB104|pb104)\b", text),
    }
    return evidence


def suggestion_text(sug: dict) -> str:
    """
    Suggested identity/treatment fields only.

    Do NOT include suggested_comparator_or_background or free-text evidence here,
    because those may mention valid comparator classes such as DHA/BTZ for a
    no-drug control row.
    """
    keys = [
        "sample_class_id",
        "suggested_condition",
        "suggested_perturbation_or_treatment",
        "suggested_sample_role",
        "suggested_strain",
    ]
    return " | ".join(clean(sug.get(k, "")) for k in keys)


def validate(packet_tsv: Path, ai_json: Path, outdir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    x = pd.read_csv(packet_tsv, sep="\t", dtype=str).fillna("")
    ai = json.loads(ai_json.read_text())

    packet_ids = set(x["source_row_id"].astype(str))
    packet_by_id = {r["source_row_id"]: r for _, r in x.iterrows()}

    issues = []

    row_sugs = ai.get("rowwise_suggestions", []) or []
    sug_ids = [clean(s.get("source_row_id", "")) for s in row_sugs]
    sug_id_counts = pd.Series(sug_ids).value_counts()

    # Rowwise coverage checks.
    for sid in sorted(packet_ids - set(sug_ids)):
        issues.append({
            "severity": "FAIL",
            "check": "rowwise_suggestion_missing",
            "source_row_id": sid,
            "Run": clean(packet_by_id[sid].get("Run", "")),
            "message": "Packet row has no rowwise_suggestion.",
        })

    for sid, n in sug_id_counts.items():
        if not sid:
            issues.append({
                "severity": "FAIL",
                "check": "rowwise_suggestion_blank_source_row_id",
                "source_row_id": "",
                "Run": "",
                "message": "A rowwise_suggestion has blank source_row_id.",
            })
        elif sid not in packet_ids:
            issues.append({
                "severity": "FAIL",
                "check": "rowwise_suggestion_unknown_source_row_id",
                "source_row_id": sid,
                "Run": "",
                "message": "A rowwise_suggestion references a source_row_id not in packet.",
            })
        elif n != 1:
            issues.append({
                "severity": "FAIL",
                "check": "rowwise_suggestion_duplicate",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": f"source_row_id appears {n} times in rowwise_suggestions.",
            })

    # Contradiction checks.
    for sug in row_sugs:
        sid = clean(sug.get("source_row_id", ""))
        if sid not in packet_by_id:
            continue

        rt = row_text(packet_by_id[sid])
        ev = classify_row_from_evidence(rt)
        st = suggestion_text(sug)

        if ev["is_nodrug_control"] and has(r"\b(DHA|BTZ|bortezomib|dihydroartemisinin|drug treated|drug-treated)\b", st):
            issues.append({
                "severity": "FAIL",
                "check": "treatment_contradiction_nodrug_labeled_treated",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": f"Evidence suggests no-drug/control but AI labels as treated: {st[:300]}",
            })

        if ev["is_dha"] and has(r"\b(BTZ|bortezomib|no drug|nodrug|untreated|vehicle)\b", st):
            issues.append({
                "severity": "FAIL",
                "check": "treatment_contradiction_dha",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": f"Evidence suggests DHA but AI suggests incompatible treatment/control: {st[:300]}",
            })

        if ev["is_btz"] and has(r"\b(DHA|dihydroartemisinin|no drug|nodrug|untreated|vehicle)\b", st):
            issues.append({
                "severity": "FAIL",
                "check": "treatment_contradiction_btz",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": f"Evidence suggests BTZ but AI suggests incompatible treatment/control: {st[:300]}",
            })

        if ev["is_nf54"] and has(r"\bPB104|pB104|pb104\b", clean(sug.get("suggested_strain", ""))):
            issues.append({
                "severity": "FAIL",
                "check": "strain_contradiction_nf54",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": "Evidence suggests NF54 but AI suggested PB104.",
            })

        if ev["is_pb104"] and has(r"\bNF54\b", clean(sug.get("suggested_strain", ""))):
            issues.append({
                "severity": "FAIL",
                "check": "strain_contradiction_pb104",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": "Evidence suggests PB104 but AI suggested NF54.",
            })

    # sample_map checks.
    sample_ids = []
    for sm in ai.get("sample_map", []) or []:
        class_id = clean(sm.get("sample_class_id", ""))
        for sid in sm.get("matched_source_row_ids", []) or []:
            sid = clean(sid)
            if not sid:
                continue
            sample_ids.append(sid)
            if sid not in packet_ids:
                issues.append({
                    "severity": "FAIL",
                    "check": "sample_map_unknown_source_row_id",
                    "source_row_id": sid,
                    "Run": "",
                    "message": f"sample_map class {class_id} references source_row_id not in packet.",
                })

    sm_counts = pd.Series(sample_ids).value_counts()
    for sid, n in sm_counts.items():
        if sid in packet_ids and n > 1:
            issues.append({
                "severity": "WARN",
                "check": "sample_map_duplicate_source_row_id",
                "source_row_id": sid,
                "Run": clean(packet_by_id[sid].get("Run", "")),
                "message": f"source_row_id appears {n} times in sample_map. This may indicate context/contrast classes mixed with real sample classes.",
            })

    missing_sm = sorted(packet_ids - set(sample_ids))
    for sid in missing_sm:
        issues.append({
            "severity": "WARN",
            "check": "sample_map_missing_source_row_id",
            "source_row_id": sid,
            "Run": clean(packet_by_id[sid].get("Run", "")),
            "message": "Packet row is not represented in sample_map matched_source_row_ids.",
        })

    issues_df = pd.DataFrame(issues)
    if issues_df.empty:
        issues_df = pd.DataFrame(columns=["severity", "check", "source_row_id", "Run", "message"])

    summary_rows = [
        {"metric": "packet_tsv", "value": str(packet_tsv)},
        {"metric": "ai_json", "value": str(ai_json)},
        {"metric": "n_packet_rows", "value": len(x)},
        {"metric": "n_rowwise_suggestions", "value": len(row_sugs)},
        {"metric": "n_sample_map_entries", "value": len(ai.get("sample_map", []) or [])},
        {"metric": "n_fail", "value": int((issues_df["severity"] == "FAIL").sum())},
        {"metric": "n_warn", "value": int((issues_df["severity"] == "WARN").sum())},
    ]

    for check, n in issues_df["check"].value_counts().items():
        summary_rows.append({"metric": f"check:{check}", "value": int(n)})

    status = "PASS"
    if (issues_df["severity"] == "FAIL").any():
        status = "FAIL"
    elif (issues_df["severity"] == "WARN").any():
        status = "WARN"

    summary_rows.append({"metric": "validation_status", "value": status})
    summary_df = pd.DataFrame(summary_rows)

    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        stem = ai_json.stem.replace(".ai_curation", "")
        issues_df.to_csv(outdir / f"{stem}.validation_issues.tsv", sep="\t", index=False)
        summary_df.to_csv(outdir / f"{stem}.validation_summary.tsv", sep="\t", index=False)

    return summary_df, issues_df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-tsv", type=Path, required=True)
    parser.add_argument("--ai-json", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, default=Path("outputs/04_AGENTIC_AI_ASSIST/validation"))
    args = parser.parse_args()

    summary, issues = validate(args.packet_tsv, args.ai_json, args.outdir)

    print("\nVALIDATION SUMMARY")
    print(summary.to_string(index=False))

    print("\nTOP ISSUES")
    if len(issues):
        print(issues.head(40).to_string(index=False))
    else:
        print("No issues found.")


if __name__ == "__main__":
    main()
