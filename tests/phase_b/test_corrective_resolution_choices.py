from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping, Sequence
from typing import Any

from mtg_deck import build_exact_game
from mtg_kernel.models import CopyKind, TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy import (
    ActionBroker,
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

PLAYERS = ("P0", "P1", "P2", "P3")


def pass_round(executor: Any) -> None:
    living = [p.player_id for p in executor.state.players.values() if p.in_game]
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


def provider() -> PolicyStrategicChoiceProvider:
    return PolicyStrategicChoiceProvider(
        load_policy_matrix()[0], ContextualEvaluator(load_evaluator_config())
    )


def test_exact_deck_transmute_selects_singleton_at_resolution() -> None:
    state, executor, created = build_exact_game("corrective-transmute", PLAYERS)
    all_library = list(created["library"])
    dizzy = move_named(executor, all_library, "Dizzy Spell", Zone.HAND)
    executor.bind_strategic_choice_provider(TutorOverrideProvider(provider(), "Sol Ring"))
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({s: 0 for s in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 2
    state.players["P0"].mana_pool["C"] = 1
    observation, actions = ActionBroker(executor, "P0").refresh()
    transmute = [a for a in actions if a.kind == "ACTIVATE_HAND" and a.identity == "Dizzy Spell"]
    assert (
        len(transmute) == 1
        and transmute[0].metadata["choice_timing"] == "RESOLUTION"
        and "Sol Ring" in transmute[0].metadata["eligible_tutor_identities"]
    )
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    action = next(a for a in actions if a.kind == "ACTIVATE_HAND" and a.identity == "Dizzy Spell")
    broker.execute(int(observation["generation"]), action.handle)
    assert not any(c.kind == "TRANSMUTE" for c in state.choices)
    pass_round(executor)
    rings = [
        o
        for o in state.objects.values()
        if not o.retired
        and o.zone is Zone.HAND
        and o.current_characteristics.get("name") == "Sol Ring"
    ]
    assert len(rings) == 1
    choice = next(c for c in state.choices if c.kind == "TRANSMUTE")
    assert (
        choice.selected["identity"] == "Sol Ring"
        and choice.selected["chosen_at"] == "RESOLUTION"
        and dizzy.retired
    )


def test_exact_deck_fact_or_fiction_keeps_twinflame_over_excess_lands() -> None:
    state, executor, created = build_exact_game("corrective-fact", PLAYERS)
    library = list(created["library"])
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    executor.bind_strategic_choice_provider(provider())
    for _ in range(3):
        move_named(executor, library, "Island", Zone.BATTLEFIELD)
        library = [o for o in library if not o.retired]
    fact = move_named(executor, library, "Fact or Fiction", Zone.HAND)
    library = [o for o in library if not o.retired]
    move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [o for o in library if not o.retired]
    reveal = []
    for name in ["Island", "Island", "Island", "Mountain", "Twinflame"]:
        obj = next(
            o for o in library if not o.retired and o.current_characteristics.get("name") == name
        )
        reveal.append(obj)
        library.remove(obj)
    zone = state.zones[executor.zones.zone_key(Zone.LIBRARY, "P0")]
    for obj in reveal:
        zone.remove(obj.object_id)
    zone.extend(obj.object_id for obj in reversed(reveal))
    state.players["P0"].mana_pool.update({s: 0 for s in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 1
    state.players["P0"].mana_pool["C"] = 3
    executor.cast("P0", fact.object_id)
    pass_round(executor)
    chosen = next(c for c in state.choices if c.kind == "FACT_OR_FICTION_PILE")
    assert (
        "Twinflame" in chosen.selected["cards"]
        and chosen.selected["evaluator_id"] == "contextual_combo_v1"
    )
    replayed = validate_replay(transcript(state, seed="corrective-fact"))
    assert (
        next(c for c in replayed.choices if c.kind == "FACT_OR_FICTION_PILE").selected
        == chosen.selected
    )


def test_actual_dualcaster_twinflame_line_is_bounded_by_policy_choice() -> None:
    state, executor, created = build_exact_game("corrective-dualcaster", ("P0", "P1"))
    library = list(created["library"])
    executor.bind_strategic_choice_provider(LoopWitnessProvider(provider(), 2))
    state.turn.phase = "PRECOMBAT_MAIN"
    dualcaster = move_named(executor, library, "Dualcaster Mage", Zone.HAND)
    library = [o for o in library if not o.retired]
    twinflame = move_named(executor, library, "Twinflame", Zone.HAND)
    malcolm = move_named(
        executor, list(created["command"]), "Malcolm, Keen-Eyed Navigator", Zone.BATTLEFIELD
    )
    state.players["P0"].mana_pool.update({s: 0 for s in state.players["P0"].mana_pool})
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
        o
        for o in state.objects.values()
        if not o.retired
        and o.copy_kind is CopyKind.TOKEN_COPY
        and o.current_characteristics.get("name") == "Dualcaster Mage"
    ]
    assert len(tokens) == 2
    copies = [
        o
        for o in state.objects.values()
        if o.copy_kind is CopyKind.SPELL_COPY
        and o.current_characteristics.get("name") == "Twinflame"
    ]
    assert copies and all(c.was_cast is False and not c.component_card_instance_ids for c in copies)
    strategies = [
        c.selected.get("diagnostics", {}).get("strategy")
        for c in state.choices
        if c.kind == "COPY_TARGETS" and isinstance(c.selected, dict)
    ]
    assert (
        "CONTINUE_BOUNDED_DUALCASTER_LOOP" in strategies
        and "STOP_BOUNDED_DUALCASTER_LOOP" in strategies
    )
