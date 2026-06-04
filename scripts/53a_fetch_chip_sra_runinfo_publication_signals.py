#!/usr/bin/env python3
"""
Fetch NCBI/SRA RunInfo for ChIP runs and extract publication signals.

This is the first ChIP publication-resolution step.

Reads:
  outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv

Writes:
  outputs/06_CHIP_AI_ASSIST/03_public_metadata/
    chip_sra_runinfo.tsv
    chip_rowwise_evidence_sra_enriched.tsv
    chip_publication_signal_by_bioproject.tsv
    chip_ap2_publication_signal_by_bioproject.tsv
    CHIP_SRA_PUBLICATION_SIGNAL_REPORT.md

What this does:
  - Fetches NCBI SRA RunInfo for all ChIP SRR runs.
  - Merges SRA public metadata back onto our ChIP rowwise evidence.
  - Extracts PMID-like values from:
      existing paper_link
      SRA Study_Pubmed_id or similar columns
      any SRA RunInfo text fields
  - Extracts GEO/GSE/GSM/SRP/SRX/SRR-like tokens.
  - Flags paper_link vs NCBI/SRA PMID mismatches.
  - Prioritizes AP2-containing BioProjects.

This does NOT modify the master sheet.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import csv
import hashlib
import io
import os
import re
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import pandas as pd


IN_ROWWISE = Path("outputs/06_CHIP_AI_ASSIST/01_rowwise_evidence/chip_rowwise_evidence.tsv")
OUT = Path("outputs/06_CHIP_AI_ASSIST/03_public_metadata")
CACHE = OUT / "_runinfo_cache"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "")
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")

RUNINFO_URL = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo"


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def norm_col(x: str) -> str:
    x = clean(x)
    x = re.sub(r"[^A-Za-z0-9]+", "_", x).strip("_")
    return x


def norm_key(x: str) -> str:
    x = clean(x).lower()
    x = re.sub(r"[^a-z0-9]+", "_", x).strip("_")
    return x


def is_ap2_target(x: str) -> bool:
    x = clean(x).lower()
    return bool(re.search(r"\bpf?ap2|^ap2|ap214|ap2tel|gfpap2|ddgfpap", x))


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def split_semicolon(x: str) -> list[str]:
    x = clean(x)
    if not x:
        return []
    parts = re.split(r"[;,|]\s*|\s+", x)
    return [p for p in (clean(v) for v in parts) if p]


def unique_join(vals, max_len=1200) -> str:
    xs = sorted(set(clean(v) for v in vals if clean(v)))
    s = "; ".join(xs)
    return s[:max_len]


def extract_pmids_from_text(text: str) -> list[str]:
    text = clean(text)
    if not text:
        return []

    pmids = set()

    # Explicit PMID-like patterns.
    for pat in [
        r"\bPMID[:\s_=-]*(\d{6,9})\b",
        r"\bPubMed[:\s_=-]*(\d{6,9})\b",
        r"\bStudy_Pubmed_id[:\s_=-]*(\d{6,9})\b",
        r"\bpubmed_id[:\s_=-]*(\d{6,9})\b",
    ]:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            pmids.add(m.group(1))

    # Standalone numbers are too risky generally, so only accept if nearby PubMed/PMID.
    # But SRA RunInfo has dedicated columns handled elsewhere.

    return sorted(pmids, key=int)


def extract_accession_tokens(text: str) -> str:
    text = clean(text)
    if not text:
        return ""

    toks = set()
    patterns = [
        r"\bGSE\d+\b",
        r"\bGSM\d+\b",
        r"\bSRP\d+\b",
        r"\bSRX\d+\b",
        r"\bSRS\d+\b",
        r"\bSRR\d+\b",
        r"\bSAMN\d+\b",
        r"\bPRJNA\d+\b",
        r"\bPRJEB\d+\b",
        r"\bPRJDB\d+\b",
        r"\bERP\d+\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            toks.add(m.group(0).upper())

    return "; ".join(sorted(toks))


def chunked(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]


def fetch_runinfo_chunk(runs: list[str], max_tries: int = 3) -> pd.DataFrame:
    runs = [clean(r) for r in runs if clean(r)]
    key = hashlib.sha1(",".join(runs).encode("utf-8")).hexdigest()[:16]
    cache_path = CACHE / f"runinfo_{key}_{len(runs)}.csv"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return pd.read_csv(cache_path, dtype=str).fillna("")

    params = {"acc": ",".join(runs)}
    # The trace runinfo endpoint does not need email/API key, but keep fields in URL if present
    # for audit friendliness. It will ignore unknown params if unsupported.
    if NCBI_EMAIL:
        params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = RUNINFO_URL + "?" + urlencode(params)
    last_err = None

    for attempt in range(1, max_tries + 1):
        try:
            time.sleep(0.25)
            req = Request(url, headers={"User-Agent": "sra_paper_curator_chip_runinfo/1.0"})
            with urlopen(req, timeout=60) as fh:
                raw = fh.read().decode("utf-8", errors="replace")

            if not raw.strip():
                raise RuntimeError("empty RunInfo response")

            cache_path.write_text(raw)
            return pd.read_csv(io.StringIO(raw), dtype=str).fillna("")

        except Exception as e:
            last_err = e
            time.sleep(0.75 * attempt)

    print(f"WARNING: failed RunInfo chunk of {len(runs)} runs: {last_err}")
    return pd.DataFrame({"Run": runs, "runinfo_fetch_error": str(last_err)})


def find_sra_pubmed_columns(runinfo: pd.DataFrame) -> list[str]:
    cols = []
    for c in runinfo.columns:
        nc = norm_col(c).lower()
        if "pubmed" in nc or "pmid" in nc:
            cols.append(c)
    return cols


def collect_candidate_pmids(row: pd.Series, sra_pubmed_cols: list[str]) -> tuple[str, str, str]:
    existing = clean(row.get("publication_key", ""))
    existing_pmids = [existing] if is_pmid(existing) else []

    sra_pmids = set()
    for c in sra_pubmed_cols:
        val = clean(row.get(c, ""))
        if not val:
            continue
        for part in split_semicolon(val):
            if is_pmid(part):
                sra_pmids.add(part)

    # Search all SRA text fields for explicit PMID mentions.
    text = " | ".join(clean(v) for v in row.values)
    text_pmids = set(extract_pmids_from_text(text))

    all_pmids = sorted(set(existing_pmids) | sra_pmids | text_pmids, key=lambda x: int(x))

    return (
        ";".join(existing_pmids),
        ";".join(sorted(sra_pmids, key=lambda x: int(x))),
        ";".join(all_pmids),
    )


def main():
    if not IN_ROWWISE.exists():
        raise SystemExit(f"Missing input: {IN_ROWWISE}")

    chip = pd.read_csv(IN_ROWWISE, sep="\t", dtype=str).fillna("")

    if "run" not in chip.columns:
        raise SystemExit("Expected column 'run' in chip_rowwise_evidence.tsv")

    runs = sorted(set(chip["run"].map(clean)) - {""})
    print(f"ChIP runs to fetch RunInfo for: {len(runs)}")
    print(f"NCBI_EMAIL set: {bool(NCBI_EMAIL)}")
    print(f"NCBI_API_KEY set: {bool(NCBI_API_KEY)}")

    frames = []
    for i, rs in enumerate(chunked(runs, 100), start=1):
        print(f"Fetching RunInfo chunk {i}: {len(rs)} runs")
        frames.append(fetch_runinfo_chunk(rs))

    runinfo = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    runinfo = runinfo.fillna("")
    runinfo.columns = [norm_col(c) for c in runinfo.columns]

    # Ensure Run column exists.
    if "Run" not in runinfo.columns:
        possible = [c for c in runinfo.columns if c.lower() == "run"]
        if possible:
            runinfo = runinfo.rename(columns={possible[0]: "Run"})
        else:
            raise SystemExit("RunInfo output has no Run column.")

    # Deduplicate by Run.
    runinfo = runinfo.drop_duplicates("Run", keep="first")

    runinfo_path = OUT / "chip_sra_runinfo.tsv"
    runinfo.to_csv(runinfo_path, sep="\t", index=False)

    # Prefix SRA columns except Run.
    sra = runinfo.copy()
    rename = {c: f"sra_{c}" for c in sra.columns if c != "Run"}
    sra = sra.rename(columns=rename)

    enriched = chip.merge(sra, left_on="run", right_on="Run", how="left")
    if "Run" in enriched.columns:
        enriched = enriched.drop(columns=["Run"])

    sra_pubmed_cols = [f"sra_{c}" for c in find_sra_pubmed_columns(runinfo)]

    # Add candidate PMID fields.
    pmid_existing = []
    pmid_sra = []
    pmid_all = []
    for _, row in enriched.iterrows():
        e, s, a = collect_candidate_pmids(row, sra_pubmed_cols)
        pmid_existing.append(e)
        pmid_sra.append(s)
        pmid_all.append(a)

    enriched["existing_paper_link_pmid"] = pmid_existing
    enriched["sra_pubmed_candidate_pmids"] = pmid_sra
    enriched["all_detected_candidate_pmids"] = pmid_all

    def mismatch(row):
        existing = set(split_semicolon(row["existing_paper_link_pmid"]))
        sra_pmids = set(split_semicolon(row["sra_pubmed_candidate_pmids"]))
        if existing and sra_pmids and existing != sra_pmids:
            return "paper_link_sra_pubmed_mismatch"
        if (not existing) and sra_pmids:
            return "paper_link_blank_sra_pubmed_available"
        if existing and not sra_pmids:
            return "paper_link_present_no_sra_pubmed"
        if not existing and not sra_pmids:
            return "no_pmid_detected"
        return "paper_link_matches_sra_pubmed"

    enriched["publication_signal_status"] = enriched.apply(mismatch, axis=1)

    # GEO/accession token extraction.
    token_cols = [c for c in enriched.columns if c.startswith("sra_")] + [
        c for c in [
            "raw_metadata_joined", "chip_public_metadata_evidence_compact",
            "notes", "raw_metadata_col1", "raw_metadata_col2", "raw_metadata_col3"
        ] if c in enriched.columns
    ]
    enriched["detected_accession_tokens"] = [
        extract_accession_tokens(" | ".join(clean(row.get(c, "")) for c in token_cols))
        for _, row in enriched.iterrows()
    ]

    enriched["is_ap2_row"] = enriched["target_clean"].map(is_ap2_target) if "target_clean" in enriched.columns else False

    enriched_path = OUT / "chip_rowwise_evidence_sra_enriched.tsv"
    enriched.to_csv(enriched_path, sep="\t", index=False)

    # Group summary by BioProject.
    for c in ["publication_key", "bioproject", "target_clean", "target_type", "chip_role",
              "stage_combined", "strain_context", "condition_context",
              "all_detected_candidate_pmids", "sra_pubmed_candidate_pmids",
              "existing_paper_link_pmid", "detected_accession_tokens",
              "publication_signal_status"]:
        if c not in enriched.columns:
            enriched[c] = ""

    group = (
        enriched.groupby("bioproject", dropna=False)
        .agg(
            n_rows=("source_row_id", "count"),
            n_runs=("run", "nunique"),
            n_chip_ip_rows=("chip_role", lambda s: int((s == "chip_ip").sum())),
            n_background_control_rows=("chip_role", lambda s: int((s == "background_control").sum())),
            n_unique_targets=("target_clean", lambda s: int(pd.Series([x for x in s if clean(x)]).nunique())),
            targets=("target_clean", unique_join),
            target_types=("target_type", unique_join),
            existing_paper_link_pmids=("existing_paper_link_pmid", unique_join),
            sra_pubmed_candidate_pmids=("sra_pubmed_candidate_pmids", unique_join),
            all_detected_candidate_pmids=("all_detected_candidate_pmids", unique_join),
            publication_signal_statuses=("publication_signal_status", unique_join),
            detected_accession_tokens=("detected_accession_tokens", unique_join),
            stages=("stage_combined", unique_join),
            strains=("strain_context", unique_join),
            conditions=("condition_context", unique_join),
            n_ap2_rows=("is_ap2_row", lambda s: int(pd.Series(s).astype(bool).sum())),
        )
        .reset_index()
    )

    def suggested(row):
        existing = split_semicolon(row["existing_paper_link_pmids"])
        sra_pmids = split_semicolon(row["sra_pubmed_candidate_pmids"])
        all_pmids = split_semicolon(row["all_detected_candidate_pmids"])

        if existing and sra_pmids and set(existing) != set(sra_pmids):
            return "manual_review_pmid_mismatch"
        if existing:
            return "keep_existing_paper_link"
        if sra_pmids:
            return "backfill_from_sra_pubmed"
        if all_pmids:
            return "manual_review_detected_pmid"
        toks = clean(row["detected_accession_tokens"])
        if "GSE" in toks or "GSM" in toks:
            return "resolve_via_geo_tokens"
        return "needs_ncbi_elink_or_pubmed_search"

    group["publication_resolution_action"] = group.apply(suggested, axis=1)
    group["is_ap2_group"] = group["n_ap2_rows"].astype(int) > 0

    group = group.sort_values(["is_ap2_group", "publication_resolution_action", "n_rows"], ascending=[False, True, False])

    group_path = OUT / "chip_publication_signal_by_bioproject.tsv"
    group.to_csv(group_path, sep="\t", index=False)

    ap2 = group[group["is_ap2_group"]].copy()
    ap2_path = OUT / "chip_ap2_publication_signal_by_bioproject.tsv"
    ap2.to_csv(ap2_path, sep="\t", index=False)

    # Report.
    report = []
    report.append("# ChIP SRA Publication Signal Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Inputs")
    report.append("")
    report.append(f"- `{IN_ROWWISE}`")
    report.append("")
    report.append("## Outputs")
    report.append("")
    report.append(f"- `{runinfo_path}`")
    report.append(f"- `{enriched_path}`")
    report.append(f"- `{group_path}`")
    report.append(f"- `{ap2_path}`")
    report.append("")
    report.append("## Basic counts")
    report.append("")
    report.append(f"- ChIP rows: {len(enriched)}")
    report.append(f"- unique runs: {enriched['run'].nunique()}")
    report.append(f"- RunInfo rows fetched: {len(runinfo)}")
    report.append(f"- BioProjects: {group['bioproject'].nunique()}")
    report.append(f"- AP2-containing BioProjects: {int(group['is_ap2_group'].sum())}")
    report.append("")
    report.append("## Publication signal statuses, row-level")
    report.append("")
    for k, v in enriched["publication_signal_status"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## Publication resolution actions, BioProject-level")
    report.append("")
    for k, v in group["publication_resolution_action"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## AP2-containing BioProjects")
    report.append("")
    if ap2.empty:
        report.append("- none")
    else:
        for _, r in ap2.iterrows():
            report.append(
                f"- {r['bioproject']}: rows={r['n_rows']}; AP2_rows={r['n_ap2_rows']}; "
                f"targets={r['targets'][:180]}; "
                f"existing={r['existing_paper_link_pmids']}; "
                f"sra_pubmed={r['sra_pubmed_candidate_pmids']}; "
                f"action={r['publication_resolution_action']}"
            )

    report_path = OUT / "CHIP_SRA_PUBLICATION_SIGNAL_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", runinfo_path)
    print("Wrote:", enriched_path)
    print("Wrote:", group_path)
    print("Wrote:", ap2_path)
    print("Wrote:", report_path)
    print()
    print("Row-level publication signal statuses:")
    print(enriched["publication_signal_status"].value_counts().to_string())
    print()
    print("BioProject-level publication resolution actions:")
    print(group["publication_resolution_action"].value_counts().to_string())
    print()
    print("AP2 BioProjects:")
    show = [
        "bioproject", "n_rows", "n_ap2_rows", "targets",
        "existing_paper_link_pmids", "sra_pubmed_candidate_pmids",
        "all_detected_candidate_pmids", "publication_resolution_action"
    ]
    print(ap2[show].to_string(index=False))


if __name__ == "__main__":
    main()
