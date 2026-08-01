"""Cross-surface behavioral scenarios required by the Phase B transcript gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.phase_b_actions import foretell
from mtg_kernel.replay import transcript
from mtg_measure import (
    CardMeasurement,
    ComboMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    measurement_digest,
)
from mtg_policy import ActionBroker, StandardPolicy, load_policy_matrix
from mtg_runs import replay_in_fresh_process, verify_worker_invariance
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition

ROOT = Path(__file__).resolve().parents[2]


def funded_game(seed: str, players: tuple[str, ...] = ("P0", "P1", "P2", "P3")):
    state, executor = new_game(players, seed=seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_all(executor: GameExecutor) -> None:
    players = [player.player_id for player in executor.state.players.values() if player.in_game]
    for _ in players:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def test_glint_horn_curiosity_table_elimination_orders_terminal_before_optional_draws() -> None:
    state, executor, specs = funded_game("glint-curiosity-terminal")
    for opponent in ("P1", "P2", "P3"):
        state.players[opponent].life = 1
    add_card(executor, specs["Island"], Zone.LIBRARY)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND)
    executor.cast("P0", curiosity.object_id, (TargetRef(glint.object_id),))
    pass_all(executor)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0",
        glint.object_id,
        "glint-horn:loot",
        choices={"discard_ids": [discarded.object_id]},
    )
    activated_id, damage_trigger_id = state.stack
    pass_all(executor)

    assert state.terminal.status == "TERMINAL"
    assert state.stack == [activated_id]
    assert not state.waiting_triggers
    assert all(not state.players[player].in_game for player in ("P1", "P2", "P3"))
    assert all(
        state.players[player].loss_reasons == ["LIFE_TOTAL"] for player in ("P1", "P2", "P3")
    )
    resolved = next(
        index
        for index, event in enumerate(state.events)
        if event.kind == "STACK_OBJECT_RESOLVED"
        and event.payload.get("object_id") == damage_trigger_id
    )
    terminal = next(
        index for index, event in enumerate(state.events) if event.kind == "GAME_TERMINATED"
    )
    assert resolved < terminal == len(state.events) - 1
    assert not any(event.kind == "TRIGGER_PUT_ON_STACK" for event in state.events[terminal + 1 :])
    assert len(state.zones.get("HAND:P0", [])) == 0


def test_modal_x_and_alternative_cost_legality_and_payment_share_executor() -> None:
    state, executor, specs = funded_game("modal-x-alt")
    creature = add_card(
        executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD, owner="P1"
    )
    artifact_a = add_card(executor, specs["Sol Ring"], Zone.BATTLEFIELD, owner="P1")
    artifact_b = add_card(executor, specs["Arcane Signet"], Zone.BATTLEFIELD, owner="P2")

    abrade = add_card(executor, specs["Abrade"], Zone.HAND)
    abrade_spell = executor.cast(
        "P0", abrade.object_id, (TargetRef(creature.object_id),), mode="damage"
    )
    assert executor._created_action(abrade_spell).modes == ("damage",)
    executor.counter(abrade_spell.object_id)

    by_force = add_card(executor, specs["By Force"], Zone.HAND)
    before = state_hash(state)
    with pytest.raises(IllegalAction, match="targets must equal"):
        executor.cast(
            "P0",
            by_force.object_id,
            (TargetRef(artifact_a.object_id),),
            x_value=2,
        )
    assert state_hash(state) == before
    x_spell = executor.cast(
        "P0",
        by_force.object_id,
        (TargetRef(artifact_a.object_id), TargetRef(artifact_b.object_id)),
        x_value=2,
    )
    x_action = executor._created_action(x_spell)
    assert x_action.x_value == 2
    assert x_action.payments["cost"]["GENERIC"] == 2
    executor.counter(x_spell.object_id)

    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)
    foretold = foretell(executor, "P0", ravenform.object_id, "ravenform:foretell")
    state.turn.number += 1
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 1
    alt_spell = executor.cast(
        "P0",
        foretold.object_id,
        (TargetRef(artifact_a.object_id),),
        mode="foretell",
    )
    alt_action = executor._created_action(alt_spell)
    assert alt_action.payments["cost"]["U"] == 1
    assert sum(alt_action.payments["cost"].values()) == 1


def test_standard_and_exploratory_paths_share_broker_and_record_first_divergence() -> None:
    _state, executor, specs = funded_game("shared-broker-divergence")
    add_card(executor, specs["Island"], Zone.HAND)
    add_card(executor, specs["Sol Ring"], Zone.HAND)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    standard = StandardPolicy(load_policy_matrix()[0]).select_action(observation, actions)

    root = SearchPosition(observation, actions, SearchEvaluation(), 0)

    def expand(parent: SearchPosition, action, seed: int) -> SearchPosition:
        prefers_ring = action.kind == "CAST" and action.identity == "Sol Ring"
        return SearchPosition(
            {"generation": 2, "turn": {"number": 1}, "sample": seed},
            (),
            SearchEvaluation(net_usable_mana=2 if prefers_ring else 0),
            parent.player_turns_elapsed + 1,
        )

    exploratory = BoundedExplorer().choose(root, belief_sample_seeds=(101, 102), expand=expand)
    assert {action.handle for action in actions} == {action.handle for action in root.actions}
    assert standard in {action.handle for action in actions}
    assert exploratory.selected_action in {action.handle for action in actions}
    assert standard != exploratory.selected_action
    standard_action = next(action for action in actions if action.handle == standard)
    exploratory_action = next(
        action for action in actions if action.handle == exploratory.selected_action
    )
    assert standard_action.kind == "PLAY_LAND"
    assert exploratory_action.kind == "CAST" and exploratory_action.identity == "Sol Ring"
    assert exploratory.log.actual_hidden_future_inaccessible is True
    assert exploratory.log.post_result_replay_attempts == 0


def test_fresh_process_replay_measurement_and_worker_invariance_with_terminal_short_circuit() -> (
    None
):
    state, executor, specs = funded_game("slice3-invariance", ("P0", "P1"))
    state.replay_initial_state = state.audit_dict()
    state.players["P1"].life = 1
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    state.replay_initial_state = state.audit_dict()
    executor.deal_damage_to_player(malcolm.object_id, "P1", 1, combat=True)
    assert state.terminal.status == "TERMINAL"
    with pytest.raises(IllegalAction, match="game is terminal"):
        executor.pass_priority("P0")

    replay = replay_in_fresh_process(transcript(state, seed="slice3-invariance"), cwd=ROOT)
    assert replay.state_hash == state_hash(state)

    measurement = GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=1,
        seed=11,
        mode="AUDIT_ONLY",
        policy_config_id="anchor_balanced",
        opening_hands=(OpeningHandMeasurement(1, 7, ("Island",) * 7, True),),
        kept_at=7,
        checkpoint_table_win_access={5: False, 6: False, 8: False, 10: True},
        failure_labels={5: ("mana_shortage",), 6: (), 8: (), 10: ()},
        primary_failure={5: "mana_shortage", 6: None, 8: None, 10: None},
        combo_records=(
            ComboMeasurement(
                "malcolm_glint_horn", 10, True, True, False, False, True, True, True, False
            ),
        ),
        earliest_legal_attempt_turn=10,
        actual_first_attempt_turn=10,
        attempt_package="malcolm_glint_horn",
        attempt_timing="IMMEDIATE",
        usable_protection_count=0,
        protection_in_hand_not_payable=False,
        protection_category_mismatch=False,
        independent_second_line_available=False,
        card_records=(CardMeasurement("Malcolm, Keen-Eyed Navigator", drawn=0, cast=1),),
        terminal_status="WIN",
        terminal_turn=10,
    )
    digest = measurement_digest((measurement,))
    raw = ({"game_index": 1, "seed": 11, "measurement_sha256": digest},)
    assert verify_worker_invariance({1: raw, 4: tuple(reversed(raw))}) == verify_worker_invariance(
        {2: raw}
    )


def test_malcolm_treasure_count_uses_exact_damaged_opponent_set() -> None:
    state, executor, specs = funded_game("malcolm-opponent-set")
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0", glint.object_id, "glint-horn:loot", choices={"discard_ids": [discarded.object_id]}
    )
    pass_all(executor)
    malcolm_triggers = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.current_characteristics.get("ability", {}).get("ability_id")
        == "malcolm:pirate-damage"
    ]
    assert len(malcolm_triggers) == 1
    assert set(malcolm_triggers[0].current_characteristics["trigger_context"]["opponents"]) == {
        "P1",
        "P2",
        "P3",
    }
    pass_all(executor)
    treasures = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == "Treasure"
    ]
    assert len(treasures) == 3
    assert malcolm.zone is Zone.BATTLEFIELD


def test_breeches_unknown_cards_are_recorded_but_never_deterministic_resources() -> None:
    state, executor, specs = funded_game("breeches-unknown")
    breeches = add_card(executor, specs["Breeches, Brazen Plunderer"], Zone.BATTLEFIELD)
    pirate = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    executor.deal_damage_to_player(pirate.object_id, "P1", 1, combat=True)
    assert state.stack
    while state.stack and state.terminal.status == "ACTIVE":
        pass_all(executor)
    record = next(choice for choice in state.choices if choice.kind == "BREECHES_UNKNOWN_EXCLUSION")
    assert record.selected == {
        "opponents": ["P1"],
        "deterministic_resources_added": 0,
        "hidden_identities_exposed": False,
    }
    assert not any(obj.zone is Zone.EXILE for obj in state.objects.values() if not obj.retired)
    assert breeches.zone is Zone.BATTLEFIELD
