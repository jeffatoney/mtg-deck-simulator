"""Casting-time validation for conditional exact-deck counterspells."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import GameObject, TargetRef
from mtg_kernel.phase_b_runtime_helpers import _cast, _spell_satisfies


def cast_with_counter_predicate(
    self: Any,
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
    """Validate exact-deck casting predicates before costs or mutation."""

    card = self.state.objects[card_object_id]
    cast_from_zone = card.zone
    face_data = self._selected_face(card, face)
    ability = self._selected_spell_ability(face_data, mode)
    effect = dict(ability.get("effect", {}))
    if effect.get("target_count_from_x") and len(targets) != x_value:
        raise IllegalAction("targets must equal X")
    if str(effect.get("kind", "")) == "COUNTER_IF" and len(targets) == 1:
        target = self.state.objects.get(targets[0].object_id)
        if target is not None and not _spell_satisfies(target, dict(effect.get("predicate", {}))):
            raise IllegalAction("target spell does not satisfy counter predicate")
    spell = _cast(
        self,
        actor,
        card_object_id,
        targets,
        face,
        x_value,
        mode,
        choices,
        _record=_record,
    )
    spell.current_characteristics["cast_from_zone"] = cast_from_zone.value
    return spell
