"""Continuous, fail-closed combo-access detection for policy and measurement.

The tracker is observation-time infrastructure, not a reporting checkpoint.  It may
be attached to the shared executor and is sampled before and after every broker
action.  Turn 5/6/8/10 summaries are derived cumulatively from the earliest legal
turn, so an actual Turn 3 or Turn 4 line is never hidden by the first checkpoint.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.mana import parse_mana_cost, pay_mana
from mtg_kernel.models import GameObject, Zone

CHECKPOINTS = (5, 6, 8, 10)
MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}
_PROTECTION_EFFECTS = {
    "COUNTER",
    "COUNTER_IF",
    "COUNTER_TARGETING_CONTROLLER",
    "COUNTER_UNLESS_PAY",
    "COUNTER_UNLESS_PAY_EXILE",
    "AMASS_AND_HEXPROOF",
    "PHASE_OUT",
}


@dataclass(frozen=True)
class ComboAccessSnapshot:
    observation_index: int
    package: str
    turn: int
    pieces_assembled: bool
    sufficient_mana: bool
    legally_executable: bool
    usable_protection: bool
    full_table_kill: bool
    conditional_kill_or_takeover: bool
    blockers: tuple[str, ...]


class ComboAccessTracker:
    """Record combo access whenever the shared legal-action broker observes state."""

    def __init__(
        self,
        player_id: str,
        package_definitions: Mapping[str, Sequence[str]],
    ) -> None:
        self.player_id = player_id
        self.package_definitions = {
            str(package): tuple(str(card) for card in cards)
            for package, cards in package_definitions.items()
        }
        self.records: list[ComboAccessSnapshot] = []
        self._observation_index = 0

    @staticmethod
    def _active_objects(executor: Any) -> list[GameObject]:
        return [
            obj
            for obj in executor.state.objects.values()
            if not obj.retired and not obj.ceased_to_exist
        ]

    def _owned_names_by_zone(self, executor: Any) -> dict[Zone, list[str]]:
        result: dict[Zone, list[str]] = {zone: [] for zone in Zone}
        for obj in self._active_objects(executor):
            if obj.owner != self.player_id:
                continue
            name = str(obj.current_characteristics.get("name", ""))
            if name:
                result[obj.zone].append(name)
        return result

    @staticmethod
    def _can_pay_sequence(mana_pool: Mapping[str, int], costs: Sequence[str]) -> bool:
        pool = deepcopy(dict(mana_pool))
        try:
            for cost in costs:
                pay_mana(pool, parse_mana_cost(cost))
        except IllegalAction:
            return False
        return True

    def _controlled_creature_exists(self, executor: Any) -> bool:
        return any(
            obj.zone is Zone.BATTLEFIELD
            and obj.controller == self.player_id
            and "Creature" in obj.current_characteristics.get("card_types", ())
            for obj in self._active_objects(executor)
        )

    def _usable_protection_after_costs(self, executor: Any, costs: Sequence[str]) -> bool:
        pool = deepcopy(dict(executor.state.players[self.player_id].mana_pool))
        try:
            for cost in costs:
                pay_mana(pool, parse_mana_cost(cost))
        except IllegalAction:
            return False
        for obj in self._active_objects(executor):
            if obj.owner != self.player_id or obj.zone is not Zone.HAND:
                continue
            faces = obj.current_characteristics.get("faces", ())
            if not isinstance(faces, Sequence):
                continue
            effects: set[str] = set()
            mana_cost = ""
            for face in faces:
                if not isinstance(face, Mapping):
                    continue
                mana_cost = str(face.get("mana_cost", mana_cost))
                for ability in face.get("spell_modes", ()):
                    if isinstance(ability, Mapping):
                        effect = ability.get("effect", {})
                        if isinstance(effect, Mapping):
                            effects.add(str(effect.get("kind", "")))
            if not effects.intersection(_PROTECTION_EFFECTS):
                continue
            candidate_pool = deepcopy(pool)
            try:
                pay_mana(candidate_pool, parse_mana_cost(mana_cost))
            except IllegalAction:
                continue
            return True
        return False

    def _dualcaster_twinflame(self, executor: Any) -> ComboAccessSnapshot:
        zones = self._owned_names_by_zone(executor)
        hand = zones[Zone.HAND]
        pieces = "Dualcaster Mage" in hand and "Twinflame" in hand
        costs = ("{1}{R}", "{1}{R}{R}")
        sufficient = pieces and self._can_pay_sequence(
            executor.state.players[self.player_id].mana_pool,
            costs,
        )
        blockers: list[str] = []
        if not pieces:
            blockers.append("MISSING_COMPONENT")
        if pieces and not sufficient:
            blockers.append("INSUFFICIENT_MANA")
        if not self._controlled_creature_exists(executor):
            blockers.append("NO_TWINFLAME_TARGET")
        turn = executor.state.turn
        if turn.active_player_id != self.player_id:
            blockers.append("NOT_ACTIVE_PLAYER")
        if turn.priority_holder_id != self.player_id:
            blockers.append("NO_PRIORITY")
        if turn.phase not in MAIN_PHASES or executor.state.stack:
            blockers.append("SORCERY_TIMING_UNAVAILABLE")
        legal = pieces and sufficient and not blockers
        return ComboAccessSnapshot(
            self._observation_index,
            "dualcaster_twinflame",
            int(turn.number),
            pieces,
            sufficient,
            legal,
            legal and self._usable_protection_after_costs(executor, costs),
            legal,
            False,
            tuple(blockers),
        )

    def _unsupported_package(self, executor: Any, package: str) -> ComboAccessSnapshot:
        zones = self._owned_names_by_zone(executor)
        accessible = set(zones[Zone.HAND]) | set(zones[Zone.BATTLEFIELD]) | set(zones[Zone.COMMAND])
        required = set(self.package_definitions[package])
        assembled = required.issubset(accessible)
        return ComboAccessSnapshot(
            self._observation_index,
            package,
            int(executor.state.turn.number),
            assembled,
            False,
            False,
            False,
            False,
            assembled,
            ("PACKAGE_EXECUTION_DETECTOR_UNIMPLEMENTED",),
        )

    def observe(self, executor: Any) -> tuple[ComboAccessSnapshot, ...]:
        """Record all packages at the current state, regardless of checkpoint turn."""

        self._observation_index += 1
        current: list[ComboAccessSnapshot] = []
        for package in sorted(self.package_definitions):
            if package == "dualcaster_twinflame":
                snapshot = self._dualcaster_twinflame(executor)
            else:
                snapshot = self._unsupported_package(executor, package)
            current.append(snapshot)
            self.records.append(snapshot)
        return tuple(current)

    def earliest_legal_turn(self, package: str | None = None) -> int | None:
        turns = [
            record.turn
            for record in self.records
            if record.legally_executable and (package is None or record.package == package)
        ]
        return min(turns) if turns else None

    def cumulative_checkpoint_access(
        self,
        package: str | None = None,
        checkpoints: Sequence[int] = CHECKPOINTS,
    ) -> dict[int, bool]:
        earliest = self.earliest_legal_turn(package)
        return {int(turn): earliest is not None and earliest <= int(turn) for turn in checkpoints}


def bind_combo_access_tracker(
    executor: Any,
    player_id: str,
    package_definitions: Mapping[str, Sequence[str]],
) -> ComboAccessTracker:
    tracker = ComboAccessTracker(player_id, package_definitions)
    executor.combo_access_tracker = tracker
    return tracker
