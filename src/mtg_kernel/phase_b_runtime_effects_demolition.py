"""Demolition Field resolution for the exact-deck Phase B runtime."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_effects_search import (
    _basic_lands,
    _choice_handle,
    _deck_position,
    _observation,
)
from mtg_kernel.phase_b_runtime_helpers import _destroy
from mtg_kernel.strategic_choices import PublicCard, TutorChoiceRequest, require_provider


def _search_basic_for_player(
    executor: Any,
    action: Action,
    player_id: str,
    *,
    search_role: str,
) -> None:
    eligible = _basic_lands(executor, player_id)
    eligible_identities = tuple(
        sorted({str(obj.current_characteristics.get("name", "")) for obj in eligible})
    )
    request_id = executor.identity.new_id("strategic-request")
    provider = require_provider(
        getattr(executor, "strategic_choice_provider", None),
        "Demolition Field basic-land search resolution",
    )
    selection = provider.choose_tutor(
        TutorChoiceRequest(
            request_id=request_id,
            actor_id=player_id,
            ability_id=str(action.metadata.get("ability_id", "")),
            turn_number=executor.state.turn.number,
            observation=_observation(executor, player_id),
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
        search_kind="DEMOLITION_FIELD",
        search_role=search_role,
        player_id=player_id,
        selected_name=selected_name,
        evaluator_id=selection.evaluator_id,
        evaluator_sha256=selection.evaluator_sha256,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            player_id,
            "FETCH_BASIC",
            {
                "identity": selected_name,
                "search_kind": "DEMOLITION_FIELD",
                "search_role": search_role,
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
            player_id=player_id,
            object_id=selected.object_id,
            identity=selected_name,
            search_kind="DEMOLITION_FIELD",
            search_role=search_role,
        )
        permanent = executor.zones.move(
            selected.object_id,
            Zone.BATTLEFIELD,
            "DEMOLITION_FIELD",
            reveal_event,
            object_kind=ObjectKind.PERMANENT,
            controller=player_id,
        )
        if permanent is None or permanent.permanent_status is None:
            raise IllegalAction("searched basic land did not enter the battlefield")
        permanent.permanent_status["tap"] = "UNTAPPED"
        executor._queue_etb(permanent)
    executor.shuffle_library(player_id, action)


def apply_demolition_field(
    executor: Any,
    action: Action,
    targets: list[GameObject],
) -> None:
    """Destroy the target and resolve both optional basic-land searches in order."""

    if len(targets) != 1:
        raise IllegalAction("Demolition Field requires one legal land target")
    target = targets[0]
    target_controller = target.controller or target.owner
    if target_controller is None:
        raise IllegalAction("Demolition Field target has no controller or owner")

    _destroy(executor, target, action, "DEMOLITION_FIELD")
    _search_basic_for_player(
        executor,
        action,
        target_controller,
        search_role="DESTROYED_LAND_CONTROLLER",
    )
    _search_basic_for_player(
        executor,
        action,
        action.actor_id,
        search_role="ABILITY_CONTROLLER",
    )
