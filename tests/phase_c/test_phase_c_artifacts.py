from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from mtg_measure import GameMeasurement, OpeningHandMeasurement, aggregate_measurements
from mtg_runs.phase_c_artifacts import (
    build_shard_manifest,
    load_phase_c_shard,
    make_game_artifact,
    validate_phase_c_aggregate,
    write_phase_c_shard,
)


@pytest.fixture(autouse=True)
def _restore_artifact_permissions(tmp_path: Path):
    """Return immutable fixture artifacts to pytest-cleanable permissions."""
    yield
    for path in sorted(tmp_path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        try:
            path.chmod(0o755 if path.is_dir() else 0o644)
        except FileNotFoundError:
            pass
    tmp_path.chmod(0o755)


def _measurement(index: int, seed: int, mode: str) -> GameMeasurement:
    return GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=index,
        seed=seed,
        mode=mode,
        policy_config_id="anchor_balanced",
        opening_hands=(OpeningHandMeasurement(1, 7, ("Island",) * 7, True),),
        kept_at=7,
        checkpoint_table_win_access={5: False, 6: False, 8: False, 10: False},
        failure_labels={
            5: ("other_documented_cause",),
            6: ("other_documented_cause",),
            8: ("other_documented_cause",),
            10: ("other_documented_cause",),
        },
        primary_failure={
            5: "other_documented_cause",
            6: "other_documented_cause",
            8: "other_documented_cause",
            10: "other_documented_cause",
        },
        combo_records=(),
        earliest_legal_attempt_turn=None,
        actual_first_attempt_turn=None,
        attempt_package=None,
        attempt_timing=None,
        usable_protection_count=0,
        protection_in_hand_not_payable=False,
        protection_category_mismatch=False,
        independent_second_line_available=False,
        card_records=(),
    )


def _write_shard(
    root: Path,
    *,
    mode: str,
    shard_index: int,
    shard_count: int,
    first_index: int,
    seeds: tuple[int, ...],
) -> Path:
    measurements = tuple(
        _measurement(first_index + offset, seed, mode) for offset, seed in enumerate(seeds)
    )
    replays = tuple(
        {"schema_version": "test-replay-v1", "seed": seed, "digest": f"{seed:064x}"[-64:]}
        for seed in seeds
    )
    technical = tuple(
        {
            "schema_version": "phase-c-technical-game-v2",
            "mode": mode,
            "seed": seed,
            "replay_digest": replay["digest"],
            "final_state_hash": f"{seed + 1:064x}"[-64:],
            "terminal_status": "ACTIVE",
        }
        for seed, replay in zip(seeds, replays, strict=True)
    )
    games = tuple(
        make_game_artifact(
            mode=mode,
            game_index=measurement.game_index,
            seed=seed,
            technical_game=game,
            replay=replay,
            measurement=measurement,
        )
        for seed, game, replay, measurement in zip(
            seeds, technical, replays, measurements, strict=True
        )
    )
    summary = asdict(aggregate_measurements(measurements))
    manifest = build_shard_manifest(
        mode=mode,
        shard_index=shard_index,
        shard_count=shard_count,
        first_game_index=first_index,
        seeds=seeds,
        implementation_commit="1" * 40,
        implementation_tree="2" * 40,
        activation_commit="3" * 40,
        locked_config_sha256="4" * 64,
        workflow_sha256="5" * 64,
        approval_record_sha256="6" * 64,
        policy_config_id="anchor_balanced",
        policy_config_sha256="7" * 64,
        evaluator_snapshot_id="contextual_combo_v1",
        evaluator_snapshot_sha256="8" * 64,
        learning_plan_sha256="9" * 64,
        technical_games=technical,
        game_records=games,
        replays=replays,
        measurements=measurements,
        summary=summary,
    )
    return write_phase_c_shard(
        root, manifest, technical, games, replays, measurements, summary
    )


def test_manifest_rejects_git_oid_and_sha256_domain_mixing(tmp_path: Path) -> None:
    measurement = _measurement(1, 11, "STANDARD")
    replay = {"digest": "a" * 64}
    technical = {
        "replay_digest": "a" * 64,
        "final_state_hash": "b" * 64,
        "terminal_status": "ACTIVE",
    }
    game = make_game_artifact(
        mode="STANDARD",
        game_index=1,
        seed=11,
        technical_game=technical,
        replay=replay,
        measurement=measurement,
    )
    summary = asdict(aggregate_measurements((measurement,)))
    with pytest.raises(ValueError, match="40-character Git object ID"):
        build_shard_manifest(
            mode="STANDARD",
            shard_index=0,
            shard_count=1,
            first_game_index=1,
            seeds=(11,),
            implementation_commit="1" * 64,
            implementation_tree="2" * 40,
            activation_commit="3" * 40,
            locked_config_sha256="4" * 64,
            workflow_sha256="5" * 64,
            approval_record_sha256="6" * 64,
            policy_config_id="anchor_balanced",
            policy_config_sha256="7" * 64,
            evaluator_snapshot_id="contextual_combo_v1",
            evaluator_snapshot_sha256="8" * 64,
            learning_plan_sha256="9" * 64,
            technical_games=(technical,),
            game_records=(game,),
            replays=(replay,),
            measurements=(measurement,),
            summary=summary,
        )


def test_shard_cross_file_tampering_fails_closed(tmp_path: Path) -> None:
    def one(label: str) -> Path:
        root = tmp_path / label
        root.mkdir()
        return _write_shard(
            root,
            mode="STANDARD",
            shard_index=0,
            shard_count=1,
            first_index=1,
            seeds=(11,),
        )

    technical_dir = one("technical")
    technical_path = technical_dir / "technical-games.jsonl"
    technical = json.loads(technical_path.read_text().strip())
    technical["final_state_hash"] = "f" * 64
    technical_path.chmod(0o644)
    technical_path.write_text(json.dumps(technical) + "\n")
    with pytest.raises(ValueError, match="technical-game digest differs"):
        load_phase_c_shard(technical_dir)

    replay_dir = one("replay")
    replay_path = replay_dir / "replays/game-0001.json"
    replay = json.loads(replay_path.read_text())
    replay["digest"] = "e" * 64
    replay_path.chmod(0o644)
    replay_path.write_text(json.dumps(replay) + "\n")
    with pytest.raises(ValueError, match="replay file digest differs"):
        load_phase_c_shard(replay_dir)

    measurement_dir = one("measurement")
    measurement_path = measurement_dir / "measurements.jsonl"
    measurement = json.loads(measurement_path.read_text().strip())
    measurement["usable_protection_count"] = 99
    measurement_path.chmod(0o644)
    measurement_path.write_text(json.dumps(measurement) + "\n")
    with pytest.raises(ValueError, match="measurement digest differs"):
        load_phase_c_shard(measurement_dir)

    summary_dir = one("summary")
    summary_path = summary_dir / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["game_denominator"] = 999
    summary_path.chmod(0o644)
    summary_path.write_text(json.dumps(summary) + "\n")
    with pytest.raises(ValueError, match="summary digest mismatch"):
        load_phase_c_shard(summary_dir)


def test_exact_500_200_shard_aggregation_is_deterministic_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    standard = tuple(range(1, 501))
    exploratory = tuple(range(1001, 1201))
    shard_dirs: list[Path] = []
    for index in range(10):
        shard_dirs.append(
            _write_shard(
                tmp_path,
                mode="STANDARD",
                shard_index=index,
                shard_count=10,
                first_index=index * 50 + 1,
                seeds=standard[index * 50 : (index + 1) * 50],
            )
        )
        shard_dirs.append(
            _write_shard(
                tmp_path,
                mode="EXPLORATORY",
                shard_index=index,
                shard_count=10,
                first_index=index * 20 + 1,
                seeds=exploratory[index * 20 : (index + 1) * 20],
            )
        )
    first, standard_summary, exploratory_summary = validate_phase_c_aggregate(
        shard_dirs,
        expected_standard_seeds=standard,
        expected_exploratory_seeds=exploratory,
        expected_standard_shards=10,
        expected_exploratory_shards=10,
    )
    second, _, _ = validate_phase_c_aggregate(
        tuple(reversed(shard_dirs)),
        expected_standard_seeds=standard,
        expected_exploratory_seeds=exploratory,
        expected_standard_shards=10,
        expected_exploratory_shards=10,
    )
    assert first == second
    assert standard_summary["game_denominator"] == 500
    assert exploratory_summary["game_denominator"] == 200

    manifest_path = shard_dirs[0] / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    payload["implementation_tree"] = "f" * 64
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="40-character Git object ID"):
        validate_phase_c_aggregate(
            shard_dirs,
            expected_standard_seeds=standard,
            expected_exploratory_seeds=exploratory,
            expected_standard_shards=10,
            expected_exploratory_shards=10,
        )
