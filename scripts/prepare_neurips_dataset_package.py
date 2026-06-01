#!/usr/bin/env python3
"""Create a clean LivePI release package for Dataverse upload."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "livepi_neurips_dataset"

EXCLUDE_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "node_modules",
    "results",
    "generated",
}

EXCLUDE_GLOBS = (
    "*.pyc",
    "*.pyo",
    "*.tar.gz",
    "*.zip",
    ".DS_Store",
    ".env",
    ".env.*",
    "*.secrets.env",
    "secrets.env",
    ".gateway_device_identity.json",
    "prompt_injection_lab/results*",
    "prompt_injection_lab/generated",
    "prompt_injection_lab/.gateway_device_identity.json",
)

INCLUDE_EXCEPTIONS = {
    "prompt_injection_lab/.env.example",
    "secrets.example.env",
}


@dataclass(frozen=True)
class ManifestEntry:
    relpath: str
    size: int
    sha256: str


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _excluded(path: Path) -> bool:
    rel = _rel(path)
    if rel in INCLUDE_EXCEPTIONS:
        return False
    parts = set(path.relative_to(REPO_ROOT).parts)
    if parts & EXCLUDE_PARTS:
        return True
    return any(fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_GLOBS)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if path.is_dir() or _excluded(path):
            continue
        files.append(path)
    return sorted(files, key=_rel)


def _copy_release(output: Path) -> list[ManifestEntry]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    entries: list[ManifestEntry] = []
    for src in _iter_files():
        rel = _rel(src)
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        entries.append(ManifestEntry(rel, src.stat().st_size, _sha256(src)))
    return entries


def _write_manifest(output: Path, entries: list[ManifestEntry]) -> None:
    manifest = output / "MANIFEST.sha256"
    with manifest.open("w", encoding="utf-8") as f:
        f.write("# sha256  size_bytes  path\n")
        for entry in entries:
            f.write(f"{entry.sha256}  {entry.size}  {entry.relpath}\n")


def _make_archive(output: Path) -> Path:
    archive = output.with_suffix(".tar.gz")
    if archive.exists():
        archive.unlink()
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(output, arcname=output.name)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Release directory to create")
    parser.add_argument("--archive", action="store_true", help="Also create a .tar.gz archive")
    args = parser.parse_args()

    output = args.output.resolve()
    entries = _copy_release(output)
    _write_manifest(output, entries)

    print(f"Wrote release directory: {output}")
    print(f"Included files: {len(entries)}")
    print(f"Manifest: {output / 'MANIFEST.sha256'}")
    if args.archive:
        archive = _make_archive(output)
        print(f"Archive: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
