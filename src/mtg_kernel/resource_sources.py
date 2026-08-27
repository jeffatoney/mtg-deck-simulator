"""State adapter for the authoritative resource-payment solver.

This module extracts only current, public rules state.  It does not inspect library
contents, project draws or land drops, or make policy choices.  Unsupported mana-source
semantics fail closed before feasibility is reported.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import GameObject, GameState, Zone
from mtg_kernel.resource_payment import (
    FloatingMana,
    ManaProduction,
    PaymentStep,
    ResourcePaymentResult,
    ResourceSource,
    solve_resource_payment,
)

_MANA_COLORS = ("W", "U", "B", "R", "G", "C")
DEFAULT_OPPONENT_MANA_PROFILE = "blue_red_available"
_OPPONENT_MANA_PROFILE_COLORS: dict[str, tuple[str, ...]] = {
    DEFAULT_OPPONENT_MANA_PROFILE: ("U", "R"),
    "no_known_colors": (),
}


def validate_opponent_mana_profile(value: object) -> str:
    """Return one supported replay-safe opponent mana profile."""

    if not isinstance(value, str) or value not in _OPPONENT_MANA_PROFILE_COLORS:
        raise UnsupportedCapability(f"unsupported opponent mana profile: {value}")
    return value


@dataclass(frozen=True)
class ResourceInventory:
    sources: tuple[ResourceSource, ...]
    floating_mana: tuple[FloatingMana, ...]
    assumptions: tuple[str, ...]


def _active_controlled_permanents(state: GameState, player_id: str) -> list[GameObject]:
    return [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and not obj.ceased_to_exist
        and obj.zone is Zone.BATTLEFIELD
        and obj.controller == player_id
    ]


def _is_untapped(obj: GameObject) -> bool:
    return obj.permanent_status is not None and obj.permanent_status.get("tap") == "UNTAPPED"


def _tap_ability_available(state: GameState, player_id: str, obj: GameObject) -> bool:
    if obj.controller != player_id or obj.zone is not Zone.BATTLEFIELD or not _is_untapped(obj):
        return False
    card_types = {str(value) for value in obj.current_characteristics.get("card_types", ())}
    if "Creature" not in card_types:
        return True
    keywords = {str(value) for value in obj.current_characteristics.get("keywords", ())}
    if "Haste" in keywords:
        return True
    status = obj.permanent_status or {}
    try:
        controlled_since = int(status.get("controller_since_turn", state.turn.number))
    except (TypeError, ValueError):
        return False
    return controlled_since < int(state.turn.number)


def _commander_colors(state: GameState, player_id: str) -> tuple[str, ...]:
    colors: set[str] = set()
    for instance in state.card_instances.values():
        if instance.owner_id != player_id or not instance.commander_designation:
            continue
        spec = state.card_specs.get(instance.card_spec_id)
        if spec is not None:
            colors.update(color for color in spec.color_identity if color in _MANA_COLORS)
    if colors:
        return tuple(color for color in _MANA_COLORS if color in colors)
    for obj in state.objects.values():
        if obj.owner != player_id:
            continue
        identity = obj.current_characteristics.get("color_identity", ())
        if obj.current_characteristics.get("commander_designation") is True:
            colors.update(str(color) for color in identity if str(color) in _MANA_COLORS)
    if not colors:
        raise UnsupportedCapability("commander-color mana source has no modeled commander colors")
    return tuple(color for color in _MANA_COLORS if color in colors)


def commander_colors_from_state(state: GameState, player_id: str) -> tuple[str, ...]:
    """Return the modeled commander colors shared by previews and broker execution."""
    return _commander_colors(state, player_id)


def _mana_map(raw: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(raw, Mapping):
        raise UnsupportedCapability("mana-source effect is missing a mana mapping")
    result: list[tuple[str, int]] = []
    for color, amount in raw.items():
        symbol = str(color)
        value = int(amount)
        if symbol not in _MANA_COLORS or value <= 0:
            raise UnsupportedCapability("mana-source effect contains unsupported production")
        result.append((symbol, value))
    if not result:
        raise UnsupportedCapability("mana-source effect produces no modeled mana")
    return tuple(sorted(result, key=lambda item: _MANA_COLORS.index(item[0])))


def _choice_productions(
    choices: object, *, activation_cost: str = ""
) -> tuple[ManaProduction, ...]:
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
        raise UnsupportedCapability("chosen-mana effect is missing explicit choices")
    productions = []
    for raw_color in choices:
        color = str(raw_color)
        if color not in _MANA_COLORS:
            raise UnsupportedCapability("chosen-mana effect contains an unsupported color")
        productions.append(ManaProduction(((color, 1),), activation_cost=activation_cost))
    if not productions:
        raise UnsupportedCapability("chosen-mana effect has no legal choices")
    return tuple(productions)


def _effect_productions(
    state: GameState,
    player_id: str,
    obj: GameObject,
    ability: Mapping[str, Any],
    *,
    opponent_mana_profile: str,
) -> tuple[ManaProduction, ...]:
    effect = ability.get("effect", {})
    if not isinstance(effect, Mapping):
        raise UnsupportedCapability("mana ability has no declarative effect mapping")
    cost = ability.get("cost", {})
    if not isinstance(cost, Mapping):
        raise UnsupportedCapability("mana ability has no declarative cost mapping")
    activation_cost = str(cost.get("mana", ""))
    kind = str(effect.get("kind", ""))
    if kind == "ADD_MANA":
        return (ManaProduction(_mana_map(effect.get("mana")), activation_cost=activation_cost),)
    if kind == "ADD_CHOSEN_MANA":
        return _choice_productions(effect.get("choices", ()), activation_cost=activation_cost)
    if kind == "FILTER_MANA_OPTIONS":
        options = effect.get("options", ())
        if not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
            raise UnsupportedCapability("filter mana source is missing production options")
        return tuple(
            ManaProduction(_mana_map(option), activation_cost=activation_cost) for option in options
        )
    if kind in {"ADD_COMMANDER_COLOR", "ADD_COMMANDER_COLOR_AND_MARK"}:
        return _choice_productions(
            commander_colors_from_state(state, player_id), activation_cost=activation_cost
        )
    if kind == "ADD_OPPONENT_PROFILE_COLOR":
        opponent_mana_profile = validate_opponent_mana_profile(opponent_mana_profile)
        colors = _OPPONENT_MANA_PROFILE_COLORS[opponent_mana_profile]
        if not colors:
            return ()
        return _choice_productions(colors, activation_cost=activation_cost)
    if kind == "ADD_CHOSEN_MANA_AND_DAMAGE_SELF":
        damage = int(effect.get("damage", 1))
        if state.players[player_id].life <= damage:
            # This known activation is currently illegal because it would cause a
            # state-based loss. Omit only this production mode; other independent
            # mana abilities on the same permanent remain available.
            return ()
        return _choice_productions(effect.get("choices", ()), activation_cost=activation_cost)
    if kind == "ADD_BLUE_OR_FIXED_CHOSEN":
        fixed = str(obj.current_characteristics.get("chosen_color", ""))
        choices = tuple(dict.fromkeys(color for color in ("U", fixed) if color))
        return _choice_productions(choices, activation_cost=activation_cost)
    raise UnsupportedCapability(f"unsupported mana-source effect in resource preview: {kind}")


def _treasure_source(obj: GameObject) -> ResourceSource | None:
    name = str(obj.current_characteristics.get("name", ""))
    subtypes = {str(value) for value in obj.current_characteristics.get("subtypes", ())}
    if name != "Treasure" and "Treasure" not in subtypes:
        return None
    return ResourceSource(
        semantic_id="Treasure:treasure-mana",
        productions=tuple(ManaProduction(((color, 1),)) for color in ("W", "U", "B", "R", "G")),
        count=1,
        tap_to_activate=True,
        sacrifice_to_activate=True,
        persistent=True,
        tapped=not _is_untapped(obj),
        execution_refs=(obj.object_id,),
    )


def _permanent_mana_source(
    state: GameState,
    player_id: str,
    obj: GameObject,
    *,
    opponent_mana_profile: str,
) -> ResourceSource | None:
    mana_abilities = [
        ability
        for ability in obj.current_characteristics.get("abilities", ())
        if isinstance(ability, Mapping)
        and ability.get("kind") == "ACTIVATED"
        and ability.get("mana_ability") is True
    ]
    if not mana_abilities:
        return None
    tap_flags = {bool(dict(ability.get("cost", {})).get("tap")) for ability in mana_abilities}
    sacrifice_flags = {
        bool(dict(ability.get("cost", {})).get("sacrifice_source")) for ability in mana_abilities
    }
    if len(tap_flags) != 1 or len(sacrifice_flags) != 1:
        raise UnsupportedCapability(
            "mana abilities with different source-capacity costs are unsupported"
        )
    tap_to_activate = next(iter(tap_flags))
    sacrifice_to_activate = next(iter(sacrifice_flags))
    if not tap_to_activate and not sacrifice_to_activate:
        raise UnsupportedCapability("repeatable no-capacity mana ability is unsupported")
    allowed_cost_keys = {"mana", "tap", "sacrifice_source"}
    for ability in mana_abilities:
        raw_cost = ability.get("cost", {})
        if not isinstance(raw_cost, Mapping) or set(raw_cost) - allowed_cost_keys:
            raise UnsupportedCapability("mana ability has unsupported nonmana activation costs")
    productions = tuple(
        production
        for ability in mana_abilities
        for production in _effect_productions(
            state,
            player_id,
            obj,
            ability,
            opponent_mana_profile=opponent_mana_profile,
        )
    )
    if not productions:
        return None
    name = str(obj.current_characteristics.get("name", "unnamed permanent"))
    tapped = tap_to_activate and not _tap_ability_available(state, player_id, obj)
    return ResourceSource(
        semantic_id=f"{name}:mana-source",
        productions=productions,
        count=1,
        tap_to_activate=tap_to_activate,
        sacrifice_to_activate=sacrifice_to_activate,
        persistent=True,
        tapped=tapped,
        execution_refs=(obj.object_id,),
    )


def resource_inventory_from_state(
    state: GameState,
    player_id: str,
    *,
    opponent_mana_profile: str = DEFAULT_OPPONENT_MANA_PROFILE,
) -> ResourceInventory:
    """Extract current usable resources without reading hidden-zone contents."""

    if player_id not in state.players:
        raise IllegalAction("resource preview player does not exist")
    opponent_mana_profile = validate_opponent_mana_profile(opponent_mana_profile)
    sources: list[ResourceSource] = []
    for obj in _active_controlled_permanents(state, player_id):
        treasure = _treasure_source(obj)
        if treasure is not None:
            sources.append(treasure)
            continue
        source = _permanent_mana_source(
            state,
            player_id,
            obj,
            opponent_mana_profile=opponent_mana_profile,
        )
        if source is not None:
            sources.append(source)
    floating = tuple(
        FloatingMana(color, int(amount), semantic_id=f"floating:{color}")
        for color, amount in state.players[player_id].mana_pool.items()
        if color in _MANA_COLORS and int(amount) > 0
    )
    return ResourceInventory(
        sources=tuple(sources),
        floating_mana=floating,
        assumptions=(
            "current battlefield tap/controller/zone state is authoritative",
            "no unrepresented future draw, land drop, untap, or opponent cooperation",
        ),
    )


def solve_state_payment(
    state: GameState,
    player_id: str,
    steps: Sequence[PaymentStep],
    *,
    additional_sources: Sequence[ResourceSource] = (),
    opponent_mana_profile: str = DEFAULT_OPPONENT_MANA_PROFILE,
) -> ResourcePaymentResult:
    """Adapt current state into the single authoritative payment solver."""

    inventory = resource_inventory_from_state(
        state,
        player_id,
        opponent_mana_profile=opponent_mana_profile,
    )
    return solve_resource_payment(
        (*inventory.sources, *tuple(additional_sources)),
        tuple(steps),
        floating_mana=inventory.floating_mana,
        assumptions=inventory.assumptions,
    )
