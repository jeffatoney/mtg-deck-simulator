"""Clean, card-agnostic Magic rules kernel."""

from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.interaction_rules_conformance import install_interaction_rules_conformance
from mtg_kernel.phase_b_runtime import install_phase_b_runtime
from mtg_kernel.phase_b_trigger_targets import install_trigger_target_choices

install_phase_b_runtime(GameExecutor)
install_trigger_target_choices(GameExecutor)
install_interaction_rules_conformance(GameExecutor)

__all__ = ["GameExecutor", "add_card", "new_game"]
