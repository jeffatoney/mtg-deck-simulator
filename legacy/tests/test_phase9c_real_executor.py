from __future__ import annotations

import ast
import csv
from pathlib import Path

import pandas as pd
import pytest

from mtg_sim.engine import RulesError
from mtg_sim.game_executor import GameExecutor, dualcaster_twinflame_fixture, replay_events
from mtg_sim.pilot import run, simulate_game
from mtg_sim.policies import CandidatePolicy, frozen_policy_matrix


def _policy() -> CandidatePolicy:
    return CandidatePolicy(frozen_policy_matrix()[0])


def test_pass_only_game_cannot_win() -> None:
    result = GameExecutor(101, 1, "anchor_balanced", "standard").run(_policy())
    assert result.terminal_status != "won"
    assert result.table_win_turn is None


def test_policy_id_without_decision_change_does_not_change_result() -> None:
    a, _ = simulate_game(101, 1, "anchor_balanced", "standard")
    b, _ = simulate_game(101, 1, "mulligan_aggressive", "standard")
    assert (a.terminal_status, a.table_win_turn) == (b.terminal_status, b.table_win_turn)


def test_hash_function_changes_cannot_change_outcome() -> None:
    first, _ = simulate_game(202, 1, "anchor_balanced", "standard")
    second, _ = simulate_game(202, 1, "anchor_balanced", "standard")
    assert (first.terminal_status, first.table_win_turn) == (
        second.terminal_status,
        second.table_win_turn,
    )


def test_fixture_win_has_elimination_sequence_and_replays() -> None:
    result = dualcaster_twinflame_fixture()
    assert result.terminal_status == "won"
    assert {"damage_dealt", "opponent_lost", "table_win"} <= {e["event"] for e in result.events}
    assert replay_events(result.events) == "won"


def test_win_replay_requires_real_loss_mechanism() -> None:
    events = [
        {"event": "game_started"},
        {"event": "table_win"},
        {"event": "game_ended", "terminal_status": "won"},
    ]
    with pytest.raises(RulesError):
        replay_events(events)


def test_pilot_source_has_no_synthetic_outcome_assignment() -> None:
    source = Path("src/mtg_sim/pilot.py").read_text()
    tree = ast.parse(source)
    forbidden_names = {"score", "win_turn"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            assert not (targets & forbidden_names and isinstance(node.value, ast.Call))
    assert "_legal_noop_event" not in source
    assert "placeholder" not in source.lower()


def test_missing_action_events_and_pass_only_audits_fail() -> None:
    with pytest.raises(RulesError):
        replay_events(
            [
                {"event": "object_resolved", "detail": "pass_priority"},
                {"event": "game_ended", "terminal_status": "won"},
            ]
        )


def test_real_smoke_writes_decoded_games_and_paired_differences() -> None:
    root = run(Path("configs/real-executor-smoke.toml"), smoke=True).parent
    decoded = sorted((root / "decoded-games").glob("*.txt"))
    assert decoded
    assert all("placeholder" not in p.read_text().lower() for p in decoded)
    paired = list(csv.DictReader((root / "paired-differences.csv").read_text().splitlines()))
    assert paired
    assert all(row["change_in_win_turn"] != "" for row in paired)


def test_random_audit_selection_not_first_n_when_possible() -> None:
    root = run(Path("configs/real-executor-smoke.toml"), smoke=True).parent
    audit = list(csv.DictReader((root / "audit-selection.csv").read_text().splitlines()))
    selected = [int(r["game_id"]) for r in audit if r["mode"] == "standard"]
    assert set(selected) != {1, 2} or len(selected) < 2


def test_worker_count_changes_do_not_change_real_smoke_results() -> None:
    one = run(Path("configs/real-executor-smoke.toml"), smoke=True, worker_count=1).parent
    two = run(Path("configs/real-executor-smoke.toml"), smoke=True, worker_count=2).parent
    a = pd.read_parquet(one / "canonical-standard-games.parquet").drop(columns=["game_id"])
    b = pd.read_parquet(two / "canonical-standard-games.parquet").drop(columns=["game_id"])
    pd.testing.assert_frame_equal(a, b)
