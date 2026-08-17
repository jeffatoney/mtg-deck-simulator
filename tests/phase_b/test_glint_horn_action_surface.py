from __future__ import annotations

import pytest

from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card
from mtg_kernel.models import Zone
from mtg_policy.broker import ActionBroker, ObservedAction
from tests.phase_b.transcripts.support import funded_game

ABILITY_ID = "glint-horn:loot"
GLINT_HORN = "Glint-Horn Buccaneer"


def _arranged_state(
    seed: str,
    *,
    attacking: bool = True,
    payable_mana: bool = True,
    discardable_card: bool = True,
    has_priority: bool = True,
):
    state, executor, specs = funded_game(seed)
    pool = state.players["P0"].mana_pool
    for symbol in pool:
        pool[symbol] = 0
    pool["R"] = 1
    if payable_mana:
        pool["C"] = 1

    state.turn.phase = "COMBAT"
    state.turn.step = "DECLARE_ATTACKERS"
    state.turn.priority_holder_id = "P0" if has_priority else "P1"

    glint = add_card(executor, specs[GLINT_HORN], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = attacking
    discard = add_card(executor, specs["Opt"], Zone.HAND) if discardable_card else None
    return state, executor, glint, discard


def _glint_horn_activations(actions: tuple[ObservedAction, ...]) -> tuple[ObservedAction, ...]:
    return tuple(
        action
        for action in actions
        if action.kind == "ACTIVATE"
        and action.identity == GLINT_HORN
        and action.metadata.get("ability_id") == ABILITY_ID
    )


def test_direct_executor_accepts_legal_glint_horn_loot_activation() -> None:
    state, executor, glint, discard = _arranged_state("glint-horn-direct-positive")
    assert discard is not None
    before_action_count = len(state.actions)

    executor.activate(
        "P0",
        glint.object_id,
        ABILITY_ID,
        choices={"discard_ids": [discard.object_id]},
    )

    new_actions = state.actions[before_action_count:]
    action = next(
        record
        for record in new_actions
        if record.kind == "ACTIVATE" and record.metadata.get("ability_id") == ABILITY_ID
    )
    action_id = action.action_id
    assert action.payments["cost"]["GENERIC"] == 1
    assert action.payments["cost"]["R"] == 1
    assert action.payments["mana"] == {"R": 1, "C": 1}
    assert state.players["P0"].mana_pool["R"] == 0
    assert state.players["P0"].mana_pool["C"] == 0
    assert any(
        record.kind == "TRIGGER" and record.metadata.get("ability_id") == "glint-horn:discard"
        for record in new_actions
    )

    discard_changes = [
        change for change in state.zone_changes if change.from_object_id == discard.object_id
    ]
    assert len(discard_changes) == 1
    assert discard_changes[0].from_zone is Zone.HAND
    assert discard_changes[0].to_zone is Zone.GRAVEYARD
    assert any(
        event.kind == "CARD_DISCARDED" and event.cause_action_id == action_id
        for event in state.events
    )


def test_executor_rejects_broker_shaped_activation_without_discard_ids() -> None:
    _, executor, glint, _ = _arranged_state("glint-horn-broker-shaped-empty-choices")

    with pytest.raises(IllegalAction, match="activation requires explicit discard-cost choices"):
        executor.activate("P0", glint.object_id, ABILITY_ID, choices={})


def test_broker_exposes_and_executes_legal_glint_horn_loot_activation() -> None:
    state, executor, _, _ = _arranged_state("glint-horn-broker-positive")
    broker = ActionBroker(executor, "P0")

    observation, actions = broker.refresh()
    matches = _glint_horn_activations(actions)

    assert matches, "production broker omitted rules-legal glint-horn:loot activation"
    broker.execute(int(observation["generation"]), matches[0].handle)
    assert state.actions[-1].kind == "ACTIVATE"
    assert state.actions[-1].metadata["ability_id"] == ABILITY_ID


def test_broker_omits_glint_horn_loot_when_source_is_not_attacking() -> None:
    _, executor, _, _ = _arranged_state("glint-horn-not-attacking", attacking=False)
    _, actions = ActionBroker(executor, "P0").refresh()
    assert not _glint_horn_activations(actions)


def test_broker_omits_glint_horn_loot_without_one_generic_and_one_red_mana() -> None:
    _, executor, _, _ = _arranged_state("glint-horn-no-mana", payable_mana=False)
    _, actions = ActionBroker(executor, "P0").refresh()
    assert not _glint_horn_activations(actions)


def test_broker_omits_glint_horn_loot_without_a_discardable_card() -> None:
    _, executor, _, _ = _arranged_state("glint-horn-no-discard", discardable_card=False)
    _, actions = ActionBroker(executor, "P0").refresh()
    assert not _glint_horn_activations(actions)


def test_broker_omits_glint_horn_loot_when_p0_lacks_priority() -> None:
    _, executor, _, _ = _arranged_state("glint-horn-no-priority", has_priority=False)
    _, actions = ActionBroker(executor, "P0").refresh()
    assert not _glint_horn_activations(actions)


def test_executor_rejects_each_isolated_negative_control() -> None:
    cases = (
        ("not-attacking", {"attacking": False}),
        ("no-mana", {"payable_mana": False}),
        ("no-discard", {"discardable_card": False}),
        ("no-priority", {"has_priority": False}),
    )
    for label, overrides in cases:
        _, executor, glint, discard = _arranged_state(f"glint-horn-direct-{label}", **overrides)
        choices = {"discard_ids": [discard.object_id]} if discard is not None else {}
        with pytest.raises(IllegalAction):
            executor.activate("P0", glint.object_id, ABILITY_ID, choices=choices)
