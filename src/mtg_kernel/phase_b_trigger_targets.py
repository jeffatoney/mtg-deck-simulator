"""Observation-safe strategic choices for mandatory targeted triggered abilities."""

from __future__ import annotations

from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.models import Choice, GameObject, ObjectKind, TargetRef, Zone
from mtg_kernel.phase_b_runtime_support import (
    _choose_trigger_targets as _runtime_choose_trigger_targets,
    _ensure_player_target_objects,
)
from mtg_kernel.strategic_choices import CardSelectionRequest, PublicCard, require_provider


def _public_target(self: Any, request_id: str, candidate: GameObject) -> PublicCard:
    handle = self._strategic_handle(request_id, candidate.object_id)
    if (
        candidate.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
        and candidate.zone is Zone.NONE
        and candidate.current_characteristics.get("target_kind") == "PLAYER"
    ):
        player_id = str(candidate.current_characteristics.get("player_id", ""))
        return PublicCard(
            handle=handle,
            identity=f"Player {player_id}",
            mana_value=0,
            card_types=("PLAYER",),
            effect_kinds=(),
        )
    return PublicCard(
        handle=handle,
        identity=str(candidate.current_characteristics.get("name", "")),
        mana_value=int(candidate.current_characteristics.get("mana_value", 0)),
        card_types=tuple(
            str(value) for value in candidate.current_characteristics.get("card_types", ())
        ),
        effect_kinds=self._strategic_effect_kinds(candidate),
    )


def _choose_trigger_targets(
    self: Any,
    trigger: GameObject,
    ability: dict[str, Any],
) -> tuple[TargetRef, ...]:
    """Delegate legal target choice to policy only when rules require a real choice."""

    schema = dict(
        ability.get("target_schema", {"kind": "NONE", "min": 0, "max": 0, "unique": True})
    )
    if str(schema.get("kind", "NONE")) == "ANY_TARGET":
        _ensure_player_target_objects(self)

    actor = trigger.controller or ""
    candidates = self._legal_candidates(actor, schema)
    hints = dict(trigger.current_characteristics.get("choice_hints", {}))
    target_hints = dict(hints.get("trigger_targets", {}))
    ability_id = str(ability["ability_id"])

    # Preserve every pre-recorded choice and the rules engine's sole/no-target
    # behavior. Only a genuine multi-candidate decision crosses the policy boundary.
    if ability_id in target_hints or len(candidates) <= 1:
        return _runtime_choose_trigger_targets(self, trigger, ability)

    minimum = int(schema.get("min", 0) or 0)
    maximum_raw = schema.get("max")
    maximum = int(maximum_raw) if maximum_raw is not None else None
    if minimum != 1 or maximum != 1:
        raise IllegalAction(
            "strategic trigger target selection supports exactly one required target"
        )

    raw_provider = getattr(self, "strategic_choice_provider", None)
    if raw_provider is None:
        # Preserve the kernel's longstanding fail-closed contract for callers that
        # intentionally exercise a targeted trigger without a policy provider.
        raise IllegalAction("explicit trigger target choice is required")
    provider = require_provider(raw_provider, "mandatory trigger target selection")
    request_id = self.identity.new_id("strategic-request")
    public_candidates = tuple(
        _public_target(self, request_id, candidate) for candidate in candidates
    )
    purpose = f"TRIGGER_TARGET:{str(dict(ability.get('effect', {})).get('kind', 'NONE'))}"
    selection = provider.choose_cards(
        CardSelectionRequest(
            request_id=request_id,
            actor_id=actor,
            ability_id=ability_id,
            purpose=purpose,
            turn_number=self.state.turn.number,
            observation=self._strategic_observation(actor),
            candidates=public_candidates,
            minimum=1,
            maximum=1,
        )
    )
    selected_handles = tuple(selection.selected_handles)
    by_handle = {
        public.handle: candidate
        for public, candidate in zip(public_candidates, candidates, strict=True)
    }
    if len(selected_handles) != 1 or selected_handles[0] not in by_handle:
        raise IllegalAction("strategic provider selected an illegal trigger target")
    selected = by_handle[selected_handles[0]]

    event = self._event(
        "STRATEGIC_TRIGGER_TARGET_SELECTION",
        source_object_id=trigger.source_object_id,
        ability_id=ability_id,
        purpose=purpose,
    )
    self.state.choices.append(
        Choice(
            self.identity.new_id("choice"),
            actor,
            "CARD_SELECTION",
            {
                "purpose": purpose,
                "selected_handles": list(selected_handles),
                "evaluator_id": selection.evaluator_id,
                "evaluator_sha256": selection.evaluator_sha256,
                "diagnostics": dict(selection.diagnostics),
                "chosen_at": "TRIGGER_PLACEMENT",
            },
            event.event_id,
        )
    )
    target_hints[ability_id] = selected.object_id
    hints["trigger_targets"] = target_hints
    trigger.current_characteristics["choice_hints"] = hints
    return _runtime_choose_trigger_targets(self, trigger, ability)


def install_trigger_target_choices(executor_class: type[Any]) -> None:
    """Install the explicit strategic target bridge after the Phase B runtime."""

    executor_class._choose_trigger_targets = _choose_trigger_targets


__all__ = ["install_trigger_target_choices"]
