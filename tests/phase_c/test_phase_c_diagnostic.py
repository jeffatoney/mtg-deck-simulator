from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mtg_runs import phase_c_diagnostic as diagnostic
from mtg_runs.phase_c import PhaseCControlError

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/phase-c-diagnostic.yml"
SOURCE = ROOT / "src/mtg_runs/phase_c_diagnostic.py"


def test_diagnostic_workflow_is_non_authorized_and_does_not_fail_fast() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "fail-fast: false" in text
    assert "confirmation:" not in text
    assert "activation_commit:" not in text
    assert "AUTHORIZE_PHASE_C_500_STANDARD_200_EXPLORATORY" not in text
    assert "phase-c-pilot \\" not in text
    assert "python -m mtg_runs.phase_c_diagnostic shard" in text
    assert "python -m mtg_runs.phase_c_diagnostic aggregate" in text
    assert "if: always()" in text


def test_diagnostic_workflow_requires_fresh_production_path_and_forbids_pilot_roots() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    assert "validate_fresh_replay=True" in source
    assert "policy_actions=True" in source
    assert "through_turn=10" in source
    assert source.count("run_phase_c_game_execution(") == 1
    assert "artifacts/phase-c-shards" in text
    assert "artifacts/phase-c-pilot" in text
    assert "pilot_measurement_artifacts_created" in source
    assert "phase_c_artifacts" not in source
    assert "aggregate_measurements" not in source
    assert "write_phase_c_shard" not in source
    assert "write_phase_c_aggregate" not in source


def test_non_authorized_config_guard_rejects_authorized_state() -> None:
    locked = SimpleNamespace(
        execution_allowed=False,
        authorization_status="LOCKED_PENDING_OWNER_APPROVAL",
    )
    diagnostic._require_non_authorized_config(locked)

    authorized = SimpleNamespace(execution_allowed=True, authorization_status="AUTHORIZED")
    with pytest.raises(PhaseCControlError, match="refuses an authorized"):
        diagnostic._require_non_authorized_config(authorized)


def test_distinct_errors_group_exact_type_and_reason() -> None:
    records = [
        diagnostic.DiagnosticGameRecord(
            mode="STANDARD",
            game_index=1,
            seed=11,
            pair_id=None,
            paired_standard_game_index=None,
            search_seed=None,
            status="FAIL",
            error_type="IllegalAction",
            reason="explicit trigger target choice is required",
            error_signature="a" * 64,
        ),
        diagnostic.DiagnosticGameRecord(
            mode="STANDARD",
            game_index=2,
            seed=12,
            pair_id=None,
            paired_standard_game_index=None,
            search_seed=None,
            status="FAIL",
            error_type="IllegalAction",
            reason="explicit trigger target choice is required",
            error_signature="a" * 64,
        ),
        diagnostic.DiagnosticGameRecord(
            mode="EXPLORATORY",
            game_index=1,
            seed=11,
            pair_id="pair-1",
            paired_standard_game_index=1,
            search_seed=99,
            status="FAIL",
            error_type="UnsupportedCapability",
            reason="different failure",
            error_signature="b" * 64,
        ),
    ]
    errors = diagnostic._distinct_errors(records)
    assert len(errors) == 2
    assert errors[0]["count"] == 2
    assert errors[1]["count"] == 1


def test_diagnostic_shard_discards_measurement_and_keeps_running_after_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = SimpleNamespace(
        execution_allowed=False,
        authorization_status="LOCKED_PENDING_OWNER_APPROVAL",
        policy_config_id="anchor_balanced",
        sha256="config-sha",
    )
    seeds = SimpleNamespace(
        standard_sha256="standard-sha",
        exploratory_sha256="exploratory-sha",
        exploratory_search_sha256="search-sha",
        pair_assignment_sha256="pair-sha",
    )
    assignment = SimpleNamespace(
        seeds=(101, 102),
        search_seeds=(None, None),
        pair_ids=(None, None),
        paired_standard_game_indexes=(None, None),
        first_game_index=1,
        last_game_index=2,
        shard_index=0,
        shard_count=10,
    )
    technical = SimpleNamespace(
        pilot_result=False,
        authorized_pilot_result=False,
        controlled_turns_completed=10,
        terminal_status="TURN_LIMIT",
        command_count=123,
        replay_digest="replay",
        final_state_hash="state",
        fresh_replay_state_hash="state",
    )
    fake_execution = SimpleNamespace(
        technical_game=technical,
        measurement=SimpleNamespace(secret_pilot_measurement="must-not-serialize"),
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(diagnostic, "load_phase_c_config", lambda _path: config)
    monkeypatch.setattr(diagnostic, "build_pilot_seed_plan", lambda _config: seeds)
    monkeypatch.setattr(
        diagnostic,
        "build_pilot_shard_assignment",
        lambda _config, _seeds, *, mode, shard_index: assignment,
    )

    def fake_run(**kwargs: object) -> object:
        calls.append(dict(kwargs))
        if kwargs["seed"] == 101:
            raise RuntimeError("first failure")
        return fake_execution

    monkeypatch.setattr(diagnostic, "run_phase_c_game_execution", fake_run)
    report = diagnostic.run_diagnostic_shard(
        mode="STANDARD",
        shard_index=0,
        output_root=tmp_path / "diagnostic",
        root=tmp_path,
    )

    assert len(calls) == 2
    assert all(call["validate_fresh_replay"] is True for call in calls)
    assert all(call["policy_actions"] is True for call in calls)
    assert all(call["through_turn"] == 10 for call in calls)
    assert report["game_count"] == 2
    assert report["pass_count"] == 1
    assert report["fail_count"] == 1
    assert report["pilot_measurement_artifacts_created"] == 0
    serialized = str(report)
    assert "secret_pilot_measurement" not in serialized
    assert "first failure" in serialized
