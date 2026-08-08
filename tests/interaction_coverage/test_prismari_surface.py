from __future__ import annotations

from scripts.build_interaction_coverage_manifest import build_manifest
from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_policy import ContextualEvaluator, bind_policy_strategic_choices, load_evaluator_config
from mtg_policy.broker import ActionBroker
from mtg_policy.config import load_policy_matrix


def _funded_game(seed: str):
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    bundle = next(
        value for value in load_policy_matrix() if value.policy_config_id == "anchor_balanced"
    )
    bind_policy_strategic_choices(executor, bundle, ContextualEvaluator(load_evaluator_config()))
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def _pass_cycle(executor) -> None:
    for _ in range(4):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_prismari_manifest_exposes_mode_owned_target_words_and_target_player_actor() -> None:
    manifest = build_manifest()
    prismari = next(
        record
        for record in manifest["records"]
        if record["record_class"] == "CARD_EFFECT"
        and record["card"]["name"] == "Prismari Command"
        and record["effect"]["kind"] == "PRISMARI_COMMAND"
    )

    purposes = {choice["purpose"]: choice for choice in prismari["choices"]}
    assert purposes["MODE_SELECTION"]["timing"] == "CAST_PROPOSAL"
    assert purposes["MODE_TARGET_ASSIGNMENTS"]["timing"] == "CAST_PROPOSAL"
    assert purposes["DRAW_DISCARD_SELECTION_IF_CHOSEN"]["actor"] == "TARGET_PLAYER"
    assert purposes["DRAW_DISCARD_SELECTION_IF_CHOSEN"]["timing"] == "RESOLUTION"

    schema = prismari["legality"]["target_schema"]
    assert schema["kind"] == "PRISMARI_MODE_TARGETS"
    assert schema["selected_mode_count"] == 2
    assert schema["cross_role_unique"] is False
    assert schema["roles"] == {
        "CREATE_TREASURE": "PLAYER",
        "DAMAGE": "ANY_TARGET",
        "DESTROY_ARTIFACT": "ARTIFACT",
        "DRAW_DISCARD": "PLAYER",
    }


def test_prismari_same_player_can_fill_two_distinct_target_words() -> None:
    state, executor, specs = _funded_game("prismari-duplicate-role-target")
    spell = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    life_before = state.players["P1"].life

    executor.cast(
        "P0",
        spell.object_id,
        choices={
            "prismari_modes": ["DAMAGE", "CREATE_TREASURE"],
            "prismari_targets": {
                "DAMAGE": {"player_id": "P1"},
                "CREATE_TREASURE": {"player_id": "P1"},
            },
        },
    )
    _pass_cycle(executor)

    assert state.players["P1"].life == life_before - 2
    treasures = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == "P1"
        and obj.current_characteristics.get("name") == "Treasure"
    ]
    assert len(treasures) == 1


def test_prismari_draw_discard_choice_belongs_to_target_player() -> None:
    state, executor, specs = _funded_game("prismari-target-player-discard")
    spell = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    for name in ("Island", "Mountain", "Opt"):
        add_card(executor, specs[name], Zone.HAND, owner="P1")
    for name in ("Island", "Mountain", "Opt"):
        add_card(executor, specs[name], Zone.LIBRARY, owner="P1")

    executor.cast(
        "P0",
        spell.object_id,
        choices={
            "prismari_modes": ["DRAW_DISCARD", "CREATE_TREASURE"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P1"},
                "CREATE_TREASURE": {"player_id": "P1"},
            },
        },
    )
    _pass_cycle(executor)

    selection = next(
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION"
        and choice.actor_id == "P1"
        and isinstance(choice.selected, dict)
        and choice.selected.get("purpose") == "PRISMARI_DISCARD"
    )
    assert selection.selected["chosen_at"] == "RESOLUTION"
    assert selection.selected["purpose"] == "PRISMARI_DISCARD"


def test_broker_exposes_complete_prismari_mode_target_casts_without_object_ids() -> None:
    _state, executor, specs = _funded_game("prismari-broker-surface")
    spell = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    artifact = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")

    observation, actions = ActionBroker(executor, "P0").refresh()
    prismari = [
        action for action in actions if action.kind == "CAST" and action.identity == "Prismari Command"
    ]

    assert prismari
    assert all(action.target_count == 2 for action in prismari)
    assert all("prismari_modes" in action.metadata for action in prismari)
    assert all("prismari_targets" in action.metadata for action in prismari)
    encoded = repr((observation, [action.metadata for action in prismari]))
    assert spell.object_id not in encoded
    assert artifact.object_id not in encoded
