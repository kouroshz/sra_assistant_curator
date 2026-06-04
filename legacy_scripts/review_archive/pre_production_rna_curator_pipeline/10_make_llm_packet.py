#!/usr/bin/env python3

from pathlib import Path
import argparse
import json
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def find_rows_file(pmid):
    with_paper = OUT / f"PMID_{pmid}_agent_filled_master_rows_with_paper_context.tsv"
    base = OUT / f"PMID_{pmid}_agent_filled_master_rows.tsv"

    if with_paper.exists():
        return with_paper
    if base.exists():
        return base

    raise FileNotFoundError(f"No filled rows TSV found for PMID {pmid}")


def read_paper_text(pmid):
    f = OUT / f"PMID_{pmid}_paper_text.txt"
    if not f.exists():
        raise FileNotFoundError(
            f"Missing {f}. Run scripts/07_extract_paper_context.py first."
        )
    return f.read_text(encoding="utf-8", errors="ignore")


def parse_pages(text):
    chunks = re.split(r"--- PAGE\s+(\d+)\s+---", text)
    pages = []

    if len(chunks) < 3:
        return [{"page": "", "text": text}]

    for i in range(1, len(chunks), 2):
        page = chunks[i]
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        pages.append({"page": page, "text": body})

    return pages


def split_sentences(text):
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]


def collect_terms(df):
    term_cols = [
        "Cell_Cycle_Stage",
        "Life_Stage",
        "Target",
        "Strain",
        "Substrain",
        "Mutant",
        "Condition1",
        "Condition2",
        "Condition3",
        "background_or_control_1",
        "background_or_control_2",
    ]

    terms = set()

    for col in term_cols:
        if col not in df.columns:
            continue
        for val in df[col].map(clean).unique():
            if not val:
                continue
            for part in re.split(r"[;/,|]", val):
                part = clean(part)
                if len(part) >= 2:
                    terms.add(part)

    # generic curator keywords
    terms.update([
        "RNA-seq", "RNAseq", "transcriptome", "sequencing",
        "overall design", "replicate", "control", "treated",
        "treatment", "condition", "static", "baseline",
        "suspended", "knockdown", "mutant", "overexpression",
        "wild type", "temperature", "heat", "fever",
        "GEO", "SRA", "BioSample",
    ])

    return sorted(terms, key=lambda x: (-len(x), x.lower()))


def collect_paper_snippets(pages, terms, max_snippets=80):
    rows = []
    seen = set()

    lower_terms = [(t, t.lower()) for t in terms]

    for page in pages:
        for sent in split_sentences(page["text"]):
            sl = sent.lower()
            matched = []

            for original, tl in lower_terms:
                if tl and tl in sl:
                    matched.append(original)
                    if len(matched) >= 4:
                        break

            if not matched:
                continue

            key = sent[:250]
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "page": page["page"],
                "matched_terms": "; ".join(matched),
                "text": sent[:1200],
            })

            if len(rows) >= max_snippets:
                return rows

    return rows


def make_group_summary(df):
    group_cols = [
        c for c in [
            "Strain",
            "Cell_Cycle_Stage",
            "Target",
            "Mutant",
            "Condition1",
            "background_or_control_1",
            "needs_human_review",
            "review_priority",
            "review_reason",
        ]
        if c in df.columns
    ]

    if not group_cols:
        return []

    g = (
        df.groupby(group_cols, dropna=False)
        .agg(
            n_runs=("Run", "count"),
            runs=("Run", lambda x: ";".join(map(str, x))),
            biosamples=("BioSample", lambda x: ";".join(sorted(set(map(str, x)))) if "BioSample" in df.columns else ""),
            samples=("SampleName", lambda x: ";".join(sorted(set(map(str, x)))) if "SampleName" in df.columns else ""),
        )
        .reset_index()
    )

    return g.fillna("").astype(str).to_dict(orient="records")


def compact_rows(df, review_only=False):
    keep = [
        "Run", "BioSample", "SampleName", "BioProject", "LibraryStrategy",
        "Cell_Cycle_Stage", "Life_Stage", "Target", "Strain", "Substrain",
        "Mutant", "Condition1", "Condition2", "Condition3",
        "experimental_factor", "control_role", "curator_condition_note",
        "replicate_number",
        "technical_run_count", "technical_run_group",
        "assigned_control1", "assigned_control_biosample1", "assigned_control_sample1",
        "assigned_control2", "assigned_control_biosample2", "assigned_control_sample2",
        "background_or_control_1", "background_or_control_2",
        "sra_row_omics", "paper_other_assays",
        "Notes", "curation_source", "curation_confidence",
        "curation_note", "curation_evidence",
        "needs_human_review", "review_priority", "review_reason",
    ]

    keep = [c for c in keep if c in df.columns]
    d = df.copy()

    if review_only and "needs_human_review" in d.columns:
        d = d[d["needs_human_review"].map(clean) == "yes"].copy()

    return d[keep].fillna("").astype(str).to_dict(orient="records")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmid", required=True)
    parser.add_argument("--max-snippets", type=int, default=80)
    parser.add_argument("--include-all-rows", action="store_true")
    args = parser.parse_args()

    pmid = clean(args.pmid)

    rows_file = find_rows_file(pmid)
    df = pd.read_csv(rows_file, sep="\t", dtype=str).fillna("")

    paper_text = read_paper_text(pmid)
    pages = parse_pages(paper_text)

    terms = collect_terms(df)
    snippets = collect_paper_snippets(pages, terms, max_snippets=args.max_snippets)

    # Include beginning of paper as abstract-ish context.
    first_pages = "\n".join([p["text"] for p in pages[:2]])[:6000]

    packet = {
        "pmid": pmid,
        "rows_file": str(rows_file),
        "n_rows": int(df.shape[0]),
        "n_rows_needing_review": int((df.get("needs_human_review", "") == "yes").sum()) if "needs_human_review" in df.columns else None,
        "paper_beginning": first_pages,
        "paper_snippets": snippets,
        "deterministic_group_summary": make_group_summary(df),
        "review_rows": compact_rows(df, review_only=True),
        "all_rows": compact_rows(df, review_only=False) if args.include_all_rows else [],
        "task_instruction": (
            "Use BioSample/SRA metadata as primary row identity. Use paper snippets to confirm experimental design, "
            "controls, ambiguous conditions, experimental_factor/control_role interpretation, omics types, technical run structure, and curator notes. "
            "Distinguish SRA-row omics from other paper-level assays. Do not invent new rows."
        ),
    }

    out = OUT / f"PMID_{pmid}_llm_packet.json"
    out.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    print(f"\n=== LLM packet created for PMID {pmid} ===")
    print(f"Rows: {df.shape[0]}")
    print(f"Rows needing review: {packet['n_rows_needing_review']}")
    print(f"Paper snippets: {len(snippets)}")
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
