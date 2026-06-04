#!/usr/bin/env python3
"""
Resolve ChIP BioProject publication links using Entrez links/searches.

This follows the RNA strategy:
  public metadata -> publication candidates -> confidence-scored backfill suggestions.

Reads:
  outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_publication_signal_by_bioproject.tsv
  outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_ap2_publication_signal_by_bioproject.tsv

Writes:
  outputs/06_CHIP_AI_ASSIST/04_publication_resolution/
    chip_entrez_publication_candidates_long.tsv
    chip_entrez_publication_resolution_by_bioproject.tsv
    chip_ap2_entrez_publication_resolution.tsv
    chip_publication_backfill_suggestions.tsv
    CHIP_ENTREZ_PUBLICATION_RESOLUTION_REPORT.md

Environment:
  NCBI_EMAIL   recommended
  NCBI_API_KEY optional
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os
import re
import time
import pandas as pd


BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "sra_paper_curator_chip_entrez_publication_resolver"
EMAIL = os.environ.get("NCBI_EMAIL", "")
API_KEY = os.environ.get("NCBI_API_KEY", "")
SLEEP = 0.12 if API_KEY else 0.36

IN_GROUPS = Path("outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_publication_signal_by_bioproject.tsv")
IN_AP2 = Path("outputs/06_CHIP_AI_ASSIST/03_public_metadata/chip_ap2_publication_signal_by_bioproject.tsv")

OUT = Path("outputs/06_CHIP_AI_ASSIST/04_publication_resolution")
OUT.mkdir(parents=True, exist_ok=True)


def clean(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def split_vals(x: str) -> list[str]:
    x = clean(x)
    if not x:
        return []
    parts = re.split(r"[;|,]\s*|\s+", x)
    return [clean(p) for p in parts if clean(p)]


def is_pmid(x: str) -> bool:
    return bool(re.fullmatch(r"\d{6,9}", clean(x)))


def unique_sorted(xs):
    vals = sorted(set(clean(x) for x in xs if clean(x)))
    return vals


def extract_tokens(text: str, prefix: str, limit: int = 25) -> list[str]:
    text = clean(text)
    if not text:
        return []
    pat = {
        "GSE": r"\bGSE\d+\b",
        "GSM": r"\bGSM\d+\b",
        "SRP": r"\bSRP\d+\b",
        "SRX": r"\bSRX\d+\b",
        "SRR": r"\bSRR\d+\b",
        "PRJ": r"\bPRJ(?:NA|EB|DB)\d+\b",
        "ERP": r"\bERP\d+\b",
    }[prefix]
    vals = unique_sorted(m.group(0).upper() for m in re.finditer(pat, text, flags=re.I))
    return vals[:limit]


def eutils(endpoint: str, params: dict, retmode: str = "json", max_tries: int = 3):
    p = dict(params)
    p["tool"] = TOOL
    if EMAIL:
        p["email"] = EMAIL
    if API_KEY:
        p["api_key"] = API_KEY
    if retmode:
        p["retmode"] = retmode

    url = f"{BASE}/{endpoint}?{urlencode(p)}"
    last_err = None

    for attempt in range(1, max_tries + 1):
        try:
            time.sleep(SLEEP)
            req = Request(url, headers={"User-Agent": f"{TOOL}/1.0"})
            with urlopen(req, timeout=45) as fh:
                raw = fh.read().decode("utf-8", errors="replace")
            if retmode == "json":
                return json.loads(raw)
            return raw
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(0.7 * attempt)

    print(f"WARNING: failed {endpoint} {params}: {last_err}")
    return {} if retmode == "json" else ""


def esearch(db: str, term: str, retmax: int = 30) -> list[str]:
    obj = eutils("esearch.fcgi", {"db": db, "term": term, "retmax": str(retmax)}, "json")
    return obj.get("esearchresult", {}).get("idlist", []) or []


def elink(dbfrom: str, db: str, ids: list[str]) -> list[str]:
    ids = [clean(x) for x in ids if clean(x)]
    if not ids:
        return []

    obj = eutils(
        "elink.fcgi",
        {"dbfrom": dbfrom, "db": db, "id": ",".join(ids)},
        "json",
    )

    found = []
    for linkset in obj.get("linksets", []) or []:
        for ldb in linkset.get("linksetdbs", []) or []:
            dbto = clean(ldb.get("dbto", "")).lower()
            lname = clean(ldb.get("linkname", "")).lower()
            if db.lower() == dbto or db.lower() in lname:
                found.extend([str(x) for x in ldb.get("links", []) or []])

    return sorted(set(found), key=lambda x: int(x) if x.isdigit() else x)


def pubmed_summary(pmids: list[str]) -> dict[str, dict]:
    pmids = [str(p) for p in unique_sorted(pmids) if is_pmid(p)]
    if not pmids:
        return {}

    obj = eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(pmids)}, "json")
    result = obj.get("result", {}) or {}

    out = {}
    for pmid in pmids:
        rec = result.get(str(pmid), {}) or {}
        doi = ""
        for aid in rec.get("articleids", []) or []:
            if clean(aid.get("idtype", "")).lower() == "doi":
                doi = clean(aid.get("value", ""))
        out[str(pmid)] = {
            "pmid": str(pmid),
            "title": clean(rec.get("title", "")),
            "journal": clean(rec.get("source", "")),
            "pubdate": clean(rec.get("pubdate", "")),
            "doi": doi,
            "authors": "; ".join(clean(a.get("name", "")) for a in rec.get("authors", [])[:8] if clean(a.get("name", ""))),
        }
    return out


def route_existing(row):
    vals = []
    for p in split_vals(row.get("existing_paper_link_pmids", "")):
        if is_pmid(p):
            vals.append(p)
    return vals


def route_bioproject_elink(bp):
    ids = esearch("bioproject", f'"{bp}"[Project Accession]', retmax=10)
    if not ids:
        ids = esearch("bioproject", f'"{bp}"[All Fields]', retmax=10)
    return elink("bioproject", "pubmed", ids)


def route_sra_elink_by_bioproject(bp):
    ids = esearch("sra", f'"{bp}"[All Fields]', retmax=200)
    return elink("sra", "pubmed", ids)


def route_gds_elink_by_geo_tokens(tokens_text):
    pmids = []
    # Prefer GSE, then GSM. GSM-only may still work but can be noisy/slow.
    tokens = extract_tokens(tokens_text, "GSE", 30)
    if not tokens:
        tokens = extract_tokens(tokens_text, "GSM", 20)

    for tok in tokens:
        ids = esearch("gds", f'"{tok}"[All Fields]', retmax=20)
        pmids.extend(elink("gds", "pubmed", ids))

    return unique_sorted(pmids)


def route_sra_elink_by_sra_tokens(tokens_text):
    pmids = []
    tokens = extract_tokens(tokens_text, "SRP", 15) + extract_tokens(tokens_text, "SRX", 15)
    for tok in unique_sorted(tokens)[:25]:
        ids = esearch("sra", f'"{tok}"[All Fields]', retmax=50)
        pmids.extend(elink("sra", "pubmed", ids))
    return unique_sorted(pmids)


def route_pubmed_search_bioproject(bp):
    return esearch("pubmed", f'"{bp}"[All Fields]', retmax=20)


def route_pubmed_search_targets(row):
    targets = []
    for t in split_vals(row.get("targets", "")):
        tl = t.lower()
        if not t or tl in {"input", "igg", "control", "background"}:
            continue
        # Avoid very generic tags.
        if tl in {"ha", "gfp", "flag", "myc"}:
            continue
        targets.append(t)

    targets = targets[:8]
    if not targets:
        return []

    target_query = " OR ".join(f'"{t}"[All Fields]' for t in targets)
    term = (
        '("Plasmodium falciparum"[All Fields] OR malaria[All Fields]) '
        f'AND ({target_query}) '
        'AND (ChIP[All Fields] OR "ChIP-seq"[All Fields] OR chromatin[All Fields] OR "CUT&RUN"[All Fields] OR "CUT&Tag"[All Fields])'
    )
    return esearch("pubmed", term, retmax=30)


def route_score(route: str) -> int:
    return {
        "existing_paper_link": 125,
        "bioproject_elink_pubmed": 115,
        "sra_elink_by_bioproject": 105,
        "gds_elink_by_geo_tokens": 95,
        "sra_elink_by_sra_tokens": 90,
        "pubmed_search_bioproject": 80,
        "pubmed_search_targets": 55,
    }.get(route, 20)


def biological_score(title: str, targets: str, is_ap2: bool) -> int:
    t = clean(title).lower()
    targets_l = clean(targets).lower()
    score = 0

    if "plasmodium" in t:
        score += 12
    if "falciparum" in t:
        score += 8
    if "malaria" in t:
        score += 5
    if "chip" in t or "chromatin" in t:
        score += 7
    if "transcription" in t or "transcription factor" in t:
        score += 5
    if is_ap2 and ("ap2" in t or "apiap2" in t):
        score += 15
    if "ap2" in targets_l and ("ap2" in t or "apiap2" in t):
        score += 10
    if "histone" in t and any(x in targets_l for x in ["h3", "h2a", "h2b", "h4"]):
        score += 8

    return score


def confidence(top_score: int, n_unique_top_pmids: int, routes_for_top: str) -> str:
    if top_score >= 125:
        return "existing_or_very_high"
    if top_score >= 110:
        return "high"
    if top_score >= 95:
        return "medium_high"
    if top_score >= 80:
        return "medium"
    if top_score >= 60:
        return "low"
    return "very_low"


def main():
    if not IN_GROUPS.exists():
        raise SystemExit(f"Missing input: {IN_GROUPS}")

    groups = pd.read_csv(IN_GROUPS, sep="\t", dtype=str).fillna("")

    for c in ["bioproject", "targets", "detected_accession_tokens", "publication_resolution_action", "n_rows", "n_ap2_rows"]:
        if c not in groups.columns:
            groups[c] = ""

    groups["is_ap2_group"] = pd.to_numeric(groups.get("n_ap2_rows", "0"), errors="coerce").fillna(0).astype(int) > 0
    groups["n_rows_num"] = pd.to_numeric(groups["n_rows"], errors="coerce").fillna(0).astype(int)

    # Prioritize AP2 groups, then groups with GEO tokens, then large groups.
    groups = groups.sort_values(
        ["is_ap2_group", "publication_resolution_action", "n_rows_num"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    all_rows = []
    summary_rows = []

    print(f"Groups to resolve: {len(groups)}")
    print(f"AP2 groups: {int(groups['is_ap2_group'].sum())}")
    print(f"NCBI_EMAIL set: {bool(EMAIL)}")
    print(f"NCBI_API_KEY set: {bool(API_KEY)}")

    for i, row in groups.iterrows():
        bp = clean(row["bioproject"])
        is_ap2 = bool(row["is_ap2_group"])
        targets = clean(row.get("targets", ""))
        toks = clean(row.get("detected_accession_tokens", ""))

        print(f"[{i+1}/{len(groups)}] {bp} ap2={is_ap2} rows={row.get('n_rows','')} action={row.get('publication_resolution_action','')}")

        route_map = {}

        route_map["existing_paper_link"] = route_existing(row)
        route_map["bioproject_elink_pubmed"] = route_bioproject_elink(bp)
        route_map["sra_elink_by_bioproject"] = route_sra_elink_by_bioproject(bp)
        route_map["gds_elink_by_geo_tokens"] = route_gds_elink_by_geo_tokens(toks)
        route_map["sra_elink_by_sra_tokens"] = route_sra_elink_by_sra_tokens(toks)
        route_map["pubmed_search_bioproject"] = route_pubmed_search_bioproject(bp)

        # Use target search mainly for AP2 or unresolved groups to avoid noise.
        if is_ap2 or not any(route_map.values()):
            route_map["pubmed_search_targets"] = route_pubmed_search_targets(row)
        else:
            route_map["pubmed_search_targets"] = []

        all_pmids = unique_sorted(p for vals in route_map.values() for p in vals if is_pmid(p))
        meta = pubmed_summary(all_pmids)

        cand_rows = []
        for route, pmids in route_map.items():
            for pmid in unique_sorted(p for p in pmids if is_pmid(p)):
                m = meta.get(str(pmid), {})
                score = route_score(route) + biological_score(m.get("title", ""), targets, is_ap2)
                cand_rows.append({
                    "bioproject": bp,
                    "route": route,
                    "candidate_pmid": str(pmid),
                    "candidate_score": score,
                    "candidate_title": m.get("title", ""),
                    "candidate_journal": m.get("journal", ""),
                    "candidate_pubdate": m.get("pubdate", ""),
                    "candidate_doi": m.get("doi", ""),
                    "candidate_authors": m.get("authors", ""),
                    "is_ap2_group": is_ap2,
                    "n_rows": clean(row.get("n_rows", "")),
                    "n_ap2_rows": clean(row.get("n_ap2_rows", "")),
                    "targets": targets,
                    "target_types": clean(row.get("target_types", "")),
                    "detected_accession_tokens": toks[:1000],
                })

        if cand_rows:
            cand = pd.DataFrame(cand_rows)
            # Same PMID may appear through multiple routes. Summarize routes and keep max score.
            agg = (
                cand.groupby(["bioproject", "candidate_pmid"], dropna=False)
                .agg(
                    candidate_score=("candidate_score", "max"),
                    routes=("route", lambda s: ";".join(sorted(set(s)))),
                    candidate_title=("candidate_title", "first"),
                    candidate_journal=("candidate_journal", "first"),
                    candidate_pubdate=("candidate_pubdate", "first"),
                    candidate_doi=("candidate_doi", "first"),
                    candidate_authors=("candidate_authors", "first"),
                    is_ap2_group=("is_ap2_group", "first"),
                    n_rows=("n_rows", "first"),
                    n_ap2_rows=("n_ap2_rows", "first"),
                    targets=("targets", "first"),
                    target_types=("target_types", "first"),
                    detected_accession_tokens=("detected_accession_tokens", "first"),
                )
                .reset_index()
                .sort_values("candidate_score", ascending=False)
            )
            all_rows.extend(agg.to_dict("records"))

            top = agg.iloc[0]
            top_score = int(top["candidate_score"])
            conf = confidence(top_score, len(agg), clean(top["routes"]))

            # Auto-suggest only medium_high or better. Medium needs manual review.
            suggested = clean(top["candidate_pmid"]) if conf in {"existing_or_very_high", "high", "medium_high"} else ""
            n_candidates = len(agg)
            top_title = clean(top["candidate_title"])
            top_routes = clean(top["routes"])
            top_pmid = clean(top["candidate_pmid"])
        else:
            conf = "none"
            suggested = ""
            n_candidates = 0
            top_score = ""
            top_title = ""
            top_routes = ""
            top_pmid = ""

        summary_rows.append({
            "bioproject": bp,
            "is_ap2_group": is_ap2,
            "n_rows": clean(row.get("n_rows", "")),
            "n_ap2_rows": clean(row.get("n_ap2_rows", "")),
            "targets": targets,
            "target_types": clean(row.get("target_types", "")),
            "publication_resolution_action_prior": clean(row.get("publication_resolution_action", "")),
            "n_candidates": n_candidates,
            "resolution_confidence": conf,
            "suggested_paper_link_pmid": suggested,
            "top_candidate_pmid": top_pmid,
            "top_candidate_score": top_score,
            "top_candidate_routes": top_routes,
            "top_candidate_title": top_title,
            "needs_manual_review": conf not in {"existing_or_very_high", "high", "medium_high"},
        })

    candidates = pd.DataFrame(all_rows)
    if not candidates.empty:
        candidates = candidates.sort_values(["bioproject", "candidate_score"], ascending=[True, False])

    summary = pd.DataFrame(summary_rows)
    if not summary.empty:
        summary = summary.sort_values(["is_ap2_group", "resolution_confidence", "n_rows"], ascending=[False, True, False])

    backfill = summary[summary["suggested_paper_link_pmid"].astype(str).str.strip() != ""].copy()
    ap2 = summary[summary["is_ap2_group"] == True].copy()

    candidates_path = OUT / "chip_entrez_publication_candidates_long.tsv"
    summary_path = OUT / "chip_entrez_publication_resolution_by_bioproject.tsv"
    ap2_path = OUT / "chip_ap2_entrez_publication_resolution.tsv"
    backfill_path = OUT / "chip_publication_backfill_suggestions.tsv"

    candidates.to_csv(candidates_path, sep="\t", index=False)
    summary.to_csv(summary_path, sep="\t", index=False)
    ap2.to_csv(ap2_path, sep="\t", index=False)
    backfill.to_csv(backfill_path, sep="\t", index=False)

    report = []
    report.append("# ChIP Entrez Publication Resolution Report")
    report.append("")
    report.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report.append("")
    report.append("## Inputs")
    report.append("")
    report.append(f"- `{IN_GROUPS}`")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- groups queried: {len(summary)}")
    report.append(f"- AP2 groups queried: {int(summary['is_ap2_group'].sum()) if not summary.empty else 0}")
    report.append(f"- groups with at least one candidate: {int((summary['n_candidates'].astype(int) > 0).sum()) if not summary.empty else 0}")
    report.append(f"- groups with auto backfill suggestion: {len(backfill)}")
    report.append("")
    report.append("## Confidence counts")
    report.append("")
    for k, v in summary["resolution_confidence"].value_counts().items():
        report.append(f"- {k}: {v}")
    report.append("")
    report.append("## AP2 publication resolution")
    report.append("")
    if ap2.empty:
        report.append("- none")
    else:
        for _, r in ap2.iterrows():
            report.append(
                f"- {r['bioproject']}: rows={r['n_rows']}; AP2_rows={r['n_ap2_rows']}; "
                f"targets={r['targets'][:160]}; "
                f"confidence={r['resolution_confidence']}; suggested={r['suggested_paper_link_pmid']}; "
                f"top={r['top_candidate_pmid']} routes={r['top_candidate_routes']}; "
                f"title={r['top_candidate_title'][:180]}"
            )
    report.append("")
    report.append("## Suggested backfills")
    report.append("")
    if backfill.empty:
        report.append("- none")
    else:
        for _, r in backfill.head(80).iterrows():
            report.append(
                f"- {r['bioproject']} -> PMID {r['suggested_paper_link_pmid']} "
                f"({r['resolution_confidence']}; routes={r['top_candidate_routes']}): "
                f"{r['top_candidate_title'][:180]}"
            )
    report.append("")
    report.append("## Files written")
    report.append("")
    for p in [candidates_path, summary_path, ap2_path, backfill_path]:
        report.append(f"- `{p}`")

    report_path = OUT / "CHIP_ENTREZ_PUBLICATION_RESOLUTION_REPORT.md"
    report_path.write_text("\n".join(report))

    print("Wrote:", candidates_path)
    print("Wrote:", summary_path)
    print("Wrote:", ap2_path)
    print("Wrote:", backfill_path)
    print("Wrote:", report_path)
    print()
    print("Confidence counts:")
    print(summary["resolution_confidence"].value_counts().to_string())
    print()
    print("AP2 resolution:")
    show = [
        "bioproject", "n_rows", "n_ap2_rows", "targets", "n_candidates",
        "resolution_confidence", "suggested_paper_link_pmid",
        "top_candidate_pmid", "top_candidate_routes", "top_candidate_title"
    ]
    print(ap2[show].to_string(index=False))


if __name__ == "__main__":
    main()
