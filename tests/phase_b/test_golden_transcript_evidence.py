"""Runtime-bound evidence scenarios for the twelve Phase B golden transcripts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_deck import build_exact_game
from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import CopyKind, TargetRef, Zone
from mtg_kernel.phase_b_actions import foretell
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_measure import (
    CardMeasurement,
    ComboMeasurement,
    DivergenceMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    measurement_digest,
)
from mtg_policy import (
    ActionBroker,
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    StandardPolicy,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_policy.mulligan import (
    LEAGUE_CANDIDATE_HAND_SIZES,
    REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE,
    LeagueMulliganResult,
    draw_back_to_seven,
)
from mtg_runs import replay_in_fresh_process, verify_worker_invariance
from mtg_search import BoundedExplorer, SearchEvaluation, SearchPosition
from mtg_verify.transcript_evidence import (
    audit_event,
    record_audit_evidence,
    record_game_state_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
PLAYERS = ("P0", "P1", "P2", "P3")


def funded_game(seed: str, players: tuple[str, ...] = PLAYERS):
    state, executor = new_game(players, seed=seed)
    for player in state.players.values():
        for symbol in ("W", "U", "B", "R", "G", "C"):
            player.mana_pool[symbol] = 30
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    return state, executor, specs


def pass_round(executor: Any) -> None:
    living = [player.player_id for player in executor.state.players.values() if player.in_game]
    for _ in living:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def move_named(executor: Any, objects: list[Any] | tuple[Any, ...], name: str, zone: Zone) -> Any:
    original = next(
        obj
        for obj in objects
        if not obj.retired and obj.current_characteristics.get("name") == name
    )
    moved = executor.zones.move(
        original.object_id,
        zone,
        "TEST_SETUP",
        executor._event("TEST_SETUP", object_id=original.object_id),
        controller=original.owner if zone is Zone.BATTLEFIELD else None,
    )
    assert moved is not None
    return moved


def provider() -> PolicyStrategicChoiceProvider:
    return PolicyStrategicChoiceProvider(
        load_policy_matrix()[0], ContextualEvaluator(load_evaluator_config())
    )


class TutorOverrideProvider:
    def __init__(self, base: PolicyStrategicChoiceProvider, identity: str) -> None:
        self.base = base
        self.identity = identity

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        assert self.identity in request.eligible_identities
        return TutorChoiceSelection(
            self.identity,
            self.base.evaluator_id,
            self.base.evaluator_sha256,
            {"test_override": True},
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        return self.base.choose_fact_or_fiction(request)

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        return self.base.choose_spell_copy_targets(request)


class LoopWitnessProvider:
    def __init__(self, base: PolicyStrategicChoiceProvider, token_limit: int = 2) -> None:
        self.base = base
        self.token_limit = token_limit

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        return self.base.choose_tutor(request)

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        return self.base.choose_fact_or_fiction(request)

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        target_by_handle = {card.handle: card for card in request.legal_targets}
        objects = request.observation.get("objects", ())
        dualcasters = (
            sum(
                isinstance(raw, Mapping)
                and raw.get("zone") == "BATTLEFIELD"
                and raw.get("identity") == "Dualcaster Mage"
                for raw in objects
            )
            if isinstance(objects, Sequence)
            else 0
        )
        token_count = max(0, dualcasters - 1)
        if token_count < self.token_limit:
            options = [
                targets
                for targets in request.legal_target_sets
                if len(targets) == 1 and target_by_handle[targets[0]].identity == "Dualcaster Mage"
            ]
            strategy = "CONTINUE_BOUNDED_DUALCASTER_LOOP"
        else:
            options = [
                targets
                for targets in request.legal_target_sets
                if len(targets) == 1 and target_by_handle[targets[0]].identity != "Dualcaster Mage"
            ]
            strategy = "STOP_BOUNDED_DUALCASTER_LOOP"
        assert options
        return SpellCopyTargetSelection(
            min(options),
            "dualcaster-loop-witness-v1",
            "1" * 64,
            {
                "strategy": strategy,
                "token_count": token_count,
                "audit_witness_limit": self.token_limit,
                "canonical_policy_eligible": False,
            },
        )


def test_pb_t01_exact_deck_evidence() -> None:
    state, _, objects = build_exact_game("golden-t01")
    assert len(objects["library"]) == 98
    assert len(objects["command"]) == 2
    assert len(state.card_instances) == len(state.deck_slots) == 100
    assert len(set(state.card_instances)) == 100
    active = [obj for obj in state.objects.values() if not obj.retired and not obj.ceased_to_exist]
    assert len(active) == 100 == len({obj.object_id for obj in active})
    assert all(len(obj.component_card_instance_ids) == 1 for obj in active)
    assert {obj.component_card_instance_ids[0] for obj in active} == set(state.card_instances)
    names = Counter(obj.current_characteristics["name"] for obj in objects["library"])
    assert names["Island"] == 12 and names["Mountain"] == 10
    commanders = sorted(obj.current_characteristics["name"] for obj in objects["command"])
    assert commanders == ["Breeches, Brazen Plunderer", "Malcolm, Keen-Eyed Navigator"]
    record_audit_evidence(
        "PB-T01-exact-deck",
        (
            audit_event("DECK_PACKAGE_VALIDATED", library_count=98, command_count=2),
            audit_event("CARD_INSTANCE_IDENTIFIERS_VALIDATED", count=100),
            audit_event("ACTIVE_OBJECT_IDENTIFIERS_VALIDATED", count=100),
            audit_event("COMMAND_ZONE_ASSIGNMENTS_VALIDATED", commanders=commanders),
        ),
        facts={"island_count": 12, "mountain_count": 10},
    )


def test_pb_t02_league_mulligan_evidence() -> None:
    assert LEAGUE_CANDIDATE_HAND_SIZES == (7, 7, 6, 5, 4)
    assert REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE is True
    results: list[LeagueMulliganResult] = []
    for keep_size in (7, 6, 5, 4):
        result = draw_back_to_seven(
            tuple(f"kept-{index}" for index in range(keep_size)),
            tuple(f"refill-{index}" for index in range(7 - keep_size)),
            nominal_keep_size=keep_size,
        )
        assert len(result.final_hand) == 7
        results.append(result)
    with pytest.raises(ValueError, match="stop at four") as floor_error:
        draw_back_to_seven(("a", "b", "c"), ("d",) * 4, nominal_keep_size=3)
    record_audit_evidence(
        "PB-T02-league-mulligan",
        (
            audit_event(
                "LEAGUE_MULLIGAN_SEQUENCE_VALIDATED",
                candidate_sizes=list(LEAGUE_CANDIDATE_HAND_SIZES),
            ),
            audit_event(
                "REJECTED_HAND_SHUFFLE_POLICY_VALIDATED",
                returned_to_library=True,
                shuffled_before_next_hand=True,
            ),
            audit_event(
                "LEAGUE_KEEP_LEVELS_VALIDATED",
                keep_sizes=[result.nominal_keep_size for result in results],
            ),
            audit_event(
                "LEAGUE_REFILL_VALIDATED",
                final_sizes=[len(result.final_hand) for result in results],
            ),
            audit_event("FOUR_CARD_FLOOR_ENFORCED", reason=str(floor_error.value)),
        ),
    )


def test_pb_t03_malcolm_opponent_set_evidence() -> None:
    state, executor, specs = funded_game("golden-t03")
    add_card(executor, specs["Island"], Zone.LIBRARY)
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0", glint.object_id, "glint-horn:loot", choices={"discard_ids": [discarded.object_id]}
    )
    pass_round(executor)
    trigger = next(
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.current_characteristics.get("ability", {}).get("ability_id")
        == "malcolm:pirate-damage"
    )
    assert set(trigger.current_characteristics["trigger_context"]["opponents"]) == {
        "P1",
        "P2",
        "P3",
    }
    pass_round(executor)
    treasures = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.BATTLEFIELD
        and obj.current_characteristics.get("name") == "Treasure"
    ]
    assert len(treasures) == 3 and malcolm.zone is Zone.BATTLEFIELD
    kinds = [event.kind for event in state.events]
    assert kinds.index("TREASURE_CREATED") < kinds.index("CARD_DRAWN")
    record_game_state_evidence(
        "PB-T03-malcolm-opponents",
        state,
        facts={"damaged_opponents": ["P1", "P2", "P3"], "treasure_count": 3},
    )


def test_pb_t04_breeches_boundary_evidence() -> None:
    state, executor, specs = funded_game("golden-t04")
    breeches = add_card(executor, specs["Breeches, Brazen Plunderer"], Zone.BATTLEFIELD)
    pirate = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    executor.deal_damage_to_player(pirate.object_id, "P1", 1, combat=True)
    while state.stack and state.terminal.status == "ACTIVE":
        pass_round(executor)
    record = next(choice for choice in state.choices if choice.kind == "BREECHES_UNKNOWN_EXCLUSION")
    assert record.selected == {
        "opponents": ["P1"],
        "deterministic_resources_added": 0,
        "hidden_identities_exposed": False,
    }
    assert not any(obj.zone is Zone.EXILE for obj in state.objects.values() if not obj.retired)
    assert breeches.zone is Zone.BATTLEFIELD
    record_game_state_evidence(
        "PB-T04-breeches-unknown",
        state,
        facts={
            "modeled_opponent_library_objects": 0,
            "local_exile_objects_added": 0,
            "deterministic_resources_added": 0,
        },
    )


def test_pb_t05_dualcaster_twinflame_evidence() -> None:
    state, executor, created = build_exact_game("golden-t05", ("P0", "P1"))
    library = list(created["library"])
    executor.bind_strategic_choice_provider(LoopWitnessProvider(provider(), 2))
    state.turn.phase = "PRECOMBAT_MAIN"
    dualcaster = move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    twinflame = move_named(executor, library, "Twinflame", Zone.HAND)
    malcolm = move_named(
        executor, list(created["command"]), "Malcolm, Keen-Eyed Navigator", Zone.BATTLEFIELD
    )
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["R"] = 3
    state.players["P0"].mana_pool["C"] = 3
    original = executor.cast("P0", twinflame.object_id, (TargetRef(malcolm.object_id),))
    executor.cast(
        "P0",
        dualcaster.object_id,
        choices={"trigger_targets": {"dualcaster:etb": original.object_id}},
    )
    for _ in range(30):
        if not state.stack and not state.waiting_triggers:
            break
        pass_round(executor)
    else:
        raise AssertionError("bounded Dualcaster line did not terminate")
    tokens = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.copy_kind is CopyKind.TOKEN_COPY
        and obj.current_characteristics.get("name") == "Dualcaster Mage"
    ]
    copies = [
        obj
        for obj in state.objects.values()
        if obj.copy_kind is CopyKind.SPELL_COPY
        and obj.current_characteristics.get("name") == "Twinflame"
    ]
    assert len(tokens) == 2
    assert copies and all(
        copy.was_cast is False and not copy.component_card_instance_ids for copy in copies
    )
    strategies = [
        choice.selected.get("diagnostics", {}).get("strategy")
        for choice in state.choices
        if choice.kind == "COPY_TARGETS" and isinstance(choice.selected, dict)
    ]
    assert "CONTINUE_BOUNDED_DUALCASTER_LOOP" in strategies
    assert "STOP_BOUNDED_DUALCASTER_LOOP" in strategies
    kinds = [event.kind for event in state.events]
    assert (
        kinds.index("COPY_TARGET_DECISION")
        < kinds.index("SPELL_COPIED")
        < kinds.index("TOKEN_COPY_CREATED")
    )
    record_game_state_evidence(
        "PB-T05-dualcaster-twinflame",
        state,
        facts={
            "token_dualcaster_count": 2,
            "copy_target_decision_precedes_copy": True,
            "canonical_policy_eligible": False,
        },
    )


def test_pb_t06_glint_curiosity_terminal_evidence() -> None:
    state, executor, specs = funded_game("golden-t06")
    for opponent in ("P1", "P2", "P3"):
        state.players[opponent].life = 1
    add_card(executor, specs["Island"], Zone.LIBRARY)
    glint = add_card(executor, specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD)
    curiosity = add_card(executor, specs["Curiosity"], Zone.HAND)
    executor.cast("P0", curiosity.object_id, (TargetRef(glint.object_id),))
    pass_round(executor)
    glint.current_characteristics["attacking"] = True
    discarded = add_card(executor, specs["Opt"], Zone.HAND)
    executor.activate(
        "P0", glint.object_id, "glint-horn:loot", choices={"discard_ids": [discarded.object_id]}
    )
    activated_id, damage_trigger_id = state.stack
    pass_round(executor)
    assert state.terminal.status == "TERMINAL"
    assert state.stack == [activated_id]
    assert not state.waiting_triggers
    assert all(not state.players[player].in_game for player in ("P1", "P2", "P3"))
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
    curiosity_triggers = [
        event
        for event in state.events
        if event.kind == "ABILITY_TRIGGERED"
        and event.payload.get("ability_id") == "curiosity:damage"
    ]
    assert len(curiosity_triggers) == 3
    assert any(event.kind == "SBA_SYNTHETIC_CEASE" for event in state.events)
    assert any(event.kind == "SYNTHETIC_OBJECT_CEASED" for event in state.events)
    assert not any(event.kind == "CARD_DRAWN" for event in state.events)

    negative_state, negative_executor, negative_specs = funded_game(
        "golden-t06-not-attacking", ("P0", "P1")
    )
    negative_glint = add_card(
        negative_executor, negative_specs["Glint-Horn Buccaneer"], Zone.BATTLEFIELD
    )
    negative_discard = add_card(negative_executor, negative_specs["Opt"], Zone.HAND)
    before = state_hash(negative_state)
    with pytest.raises(IllegalAction, match="only while the source attacks"):
        negative_executor.activate(
            "P0",
            negative_glint.object_id,
            "glint-horn:loot",
            choices={"discard_ids": [negative_discard.object_id]},
        )
    assert state_hash(negative_state) == before
    record_game_state_evidence(
        "PB-T06-glint-curiosity-terminal",
        state,
        facts={
            "curiosity_trigger_count": 3,
            "nonattacking_activation_rejected": True,
            "post_terminal_draw_count": 0,
        },
    )


def test_pb_t07_transmute_resolution_evidence() -> None:
    state, executor, created = build_exact_game("golden-t07", PLAYERS)
    library = list(created["library"])
    dizzy = move_named(executor, library, "Dizzy Spell", Zone.HAND)
    executor.bind_strategic_choice_provider(TutorOverrideProvider(provider(), "Sol Ring"))
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 2
    state.players["P0"].mana_pool["C"] = 1
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    action = next(
        item for item in actions if item.kind == "ACTIVATE_HAND" and item.identity == "Dizzy Spell"
    )
    assert action.metadata["choice_timing"] == "RESOLUTION"
    broker.execute(int(observation["generation"]), action.handle)
    assert not any(choice.kind == "TRANSMUTE" for choice in state.choices)
    pass_round(executor)
    rings = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Sol Ring"
    ]
    assert len(rings) == 1
    choice = next(item for item in state.choices if item.kind == "TRANSMUTE")
    assert choice.selected["identity"] == "Sol Ring"
    assert choice.selected["chosen_at"] == "RESOLUTION"
    assert dizzy.retired
    record_game_state_evidence(
        "PB-T07-tutor-one",
        state,
        facts={
            "activation_event_semantics": "ANNOUNCED_AND_STACKED_BEFORE_COST_EVENTS",
            "selected_identity": "Sol Ring",
        },
    )


def test_pb_t08_modal_x_foretell_evidence() -> None:
    state, executor, specs = funded_game("golden-t08")
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
        executor.cast("P0", by_force.object_id, (TargetRef(artifact_a.object_id),), x_value=2)
    assert state_hash(state) == before
    x_spell = executor.cast(
        "P0",
        by_force.object_id,
        (TargetRef(artifact_a.object_id), TargetRef(artifact_b.object_id)),
        x_value=2,
    )
    x_action = executor._created_action(x_spell)
    assert x_action.x_value == 2 and x_action.payments["cost"]["GENERIC"] == 2
    executor.counter(x_spell.object_id)
    ravenform = add_card(executor, specs["Ravenform"], Zone.HAND)
    foretold = foretell(executor, "P0", ravenform.object_id, "ravenform:foretell")
    state.turn.number += 1
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in ("W", "U", "B", "R", "G", "C")})
    state.players["P0"].mana_pool["U"] = 1
    alt_spell = executor.cast(
        "P0", foretold.object_id, (TargetRef(artifact_a.object_id),), mode="foretell"
    )
    alt_action = executor._created_action(alt_spell)
    assert alt_action.payments["cost"]["U"] == 1
    assert sum(alt_action.payments["cost"].values()) == 1
    record_game_state_evidence(
        "PB-T08-modal-x-alt",
        state,
        facts={"illegal_x_cast_rolled_back": True, "x_value": 2, "foretell_cast_payment": 1},
    )


def test_pb_t09_fact_or_fiction_evidence() -> None:
    state, executor, created = build_exact_game("golden-t09", PLAYERS)
    library = list(created["library"])
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    executor.bind_strategic_choice_provider(provider())
    for _ in range(3):
        move_named(executor, library, "Island", Zone.BATTLEFIELD)
        library = [obj for obj in library if not obj.retired]
    fact = move_named(executor, library, "Fact or Fiction", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [obj for obj in library if not obj.retired]
    reveal = []
    for name in ["Island", "Island", "Island", "Mountain", "Twinflame"]:
        obj = next(
            candidate
            for candidate in library
            if not candidate.retired and candidate.current_characteristics.get("name") == name
        )
        reveal.append(obj)
        library.remove(obj)
    zone = state.zones[executor.zones.zone_key(Zone.LIBRARY, "P0")]
    for obj in reveal:
        zone.remove(obj.object_id)
    zone.extend(obj.object_id for obj in reversed(reveal))
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 1
    state.players["P0"].mana_pool["C"] = 3
    executor.cast("P0", fact.object_id)
    pass_round(executor)
    chosen = next(choice for choice in state.choices if choice.kind == "FACT_OR_FICTION_PILE")
    assert "Twinflame" in chosen.selected["cards"]
    graveyard_names = [
        obj.current_characteristics.get("name")
        for obj in state.objects.values()
        if not obj.retired and obj.zone is Zone.GRAVEYARD and obj.owner == "P0"
    ]
    assert graveyard_names.count("Island") >= 3
    replayed = validate_replay(transcript(state, seed="golden-t09"))
    assert (
        next(
            choice for choice in replayed.choices if choice.kind == "FACT_OR_FICTION_PILE"
        ).selected
        == chosen.selected
    )
    record_game_state_evidence(
        "PB-T09-fact-min",
        state,
        facts={
            "twinflame_reached_hand": True,
            "rejected_islands_in_graveyard": graveyard_names.count("Island"),
            "fresh_replay_reproduced_selection": True,
            "test_fixture_uses_sol_ring": False,
        },
    )


def test_pb_t10_hidden_future_evidence() -> None:
    from mtg_policy.broker import ObservedAction

    action = ObservedAction("a", "TEST", None, 0, (), 0, {})
    with pytest.raises(ValueError, match="forbidden hidden field") as hidden_error:
        SearchPosition(
            {"generation": 1, "turn": {}, "library_order": ["A"]},
            (action,),
            SearchEvaluation(),
        )
    root = SearchPosition(
        {"generation": 1, "turn": {"number": 1}, "public_value": 0},
        (action,),
        SearchEvaluation(),
        0,
    )
    with pytest.raises(ValueError, match="maximum of eight") as sample_error:
        BoundedExplorer().choose(
            root,
            belief_sample_seeds=tuple(range(9)),
            expand=lambda parent, selected, seed: SearchPosition(
                parent.observation, parent.actions, parent.evaluation, 1
            ),
        )
    record_audit_evidence(
        "PB-T10-hidden-future",
        (
            audit_event("HIDDEN_FIELD_REJECTED", reason=str(hidden_error.value)),
            audit_event("BELIEF_SAMPLE_CAP_REJECTED", reason=str(sample_error.value), attempted=9),
        ),
        facts={"successful_samples_claimed": 0, "post_result_replay_attempted": False},
    )


def test_pb_t11_shared_broker_divergence_evidence() -> None:
    _state, executor, specs = funded_game("golden-t11")
    add_card(executor, specs["Island"], Zone.HAND)
    add_card(executor, specs["Sol Ring"], Zone.HAND)
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    generation = int(observation["generation"])
    handles = {action.handle for action in actions}
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
    assert standard in handles and exploratory.selected_action in handles
    assert standard != exploratory.selected_action
    standard_action = next(action for action in actions if action.handle == standard)
    exploratory_action = next(
        action for action in actions if action.handle == exploratory.selected_action
    )
    assert standard_action.kind == "PLAY_LAND"
    assert exploratory_action.kind == "CAST" and exploratory_action.identity == "Sol Ring"
    divergence = DivergenceMeasurement(
        paired_seed=101,
        standard_result=f"{standard_action.kind}:{standard_action.identity}",
        exploratory_result=f"{exploratory_action.kind}:{exploratory_action.identity}",
        first_decision_divergence=(
            f"{standard_action.kind}:{standard_action.identity} -> "
            f"{exploratory_action.kind}:{exploratory_action.identity}"
        ),
        visible_information=observation,
        win_turn_change=None,
        narrow_condition=False,
        branches_searched=exploratory.log.branches_searched,
        nodes_evaluated=exploratory.log.nodes_evaluated,
        depth_reached=exploratory.log.depth_reached,
        selected_before_future_draws=True,
    )
    refreshed, _ = broker.refresh()
    assert int(refreshed["generation"]) > generation
    with pytest.raises(IllegalAction, match="revoked") as stale_error:
        broker.execute(generation, standard)
    record_audit_evidence(
        "PB-T11-shared-broker",
        (
            audit_event(
                "BROKER_ACTION_SET_VALIDATED", generation=generation, action_count=len(actions)
            ),
            audit_event("STANDARD_SELECTION_VALIDATED", handle=standard),
            audit_event(
                "EXPLORATORY_SELECTION_VALIDATED",
                handle=exploratory.selected_action,
                evaluation_fixture="SOL_RING_NET_USABLE_MANA_TWO",
            ),
            audit_event(
                "FIRST_DIVERGENCE_RECORDED",
                description=divergence.first_decision_divergence,
            ),
            audit_event("STALE_BROKER_HANDLE_REJECTED", reason=str(stale_error.value)),
        ),
        facts={"divergence_is_fixture_driven": True, "shared_handle_count": len(handles)},
    )


def test_pb_t12_replay_measurement_worker_evidence() -> None:
    state, executor, specs = funded_game("golden-t12", ("P0", "P1"))
    state.replay_initial_state = state.audit_dict()
    state.players["P1"].life = 1
    malcolm = add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    state.replay_initial_state = state.audit_dict()
    executor.deal_damage_to_player(malcolm.object_id, "P1", 1, combat=True)
    assert state.terminal.status == "TERMINAL"
    with pytest.raises(IllegalAction, match="game is terminal") as terminal_error:
        executor.pass_priority("P0")
    replay = replay_in_fresh_process(transcript(state, seed="golden-t12"), cwd=ROOT)
    original_hash = state_hash(state)
    assert replay.state_hash == original_hash
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
    assert measurement_digest((measurement,)) == digest
    raw = ({"game_index": 1, "seed": 11, "measurement_sha256": digest},)
    workers_a = verify_worker_invariance({1: raw, 4: tuple(reversed(raw))})
    workers_b = verify_worker_invariance({2: raw})
    assert workers_a == workers_b
    damage_event = next(event for event in state.events if event.kind == "DAMAGE_DEALT")
    terminal_event = next(event for event in state.events if event.kind == "GAME_TERMINATED")
    record_audit_evidence(
        "PB-T12-replay-invariance",
        (
            audit_event("DAMAGE_DEALT", event_id=damage_event.event_id),
            audit_event("GAME_TERMINATED", event_id=terminal_event.event_id),
            audit_event("POST_TERMINAL_ACTION_REJECTED", reason=str(terminal_error.value)),
            audit_event(
                "REPLAY_STATE_HASH_VALIDATED",
                original=original_hash,
                replayed=replay.state_hash,
            ),
            audit_event("MEASUREMENT_DIGEST_VALIDATED", sha256=digest),
            audit_event("WORKER_INVARIANCE_VALIDATED", canonical_digest=workers_a),
        ),
        facts={"thread_safety_claimed": False, "worker_configurations": [1, 2, 4]},
    )
