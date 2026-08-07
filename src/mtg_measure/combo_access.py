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
    "COUNTER_WITH_DELAYED_DRAWS",
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

    def _objects_named(
        self, executor: Any, name: str, zones: Sequence[Zone] | None = None
    ) -> list[GameObject]:
        allowed = set(zones) if zones is not None else None
        return [
            obj
            for obj in self._active_objects(executor)
            if obj.owner == self.player_id
            and str(obj.current_characteristics.get("name", "")) == name
            and (allowed is None or obj.zone in allowed)
        ]

    @staticmethod
    def _is_untapped(obj: GameObject) -> bool:
        return obj.permanent_status is not None and obj.permanent_status.get("tap") == "UNTAPPED"

    def _can_use_tap_ability(self, executor: Any, obj: GameObject) -> bool:
        if obj.zone is not Zone.BATTLEFIELD or obj.controller != self.player_id or not self._is_untapped(obj):
            return False
        keywords = {str(value) for value in obj.current_characteristics.get("keywords", ())}
        if "Creature" not in obj.current_characteristics.get("card_types", ()) or "Haste" in keywords:
            return True
        status = obj.permanent_status or {}
        try:
            since = int(status.get("controller_since_turn", executor.state.turn.number))
        except (TypeError, ValueError):
            return False
        return since < int(executor.state.turn.number)

    @staticmethod
    def _mana_total(mana_pool: Mapping[str, int]) -> int:
        return sum(max(0, int(value)) for value in mana_pool.values())

    def _untapped_treasures(self, executor: Any) -> int:
        return sum(
            1
            for obj in self._active_objects(executor)
            if obj.zone is Zone.BATTLEFIELD
            and obj.controller == self.player_id
            and str(obj.current_characteristics.get("name", "")) == "Treasure"
            and self._is_untapped(obj)
        )

    def _available_generic_resources(self, executor: Any) -> int:
        return self._mana_total(executor.state.players[self.player_id].mana_pool) + self._untapped_treasures(executor)

    def _has_red_resource(self, executor: Any) -> bool:
        return int(executor.state.players[self.player_id].mana_pool.get("R", 0)) > 0 or self._untapped_treasures(executor) > 0

    def _main_phase_priority(self, executor: Any) -> bool:
        turn = executor.state.turn
        return bool(
            turn.active_player_id == self.player_id
            and turn.priority_holder_id == self.player_id
            and turn.phase in MAIN_PHASES
            and not executor.state.stack
        )

    def _accessible_names(self, executor: Any) -> set[str]:
        zones = self._owned_names_by_zone(executor)
        return set(zones[Zone.HAND]) | set(zones[Zone.BATTLEFIELD]) | set(zones[Zone.COMMAND])

    def _snapshot(
        self,
        executor: Any,
        package: str,
        *,
        pieces: bool,
        sufficient: bool,
        legal: bool,
        costs: Sequence[str] = (),
        full_table_kill: bool = False,
        conditional: bool = False,
        blockers: Sequence[str] = (),
    ) -> ComboAccessSnapshot:
        return ComboAccessSnapshot(
            self._observation_index,
            package,
            int(executor.state.turn.number),
            pieces,
            sufficient,
            legal,
            legal and self._usable_protection_after_costs(executor, costs),
            full_table_kill,
            conditional,
            tuple(blockers),
        )

    def _dualcaster_copy_spell(self, executor: Any, package: str, spell: str) -> ComboAccessSnapshot:
        hand_names = self._owned_names_by_zone(executor)[Zone.HAND]
        grave_names = self._owned_names_by_zone(executor)[Zone.GRAVEYARD]
        dualcaster_in_hand = "Dualcaster Mage" in hand_names
        normal_spell = spell in hand_names
        flashback_spell = spell == "Electroduplicate" and spell in grave_names
        pieces = dualcaster_in_hand and (normal_spell or flashback_spell)
        spell_cost = "{1}{R}" if spell == "Twinflame" else ("{2}{R}" if normal_spell else "{2}{R}{R}")
        costs = (spell_cost, "{1}{R}{R}")
        sufficient = pieces and self._can_pay_sequence(
            executor.state.players[self.player_id].mana_pool, costs
        )
        controlled_target = self._controlled_creature_exists(executor)
        timing = self._main_phase_priority(executor)
        blockers: list[str] = []
        if not dualcaster_in_hand:
            blockers.append("DUALCASTER_NOT_IN_HAND")
        if not normal_spell and not flashback_spell:
            blockers.append("COPY_SPELL_UNAVAILABLE")
        if pieces and not sufficient:
            blockers.append("INSUFFICIENT_MANA")
        if not controlled_target:
            blockers.append("NO_INITIAL_COPY_TARGET")
        if not timing:
            blockers.append("SORCERY_TIMING_UNAVAILABLE")
        legal = pieces and sufficient and controlled_target and timing
        return self._snapshot(
            executor,
            package,
            pieces=pieces,
            sufficient=sufficient,
            legal=legal,
            costs=costs,
            full_table_kill=legal,
            blockers=blockers,
        )

    def _dualcaster_twinflame(self, executor: Any) -> ComboAccessSnapshot:
        return self._dualcaster_copy_spell(executor, "dualcaster_twinflame", "Twinflame")

    def _dualcaster_electroduplicate(self, executor: Any) -> ComboAccessSnapshot:
        return self._dualcaster_copy_spell(
            executor, "dualcaster_electroduplicate", "Electroduplicate"
        )

    @staticmethod
    def _living_opponent_life(executor: Any, player_id: str) -> dict[str, int]:
        return {
            pid: int(player.life)
            for pid, player in executor.state.players.items()
            if pid != player_id and player.in_game and player.life > 0
        }

    @staticmethod
    def _loop_can_kill_with_generated_mana(
        life: Mapping[str, int],
        *,
        starting_resources: int,
        activation_cost: int,
        generated_per_hit: bool,
        maximum_iterations: int,
    ) -> bool:
        remaining = dict(life)
        resources = starting_resources
        for _ in range(maximum_iterations):
            if not remaining:
                return True
            if resources < activation_cost:
                return False
            resources -= activation_cost
            damaged = len(remaining)
            if generated_per_hit:
                resources += damaged
            for player_id in tuple(remaining):
                remaining[player_id] -= 1
                if remaining[player_id] <= 0:
                    del remaining[player_id]
        return not remaining

    def _malcolm_glint_horn(self, executor: Any) -> ComboAccessSnapshot:
        accessible = self._accessible_names(executor)
        pieces = {"Malcolm, Keen-Eyed Navigator", "Glint-Horn Buccaneer"}.issubset(accessible)
        malcolm_battle = self._objects_named(
            executor, "Malcolm, Keen-Eyed Navigator", (Zone.BATTLEFIELD,)
        )
        glint_battle = self._objects_named(executor, "Glint-Horn Buccaneer", (Zone.BATTLEFIELD,))
        glint = glint_battle[0] if glint_battle else None
        hand_key = executor.zones.zone_key(Zone.HAND, self.player_id)
        hand_count = len(executor.state.zones.get(hand_key, ()))
        missing_cast_costs: list[str] = []
        if not malcolm_battle and "Malcolm, Keen-Eyed Navigator" in accessible:
            missing_cast_costs.append("{2}{U}")
        if glint is None and "Glint-Horn Buccaneer" in accessible:
            missing_cast_costs.append("{1}{R}{R}")
        costs = tuple(missing_cast_costs + ["{1}{R}"])
        enough_cast_and_activate = pieces and self._can_pay_sequence(
            executor.state.players[self.player_id].mana_pool, costs
        )
        can_reach_attack = False
        if glint is not None:
            can_reach_attack = bool(
                glint.current_characteristics.get("attacking") is True
                or (
                    executor.state.turn.phase == "PRECOMBAT_MAIN"
                    and self._main_phase_priority(executor)
                    and (
                        "Haste" in glint.current_characteristics.get("keywords", ())
                        or self._can_use_tap_ability(executor, glint)
                    )
                )
            )
        elif self._main_phase_priority(executor):
            # Glint-Horn has haste, so a cast in precombat main can attack this turn.
            can_reach_attack = executor.state.turn.phase == "PRECOMBAT_MAIN"
        remaining_hand = hand_count - sum(
            1
            for name in ("Malcolm, Keen-Eyed Navigator", "Glint-Horn Buccaneer")
            if name in self._owned_names_by_zone(executor)[Zone.HAND] and not self._objects_named(executor, name, (Zone.BATTLEFIELD,))
        )
        has_discard = remaining_hand > 0
        sufficient = enough_cast_and_activate and has_discard
        legal = bool(
            pieces
            and malcolm_battle
            and glint is not None
            and glint.current_characteristics.get("attacking") is True
            and self._has_red_resource(executor)
            and self._available_generic_resources(executor) >= 2
            and has_discard
            and executor.state.turn.priority_holder_id == self.player_id
        )
        # Access before attackers are declared is still a deterministic this-turn line
        # when every missing piece can be cast and Glint-Horn can legally attack.
        this_turn_access = pieces and sufficient and can_reach_attack and self._main_phase_priority(executor)
        legal = legal or this_turn_access
        life = self._living_opponent_life(executor, self.player_id)
        library_key = executor.zones.zone_key(Zone.LIBRARY, self.player_id)
        max_iterations = len(executor.state.zones.get(library_key, ())) + (1 if has_discard else 0)
        full_kill = legal and self._loop_can_kill_with_generated_mana(
            life,
            starting_resources=self._available_generic_resources(executor),
            activation_cost=2,
            generated_per_hit=True,
            maximum_iterations=max_iterations,
        )
        blockers: list[str] = []
        if not pieces:
            blockers.append("MISSING_COMPONENT")
        if pieces and not sufficient:
            blockers.append("INSUFFICIENT_MANA_OR_DISCARD")
        if pieces and not can_reach_attack:
            blockers.append("GLINT_HORN_CANNOT_ATTACK_OR_IS_NOT_ATTACKING")
        if legal and not full_kill:
            blockers.append("FINITE_RESOURCES_DO_NOT_PROVE_TABLE_KILL")
        return self._snapshot(
            executor,
            "malcolm_glint_horn",
            pieces=pieces,
            sufficient=sufficient,
            legal=legal,
            costs=costs,
            full_table_kill=full_kill,
            conditional=legal and not full_kill,
            blockers=blockers,
        )

    def _lightning_rig_crab_umbra_malcolm(self, executor: Any) -> ComboAccessSnapshot:
        accessible = self._accessible_names(executor)
        required = {
            "Lightning-Rig Crew",
            "Crab Umbra",
            "Malcolm, Keen-Eyed Navigator",
        }
        pieces = required.issubset(accessible)
        crew_list = self._objects_named(executor, "Lightning-Rig Crew", (Zone.BATTLEFIELD,))
        malcolm = self._objects_named(executor, "Malcolm, Keen-Eyed Navigator", (Zone.BATTLEFIELD,))
        aura_list = self._objects_named(executor, "Crab Umbra", (Zone.BATTLEFIELD,))
        crew = crew_list[0] if crew_list else None
        attached = bool(
            crew is not None
            and any(
                aura.attached_to_ref is not None and aura.attached_to_ref.object_id == crew.object_id
                for aura in aura_list
            )
        )
        crew_ready = crew is not None and self._can_use_tap_ability(executor, crew)
        life = self._living_opponent_life(executor, self.player_id)
        enough_opponents = len(life) >= 1
        sufficient = pieces and crew_ready and attached and enough_opponents
        legal = sufficient and bool(malcolm) and executor.state.turn.priority_holder_id == self.player_id
        full_kill = legal and self._loop_can_kill_with_generated_mana(
            life,
            starting_resources=self._available_generic_resources(executor) + 3,
            activation_cost=3,
            generated_per_hit=True,
            maximum_iterations=max(life.values(), default=0),
        )
        blockers: list[str] = []
        if not pieces:
            blockers.append("MISSING_COMPONENT")
        if not malcolm:
            blockers.append("MALCOLM_NOT_ON_BATTLEFIELD")
        if crew is None:
            blockers.append("LIGHTNING_RIG_CREW_NOT_ON_BATTLEFIELD")
        elif not crew_ready:
            blockers.append("LIGHTNING_RIG_CREW_CANNOT_TAP")
        if not attached:
            blockers.append("CRAB_UMBRA_NOT_ATTACHED_TO_CREW")
        if legal and not full_kill:
            blockers.append("TREASURE_RESERVE_DOES_NOT_PROVE_TABLE_KILL")
        return self._snapshot(
            executor,
            "lightning_rig_crab_umbra_malcolm",
            pieces=pieces,
            sufficient=sufficient,
            legal=legal,
            full_table_kill=full_kill,
            conditional=legal and not full_kill,
            blockers=blockers,
        )

    def _niv_mizzet_curiosity(self, executor: Any) -> ComboAccessSnapshot:
        accessible = self._accessible_names(executor)
        pieces = {"Niv-Mizzet, the Firemind", "Curiosity"}.issubset(accessible)
        niv_list = self._objects_named(executor, "Niv-Mizzet, the Firemind", (Zone.BATTLEFIELD,))
        niv = niv_list[0] if niv_list else None
        curiosity_list = self._objects_named(executor, "Curiosity", (Zone.BATTLEFIELD,))
        attached = bool(
            niv is not None
            and any(
                aura.attached_to_ref is not None and aura.attached_to_ref.object_id == niv.object_id
                for aura in curiosity_list
            )
        )
        curiosity_in_hand = bool(self._objects_named(executor, "Curiosity", (Zone.HAND,)))
        niv_ready = niv is not None and self._can_use_tap_ability(executor, niv)
        cast_curiosity = (
            curiosity_in_hand
            and niv is not None
            and self._main_phase_priority(executor)
            and self._can_pay_sequence(executor.state.players[self.player_id].mana_pool, ("{U}",))
        )
        sufficient = pieces and niv_ready and (attached or cast_curiosity)
        legal = sufficient and executor.state.turn.priority_holder_id == self.player_id
        life = self._living_opponent_life(executor, self.player_id)
        library_key = executor.zones.zone_key(Zone.LIBRARY, self.player_id)
        available_draws = len(executor.state.zones.get(library_key, ()))
        full_kill = legal and available_draws >= sum(life.values())
        blockers: list[str] = []
        if not pieces:
            blockers.append("MISSING_COMPONENT")
        if niv is None:
            blockers.append("NIV_MIZZET_NOT_ON_BATTLEFIELD")
        elif not niv_ready:
            blockers.append("NIV_MIZZET_CANNOT_TAP")
        if not attached and not cast_curiosity:
            blockers.append("CURIOSITY_NOT_ATTACHED_OR_CASTABLE")
        if legal and not full_kill:
            blockers.append("LIBRARY_TOO_SMALL_FOR_PROVEN_TABLE_KILL")
        return self._snapshot(
            executor,
            "niv_mizzet_curiosity",
            pieces=pieces,
            sufficient=sufficient,
            legal=legal,
            costs=("{U}",) if cast_curiosity else (),
            full_table_kill=full_kill,
            conditional=legal and not full_kill,
            blockers=blockers,
        )

    def _psychosis_crawler_draw(self, executor: Any) -> ComboAccessSnapshot:
        crawler = self._objects_named(executor, "Psychosis Crawler", (Zone.BATTLEFIELD,))
        hand_crawler = self._objects_named(executor, "Psychosis Crawler", (Zone.HAND,))
        pieces = bool(crawler or hand_crawler)
        can_cast = bool(
            hand_crawler
            and self._main_phase_priority(executor)
            and self._can_pay_sequence(executor.state.players[self.player_id].mana_pool, ("{5}",))
        )
        active = bool(crawler) or can_cast
        # This package is intentionally conditional: Crawler converts subsequent draws
        # into life loss but does not itself supply an unbounded draw engine.
        sufficient = active
        legal = active and executor.state.turn.priority_holder_id == self.player_id
        blockers: list[str] = []
        if not pieces:
            blockers.append("PSYCHOSIS_CRAWLER_UNAVAILABLE")
        if pieces and not active:
            blockers.append("PSYCHOSIS_CRAWLER_NOT_CASTABLE")
        return self._snapshot(
            executor,
            "psychosis_crawler_draw",
            pieces=pieces,
            sufficient=sufficient,
            legal=legal,
            costs=("{5}",) if can_cast else (),
            full_table_kill=False,
            conditional=legal,
            blockers=blockers,
        )

    def observe(self, executor: Any) -> tuple[ComboAccessSnapshot, ...]:
        """Record all packages at the current state, regardless of checkpoint turn."""

        self._observation_index += 1
        current: list[ComboAccessSnapshot] = []
        detectors = {
            "dualcaster_twinflame": self._dualcaster_twinflame,
            "dualcaster_electroduplicate": self._dualcaster_electroduplicate,
            "malcolm_glint_horn": self._malcolm_glint_horn,
            "lightning_rig_crab_umbra_malcolm": self._lightning_rig_crab_umbra_malcolm,
            "niv_mizzet_curiosity": self._niv_mizzet_curiosity,
            "psychosis_crawler_draw": self._psychosis_crawler_draw,
        }
        for package in sorted(self.package_definitions):
            detector = detectors.get(package)
            if detector is None:
                raise ValueError(f"unregistered frozen combo package: {package}")
            snapshot = detector(executor)
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
