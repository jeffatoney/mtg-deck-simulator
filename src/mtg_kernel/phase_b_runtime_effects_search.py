"""Hidden-zone search effects for the exact-deck Phase B runtime."""

from __future__ import annotations

import hashlib
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.strategic_choices import PublicCard, TutorChoiceRequest, require_provider


def _deck_position(executor: Any, obj: GameObject) -> int:
    if not obj.component_card_instance_ids:
        return 2**31 - 1
    instance = executor.state.card_instances[obj.component_card_instance_ids[0]]
    return executor.state.deck_slots[instance.deck_slot_id].deck_source_position


def _choice_handle(request_id: str, object_id: str) -> str:
    return hashlib.sha256(f"strategic-choice:{request_id}:{object_id}".encode()).hexdigest()[:24]


def _observation(executor: Any, actor_id: str) -> dict[str, Any]:
    observation = ObservationService(executor.state).observe_for_policy(actor_id)
    observation["mana_pool"] = dict(executor.state.players[actor_id].mana_pool)
    observation["land_played_this_turn"] = bool(
        getattr(executor.state.turn, "land_played_this_turn", False)
    )
    return observation


def _basic_lands(executor: Any, actor_id: str) -> list[GameObject]:
    key = executor.zones.zone_key(Zone.LIBRARY, actor_id)
    return [
        executor.state.objects[object_id]
        for object_id in executor.state.zones.get(key, ())
        if "Basic"
        in executor.state.objects[object_id].current_characteristics.get("supertypes", ())
        and "Land"
        in executor.state.objects[object_id].current_characteristics.get("card_types", ())
    ]


def _fetch_basic(executor: Any, action: Action) -> None:
    eligible = _basic_lands(executor, action.actor_id)
    eligible_identities = tuple(
        sorted({str(obj.current_characteristics.get("name", "")) for obj in eligible})
    )
    request_id = executor.identity.new_id("strategic-request")
    provider = require_provider(
        getattr(executor, "strategic_choice_provider", None),
        "basic-land search resolution",
    )
    selection = provider.choose_tutor(
        TutorChoiceRequest(
            request_id=request_id,
            actor_id=action.actor_id,
            ability_id=str(action.metadata.get("ability_id", "")),
            turn_number=executor.state.turn.number,
            observation=_observation(executor, action.actor_id),
            eligible_identities=eligible_identities,
            eligible_cards=tuple(
                PublicCard(
                    handle=_choice_handle(request_id, obj.object_id),
                    identity=str(obj.current_characteristics.get("name", "")),
                    mana_value=int(obj.current_characteristics.get("mana_value", 0)),
                    card_types=tuple(
                        str(value) for value in obj.current_characteristics.get("card_types", ())
                    ),
                    effect_kinds=(),
                )
                for obj in eligible
            ),
        )
    )
    selected_name = selection.selected_identity
    if selected_name != "FAIL_TO_FIND" and selected_name not in eligible_identities:
        raise IllegalAction("strategic tutor provider selected an ineligible basic land")
    matches = [
        obj for obj in eligible if str(obj.current_characteristics.get("name", "")) == selected_name
    ]
    selected = min(matches, key=lambda obj: _deck_position(executor, obj)) if matches else None
    if selected is None:
        selected_name = "FAIL_TO_FIND"

    choice_event = executor._event(
        "LIBRARY_SEARCH_CHOICE",
        action,
        search_kind="FETCH_BASIC",
        selected_name=selected_name,
        evaluator_id=selection.evaluator_id,
        evaluator_sha256=selection.evaluator_sha256,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "FETCH_BASIC",
            {
                "identity": selected_name,
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": dict(selection.diagnostics),
                "chosen_at": "RESOLUTION",
            },
            choice_event.event_id,
        )
    )
    if selected is not None:
        reveal_event = executor._event(
            "SEARCH_CARD_REVEALED",
            action,
            player_id=action.actor_id,
            object_id=selected.object_id,
            identity=selected_name,
        )
        permanent = executor.zones.move(
            selected.object_id,
            Zone.BATTLEFIELD,
            "FETCH_BASIC",
            reveal_event,
            object_kind=ObjectKind.PERMANENT,
            controller=action.actor_id,
        )
        if permanent is None or permanent.permanent_status is None:
            raise IllegalAction("searched basic land did not enter the battlefield")
        permanent.permanent_status["tap"] = "TAPPED"
        executor._queue_etb(permanent)
    executor.shuffle_library(action.actor_id, action)


def apply_effect_search(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    del source, targets, choices
    if str(effect.get("kind", "NONE")) != "FETCH_BASIC":
        return False
    _fetch_basic(self, action)
    return True
