from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_current_handoff.py"
SPEC = importlib.util.spec_from_file_location("generate_current_handoff", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _config(*, pilot_allowed: bool = False, full_allowed: bool = False) -> dict[str, object]:
    return {
        "authorization": {
            "execution_allowed": pilot_allowed,
            "status": "AUTHORIZED" if pilot_allowed else "LOCKED_PENDING_OWNER_APPROVAL",
        },
        "full_study": {
            "execution_allowed": full_allowed,
            "authorization_status": (
                "AUTHORIZED" if full_allowed else "LOCKED_PENDING_POST_PILOT_REVIEW"
            ),
            "standard_games": 20_000,
            "exploratory_games": 5_000,
        },
        "pilot": {
            "standard_games": 500,
            "exploratory_games": 200,
            "standard_shards": 10,
            "exploratory_shards": 10,
        },
        "game_model": {
            "opponent_interaction_modeled": False,
            "blocking_modeled": False,
            "opponent_wins_modeled": False,
            "end_after_controlled_turn": 10,
        },
        "paired_analysis": {
            "paired_game_count": 200,
            "primary_outcome": "LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_BY_TURN_8",
            "secondary_outcome": "EARLIEST_LEGAL_DETERMINISTIC_TABLE_WIN_ACCESS_TURN",
        },
    }


def test_governance_snapshot_reads_frozen_no_opponent_model() -> None:
    snapshot = MODULE._governance_snapshot(_config(), {"status": "PENDING_OWNER_APPROVAL"})

    assert snapshot["pilot"]["execution_allowed"] is False
    assert snapshot["study_model"]["opponent_interaction_modeled"] is False
    assert snapshot["study_model"]["paired_game_count"] == 200


def test_governance_snapshot_fails_closed_on_unapproved_execution() -> None:
    with pytest.raises(MODULE.HandoffError, match="without an APPROVED approval record"):
        MODULE._governance_snapshot(
            _config(pilot_allowed=True),
            {"status": "PENDING_OWNER_APPROVAL"},
        )


def test_governance_snapshot_rejects_full_study_when_pilot_is_locked() -> None:
    with pytest.raises(MODULE.HandoffError, match="full study is allowed"):
        MODULE._governance_snapshot(
            _config(full_allowed=True),
            {"status": "PENDING_OWNER_APPROVAL"},
        )
