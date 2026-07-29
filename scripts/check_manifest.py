#!/usr/bin/env python3
"""Validate frozen handoff hashes and required tracked bootstrap files."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "HANDOFF_MANIFEST.json"

REQUIRED_TRACKED_PATHS = (
    ".github/pull_request_template.md",
    ".github/workflows/ci.yml",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "CODEX_CLOUD_SETUP_SCRIPT.sh",
    "HANDOFF_MANIFEST.json",
    "README.md",
    "pyproject.toml",
    "scripts/check_manifest.py",
    "src/mtg_sources/__init__.py",
    "src/mtg_sources/cli.py",
    "legacy/mtg_sim/__init__.py",
    "legacy/mtg_sim/cli.py",
    "tests/test_bootstrap.py",
    "docs/source/MagicCompRules_2026-06-19.txt",
    "docs/source/commanders.txt",
    "docs/source/decklist.txt",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []

    for relative in REQUIRED_TRACKED_PATHS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"required file missing: {relative}")
        elif not is_tracked(relative):
            errors.append(f"required file is not tracked: {relative}")

    for relative, metadata in sorted(data.items()):
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"manifest file missing: {relative}")
            continue
        if not is_tracked(relative):
            errors.append(f"manifest file is not tracked: {relative}")
            continue

        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        expected_size = int(metadata["bytes"])
        expected_hash = str(metadata["sha256"])
        if actual_size != expected_size:
            errors.append(f"size mismatch: {relative}: expected {expected_size}, got {actual_size}")
        if actual_hash != expected_hash:
            errors.append(f"hash mismatch: {relative}: expected {expected_hash}, got {actual_hash}")

    if errors:
        print("Manifest integrity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"Manifest integrity check passed for {len(data)} frozen files "
        f"and {len(REQUIRED_TRACKED_PATHS)} required paths."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
