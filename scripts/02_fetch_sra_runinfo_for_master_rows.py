#!/usr/bin/env python3

from pathlib import Path
import argparse
import time
from io import StringIO
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
CACHE = DATA / "sra_runinfo_cache"
CACHE.mkdir(parents=True, exist_ok=True)

RUNINFO_URL = "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def fetch_runinfo_chunk(runs):
    acc = ",".join(runs)
    resp = requests.get(RUNINFO_URL, params={"acc": acc}, timeout=60)
    resp.raise_for_status()

    text = resp.text.strip()
    if not text:
        return pd.DataFrame()

    return pd.read_csv(StringIO(text), dtype=str).fillna("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pmid = clean(args.pmid)
    subset_file = OUT / f"PMID_{pmid}_master_subset.tsv"
    cache_file = CACHE / f"PMID_{pmid}_sra_runinfo.csv"
    out_summary = OUT / f"PMID_{pmid}_sra_runinfo_summary.tsv"

    if not subset_file.exists():
        raise FileNotFoundError(f"Missing master subset: {subset_file}. Run script 01 first.")

    subset = pd.read_csv(subset_file, sep="\t", dtype=str).fillna("")

    if "_run_norm" not in subset.columns:
        raise ValueError("Expected _run_norm column in master subset.")

    master_runs = sorted({clean(x) for x in subset["_run_norm"] if clean(x)})

    print(f"\n=== Fetching SRA RunInfo for PMID {pmid} ===")
    print(f"Master rows/runs: {subset.shape[0]} rows, {len(master_runs)} unique runs")

    if cache_file.exists() and not args.force:
        print(f"Using cached RunInfo: {cache_file}")
        runinfo = pd.read_csv(cache_file, dtype=str).fillna("")
    else:
        frames = []
        for i in range(0, len(master_runs), args.chunk_size):
            chunk = master_runs[i:i + args.chunk_size]
            print(f"Fetching runs {i + 1}-{i + len(chunk)} of {len(master_runs)}")
            df = fetch_runinfo_chunk(chunk)
            frames.append(df)
            time.sleep(args.sleep)

        runinfo = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        runinfo.to_csv(cache_file, index=False)

    if runinfo.empty:
        raise RuntimeError("No SRA RunInfo metadata retrieved.")

    run_col = "Run" if "Run" in runinfo.columns else None
    if run_col is None:
        raise ValueError("SRA RunInfo did not include a Run column.")

    runinfo["_run_norm"] = runinfo[run_col].map(clean)

    found_runs = set(runinfo["_run_norm"])
    missing_from_sra = sorted(set(master_runs) - found_runs)
    extra_from_sra = sorted(found_runs - set(master_runs))

    # Coverage for biologically useful columns
    useful_cols = [
        "source_name",
        "genotype",
        "strain",
        "Development_stage",
        "Sample Name",
        "GEO_Accession (exp)",
        "BioSample",
        "BioProject",
        "LibraryStrategy",
        "LibrarySource",
    ]

    rows = []
    for col in useful_cols:
        if col in runinfo.columns:
            n_nonempty = int(runinfo[col].astype(str).str.strip().ne("").sum())
            n_unique = int(runinfo[col].astype(str).str.strip().replace("", pd.NA).dropna().nunique())
        else:
            n_nonempty = 0
            n_unique = 0

        rows.append({
            "column": col,
            "present": col in runinfo.columns,
            "nonempty_count": n_nonempty,
            "unique_nonempty_count": n_unique,
        })

    summary = pd.DataFrame(rows)
    summary.to_csv(out_summary, sep="\t", index=False)

    print("\nRun overlap:")
    print(f"Master runs: {len(master_runs)}")
    print(f"SRA RunInfo runs: {len(found_runs)}")
    print(f"Master runs missing from SRA RunInfo: {len(missing_from_sra)}")
    print(f"SRA RunInfo runs not in master subset: {len(extra_from_sra)}")

    print("\nUseful SRA metadata coverage:")
    print(summary.to_string(index=False))

    print("\nWrote:")
    print(cache_file)
    print(out_summary)
    print("\nDone.")


if __name__ == "__main__":
    main()
