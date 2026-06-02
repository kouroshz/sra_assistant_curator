#!/usr/bin/env python3

"""
Fetch/cache public SRA RunInfo and BioSample XML metadata.

This script is deterministic and does NOT call OpenAI.

Inputs:
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv

Caches:
  data/sra_runinfo_cache/<Run>.csv
  data/biosample_cache/<BioSample>.xml

Summary:
  outputs/02_QC_SUMMARIES/public_metadata_fetch_summary.tsv

Notes:
  - Safe to rerun; existing cache files are skipped unless --force.
  - Uses local .env if present for NCBI_EMAIL, NCBI_API_KEY, NCBI_TOOL.
"""

from __future__ import annotations

import argparse
import csv
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


DEFAULT_ROWWISE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_master_with_stable_ids.tsv")
DEFAULT_SRA_CACHE = Path("data/sra_runinfo_cache")
DEFAULT_BIOSAMPLE_CACHE = Path("data/biosample_cache")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/public_metadata_fetch_summary.tsv")


def clean_value(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(Path(".env"))


def urlopen_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "sra_paper_curator/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def add_eutils_params(params: dict) -> dict:
    params = dict(params)
    email = os.getenv("NCBI_EMAIL", "").strip()
    api_key = os.getenv("NCBI_API_KEY", "").strip()
    tool = os.getenv("NCBI_TOOL", "sra_paper_curator").strip() or "sra_paper_curator"

    params["tool"] = tool
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def esearch_biosample_uid(accession: str) -> str:
    """Resolve BioSample accession to Entrez UID."""
    params = add_eutils_params({
        "db": "biosample",
        "term": accession,
        "retmode": "xml",
    })
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    text = urlopen_text(url)

    try:
        root = ET.fromstring(text)
        ids = [x.text for x in root.findall(".//Id") if x.text]
    except Exception:
        ids = []

    if not ids:
        return ""
    return ids[0]


def fetch_sra_runinfo(run: str) -> str:
    """
    Fetch SRA RunInfo CSV for a run.

    The trace runinfo endpoint is commonly used for run-level CSV metadata.
    """
    params = urllib.parse.urlencode({"acc": run})
    url = f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?{params}"
    return urlopen_text(url)


def fetch_biosample_xml(biosample: str) -> tuple[str, str]:
    """
    Fetch BioSample XML via E-utilities.

    BioSample efetch is more reliable after resolving accession -> UID with esearch.
    Returns (xml_text, uid).
    """
    uid = esearch_biosample_uid(biosample)
    if not uid:
        return f"ERROR: could not resolve BioSample accession to UID: {biosample}\n", ""

    params = add_eutils_params({
        "db": "biosample",
        "id": uid,
        "retmode": "xml",
    })
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(params)
    return urlopen_text(url), uid


def looks_like_runinfo_csv(text: str, run: str) -> bool:
    if not text.strip():
        return False
    first = text.splitlines()[0].lower()
    return "run" in first and (run in text or "run," in first or first.startswith("run"))


def looks_like_biosample_xml(text: str, biosample: str) -> bool:
    low = text.lower()
    if "<biosampleset></biosampleset>" in low.replace("\n", "").replace(" ", ""):
        return False
    return "<biosample " in low or "<biosample>" in low or biosample.lower() in low


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rowwise", type=Path, default=DEFAULT_ROWWISE)
    parser.add_argument("--sra-cache", type=Path, default=DEFAULT_SRA_CACHE)
    parser.add_argument("--biosample-cache", type=Path, default=DEFAULT_BIOSAMPLE_CACHE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between requests. BioSample fetch uses esearch + efetch, so keep this conservative.")
    parser.add_argument("--max-runs", type=int, default=None, help="Pilot limit on number of runs.")
    parser.add_argument("--max-biosamples", type=int, default=None, help="Pilot limit on number of BioSamples.")
    parser.add_argument("--force", action="store_true", help="Refetch existing cache files.")
    args = parser.parse_args()

    load_env()

    if not args.rowwise.exists():
        raise FileNotFoundError(f"Missing rowwise table: {args.rowwise}")

    args.sra_cache.mkdir(parents=True, exist_ok=True)
    args.biosample_cache.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.rowwise, sep="\t", dtype=str)

    runs = []
    if "Run" in df.columns:
        runs = sorted(set(clean_value(x) for x in df["Run"] if clean_value(x)))
    biosamples = []
    if "BioSample" in df.columns:
        biosamples = sorted(set(clean_value(x) for x in df["BioSample"] if clean_value(x)))

    if args.max_runs is not None:
        runs = runs[: args.max_runs]
    if args.max_biosamples is not None:
        biosamples = biosamples[: args.max_biosamples]

    events = []

    for i, run in enumerate(runs, start=1):
        out = args.sra_cache / f"{run}.csv"
        if out.exists() and not args.force:
            events.append({"type": "sra_runinfo", "id": run, "status": "cached", "path": str(out)})
            continue

        try:
            text = fetch_sra_runinfo(run)
            status = "ok" if looks_like_runinfo_csv(text, run) else "warning_unexpected_content"
            out.write_text(text)
        except Exception as e:
            status = f"error:{type(e).__name__}:{e}"
            out.write_text(f"ERROR fetching {run}: {e}\n")

        events.append({"type": "sra_runinfo", "id": run, "status": status, "path": str(out)})
        time.sleep(args.sleep)

    for i, biosample in enumerate(biosamples, start=1):
        out = args.biosample_cache / f"{biosample}.xml"
        if out.exists() and not args.force:
            events.append({"type": "biosample_xml", "id": biosample, "status": "cached", "path": str(out)})
            continue

        try:
            text, uid = fetch_biosample_xml(biosample)
            status = "ok" if looks_like_biosample_xml(text, biosample) else "warning_unexpected_content"
            out.write_text(text)
        except Exception as e:
            uid = ""
            status = f"error:{type(e).__name__}:{e}"
            out.write_text(f"ERROR fetching {biosample}: {e}\n")

        events.append({"type": "biosample_xml", "id": biosample, "uid": uid, "status": status, "path": str(out)})
        time.sleep(args.sleep)

    summary = pd.DataFrame(events)
    summary.to_csv(args.summary, sep="\t", index=False)

    print(f"Runs requested:       {len(runs)}")
    print(f"BioSamples requested: {len(biosamples)}")
    print(f"Wrote summary:        {args.summary}")
    print(summary["status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
