"""Deck-scoped executable behavior primitives.

The project still lacks a full game executor. These functions are narrow,
unit-tested rules primitives for the next gated phase; any undeclared or untested
card behavior must remain unavailable to pilots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


class BehaviorExecutionError(ValueError):
    """Raised when a behavior cannot execute legally under the modeled state."""


@dataclass(frozen=True, slots=True)
class LibraryState:
    size: int

    def draw(self, count: int = 1) -> "LibraryState":
        if count < 0:
            raise BehaviorExecutionError("draw count cannot be negative")
        if count > self.size:
            raise BehaviorExecutionError("cannot draw from an empty or undersized library")
        return LibraryState(self.size - count)


@dataclass(frozen=True, slots=True)
class MalcolmDamageEvent:
    pirate_damage_by_opponent: tuple[bool, bool, bool]


def malcolm_treasures(event: MalcolmDamageEvent) -> int:
    """Create one Treasure for each opponent actually dealt Pirate damage."""
    return sum(1 for damaged in event.pirate_damage_by_opponent if damaged)


def glint_horn_damage(discarded_cards: int, opponents: int = 3) -> int:
    if discarded_cards < 0 or opponents < 0:
        raise BehaviorExecutionError("discarded cards and opponents cannot be negative")
    return discarded_cards * opponents


def curiosity_draws(noncombat_damage_events: int, library: LibraryState) -> LibraryState:
    if noncombat_damage_events < 0:
        raise BehaviorExecutionError("damage event count cannot be negative")
    return library.draw(noncombat_damage_events)


def dualcaster_twinflame_copies(iterations: int) -> int:
    if iterations < 1:
        raise BehaviorExecutionError("Dualcaster/Twinflame combo requires at least one iteration")
    return iterations


def long_term_plans_new_depth(starting_depth: int = 1) -> int:
    if starting_depth < 1:
        raise BehaviorExecutionError("tutored card depth is one-indexed")
    return 3


TRANSMUTE_MANA_VALUES: Final[dict[str, int]] = {
    "Dizzy Spell": 1,
    "Muddle the Mixture": 2,
    "Drift of Phantasms": 3,
}
WIZARDCYCLING_CARDS: Final[frozenset[str]] = frozenset({"Step Through", "Vedalken Aethermage"})
SPLIT_CARDS: Final[frozenset[str]] = frozenset({"Invert // Invent", "Commit // Memory"})
EXECUTABLE_IMPLEMENTATIONS: Final[frozenset[str]] = frozenset(
    {
        "malcolm_treasure_trigger_v1",
        "glint_horn_buccaneer_v1",
        "dualcaster_mage_copy_trigger_v1",
        "twinflame_strive_copy_v1",
        "electroduplicate_flashback_v1",
        "curiosity_optional_damage_draw_v1",
        "lightning_rig_crew_v1",
        "crab_umbra_untap_totem_armor_v1",
        "drift_phantasms_transmute_mv3_v1",
        "muddle_counter_transmute_mv2_v1",
        "dizzy_spell_transmute_mv1_v1",
        "step_through_wizardcycling_v1",
        "vedalken_aethermage_wizardcycling_v1",
        "long_term_plans_third_from_top_v1",
        "invert_invent_split_instant_v1",
        "commit_memory_aftermath_v1",
        "expedite_haste_draw_v1",
        "opt_scry_draw_v1",
        "sleight_of_hand_selection_v1",
        "faithless_looting_flashback_v1",
        "frantic_search_untap_v1",
        "impulse_top_four_v1",
        "siren_stormtamer_protection_v1",
        "lazotep_plating_hexproof_v1",
        "sol_ring_mana_v1",
        "command_tower_v1",
        "basic_island_v1",
        "basic_mountain_v1",
    }
)
