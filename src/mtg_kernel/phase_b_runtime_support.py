"""Phase B support registry and exact-deck target-schema extensions."""

from __future__ import annotations

from typing import Any, Callable, cast

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import GameObject, ObjectKind, TargetRef, Zone

SUPPORTED_EFFECTS = frozenset(
    {
        "NONE",
        "ADD_BLUE_OR_FIXED_CHOSEN",
        "ADD_CHOSEN_MANA",
        "ADD_CHOSEN_MANA_AND_DAMAGE_SELF",
        "ADD_COMMANDER_COLOR",
        "ADD_MANA",
        "ADD_OPPONENT_PROFILE_COLOR",
        "AMASS_AND_HEXPROOF",
        "ATTACH_AURA",
        "BOUNCE_ALL_ARTIFACTS",
        "BOUNCE_AND_CONDITIONAL_SCRY",
        "BOUNCE_AND_KICKER_DRAW",
        "BOUNCE_ATTACKING_CREATURES",
        "BOUNCE_TARGET",
        "BOUNCE_TARGETS",
        "CANT_BE_BLOCKED",
        "COUNTER",
        "COUNTER_IF",
        "COUNTER_TARGETING_CONTROLLER",
        "COUNTER_UNLESS_PAY",
        "COUNTER_UNLESS_PAY_EXILE",
        "CREATE_SPELL_COPY",
        "CREATE_TOKEN_COPIES",
        "CREATE_TREASURE",
        "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS",
        "DAMAGE",
        "DAMAGE_ALL_CREATURES_PLANESWALKERS",
        "DAMAGE_ALL_NON_SUBTYPE",
        "DAMAGE_ANY_TARGET",
        "DAMAGE_EACH_OPPONENT",
        "DESTROY",
        "DESTROY_ALL_OPPONENT_ARTIFACTS",
        "DESTROY_ARTIFACTS_MV_LEQ",
        "DESTROY_TARGETS",
        "DRAW",
        "DRAW_DISCARD",
        "DRAW_DISCARD_UNTAP_LANDS",
        "EACH_OPPONENT_LOSES_LIFE",
        "ECHOING_BOUNCE",
        "EXILE_ALL_GRAVEYARDS",
        "EXILE_CREATE_TOKEN",
        "EXILE_CREATURES_CREATE_BOARS",
        "EXILE_OBJECTS",
        "EXILE_OPPONENT_GRAVEYARDS",
        "EXILE_TARGET",
        "EXILE_THEN_CONTROLLER_DRAWS",
        "FACT_OR_FICTION_MINIMIZING",
        "FETCH_BASIC",
        "FILTER_MANA_OPTIONS",
        "FORETELL",
        "GRANT_HASTE",
        "HAND_SIZE_POWER_TOUGHNESS",
        "KEYWORD",
        "LIBRARY_SECOND",
        "LOOK_SELECT_REST_BOTTOM",
        "MEMORY",
        "MODIFY_POWER_TOUGHNESS",
        "PHASE_OUT",
        "RECORD_UNKNOWN_BREECHES_EXILES",
        "RETURN_CONTROLLED_LAND",
        "SCRY",
        "SEQUENCE",
        "SWITCH_POWER_TOUGHNESS",
        "TRANSMUTE",
        "TUTOR_THIRD_FROM_TOP",
        "TUTOR_TYPES",
        "TYPECYCLE",
        "UMBRA_ARMOR",
        "UNTAP_ATTACHED",
        "UNTAP_SOURCE",
    }
)

SUPPORTED_NO_CHOICE_TRIGGERS = frozenset(
    {
        "CONTROLLER_CASTS_PIRATE",
        "CONTROLLER_DISCARDS",
        "CONTROLLER_DRAWS",
        "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT",
        "ETB",
        "PIRATE_DAMAGE_TO_OPPONENTS",
    }
)
SUPPORTED_ENTRY_REPLACEMENTS = frozenset(
    {"CHOOSE_COLOR_ENTER_TAPPED", "ENTER_TAPPED", "REVEAL_OR_ENTER_TAPPED"}
)
SUPPORTED_STATIC_EFFECTS = frozenset({"HAND_SIZE_POWER_TOUGHNESS", "KEYWORD", "CANT_BE_BLOCKED"})
SUPPORTED_ETB_TARGET_SCHEMAS = frozenset(
    {
        "NONE",
        "CONTROLLED_LAND",
        "GRAVEYARD_CARD",
        "INSTANT_OR_SORCERY_SPELL",
        "SLIVER",
    }
)
STORMTAMER_TARGET_SCHEMA = "SPELL_OR_ABILITY_TARGETING_YOU_OR_CONTROLLED_CREATURE"


def effect_execution_supported(effect: dict[str, Any]) -> bool:
    """Return whether one effect has a fail-closed production implementation."""

    kind = str(effect.get("kind", "NONE"))
    if kind == "SEQUENCE":
        return all(effect_execution_supported(dict(child)) for child in effect.get("effects", ()))
    if kind == "SCRY":
        return int(effect.get("count", 1)) == 1
    return kind in SUPPORTED_EFFECTS


def _effect_requires_explicit_choice(effect: dict[str, Any]) -> bool:
    kind = str(effect.get("kind", "NONE"))
    if kind == "SEQUENCE":
        return any(
            _effect_requires_explicit_choice(dict(child)) for child in effect.get("effects", ())
        )
    return kind in {
        "ADD_BLUE_OR_FIXED_CHOSEN",
        "ADD_CHOSEN_MANA",
        "ADD_CHOSEN_MANA_AND_DAMAGE_SELF",
        "ADD_COMMANDER_COLOR",
        "ADD_OPPONENT_PROFILE_COLOR",
        "FILTER_MANA_OPTIONS",
        "SCRY",
    }


def automatic_ability_execution_supported(ability: dict[str, Any], *, entering: bool) -> bool:
    """Return whether an ability can execute automatically without an unmade choice."""

    kind = str(ability.get("kind", ""))
    effect = dict(ability.get("effect", {}))
    if kind in {"SPELL", "ACTIVATED", "SPECIAL_ACTION"}:
        return effect_execution_supported(effect)
    if kind == "STATIC":
        return str(effect.get("kind", "")) in SUPPORTED_STATIC_EFFECTS
    if kind == "REPLACEMENT":
        event = str(ability.get("event", ""))
        effect_kind = str(effect.get("kind", ""))
        return (event == "ENTERS_BATTLEFIELD" and effect_kind in SUPPORTED_ENTRY_REPLACEMENTS) or (
            event == "ENCHANTED_CREATURE_DESTROY" and effect_kind == "UMBRA_ARMOR"
        )
    if kind != "TRIGGERED":
        return False
    trigger = str(ability.get("trigger", ""))
    if trigger == "ETB" and not entering:
        return True
    schema = dict(ability.get("target_schema", {}))
    minimum = int(schema.get("min", 0) or 0)
    maximum_value = schema.get("max", 0)
    maximum = int(maximum_value) if maximum_value is not None else None
    # Entry-trigger target and resolution choices are captured as cast/play
    # choice hints, then validated when the waiting trigger is put on the stack.
    if (
        trigger == "ETB"
        and not ability.get("optional")
        and str(schema.get("kind", "NONE")) in SUPPORTED_ETB_TARGET_SCHEMAS
        and minimum <= 1
        and maximum is not None
        and maximum <= 1
        and effect_execution_supported(effect)
    ):
        return True
    # Niv-Mizzet's mandatory draw trigger is executable only with an explicit
    # legal any-target choice recorded on the action that caused the draw.
    if (
        trigger in SUPPORTED_NO_CHOICE_TRIGGERS
        and not ability.get("optional")
        and str(schema.get("kind", "NONE")) == "ANY_TARGET"
        and minimum == 1
        and maximum == 1
        and effect_execution_supported(effect)
        and not _effect_requires_explicit_choice(effect)
    ):
        return True
    # Optional triggers are executable only through an explicit recorded yes/no
    # choice. The trigger path enforces that choice before the ability is put on
    # the stack, so their optionality is not a silent default.
    return bool(
        trigger in SUPPORTED_NO_CHOICE_TRIGGERS
        and effect_execution_supported(effect)
        and int(schema.get("max", 0) or 0) == 0
        and not _effect_requires_explicit_choice(effect)
    )


def object_automatic_execution_supported(obj: GameObject, *, entering: bool) -> bool:
    return all(
        automatic_ability_execution_supported(dict(ability), entering=entering)
        for ability in obj.current_characteristics.get("abilities", ())
    )


_ORIGINALS: dict[str, Callable[..., Any]] = {}


def _types(obj: GameObject) -> set[str]:
    return set(str(value) for value in obj.current_characteristics.get("card_types", ()))


def _subtypes(obj: GameObject) -> set[str]:
    return set(str(value) for value in obj.current_characteristics.get("subtypes", ()))


def _is_permanent(obj: GameObject) -> bool:
    """Treat phased-out battlefield objects as nonexistent for rules queries."""

    if not bool(_ORIGINALS["is_permanent"](obj)):
        return False
    status = obj.permanent_status or {}
    return status.get("phase", "PHASED_IN") != "PHASED_OUT"


def _player_has_hexproof(self: Any, player_id: str) -> bool:
    return any(
        record.get("kind") == "PLAYER_AND_CONTROLLED_PERMANENTS_HEXPROOF"
        and record.get("player_id") == player_id
        and record.get("protect_player") is True
        for record in self.state.continuous_effects
    )


def _permanent_has_hexproof_from(self: Any, actor: str, obj: GameObject) -> bool:
    controller = obj.controller
    if controller is None or controller == actor:
        return False
    return any(
        record.get("kind") == "PLAYER_AND_CONTROLLED_PERMANENTS_HEXPROOF"
        and record.get("player_id") == controller
        and record.get("protect_controlled_permanents") is True
        for record in self.state.continuous_effects
    )


def _stack_object_targets_actor_or_controlled_creature(
    self: Any, actor: str, obj: GameObject
) -> bool:
    if obj.zone is not Zone.STACK or obj.object_kind is ObjectKind.MANA_ABILITY:
        return False
    try:
        created = self._created_action(obj)
    except IllegalAction:
        return False
    for ref in created.targets:
        try:
            target = self.identity.resolve_reference(ref)
        except IllegalAction:
            continue
        if not isinstance(target, GameObject):
            continue
        if (
            target.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
            and target.zone is Zone.NONE
            and target.current_characteristics.get("target_kind") == "PLAYER"
            and target.current_characteristics.get("player_id") == actor
            and actor in self.state.players
            and self.state.players[actor].in_game
        ):
            return True
        if (
            self._is_permanent(target)
            and target.controller == actor
            and "Creature" in _types(target)
        ):
            return True
    return False


def _target_matches(self: Any, actor: str, obj: GameObject, kind: str) -> bool:
    types = _types(obj)
    subtypes = _subtypes(obj)
    supertypes = set(str(value) for value in obj.current_characteristics.get("supertypes", ()))
    permanent = bool(self._is_permanent(obj))
    if kind == "ANY_TARGET":
        if (
            obj.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
            and obj.zone is Zone.NONE
            and obj.current_characteristics.get("target_kind") == "PLAYER"
        ):
            player_id = str(obj.current_characteristics.get("player_id", ""))
            return bool(
                player_id in self.state.players
                and self.state.players[player_id].in_game
                and (player_id == actor or not _player_has_hexproof(self, player_id))
            )
        if permanent and _permanent_has_hexproof_from(self, actor, obj):
            return False
        return permanent and bool(types.intersection({"Creature", "Planeswalker", "Battle"}))
    if kind == STORMTAMER_TARGET_SCHEMA:
        return _stack_object_targets_actor_or_controlled_creature(self, actor, obj)
    if permanent and _permanent_has_hexproof_from(self, actor, obj):
        return False
    if kind == "SPELL":
        return obj.zone is Zone.STACK and obj.object_kind in {
            ObjectKind.SPELL,
            ObjectKind.SPELL_COPY,
        }
    if kind == "SPELL_OR_ABILITY":
        return obj.zone is Zone.STACK and obj.object_kind is not ObjectKind.MANA_ABILITY
    if kind == "NONLAND_PERMANENT":
        return permanent and "Land" not in types
    if kind == "PERMANENT":
        return permanent
    if kind == "OPPONENT_NONBASIC_LAND":
        return (
            permanent and obj.controller != actor and "Land" in types and "Basic" not in supertypes
        )
    if kind == "OPPONENT_ARTIFACT":
        return permanent and obj.controller != actor and "Artifact" in types
    if kind == "ARTIFACT_CREATURE_OR_LAND":
        return permanent and bool(types.intersection({"Artifact", "Creature", "Land"}))
    if kind == "CONTROLLED_LAND":
        return permanent and obj.controller == actor and "Land" in types
    if kind == "SLIVER":
        return permanent and "Sliver" in subtypes
    return bool(_ORIGINALS["target_matches"](self, actor, obj, kind))


def _ability_by_id(self: Any, source: GameObject, ability_id: str) -> dict[str, Any]:
    """Select the unique activated ability even when a trigger reuses its ID."""

    matches = [
        dict(ability)
        for ability in source.current_characteristics.get("abilities", ())
        if ability.get("ability_id") == ability_id and ability.get("kind") == "ACTIVATED"
    ]
    if len(matches) != 1:
        raise IllegalAction("activated ability is unavailable")
    selected = matches[0]
    if str(dict(selected.get("effect", {})).get("kind", "")) == "COUNTER_TARGETING_CONTROLLER":
        schema = dict(selected.get("target_schema", {}))
        if str(schema.get("kind", "")) != "SPELL_OR_ABILITY":
            raise IllegalAction("controller-targeting counter has an invalid target schema")
        schema["kind"] = STORMTAMER_TARGET_SCHEMA
        selected["target_schema"] = schema
    return selected


def _ensure_player_target_objects(self: Any) -> dict[str, GameObject]:
    proxies: dict[str, GameObject] = {}
    for obj in self.state.objects.values():
        if (
            not obj.retired
            and not obj.ceased_to_exist
            and obj.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
            and obj.zone is Zone.NONE
            and obj.current_characteristics.get("target_kind") == "PLAYER"
        ):
            player_id = str(obj.current_characteristics.get("player_id", ""))
            if player_id in self.state.players:
                proxies[player_id] = obj
    for player_id, player in self.state.players.items():
        if not player.in_game or player_id in proxies:
            continue
        proxy = GameObject(
            self.identity.new_id("object"),
            ObjectKind.EXTERNAL_PUBLIC_OBJECT,
            Zone.NONE,
            player_id,
            None,
            current_characteristics={
                "name": f"Player {player_id}",
                "target_kind": "PLAYER",
                "player_id": player_id,
            },
            identity_visible_to=set(self.state.players),
        )
        self.state.objects[proxy.object_id] = proxy
        self.zones.register(proxy)
        proxies[player_id] = proxy
    return proxies


def _choose_trigger_targets(
    self: Any, trigger: GameObject, ability: dict[str, Any]
) -> tuple[TargetRef, ...]:
    schema = dict(
        ability.get("target_schema", {"kind": "NONE", "min": 0, "max": 0, "unique": True})
    )
    if str(schema.get("kind", "NONE")) != "ANY_TARGET":
        return cast(
            tuple[TargetRef, ...],
            _ORIGINALS["choose_trigger_targets"](self, trigger, ability),
        )

    proxies = _ensure_player_target_objects(self)
    hints = dict(trigger.current_characteristics.get("choice_hints", {}))
    target_hints = dict(hints.get("trigger_targets", {}))
    selected = target_hints.get(ability["ability_id"])
    if isinstance(selected, str) and selected in proxies:
        target_hints[ability["ability_id"]] = proxies[selected].object_id
    elif isinstance(selected, list):
        target_hints[ability["ability_id"]] = [
            proxies[str(value)].object_id if str(value) in proxies else str(value)
            for value in selected
        ]
    hints["trigger_targets"] = target_hints
    trigger.current_characteristics["choice_hints"] = hints
    return cast(
        tuple[TargetRef, ...],
        _ORIGINALS["choose_trigger_targets"](self, trigger, ability),
    )
