#!/usr/bin/env python3
"""
Classify unmapped scripts before legacy cleanup.

Non-destructive:
- reads docs/SCRIPT_CLEANUP_INVENTORY.tsv
- examines scripts marked UNMAPPED_REVIEW
- checks whether they are referenced by active/production scripts
- assigns a tentative review category
- writes docs/UNMAPPED_SCRIPT_REVIEW.tsv
- writes docs/UNMAPPED_SCRIPT_REVIEW.md

No files are moved.
No APIs are called.
"""

from pathlib import Path
from datetime import datetime
import ast
import csv


INVENTORY = Path("docs/SCRIPT_CLEANUP_INVENTORY.tsv")
OUT_TSV = Path("docs/UNMAPPED_SCRIPT_REVIEW.tsv")
OUT_MD = Path("docs/UNMAPPED_SCRIPT_REVIEW.md")

SEARCH_DIRS = [
    Path("scripts"),
    Path("workflows"),
    Path("src"),
    Path("tests"),
    Path("docs"),
]

# Generated reports should not count as meaningful references.
REFERENCE_IGNORE_FILES = {
    "docs/SCRIPT_CLEANUP_INVENTORY.tsv",
    "docs/SCRIPT_CLEANUP_PLAN.md",
    "docs/UNMAPPED_SCRIPT_REVIEW.tsv",
    "docs/UNMAPPED_SCRIPT_REVIEW.md",
}

# These are legacy docs/legacy drivers. They are useful historical references,
# but they should not by themselves prevent archiving a script.
WEAK_REFERENCE_FILES = {
    "docs/LEGACY_README_BEFORE_PRODUCTION_REORG.md",
    "docs/PIPELINE_OVERVIEW.md",
    "docs/QUICKSTART.md",
    "docs/WORKFLOW.md",
    "scripts/README.md",
    "scripts/run_curator_pipeline.py",
}


SCRATCH_HINTS = [
    "debug",
    "tmp",
    "temp",
    "scratch",
    "sandbox",
    "adhoc",
    "quick",
    "test_",
    "probe",
    "inspect",
    "explore",
]

HISTORICAL_HINTS = [
    "old",
    "backup",
    "archive",
    "draft",
    "pilot",
    "v1",
    "v2",
    "v3",
    "prototype",
]

PAPER_OR_PDF_HINTS = [
    "pdf",
    "paper",
    "pmid",
    "publication",
    "pubmed",
    "open_access",
]

AI_HINTS = [
    "ai",
    "agentic",
    "openai",
    "prompt",
]

QC_HINTS = [
    "qc",
    "validate",
    "validation",
    "check",
    "audit",
    "inventory",
]


def read_inventory():
    with open(INVENTORY, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def get_docstring(path):
    try:
        tree = ast.parse(Path(path).read_text(errors="ignore"))
        return (ast.get_docstring(tree) or "").strip().replace("\n", " ")
    except Exception:
        return ""


def read_text(path):
    try:
        return Path(path).read_text(errors="ignore")
    except Exception:
        return ""


def count_references(script_path):
    target = str(script_path)
    basename = Path(script_path).name
    strong_refs = []
    weak_refs = []

    for d in SEARCH_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            if p == Path(script_path):
                continue
            if p.suffix not in {".py", ".md", ".tsv", ".yaml", ".yml", ".txt"}:
                continue

            p_str = str(p)
            if p_str in REFERENCE_IGNORE_FILES:
                continue

            text = read_text(p)
            if target in text or basename in text:
                if p_str in WEAK_REFERENCE_FILES:
                    weak_refs.append(p_str)
                else:
                    strong_refs.append(p_str)

    return sorted(set(strong_refs)), sorted(set(weak_refs))


def has_any(text, hints):
    low = text.lower()
    return any(h.lower() in low for h in hints)


def classify(script, doc, strong_refs, weak_refs):
    name = Path(script).name.lower()
    combined = (name + " " + doc).lower()

    if strong_refs:
        return "KEEP_REVIEW_STRONG_CODE_REFERENCE", "Referenced by non-legacy tracked files; do not move without manual inspection."

    if has_any(combined, SCRATCH_HINTS):
        return "SCRATCH_OR_INSPECTION_CANDIDATE", "Looks like scratch/inspection/debug/exploratory code; candidate for archive after review."

    if has_any(combined, HISTORICAL_HINTS):
        return "HISTORICAL_ARCHIVE_CANDIDATE", "Looks historical/prototype/pilot/versioned; candidate for archive after review."

    if has_any(combined, QC_HINTS):
        return "POSSIBLE_QC_UTILITY_REVIEW", "Looks like QC/validation/inventory logic; inspect before moving."

    if has_any(combined, PAPER_OR_PDF_HINTS):
        return "POSSIBLE_PAPER_PUBLICATION_UTILITY_REVIEW", "Looks related to paper/PDF/PMID/publication logic; inspect before moving."

    if has_any(combined, AI_HINTS):
        return "POSSIBLE_AI_UTILITY_REVIEW", "Looks AI/prompt-related; inspect before moving."

    return "MANUAL_REVIEW", "No clear classification; inspect manually."


def main():
    rows = read_inventory()
    unmapped = [r for r in rows if r.get("status") == "UNMAPPED_REVIEW"]

    out_rows = []

    for r in unmapped:
        script = r["script"]
        doc = get_docstring(script)
        strong_refs, weak_refs = count_references(script)
        category, recommendation = classify(script, doc, strong_refs, weak_refs)

        out_rows.append({
            "script": script,
            "category": category,
            "recommendation": recommendation,
            "n_strong_references": len(strong_refs),
            "strong_references": " | ".join(strong_refs[:20]),
            "n_weak_references": len(weak_refs),
            "weak_references": " | ".join(weak_refs[:20]),
            "docstring": doc[:500],
        })

    OUT_TSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TSV, "w", newline="") as f:
        cols = ["script", "category", "recommendation", "n_strong_references", "strong_references", "n_weak_references", "weak_references", "docstring"]
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    by_cat = {}
    for r in out_rows:
        by_cat.setdefault(r["category"], []).append(r)

    lines = []
    lines.append("# Unmapped Script Review")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("This is a non-destructive classification of scripts not currently in `workflows/steps.tsv` and not production infrastructure.")
    lines.append("")
    lines.append("Do not move these automatically. Use this report to decide what should be archived next.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for cat in sorted(by_cat):
        lines.append(f"- {cat}: {len(by_cat[cat])}")
    lines.append("")
    lines.append("## Categories")
    lines.append("")
    lines.append("- KEEP_REVIEW_STRONG_CODE_REFERENCE: referenced by non-legacy tracked files; do not move without inspection.")
    lines.append("- SCRATCH_OR_INSPECTION_CANDIDATE: likely exploratory/inspection/debug; candidate for archive.")
    lines.append("- HISTORICAL_ARCHIVE_CANDIDATE: likely old prototype/pilot/versioned script; candidate for archive.")
    lines.append("- POSSIBLE_QC_UTILITY_REVIEW: may contain reusable validation/QC logic.")
    lines.append("- POSSIBLE_PAPER_PUBLICATION_UTILITY_REVIEW: may contain paper/PMID/PDF logic.")
    lines.append("- POSSIBLE_AI_UTILITY_REVIEW: may contain AI prompt/run logic.")
    lines.append("- MANUAL_REVIEW: unclear.")
    lines.append("")

    for cat in sorted(by_cat):
        lines.append(f"## {cat}")
        lines.append("")
        for r in by_cat[cat]:
            lines.append(f"- `{r['script']}`")
            lines.append(f"  - recommendation: {r['recommendation']}")
            lines.append(f"  - strong references: {r['n_strong_references']}")
            if r["strong_references"]:
                lines.append(f"  - strongly referenced by: {r['strong_references']}")
            lines.append(f"  - weak legacy/doc references: {r['n_weak_references']}")
            if r["weak_references"]:
                lines.append(f"  - weakly referenced by: {r['weak_references']}")
            if r["docstring"]:
                lines.append(f"  - doc: {r['docstring']}")
        lines.append("")

    OUT_MD.write_text("\n".join(lines))

    print("Wrote:")
    print("  " + str(OUT_TSV))
    print("  " + str(OUT_MD))
    print("")
    for cat in sorted(by_cat):
        print(f"{cat}: {len(by_cat[cat])}")


if __name__ == "__main__":
    main()
