"""Content digests for the durable Phase B certification surface."""

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
    "src/mtg_deck",
    "src/mtg_policy",
    "src/mtg_search",
    "src/mtg_measure",
    "src/mtg_runs",
    "src/mtg_verify",
    "tests/phase_a",
    "tests/phase_b",
    "automation/phase-b-authority-map.json",
    "automation/phase-b-test-mapping.json",
    "scripts/_phase_b_paths.py",
    "scripts/check_phase_b_authority.py",
    "scripts/check_phase_b_certification.py",
    "scripts/check_phase_b_golden_transcripts.py",
    "scripts/record_phase_b_certification.py",
    "scripts/check_clean_engine_boundary.py",
    "scripts/check_full_deck_coverage.py",
    "configs/baseline.toml",
    "configs/policies.json",
    "configs/policies.yaml",
    "configs/policy_seeds.json",
    "docs/source/MagicCompRules_2026-06-19.txt",
    "docs/source/oracle/snapshot_v1.json",
    "docs/source/decklist.txt",
    "docs/source/commanders.txt",
    "docs/spec/ENGINE_BUILD_PHASE_B.md",
    "docs/spec/EXPLORATORY_SEARCH_LIMITS.md",
    "docs/spec/MEASUREMENTS.md",
    "docs/audit/phase-b-golden-transcripts",
)
_IGNORED = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _files(relative: str) -> list[Path]:
    target = ROOT / relative
    if not target.exists():
        raise FileNotFoundError(f"covered path is missing: {relative}")
    if target.is_file():
        return [target]
    files = sorted(
        path
        for path in target.rglob("*")
        if path.is_file() and not any(part in _IGNORED for part in path.parts)
    )
    if not files:
        raise FileNotFoundError(f"covered directory has no files: {relative}")
    return files


def content_digest(relative: str) -> str:
    digest = hashlib.sha256()
    for path in _files(relative):
        data = path.read_bytes()
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(str(len(data)).encode())
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def all_digests() -> dict[str, str]:
    return {relative: content_digest(relative) for relative in COVERED_PATHS}


def aggregate_digest(digests: dict[str, str] | None = None) -> str:
    payload = all_digests() if digests is None else digests
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
