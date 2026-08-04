from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mtg_policy import load_policy_matrix
from mtg_runs.phase_c import (
    CONFIRMATION_TOKEN,
    CURRENT_ENGINE_BLOCKERS,
    DEFAULT_APPROVAL,
    DEFAULT_CONFIG,
    DEFAULT_WORKFLOW,
    PhaseCControlError,
    build_pilot_seed_plan,
    dry_run_phase_c,
    load_phase_c_config,
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
    assert report.status == "LOCKED_ENGINE_INCOMPLETE"
    assert report.execution_allowed is False
    assert report.authorization_status == "LOCKED_PENDING_OWNER_APPROVAL"
    assert report.game_results_created == 0
    assert report.full_study_execution_allowed is False
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
