"""Production broker retaining strategic providers inside disposable legality probes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_policy.broker import ActionBroker as _BaseActionBroker


class ActionBroker(_BaseActionBroker):
    """Probe legal actions through the same strategic-choice-capable executor."""

    def _probe(self, operation: str, arguments: dict[str, Any]) -> bool:
        # Match the certified core broker's replay-history detachment while
        # retaining the frozen provider for rules-defined choices that occur
        # during a probe (for example a targeted land ETB trigger).
        live = self.executor.state
        replay_initial = live.replay_initial_state
        replay_commands = live.replay_commands
        live.replay_initial_state = None
        live.replay_commands = []
        try:
            state = deepcopy(live)
        finally:
            live.replay_initial_state = replay_initial
            live.replay_commands = replay_commands
        state.replay_initial_state = replay_initial
        state.replay_commands = list(replay_commands)
        probe = GameExecutor(
            state,
            self.executor.seed,
            replaying=True,
            probing=True,
            strategic_choice_provider=self.executor.strategic_choice_provider,
        )
        try:
            self._invoke(probe, operation, arguments, record=False)
        except (IllegalAction, UnsupportedCapability, KeyError, ValueError):
            return False
        return True


__all__ = ["ActionBroker"]
