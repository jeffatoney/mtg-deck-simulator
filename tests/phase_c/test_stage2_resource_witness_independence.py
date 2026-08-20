from __future__ import annotations

from copy import deepcopy

import pytest

from mtg_kernel.engine import GameExecutor
from mtg_policy.broker import ActionBroker
from mtg_policy.public_actions import policy_action_view
from tests.phase_c import test_malcolm_glint_horn_witness_contract as witness


def _is_glint_loot(action: object) -> bool:
    view = policy_action_view(action)
    return (
        view.kind == "ACTIVATE"
        and view.identity == witness.GLINT
        and view.metadata.get("ability_id") == "glint-horn:loot"
    )


def _is_treasure_mana(action: object, color: str) -> bool:
    view = policy_action_view(action)
    return (
        view.kind == "ACTIVATE"
        and view.identity == "Treasure"
        and view.metadata.get("ability_id") == "token:treasure-mana"
        and view.metadata.get("mana_color") == color
    )


def _execute_broker_action(executor: GameExecutor, predicate: object) -> None:
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    selected = next((action for action in actions if predicate(action)), None)  # type: ignore[operator]
    assert selected is not None
    broker.execute(int(observation["generation"]), selected.handle)


def _prove_initial_glint_activation_executes(executor: GameExecutor) -> None:
    for _ in range(3):
        broker = ActionBroker(executor, "P0")
        observation, actions = broker.refresh()
        glint = next((action for action in actions if _is_glint_loot(action)), None)
        if glint is not None:
            before = len(executor.state.actions)
            broker.execute(int(observation["generation"]), glint.handle)
            new_actions = executor.state.actions[before:]
            assert any(
                action.kind == "ACTIVATE"
                and action.metadata.get("ability_id") == "glint-horn:loot"
                for action in new_actions
            )
            return

        pool = executor.state.players["P0"].mana_pool
        if int(pool.get("R", 0)) < 1:
            _execute_broker_action(executor, lambda action: _is_treasure_mana(action, "R"))
            continue
        if sum(int(value) for value in pool.values()) < 2:
            _execute_broker_action(executor, lambda action: _is_treasure_mana(action, "W"))
            continue
        raise AssertionError("production broker omitted Glint-Horn despite payable public state")
    raise AssertionError("captured 391 state did not expose an executable Glint-Horn activation")


@pytest.mark.parametrize(
    ("label", "legacy"),
    (("repaired-391", False), ("legacy-391", True)),
)
def test_captured_391_resource_line_executes_through_production_broker(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    legacy: bool,
) -> None:
    state, seed_text, snapshot = witness._first_access(
        monkeypatch,
        label,
        391730338978874520,
        legacy,
    )
    assert state.turn.phase == "COMBAT"
    assert state.turn.step == "COMBAT_DAMAGE"
    assert snapshot["legally_executable"] is True
    assert snapshot["full_table_kill"] is True

    executor = GameExecutor(deepcopy(state), seed_text)
    _prove_initial_glint_activation_executes(executor)
