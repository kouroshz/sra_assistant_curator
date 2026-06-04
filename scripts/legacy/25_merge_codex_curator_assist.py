#!/usr/bin/env python3

from pathlib import Path
import pandas as pd

OUT = Path("outputs")

def read_tsv_safe(path):
    if not path.exists():
        return pd.DataFrame([{"status": "missing", "file": str(path)}])
    try:
        return pd.read_csv(path, sep="\t", dtype=str).fillna("")
    except Exception as e:
        return pd.DataFrame([{
            "status": "read_error",
            "file": str(path),
            "error": f"{type(e).__name__}: {e}",
        }])

def read_md_lines(path):
    if not path.exists():
        return pd.DataFrame([{"markdown": f"MISSING: {path}"}])
    return pd.DataFrame({"markdown": path.read_text(errors="replace").splitlines()})

def main():
    pmids = sorted({
        p.name.split("_")[1]
        for p in OUT.glob("PMID_*_agentic_ai_group_suggestions.tsv")
    })

    rows = []
    for pmid in pmids:
        md = OUT / f"PMID_{pmid}_agentic_ai_curator_assist.md"
        tsv = OUT / f"PMID_{pmid}_agentic_ai_group_suggestions.tsv"

        rows.append({
            "PMID": pmid,
            "has_markdown": md.exists(),
            "has_group_suggestions": tsv.exists(),
            "markdown_file": str(md) if md.exists() else "",
            "group_suggestions_file": str(tsv) if tsv.exists() else "",
        })

    status = pd.DataFrame(rows)
    out_xlsx = OUT / "selected_agentic_ai_curator_assist_summary.xlsx"

    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        status.to_excel(writer, sheet_name="agentic AI_Run_Status", index=False)

        for pmid in pmids:
            md = OUT / f"PMID_{pmid}_agentic_ai_curator_assist.md"
            tsv = OUT / f"PMID_{pmid}_agentic_ai_group_suggestions.tsv"

            read_tsv_safe(tsv).to_excel(writer, sheet_name=f"{pmid}_groups"[:31], index=False)
            read_md_lines(md).to_excel(writer, sheet_name=f"{pmid}_notes"[:31], index=False)

    print(f"Wrote {out_xlsx}")
    print(status.to_string(index=False))

if __name__ == "__main__":
    main()
