#!/usr/bin/env python3

"""
Resolve or flag publication links for paper/BioProject packets.

This script does NOT call OpenAI.

Purpose:
  - Treat missing PMID as a gating QC issue.
  - Try deterministic/public resolution before AI.
  - Mark unresolved BioProjects as publication_unresolved_hold.

Inputs:
  outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv
  outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv
  papers/

Outputs:
  outputs/02_QC_SUMMARIES/publication_resolution_by_packet.tsv
  outputs/02_QC_SUMMARIES/publication_resolution_summary.tsv
"""

from __future__ import annotations

import argparse
import os
import re
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


DEFAULT_PACKET_INDEX = Path("outputs/04_AGENTIC_AI_ASSIST/paper_packets/paper_packet_index.tsv")
DEFAULT_EVIDENCE = Path("outputs/01_CURRENT_DRAFT_TABLES/rowwise_public_metadata_evidence.tsv")
DEFAULT_PAPERS_DIR = Path("papers")
DEFAULT_OUT = Path("outputs/02_QC_SUMMARIES/publication_resolution_by_packet.tsv")
DEFAULT_SUMMARY = Path("outputs/02_QC_SUMMARIES/publication_resolution_summary.tsv")


def clean(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.lower() in {"nan", "none", "na", "n/a", "<na>"}:
        return ""
    return s


def norm_pmid(x) -> str:
    s = clean(x)
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if not s or s.lower() == "nopmid":
        return ""
    return s


def valid_pmid(x) -> bool:
    s = norm_pmid(x)
    # PubMed IDs can be shorter historically, but current useful paper PMIDs here should not be "3".
    return bool(re.fullmatch(r"\d{6,9}", s))


def load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(Path(".env"))


def eutils_params(params: dict) -> dict:
    params = dict(params)
    tool = os.getenv("NCBI_TOOL", "sra_paper_curator").strip() or "sra_paper_curator"
    email = os.getenv("NCBI_EMAIL", "").strip()
    api_key = os.getenv("NCBI_API_KEY", "").strip()

    params["tool"] = tool
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def urlopen_text(url: str, timeout: int = 60, retries: int = 4, backoff: float = 2.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "sra_paper_curator/0.1"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(backoff * (i + 1))
    raise last


def esearch_ids(db: str, term: str, retmax: int = 20) -> list[str]:
    params = eutils_params({
        "db": db,
        "term": term,
        "retmode": "xml",
        "retmax": str(retmax),
    })
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    txt = urlopen_text(url)
    try:
        root = ET.fromstring(txt)
        return [x.text for x in root.findall(".//Id") if x.text]
    except Exception:
        return []


def elink_ids(dbfrom: str, db: str, uid: str) -> list[str]:
    params = eutils_params({
        "dbfrom": dbfrom,
        "db": db,
        "id": uid,
        "retmode": "xml",
    })
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?" + urllib.parse.urlencode(params)
    txt = urlopen_text(url)
    try:
        root = ET.fromstring(txt)
        return [x.text for x in root.findall(".//LinkSetDb/Link/Id") if x.text]
    except Exception:
        return []


def pubmed_search_for_accession(accession: str, organism_hint: str = "Plasmodium") -> list[str]:
    queries = [
        accession,
        f"{accession} {organism_hint}",
        f'"{accession}"',
    ]
    hits = []
    for q in queries:
        ids = esearch_ids("pubmed", q, retmax=10)
        for x in ids:
            if x not in hits:
                hits.append(x)
        time.sleep(0.34)
    return hits


def bioproject_to_pubmed(bioproject: str) -> tuple[list[str], list[str]]:
    """
    Return (pubmed_ids, bioproject_uids).
    """
    bp_uids = esearch_ids("bioproject", bioproject, retmax=10)
    pmids = []
    for uid in bp_uids:
        linked = elink_ids("bioproject", "pubmed", uid)
        for p in linked:
            if p not in pmids:
                pmids.append(p)
        time.sleep(0.34)
    return pmids, bp_uids


def find_local_pdfs_for_token(papers_dir: Path, token: str) -> list[str]:
    if not token or not papers_dir.exists():
        return []
    token = str(token)
    hits = []
    for pdf in papers_dir.glob("*.pdf"):
        if token in pdf.name:
            hits.append(str(pdf))
    return sorted(hits)


def collect_gsm_gse_tokens(g: pd.DataFrame, max_tokens: int = 20) -> list[str]:
    cols = [
        "sra_SampleName", "SampleName", "sra_LibraryName", "LibraryName",
        "biosample_title", "biosample_attr_sample_name", "biosample_attr_submitter_id",
        "public_metadata_evidence_compact",
    ]
    text = " ".join(
        " ".join(g[c].fillna("").astype(str).head(200).tolist())
        for c in cols if c in g.columns
    )
    tokens = []
    for pat in [r"\bGSE\d+\b", r"\bGSM\d+\b"]:
        for m in re.findall(pat, text):
            if m not in tokens:
                tokens.append(m)
            if len(tokens) >= max_tokens:
                return tokens
    return tokens


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-index", type=Path, default=DEFAULT_PACKET_INDEX)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--papers-dir", type=Path, default=DEFAULT_PAPERS_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--only-nopmid", action="store_true", default=True)
    args = parser.parse_args()

    load_env()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    idx = pd.read_csv(args.packet_index, sep="\t", dtype=str).fillna("")
    evidence = pd.read_csv(args.evidence, sep="\t", dtype=str).fillna("")

    # Normalize packet unit keys.
    evidence["PMID_norm"] = evidence["PMID"].map(norm_pmid) if "PMID" in evidence.columns else ""
    evidence["packet_pmid_norm"] = evidence["PMID_norm"].replace("", "noPMID")
    evidence["packet_bioproject"] = evidence["BioProject"].map(lambda x: clean(x) or "noBioProject")

    rows = []

    for _, r in idx.iterrows():
        packet_id = clean(r.get("packet_id", ""))
        current_pmid = norm_pmid(r.get("pmid", ""))
        bioproject = clean(r.get("bioproject", ""))

        if args.only_nopmid and current_pmid:
            status = "already_has_master_pmid"
            rows.append({
                **r.to_dict(),
                "publication_resolution_status": status,
                "resolved_pmid": current_pmid,
                "resolved_source": "master_packet_index",
                "resolved_confidence": "high",
                "candidate_pmids": current_pmid,
                "candidate_bioproject_uids": "",
                "candidate_geo_tokens": "",
                "local_pdf_candidates_after_resolution": clean(r.get("paper_pdf_candidates", "")),
                "publication_resolution_note": "Packet already has PMID.",
            })
            continue

        g = evidence[
            (evidence["packet_pmid_norm"] == (current_pmid or "noPMID")) &
            (evidence["packet_bioproject"] == bioproject)
        ].copy()

        candidate_pmids = []
        sources = []
        notes = []

        # 1. SRA Study_Pubmed_id from runinfo, if valid.
        if "sra_Study_Pubmed_id" in g.columns:
            vals = sorted(set(norm_pmid(x) for x in g["sra_Study_Pubmed_id"] if valid_pmid(x)))
            for v in vals:
                if v not in candidate_pmids:
                    candidate_pmids.append(v)
            if vals:
                sources.append("sra_Study_Pubmed_id")

        # 2. BioProject -> PubMed ELink.
        bp_pmids = []
        bp_uids = []
        if bioproject and bioproject != "noBioProject":
            try:
                bp_pmids, bp_uids = bioproject_to_pubmed(bioproject)
                for v in bp_pmids:
                    if valid_pmid(v) and v not in candidate_pmids:
                        candidate_pmids.append(v)
                if bp_pmids:
                    sources.append("ncbi_bioproject_elink_pubmed")
            except Exception as e:
                notes.append(f"bioproject_elink_error:{type(e).__name__}:{e}")
            time.sleep(args.sleep)

        # 3. PubMed search by BioProject accession.
        search_pmids = []
        if bioproject and bioproject != "noBioProject":
            try:
                search_pmids = pubmed_search_for_accession(bioproject)
                for v in search_pmids:
                    if valid_pmid(v) and v not in candidate_pmids:
                        candidate_pmids.append(v)
                if search_pmids:
                    sources.append("pubmed_search_bioproject")
            except Exception as e:
                notes.append(f"pubmed_search_error:{type(e).__name__}:{e}")
            time.sleep(args.sleep)

        # 4. GEO/GSM/GSE tokens, not fully resolved yet.
        geo_tokens = collect_gsm_gse_tokens(g)

        # 5. Local PDFs by resolved PMID.
        pdf_hits = []
        for pmid in candidate_pmids:
            for p in find_local_pdfs_for_token(args.papers_dir, pmid):
                if p not in pdf_hits:
                    pdf_hits.append(p)

        if current_pmid:
            status = "already_has_master_pmid"
            resolved = current_pmid
            confidence = "high"
            source = "master_packet_index"
        elif len(candidate_pmids) == 1:
            status = "resolved_to_single_pmid"
            resolved = candidate_pmids[0]
            confidence = "high" if pdf_hits else "medium"
            source = "+".join(sorted(set(sources))) if sources else "unknown"
        elif len(candidate_pmids) > 1:
            status = "multiple_candidate_pmids_needs_review"
            resolved = ""
            confidence = "low"
            source = "+".join(sorted(set(sources))) if sources else "unknown"
        elif geo_tokens:
            status = "geo_tokens_found_needs_geo_resolution"
            resolved = ""
            confidence = "low"
            source = "geo_token_detected"
        else:
            status = "publication_unresolved_hold"
            resolved = ""
            confidence = "low"
            source = "none"

        rows.append({
            **r.to_dict(),
            "publication_resolution_status": status,
            "resolved_pmid": resolved,
            "resolved_source": source,
            "resolved_confidence": confidence,
            "candidate_pmids": ";".join(candidate_pmids),
            "candidate_bioproject_uids": ";".join(bp_uids),
            "candidate_geo_tokens": ";".join(geo_tokens[:30]),
            "local_pdf_candidates_after_resolution": ";".join(pdf_hits),
            "publication_resolution_note": ";".join(notes),
        })

    out = pd.DataFrame(rows)
    out.to_csv(args.out, sep="\t", index=False)

    summary = []
    summary.append({"metric": "n_packets", "value": len(out)})
    for col in ["publication_resolution_status", "resolved_confidence", "resolved_source"]:
        counts = out[col].value_counts(dropna=False)
        for k, v in counts.items():
            summary.append({"metric": f"{col}:{k}", "value": int(v)})

    summary.append({"metric": "n_packets_with_resolved_pmid", "value": int(out["resolved_pmid"].map(clean).astype(bool).sum())})
    summary.append({"metric": "n_packets_with_candidate_pmids", "value": int(out["candidate_pmids"].map(clean).astype(bool).sum())})
    summary.append({"metric": "n_packets_with_geo_tokens", "value": int(out["candidate_geo_tokens"].map(clean).astype(bool).sum())})
    summary.append({"metric": "output_table", "value": str(args.out)})

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(args.summary, sep="\t", index=False)

    print(f"Wrote publication resolution table: {args.out}")
    print(f"Wrote summary: {args.summary}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
