"""Strategic resolution choices and policy-attributed Phase B effects."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.phase_b_actions_common import (
    _deck_position,
    _library_objects,
    _matches_tutor,
)
from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSplit,
    PublicCard,
    TutorChoiceRequest,
    require_provider,
)

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor


def _strategic_observation(executor: GameExecutor, actor_id: str) -> dict[str, Any]:
    """Create a fresh hidden-information-safe observation for a strategic choice."""

    observation = ObservationService(executor.state).observe_for_policy(actor_id)
    observation["mana_pool"] = dict(executor.state.players[actor_id].mana_pool)
    observation["land_played_this_turn"] = bool(
        getattr(executor.state.turn, "land_played_this_turn", False)
    )
    return observation


def _choice_handle(request_id: str, object_id: str) -> str:
    return hashlib.sha256(f"strategic-choice:{request_id}:{object_id}".encode()).hexdigest()[:24]


def _effect_kinds(obj: GameObject) -> tuple[str, ...]:
    kinds: set[str] = set()
    for ability in obj.current_characteristics.get("abilities", ()):
        effect = ability.get("effect", {})
        if not isinstance(effect, dict):
            continue
        kind = str(effect.get("kind", "")).strip()
        if kind:
            kinds.add(kind)
        for child in effect.get("effects", ()):
            if isinstance(child, dict):
                child_kind = str(child.get("kind", "")).strip()
                if child_kind:
                    kinds.add(child_kind)
    return tuple(sorted(kinds))


def _search_to_hand(
    executor: GameExecutor,
    action: Action,
    effect: dict[str, Any],
    choices: dict[str, Any],
) -> None:
    """Resolve a hidden-zone search with the identity chosen at resolution time."""

    del choices
    eligible = [
        obj for obj in _library_objects(executor, action.actor_id) if _matches_tutor(obj, effect)
    ]
    eligible_identities = tuple(
        sorted({str(obj.current_characteristics.get("name", "")) for obj in eligible})
    )
    request_id = executor.identity.new_id("strategic-request")
    provider = require_provider(
        executor.strategic_choice_provider,
        f"{str(effect.get('kind', 'library search'))} resolution",
    )
    selection = provider.choose_tutor(
        TutorChoiceRequest(
            request_id=request_id,
            actor_id=action.actor_id,
            ability_id=str(action.metadata.get("ability_id", "")),
            turn_number=executor.state.turn.number,
            observation=_strategic_observation(executor, action.actor_id),
            eligible_identities=eligible_identities,
            eligible_cards=tuple(
                PublicCard(
                    handle=_choice_handle(request_id, obj.object_id),
                    identity=str(obj.current_characteristics.get("name", "")),
                    mana_value=int(obj.current_characteristics.get("mana_value", 0)),
                    card_types=tuple(
                        str(value) for value in obj.current_characteristics.get("card_types", ())
                    ),
                    effect_kinds=_effect_kinds(obj),
                )
                for obj in eligible
            ),
        )
    )
    selected_name = selection.selected_identity
    if selected_name != "FAIL_TO_FIND" and selected_name not in eligible_identities:
        raise IllegalAction("strategic tutor provider selected an ineligible identity")
    matches = [
        obj for obj in eligible if str(obj.current_characteristics.get("name", "")) == selected_name
    ]
    selected = min(matches, key=lambda obj: _deck_position(executor, obj)) if matches else None
    if selected is None:
        selected_name = "FAIL_TO_FIND"

    selected_record = {
        "identity": selected_name,
        "evaluator_id": selection.evaluator_id,
        "evaluator_sha256": selection.evaluator_sha256,
        "diagnostics": dict(selection.diagnostics),
        "chosen_at": "RESOLUTION",
    }
    choice_event = executor._event(
        "LIBRARY_SEARCH_CHOICE",
        action,
        search_kind=str(effect.get("kind", "")),
        selected_name=selected_name,
        evaluator_id=selection.evaluator_id,
        evaluator_sha256=selection.evaluator_sha256,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            str(effect.get("kind", "")),
            selected_record,
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
        moved = executor.zones.move(selected.object_id, Zone.HAND, "SEARCH_TO_HAND", reveal_event)
        if moved is None:
            raise IllegalAction("searched physical card did not reach hand")
    executor.shuffle_library(action.actor_id, action)


def _pile_key(executor: GameExecutor, cards: list[GameObject]) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(
            (
                str(card.current_characteristics.get("name", "")),
                _deck_position(executor, card),
            )
            for card in cards
        )
    )


def _fact_or_fiction(executor: GameExecutor, action: Action, effect: dict[str, Any]) -> None:
    """Enumerate legal piles in the kernel and delegate valuation to policy."""

    key = executor.zones.zone_key(Zone.LIBRARY, action.actor_id)
    library = executor.state.zones.get(key, [])
    count = min(int(effect.get("reveal", 5)), len(library))
    cards = [executor.state.objects[object_id] for object_id in reversed(library[-count:])]
    reveal_event = executor._event(
        "FACT_OR_FICTION_REVEALED",
        action,
        cards=[
            {
                "object_id": card.object_id,
                "identity": str(card.current_characteristics.get("name", "")),
            }
            for card in cards
        ],
    )
    if not cards:
        executor.state.choices.append(
            Choice(
                executor.identity.new_id("choice"),
                action.actor_id,
                "FACT_OR_FICTION_PILE",
                {
                    "selected": [],
                    "evaluator_id": "NO_CARDS",
                    "evaluator_sha256": "0" * 64,
                    "diagnostics": {},
                },
                reveal_event.event_id,
            )
        )
        return

    request_id = executor.identity.new_id("strategic-request")
    handles = {card.object_id: _choice_handle(request_id, card.object_id) for card in cards}
    public_cards = tuple(
        PublicCard(
            handle=handles[card.object_id],
            identity=str(card.current_characteristics.get("name", "")),
            mana_value=int(card.current_characteristics.get("mana_value", 0)),
            card_types=tuple(
                str(value) for value in card.current_characteristics.get("card_types", ())
            ),
            effect_kinds=_effect_kinds(card),
        )
        for card in cards
    )
    internal_splits: list[tuple[list[GameObject], list[GameObject]]] = []
    legal_splits: list[FactOrFictionSplit] = []
    # Piles are unordered while the opponent splits them, so require the first
    # revealed card in pile A to enumerate each legal split exactly once.
    for mask in range(1 << max(0, len(cards) - 1)):
        pile_a = [cards[0]]
        pile_b: list[GameObject] = []
        for offset, card in enumerate(cards[1:]):
            (pile_a if mask & (1 << offset) else pile_b).append(card)
        split_index = len(internal_splits)
        internal_splits.append((pile_a, pile_b))
        legal_splits.append(
            FactOrFictionSplit(
                split_index,
                tuple(handles[card.object_id] for card in pile_a),
                tuple(handles[card.object_id] for card in pile_b),
            )
        )

    opponent_id = next(
        player_id
        for player_id, player in executor.state.players.items()
        if player.in_game and player_id != action.actor_id
    )
    provider = require_provider(
        executor.strategic_choice_provider,
        "Fact or Fiction split and pile selection",
    )
    selection = provider.choose_fact_or_fiction(
        FactOrFictionRequest(
            request_id=request_id,
            actor_id=action.actor_id,
            opponent_id=opponent_id,
            turn_number=executor.state.turn.number,
            observation=_strategic_observation(executor, action.actor_id),
            revealed_cards=public_cards,
            legal_splits=tuple(legal_splits),
        )
    )
    if not 0 <= selection.split_index < len(internal_splits):
        raise IllegalAction("strategic provider selected an illegal Fact or Fiction split")
    pile_a, pile_b = internal_splits[selection.split_index]
    split_public = legal_splits[selection.split_index]
    if selection.chosen_pile not in {"A", "B"}:
        raise IllegalAction("strategic provider selected an invalid Fact or Fiction pile")

    diagnostics = dict(selection.diagnostics)
    split_event = executor._event(
        "FACT_OR_FICTION_SPLIT",
        action,
        opponent_id=opponent_id,
        split_index=selection.split_index,
        pile_a=[str(card.current_characteristics.get("name", "")) for card in pile_a],
        pile_b=[str(card.current_characteristics.get("name", "")) for card in pile_b],
        evaluator_id=selection.evaluator_id,
        evaluator_sha256=selection.evaluator_sha256,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            opponent_id,
            "FACT_OR_FICTION_SPLIT",
            {
                "split_index": selection.split_index,
                "pile_a_handles": list(split_public.pile_a_handles),
                "pile_b_handles": list(split_public.pile_b_handles),
                "pile_a": [str(card.current_characteristics.get("name", "")) for card in pile_a],
                "pile_b": [str(card.current_characteristics.get("name", "")) for card in pile_b],
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": diagnostics,
            },
            split_event.event_id,
        )
    )
    chosen, rejected = (pile_a, pile_b) if selection.chosen_pile == "A" else (pile_b, pile_a)
    pile_event = executor._event(
        "FACT_OR_FICTION_PILE_CHOSEN",
        action,
        selected=selection.chosen_pile,
        evaluator_id=selection.evaluator_id,
        evaluator_sha256=selection.evaluator_sha256,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "FACT_OR_FICTION_PILE",
            {
                "selected": selection.chosen_pile,
                "cards": [str(card.current_characteristics.get("name", "")) for card in chosen],
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": diagnostics,
            },
            pile_event.event_id,
        )
    )
    for card in chosen:
        executor.zones.move(card.object_id, Zone.HAND, "FACT_OR_FICTION_TO_HAND", pile_event)
    for card in rejected:
        executor.zones.move(
            card.object_id,
            Zone.GRAVEYARD,
            "FACT_OR_FICTION_TO_GRAVEYARD",
            pile_event,
        )


def _create_token(
    executor: GameExecutor,
    controller: str,
    action: Action,
    token_spec: dict[str, Any],
) -> GameObject:
    name = str(token_spec.get("name", "Token"))
    event = executor._event(
        "TOKEN_CREATED",
        action,
        controller=controller,
        token_name=name,
    )
    characteristics: dict[str, Any] = {
        "name": name,
        "card_types": list(token_spec.get("card_types", ["Creature"])),
        "subtypes": list(token_spec.get("subtypes", [])),
        "colors": list(token_spec.get("colors", [])),
        "keywords": list(token_spec.get("keywords", [])),
        "abilities": list(token_spec.get("abilities", [])),
    }
    if "power" in token_spec:
        characteristics["power"] = int(token_spec["power"])
    if "toughness" in token_spec:
        characteristics["toughness"] = int(token_spec["toughness"])
    token = GameObject(
        executor.identity.new_id("object"),
        ObjectKind.TOKEN_OBJECT,
        Zone.BATTLEFIELD,
        controller,
        controller,
        created_by_event_id=event.event_id,
        current_characteristics=characteristics,
        permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"},
        identity_visible_to=set(executor.state.players),
    )
    executor.state.objects[token.object_id] = token
    executor.zones.register(token)
    executor._queue_etb(token)
    return token


def _exile_create_token(
    executor: GameExecutor,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
) -> None:
    if len(targets) != 1:
        raise IllegalAction("exile-and-token effect requires exactly one legal target")
    target = targets[0]
    controller = target.controller or target.owner
    if controller is None:
        raise IllegalAction("target has no player to create the token")
    exile_event = executor._event(
        "OBJECT_EXILED",
        action,
        target_object_id=target.object_id,
    )
    executor.zones.move(target.object_id, Zone.EXILE, "EXILE", exile_event)
    token_spec = effect.get("token")
    if not isinstance(token_spec, dict):
        raise IllegalAction("exile-and-token effect omits its token specification")
    _create_token(executor, controller, action, dict(token_spec))


def apply_phase_b_effect(
    executor: GameExecutor,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    """Apply one Phase B primitive and report whether it was handled."""

    del source
    kind = str(effect.get("kind", ""))
    if kind in {"TRANSMUTE", "TYPECYCLE"}:
        _search_to_hand(executor, action, effect, choices)
        return True
    if kind == "FACT_OR_FICTION_MINIMIZING":
        _fact_or_fiction(executor, action, effect)
        return True
    if kind == "EXILE_CREATE_TOKEN":
        _exile_create_token(executor, action, effect, targets)
        return True
    return False
