from __future__ import annotations

from typing import Any

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_runs.replay_audit import replay_in_fresh_process
import mtg_runs.phase_c_runner as runner
from mtg_runs.phase_c_runner import run_phase_c_game_execution

ROOT = runner.ROOT


class _DecisionFailPolicy:
    def select_action(self, observation: Any, actions: Any) -> str:
        raise AssertionError("strategic decision requested after terminal transition")


def test_repaired_standard_historical_terminal_seed_trace_is_replay_exact() -> None:
    execution = run_phase_c_game_execution(
        seed=391730338978874520,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    assert execution.technical_game.terminal_status == "ACTIVE"
    assert execution.technical_game.controlled_turns_completed == 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )


def test_terminal_cleanup_stops_without_commands_decisions_or_repetition(
    monkeypatch: Any,
) -> None:
    state, executor = new_game(("P0", "P1"), seed="terminal-cleanup-policy-independent")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    source = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    state.players["P1"].life = 1
    # A pending object makes cleanup enter its resolution window. The regression
    # controls only the surrounding turn driver; the terminal transition itself
    # is a real production executor command and is replayed through production.
    state.stack.append(source.object_id)
    state.turn.cleanup_repeat_pending = True
    state.replay_initial_state = state.audit_dict()
    state.replay_commands.clear()

    cleanup_calls = 0
    transition_command_count = -1

    def begin_cleanup(step: str, choices: dict[str, Any]) -> None:
        nonlocal cleanup_calls
        assert step == "CLEANUP"
        assert choices == {"discard_ids": []}
        cleanup_calls += 1

    def terminate_during_resolution(*args: Any, **kwargs: Any) -> None:
        nonlocal transition_command_count
        executor.deal_damage_to_player(source.object_id, "P1", 1, combat=True)
        transition_command_count = len(state.replay_commands)

    monkeypatch.setattr(executor, "begin_step", begin_cleanup)
    monkeypatch.setattr(runner, "_priority_window", terminate_during_resolution)

    runner._run_cleanup_step(
        executor,
        _DecisionFailPolicy(),  # type: ignore[arg-type]
        object(),
        policy_actions=True,
    )

    assert state.terminal.status == "TERMINAL"
    assert cleanup_calls == 1
    assert transition_command_count > 0
    assert len(state.replay_commands) == transition_command_count
    body = transcript(state, seed="terminal-cleanup-policy-independent")
    assert state_hash(validate_replay(body)) == state_hash(state)
    assert replay_in_fresh_process(body, cwd=ROOT).state_hash == state_hash(state)
