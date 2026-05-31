#!/usr/bin/env python3

from pathlib import Path
import argparse
import time
import xml.etree.ElementTree as ET
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
CACHE = DATA / "biosample_cache"
CACHE.mkdir(parents=True, exist_ok=True)

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def find_col(df, candidates):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in lookup:
            return lookup[key]
    return None


def request_with_retries(url, params, max_retries=6, base_sleep=2.0):
    last_error = None

    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=60)

            if r.status_code == 429:
                wait = base_sleep * (2 ** attempt)
                print(f"  hit 429 rate limit; sleeping {wait:.1f}s")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except Exception as e:
            last_error = e
            wait = base_sleep * (2 ** attempt)
            print(f"  request error: {e}; sleeping {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"Request failed after retries: {last_error}")


def esearch_biosample_uid(accession, email=None):
    params = {
        "db": "biosample",
        "term": f"{accession}[Accession]",
        "retmode": "json",
    }
    if email:
        params["email"] = email

    r = request_with_retries(ESEARCH, params)
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else ""


def efetch_biosample_xml(uid, email=None):
    params = {
        "db": "biosample",
        "id": uid,
        "retmode": "xml",
    }
    if email:
        params["email"] = email

    r = request_with_retries(EFETCH, params)
    return r.text


def parse_biosample_xml(xml_text, accession_hint=""):
    out = {
        "BioSample": accession_hint,
        "biosample_uid": "",
        "biosample_accession": accession_hint,
        "biosample_title": "",
        "biosample_organism": "",
        "biosample_taxid": "",
    }

    root = ET.fromstring(xml_text)

    biosamples = root.findall(".//BioSample")
    if not biosamples and root.tag == "BioSample":
        biosamples = [root]

    if not biosamples:
        out["parse_error"] = "no BioSample node found"
        return out

    bs = biosamples[0]

    out["biosample_uid"] = clean(bs.attrib.get("id", ""))
    out["biosample_accession"] = clean(bs.attrib.get("accession", accession_hint))
    out["BioSample"] = out["biosample_accession"] or accession_hint

    title_node = bs.find(".//Title")
    if title_node is not None and title_node.text:
        out["biosample_title"] = clean(title_node.text)

    org_node = bs.find(".//Organism")
    if org_node is not None:
        out["biosample_organism"] = clean(org_node.attrib.get("taxonomy_name", ""))
        out["biosample_taxid"] = clean(org_node.attrib.get("taxonomy_id", ""))

    for attr in bs.findall(".//Attributes/Attribute"):
        val = clean(attr.text)
        if not val:
            continue

        names = []
        for key in ["attribute_name", "harmonized_name", "display_name"]:
            nm = clean(attr.attrib.get(key, ""))
            if nm:
                names.append(nm)

        for nm in names:
            col = "biosample_attr__" + nm.strip().replace(" ", "_")
            if col not in out:
                out[col] = val

    return out


def summarize(attrs, pmid):
    useful_patterns = [
        "source", "genotype", "strain", "stage", "development",
        "treatment", "condition", "title", "organism"
    ]

    useful_cols = [
        c for c in attrs.columns
        if any(p in c.lower() for p in useful_patterns)
    ]

    rows = []
    for c in useful_cols:
        s = attrs[c].astype(str).str.strip()
        top = (
            s.replace("", pd.NA)
            .dropna()
            .value_counts()
            .head(8)
        )
        rows.append({
            "column": c,
            "nonempty_count": int(s.ne("").sum()),
            "unique_nonempty_count": int(s.replace("", pd.NA).dropna().nunique()),
            "top_values": "; ".join([f"{k} ({v})" for k, v in top.items()]),
        })

    summary = pd.DataFrame(rows)
    summary_file = OUT / f"PMID_{pmid}_biosample_attribute_summary.tsv"
    summary.to_csv(summary_file, sep="\t", index=False)

    print("\nBioSample fetch status:")
    print(attrs["fetch_status"].value_counts(dropna=False).to_string())

    print("\nUseful BioSample attribute coverage:")
    if summary.empty:
        print("No useful source/genotype/stage/strain-like BioSample attributes detected.")
    else:
        print(summary.to_string(index=False))

    print("\nWrote:")
    print(summary_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--email", default="")
    parser.add_argument("--sleep", type=float, default=1.5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pmid = clean(args.pmid)
    subset_file = OUT / f"PMID_{pmid}_master_subset.tsv"
    cache_file = CACHE / f"PMID_{pmid}_biosample_attributes.tsv"

    if not subset_file.exists():
        raise FileNotFoundError(f"Missing master subset: {subset_file}. Run script 01 first.")

    subset = pd.read_csv(subset_file, sep="\t", dtype=str).fillna("")
    biosample_col = find_col(subset, ["BioSample", "BioSample ID", "biosample"])

    if biosample_col is None:
        raise ValueError("Could not find BioSample column in master subset.")

    biosamples = sorted({clean(x) for x in subset[biosample_col] if clean(x)})

    print(f"\n=== Fetching BioSample attributes for PMID {pmid} ===")
    print(f"BioSamples from master subset: {len(biosamples)}")

    existing = pd.DataFrame()

    if cache_file.exists() and not args.force:
        existing = pd.read_csv(cache_file, sep="\t", dtype=str).fillna("")
        print(f"Loaded existing cache: {cache_file}")
        print(existing["fetch_status"].value_counts(dropna=False).to_string())

    existing_ok = set()
    if not existing.empty and "BioSample" in existing.columns and "fetch_status" in existing.columns:
        existing_ok = set(existing.loc[existing["fetch_status"] == "ok", "BioSample"].map(clean))

    to_fetch = biosamples if args.force else [b for b in biosamples if b not in existing_ok]

    print(f"Already OK: {len(existing_ok)}")
    print(f"To fetch/retry: {len(to_fetch)}")

    rows = []

    if not existing.empty and not args.force:
        rows.extend(existing.to_dict(orient="records"))

    # Remove non-ok rows for BioSamples we are retrying, so old errors do not remain duplicated.
    if rows:
        retry_set = set(to_fetch)
        rows = [
            r for r in rows
            if clean(r.get("BioSample", "")) not in retry_set
        ]

    for i, accession in enumerate(to_fetch, start=1):
        print(f"[{i}/{len(to_fetch)}] {accession}")

        row = {
            "BioSample": accession,
            "biosample_accession": accession,
            "biosample_uid": "",
            "fetch_status": "",
            "fetch_error": "",
        }

        try:
            uid = esearch_biosample_uid(accession, email=args.email)
            row["biosample_uid"] = uid

            if not uid:
                row["fetch_status"] = "not_found"
                rows.append(row)
                time.sleep(args.sleep)
                continue

            xml_text = efetch_biosample_xml(uid, email=args.email)
            parsed = parse_biosample_xml(xml_text, accession_hint=accession)
            row.update(parsed)
            row["fetch_status"] = "ok"

        except Exception as e:
            row["fetch_status"] = "error"
            row["fetch_error"] = str(e)

        rows.append(row)
        time.sleep(args.sleep)

    attrs = pd.DataFrame(rows).fillna("")
    attrs = attrs.drop_duplicates(subset=["BioSample"], keep="last")
    attrs.to_csv(cache_file, sep="\t", index=False)

    summarize(attrs, pmid)

    print("\nCache:")
    print(cache_file)
    print("\nDone.")


if __name__ == "__main__":
    main()
