"""Casting-time validation for conditional exact-deck counterspells and kicker."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import combine_costs, parse_mana_cost, pay_mana
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
    """Validate exact-deck predicates and pay an explicitly selected kicker."""

    card = self.state.objects[card_object_id]
    cast_from_zone = card.zone
    face_data = self._selected_face(card, face)
    ability = self._selected_spell_ability(face_data, mode)
    effect = dict(ability.get("effect", {}))
    selected_choices = dict(choices or {})
    if effect.get("target_count_from_x") and len(targets) != x_value:
        raise IllegalAction("targets must equal X")
    counter_kinds = {"COUNTER_IF", "COUNTER_UNLESS_PAY", "COUNTER_UNLESS_PAY_EXILE"}
    if str(effect.get("kind", "")) in counter_kinds and len(targets) == 1:
        target = self.state.objects.get(targets[0].object_id)
        predicate = dict(effect.get("predicate", {}))
        if target is not None and predicate and not _spell_satisfies(target, predicate):
            raise IllegalAction("target spell does not satisfy counter predicate")

    kicker_text = str(effect.get("kicker", ""))
    kicked = bool(selected_choices.get("kicked", False))
    if not kicker_text or not kicked:
        spell = _cast(
            self,
            actor,
            card_object_id,
            targets,
            face,
            x_value,
            mode,
            selected_choices,
            _record=_record,
        )
        spell.current_characteristics["cast_from_zone"] = cast_from_zone.value
        return spell

    before = self._begin_atomic()
    try:
        kicker_cost = parse_mana_cost(kicker_text)
        kicker_payment = pay_mana(self.state.players[actor].mana_pool, kicker_cost)
        spell = _cast(
            self,
            actor,
            card_object_id,
            targets,
            face,
            x_value,
            mode,
            selected_choices,
            _record=_record,
        )
        action = self._created_action(spell)
        action.payments["cost"] = combine_costs(dict(action.payments.get("cost", {})), kicker_cost)
        action.payments["mana"] = combine_costs(
            dict(action.payments.get("mana", {})), kicker_payment
        )
        action.metadata["kicker_payment"] = dict(kicker_payment)
        spell.current_characteristics["cast_payment"] = dict(action.payments["mana"])
        spell.current_characteristics["kicked"] = True
        spell.current_characteristics["cast_from_zone"] = cast_from_zone.value
        return spell
    except Exception:
        self._rollback(before)
        raise
