"""Shared file/path utilities for production workflow scripts."""

from __future__ import annotations

from pathlib import Path
import csv
import hashlib
import shutil
import zipfile


def sha256_file(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def size_human(path: str | Path) -> str:
    path = Path(path)
    n = path.stat().st_size
    for unit in ["B", "K", "M", "G"]:
        if n < 1024:
            return f"{n}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def latest_glob(pattern: str, root: str | Path = ".") -> Path | None:
    root = Path(root)
    hits = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def latest_from_pointer(pointer: str | Path) -> Path | None:
    pointer = Path(pointer)
    if not pointer.exists():
        return None
    for line in pointer.read_text().strip().splitlines():
        p = Path(line.strip())
        if p.exists() and p.is_file():
            return p
    return None


def copy_file_with_manifest(
    src: str | Path | None,
    dst_dir: str | Path,
    out_name: str,
    description: str,
    manifest: list[dict],
    required: bool = False,
) -> Path | None:
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
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / out_name
    shutil.copy2(src, dst)

    manifest.append({
        "status": "copied",
        "description": description,
        "source": str(src),
        "destination": str(dst),
        "size": size_human(dst),
        "sha256": sha256_file(dst),
    })
    return dst


def write_manifest_tsv(manifest: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["status", "description", "source", "destination", "size", "sha256"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for row in manifest:
            w.writerow(row)
    return path


def count_tsv_rows(path: str | Path) -> int:
    path = Path(path)
    if not path.exists():
        return 0
    with open(path, newline="", errors="ignore") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return max(len(rows) - 1, 0)


def count_text_marker(path: str | Path, marker: str) -> int:
    path = Path(path)
    if not path.exists():
        return 0
    return path.read_text(errors="ignore").count(marker)


def zip_directory_contents(source_dir: str | Path, zip_path: str | Path, archive_parent: bool = True) -> Path:
    source_dir = Path(source_dir)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in source_dir.rglob("*"):
            if p.is_file():
                if archive_parent:
                    arcname = p.relative_to(source_dir.parent)
                else:
                    arcname = p.relative_to(source_dir)
                z.write(p, arcname)

    return zip_path


def find_forbidden_files(
    root: str | Path,
    forbidden_suffixes: list[str],
    forbidden_name_parts: list[str],
) -> list[str]:
    root = Path(root)
    hits = []
    if not root.exists():
        return hits

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if any(name.endswith(s.lower()) for s in forbidden_suffixes):
            hits.append(str(p))
        if any(part.lower() in name for part in forbidden_name_parts):
            hits.append(str(p))

    return sorted(set(hits))
