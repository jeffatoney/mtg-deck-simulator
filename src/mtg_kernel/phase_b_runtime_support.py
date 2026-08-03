"""Phase B support registry and exact-deck target-schema extensions."""

from __future__ import annotations

from typing import Any, Callable

from mtg_kernel.models import GameObject, ObjectKind, Zone

SUPPORTED_EFFECTS = frozenset(
    {
        "NONE",
        "ADD_BLUE_OR_FIXED_CHOSEN",
        "ADD_CHOSEN_MANA",
        "ADD_CHOSEN_MANA_AND_DAMAGE_SELF",
        "ADD_COMMANDER_COLOR",
        "ADD_MANA",
        "ADD_OPPONENT_PROFILE_COLOR",
        "ATTACH_AURA",
        "BOUNCE_ALL_ARTIFACTS",
        "BOUNCE_AND_CONDITIONAL_SCRY",
        "BOUNCE_ATTACKING_CREATURES",
        "BOUNCE_TARGET",
        "BOUNCE_TARGETS",
        "CANT_BE_BLOCKED",
        "COUNTER",
        "COUNTER_IF",
        "COUNTER_TARGETING_CONTROLLER",
        "CREATE_SPELL_COPY",
        "CREATE_TOKEN_COPIES",
        "CREATE_TREASURE",
        "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS",
        "DAMAGE",
        "DAMAGE_ALL_CREATURES_PLANESWALKERS",
        "DAMAGE_ALL_NON_SUBTYPE",
        "DAMAGE_EACH_OPPONENT",
        "DESTROY",
        "DESTROY_ALL_OPPONENT_ARTIFACTS",
        "DESTROY_ARTIFACTS_MV_LEQ",
        "DESTROY_TARGETS",
        "DRAW",
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
        "FORETELL",
        "GRANT_HASTE",
        "HAND_SIZE_POWER_TOUGHNESS",
        "KEYWORD",
        "LIBRARY_SECOND",
        "MEMORY",
        "MODIFY_POWER_TOUGHNESS",
        "RECORD_UNKNOWN_BREECHES_EXILES",
        "RETURN_CONTROLLED_LAND",
        "SCRY",
        "SEQUENCE",
        "SWITCH_POWER_TOUGHNESS",
        "TRANSMUTE",
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
        "ETB",
        "PIRATE_DAMAGE_TO_OPPONENTS",
    }
)
SUPPORTED_ENTRY_REPLACEMENTS = frozenset(
    {"CHOOSE_COLOR_ENTER_TAPPED", "ENTER_TAPPED", "REVEAL_OR_ENTER_TAPPED"}
)
SUPPORTED_STATIC_EFFECTS = frozenset({"HAND_SIZE_POWER_TOUGHNESS", "KEYWORD", "CANT_BE_BLOCKED"})


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
    if (
        trigger == "ETB"
        and str(effect.get("kind", "")) == "CREATE_SPELL_COPY"
        and str(schema.get("kind", "")) == "INSTANT_OR_SORCERY_SPELL"
        and int(schema.get("min", 0) or 0) == 1
        and int(schema.get("max", 0) or 0) == 1
        and not ability.get("optional")
        and effect_execution_supported(effect)
    ):
        return True
    return bool(
        trigger in SUPPORTED_NO_CHOICE_TRIGGERS
        and effect_execution_supported(effect)
        and not ability.get("optional")
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


def _target_matches(self: Any, actor: str, obj: GameObject, kind: str) -> bool:
    types = _types(obj)
    subtypes = _subtypes(obj)
    supertypes = set(str(value) for value in obj.current_characteristics.get("supertypes", ()))
    permanent = bool(self._is_permanent(obj))
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