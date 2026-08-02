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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _declared_evaluator_identity(path: Path) -> tuple[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for identity_key, digest_key in (("snapshot_id", "snapshot_sha256"), ("evaluator_id", "config_sha256")):
        identity = str(payload.get(identity_key, ""))
        digest = str(payload.get(digest_key, ""))
        if identity and len(digest) == 64:
            return identity, digest
    raise ValueError("evaluator artifact omits a content-addressed identity and SHA-256")


def _declared_learning_plan_sha256(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = str(payload.get("plan_sha256", ""))
    body = {key: value for key, value in payload.items() if key != "plan_sha256"}
    actual = hashlib.sha256(_canonical(body)).hexdigest()
    if len(recorded) != 64 or recorded != actual:
        raise ValueError("learning plan omits or mismatches its declared SHA-256")
    return recorded


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
        if self.passed < 1 or len(self.artifact_sha256) != 64:
            raise ValueError("same-commit test evidence is incomplete")


@dataclass(frozen=True)
class SeedAssignment:
    shard_index: int
    first_game_index: int
    last_game_index: int
    seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.shard_index < 0 or self.first_game_index < 1 or self.last_game_index < self.first_game_index:
            raise ValueError("invalid shard assignment")
        expected = self.last_game_index - self.first_game_index + 1
        if len(self.seeds) != expected or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("invalid shard seed assignment")


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
    evaluator_snapshot_id: str
    evaluator_snapshot_sha256: str
    learning_plan_sha256: str | None
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
        if self.schema_version != "phase-b-run-manifest-v2" or self.run_mode not in {"STANDARD", "EXPLORATORY", "AUDIT_ONLY", "VERIFICATION"}:
            raise ValueError("unsupported run manifest")
        if not self.evaluator_snapshot_id or len(self.evaluator_snapshot_sha256) != 64:
            raise ValueError("run manifest requires a content-addressed evaluator")
        if self.learning_plan_sha256 is not None and len(self.learning_plan_sha256) != 64:
            raise ValueError("invalid learning-plan digest")
        if self.dirty_tree or self.worker_count < 1 or self.test_evidence.commit != self.git_commit:
            raise ValueError("authoritative run manifest is not clean or same-commit")
        if self.evidence_classification != "CLEAN_ENGINE_PRODUCTION_PATH" or self.legacy_evidence_used or self.pilot_authorized:
            raise ValueError("run manifest violates Phase B evidence controls")
        if not self.command_line or self.run_id != manifest_run_id(self, include_run_id=False):
            raise ValueError("run manifest command or content-bound ID is invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def manifest_run_id(manifest: RunManifest | Mapping[str, Any], *, include_run_id: bool = True) -> str:
    body = asdict(manifest) if isinstance(manifest, RunManifest) else dict(manifest)
    if not include_run_id:
        body.pop("run_id", None)
    return f"phase-b-{hashlib.sha256(_canonical(body)).hexdigest()[:24]}"


def build_manifest(*, run_mode: str, config_path: Path, evaluator_path: Path, evaluator_snapshot_id: str, seed_path: Path, learning_plan_path: Path | None = None, command_line: Sequence[str], started_at: str, ended_at: str, worker_count: int, assignment: SeedAssignment, test_evidence: TestEvidence, root: Path = ROOT) -> RunManifest:
    commit = _git(root, "rev-parse", "HEAD")
    declared_id, declared_sha = _declared_evaluator_identity(evaluator_path)
    if evaluator_snapshot_id != declared_id:
        raise ValueError("evaluator identity does not match selected artifact")
    data: dict[str, Any] = {
        "schema_version": "phase-b-run-manifest-v2", "run_id": "", "run_mode": run_mode,
        "git_commit": commit, "dirty_tree": bool(_git(root, "status", "--porcelain")),
        "python_version": platform.python_version(), "dependency_lock_sha256": _sha256(root / "uv.lock"),
        "rules_source_sha256": _sha256(root / "docs/source/MagicCompRules_2026-06-19.txt"),
        "oracle_snapshot_sha256": _sha256(root / "docs/source/oracle/snapshot_v1.json"),
        "decklist_sha256": _sha256(root / "docs/source/decklist.txt"), "config_sha256": _sha256(config_path),
        "evaluator_snapshot_id": evaluator_snapshot_id, "evaluator_snapshot_sha256": declared_sha,
        "learning_plan_sha256": _declared_learning_plan_sha256(learning_plan_path) if learning_plan_path else None,
        "seed_list_sha256": _sha256(seed_path), "command_line": tuple(str(v) for v in command_line),
        "started_at": started_at, "ended_at": ended_at, "worker_count": worker_count,
        "assignment": assignment, "test_evidence": test_evidence,
        "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH", "legacy_evidence_used": False, "pilot_authorized": False,
    }
    data["run_id"] = manifest_run_id(data, include_run_id=False)
    return RunManifest(**data)


def write_immutable_run(root: Path, manifest: RunManifest, raw_records: Sequence[Mapping[str, Any]]) -> Path:
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
    invariant_fields = ("run_mode", "git_commit", "python_version", "dependency_lock_sha256", "rules_source_sha256", "oracle_snapshot_sha256", "decklist_sha256", "config_sha256", "evaluator_snapshot_id", "evaluator_snapshot_sha256", "learning_plan_sha256", "seed_list_sha256", "evidence_classification", "legacy_evidence_used", "pilot_authorized")
    first = manifests[0]
    for manifest in manifests[1:]:
        mixed = [field for field in invariant_fields if getattr(manifest, field) != getattr(first, field)]
        if mixed:
            raise ValueError(f"aggregation rejects mixed manifest fields: {mixed}")
        if manifest.test_evidence != first.test_evidence:
            raise ValueError("aggregation rejects mixed same-commit test evidence")
    assignments = sorted((m.assignment for m in manifests), key=lambda a: a.first_game_index)
    expected_index = 1
    seeds: list[int] = []
    shard_indexes: set[int] = set()
    for assignment in assignments:
        if assignment.shard_index in shard_indexes or assignment.first_game_index != expected_index:
            raise ValueError("aggregation rejects duplicate shards, gaps, or overlaps")
        shard_indexes.add(assignment.shard_index)
        expected_index = assignment.last_game_index + 1
        seeds.extend(assignment.seeds)
    if len(seeds) != len(set(seeds)):
        raise ValueError("aggregation rejects duplicate seeds")
    return {"schema_version": "phase-b-aggregation-validation-v1", "status": "PASS", "git_commit": first.git_commit, "run_mode": first.run_mode, "shard_count": len(manifests), "game_count": len(seeds), "first_game_index": 1, "last_game_index": expected_index - 1, "seed_sha256": hashlib.sha256(_canonical(seeds)).hexdigest(), "worker_counts": sorted({m.worker_count for m in manifests})}
