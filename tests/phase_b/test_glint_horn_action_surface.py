from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction
from mtg_kernel.hashing import state_hash
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.factory import add_card
from mtg_kernel.models import Zone
from mtg_policy import StandardPolicy, load_policy_matrix
from mtg_policy.broker import ActionBroker, ObservedAction
from mtg_policy.public_actions import (
    policy_action_view,
    public_action_classes,
    resolve_selected_action_handle,
)
from mtg_runs import replay_in_fresh_process
from tests.phase_b.transcripts.support import funded_game

ABILITY_ID = "glint-horn:loot"
GLINT_HORN = "Glint-Horn Buccaneer"
ROOT = Path(__file__).resolve().parents[2]


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
    state.turn.priority_holder_id = "P0"

    glint = add_card(executor, specs[GLINT_HORN], Zone.BATTLEFIELD)
    if attacking:
        executor.declare_attackers("P0", {glint.object_id: "P1"})
    else:
        glint.current_characteristics["attacking"] = False
    state.turn.priority_holder_id = "P0" if has_priority else "P1"
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
    activation = next(
        record
        for record in reversed(state.actions)
        if record.kind == "ACTIVATE" and record.metadata.get("ability_id") == ABILITY_ID
    )
    assert activation.metadata["ability_id"] == ABILITY_ID


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


def _spec(name: str):
    return next(spec for spec in load_full_deck_specs().values() if spec.name == name)


def _standard_policy() -> StandardPolicy:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    return StandardPolicy(bundle, opponent_interaction_modeled=True)


def _surface_with_discards(
    seed: str,
    discard_names: tuple[str, ...],
    *,
    hidden_library: tuple[str, ...] = (),
):
    state, executor, _, _ = _arranged_state(seed, discardable_card=False)
    discards = [add_card(executor, _spec(name), Zone.HAND) for name in discard_names]
    for name in hidden_library:
        add_card(executor, _spec(name), Zone.LIBRARY, visible_to=set())
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    return state, executor, broker, observation, actions, discards


def test_broker_single_discard_choice_is_private_and_replay_exact() -> None:
    seed = "glint-horn-single-discard-replay"
    state, executor, _, discard = _arranged_state(seed)
    assert discard is not None
    state.replay_commands.clear()
    state.replay_initial_state = state.audit_dict()
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    matches = _glint_horn_activations(actions)
    assert len(matches) == 1
    selected = matches[0]

    encoded = json.dumps(selected.metadata, sort_keys=True)
    assert "discard_ids" not in encoded
    assert discard.object_id not in encoded
    assert discard.component_card_instance_ids[0] not in encoded
    public_card = selected.metadata["discard_cards"][0]
    assert public_card["identity"] == "Opt"
    assert set(public_card) == {"identity", "mana_value", "card_types", "effect_kinds"}

    broker.execute(int(observation["generation"]), selected.handle)
    assert any(
        change.from_object_id == discard.object_id
        and change.from_zone is Zone.HAND
        and change.to_zone is Zone.GRAVEYARD
        for change in state.zone_changes
    )

    recorded = transcript(state, seed=seed)
    same_process = validate_replay(recorded)
    assert state_hash(same_process) == state_hash(state)
    fresh = replay_in_fresh_process(recorded, cwd=ROOT)
    assert fresh.state_hash == state_hash(state)


def test_multiple_public_discard_semantics_do_not_depend_on_private_enumeration() -> None:
    first = _surface_with_discards("glint-horn-multiple-semantic-order", ("Opt", "Mountain"))
    second = _surface_with_discards("glint-horn-multiple-semantic-order", ("Mountain", "Opt"))
    _, _, broker_a, observation_a, actions_a, discards_a = first
    _, _, _, observation_b, actions_b, _ = second
    matches_a = _glint_horn_activations(actions_a)
    matches_b = _glint_horn_activations(actions_b)
    assert len(matches_a) == len(matches_b) == 2
    assert {action.metadata["discard_cards"][0]["identity"] for action in matches_a} == {
        "Mountain",
        "Opt",
    }
    assert {policy_action_view(action).key for action in matches_a} == {
        policy_action_view(action).key for action in matches_b
    }

    policy = _standard_policy()
    assert policy.select_public_action_key(
        observation_a, actions_a
    ) == policy.select_public_action_key(observation_b, tuple(reversed(actions_b)))

    mountain_action = next(
        action
        for action in matches_a
        if action.metadata["discard_cards"][0]["identity"] == "Mountain"
    )
    opt, mountain = discards_a
    broker_a.execute(int(observation_a["generation"]), mountain_action.handle)
    assert any(
        change.from_object_id == mountain.object_id and change.to_zone is Zone.GRAVEYARD
        for change in broker_a.executor.state.zone_changes
    )
    assert not any(
        change.from_object_id == opt.object_id for change in broker_a.executor.state.zone_changes
    )


def test_equivalent_duplicate_discards_collapse_before_private_resolution() -> None:
    _, _, _, _, actions, _ = _surface_with_discards(
        "glint-horn-duplicate-equivalence", ("Opt", "Opt")
    )
    matches = _glint_horn_activations(actions)
    assert len(matches) == 2
    assert policy_action_view(matches[0]).key == policy_action_view(matches[1]).key
    classes = public_action_classes(matches)
    assert len(classes) == 1
    assert classes[0].representative_count == 2
    resolved_handle = resolve_selected_action_handle(matches, classes[0].key)
    assert resolved_handle in {action.handle for action in matches}


def test_hidden_only_mutation_preserves_public_classes_and_selected_key() -> None:
    first = _surface_with_discards(
        "glint-horn-hidden-only",
        ("Opt", "Mountain"),
        hidden_library=("Twinflame", "Curiosity"),
    )
    second = _surface_with_discards(
        "glint-horn-hidden-only",
        ("Opt", "Mountain"),
        hidden_library=("Curiosity", "Twinflame"),
    )
    _, _, _, observation_a, actions_a, discards_a = first
    _, _, _, observation_b, actions_b, discards_b = second
    encoded = json.dumps([action.metadata for action in (*actions_a, *actions_b)], sort_keys=True)
    private_ids = {
        value
        for card in (*discards_a, *discards_b)
        for value in (card.object_id, card.component_card_instance_ids[0])
    }
    assert "discard_ids" not in encoded
    assert all(private_id not in encoded for private_id in private_ids)
    assert {item.key for item in public_action_classes(actions_a)} == {
        item.key for item in public_action_classes(actions_b)
    }
    policy = _standard_policy()
    assert policy.select_public_action_key(
        observation_a, actions_a
    ) == policy.select_public_action_key(observation_b, tuple(reversed(actions_b)))
