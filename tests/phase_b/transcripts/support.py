"""Shared support for runtime-bound Phase B transcript evidence tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import new_game
from mtg_kernel.models import Zone
from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)

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
