"""Rules-correct mana-ability planning for payments made during resolution.

Magic rules 117.2e, 118.2, and 608.2g allow a player asked to pay mana while a
spell or ability resolves to activate mana abilities before making that payment.
This module keeps that narrow exception inside the rules engine: only declared
mana abilities may be used, they resolve immediately, and no priority is granted.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.mana import pay_mana
from mtg_kernel.models import GameObject, Zone

_MAX_RESOLUTION_MANA_ACTIVATIONS = 32
_ALLOWED_CHOSEN_MANA = frozenset({"W", "U", "B", "R", "G", "C"})


def _copy_executor(executor: Any) -> Any:
    live = executor.state
    replay_initial = live.replay_initial_state
    replay_commands = live.replay_commands
    live.replay_initial_state = None
    live.replay_commands = []
    try:
        cloned_state = deepcopy(live)
    finally:
        live.replay_initial_state = replay_initial
        live.replay_commands = replay_commands
    cloned_state.replay_initial_state = replay_initial
    cloned_state.replay_commands = list(replay_commands)
    clone = executor.__class__(cloned_state, executor.seed, probing=True)
    clone._resolution_depth = max(1, int(getattr(executor, "_resolution_depth", 0)))
    return clone


def _can_pay_generic(pool: Mapping[str, int], amount: int) -> bool:
    working = {str(symbol): int(value) for symbol, value in pool.items()}
    try:
        pay_mana(working, {"GENERIC": amount})
    except IllegalAction:
        return False
    return True


def _mana_ability_choices(executor: Any, source: GameObject, ability: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    effect = ability.get("effect", {})
    if not isinstance(effect, Mapping):
        raise UnsupportedCapability("mana ability has malformed effect data")
    kind = str(effect.get("kind", ""))
    if kind == "ADD_MANA":
        return ({},)
    if kind == "ADD_CHOSEN_MANA":
        raw = effect.get("choices", ())
        colors = tuple(sorted({str(value) for value in raw if str(value) in _ALLOWED_CHOSEN_MANA}))
        if not colors:
            raise UnsupportedCapability("chosen-mana ability has no supported legal colors")
        return tuple({"mana_color": color} for color in colors)
    if kind in {"ADD_COMMANDER_COLOR", "ADD_COMMANDER_COLOR_AND_MARK"}:
        from mtg_kernel.phase_b_marked_mana import commander_color_identity

        colors = tuple(sorted(commander_color_identity(executor, source.controller or source.owner or "")))
        if not colors:
            raise UnsupportedCapability("commander-color mana ability has no legal color")
        return tuple({"mana_color": color} for color in colors)
    if kind == "FILTER_MANA_OPTIONS":
        raw_options = effect.get("options", ())
        if not isinstance(raw_options, (list, tuple)):
            raise UnsupportedCapability("filter-mana ability options are malformed")
        normalized: list[dict[str, Any]] = []
        for option in raw_options:
            if not isinstance(option, Mapping):
                raise UnsupportedCapability("filter-mana ability option is malformed")
            normalized.append({"mana_option": {str(key): int(value) for key, value in sorted(option.items())}})
        return tuple(normalized)
    if kind == "ADD_BLUE_OR_FIXED_CHOSEN":
        # Exact-deck support for opponent-profile mana rocks. The effect implementation
        # validates the selected public option; keep the planner fail closed when the
        # effect does not publish an explicit finite choice set.
        raw = effect.get("choices", ())
        colors = tuple(sorted({str(value) for value in raw if str(value) in _ALLOWED_CHOSEN_MANA}))
        if colors:
            return tuple({"mana_color": color} for color in colors)
    raise UnsupportedCapability(f"resolution mana planner does not support effect kind: {kind}")


def _candidate_activations(executor: Any, player_id: str, request_id: str) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    for source in executor.state.objects.values():
        if (
            source.retired
            or source.ceased_to_exist
            or source.zone is not Zone.BATTLEFIELD
            or source.controller != player_id
        ):
            continue
        abilities = source.current_characteristics.get("abilities", ())
        if not isinstance(abilities, (list, tuple)):
            continue
        for raw_ability in abilities:
            if not isinstance(raw_ability, Mapping) or not bool(raw_ability.get("mana_ability")):
                continue
            ability = dict(raw_ability)
            ability_id = str(ability.get("ability_id", ""))
            if not ability_id:
                raise UnsupportedCapability("mana ability omits ability_id")
            source_handle = executor._strategic_handle(request_id, source.object_id)
            identity = str(source.current_characteristics.get("name", ""))
            for choices in _mana_ability_choices(executor, source, ability):
                candidates.append(
                    {
                        "source_handle": source_handle,
                        "source_identity": identity,
                        "ability_id": ability_id,
                        "choices": choices,
                    }
                )
    candidates.sort(
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )
    return tuple(candidates)


def _public_payment_signature(executor: Any, player_id: str, request_id: str) -> str:
    objects: list[dict[str, Any]] = []
    for source in executor.state.objects.values():
        if source.controller != player_id or source.zone is not Zone.BATTLEFIELD or source.retired:
            continue
        if not any(
            isinstance(ability, Mapping) and bool(ability.get("mana_ability"))
            for ability in source.current_characteristics.get("abilities", ())
        ):
            continue
        objects.append(
            {
                "handle": executor._strategic_handle(request_id, source.object_id),
                "tap": None if source.permanent_status is None else source.permanent_status.get("tap"),
                "identity": str(source.current_characteristics.get("name", "")),
            }
        )
    payload = {
        "mana_pool": dict(sorted(executor.state.players[player_id].mana_pool.items())),
        "sources": sorted(objects, key=lambda item: str(item["handle"])),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _resolve_source_handle(executor: Any, player_id: str, request_id: str, handle: str) -> GameObject:
    matches = [
        source
        for source in executor.state.objects.values()
        if not source.retired
        and not source.ceased_to_exist
        and source.zone is Zone.BATTLEFIELD
        and source.controller == player_id
        and executor._strategic_handle(request_id, source.object_id) == handle
    ]
    if len(matches) != 1:
        raise IllegalAction("resolution mana activation source handle is stale or ambiguous")
    return matches[0]


def activate_mana_ability_during_resolution(
    self: Any,
    player_id: str,
    request_id: str,
    activation: Mapping[str, Any],
) -> None:
    """Activate one mana ability during resolution without granting priority."""

    if int(getattr(self, "_resolution_depth", 0)) <= 0:
        raise IllegalAction("resolution mana ability may be used only while resolving an effect")
    source = _resolve_source_handle(self, player_id, request_id, str(activation.get("source_handle", "")))
    ability_id = str(activation.get("ability_id", ""))
    selected = self._ability_by_id(source, ability_id)
    if not bool(selected.get("mana_ability")):
        raise IllegalAction("resolution payment may activate only mana abilities")
    choices_raw = activation.get("choices", {})
    if not isinstance(choices_raw, Mapping):
        raise IllegalAction("resolution mana activation choices are malformed")
    previous_priority = self.state.turn.priority_holder_id
    self.state.turn.priority_holder_id = player_id
    try:
        self.activate(
            player_id,
            source.object_id,
            ability_id,
            choices={str(key): value for key, value in choices_raw.items()},
            _record=False,
        )
    finally:
        self.state.turn.priority_holder_id = previous_priority


def find_resolution_generic_payment_plan(
    self: Any,
    player_id: str,
    amount: int,
    request_id: str,
) -> tuple[Mapping[str, Any], ...] | None:
    """Return the canonical shortest public mana-ability plan, or prove none exists.

    Search is breadth-first and canonical over request-scoped public source handles.
    A hard bound is fail-closed: hitting it raises instead of falsely reporting that
    PAY is impossible.
    """

    if amount < 0:
        raise IllegalAction("resolution payment amount cannot be negative")
    if _can_pay_generic(self.state.players[player_id].mana_pool, amount):
        return ()

    root = _copy_executor(self)
    frontier: list[tuple[Any, tuple[Mapping[str, Any], ...]]] = [(root, ())]
    seen = {_public_payment_signature(root, player_id, request_id)}
    for depth in range(1, _MAX_RESOLUTION_MANA_ACTIVATIONS + 1):
        next_frontier: list[tuple[Any, tuple[Mapping[str, Any], ...]]] = []
        for executor, plan in frontier:
            for activation in _candidate_activations(executor, player_id, request_id):
                branch = _copy_executor(executor)
                try:
                    activate_mana_ability_during_resolution(
                        branch,
                        player_id,
                        request_id,
                        activation,
                    )
                except (IllegalAction, UnsupportedCapability):
                    continue
                new_plan = (*plan, activation)
                if _can_pay_generic(branch.state.players[player_id].mana_pool, amount):
                    return new_plan
                signature = _public_payment_signature(branch, player_id, request_id)
                if signature in seen:
                    continue
                seen.add(signature)
                next_frontier.append((branch, new_plan))
        if not next_frontier:
            return None
        frontier = next_frontier
        if depth == _MAX_RESOLUTION_MANA_ACTIVATIONS:
            raise UnsupportedCapability(
                "resolution mana-payment search reached its bounded activation limit"
            )
    return None


def execute_resolution_generic_payment_plan(
    self: Any,
    player_id: str,
    amount: int,
    request_id: str,
    plan: tuple[Mapping[str, Any], ...],
) -> dict[str, int]:
    for activation in plan:
        activate_mana_ability_during_resolution(self, player_id, request_id, activation)
    return pay_mana(self.state.players[player_id].mana_pool, {"GENERIC": amount})


__all__ = [
    "activate_mana_ability_during_resolution",
    "execute_resolution_generic_payment_plan",
    "find_resolution_generic_payment_plan",
]
