#!/usr/bin/env python3
"""
Create a script cleanup inventory before moving legacy files.

Non-destructive:
- reads scripts/*.py
- reads workflows/steps.tsv
- classifies scripts as active workflow, production infrastructure, superseded candidate, or unmapped review
- writes docs/SCRIPT_CLEANUP_INVENTORY.tsv
- writes docs/SCRIPT_CLEANUP_PLAN.md
"""

from pathlib import Path
from datetime import datetime
import ast
import csv


WORKFLOW_STEPS = Path("workflows/steps.tsv")
OUT_TSV = Path("docs/SCRIPT_CLEANUP_INVENTORY.tsv")
OUT_MD = Path("docs/SCRIPT_CLEANUP_PLAN.md")


PRODUCTION_INFRA = {
    "scripts/00_audit_current_pipeline_for_reorg.py",
    "scripts/01_define_active_workflow_and_outputs.py",
    "scripts/02_create_clean_final_release.py",
    "scripts/03_qc_final_release.py",
    "scripts/04_pipeline_readiness_report.py",
    "scripts/05_run_all_checks.py",
    "scripts/06_script_cleanup_inventory.py",
    "scripts/07_classify_unmapped_scripts.py",
}


SUPERSEDED_KNOWN = {
    "scripts/68_build_chip_curator_excel.py": "Superseded by scripts/68e_finalize_chip_curator_excel_v5.py",
    "scripts/68b_build_chip_curator_excel_v2.py": "Superseded by scripts/68e_finalize_chip_curator_excel_v5.py",
    "scripts/68c_polish_chip_curator_excel_v3.py": "Superseded by scripts/68e_finalize_chip_curator_excel_v5.py",
    "scripts/68d_polish_chip_curator_excel_v4.py": "Superseded by scripts/68e_finalize_chip_curator_excel_v5.py",
    "scripts/72_export_chip_study_summaries_clean.py": "Superseded by scripts/72c_final_qc_chip_study_summaries.py",
    "scripts/72b_qc_and_export_chip_study_summaries_rna_style.py": "Superseded by scripts/72c_final_qc_chip_study_summaries.py",
}


def read_active_workflow_scripts():
    active = set()
    if not WORKFLOW_STEPS.exists():
        return active
    with open(WORKFLOW_STEPS, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            script = row.get("script", "").strip()
            if script:
                active.add(script)
    return active


def get_docstring(path):
    try:
        tree = ast.parse(Path(path).read_text(errors="ignore"))
        return (ast.get_docstring(tree) or "").strip().replace("\n", " ")
    except Exception:
        return ""


def classify(path, active):
    s = str(path)

    if s in active:
        return "ACTIVE_WORKFLOW", "Used by workflows/steps.tsv"

    if s in PRODUCTION_INFRA:
        return "PRODUCTION_INFRA", "Production wrapper/QC/reorg infrastructure"

    if s in SUPERSEDED_KNOWN:
        return "SUPERSEDED_CANDIDATE", SUPERSEDED_KNOWN[s]

    return "UNMAPPED_REVIEW", "Not in active workflow map; review before moving/deleting"


def main():
    active = read_active_workflow_scripts()
    rows = []

    for path in sorted(Path("scripts").glob("*.py")):
        status, note = classify(path, active)
        rows.append({
            "script": str(path),
            "status": status,
            "note": note,
            "docstring": get_docstring(path)[:300],
        })

    OUT_TSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_TSV, "w", newline="") as f:
        cols = ["script", "status", "note", "docstring"]
        writer = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    by_status = {}
    for r in rows:
        by_status.setdefault(r["status"], []).append(r)

    lines = []
    lines.append("# Script Cleanup Plan")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("This is a non-destructive cleanup inventory.")
    lines.append("")
    lines.append("Do not move active workflow scripts yet.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for status in sorted(by_status):
        lines.append(f"- {status}: {len(by_status[status])}")
    lines.append("")
    lines.append("## Cleanup policy")
    lines.append("")
    lines.append("1. Keep `ACTIVE_WORKFLOW` scripts in place until clean wrappers fully replace them.")
    lines.append("2. Keep `PRODUCTION_INFRA` scripts in place.")
    lines.append("3. Move only `SUPERSEDED_CANDIDATE` scripts first.")
    lines.append("4. Do not move `UNMAPPED_REVIEW` scripts until manually inspected.")
    lines.append("5. Run `python scripts/05_run_all_checks.py` after every move.")
    lines.append("")
    lines.append("## Scripts by category")
    lines.append("")

    for status in ["ACTIVE_WORKFLOW", "PRODUCTION_INFRA", "SUPERSEDED_CANDIDATE", "UNMAPPED_REVIEW"]:
        lines.append(f"### {status}")
        lines.append("")
        for r in by_status.get(status, []):
            lines.append(f"- `{r['script']}`")
            lines.append(f"  - {r['note']}")
            if r["docstring"]:
                lines.append(f"  - doc: {r['docstring']}")
        lines.append("")

    OUT_MD.write_text("\n".join(lines))

    print("Wrote:")
    print("  " + str(OUT_TSV))
    print("  " + str(OUT_MD))
    print("")
    for status in sorted(by_status):
        print(f"{status}: {len(by_status[status])}")


if __name__ == "__main__":
    main()
