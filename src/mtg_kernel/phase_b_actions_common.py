"""Phase B hand actions and deck-scoped resolution primitives.

The services in this module operate through the existing ``GameExecutor`` state,
identity, zone, payment, priority, trigger, and replay paths.  They do not create a
second executor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, TargetRef, Zone

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor

MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}

# Broker-visible actions are limited to effect primitives that the production
# executor can resolve without fallback.  This registry is deliberately smaller
# than the declarative deck composition and must expand only with competency
# evidence.
_BROKER_SUPPORTED_EFFECTS = frozenset(
    {
        "NONE",
        "ADD_MANA",
        "ADD_CHOSEN_MANA",
        "ATTACH_AURA",
        "CREATE_SPELL_COPY",
        "CREATE_TOKEN_COPIES",
        "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS",
        "DAMAGE",
        "DAMAGE_EACH_OPPONENT",
        "DESTROY",
        "DRAW",
        "EXILE_CREATE_TOKEN",
        "EXILE_OBJECTS",
        "EXILE_OPPONENT_GRAVEYARDS",
        "EXILE_TARGET",
        "FACT_OR_FICTION_MINIMIZING",
        "RECORD_UNKNOWN_BREECHES_EXILES",
        "SCRY",
        "TRANSMUTE",
        "TYPECYCLE",
    }
)
_BROKER_SUPPORTED_TRIGGERS = frozenset(
    {
        "CONTROLLER_DISCARDS",
        "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT",
        "ETB",
        "PIRATE_DAMAGE_TO_OPPONENTS",
    }
)
_BROKER_SUPPORTED_ENTRY_REPLACEMENTS = frozenset(
    {"CHOOSE_COLOR_ENTER_TAPPED", "ENTER_TAPPED", "REVEAL_OR_ENTER_TAPPED"}
)


def effect_execution_supported(effect: dict[str, Any]) -> bool:
    """Return whether the shared executor has a fail-closed implementation."""

    kind = str(effect.get("kind", "NONE"))
    if kind == "SEQUENCE":
        return all(effect_execution_supported(dict(child)) for child in effect.get("effects", ()))
    if kind == "SCRY":
        return int(effect.get("count", 1)) == 1
    return kind in _BROKER_SUPPORTED_EFFECTS


def _effect_requires_explicit_choice(effect: dict[str, Any]) -> bool:
    kind = str(effect.get("kind", "NONE"))
    if kind == "SEQUENCE":
        return any(
            _effect_requires_explicit_choice(dict(child)) for child in effect.get("effects", ())
        )
    return kind in {"ADD_CHOSEN_MANA", "SCRY"}


def automatic_ability_execution_supported(ability: dict[str, Any], *, entering: bool) -> bool:
    """Reject automatic behavior that could otherwise become a silent no-op."""

    kind = str(ability.get("kind", ""))
    effect = dict(ability.get("effect", {}))
    if kind in {"SPELL", "ACTIVATED", "SPECIAL_ACTION"}:
        return True
    if kind == "STATIC":
        return False
    if kind == "REPLACEMENT":
        if str(ability.get("event", "")) != "ENTERS_BATTLEFIELD":
            return False
        return str(effect.get("kind", "")) in _BROKER_SUPPORTED_ENTRY_REPLACEMENTS
    if kind != "TRIGGERED":
        return False
    trigger = str(ability.get("trigger", ""))
    if trigger == "ETB" and not entering:
        return True
    schema = dict(ability.get("target_schema", {}))
    return bool(
        trigger in _BROKER_SUPPORTED_TRIGGERS
        and effect_execution_supported(effect)
        and not ability.get("optional")
        and int(schema.get("max", 0) or 0) == 0
        and not _effect_requires_explicit_choice(effect)
    )


def object_automatic_execution_supported(obj: GameObject, *, entering: bool) -> bool:
    """Check every automatic ability that can affect this object's legal state."""

    return all(
        automatic_ability_execution_supported(dict(ability), entering=entering)
        for ability in obj.current_characteristics.get("abilities", ())
    )


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


def _spec_matches_tutor(spec: Any, effect: dict[str, Any]) -> bool:
    kind = str(effect.get("kind", ""))
    if kind == "TRANSMUTE":
        return int(spec.mana_value) == int(effect.get("mana_value", -2))
    if kind == "TYPECYCLE":
        selector = str(effect.get("subtype", ""))
        if selector == "Basic Land":
            return "Basic" in spec.supertypes and "Land" in spec.card_types
        return selector in spec.subtypes
    return False


def legal_tutor_names(
    executor: GameExecutor, player_id: str, effect: dict[str, Any]
) -> tuple[str, ...]:
    """Return deck-list candidates without inspecting current hidden library contents."""

    names: set[str] = set()
    for instance in executor.state.card_instances.values():
        if instance.owner_id != player_id or instance.commander_designation:
            continue
        spec = executor.state.card_specs[instance.card_spec_id]
        if _spec_matches_tutor(spec, effect):
            names.add(spec.name)
    return tuple(sorted(names))
