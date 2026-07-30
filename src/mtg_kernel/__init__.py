"""Clean, card-agnostic Magic rules kernel."""

from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card, new_game

__all__ = ["GameExecutor", "add_card", "new_game"]
