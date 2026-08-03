"""Clean, card-agnostic Magic rules kernel."""

from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.phase_b_runtime import install_phase_b_runtime

install_phase_b_runtime(GameExecutor)

__all__ = ["GameExecutor", "add_card", "new_game"]
