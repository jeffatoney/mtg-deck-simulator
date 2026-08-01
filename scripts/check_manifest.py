#!/usr/bin/env python3
"""Validate or deterministically refresh frozen handoff hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Sequence

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


def _tracked_path_errors(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_TRACKED_PATHS:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"required file missing: {relative}")
        elif not is_tracked(relative):
            errors.append(f"required file is not tracked: {relative}")

    for relative in sorted(data):
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"manifest file missing: {relative}")
        elif not is_tracked(relative):
            errors.append(f"manifest file is not tracked: {relative}")
    return errors


def refreshed_manifest(data: dict[str, object]) -> dict[str, dict[str, int | str]]:
    """Recompute existing frozen entries without adding or removing paths."""

    return {
        relative: {
            "bytes": (ROOT / relative).stat().st_size,
            "sha256": sha256(ROOT / relative),
        }
        for relative in sorted(data)
    }


def write_manifest(data: dict[str, object]) -> None:
    refreshed = refreshed_manifest(data)
    MANIFEST.write_text(
        json.dumps(refreshed, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_manifest(data: dict[str, object]) -> list[str]:
    errors = _tracked_path_errors(data)
    if errors:
        return errors

    for relative, metadata_raw in sorted(data.items()):
        if not isinstance(metadata_raw, dict):
            errors.append(f"manifest metadata is not an object: {relative}")
            continue
        metadata = metadata_raw
        path = ROOT / relative
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        expected_size = int(metadata["bytes"])
        expected_hash = str(metadata["sha256"])
        if actual_size != expected_size:
            errors.append(f"size mismatch: {relative}: expected {expected_size}, got {actual_size}")
        if actual_hash != expected_hash:
            errors.append(f"hash mismatch: {relative}: expected {expected_hash}, got {actual_hash}")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="refresh bytes and SHA-256 values for the existing manifest paths",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("Manifest integrity check failed:\n- manifest root is not an object")
        return 1

    tracked_errors = _tracked_path_errors(data)
    if tracked_errors:
        print("Manifest integrity check failed:")
        for error in tracked_errors:
            print(f"- {error}")
        return 1

    if args.write:
        write_manifest(data)
        print(f"Refreshed {len(data)} frozen manifest entries deterministically.")
        return 0

    errors = validate_manifest(data)
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
