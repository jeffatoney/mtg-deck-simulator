"""Production broker retaining strategic providers inside disposable legality probes."""

from __future__ import annotations

from typing import Any

from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_policy.broker import ActionBroker as _BaseActionBroker
from mtg_policy.broker_core import disposable_probe_state


class ActionBroker(_BaseActionBroker):
    """Probe legal actions through the same strategic-choice-capable executor."""

    def _probe(self, operation: str, arguments: dict[str, Any]) -> bool:
        # Match the certified core broker's replay-history detachment while
        # retaining the frozen provider binding for rules-defined choices that
        # occur during a probe (for example a targeted land ETB trigger).
        state = disposable_probe_state(self.executor.state)
        probe = GameExecutor(
            state,
            self.executor.seed,
            replaying=True,
            probing=True,
            opponent_mana_profile=self.executor.opponent_mana_profile,
            strategic_choice_binding=getattr(self.executor, "strategic_choice_binding", None),
        )
        try:
            self._invoke(probe, operation, arguments, record=False)
        except (IllegalAction, UnsupportedCapability, KeyError, ValueError):
            return False
        return True


__all__ = ["ActionBroker"]
