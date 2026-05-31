#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------------------
# 1. Regenerate current row-level all-PMID draft table from latest outputs
# ---------------------------------------------------------------------

row_files = sorted([
    p for p in OUT.glob("PMID_*_agent_filled_master_rows_with_paper_context.tsv")
    if not any(part.startswith("archive_") for part in p.parts)
])

dfs = []
missing_or_bad = []

for f in row_files:
    try:
        pmid = f.name.split("_")[1]
        df = pd.read_csv(f, sep="\t", dtype=str).fillna("")
        df["_source_file"] = str(f)
        df["_PMID_from_filename"] = pmid
        dfs.append(df)
    except Exception as e:
        missing_or_bad.append({
            "file": str(f),
            "error": f"{type(e).__name__}: {e}",
        })

if dfs:
    big = pd.concat(dfs, ignore_index=True, sort=False).fillna("")
else:
    big = pd.DataFrame()

current_out = OUT / "all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.tsv"
big.to_csv(current_out, sep="\t", index=False)

summary = pd.DataFrame([{
    "generated_at": timestamp,
    "n_input_pmid_files": len(row_files),
    "n_rows": len(big),
    "n_columns": big.shape[1],
    "n_unique_PMID_from_filename": big["_PMID_from_filename"].nunique() if "_PMID_from_filename" in big.columns else 0,
    "output_file": str(current_out),
}])

summary_out = OUT / "all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.summary.tsv"
summary.to_csv(summary_out, sep="\t", index=False)

if missing_or_bad:
    pd.DataFrame(missing_or_bad).to_csv(
        OUT / "all_pmids_agent_filled_master_rows_with_paper_context_CURRENT.errors.tsv",
        sep="\t",
        index=False,
    )

# ---------------------------------------------------------------------
# 2. Write pre-cleanup manifest for outputs/
# ---------------------------------------------------------------------

manifest_rows = []

for p in sorted(OUT.rglob("*")):
    if p.is_file():
        rel = p.relative_to(OUT)
        manifest_rows.append({
            "path": str(rel),
            "size_bytes": p.stat().st_size,
            "modified_time": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "suffix": p.suffix,
        })

manifest = pd.DataFrame(manifest_rows)
manifest_out = OUT / "OUTPUT_MANIFEST_PRE_CLEANUP.tsv"
manifest.to_csv(manifest_out, sep="\t", index=False)

# ---------------------------------------------------------------------
# 3. Print useful summary
# ---------------------------------------------------------------------

print("\n=== Current all-PMID row-level table regenerated ===")
print(summary.to_string(index=False))

print("\n=== Output manifest written ===")
print(manifest_out)
print(f"Files in outputs/: {len(manifest)}")

print("\nTop-level outputs/ file count by suffix:")
print(manifest["suffix"].replace("", "[no_suffix]").value_counts().to_string())

print("\nLargest 20 files:")
print(
    manifest.sort_values("size_bytes", ascending=False)
    .head(20)[["path", "size_bytes"]]
    .to_string(index=False)
)
