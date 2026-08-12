"""Content digests for the durable Phase B certification surface."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COVERED_PATHS = (
    ".github/workflows/ci.yml",
    ".github/workflows/phase-c-pilot.yml",
    ".github/workflows/phase-c-diagnostic.yml",
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
    "tests/phase_c",
    "automation/phase-b-authority-map.json",
    "automation/phase-b-test-mapping.json",
    "scripts/_phase_b_paths.py",
    "scripts/_certification_provenance.py",
    "scripts/check_phase_b_authority.py",
    "scripts/check_phase_b_certification.py",
    "scripts/check_phase_b_evaluator.py",
    "scripts/check_phase_b_golden_transcripts.py",
    "scripts/record_phase_b_certification.py",
    "scripts/check_clean_engine_boundary.py",
    "scripts/check_full_deck_coverage.py",
    "scripts/check_phase_c_turn10.py",
    "configs/baseline.toml",
    "configs/policies.json",
    "configs/policies.yaml",
    "configs/policy_seeds.json",
    "configs/evaluators",
    "docs/source/MagicCompRules_2026-06-19.txt",
    "docs/source/oracle/snapshot_v1.json",
    "docs/source/decklist.txt",
    "docs/source/commanders.txt",
    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",
    "docs/spec/phase-c/NO_OPPONENT_POLICY_GUARDRAIL.json",
    "docs/architecture/decisions/0015-strategic-choice-boundary-and-learning-snapshots.md",
    "docs/spec/ENGINE_BUILD_PHASE_B.md",
    "docs/spec/EXPLORATORY_SEARCH_LIMITS.md",
    "docs/spec/MEASUREMENTS.md",
    "docs/spec/OPEN_DECISIONS.md",
    "docs/spec/POLICY_CANDIDATES.md",
    "docs/spec/PILOT_PROTOCOL.md",
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


def _archived_files(commit: str) -> dict[str, bytes]:
    """Read the complete certification surface from one exact Git tree in one process."""
    command = ["git", "archive", "--format=tar", commit, "--", *COVERED_PATHS]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise FileNotFoundError(
            f"unable to archive certification surface at commit {commit}: {message}"
        )
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if any(part in _IGNORED for part in Path(member.name).parts):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(f"unable to read {member.name} at commit {commit}")
            files[member.name] = extracted.read()
    return files


def _digest_archived_path(relative: str, files: dict[str, bytes], commit: str) -> str:
    exact = [(relative, files[relative])] if relative in files else []
    prefix = f"{relative.rstrip('/')}/"
    nested = sorted((name, data) for name, data in files.items() if name.startswith(prefix))
    selected = exact or nested
    if not selected:
        raise FileNotFoundError(f"covered path is missing at commit {commit}: {relative}")
    digest = hashlib.sha256()
    for repo_path, data in selected:
        digest.update(repo_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def content_digest_at_commit(relative: str, commit: str) -> str:
    files = _archived_files(commit)
    return _digest_archived_path(relative, files, commit)


def all_digests_at_commit(commit: str) -> dict[str, str]:
    """Return every covered digest from one exact Git archive."""
    files = _archived_files(commit)
    return {relative: _digest_archived_path(relative, files, commit) for relative in COVERED_PATHS}


def aggregate_digest(digests: dict[str, str] | None = None) -> str:
    payload = all_digests() if digests is None else digests
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
