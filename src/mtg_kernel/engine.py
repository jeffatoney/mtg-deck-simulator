"""Public production executor with Phase B atomicity and terminal hardening."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_kernel.engine_core import MAIN_PHASES, PERMANENT_TYPES
from mtg_kernel.engine_core import GameExecutor as _CoreGameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import GameObject, GameState, TargetRef


class HardenedGameExecutor(_CoreGameExecutor):
    """Runtime executor adding Slice 3 atomicity and terminal protections."""

    def cast(
        self,
        actor: str,
        card_object_id: str,
        targets: tuple[TargetRef, ...] = (),
        face: int = 0,
        x_value: int = 0,
        mode: str | None = None,
        choices: dict[str, Any] | None = None,
        *,
        _record: bool = True,
    ) -> GameObject:
        card = self.state.objects[card_object_id]
        face_data = self._selected_face(card, face)
        spell_ability = self._selected_spell_ability(face_data, mode)
        effect = dict(spell_ability.get("effect", {}))
        if effect.get("target_count_from_x") and len(targets) != x_value:
            raise IllegalAction("the number of targets must equal the chosen value of X")
        return super().cast(
            actor,
            card_object_id,
            targets,
            face,
            x_value,
            mode,
            choices,
            _record=_record,
        )

    def check_state_based_actions(self) -> None:
        super().check_state_based_actions()
        if self.state.terminal.status != "TERMINAL":
            return
        for trigger_id in self.state.waiting_triggers:
            trigger = self.state.objects[trigger_id]
            trigger.retired = True
            trigger.ceased_to_exist = True
        self.state.waiting_triggers.clear()


_CORE_INITIALIZER = _CoreGameExecutor.__init__


def _guarded_core_initializer(
    self: _CoreGameExecutor,
    state: GameState,
    seed: str = "phase-a",
    *,
    replaying: bool = False,
) -> None:
    if type(self) is _CoreGameExecutor:
        raise UnsupportedCapability(
            "internal executor core cannot be instantiated directly; "
            "use mtg_kernel.engine.GameExecutor"
        )
    _CORE_INITIALIZER(self, state, seed, replaying=replaying)


setattr(_CoreGameExecutor, "__init__", _guarded_core_initializer)


if TYPE_CHECKING:
    # The public type is the shared core interface. Runtime construction below
    # still returns the hardened subclass, so the core may call shared services
    # without creating a false nominal-subclass requirement.
    GameExecutor = _CoreGameExecutor
else:
    GameExecutor = HardenedGameExecutor


__all__ = ["GameExecutor", "MAIN_PHASES", "PERMANENT_TYPES"]
