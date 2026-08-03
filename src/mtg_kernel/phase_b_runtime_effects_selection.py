"""Resolution-time card-selection effects for the exact-deck Phase B runtime."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, Zone
from mtg_kernel.phase_b_runtime_helpers import _untap
from mtg_kernel.strategic_choices import (
    CardSelectionRequest,
    PublicCard,
    require_provider,
)


def _active_zone_objects(
    executor: Any,
    zone: Zone,
    owner: str,
) -> list[GameObject]:
    key = executor.zones.zone_key(zone, owner)
    return [
        executor.state.objects[object_id]
        for object_id in executor.state.zones.get(key, ())
        if not executor.state.objects[object_id].retired
        and not executor.state.objects[object_id].ceased_to_exist
    ]


def _select_cards(
    executor: Any,
    action: Action,
    *,
    purpose: str,
    candidates: list[GameObject],
    minimum: int,
    maximum: int,
) -> list[GameObject]:
    if minimum < 0 or maximum < minimum or maximum > len(candidates):
        raise IllegalAction("resolution-time card-selection bounds are invalid")
    request_id = executor.identity.new_id("strategic-request")
    handles = {
        candidate.object_id: executor._strategic_handle(request_id, candidate.object_id)
        for candidate in candidates
    }
    public_cards = tuple(
        PublicCard(
            handle=handles[candidate.object_id],
            identity=str(candidate.current_characteristics.get("name", "")),
            mana_value=int(candidate.current_characteristics.get("mana_value", 0)),
            card_types=tuple(
                str(value) for value in candidate.current_characteristics.get("card_types", ())
            ),
            effect_kinds=executor._strategic_effect_kinds(candidate),
        )
        for candidate in candidates
    )
    provider = require_provider(
        getattr(executor, "strategic_choice_provider", None),
        f"{purpose.lower().replace('_', ' ')} selection",
    )
    selection = provider.choose_cards(
        CardSelectionRequest(
            request_id=request_id,
            actor_id=action.actor_id,
            ability_id=str(action.metadata.get("ability_id", "")),
            purpose=purpose,
            turn_number=executor.state.turn.number,
            observation=executor._strategic_observation(action.actor_id),
            candidates=public_cards,
            minimum=minimum,
            maximum=maximum,
        )
    )
    selected_handles = tuple(selection.selected_handles)
    legal_handles = set(handles.values())
    if len(selected_handles) != len(set(selected_handles)):
        raise IllegalAction("strategic provider selected a card more than once")
    if not set(selected_handles) <= legal_handles:
        raise IllegalAction("strategic provider selected an unavailable card")
    if not minimum <= len(selected_handles) <= maximum:
        raise IllegalAction("strategic provider selected an illegal number of cards")
    objects_by_handle = {
        handle: executor.state.objects[object_id] for object_id, handle in handles.items()
    }
    selected = [objects_by_handle[handle] for handle in selected_handles]
    event = executor._event(
        "STRATEGIC_CARD_SELECTION",
        action,
        purpose=purpose,
        selected_count=len(selected),
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "CARD_SELECTION",
            {
                "purpose": purpose,
                "selected_handles": list(selected_handles),
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": dict(selection.diagnostics),
                "chosen_at": "RESOLUTION",
            },
            event.event_id,
        )
    )
    return selected


def _draw_then_discard(
    executor: Any,
    action: Action,
    *,
    draw_count: int,
    discard_count: int,
) -> None:
    if draw_count < 0 or discard_count < 0:
        raise IllegalAction("draw and discard counts cannot be negative")
    for _ in range(draw_count):
        executor.draw_card(action.actor_id, action=action)
    hand = _active_zone_objects(executor, Zone.HAND, action.actor_id)
    required = min(discard_count, len(hand))
    selected = _select_cards(
        executor,
        action,
        purpose="DISCARD",
        candidates=hand,
        minimum=required,
        maximum=required,
    )
    for card in selected:
        executor._discard_card(action.actor_id, card.object_id, action)


def apply_effect_selection(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    del source, targets, choices
    kind = str(effect.get("kind", "NONE"))
    if kind == "DRAW_DISCARD":
        _draw_then_discard(
            self,
            action,
            draw_count=int(effect.get("draw", 0)),
            discard_count=int(effect.get("discard", 0)),
        )
        return True
    if kind != "DRAW_DISCARD_UNTAP_LANDS":
        return False
    _draw_then_discard(
        self,
        action,
        draw_count=int(effect.get("draw", 0)),
        discard_count=int(effect.get("discard", 0)),
    )
    tapped_lands = [
        permanent
        for permanent in self.state.objects.values()
        if not permanent.retired
        and not permanent.ceased_to_exist
        and self._is_permanent(permanent)
        and permanent.controller == action.actor_id
        and "Land" in permanent.current_characteristics.get("card_types", ())
        and permanent.permanent_status is not None
        and permanent.permanent_status.get("tap") == "TAPPED"
    ]
    maximum = min(int(effect.get("untap", 0)), len(tapped_lands))
    selected_lands = _select_cards(
        self,
        action,
        purpose="UNTAP_LANDS",
        candidates=tapped_lands,
        minimum=0,
        maximum=maximum,
    )
    _untap(self, selected_lands, action)
    return True
