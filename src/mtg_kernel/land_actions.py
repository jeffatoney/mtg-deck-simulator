"""Production land-play rules service used by policy, scenarios, and replay."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mtg_kernel.engine_core import MAIN_PHASES, GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone


def play_land(
    executor: GameExecutor,
    actor: str,
    card_object_id: str,
    choices: dict[str, Any] | None = None,
    *,
    record: bool = True,
) -> GameObject:
    """Take the land-play special action through the clean production state path."""
    executor._ensure_active()
    before = executor._begin_atomic()
    choices = dict(choices or {})
    try:
        state = executor.state
        if state.turn.priority_holder_id != actor:
            raise IllegalAction("the land-playing player does not have priority")
        if actor != state.turn.active_player_id:
            raise IllegalAction("only the active player may play a land")
        if state.turn.phase not in MAIN_PHASES or state.stack:
            raise IllegalAction("land play requires an empty-stack main phase")
        if state.players[actor].land_plays_remaining <= 0:
            raise IllegalAction("no land play remains")
        card = state.objects[card_object_id]
        if card.retired or card.owner != actor or card.zone is not Zone.HAND:
            raise IllegalAction("land card is not in the player's hand")
        if "Land" not in executor._types(card):
            raise IllegalAction("selected card is not a land")

        action = Action(
            executor.identity.new_id("action"),
            "PLAY_LAND",
            actor,
            card_object_id,
            metadata={"choices": choices},
        )
        state.actions.append(action)

        enters_tapped = False
        chosen_color: str | None = None
        for ability in card.current_characteristics.get("abilities", []):
            if ability.get("kind") != "REPLACEMENT" or ability.get("event") != "ENTERS_BATTLEFIELD":
                continue
            effect = dict(ability.get("effect", {}))
            kind = str(effect.get("kind", ""))
            if kind == "ENTER_TAPPED":
                enters_tapped = True
            elif kind == "REVEAL_OR_ENTER_TAPPED":
                reveal_id = choices.get("reveal_object_id")
                if reveal_id is None:
                    selected = "DECLINE"
                    enters_tapped = True
                else:
                    reveal = state.objects.get(str(reveal_id))
                    allowed = set(str(value) for value in effect.get("subtypes", []))
                    legal = bool(
                        reveal
                        and reveal.object_id != card.object_id
                        and not reveal.retired
                        and reveal.zone is Zone.HAND
                        and reveal.owner == actor
                        and allowed.intersection(reveal.current_characteristics.get("subtypes", []))
                    )
                    if not legal:
                        raise IllegalAction("land entry reveal choice is not legal")
                    selected = str(reveal_id)
                choice_event = executor._event(
                    "LAND_REVEAL_CHOICE",
                    action,
                    revealed_object_id=selected if selected != "DECLINE" else None,
                )
                state.choices.append(
                    Choice(
                        executor.identity.new_id("choice"),
                        actor,
                        "REVEAL_FOR_LAND_ENTRY",
                        selected,
                        choice_event.event_id,
                    )
                )
            elif kind == "CHOOSE_COLOR_ENTER_TAPPED":
                selected = str(choices.get("chosen_color", ""))
                excluded = set(str(value) for value in effect.get("excluded", []))
                if selected not in {"W", "U", "B", "R", "G"} or selected in excluded:
                    raise IllegalAction("land entry requires an explicit legal color choice")
                chosen_color = selected
                enters_tapped = True
                choice_event = executor._event("LAND_COLOR_CHOSEN", action, color=selected)
                state.choices.append(
                    Choice(
                        executor.identity.new_id("choice"),
                        actor,
                        "LAND_ENTRY_COLOR",
                        selected,
                        choice_event.event_id,
                    )
                )
            else:
                raise UnsupportedCapability(f"unsupported land-entry replacement: {kind}")

        permanent = executor.zones.move(
            card.object_id,
            Zone.BATTLEFIELD,
            "LAND_PLAY",
            executor._event("LAND_PLAYED", action),
            object_kind=ObjectKind.PERMANENT,
            controller=actor,
        )
        if permanent is None or permanent.permanent_status is None:
            raise IllegalAction("land play did not create a permanent")
        permanent.current_characteristics["land_choices"] = deepcopy(choices)
        permanent.current_characteristics["cast_choices"] = deepcopy(choices)
        if chosen_color is not None:
            permanent.current_characteristics["chosen_color"] = chosen_color
        if enters_tapped:
            permanent.permanent_status["tap"] = "TAPPED"

        state.players[actor].land_plays_remaining -= 1
        executor._queue_etb(permanent)
        executor.put_waiting_triggers_on_stack()
        state.turn.priority_holder_id = actor
        state.turn.consecutive_priority_passes = 0
        if record:
            executor._record_command(
                "play_land", actor=actor, card_object_id=card_object_id, choices=choices
            )
        return permanent
    except Exception:
        executor._rollback(before)
        raise