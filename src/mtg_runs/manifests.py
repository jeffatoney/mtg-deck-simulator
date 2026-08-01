"""Content-bound Phase B run manifests and strict aggregation rejection rules."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@dataclass(frozen=True)
class TestEvidence:
    commit: str
    command: str
    status: str
    passed: int
    failed: int
    skipped: int
    xfailed: int
    artifact_sha256: str

    def __post_init__(self) -> None:
        if self.status != "PASS":
            raise ValueError("same-commit test evidence must be PASS")
        if self.failed or self.skipped or self.xfailed:
            raise ValueError("same-commit test evidence cannot contain failures or exclusions")
        if self.passed < 1:
            raise ValueError("same-commit test evidence must contain passing tests")
        if len(self.artifact_sha256) != 64:
            raise ValueError("test evidence digest must be SHA-256")


@dataclass(frozen=True)
class SeedAssignment:
    shard_index: int
    first_game_index: int
    last_game_index: int
    seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.shard_index < 0:
            raise ValueError("shard index cannot be negative")
        if self.first_game_index < 1 or self.last_game_index < self.first_game_index:
            raise ValueError("invalid contiguous game-index range")
        expected = self.last_game_index - self.first_game_index + 1
        if len(self.seeds) != expected:
            raise ValueError("seed count does not match the assigned game-index range")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("a shard cannot contain duplicate seeds")


@dataclass(frozen=True)
class RunManifest:
    schema_version: str
    run_id: str
    run_mode: str
    git_commit: str
    dirty_tree: bool
    python_version: str
    dependency_lock_sha256: str
    rules_source_sha256: str
    oracle_snapshot_sha256: str
    decklist_sha256: str
    config_sha256: str
    seed_list_sha256: str
    command_line: tuple[str, ...]
    started_at: str
    ended_at: str
    worker_count: int
    assignment: SeedAssignment
    test_evidence: TestEvidence
    evidence_classification: str
    legacy_evidence_used: bool
    pilot_authorized: bool

    def __post_init__(self) -> None:
        if self.schema_version != "phase-b-run-manifest-v1":
            raise ValueError("unsupported run-manifest schema")
        if self.run_mode not in {"STANDARD", "EXPLORATORY", "AUDIT_ONLY", "VERIFICATION"}:
            raise ValueError("unsupported run mode")
        if self.dirty_tree:
            raise ValueError("authoritative run manifests require a clean tree")
        if self.worker_count < 1:
            raise ValueError("worker count must be positive")
        if self.test_evidence.commit != self.git_commit:
            raise ValueError("test evidence must certify the manifest commit")
        if self.evidence_classification != "CLEAN_ENGINE_PRODUCTION_PATH":
            raise ValueError("run manifest evidence classification is not acceptable")
        if self.legacy_evidence_used:
            raise ValueError("legacy evidence is prohibited")
        if self.pilot_authorized:
            raise ValueError("Phase B manifests may not authorize pilot execution")
        if not self.command_line:
            raise ValueError("run manifest must preserve the command line")
        expected = manifest_run_id(self, include_run_id=False)
        if self.run_id != expected:
            raise ValueError("run_id does not match content-bound manifest metadata")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def manifest_run_id(
    manifest: RunManifest | Mapping[str, Any], *, include_run_id: bool = True
) -> str:
    body = asdict(manifest) if isinstance(manifest, RunManifest) else dict(manifest)
    if not include_run_id:
        body.pop("run_id", None)
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    return f"phase-b-{digest[:24]}"


def build_manifest(
    *,
    run_mode: str,
    config_path: Path,
    seed_path: Path,
    command_line: Sequence[str],
    started_at: str,
    ended_at: str,
    worker_count: int,
    assignment: SeedAssignment,
    test_evidence: TestEvidence,
    root: Path = ROOT,
) -> RunManifest:
    commit = _git(root, "rev-parse", "HEAD")
    dirty = bool(_git(root, "status", "--porcelain"))
    data: dict[str, Any] = {
        "schema_version": "phase-b-run-manifest-v1",
        "run_id": "",
        "run_mode": run_mode,
        "git_commit": commit,
        "dirty_tree": dirty,
        "python_version": platform.python_version(),
        "dependency_lock_sha256": _sha256(root / "uv.lock"),
        "rules_source_sha256": _sha256(root / "docs/source/MagicCompRules_2026-06-19.txt"),
        "oracle_snapshot_sha256": _sha256(root / "docs/source/oracle/snapshot_v1.json"),
        "decklist_sha256": _sha256(root / "docs/source/decklist.txt"),
        "config_sha256": _sha256(config_path),
        "seed_list_sha256": _sha256(seed_path),
        "command_line": tuple(str(value) for value in command_line),
        "started_at": started_at,
        "ended_at": ended_at,
        "worker_count": worker_count,
        "assignment": assignment,
        "test_evidence": test_evidence,
        "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH",
        "legacy_evidence_used": False,
        "pilot_authorized": False,
    }
    data["run_id"] = manifest_run_id(data, include_run_id=False)
    return RunManifest(**data)


def write_immutable_run(
    root: Path,
    manifest: RunManifest,
    raw_records: Sequence[Mapping[str, Any]],
) -> Path:
    run_dir = root / manifest.run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    raw_path = run_dir / "raw-records.jsonl"
    manifest_path.write_bytes(_canonical(manifest.to_dict()) + b"\n")
    with raw_path.open("xb") as stream:
        for record in raw_records:
            stream.write(_canonical(dict(record)) + b"\n")
    manifest_path.chmod(0o444)
    raw_path.chmod(0o444)
    return run_dir


def load_manifest(path: Path) -> RunManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assignment = SeedAssignment(**payload.pop("assignment"))
    evidence = TestEvidence(**payload.pop("test_evidence"))
    return RunManifest(**payload, assignment=assignment, test_evidence=evidence)


def validate_aggregation(manifests: Sequence[RunManifest]) -> dict[str, Any]:
    if not manifests:
        raise ValueError("aggregation requires at least one manifest")
    invariant_fields = (
        "run_mode",
        "git_commit",
        "python_version",
        "dependency_lock_sha256",
        "rules_source_sha256",
        "oracle_snapshot_sha256",
        "decklist_sha256",
        "config_sha256",
        "seed_list_sha256",
        "evidence_classification",
        "legacy_evidence_used",
        "pilot_authorized",
    )
    first = manifests[0]
    for manifest in manifests[1:]:
        mixed = [
            field for field in invariant_fields if getattr(manifest, field) != getattr(first, field)
        ]
        if mixed:
            raise ValueError(f"aggregation rejects mixed manifest fields: {mixed}")
        if manifest.test_evidence != first.test_evidence:
            raise ValueError("aggregation rejects mixed same-commit test evidence")

    assignments = sorted(
        (manifest.assignment for manifest in manifests),
        key=lambda assignment: assignment.first_game_index,
    )
    expected_index = 1
    seeds: list[int] = []
    shard_indexes: set[int] = set()
    for assignment in assignments:
        if assignment.shard_index in shard_indexes:
            raise ValueError("aggregation rejects duplicate shard indexes")
        shard_indexes.add(assignment.shard_index)
        if assignment.first_game_index != expected_index:
            raise ValueError("aggregation rejects gaps or overlaps in game indexes")
        expected_index = assignment.last_game_index + 1
        seeds.extend(assignment.seeds)
    if len(seeds) != len(set(seeds)):
        raise ValueError("aggregation rejects duplicate seeds")
    return {
        "schema_version": "phase-b-aggregation-validation-v1",
        "status": "PASS",
        "git_commit": first.git_commit,
        "run_mode": first.run_mode,
        "shard_count": len(manifests),
        "game_count": len(seeds),
        "first_game_index": 1,
        "last_game_index": expected_index - 1,
        "seed_sha256": hashlib.sha256(_canonical(seeds)).hexdigest(),
        "worker_counts": sorted({manifest.worker_count for manifest in manifests}),
    }
