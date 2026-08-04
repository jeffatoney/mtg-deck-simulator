"""Marked-mana tracking for Path of Ancestry and similar declarative effects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import GameObject
from mtg_kernel.phase_b_runtime_support import _subtypes, _types

MARKED_COMMANDER_MANA_KIND = "MARKED_COMMANDER_MANA"
PATH_SHARED_TYPE_TRIGGER = "MARKED_MANA_SPENT_ON_SHARED_CREATURE_TYPE"


def commander_color_identity(executor: Any, player_id: str) -> set[str]:
    """Return the declared commanders' color identity for one player."""

    colors: set[str] = set()
    for instance_id, owner_id in executor.state.commander_designations.items():
        if owner_id != player_id:
            continue
        instance = executor.state.card_instances.get(instance_id)
        if instance is None:
            continue
        spec = executor.state.card_specs.get(instance.card_spec_id)
        if spec is not None:
            colors.update(str(value) for value in spec.color_identity)
    return colors


def commander_creature_types(executor: Any, player_id: str) -> set[str]:
    """Return creature types printed on the player's declared commanders."""

    subtypes: set[str] = set()
    for instance_id, owner_id in executor.state.commander_designations.items():
        if owner_id != player_id:
            continue
        instance = executor.state.card_instances.get(instance_id)
        if instance is None:
            continue
        spec = executor.state.card_specs.get(instance.card_spec_id)
        if spec is not None and "Creature" in spec.card_types:
            subtypes.update(str(value) for value in spec.subtypes)
    return subtypes


def _selected_marker_ids(choices: Mapping[str, Any]) -> set[str] | None:
    raw = choices.get("marked_mana_event_ids")
    if raw is None:
        return None
    if not isinstance(raw, list) or any(not isinstance(value, str) for value in raw):
        raise IllegalAction("marked mana provenance must be a list of production event IDs")
    if len(raw) != len(set(raw)):
        raise IllegalAction("marked mana provenance IDs must be unique")
    return set(raw)


def _consume_markers(
    executor: Any,
    actor_id: str,
    payment: Mapping[str, Any],
    choices: Mapping[str, Any],
) -> list[dict[str, Any]]:
    markers = [
        record
        for record in executor.state.continuous_effects
        if record.get("kind") == MARKED_COMMANDER_MANA_KIND
        and record.get("player_id") == actor_id
    ]
    if not markers:
        return []

    selected_ids = _selected_marker_ids(choices)
    known_ids = {str(record.get("produced_event_id", "")) for record in markers}
    if selected_ids is not None and not selected_ids <= known_ids:
        raise IllegalAction("marked mana provenance selected an unavailable production event")

    consumed: list[dict[str, Any]] = []
    pool_after = executor.state.players[actor_id].mana_pool
    colors = sorted({str(record.get("color", "")) for record in markers})
    for color in colors:
        color_markers = [record for record in markers if record.get("color") == color]
        paid = int(payment.get(color, 0))
        available_after = int(pool_after.get(color, 0))
        total_before = available_after + paid
        marked_before = sum(int(record.get("amount", 1)) for record in color_markers)
        if marked_before > total_before:
            raise IllegalAction("marked mana ledger exceeds the available mana pool")
        unmarked_before = total_before - marked_before
        minimum_marked_spent = max(0, paid - unmarked_before)
        maximum_marked_spent = min(paid, marked_before)

        if selected_ids is None:
            if minimum_marked_spent != maximum_marked_spent:
                raise IllegalAction("marked mana payment requires an explicit provenance choice")
            selected_count = minimum_marked_spent
            selected_for_color = color_markers[:selected_count]
        else:
            selected_for_color = [
                record
                for record in color_markers
                if str(record.get("produced_event_id", "")) in selected_ids
            ]
            selected_count = sum(int(record.get("amount", 1)) for record in selected_for_color)
            if not minimum_marked_spent <= selected_count <= maximum_marked_spent:
                raise IllegalAction("selected marked mana provenance is incompatible with payment")
        consumed.extend(selected_for_color)

    if selected_ids is not None:
        consumed_ids = {str(record.get("produced_event_id", "")) for record in consumed}
        if consumed_ids != selected_ids:
            raise IllegalAction("selected marked mana provenance was not spent on this spell")

    consumed_identity = {id(record) for record in consumed}
    executor.state.continuous_effects = [
        record
        for record in executor.state.continuous_effects
        if id(record) not in consumed_identity
    ]
    return consumed


def _scry_decision(choices: Mapping[str, Any], event_id: str, count: int) -> bool:
    per_marker = choices.get("path_scry_to_bottom")
    if isinstance(per_marker, Mapping) and event_id in per_marker:
        return bool(per_marker[event_id])
    if count == 1 and "scry_to_bottom" in choices:
        return bool(choices["scry_to_bottom"])
    raise IllegalAction("Path of Ancestry trigger requires an explicit scry choice")


def process_marked_commander_mana(
    executor: Any,
    spell: GameObject,
    choices: Mapping[str, Any],
) -> None:
    """Consume marked payment and queue qualifying shared-type triggers."""

    action = executor._created_action(spell)
    consumed = _consume_markers(
        executor,
        action.actor_id,
        dict(action.payments.get("mana", {})),
        choices,
    )
    if not consumed or "Creature" not in _types(spell):
        return
    if not _subtypes(spell).intersection(commander_creature_types(executor, action.actor_id)):
        return

    queued = 0
    for record in consumed:
        source_id = str(record.get("source_object_id", ""))
        source = executor.state.objects.get(source_id)
        if source is None or not executor._is_permanent(source) or source.controller != action.actor_id:
            continue
        ability = record.get("trigger_ability")
        if not isinstance(ability, dict) or ability.get("trigger") != PATH_SHARED_TYPE_TRIGGER:
            raise IllegalAction("marked mana record has no supported shared-type trigger")
        produced_event_id = str(record.get("produced_event_id", ""))
        decision = _scry_decision(choices, produced_event_id, len(consumed))
        executor._queue_trigger(
            source,
            dict(ability),
            {
                "spell_object_id": spell.object_id,
                "produced_event_id": produced_event_id,
            },
            {"scry_to_bottom": decision},
        )
        queued += 1
    if queued:
        executor.put_waiting_triggers_on_stack()
