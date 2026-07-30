"""Content digests for the durable Phase A certification surface.

The certification record lives under ``docs/`` and is intentionally not part of the
surface it certifies. Every path that can change Phase A behavior, evidence, packaging,
or enforcement is included here. Path names and file bytes are both hashed, so renames
and uncommitted edits invalidate certification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COVERED_PATHS = (
    ".github/workflows/ci.yml",
    "pyproject.toml",
    "src/mtg_kernel",
    "src/mtg_cards",
    "src/mtg_verify",
    "src/mtg_sources",
    "tests/phase_a",
    "tests/conftest.py",
    "tests/test_gate_negatives.py",
    "tests/test_certification_gate.py",
    "tests/test_boundary_support_tier.py",
    "tests/test_source_validation.py",
    "automation/phase-a-test-mapping.json",
    "scripts/_phase_a_paths.py",
    "scripts/check_phase_a_certification.py",
    "scripts/record_phase_a_certification.py",
    "scripts/check_clean_engine_boundary.py",
    "scripts/check_phase_a_authority.py",
    "scripts/check_identity_lock.py",
    "scripts/phase_a_verify_runner.py",
    "docs/source/oracle/snapshot_v1.json",
    "docs/source/source_inventory.json",
)

_IGNORED_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _files(relative: str) -> list[Path]:
    target = ROOT / relative
    if not target.exists():
        raise FileNotFoundError(f"covered path is missing: {relative}")
    if target.is_file():
        return [target]
    files = sorted(
        path
        for path in target.rglob("*")
        if path.is_file() and not any(part in _IGNORED_DIRECTORIES for part in path.parts)
    )
    if not files:
        raise FileNotFoundError(f"covered directory has no files: {relative}")
    return files


def content_digest(relative: str) -> str:
    """Return a path-and-content SHA-256 for one covered file or directory."""
    digest = hashlib.sha256()
    for path in _files(relative):
        data = path.read_bytes()
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def all_digests() -> dict[str, str]:
    return {relative: content_digest(relative) for relative in COVERED_PATHS}


def aggregate_digest(digests: dict[str, str] | None = None) -> str:
    payload = all_digests() if digests is None else digests
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
