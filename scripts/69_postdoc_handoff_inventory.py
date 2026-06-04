#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import subprocess
import pandas as pd

OUT = Path("outputs/99_POSTDOC_HANDOFF")
OUT.mkdir(parents=True, exist_ok=True)

def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as e:
        return e.output.strip()

def latest(pattern):
    hits = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(hits[0]) if hits else ""

def exists(path):
    return "YES" if path and Path(path).exists() else "NO"

def size(path):
    if not path or not Path(path).exists():
        return ""
    return sh(f"du -sh '{path}' | cut -f1")

def df_to_markdown_simple(df):
    """Small dependency-free markdown table writer."""
    if df is None or df.empty:
        return "_empty_"

    cols = list(df.columns)

    def esc(x):
        x = "" if x is None else str(x)
        return x.replace("|", "\\|").replace("\n", " ")

    lines = []
    lines.append("| " + " | ".join(esc(c) for c in cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")

    for _, row in df.iterrows():
        lines.append("| " + " | ".join(esc(row[c]) for c in cols) + " |")

    return "\n".join(lines)

def main():
    now = datetime.now().isoformat(timespec="seconds")

    key_files = [
        ("RNA completion report", "outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md"),
        ("RNA latest curator Excel", latest("outputs/04_AGENTIC_AI_ASSIST/curator_excel/*.xlsx")),
        ("ChIP completion report", "outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md"),
        ("ChIP latest curator Excel", latest("outputs/06_CHIP_AI_ASSIST/21_curator_excel/*.xlsx")),
        ("ChIP active validated inventory", "outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_active_validated_outputs.tsv"),
        ("ChIP rowwise review TSV", "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv"),
        ("ChIP target-control map TSV", "outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv"),
    ]

    key_df = pd.DataFrame([
        {
            "item": name,
            "path": path,
            "exists": exists(path),
            "size": size(path),
        }
        for name, path in key_files
    ])
    key_df.to_csv(OUT / "key_outputs_inventory.tsv", sep="\t", index=False)

    dirs = [
        "outputs/04_AGENTIC_AI_ASSIST",
        "outputs/06_CHIP_AI_ASSIST",
        "papers",
        "data",
        "scripts",
    ]
    dir_df = pd.DataFrame([
        {
            "path": d,
            "exists": exists(d),
            "size": size(d),
        }
        for d in dirs
    ])
    dir_df.to_csv(OUT / "directory_size_inventory.tsv", sep="\t", index=False)

    git_status = sh("git status --short")
    git_branch = sh("git branch --show-current")
    git_log = sh("git log --oneline -5")
    (OUT / "git_status.txt").write_text(
        f"Generated: {now}\n\n"
        f"Branch:\n{git_branch}\n\n"
        f"Recent commits:\n{git_log}\n\n"
        f"Git status --short:\n{git_status}\n"
    )

    suggested_ignore = """# Suggested local/private/generated files to avoid committing
.env
*.env
papers/
outputs/
__pycache__/
*.pyc
.DS_Store
*.log

# Usually do not commit large raw/generated data unless intentionally versioned
data/*.pdf
data/gold_standard/
sra_curator_fresh_chat_context_pack.zip
tree
"""
    (OUT / "SUGGESTED_GITIGNORE.txt").write_text(suggested_ignore)

    runbook = f"""# Postdoc handoff: SRA paper curator production rerun

Generated: {now}

## Current milestone

RNA and ChIP AI-assisted curation have both reached structurally validated curator-review outputs.

ChIP status:
- 42/42 ChIP packets active validated PASS
- large AP2 landscape packet handled by target-centered chunking and merge
- final curator workbook generated

RNA status:
- trusted PMID-linked RNA AI phase completed earlier
- final curator workbook generated

## Core principle

The pipeline should be run in two modes:

1. Non-API / dry-run / validation-only mode
   - safe for setup, inspection, inventory, QC, and workbook rebuilding
   - should not require an API token

2. API execution mode
   - only when explicitly requested with flags such as --execute
   - requires .env / API token locally
   - API keys must never be committed

## Key curator-facing outputs

See:
- key_outputs_inventory.tsv

Most important:
- RNA curator Excel
- ChIP curator Excel
- ChIP target-control map TSV
- RNA and ChIP completion reports

## ChIP-specific production lessons

- ChIP controls/inputs/IgG are usually separate FASTQ/SRR rows.
- Target/IP rows may point to input/background rows through assigned_control columns.
- Shared input controls are expected and should be represented in Target_Control_Map, not by duplicating sample_map membership.
- sample_map must be a partition of source_row_id.
- If rowwise_suggestions cover all source_row_id exactly once, sample_map can be rebuilt deterministically.
- Missing rowwise_suggestions should not be invented.
- Large AP2 landscape packet must use target-centered chunking, then merge, then parent-level sample_map rebuild.

## Scripts added/updated recently

Important ChIP scripts:
- scripts/50_inspect_chip_master.py
- scripts/59b_patch_chip_packet_control_roles.py
- scripts/60_validate_chip_ai_output.py
- scripts/60b_rebuild_chip_sample_map_from_rowwise.py
- scripts/61_inventory_chip_ai_outputs.py
- scripts/62_batch_run_chip_small_packets_production.py
- scripts/63_prepare_chip_chunked_packet.py
- scripts/64_merge_chip_chunk_outputs.py
- scripts/65_audit_chip_repeats_and_chunk_failures.py
- scripts/66_patch_chip_rowwise_roles_from_prelim.py
- scripts/67_finalize_chip_ai_phase.py
- scripts/68_build_chip_curator_excel.py
- scripts/69_postdoc_handoff_inventory.py

## Before postdoc rerun

Recommended checks:
1. Confirm repo branch and clean git state.
2. Confirm input metadata files are present under data/.
3. Confirm .env exists only locally if API execution is needed.
4. Run inspection/preflight scripts before API execution.
5. Run API batches only with explicit --execute.
6. Validate after every batch.
7. Rebuild sample_map deterministically when rowwise coverage is exact.
8. Rebuild final Excel workbooks from validated active inventories.

## Do not commit

- .env or API tokens
- raw PDFs unless intentionally allowed
- bulky generated output folders
- temporary zip/context files
- cache files
"""
    (OUT / "POSTDOC_RERUN_RUNBOOK.md").write_text(runbook)

    summary = f"""# Handoff inventory summary

Generated: {now}

## Key outputs

{df_to_markdown_simple(key_df)}

## Directory sizes

{df_to_markdown_simple(dir_df)}

## Next recommended actions

1. Inspect `git_status.txt`.
2. Commit production scripts and small handoff/runbook files.
3. Do not commit `.env`, PDFs, or bulky generated outputs.
4. Share curator Excel files with Shalini/curators.
5. Give postdoc this runbook plus the repo branch for stress-testing.
"""
    (OUT / "HANDOFF_SUMMARY.md").write_text(summary)

    print("Wrote handoff files to:", OUT)
    print()
    print(summary)

if __name__ == "__main__":
    main()
