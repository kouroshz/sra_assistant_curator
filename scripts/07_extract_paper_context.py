#!/usr/bin/env python3

from pathlib import Path
import argparse
import json
import re
import pandas as pd
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "papers"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


KEYWORDS = {
    "baseline": [r"\bbaseline\b", r"\bBL\b"],
    "suspended": [r"\bsuspended\b", r"\bsuspension\b", r"\bmoving suspension\b", r"\bSP\b"],
    "static": [r"\bstatic\b", r"\bST\b"],
    "schizont": [r"\bschizont\b", r"\bschizonts\b"],
    "rnaseq": [r"\bRNA-seq\b", r"\bRNAseq\b", r"\bwhole transcriptome\b", r"\btranscriptome sequencing\b"],
    "chipseq": [r"\bChIP-seq\b"],
    "atacseq": [r"\bATAC-seq\b"],
    "proteomics": [r"\bproteomics\b", r"\bLC-MS/MS\b", r"\bmass spectrometry\b"],
    "metabolomics": [r"\bmetabolomics\b"],
}


def clean(x):
    return re.sub(r"\s+", " ", str(x).strip())


def find_pdf(pmid):
    hits = sorted(PAPERS.glob(f"*{pmid}*.pdf"))
    if not hits:
        raise FileNotFoundError(f"No local PDF found in {PAPERS} with PMID {pmid} in filename.")
    if len(hits) > 1:
        print("Multiple PDFs found; using first:")
        for h in hits:
            print(f"  {h}")
    return hits[0]


def extract_pages(pdf):
    reader = PdfReader(str(pdf))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            txt = f"[EXTRACTION_ERROR: {e}]"
        pages.append({"page": i, "text": txt})
    return pages


def split_sentences(text):
    text = clean(text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 30]


def collect_evidence(pages):
    rows = []
    for p in pages:
        for sent in split_sentences(p["text"]):
            for key, patterns in KEYWORDS.items():
                for pat in patterns:
                    if re.search(pat, sent, flags=re.I):
                        rows.append({
                            "keyword_group": key,
                            "page": p["page"],
                            "matched_pattern": pat,
                            "evidence_text": sent[:900],
                        })
                        break
    return pd.DataFrame(rows).drop_duplicates() if rows else pd.DataFrame()


def guess_title(pages):
    if not pages:
        return ""
    lines = [x.strip() for x in pages[0]["text"].splitlines() if x.strip()]
    candidates = []
    for line in lines[:20]:
        if len(line) > 25 and not line.lower().startswith(("scientific reports", "www.", "open")):
            candidates.append(line)
    return candidates[0] if candidates else ""


def make_rule_based_note(evidence):
    """
    Conservative keyword-only paper note.
    This should never over-interpret the paper. LLM/human curator refines later.
    """
    if evidence.empty:
        return "Paper context not extracted; requires curator review."

    groups = set(evidence["keyword_group"])

    # Only use this specific note for papers where this design is strongly represented.
    if make_condition_interpretation(evidence):
        return (
            "Paper appears to study schizont-stage P. falciparum cultures under baseline, "
            "static, and moving suspension conditions. Baseline/static controls for suspended "
            "cultures should be curator-confirmed."
        )

    if "rnaseq" in groups:
        return "Keyword scan detected RNA-seq/transcriptome evidence; paper context requires curator review."

    return "Paper context extracted by keyword scan; requires curator review."


def make_condition_interpretation(evidence):
    """
    Only return the Baseline/Static/Suspended interpretation when strongly detected.
    This prevents leaking the 31937828 interpretation into unrelated papers.
    """
    if evidence.empty or "keyword_group" not in evidence.columns:
        return ""

    counts = evidence["keyword_group"].value_counts().to_dict()

    baseline = counts.get("baseline", 0)
    static = counts.get("static", 0)
    suspended = counts.get("suspended", 0)
    schizont = counts.get("schizont", 0)
    rnaseq = counts.get("rnaseq", 0)

    # Require repeated evidence for the full design.
    if baseline >= 3 and static >= 3 and suspended >= 3 and (schizont >= 1 or rnaseq >= 1):
        return (
            "Baseline = baseline culture condition; Static = static control culture; "
            "Suspended = moving suspension culture. Use same-strain/stage Baseline or Static "
            "as comparator, with curator confirmation."
        )

    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    args = parser.parse_args()

    pmid = str(args.pmid)
    pdf = find_pdf(pmid)

    print(f"\n=== Extracting paper context for PMID {pmid} ===")
    print(f"PDF: {pdf}")

    pages = extract_pages(pdf)
    evidence = collect_evidence(pages)
    title = guess_title(pages)
    note = make_rule_based_note(evidence)

    omics_used = []
    if not evidence.empty:
        if "rnaseq" in set(evidence["keyword_group"]):
            omics_used.append("RNA-seq")

    omics_mentions = []
    if not evidence.empty:
        for k, label in [
            ("chipseq", "ChIP-seq"),
            ("atacseq", "ATAC-seq"),
            ("proteomics", "proteomics"),
            ("metabolomics", "metabolomics"),
        ]:
            if k in set(evidence["keyword_group"]):
                omics_mentions.append(label)

    condition_interpretation = make_condition_interpretation(evidence)

    summary = {
        "PMID": pmid,
        "pdf": str(pdf),
        "title_guess": title,
        "n_pages": len(pages),
        "paper_note": note,
        "paper_omics_used": ";".join(omics_used),
        "paper_omics_mentions": "",
        "condition_interpretation": condition_interpretation,
        "paper_keyword_omics_mentions": ";".join(omics_mentions),
        "needs_human_review": "yes",
        "review_reason": "Paper context was keyword-extracted and should be verified by curator.",
    }

    out_json = OUT / f"PMID_{pmid}_paper_context.json"
    out_evidence = OUT / f"PMID_{pmid}_paper_context_evidence.tsv"
    out_text = OUT / f"PMID_{pmid}_paper_text.txt"

    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    evidence.to_csv(out_evidence, sep="\t", index=False)

    full_text = "\n\n".join([f"--- PAGE {p['page']} ---\n{p['text']}" for p in pages])
    out_text.write_text(full_text, encoding="utf-8")

    print("\nSummary:")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print("\nEvidence counts:")
    if evidence.empty:
        print("No evidence found.")
    else:
        print(evidence["keyword_group"].value_counts().to_string())

    print("\nWrote:")
    print(out_json)
    print(out_evidence)
    print(out_text)


if __name__ == "__main__":
    main()
