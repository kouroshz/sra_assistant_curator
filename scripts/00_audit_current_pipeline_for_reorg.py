#!/usr/bin/env python3
"""
Audit current SRA curator pipeline before production reorganization.

This script is non-destructive.
It does not call APIs.
It does not modify existing outputs except writing audit reports.

Outputs:
  outputs/00_REORG_AUDIT/current_pipeline_script_inventory.tsv
  outputs/00_REORG_AUDIT/output_folder_inventory.tsv
  outputs/00_REORG_AUDIT/final_output_candidates.tsv
  outputs/00_REORG_AUDIT/CURRENT_PIPELINE_REORG_AUDIT.md
"""

from pathlib import Path
from datetime import datetime
import ast
import csv
import os
import re
import subprocess


OUT = Path("outputs/00_REORG_AUDIT")
OUT.mkdir(parents=True, exist_ok=True)

SCRIPT_DIRS = [Path("scripts"), Path("workflows")]
OUTPUT_DIRS = [Path("outputs"), Path("results")]
DOC_DIRS = [Path("docs")]

API_PATTERNS = [
    "OPENAI_API_KEY", "openai", "client.chat", "responses.create",
    "anthropic", "api_key", "--execute", "--execute-ai"
]

NCBI_PATTERNS = [
    "Entrez", "Bio.Entrez", "esearch", "efetch", "elink",
    "sra", "runinfo", "pubmed", "pmid"
]

PDF_PATTERNS = [
    ".pdf", "pdf", "pymupdf", "fitz", "download", "papers"
]

EXCEL_PATTERNS = [
    "ExcelWriter", "openpyxl", ".xlsx", "to_excel", "read_excel"
]

VALIDATION_PATTERNS = [
    "validate", "validation", "n_fail", "n_warn", "source_row_id",
    "duplicate", "missing", "coverage", "PASS", "FAIL"
]

CHIP_PATTERNS = [
    "chip", "target_ip", "input", "IgG", "background",
    "control", "peak", "sample_map", "target_control"
]

RNA_PATTERNS = [
    "rna", "condition", "stage", "study_summary", "semantic_red_flag"
]

PACKAGING_PATTERNS = [
    "bundle", "zip", "curator", "share", "handoff", "final"
]


def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
    except Exception as e:
        return f"ERROR: {e}"


def file_size_human(path):
    n = path.stat().st_size
    for unit in ["B", "K", "M", "G"]:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}T"


def dir_size_bytes(path):
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def size_human(n):
    for unit in ["B", "K", "M", "G", "T"]:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}P"


def contains_any(text, patterns):
    low = text.lower()
    return any(p.lower() in low for p in patterns)


def count_any(text, patterns):
    low = text.lower()
    return sum(low.count(p.lower()) for p in patterns)


def get_docstring_and_imports(path):
    try:
        text = path.read_text(errors="ignore")
        tree = ast.parse(text)
        doc = ast.get_docstring(tree) or ""
        imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                imports.append(mod)
        return doc.strip().replace("\n", " ")[:500], ";".join(sorted(set(imports))[:30])
    except Exception:
        return "", ""


def infer_script_group(name, text):
    n = name.lower()
    t = text.lower()

    if "inspect" in n:
        return "00_inspection"
    if "fetch" in n or "entrez" in t or "resolve" in n or "publication" in n or "pmid" in t:
        return "02_publication_resolution"
    if "pdf" in n or "download" in n or "paper_availability" in n:
        return "03_paper_preparation"
    if "packet" in n and "validate" not in n:
        return "04_packet_construction"
    if "run_agentic_ai" in n or "batch_run" in n or "ai" in n and "validate" not in n and "inventory" not in n:
        return "05_ai_execution_or_prompting"
    if "validate" in n or "qc" in n or "repair" in n or "patch" in n or "rebuild" in n:
        return "06_validation_repair_qc"
    if "finalize" in n or "excel" in n or "summary" in n or "curator" in n:
        return "07_finalization_export"
    if "package" in n or "bundle" in n or "handoff" in n:
        return "08_packaging_handoff"
    if "inventory" in n or "audit" in n:
        return "09_inventory_audit"
    return "99_uncategorized"


def infer_status(name):
    n = name.lower()

    superseded_markers = [
        "68_build_chip_curator_excel.py",
        "68b_build_chip_curator_excel_v2.py",
        "68c_polish_chip_curator_excel_v3.py",
        "68d_polish_chip_curator_excel_v4.py",
        "72_export_chip_study_summaries_clean.py",
        "72b_qc_and_export_chip_study_summaries_rna_style.py",
    ]

    if any(m in n for m in superseded_markers):
        return "SUPERSEDED_BY_LATER_SCRIPT"

    active_markers = [
        "50_inspect_chip_master.py",
        "51_build_chip_rowwise_evidence_and_inventory.py",
        "52_make_chip_ai_queue_and_control_policy.py",
        "53a_fetch_chip_sra_runinfo_publication_signals.py",
        "53b_resolve_chip_publications_via_entrez_links.py",
        "54_curate_chip_publication_backfills.py",
        "55_make_chip_resolved_publication_queue.py",
        "56_prepare_chip_pdf_download_manifest.py",
        "57_build_chip_paper_availability_and_ai_readiness.py",
        "58_make_chip_ai_packets_from_ready_queue.py",
        "59_preflight_qc_chip_ai_packets.py",
        "59b_patch_chip_packet_control_roles.py",
        "60_validate_chip_ai_output.py",
        "60b_rebuild_chip_sample_map_from_rowwise.py",
        "61_inventory_chip_ai_outputs.py",
        "62_batch_run_chip_small_packets_production.py",
        "63_prepare_chip_chunked_packet.py",
        "64_merge_chip_chunk_outputs.py",
        "65_audit_chip_repeats_and_chunk_failures.py",
        "66_patch_chip_rowwise_roles_from_prelim.py",
        "67_finalize_chip_ai_phase.py",
        "68e_finalize_chip_curator_excel_v5.py",
        "69_postdoc_handoff_inventory.py",
        "70_package_curator_share_bundle.py",
        "71_export_chip_curator_companion_files.py",
        "72c_final_qc_chip_study_summaries.py",
    ]

    if any(m in n for m in active_markers):
        return "ACTIVE_CURRENT_WORKFLOW"

    if re.match(r".*/(4[0-9]|3[0-9])_", n):
        return "RNA_OR_SHARED_CURRENT_OR_LEGACY_REVIEW"

    return "UNKNOWN_REVIEW"


def audit_scripts():
    rows = []
    for d in SCRIPT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.py")):
            text = p.read_text(errors="ignore")
            doc, imports = get_docstring_and_imports(p)
            rows.append({
                "script": str(p),
                "file": p.name,
                "group_guess": infer_script_group(p.name, text),
                "status_guess": infer_status(str(p)),
                "size": file_size_human(p),
                "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                "has_argparse": "argparse" in text,
                "uses_openai_or_api": contains_any(text, API_PATTERNS),
                "api_pattern_count": count_any(text, API_PATTERNS),
                "uses_ncbi_or_pubmed": contains_any(text, NCBI_PATTERNS),
                "uses_pdf_or_papers": contains_any(text, PDF_PATTERNS),
                "uses_excel": contains_any(text, EXCEL_PATTERNS),
                "validation_or_qc": contains_any(text, VALIDATION_PATTERNS),
                "chip_specific": contains_any(text, CHIP_PATTERNS),
                "rna_specific": contains_any(text, RNA_PATTERNS),
                "packaging_or_handoff": contains_any(text, PACKAGING_PATTERNS),
                "docstring": doc,
                "imports": imports,
            })
    return rows


def audit_output_folders():
    rows = []
    for base in OUTPUT_DIRS:
        if not base.exists():
            continue
        for p in sorted(base.iterdir()):
            if p.is_dir():
                rows.append({
                    "folder": str(p),
                    "size": size_human(dir_size_bytes(p)),
                    "n_files": sum(1 for x in p.rglob("*") if x.is_file()),
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                })
    return rows


def audit_final_candidates():
    patterns = [
        "outputs/**/*.xlsx",
        "outputs/**/*.zip",
        "outputs/**/*SUMMARY*.md",
        "outputs/**/*SUMMARY*.txt",
        "outputs/**/*README*.md",
        "outputs/**/*REPORT*.md",
        "outputs/**/*curator*.tsv",
        "outputs/**/*review*.tsv",
        "outputs/**/*LATEST*.txt",
    ]
    hits = []
    seen = set()
    for pat in patterns:
        for p in Path(".").glob(pat):
            if p.is_file() and str(p) not in seen:
                seen.add(str(p))
                hits.append(p)

    rows = []
    for p in sorted(hits):
        name = p.name.lower()
        final_guess = any(k in name for k in [
            "curator", "study_summaries", "final", "bundle", "phase_completion",
            "review", "latest"
        ])
        rows.append({
            "path": str(p),
            "file": p.name,
            "size": file_size_human(p),
            "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            "final_candidate_guess": final_guess,
        })
    return rows


def write_tsv(rows, path):
    if not rows:
        path.write_text("")
        return

    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def make_md(script_rows, folder_rows, final_rows):
    lines = []
    lines.append("# Current Pipeline Reorganization Audit")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("This report is non-destructive and is intended to support production reorganization.")
    lines.append("")

    lines.append("## Git state")
    lines.append("")
    lines.append("```text")
    lines.append(run_cmd(["git", "status", "--short"]))
    lines.append("```")
    lines.append("")
    lines.append(f"- current branch: `{run_cmd(['git', 'branch', '--show-current'])}`")
    lines.append(f"- latest commit: `{run_cmd(['git', 'log', '-1', '--oneline'])}`")
    lines.append("")

    lines.append("## Script inventory summary")
    lines.append("")
    lines.append(f"- total Python scripts audited: {len(script_rows)}")
    lines.append(f"- guessed active current workflow scripts: {sum(r['status_guess'] == 'ACTIVE_CURRENT_WORKFLOW' for r in script_rows)}")
    lines.append(f"- guessed superseded scripts: {sum(r['status_guess'] == 'SUPERSEDED_BY_LATER_SCRIPT' for r in script_rows)}")
    lines.append(f"- scripts using API/OpenAI-like patterns: {sum(bool(r['uses_openai_or_api']) for r in script_rows)}")
    lines.append(f"- scripts using NCBI/PubMed/SRA-like patterns: {sum(bool(r['uses_ncbi_or_pubmed']) for r in script_rows)}")
    lines.append(f"- scripts using Excel output: {sum(bool(r['uses_excel']) for r in script_rows)}")
    lines.append(f"- scripts with validation/QC logic: {sum(bool(r['validation_or_qc']) for r in script_rows)}")
    lines.append("")

    group_counts = {}
    for r in script_rows:
        group_counts[r["group_guess"]] = group_counts.get(r["group_guess"], 0) + 1

    lines.append("## Scripts by functional group")
    lines.append("")
    for g, n in sorted(group_counts.items()):
        lines.append(f"### {g} ({n})")
        lines.append("")
        for r in script_rows:
            if r["group_guess"] == g:
                flags = []
                if r["uses_openai_or_api"]:
                    flags.append("API/AI")
                if r["uses_ncbi_or_pubmed"]:
                    flags.append("NCBI/PubMed")
                if r["uses_pdf_or_papers"]:
                    flags.append("PDF/papers")
                if r["uses_excel"]:
                    flags.append("Excel")
                if r["validation_or_qc"]:
                    flags.append("QC")
                if r["chip_specific"]:
                    flags.append("ChIP")
                if r["rna_specific"]:
                    flags.append("RNA")
                if r["packaging_or_handoff"]:
                    flags.append("packaging")
                flag_text = ", ".join(flags) if flags else "no major flags"
                lines.append(f"- `{r['script']}` — {r['status_guess']} — {flag_text}")
                if r["docstring"]:
                    lines.append(f"  - doc: {r['docstring'][:240]}")
        lines.append("")

    lines.append("## Output folder inventory")
    lines.append("")
    lines.append(f"- top-level output folders audited: {len(folder_rows)}")
    for r in folder_rows:
        lines.append(f"- `{r['folder']}` — {r['size']}, {r['n_files']} files")
    lines.append("")

    lines.append("## Final-output candidates")
    lines.append("")
    lines.append(f"- candidate files found: {len(final_rows)}")
    for r in final_rows[:120]:
        mark = "FINAL?" if r["final_candidate_guess"] else "intermediate?"
        lines.append(f"- {mark} `{r['path']}` — {r['size']}")
    if len(final_rows) > 120:
        lines.append(f"- ... truncated after 120 of {len(final_rows)}")
    lines.append("")

    lines.append("## Immediate interpretation")
    lines.append("")
    lines.append("The current repository contains a working pipeline, but script naming, output folders, and final products are not yet publication-quality.")
    lines.append("The next step should be to define an ACTIVE_SCRIPT_MAP and a FINAL_OUTPUT_MAP, then create clean workflow wrappers without deleting legacy scripts.")
    lines.append("")

    return "\n".join(lines)


def main():
    script_rows = audit_scripts()
    folder_rows = audit_output_folders()
    final_rows = audit_final_candidates()

    write_tsv(script_rows, OUT / "current_pipeline_script_inventory.tsv")
    write_tsv(folder_rows, OUT / "output_folder_inventory.tsv")
    write_tsv(final_rows, OUT / "final_output_candidates.tsv")

    md = make_md(script_rows, folder_rows, final_rows)
    (OUT / "CURRENT_PIPELINE_REORG_AUDIT.md").write_text(md)

    print("Wrote:")
    print(" -", OUT / "current_pipeline_script_inventory.tsv")
    print(" -", OUT / "output_folder_inventory.tsv")
    print(" -", OUT / "final_output_candidates.tsv")
    print(" -", OUT / "CURRENT_PIPELINE_REORG_AUDIT.md")


if __name__ == "__main__":
    main()
