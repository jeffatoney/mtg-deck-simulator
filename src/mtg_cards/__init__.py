"""Oracle-backed production card specifications for the clean engine."""

from mtg_cards.full_deck import FULL_DECK_NAMES, load_full_deck_specs
from mtg_cards.oracle import PHASE_A_NAMES, load_phase_a_specs

__all__ = [
    "FULL_DECK_NAMES",
    "PHASE_A_NAMES",
    "load_full_deck_specs",
    "load_phase_a_specs",
]
