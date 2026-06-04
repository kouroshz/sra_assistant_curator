#!/usr/bin/env python3
"""
Package final curator-facing RNA + ChIP files into one shareable folder and zip.

This script does not run AI.
It does not require an API token.
It does not include raw PDFs, .env, raw AI JSONs, or bulky intermediate output folders.

Outputs:
  outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>/
  outputs/99_CURATOR_SHARE_BUNDLES/curator_share_bundle_<timestamp>.zip
  outputs/99_CURATOR_SHARE_BUNDLES/LATEST_CURATOR_SHARE_BUNDLE.txt
"""

from pathlib import Path
from datetime import datetime
import shutil
import zipfile
import hashlib
import os


OUT_BASE = Path("outputs/99_CURATOR_SHARE_BUNDLES")


def find_latest(pattern):
    hits = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def size_human(path):
    n = path.stat().st_size
    for unit in ["B", "K", "M", "G"]:
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}T"


def copy_file(src, dst_dir, label, manifest, required=True, rename=None):
    if src is None:
        manifest.append({
            "label": label,
            "source": "",
            "bundle_path": "",
            "status": "MISSING",
            "size": "",
            "sha256": "",
        })
        if required:
            print(f"WARNING missing required file for {label}")
        return

    src = Path(src)
    if not src.exists():
        manifest.append({
            "label": label,
            "source": str(src),
            "bundle_path": "",
            "status": "MISSING",
            "size": "",
            "sha256": "",
        })
        if required:
            print(f"WARNING missing required file: {src}")
        return

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_name = rename if rename else src.name
    dst = dst_dir / dst_name
    shutil.copy2(src, dst)

    manifest.append({
        "label": label,
        "source": str(src),
        "bundle_path": str(dst),
        "status": "COPIED",
        "size": size_human(dst),
        "sha256": sha256(dst),
    })


def write_tsv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["label", "source", "bundle_path", "status", "size", "sha256"]
    with open(path, "w") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")


def make_zip(folder, zip_path):
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, arcname=p.relative_to(folder.parent))


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_BASE.mkdir(parents=True, exist_ok=True)

    # Refresh ChIP curator companion files if export scripts exist.
    import subprocess

    export_script = Path("scripts/71_export_chip_curator_companion_files.py")
    if export_script.exists():
        subprocess.run(["python", str(export_script)], check=True)

    summary_script = Path("scripts/72_export_chip_study_summaries_clean.py")
    if summary_script.exists():
        subprocess.run(["python", str(summary_script)], check=True)

    bundle = OUT_BASE / f"curator_share_bundle_{ts}"
    if bundle.exists():
        shutil.rmtree(bundle)

    rna_dir = bundle / "RNA"
    chip_dir = bundle / "ChIP"
    docs_dir = bundle / "docs"

    manifest = []

    # RNA files
    rna_excel = find_latest("outputs/04_AGENTIC_AI_ASSIST/curator_excel/*.xlsx")
    copy_file(
        rna_excel,
        rna_dir,
        "RNA curator Excel workbook",
        manifest,
        required=True,
        rename="RNA_curator_review.xlsx",
    )

    copy_file(
        Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md"),
        rna_dir,
        "RNA completion report",
        manifest,
        required=True,
    )

    copy_file(
        Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc/trusted_rna_ai_phase_packet_status.tsv"),
        rna_dir,
        "RNA packet status table",
        manifest,
        required=False,
    )

    copy_file(
        Path("outputs/04_AGENTIC_AI_ASSIST/deep_qc/held_packets_for_policy_review.tsv"),
        rna_dir,
        "RNA held packets for policy review",
        manifest,
        required=False,
    )

    # ChIP files
    chip_excel = find_latest("outputs/06_CHIP_AI_ASSIST/21_curator_excel/*.xlsx")
    copy_file(
        chip_excel,
        chip_dir,
        "ChIP curator Excel workbook",
        manifest,
        required=True,
        rename="ChIP_curator_review.xlsx",
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md"),
        chip_dir,
        "ChIP completion report",
        manifest,
        required=True,
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/20_final_qc/trusted_chip_ai_phase_packet_status.tsv"),
        chip_dir,
        "ChIP packet status table",
        manifest,
        required=True,
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv"),
        chip_dir,
        "ChIP rowwise review TSV",
        manifest,
        required=True,
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv"),
        chip_dir,
        "ChIP target-control map review TSV",
        manifest,
        required=True,
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/chip_ai_active_validated_outputs.tsv"),
        chip_dir,
        "ChIP active validated output inventory",
        manifest,
        required=False,
    )

    copy_file(
        Path("outputs/06_CHIP_AI_ASSIST/14_chip_ai_inventory/CHIP_AI_OUTPUT_INVENTORY_REPORT.md"),
        chip_dir,
        "ChIP output inventory report",
        manifest,
        required=False,
    )

    # Copy standalone ChIP curator companion files.
    chip_share = Path("outputs/06_CHIP_AI_ASSIST/22_curator_share_files")
    if chip_share.exists():
        for src in sorted(chip_share.glob("*")):
            if src.is_file():
                copy_file(
                    src,
                    chip_dir / "companion_files",
                    f"ChIP companion file: {src.name}",
                    manifest,
                    required=False,
                )

    # Copy RNA-style ChIP study-summary files.
    chip_study_summaries = Path("outputs/06_CHIP_AI_ASSIST/23_study_summaries")
    if chip_study_summaries.exists():
        for src in sorted(chip_study_summaries.glob("*")):
            if src.is_file():
                copy_file(
                    src,
                    chip_dir / "study_summaries",
                    f"ChIP study summary file: {src.name}",
                    manifest,
                    required=False,
                )

    # Handoff docs
    optional_docs = [
        ("Production rerun guide", Path("README_PRODUCTION_RERUN.md")),
        ("Postdoc rerun runbook", Path("docs/POSTDOC_RERUN_RUNBOOK.md")),
        ("Handoff summary", Path("docs/HANDOFF_SUMMARY.md")),
        ("ChIP phase completion report copy", Path("docs/CHIP_AI_PHASE_COMPLETION_REPORT.md")),
        ("RNA phase completion report copy", Path("docs/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md")),
    ]

    for label, path in optional_docs:
        copy_file(path, docs_dir, label, manifest, required=False)

    # Bundle README
    readme = bundle / "CURATOR_BUNDLE_README.md"
    readme.write_text(f"""# Curator share bundle

Generated: {datetime.now().isoformat(timespec="seconds")}

This bundle contains curator-facing RNA and ChIP AI-assisted metadata review files.

AI outputs are suggestions only. Curator decisions, corrections, and comments are authoritative.

## Main files

RNA:
- RNA/RNA_curator_review.xlsx
- RNA/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md
- RNA/trusted_rna_ai_phase_packet_status.tsv
- RNA/held_packets_for_policy_review.tsv

ChIP:
- ChIP/ChIP_curator_review.xlsx
- ChIP/CHIP_AI_PHASE_COMPLETION_REPORT.md
- ChIP/chip_target_control_map_review.tsv
- ChIP/chip_rowwise_review.tsv
- ChIP/trusted_chip_ai_phase_packet_status.tsv

## Suggested curator workflow

For RNA:
1. Open RNA_curator_review.xlsx.
2. Review study-level and sample-level suggestions.
3. Pay attention to held/policy-review packets.
4. Use curator fields/comments for corrections.

For ChIP:
1. Open ChIP_curator_review.xlsx.
2. Start with README and Study_Review.
3. Prioritize Target_Control_Map_Review.
4. Use Problem_Rows to find partial/no peak-calling readiness cases.
5. Spot-check Rowwise_Review.
6. Treat shared input/background controls as expected ChIP structure, not as duplicate errors.

## Current completion status

RNA:
- Trusted PMID-linked RNA AI phase completed.
- 69 PASS packets.
- 2 intentionally held NO_VALIDATION packets.

ChIP:
- 42/42 packets active validated PASS.
- 733 rowwise review rows.
- 490 target-control map rows.
- Peak-calling readiness: 30 yes, 11 partial, 1 no.

## Not included

This bundle intentionally excludes:
- API keys and .env files
- raw PDFs
- raw AI JSONs
- bulky intermediate output folders
- local scratch files
""")

    manifest.append({
        "label": "Bundle README",
        "source": "generated",
        "bundle_path": str(readme),
        "status": "COPIED",
        "size": size_human(readme),
        "sha256": sha256(readme),
    })

    manifest_path = bundle / "MANIFEST.tsv"
    write_tsv(manifest, manifest_path)

    zip_path = OUT_BASE / f"{bundle.name}.zip"
    make_zip(bundle, zip_path)

    latest = OUT_BASE / "LATEST_CURATOR_SHARE_BUNDLE.txt"
    latest.write_text(f"{bundle}\n{zip_path}\n")

    print("Wrote bundle folder:", bundle)
    print("Wrote zip:", zip_path)
    print("Wrote latest pointer:", latest)
    print()
    print("Bundle contents:")
    for p in sorted(bundle.rglob("*")):
        if p.is_file():
            print(" -", p, size_human(p))

    print()
    print("Zip size:", size_human(zip_path))

    missing_required = [
        r for r in manifest
        if r["status"] != "COPIED" and "curator" in r["label"].lower()
    ]
    if missing_required:
        print()
        print("WARNING: Some important curator files were missing:")
        for r in missing_required:
            print(" -", r["label"], r["source"])


if __name__ == "__main__":
    main()
