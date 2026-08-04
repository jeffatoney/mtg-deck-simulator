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


def _attacked_this_turn(executor: Any, player_id: str) -> bool:
    """Return the exact-deck attack marker retained until cleanup."""

    return any(
        not obj.retired
        and not obj.ceased_to_exist
        and obj.controller == player_id
        and bool(obj.current_characteristics.get("attacking", False))
        for obj in executor.state.objects.values()
    )


def _look_select_rest_bottom(
    executor: Any,
    action: Action,
    *,
    look_count: int,
    select_count: int,
) -> None:
    if look_count < 0 or select_count < 0 or select_count > look_count:
        raise IllegalAction("look/select counts are invalid")
    key = executor.zones.zone_key(Zone.LIBRARY, action.actor_id)
    library = executor.state.zones.get(key, [])
    looked_ids = list(reversed(library[-look_count:])) if look_count else []
    looked = [executor.state.objects[object_id] for object_id in looked_ids]
    required = min(select_count, len(looked))
    selected = _select_cards(
        executor,
        action,
        purpose="LOOK_SELECT",
        candidates=looked,
        minimum=required,
        maximum=required,
    )
    selected_ids = {card.object_id for card in selected}
    remaining = [card for card in looked if card.object_id not in selected_ids]
    ordered_bottom = (
        _select_cards(
            executor,
            action,
            purpose="ORDER_LIBRARY_BOTTOM",
            candidates=remaining,
            minimum=len(remaining),
            maximum=len(remaining),
        )
        if remaining
        else []
    )

    for card in selected:
        moved = executor.zones.move(
            card.object_id,
            Zone.HAND,
            "LOOK_SELECT",
            executor._event(
                "LOOKED_CARD_PUT_IN_HAND",
                action,
                selected_object_id=card.object_id,
            ),
        )
        if moved is None:
            raise IllegalAction("look/select effect did not create a hand object")

    current_library = executor.state.zones.get(key, [])
    for card in remaining:
        if card.object_id not in current_library:
            raise IllegalAction("look/select remainder left the library unexpectedly")
        current_library.remove(card.object_id)
    current_library[0:0] = [card.object_id for card in ordered_bottom]
    executor._event(
        "LOOK_SELECT_REST_BOTTOM",
        action,
        looked_count=len(looked),
        selected_count=len(selected),
        bottom_count=len(ordered_bottom),
        bottom_order="BOTTOMMOST_FIRST",
    )


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
    if kind == "LOOK_SELECT_REST_BOTTOM":
        _look_select_rest_bottom(
            self,
            action,
            look_count=int(effect.get("look", 0)),
            select_count=int(effect.get("select", 0)),
        )
        return True
    if kind == "DRAW_DISCARD":
        _draw_then_discard(
            self,
            action,
            draw_count=int(effect.get("draw", 0)),
            discard_count=int(effect.get("discard", 0)),
        )
        return True
    if kind == "DRAW_THEN_DISCARD_UNLESS_ATTACKED":
        _draw_then_discard(
            self,
            action,
            draw_count=int(effect.get("draw", 0)),
            discard_count=(
                0 if _attacked_this_turn(self, action.actor_id) else int(effect.get("discard", 0))
            ),
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
