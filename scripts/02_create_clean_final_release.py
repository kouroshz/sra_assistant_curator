#!/usr/bin/env python3
"""
Create a clean final curator release folder.

Non-destructive:
- reads existing final outputs
- copies selected final files into results/final_curator_release/
- writes README + MANIFEST
- creates a zip

No API calls.
No modification of source outputs.
"""

from pathlib import Path
from datetime import datetime
import csv
import hashlib
import shutil
import zipfile


RELEASE_ROOT = Path("results/final_curator_release")
LATEST_POINTER = Path("results/LATEST_FINAL_CURATOR_RELEASE.txt")


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
            return f"{n}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def latest_glob(pattern):
    hits = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def latest_from_pointer(pointer):
    pointer = Path(pointer)
    if not pointer.exists():
        return None
    for line in pointer.read_text().strip().splitlines():
        p = Path(line.strip())
        if p.exists() and p.is_file():
            return p
    return None


def copy_file(src, dst_dir, out_name, description, manifest, required=False):
    if src is None or not Path(src).exists():
        if required:
            raise SystemExit(f"Missing required file: {src}")
        manifest.append({
            "status": "missing_optional",
            "description": description,
            "source": str(src) if src else "",
            "destination": "",
            "size": "",
            "sha256": "",
        })
        return None

    src = Path(src)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / out_name
    shutil.copy2(src, dst)

    manifest.append({
        "status": "copied",
        "description": description,
        "source": str(src),
        "destination": str(dst),
        "size": size_human(dst),
        "sha256": sha256(dst),
    })
    return dst


def write_manifest(manifest):
    path = RELEASE_ROOT / "MANIFEST.tsv"
    cols = ["status", "description", "source", "destination", "size", "sha256"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for row in manifest:
            w.writerow(row)


def write_readme(manifest):
    copied = [m for m in manifest if m["status"] == "copied"]
    missing = [m for m in manifest if m["status"] != "copied"]

    lines = [
        "# Final Curator Release",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "This folder contains the clean curator-facing RNA and ChIP deliverables.",
        "",
        "## Start here",
        "",
        "1. RNA/RNA_curator_review.xlsx",
        "2. ChIP/ChIP_curator_review.xlsx",
        "3. RNA/RNA_AI_STUDY_SUMMARIES_CLEAN.md",
        "4. ChIP/CHIP_AI_STUDY_SUMMARIES_CLEAN.md",
        "5. QC/ reports",
        "",
        "## Important",
        "",
        "- AI outputs are curator aids only.",
        "- Curator-final columns in the Excel files are authoritative.",
        "- ChIP target-control/background relationships should be reviewed carefully.",
        "- This folder excludes raw PDFs, raw AI JSONs, bulky intermediate outputs, and API keys.",
        "",
        "## Files copied",
        "",
    ]

    for m in copied:
        lines.append(f"- {m['destination']} — {m['description']}")

    if missing:
        lines.extend(["", "## Missing optional files", ""])
        for m in missing:
            lines.append(f"- {m['description']} — source: {m['source']}")

    lines.extend(["", "## Manifest", "", "See MANIFEST.tsv for checksums and source paths."])

    (RELEASE_ROOT / "README.md").write_text("\n".join(lines))


def zip_release(ts):
    zip_path = Path("results") / f"final_curator_release_{ts}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in RELEASE_ROOT.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(RELEASE_ROOT.parent))

    LATEST_POINTER.parent.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(str(RELEASE_ROOT) + "\n" + str(zip_path) + "\n")
    return zip_path


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)

    for sub in ["RNA", "ChIP", "QC", "docs"]:
        (RELEASE_ROOT / sub).mkdir(parents=True, exist_ok=True)

    manifest = []

    rna_workbook = latest_glob("outputs/04_AGENTIC_AI_ASSIST/curator_share/trusted_rna_*/curator_review_*.xlsx")
    if rna_workbook is None:
        rna_workbook = latest_glob("outputs/04_AGENTIC_AI_ASSIST/curator_excel/curator_review_*.xlsx")

    chip_workbook = latest_from_pointer("outputs/06_CHIP_AI_ASSIST/21_curator_excel/LATEST_CHIP_CURATOR_REVIEW.txt")
    if chip_workbook is None:
        chip_workbook = latest_glob("outputs/06_CHIP_AI_ASSIST/21_curator_excel/chip_curator_review_v5_*.xlsx")

    copy_file(rna_workbook, RELEASE_ROOT / "RNA", "RNA_curator_review.xlsx", "Final RNA curator review workbook", manifest, required=True)
    copy_file("outputs/04_AGENTIC_AI_ASSIST/deep_qc/AI_STUDY_SUMMARIES_CLEAN.md", RELEASE_ROOT / "RNA", "RNA_AI_STUDY_SUMMARIES_CLEAN.md", "RNA whole-paper AI study summaries", manifest)
    copy_file("outputs/04_AGENTIC_AI_ASSIST/deep_qc/ai_study_summaries_clean.tsv", RELEASE_ROOT / "RNA", "rna_ai_study_summaries_clean.tsv", "RNA study summaries table", manifest)

    copy_file(chip_workbook, RELEASE_ROOT / "ChIP", "ChIP_curator_review.xlsx", "Final ChIP curator review workbook", manifest, required=True)
    copy_file("outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_CLEAN.md", RELEASE_ROOT / "ChIP", "CHIP_AI_STUDY_SUMMARIES_CLEAN.md", "ChIP whole-paper AI study summaries", manifest)
    copy_file("outputs/06_CHIP_AI_ASSIST/23_study_summaries/chip_ai_study_summaries_clean.tsv", RELEASE_ROOT / "ChIP", "chip_ai_study_summaries_clean.tsv", "ChIP study summaries table", manifest)
    copy_file("outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_rowwise_review.tsv", RELEASE_ROOT / "ChIP", "chip_rowwise_review.tsv", "Final ChIP rowwise review table", manifest)
    copy_file("outputs/06_CHIP_AI_ASSIST/20_final_qc/chip_target_control_map_review.tsv", RELEASE_ROOT / "ChIP", "chip_target_control_map_review.tsv", "Final ChIP target-control map review table", manifest)

    copy_file("outputs/04_AGENTIC_AI_ASSIST/deep_qc/TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md", RELEASE_ROOT / "QC", "TRUSTED_RNA_AI_PHASE_COMPLETION_REPORT.md", "RNA AI phase completion report", manifest)
    copy_file("outputs/04_AGENTIC_AI_ASSIST/deep_qc/SEMANTIC_RED_FLAG_SUMMARY.md", RELEASE_ROOT / "QC", "RNA_SEMANTIC_RED_FLAG_SUMMARY.md", "RNA semantic red-flag summary", manifest)
    copy_file("outputs/06_CHIP_AI_ASSIST/20_final_qc/CHIP_AI_PHASE_COMPLETION_REPORT.md", RELEASE_ROOT / "QC", "CHIP_AI_PHASE_COMPLETION_REPORT.md", "ChIP AI phase completion report", manifest)
    copy_file("outputs/06_CHIP_AI_ASSIST/23_study_summaries/CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md", RELEASE_ROOT / "QC", "CHIP_AI_STUDY_SUMMARIES_FINAL_QC.md", "ChIP study-summary final QC", manifest)

    copy_file("docs/ACTIVE_WORKFLOW_MAP.md", RELEASE_ROOT / "docs", "ACTIVE_WORKFLOW_MAP.md", "Current active workflow map", manifest)
    copy_file("docs/PRODUCTION_REORG_PLAN.md", RELEASE_ROOT / "docs", "PRODUCTION_REORG_PLAN.md", "Production reorganization plan", manifest)

    write_manifest(manifest)
    write_readme(manifest)
    zip_path = zip_release(ts)

    print("Wrote clean final release folder:")
    print("  " + str(RELEASE_ROOT))
    print("Wrote zip:")
    print("  " + str(zip_path))
    print("Wrote pointer:")
    print("  " + str(LATEST_POINTER))
    print("")
    print("Files:")
    for p in sorted(RELEASE_ROOT.rglob("*")):
        if p.is_file():
            print("  " + str(p))


if __name__ == "__main__":
    main()
