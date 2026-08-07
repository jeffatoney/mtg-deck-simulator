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
    yield
    for path in sorted(tmp_path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        try:
            path.chmod(0o755 if path.is_dir() else 0o644)
        except FileNotFoundError:
            pass
    tmp_path.chmod(0o755)


def _measurement(
    index: int,
    seed: int,
    mode: str,
    *,
    access8: bool = False,
    pair_id: str | None = None,
    paired_standard_game_index: int | None = None,
    search_seed: int | None = None,
    initial_hash: str | None = None,
) -> GameMeasurement:
    checkpoint = {5: False, 6: False, 8: access8, 10: access8}
    failures = {
        turn: (() if checkpoint[turn] else ("other_documented_cause",)) for turn in (5, 6, 8, 10)
    }
    primary = {turn: (None if not labels else labels[0]) for turn, labels in failures.items()}
    return GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=index,
        seed=seed,
        mode=mode,
        policy_config_id="anchor_balanced",
        opening_hands=(OpeningHandMeasurement(1, 7, ("Island",) * 7, True),),
        kept_at=7,
        checkpoint_table_win_access=checkpoint,
        failure_labels=failures,
        primary_failure=primary,
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
        extra={
            "environment_seed": seed,
            "environment_initial_state_hash": initial_hash or f"{seed + 2:064x}"[-64:],
            "search_seed": search_seed,
            "pair_id": pair_id,
            "paired_standard_game_index": paired_standard_game_index,
        },
    )


def _write_shard(
    root: Path,
    *,
    mode: str,
    shard_index: int,
    shard_count: int,
    first_index: int,
    seeds: tuple[int, ...],
    pair_ids: tuple[str | None, ...] | None = None,
    paired_standard_indexes: tuple[int | None, ...] | None = None,
    search_seeds: tuple[int | None, ...] | None = None,
    access8: tuple[bool, ...] | None = None,
) -> Path:
    pair_ids = pair_ids or (None,) * len(seeds)
    paired_standard_indexes = paired_standard_indexes or (None,) * len(seeds)
    search_seeds = search_seeds or (None,) * len(seeds)
    access8 = access8 or (False,) * len(seeds)
    initial_hashes = tuple(f"{seed + 2:064x}"[-64:] for seed in seeds)
    measurements = tuple(
        _measurement(
            first_index + offset,
            seed,
            mode,
            access8=access8[offset],
            pair_id=pair_ids[offset],
            paired_standard_game_index=paired_standard_indexes[offset],
            search_seed=search_seeds[offset],
            initial_hash=initial_hashes[offset],
        )
        for offset, seed in enumerate(seeds)
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
            "environment_initial_state_hash": initial_hashes[offset],
            "search_seed": search_seeds[offset],
            "pair_id": pair_ids[offset],
            "paired_standard_game_index": paired_standard_indexes[offset],
            "replay_digest": replay["digest"],
            "final_state_hash": f"{seed + 1:064x}"[-64:],
            "terminal_status": "ACTIVE",
        }
        for offset, (seed, replay) in enumerate(zip(seeds, replays, strict=True))
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
        pair_ids=pair_ids,
        paired_standard_game_indexes=paired_standard_indexes,
        search_seeds=search_seeds,
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
    return write_phase_c_shard(root, manifest, technical, games, replays, measurements, summary)


def test_manifest_rejects_git_oid_and_sha256_domain_mixing(tmp_path: Path) -> None:
    measurement = _measurement(1, 11, "STANDARD")
    replay = {"digest": "a" * 64}
    technical = {
        "seed": 11,
        "pair_id": None,
        "paired_standard_game_index": None,
        "search_seed": None,
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
            pair_ids=(None,),
            paired_standard_game_indexes=(None,),
            search_seeds=(None,),
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
    root = tmp_path / "technical"
    root.mkdir()
    shard = _write_shard(
        root, mode="STANDARD", shard_index=0, shard_count=1, first_index=1, seeds=(11,)
    )
    technical_path = shard / "technical-games.jsonl"
    technical = json.loads(technical_path.read_text().strip())
    technical["final_state_hash"] = "f" * 64
    technical_path.chmod(0o644)
    technical_path.write_text(json.dumps(technical) + "\n")
    with pytest.raises(ValueError, match="technical-game digest differs"):
        load_phase_c_shard(shard)


def test_exact_500_200_paired_aggregation_is_deterministic_and_reports_real_pairs(
    tmp_path: Path,
) -> None:
    standard = tuple(range(1, 501))
    paired_indexes = tuple(shard * 50 + offset + 1 for shard in range(10) for offset in range(20))
    exploratory = tuple(standard[index - 1] for index in paired_indexes)
    search = tuple(range(10_001, 10_201))
    pair_ids = tuple(f"{index:024x}"[-24:] for index in range(1, 201))
    pair_ordinal_by_standard = {
        standard_index: ordinal for ordinal, standard_index in enumerate(paired_indexes)
    }
    shard_dirs: list[Path] = []
    for shard_index in range(10):
        standard_start = shard_index * 50
        standard_indexes = tuple(range(standard_start + 1, standard_start + 51))
        standard_pair_ids = tuple(
            pair_ids[pair_ordinal_by_standard[index]] if index in pair_ordinal_by_standard else None
            for index in standard_indexes
        )
        standard_pair_indexes = tuple(
            index if index in pair_ordinal_by_standard else None for index in standard_indexes
        )
        standard_access = tuple(
            (pair_ordinal_by_standard[index] % 4 in {0, 1})
            if index in pair_ordinal_by_standard
            else False
            for index in standard_indexes
        )
        shard_dirs.append(
            _write_shard(
                tmp_path,
                mode="STANDARD",
                shard_index=shard_index,
                shard_count=10,
                first_index=standard_start + 1,
                seeds=standard[standard_start : standard_start + 50],
                pair_ids=standard_pair_ids,
                paired_standard_indexes=standard_pair_indexes,
                search_seeds=(None,) * 50,
                access8=standard_access,
            )
        )
        exploratory_start = shard_index * 20
        ordinals = range(exploratory_start, exploratory_start + 20)
        shard_dirs.append(
            _write_shard(
                tmp_path,
                mode="EXPLORATORY",
                shard_index=shard_index,
                shard_count=10,
                first_index=exploratory_start + 1,
                seeds=exploratory[exploratory_start : exploratory_start + 20],
                pair_ids=pair_ids[exploratory_start : exploratory_start + 20],
                paired_standard_indexes=paired_indexes[exploratory_start : exploratory_start + 20],
                search_seeds=search[exploratory_start : exploratory_start + 20],
                access8=tuple(ordinal % 4 in {0, 2} for ordinal in ordinals),
            )
        )
    first, standard_summary, exploratory_summary, paired = validate_phase_c_aggregate(
        shard_dirs,
        expected_standard_seeds=standard,
        expected_exploratory_seeds=exploratory,
        expected_exploratory_search_seeds=search,
        expected_pair_ids=pair_ids,
        expected_paired_standard_game_indexes=paired_indexes,
        expected_standard_shards=10,
        expected_exploratory_shards=10,
    )
    second, _, _, paired_second = validate_phase_c_aggregate(
        tuple(reversed(shard_dirs)),
        expected_standard_seeds=standard,
        expected_exploratory_seeds=exploratory,
        expected_exploratory_search_seeds=search,
        expected_pair_ids=pair_ids,
        expected_paired_standard_game_indexes=paired_indexes,
        expected_standard_shards=10,
        expected_exploratory_shards=10,
    )
    assert first == second
    assert paired == paired_second
    assert standard_summary["game_denominator"] == 500
    assert exploratory_summary["game_denominator"] == 200
    assert paired["pair_count"] == 200
    assert paired["both_access"] == 50
    assert paired["standard_only_access"] == 50
    assert paired["exploratory_only_access"] == 50
    assert paired["neither_access"] == 50
    assert paired["paired_access_rate_difference"] == 0.0
    assert paired["mcnemar_exact_two_sided_p_value"] == 1.0
    assert paired["paired_access_rate_difference_ci"]["lower"] <= 0.0
    assert paired["paired_access_rate_difference_ci"]["upper"] >= 0.0


def test_pairing_tamper_fails_closed(tmp_path: Path) -> None:
    pair_id = "a" * 24
    standard = _write_shard(
        tmp_path,
        mode="STANDARD",
        shard_index=0,
        shard_count=1,
        first_index=1,
        seeds=(11,),
        pair_ids=(pair_id,),
        paired_standard_indexes=(1,),
        search_seeds=(None,),
    )
    measurement_path = standard / "measurements.jsonl"
    payload = json.loads(measurement_path.read_text().strip())
    payload["extra"]["pair_id"] = "b" * 24
    measurement_path.chmod(0o644)
    measurement_path.write_text(json.dumps(payload) + "\n")
    with pytest.raises(ValueError, match="pair ID linkage"):
        load_phase_c_shard(standard)
