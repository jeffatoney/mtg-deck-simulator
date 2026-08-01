"""Phase B hand actions and deck-scoped resolution primitives.

The services in this module operate through the existing ``GameExecutor`` state,
identity, zone, payment, priority, trigger, and replay paths.  They do not create a
second executor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, TargetRef, Zone

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor

MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}

SplitKey: TypeAlias = tuple[
    int,
    int,
    tuple[tuple[str, int], ...],
    tuple[tuple[str, int], ...],
]

# Frozen, card-name-independent values used only for the resolved Fact or Fiction
# opponent choice.  The opponent minimizes the value of the pile the caster will
# select.  Later policy discovery is not permitted to rewrite these values.
_EFFECT_WEIGHTS: dict[str, int] = {
    "ADD_MANA": 10,
    "ADD_CHOSEN_MANA": 10,
    "ADD_COMMANDER_COLOR": 10,
    "ADD_OPPONENT_PROFILE_COLOR": 8,
    "CREATE_SPELL_COPY": 22,
    "CREATE_TOKEN_COPIES": 22,
    "DRAW": 12,
    "DRAW_DISCARD": 12,
    "DRAW_THEN_DISCARD_UNLESS_ATTACKED": 12,
    "LOOK_SELECT_REST_BOTTOM": 11,
    "SCRY": 5,
    "TRANSMUTE": 18,
    "TYPECYCLE": 16,
    "TUTOR_TYPES": 18,
    "TUTOR_THIRD_FROM_TOP": 16,
    "COUNTER": 14,
    "COUNTER_IF": 14,
    "COUNTER_UNLESS_PAY": 12,
    "COUNTER_UNLESS_PAY_EXILE": 14,
    "DESTROY": 12,
    "DESTROY_TARGETS": 12,
    "EXILE_TARGET": 14,
    "EXILE_CREATE_TOKEN": 16,
}


def _ability_by_id(source: GameObject, ability_id: str, kind: str) -> dict[str, Any]:
    abilities = source.current_characteristics.get("abilities", [])
    matches = [
        dict(value)
        for value in abilities
        if value.get("ability_id") == ability_id and value.get("kind") == kind
    ]
    if len(matches) != 1:
        raise IllegalAction(f"{kind.lower()} ability is unavailable")
    return matches[0]


def _require_priority(executor: GameExecutor, actor: str) -> None:
    if executor.state.turn.priority_holder_id != actor:
        raise IllegalAction("the acting player does not have priority")


def activate_hand_ability(
    executor: GameExecutor,
    actor: str,
    source_id: str,
    ability_id: str,
    targets: tuple[TargetRef, ...] = (),
    choices: dict[str, Any] | None = None,
    *,
    record: bool = True,
) -> GameObject:
    """Activate cycling, typecycling, or transmute from the source card in hand."""

    executor._ensure_active()
    before = executor._begin_atomic()
    choices = dict(choices or {})
    try:
        source = executor.state.objects[source_id]
        if source.retired or source.ceased_to_exist or source.zone is not Zone.HAND:
            raise IllegalAction("hand activated ability source is unavailable")
        if source.owner != actor:
            raise IllegalAction("a player may activate only a card they own in hand")
        _require_priority(executor, actor)
        selected = _ability_by_id(source, ability_id, "ACTIVATED")
        if selected.get("mana_ability"):
            raise IllegalAction("a hand-zone activated ability cannot be a mana ability")
        restriction = str(selected.get("restriction", ""))
        if restriction == "SORCERY_SPEED":
            if executor.state.turn.active_player_id != actor:
                raise IllegalAction("transmute requires the active player")
            if executor.state.turn.phase not in MAIN_PHASES or executor.state.stack:
                raise IllegalAction("transmute requires sorcery timing")
        elif restriction not in {"", "INSTANT"}:
            raise IllegalAction("unsupported hand-zone activation restriction")

        schema = dict(
            selected.get(
                "target_schema",
                {"kind": "NONE", "min": 0, "max": 0, "unique": True},
            )
        )
        executor._validate_targets(actor, targets, schema)
        cost = dict(selected.get("cost", {}))
        if int(cost.get("discard", 0)) != 1:
            raise IllegalAction("hand activation must discard its own source exactly once")
        mana_cost = parse_mana_cost(str(cost.get("mana", "")))
        payment = pay_mana(executor.state.players[actor].mana_pool, mana_cost)

        action = Action(
            executor.identity.new_id("action"),
            "ACTIVATE_HAND",
            actor,
            source_id,
            targets,
            (),
            0,
            {"mana": payment, "cost": mana_cost},
            {"ability_id": ability_id, "target_schema": schema, "choices": choices},
        )
        executor.state.actions.append(action)
        executor.state.target_records.append(
            {
                "action_id": action.action_id,
                "targets": [executor._target_data(target) for target in targets],
            }
        )
        activated_event = executor._event(
            "ABILITY_ACTIVATED", action, ability_id=ability_id, source_zone="HAND"
        )
        ability_object = GameObject(
            executor.identity.new_id("object"),
            ObjectKind.ACTIVATED_ABILITY,
            Zone.STACK,
            None,
            actor,
            source_object_id=source_id,
            created_by_event_id=activated_event.event_id,
            current_characteristics={"ability": selected},
            was_cast=False,
        )
        executor.state.objects[ability_object.object_id] = ability_object
        executor.zones.register(ability_object)
        executor.state.pending_actions.append(action.action_id)

        executor._discard_card(actor, source_id, action)
        executor.put_waiting_triggers_on_stack()
        executor.state.turn.priority_holder_id = actor
        executor.state.turn.consecutive_priority_passes = 0
        if record:
            executor._record_command(
                "activate_hand",
                actor=actor,
                source_id=source_id,
                ability_id=ability_id,
                targets=[executor._target_data(target) for target in targets],
                choices=choices,
            )
        return ability_object
    except Exception:
        executor._rollback(before)
        raise


def foretell(
    executor: GameExecutor,
    actor: str,
    card_object_id: str,
    ability_id: str,
    *,
    record: bool = True,
) -> GameObject:
    """Take the foretell special action without using the stack."""

    executor._ensure_active()
    before = executor._begin_atomic()
    try:
        card = executor.state.objects[card_object_id]
        if card.retired or card.ceased_to_exist or card.zone is not Zone.HAND:
            raise IllegalAction("foretell requires the card in its owner's hand")
        if card.owner != actor:
            raise IllegalAction("only the card's owner may foretell it")
        _require_priority(executor, actor)
        if executor.state.turn.active_player_id != actor:
            raise IllegalAction("foretell may be taken only during the acting player's turn")
        selected = _ability_by_id(card, ability_id, "SPECIAL_ACTION")
        effect = dict(selected.get("effect", {}))
        if effect.get("kind") != "FORETELL":
            raise IllegalAction("selected special action is not foretell")
        cost = dict(selected.get("cost", {}))
        mana_cost = parse_mana_cost(str(cost.get("mana", "")))
        payment = pay_mana(executor.state.players[actor].mana_pool, mana_cost)
        action = Action(
            executor.identity.new_id("action"),
            "FORETELL",
            actor,
            card_object_id,
            payments={"mana": payment, "cost": mana_cost},
            metadata={"ability_id": ability_id},
        )
        executor.state.actions.append(action)
        event = executor._event("CARD_FORETOLD", action, player_id=actor)
        successor = executor.zones.move(card_object_id, Zone.EXILE, "FORETELL", event)
        if successor is None:
            raise IllegalAction("foretell did not preserve the physical card")
        successor.nonbattlefield_orientation = "FACE_DOWN"
        successor.identity_visible_to = {actor}
        successor.current_characteristics["foretold"] = True
        successor.current_characteristics["foretold_by"] = actor
        successor.current_characteristics["foretold_turn"] = executor.state.turn.number
        successor.current_characteristics["foretell_cost"] = str(effect.get("cast_cost", ""))
        executor.state.turn.priority_holder_id = actor
        executor.state.turn.consecutive_priority_passes = 0
        if record:
            executor._record_command(
                "foretell",
                actor=actor,
                card_object_id=card_object_id,
                ability_id=ability_id,
            )
        return successor
    except Exception:
        executor._rollback(before)
        raise


def _deck_position(executor: GameExecutor, obj: GameObject) -> int:
    if not obj.component_card_instance_ids:
        return 2**31 - 1
    instance = executor.state.card_instances[obj.component_card_instance_ids[0]]
    return executor.state.deck_slots[instance.deck_slot_id].deck_source_position


def _library_objects(executor: GameExecutor, player_id: str) -> list[GameObject]:
    key = executor.zones.zone_key(Zone.LIBRARY, player_id)
    return [executor.state.objects[object_id] for object_id in executor.state.zones.get(key, [])]


def _matches_tutor(obj: GameObject, effect: dict[str, Any]) -> bool:
    kind = str(effect.get("kind", ""))
    if kind == "TRANSMUTE":
        return int(obj.current_characteristics.get("mana_value", -1)) == int(
            effect.get("mana_value", -2)
        )
    if kind == "TYPECYCLE":
        selector = str(effect.get("subtype", ""))
        if selector == "Basic Land":
            return "Basic" in obj.current_characteristics.get(
                "supertypes", []
            ) and "Land" in obj.current_characteristics.get("card_types", [])
        return selector in obj.current_characteristics.get("subtypes", [])
    return False


def legal_tutor_names(
    executor: GameExecutor, player_id: str, effect: dict[str, Any]
) -> tuple[str, ...]:
    """Return identities that may be selected without exposing library order or object IDs."""

    return tuple(
        sorted(
            {
                str(obj.current_characteristics.get("name", ""))
                for obj in _library_objects(executor, player_id)
                if _matches_tutor(obj, effect)
            }
        )
    )


def _search_to_hand(
    executor: GameExecutor,
    action: Action,
    effect: dict[str, Any],
    choices: dict[str, Any],
) -> None:
    eligible = [
        obj for obj in _library_objects(executor, action.actor_id) if _matches_tutor(obj, effect)
    ]
    selected_name = str(choices.get("tutor_name", ""))
    if selected_name == "FAIL_TO_FIND":
        selected: GameObject | None = None
    else:
        matches = [
            obj
            for obj in eligible
            if str(obj.current_characteristics.get("name", "")) == selected_name
        ]
        if not matches:
            raise IllegalAction("tutor choice does not name a legal card")
        selected = min(matches, key=lambda obj: _deck_position(executor, obj))

    choice_event = executor._event(
        "LIBRARY_SEARCH_CHOICE",
        action,
        search_kind=str(effect.get("kind", "")),
        selected_name=selected_name,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            str(effect.get("kind", "")),
            selected_name,
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


def _frozen_card_score(obj: GameObject) -> int:
    value = 10 + min(8, max(0, int(obj.current_characteristics.get("mana_value", 0))))
    card_types = set(str(item) for item in obj.current_characteristics.get("card_types", []))
    if "Land" in card_types:
        value += 12
    if "Creature" in card_types:
        value += 4
    for ability in obj.current_characteristics.get("abilities", []):
        effect = dict(ability.get("effect", {}))
        kind = str(effect.get("kind", ""))
        value += _EFFECT_WEIGHTS.get(kind, 0)
    return value


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
                {"selected": [], "score": 0},
                reveal_event.event_id,
            )
        )
        return

    candidates: list[
        tuple[
            SplitKey,
            list[GameObject],
            list[GameObject],
            int,
            int,
        ]
    ] = []
    # Piles are unordered while the opponent splits them, so require the first
    # revealed card in pile A to enumerate each legal split exactly once.
    for mask in range(1 << max(0, len(cards) - 1)):
        pile_a = [cards[0]]
        pile_b: list[GameObject] = []
        for offset, card in enumerate(cards[1:]):
            (pile_a if mask & (1 << offset) else pile_b).append(card)
        score_a = sum(_frozen_card_score(card) for card in pile_a)
        score_b = sum(_frozen_card_score(card) for card in pile_b)
        candidates.append(
            (
                (
                    max(score_a, score_b),
                    abs(score_a - score_b),
                    _pile_key(executor, pile_a),
                    _pile_key(executor, pile_b),
                ),
                pile_a,
                pile_b,
                score_a,
                score_b,
            )
        )
    _, pile_a, pile_b, score_a, score_b = min(candidates, key=lambda value: value[0])
    opponent_id = next(
        player_id
        for player_id, player in executor.state.players.items()
        if player.in_game and player_id != action.actor_id
    )
    split_event = executor._event(
        "FACT_OR_FICTION_SPLIT",
        action,
        opponent_id=opponent_id,
        pile_a=[str(card.current_characteristics.get("name", "")) for card in pile_a],
        pile_b=[str(card.current_characteristics.get("name", "")) for card in pile_b],
        score_a=score_a,
        score_b=score_b,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            opponent_id,
            "FACT_OR_FICTION_SPLIT",
            {
                "pile_a": [str(card.current_characteristics.get("name", "")) for card in pile_a],
                "pile_b": [str(card.current_characteristics.get("name", "")) for card in pile_b],
                "score_a": score_a,
                "score_b": score_b,
                "minimized_best_score": max(score_a, score_b),
            },
            split_event.event_id,
        )
    )
    choose_a = (score_a, len(pile_a), _pile_key(executor, pile_a)) >= (
        score_b,
        len(pile_b),
        _pile_key(executor, pile_b),
    )
    chosen, rejected = (pile_a, pile_b) if choose_a else (pile_b, pile_a)
    chosen_score = score_a if choose_a else score_b
    pile_event = executor._event(
        "FACT_OR_FICTION_PILE_CHOSEN",
        action,
        selected="A" if choose_a else "B",
        score=chosen_score,
    )
    executor.state.choices.append(
        Choice(
            executor.identity.new_id("choice"),
            action.actor_id,
            "FACT_OR_FICTION_PILE",
            {
                "selected": "A" if choose_a else "B",
                "cards": [str(card.current_characteristics.get("name", "")) for card in chosen],
                "score": chosen_score,
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
