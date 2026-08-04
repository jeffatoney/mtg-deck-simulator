from __future__ import annotations
from pathlib import Path
import pytest
from mtg_runs import (
    RunManifest,
    SeedAssignment,
    TestEvidence as Evidence,
    validate_aggregation,
    write_immutable_run,
)
from mtg_runs.manifests import manifest_run_id


def evidence() -> Evidence:
    return Evidence("a" * 40, "pytest -q", "PASS", 10, 0, 0, 0, "b" * 64)


def manifest(
    shard: int,
    first: int,
    seeds: tuple[int, ...],
    *,
    config: str = "c" * 64,
    evaluator: str = "3" * 64,
) -> RunManifest:
    assignment = SeedAssignment(shard, first, first + len(seeds) - 1, seeds)
    data = {
        "schema_version": "phase-b-run-manifest-v2",
        "run_id": "",
        "run_mode": "VERIFICATION",
        "git_commit": "a" * 40,
        "dirty_tree": False,
        "python_version": "3.12.13",
        "dependency_lock_sha256": "d" * 64,
        "rules_source_sha256": "e" * 64,
        "oracle_snapshot_sha256": "f" * 64,
        "decklist_sha256": "1" * 64,
        "config_sha256": config,
        "evaluator_snapshot_id": "contextual_combo_v1",
        "evaluator_snapshot_sha256": evaluator,
        "learning_plan_sha256": None,
        "seed_list_sha256": "2" * 64,
        "command_line": ("mtg-engine", "verify-phase-b"),
        "started_at": "2026-08-01T09:00:00Z",
        "ended_at": "2026-08-01T09:01:00Z",
        "worker_count": 1,
        "assignment": assignment,
        "test_evidence": evidence(),
        "evidence_classification": "CLEAN_ENGINE_PRODUCTION_PATH",
        "legacy_evidence_used": False,
        "pilot_authorized": False,
    }
    provisional = RunManifest.__new__(RunManifest)
    for key, value in data.items():
        object.__setattr__(provisional, key, value)
    data["run_id"] = manifest_run_id(provisional, include_run_id=False)
    return RunManifest(**data)


def test_aggregation_accepts_contiguous_shards_and_rejects_mixed_duplicate_or_gapped_inputs() -> (
    None
):
    first = manifest(0, 1, (11, 12))
    second = manifest(1, 3, (13, 14))
    result = validate_aggregation((second, first))
    assert result["status"] == "PASS" and result["game_count"] == 4
    with pytest.raises(ValueError, match="mixed manifest fields"):
        validate_aggregation((first, manifest(1, 3, (13, 14), config="9" * 64)))
    with pytest.raises(ValueError, match="duplicate shards, gaps, or overlaps"):
        validate_aggregation((first, manifest(1, 4, (13, 14))))
    with pytest.raises(ValueError, match="duplicate seeds"):
        validate_aggregation((first, manifest(1, 3, (12, 14))))


def test_run_directory_is_content_addressed_and_append_only(tmp_path: Path) -> None:
    value = manifest(0, 1, (11,))
    path = write_immutable_run(tmp_path, value, ({"game_index": 1, "seed": 11},))
    assert path.name == value.run_id and (path / "manifest.json").is_file()
    with pytest.raises(FileExistsError):
        write_immutable_run(tmp_path, value, ({"game_index": 1, "seed": 11},))


def test_aggregation_rejects_mixed_evaluator_snapshots() -> None:
    with pytest.raises(ValueError, match="mixed manifest fields"):
        validate_aggregation(
            (manifest(0, 1, (11, 12)), manifest(1, 3, (13, 14), evaluator="4" * 64))
        )
