#!/usr/bin/env python3

from pathlib import Path
import pandas as pd
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PAPERS = ROOT / "papers"
OUT = ROOT / "outputs"

MASTER = DATA / "rna_seq_metadata_v1_2026-05-05.xlsx"


def clean(x):
    if pd.isna(x):
        return ""
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    if x.lower() in {"nan", "none", "na", "n/a"}:
        return ""
    return x


def find_paper(pmid):
    pdfs = list(PAPERS.glob(f"*{pmid}*.pdf"))
    return ";".join(str(p.name) for p in pdfs)


df = pd.read_excel(MASTER, sheet_name="Sheet", dtype=str).fillna("")
df.columns = [str(c).strip() for c in df.columns]

df["PMID_norm"] = df["PMID"].map(clean)
df = df[df["PMID_norm"] != ""].copy()

rows = []

for pmid, sub in df.groupby("PMID_norm"):
    rows.append({
        "PMID": pmid,
        "n_rows": sub.shape[0],
        "n_runs": sub["Run"].map(clean).nunique() if "Run" in sub.columns else "",
        "BioProjects": ";".join(sorted(set(sub["BioProject"].map(clean)))) if "BioProject" in sub.columns else "",
        "LibraryStrategies": ";".join(sorted(set(sub["LibraryStrategy"].map(clean)))) if "LibraryStrategy" in sub.columns else "",
        "local_pdf": find_paper(pmid),
    })

out = pd.DataFrame(rows).sort_values("n_rows", ascending=False)

out_file = OUT / "pmid_candidates.tsv"
out.to_csv(out_file, sep="\t", index=False)

print(out.head(30).to_string(index=False))
print(f"\nWrote {out_file}")
