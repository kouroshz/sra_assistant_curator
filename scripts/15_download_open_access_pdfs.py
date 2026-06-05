#!/usr/bin/env python3

from pathlib import Path
import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional for shell-configured runs
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
PAPERS = ROOT / "papers"
PAPERS.mkdir(exist_ok=True)


USER_AGENT = "sra_paper_curator/0.1 (academic metadata curation; contact email provided)"
DEFAULT_NCBI_TOOL = "sra_paper_curator"
CHIP_PAPER_DIR = OUT / "06_CHIP_AI_ASSIST/07_papers"
CHIP_PMID_MANIFEST = CHIP_PAPER_DIR / "chip_pmids_needing_pdfs_for_downloader.tsv"
PMID_MANIFEST_CANDIDATES = [
    CHIP_PMID_MANIFEST,
    OUT / "pmids_needing_pdfs.tsv",
]


def clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def sanitize_filename(x, max_len=90):
    x = clean(x)
    x = re.sub(r"<[^>]+>", "", x)
    x = re.sub(r"[^\w\s.-]+", "", x)
    x = re.sub(r"\s+", "_", x).strip("._-")
    return x[:max_len] or "paper"


def existing_pdf(pmid):
    hits = sorted(PAPERS.glob(f"*{pmid}*.pdf"))
    return hits[0] if hits else None


def http_get(url, timeout=45):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/json,text/xml,text/html,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        headers = dict(r.headers.items())
        final_url = r.geturl()
    return data, headers, final_url


def is_pdf_bytes(data, headers=None):
    headers = headers or {}
    ctype = headers.get("Content-Type", headers.get("content-type", "")).lower()
    return data[:5] == b"%PDF-" or "application/pdf" in ctype


def normalize_candidate_url(url):
    url = clean(url)

    # NCBI OA API sometimes returns FTP PDF links.
    # HTTPS access is more robust from scripts.
    if url.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return url.replace("ftp://ftp.ncbi.nlm.nih.gov", "https://ftp.ncbi.nlm.nih.gov", 1)

    # Prefer HTTPS for publisher links.
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]

    return url


def try_download_pdf(url, outpath):
    try:
        url = normalize_candidate_url(url)
        data, headers, final_url = http_get(url)
        if not is_pdf_bytes(data, headers):
            return False, f"not_pdf content_type={headers.get('Content-Type','')}", final_url

        outpath.write_bytes(data)
        return True, f"downloaded {len(data)} bytes", final_url

    except Exception as e:
        return False, f"{type(e).__name__}: {e}", url


def pubmed_metadata(pmid, email, tool=DEFAULT_NCBI_TOOL, api_key=""):
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "tool": tool or DEFAULT_NCBI_TOOL,
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(params)
    data, _, _ = http_get(url)

    root = ET.fromstring(data)

    article = root.find("./PubmedArticle")
    if article is None:
        article = root.find(".//PubmedArticle")

    title = ""
    title_el = article.find("./MedlineCitation/Article/ArticleTitle") if article is not None else None
    if title_el is not None:
        title = "".join(title_el.itertext()).strip()

    doi = ""
    pmcid = ""

    # IMPORTANT:
    # Only use the main article's PubmedData/ArticleIdList.
    # Do NOT search all .//ArticleId because references also contain ArticleId tags.
    id_list = article.find("./PubmedData/ArticleIdList") if article is not None else None
    if id_list is not None:
        for aid in id_list.findall("./ArticleId"):
            id_type = (aid.attrib.get("IdType") or "").lower()
            val = clean(aid.text)
            if id_type == "doi" and val:
                doi = val
            elif id_type in {"pmc", "pmcid"} and val:
                pmcid = val if val.startswith("PMC") else f"PMC{val}"

    return {"pmid": pmid, "title": title, "doi": doi, "pmcid": pmcid}


def europepmc_pdf_urls(pmid, email):
    query = f"EXT_ID:{pmid} AND SRC:MED"
    params = {
        "query": query,
        "format": "json",
        "pageSize": "1",
        "email": email,
    }
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params)
    urls = []

    try:
        data, _, _ = http_get(url)
        js = json.loads(data.decode("utf-8", errors="ignore"))
        results = js.get("resultList", {}).get("result", [])
        if not results:
            return urls

        ft_list = results[0].get("fullTextUrlList", {}).get("fullTextUrl", [])
        for ft in ft_list:
            u = clean(ft.get("url", ""))
            style = clean(ft.get("documentStyle", "")).lower()
            availability = clean(ft.get("availabilityCode", ""))
            if not u:
                continue
            if style == "pdf" or ".pdf" in u.lower():
                urls.append(("europepmc", u, f"availability={availability}; style={style}"))

    except Exception as e:
        urls.append(("europepmc_error", "", f"{type(e).__name__}: {e}"))

    return urls


def pmc_heuristic_urls(pmcid):
    if not pmcid:
        return []

    return [
        ("pmc_pdf", f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/", "PMC heuristic PDF URL"),
        ("ncbi_pmc_pdf", f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/", "NCBI PMC heuristic PDF URL"),
    ]

def europepmc_render_urls(pmcid):
    """
    Europe PMC often renders OA PDFs even when the raw PMC /pdf/ endpoint
    does not return PDF bytes cleanly.
    """
    if not pmcid:
        return []

    return [
        ("europepmc_render", f"https://europepmc.org/articles/{pmcid}?pdf=render", "Europe PMC PDF render"),
    ]


def pmc_oa_api_pdf_urls(pmcid):
    """
    Query NCBI PMC OA API for file links. This is safer than guessing /pdf/.
    """
    urls = []
    if not pmcid:
        return urls

    api = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=" + pmcid

    try:
        data, _, _ = http_get(api)
        root = ET.fromstring(data)

        for link in root.findall(".//link"):
            href = clean(link.attrib.get("href", ""))
            fmt = clean(link.attrib.get("format", "")).lower()

            if href and (fmt == "pdf" or href.lower().endswith(".pdf") or ".pdf" in href.lower()):
                urls.append(("pmc_oa_api", href, f"PMC OA API format={fmt}"))

    except Exception as e:
        urls.append(("pmc_oa_api_error", "", f"{type(e).__name__}: {e}"))

    return urls




def unpaywall_pdf_urls(doi, email):
    urls = []
    if not doi or not email:
        return urls

    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.unpaywall.org/v2/{encoded}?" + urllib.parse.urlencode({"email": email})

    try:
        data, _, _ = http_get(url)
        js = json.loads(data.decode("utf-8", errors="ignore"))

        best = js.get("best_oa_location") or {}
        u = clean(best.get("url_for_pdf", ""))
        if u:
            urls.append(("unpaywall_best", u, "best_oa_location.url_for_pdf"))

        for loc in js.get("oa_locations", []) or []:
            u = clean(loc.get("url_for_pdf", ""))
            if u:
                urls.append(("unpaywall", u, clean(loc.get("host_type", ""))))

    except Exception as e:
        urls.append(("unpaywall_error", "", f"{type(e).__name__}: {e}"))

    return urls


def openalex_pdf_urls(doi, email):
    urls = []
    if not doi:
        return urls

    doi_url = "https://doi.org/" + doi
    work_id = urllib.parse.quote(doi_url, safe=":/")
    url = f"https://api.openalex.org/works/{work_id}"
    if email:
        url += "?" + urllib.parse.urlencode({"mailto": email})

    try:
        data, _, _ = http_get(url)
        js = json.loads(data.decode("utf-8", errors="ignore"))

        for loc in js.get("locations", []) or []:
            pdf = clean(loc.get("pdf_url", ""))
            if pdf:
                urls.append(("openalex", pdf, "locations.pdf_url"))

        primary = js.get("primary_location") or {}
        pdf = clean(primary.get("pdf_url", ""))
        if pdf:
            urls.insert(0, ("openalex_primary", pdf, "primary_location.pdf_url"))

    except Exception as e:
        urls.append(("openalex_error", "", f"{type(e).__name__}: {e}"))

    return urls



def publisher_pdf_urls(doi, pmid=""):
    """
    Publisher-specific open PDF routes.
    Keep these conservative and transparent.
    """
    urls = []
    doi = clean(doi)

    if not doi:
        return urls

    doi_l = doi.lower()

    # ASM / mSphere / mBio-style DOI PDF routes.
    if doi_l.startswith("10.1128/"):
        urls.append((
            "publisher_asm_pdf",
            f"https://journals.asm.org/doi/pdf/{doi}",
            "ASM DOI PDF route",
        ))
        urls.append((
            "publisher_asm_epdf",
            f"https://journals.asm.org/doi/epdf/{doi}",
            "ASM DOI ePDF route",
        ))

    # PeerJ.
    if doi_l.startswith("10.7717/peerj."):
        article_id = doi_l.split("10.7717/peerj.", 1)[1]
        urls.append((
            "publisher_peerj_pdf",
            f"https://peerj.com/articles/{article_id}.pdf",
            "PeerJ article PDF route",
        ))

    # Science.
    if doi_l.startswith("10.1126/"):
        urls.append((
            "publisher_science_pdf",
            f"https://www.science.org/doi/pdf/{doi}",
            "Science DOI PDF route",
        ))

    # bioRxiv / medRxiv preprints.
    if doi_l.startswith("10.1101/"):
        urls.append((
            "publisher_biorxiv_pdf",
            f"https://www.biorxiv.org/content/{doi}v1.full.pdf",
            "bioRxiv DOI v1 PDF route",
        ))

    # Wellcome Open Research / F1000 platform.
    # Some DOI metadata/API routes do not expose url_for_pdf cleanly.
    # Add known PMID-specific route when PubMed metadata identifies the paper.
    if pmid == "30320226" or doi_l == "10.12688/wellcomeopenres.14645.4":
        urls.append((
            "publisher_wellcome_pdf",
            "https://wellcomeopenresearch.org/articles/3-70/v4/pdf",
            "Wellcome Open Research PDF route",
        ))

    return urls


def read_pmids(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pmid = clean(row.get("PMID", ""))
            if pmid:
                rows.append(row)
    return rows


def unique_candidates(cands):
    seen = set()
    out = []
    for source, url, note in cands:
        url = clean(url)
        if not url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((source, url, note))
    return out


def resolve_email(cli_email):
    email = clean(cli_email) or clean(os.getenv("NCBI_EMAIL")) or clean(os.getenv("ENTREZ_EMAIL"))
    if not email:
        raise SystemExit("Provide --email or set NCBI_EMAIL in .env/shell.")
    return email


def resolve_pmids_file(cli_path):
    if clean(cli_path):
        path = Path(cli_path)
        return path if path.is_absolute() else ROOT / path

    for path in PMID_MANIFEST_CANDIDATES:
        if path.exists():
            return path

    raise SystemExit(
        "No PMID download manifest found. Provide --pmids-file or run the appropriate paper-download preparation step."
    )


def output_paths_for_manifest(pmids_file):
    pmids_file = Path(pmids_file).resolve()
    if pmids_file == CHIP_PMID_MANIFEST.resolve():
        return (
            CHIP_PAPER_DIR / "chip_pdf_download_status.tsv",
            CHIP_PAPER_DIR / "chip_pmids_still_needing_manual_pdf_download.tsv",
        )
    return (
        OUT / "pdf_download_status.tsv",
        OUT / "pmids_still_needing_manual_pdf_download.tsv",
    )


def main():
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--pmids-file", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--tool", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    email = resolve_email(args.email)
    ncbi_tool = clean(args.tool) or clean(os.getenv("NCBI_TOOL")) or DEFAULT_NCBI_TOOL
    ncbi_api_key = clean(os.getenv("NCBI_API_KEY"))
    pmids_file = resolve_pmids_file(args.pmids_file)
    status_file, remaining_file = output_paths_for_manifest(pmids_file)
    print(f"Using PMID manifest: {pmids_file}")
    print(f"Download status output: {status_file}")
    print(f"Manual-needed output: {remaining_file}")

    pmid_rows = read_pmids(pmids_file)
    if args.limit and args.limit > 0:
        pmid_rows = pmid_rows[: args.limit]

    status_rows = []

    for i, row in enumerate(pmid_rows, start=1):
        pmid = clean(row.get("PMID"))
        print(f"\n[{i}/{len(pmid_rows)}] PMID {pmid}")

        already = existing_pdf(pmid)
        if already and not args.overwrite:
            print(f"  already_exists: {already}")
            status_rows.append({
                "PMID": pmid,
                "status": "already_exists",
                "pdf_path": str(already),
                "source": "",
                "doi": "",
                "pmcid": "",
                "title": "",
                "message": "",
            })
            continue

        try:
            meta = pubmed_metadata(pmid, email, tool=ncbi_tool, api_key=ncbi_api_key)
        except Exception as e:
            msg = f"pubmed_metadata_failed: {type(e).__name__}: {e}"
            print(f"  {msg}")
            status_rows.append({
                "PMID": pmid,
                "status": "error",
                "pdf_path": "",
                "source": "",
                "doi": "",
                "pmcid": "",
                "title": "",
                "message": msg,
            })
            time.sleep(args.sleep)
            continue

        title_stub = sanitize_filename(meta.get("title", ""))[:70]
        out_pdf = PAPERS / f"{pmid}_{title_stub}.pdf"

        candidates = []
        candidates.extend(europepmc_pdf_urls(pmid, email))
        candidates.extend(europepmc_render_urls(meta.get("pmcid", "")))
        candidates.extend(pmc_oa_api_pdf_urls(meta.get("pmcid", "")))
        candidates.extend(pmc_heuristic_urls(meta.get("pmcid", "")))
        candidates.extend(unpaywall_pdf_urls(meta.get("doi", ""), email))
        candidates.extend(openalex_pdf_urls(meta.get("doi", ""), email))
        candidates.extend(publisher_pdf_urls(meta.get("doi", ""), pmid))
        candidates = unique_candidates(candidates)

        downloaded = False
        messages = []

        print(f"  title: {meta.get('title','')[:100]}")
        print(f"  doi: {meta.get('doi','')}")
        print(f"  pmcid: {meta.get('pmcid','')}")
        print(f"  candidate urls: {len(candidates)}")

        for source, url, note in candidates:
            print(f"  trying {source}: {url[:110]}")
            ok, msg, final_url = try_download_pdf(url, out_pdf)
            messages.append(f"{source}: {msg}; final={final_url}")

            if ok:
                print(f"  downloaded: {out_pdf}")
                status_rows.append({
                    "PMID": pmid,
                    "status": f"downloaded_{source}",
                    "pdf_path": str(out_pdf),
                    "source": source,
                    "doi": meta.get("doi", ""),
                    "pmcid": meta.get("pmcid", ""),
                    "title": meta.get("title", ""),
                    "message": msg,
                })
                downloaded = True
                break

        if not downloaded:
            print("  no_open_access_pdf_found")
            status_rows.append({
                "PMID": pmid,
                "status": "no_open_access_pdf_found",
                "pdf_path": "",
                "source": "",
                "doi": meta.get("doi", ""),
                "pmcid": meta.get("pmcid", ""),
                "title": meta.get("title", ""),
                "message": " | ".join(messages)[:2000],
            })

        time.sleep(args.sleep)

    status_file.parent.mkdir(parents=True, exist_ok=True)
    remaining_file.parent.mkdir(parents=True, exist_ok=True)

    with open(status_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            delimiter="\t",
            fieldnames=["PMID", "status", "pdf_path", "source", "doi", "pmcid", "title", "message"],
        )
        writer.writeheader()
        writer.writerows(status_rows)

    remaining = [r for r in status_rows if not r["status"].startswith("downloaded") and r["status"] != "already_exists"]

    with open(remaining_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            delimiter="\t",
            fieldnames=["PMID", "status", "doi", "pmcid", "title", "message"],
        )
        writer.writeheader()
        for r in remaining:
            writer.writerow({
                "PMID": r["PMID"],
                "status": r["status"],
                "doi": r["doi"],
                "pmcid": r["pmcid"],
                "title": r["title"],
                "message": r["message"],
            })

    print("\n=== Done ===")
    print(f"Wrote: {status_file}")
    print(f"Wrote: {remaining_file}")
    print(f"Downloaded/already existed: {sum(1 for r in status_rows if r['status'].startswith('downloaded') or r['status'] == 'already_exists')}")
    print(f"Manual needed/errors: {len(remaining)}")


if __name__ == "__main__":
    main()
