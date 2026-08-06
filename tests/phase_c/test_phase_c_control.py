from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mtg_policy import load_policy_matrix
from mtg_runs.phase_c import (
    CONFIRMATION_TOKEN,
    CURRENT_ENGINE_BLOCKERS,
    PILOT_PRODUCTION_DECISION_LAYER_DEPTH,
    aggregate_phase_c_shard_fixtures,
    DEFAULT_APPROVAL,
    DEFAULT_CONFIG,
    DEFAULT_WORKFLOW,
    PhaseCControlError,
    build_phase_c_shard_fixture,
    build_pilot_seed_plan,
    dry_run_phase_c,
    load_phase_c_config,
    run_phase_c_technical_fixture,
    validate_execution_authorization,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _config_payload() -> dict[str, object]:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def test_locked_config_binds_exact_policy_counts_and_information_boundary() -> None:
    config = load_phase_c_config()
    policy = next(
        bundle
        for bundle in load_policy_matrix()
        if bundle.policy_config_id == config.policy_config_id
    )
    assert config.execution_allowed is False
    assert config.authorization_status == "LOCKED_PENDING_OWNER_APPROVAL"
    assert (config.standard_games, config.exploratory_games) == (500, 200)
    assert policy.config_hash == config.policy_config_hash
    assert policy.evaluator_snapshot_id == config.evaluator_snapshot_id
    assert policy.evaluator_snapshot_sha256 == config.evaluator_snapshot_sha256
    assert policy.value("learning_plan_sha256") == config.learning_plan_sha256


def test_seed_plan_is_deterministic_exact_and_disjoint() -> None:
    config = load_phase_c_config()
    first = build_pilot_seed_plan(config)
    second = build_pilot_seed_plan(config)
    assert first == second
    assert len(first.standard) == 500
    assert len(first.exploratory) == 200
    assert not set(first.standard).intersection(first.exploratory)
    assert first.standard_sha256 != first.exploratory_sha256


def test_dry_run_creates_no_game_result_and_discloses_engine_blockers() -> None:
    report = dry_run_phase_c()
    assert report.status == "READY_FOR_OWNER_REVIEW"
    assert report.execution_allowed is False
    assert report.authorization_status == "LOCKED_PENDING_OWNER_APPROVAL"
    assert report.game_results_created == 0
    assert report.full_study_execution_allowed is False
    assert report.exploratory_production_decision_layer_depth == 1
    assert report.technical_fixture_status == "PASS"
    assert report.readiness_blockers == CURRENT_ENGINE_BLOCKERS
    assert report.config_sha256 == hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
    assert (
        report.approval_record_sha256 == hashlib.sha256(DEFAULT_APPROVAL.read_bytes()).hexdigest()
    )
    assert report.workflow_sha256 == hashlib.sha256(DEFAULT_WORKFLOW.read_bytes()).hexdigest()


def test_config_rejects_count_future_information_and_full_study_drift(
    tmp_path: Path,
) -> None:
    payload = _config_payload()
    pilot = payload["pilot"]
    assert isinstance(pilot, dict)
    pilot["standard_games"] = 499
    with pytest.raises(PhaseCControlError, match="standard pilot count"):
        load_phase_c_config(_write_json(tmp_path / "wrong-count.json", payload))

    payload = _config_payload()
    search = payload["exploratory_search"]
    assert isinstance(search, dict)
    search["future_information_allowed"] = True
    with pytest.raises(PhaseCControlError, match="future information"):
        load_phase_c_config(_write_json(tmp_path / "future.json", payload))

    payload = _config_payload()
    full_study = payload["full_study"]
    assert isinstance(full_study, dict)
    full_study["execution_allowed"] = True
    with pytest.raises(PhaseCControlError, match="full-study flag"):
        load_phase_c_config(_write_json(tmp_path / "full-study.json", payload))


def test_execution_refuses_wrong_token_and_locked_configuration() -> None:
    common = {
        "authorized_commit": "0" * 40,
        "expected_config_sha256": hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
        "expected_workflow_sha256": hashlib.sha256(DEFAULT_WORKFLOW.read_bytes()).hexdigest(),
    }
    with pytest.raises(PhaseCControlError, match="confirmation token"):
        validate_execution_authorization(confirmation="WRONG", **common)
    with pytest.raises(PhaseCControlError, match="checked-out commit"):
        validate_execution_authorization(
            confirmation=CONFIRMATION_TOKEN,
            **common,
        )


def test_execution_checks_exact_counts_before_output() -> None:
    with pytest.raises(PhaseCControlError, match="exactly 500 standard"):
        validate_execution_authorization(
            confirmation=CONFIRMATION_TOKEN,
            authorized_commit="0" * 40,
            expected_config_sha256=hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
            expected_workflow_sha256=hashlib.sha256(DEFAULT_WORKFLOW.read_bytes()).hexdigest(),
            requested_standard_games=20_000,
            requested_exploratory_games=5_000,
        )


def test_manual_workflow_is_locked_and_uses_clean_verification_path() -> None:
    workflow = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert CONFIRMATION_TOKEN in workflow
    assert "phase-c-dry-run" in workflow and "phase-c-pilot" in workflow
    assert workflow.index("Phase A verifier") < workflow.index("uv run mtg-engine phase-c-pilot")
    assert workflow.index("Phase B verifier") < workflow.index("uv run mtg-engine phase-c-pilot")
    assert "check_phase_a_certification.py" in workflow
    assert "check_phase_b_certification.py" in workflow
    assert "mtg_sim" in workflow and "import mtg_sim" in workflow
    assert "20,000" not in workflow and "5000" not in workflow
    assert not (ROOT / ".github/workflows/pilot-simulation.yml").exists()


def test_phase_c_technical_fixture_reaches_turn_ten_and_replays_exactly() -> None:
    record = run_phase_c_technical_fixture(mode="STANDARD", seed=101)
    assert record["status"] == "PASS"
    assert record["pilot_result"] is False
    assert record["authorized_pilot_result"] is False
    assert record["controlled_turns_completed"] == 10
    assert record["mulligan_candidate_hand_sizes"] == [7, 7, 6, 5, 4]
    assert "TURN_1:DRAW" in record["commands"]
    assert "TURN_10:CLEANUP_REPEAT_UNTIL_STABLE" in record["commands"]
    assert record["replay_record"]["replay_digest"] == record["record_sha256"]
    assert record["replay_record"]["replay_validated_without_policy_rerun"] is True


def test_phase_c_technical_fixture_documents_combat_search_measurement_and_rollback() -> None:
    record = run_phase_c_technical_fixture(mode="EXPLORATORY", seed=202)
    assert record["exploratory_production_decision_layer_depth"] == (
        PILOT_PRODUCTION_DECISION_LAYER_DEPTH
    )
    assert "ACTION_BROKER_DECLARE_ATTACKER" in record["combat_events"]
    assert "PRODUCTION_EXECUTOR_ATTACKER_LEGAL" in record["combat_events"]
    assert record["look_select"]["revealed_candidate_count"] == 3
    assert record["look_select"]["policy_rerun_required_for_replay"] is False
    assert record["combo_access"]["cumulative_checkpoints"] == {
        "5": False,
        "6": False,
        "8": False,
        "10": False,
    }
    assert record["combo_access"]["false_positive_denial"] is True
    assert record["rollback"]["failed_action_restores_state_hash"] is True
    assert record["rollback"]["successful_action_appends_once"] is True
    assert record["cleanup_identity"]["bookkeeping_allocates_engine_identity_or_rng"] is False
    assert record["cleanup_identity"]["eight_card_cleanup_discard_replay_exact"] is True


def test_execution_rejects_non_git_oid_authorization_domain() -> None:
    with pytest.raises(PhaseCControlError, match="Git object ID"):
        validate_execution_authorization(
            confirmation=CONFIRMATION_TOKEN,
            authorized_commit="a" * 64,
            expected_config_sha256=hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest(),
            expected_workflow_sha256=hashlib.sha256(DEFAULT_WORKFLOW.read_bytes()).hexdigest(),
        )


def test_phase_c_shard_and_aggregation_fixture_rejects_mixed_or_duplicate_inputs() -> None:
    standard = build_phase_c_shard_fixture("STANDARD", (11, 12), shard_index=0)["manifest"]
    exploratory = build_phase_c_shard_fixture("EXPLORATORY", (13,), shard_index=1)["manifest"]
    aggregate = aggregate_phase_c_shard_fixtures((standard,))
    assert aggregate["schema_version"] == "phase-c-aggregate-manifest-v1"
    assert aggregate["pilot_result"] is False
    assert aggregate["authorized_pilot_result"] is False
    with pytest.raises(PhaseCControlError, match="mixed modes"):
        aggregate_phase_c_shard_fixtures((standard, exploratory))
    duplicate = build_phase_c_shard_fixture("STANDARD", (12,), shard_index=2)["manifest"]
    with pytest.raises(PhaseCControlError, match="duplicate seeds"):
        aggregate_phase_c_shard_fixtures((standard, duplicate))
