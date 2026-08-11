"""Opaque legal-action broker backed by production-executor probes."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from mtg_kernel.engine import GameExecutor
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.hashing import state_hash
from mtg_kernel.land_actions import play_land
from mtg_kernel.models import GameObject, TargetRef, Zone
from mtg_kernel.observation import ObservationService
from mtg_kernel.phase_b_actions import (
    activate_hand_ability,
    effect_execution_supported,
    foretell,
    legal_tutor_names,
    object_automatic_execution_supported,
)

PERMANENT_TYPES = {"Artifact", "Battle", "Creature", "Enchantment", "Planeswalker"}


@dataclass(frozen=True)
class ObservedAction:
    handle: str
    kind: str
    identity: str | None
    mana_value: int
    tags: tuple[str, ...]
    target_count: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _InternalAction:
    operation: str
    arguments: dict[str, Any]
    public: ObservedAction


class ActionBroker:
    """Generate only actions accepted by a cloned production executor."""

    def __init__(self, executor: GameExecutor, player_id: str) -> None:
        self.executor = executor
        self.player_id = player_id
        self.observations = ObservationService(executor.state)
        self.generation = 0
        self._state_token = ""
        self._actions: dict[str, _InternalAction] = {}

    def _handle(self, index: int, operation: str) -> str:
        material = (
            f"action:{self.player_id}:{self.generation}:{index}:{operation}:{self._state_token}"
        )
        return hashlib.sha256(material.encode()).hexdigest()[:24]

    @staticmethod
    def _tags(obj: GameObject, ability: dict[str, Any] | None = None) -> tuple[str, ...]:
        tags = set(str(value) for value in obj.current_characteristics.get("card_types", []))
        tags.update(str(value) for value in obj.current_characteristics.get("subtypes", []))
        if ability:
            effect = ability.get("effect", {})
            if isinstance(effect, dict):
                tags.add(str(effect.get("kind", "NONE")))
            tags.add(str(ability.get("kind", "")))
        name = str(obj.current_characteristics.get("name", ""))
        if name in {
            "Glint-Horn Buccaneer",
            "Dualcaster Mage",
            "Twinflame",
            "Electroduplicate",
            "Curiosity",
            "Niv-Mizzet, the Firemind",
            "Lightning-Rig Crew",
            "Crab Umbra",
            "Psychosis Crawler",
            "Malcolm, Keen-Eyed Navigator",
        }:
            tags.add("COMBO_COMPONENT")
        if tags.intersection(
            {"COUNTER_IF", "COUNTER", "COUNTER_UNLESS_PAY", "COUNTER_TARGETING_CONTROLLER"}
        ):
            tags.add("PROTECTION")
        if ability and ability.get("mana_ability"):
            tags.add("MANA_ABILITY")
        return tuple(sorted(value for value in tags if value))

    def _public_target_handles(self, targets: tuple[TargetRef, ...]) -> tuple[str, ...]:
        result: list[str] = []
        for target in targets:
            handle = self.observations.handle_for_object(
                self.player_id, self.generation, target.object_id
            )
            if handle is None:
                raise IllegalAction("a legal action target is not visible to the acting policy")
            result.append(handle)
        return tuple(result)

    def _target_sets(self, actor: str, schema: dict[str, Any]) -> tuple[tuple[TargetRef, ...], ...]:
        minimum = int(schema.get("min", 0))
        maximum_raw = schema.get("max")
        try:
            candidates = self.executor._legal_candidates(actor, schema)
        except UnsupportedCapability:
            return ()
        maximum = len(candidates) if maximum_raw is None else min(int(maximum_raw), len(candidates))
        values: list[tuple[TargetRef, ...]] = []
        for count in range(minimum, maximum + 1):
            values.extend(
                tuple(TargetRef(candidate.object_id) for candidate in selected)
                for selected in combinations(candidates, count)
            )
        return tuple(values) if values else (((),) if minimum == 0 else ())

    @staticmethod
    def _invoke(
        executor: GameExecutor,
        operation: str,
        arguments: dict[str, Any],
        *,
        record: bool,
    ) -> None:
        copied = deepcopy(arguments)
        if operation == "play_land":
            play_land(executor, record=record, **copied)
            return
        if operation == "activate_hand":
            activate_hand_ability(executor, record=record, **copied)
            return
        if operation == "foretell":
            foretell(executor, record=record, **copied)
            return
        method = getattr(executor, operation)
        method(_record=record, **copied)

    def _probe(self, operation: str, arguments: dict[str, Any]) -> bool:
        # Broker probes need mutable rules state, not a recursive copy of the
        # append-only replay transcript. Detaching it here applies the same
        # rollback-history optimization used by GameExecutor._begin_atomic.
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

    @staticmethod
    def _permanent_spell_ability() -> dict[str, Any]:
        return {
            "ability_id": "rules:permanent-spell",
            "kind": "SPELL",
            "mode": "default",
            "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
            "effect": {"kind": "NONE"},
        }

    @staticmethod
    def _effect_choice_variants(effect: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        kind = str(effect.get("kind", "NONE"))
        if kind == "SEQUENCE":
            variants: tuple[dict[str, Any], ...] = ({},)
            for child in effect.get("effects", ()):
                additions = ActionBroker._effect_choice_variants(dict(child))
                variants = tuple({**base, **extra} for base in variants for extra in additions)
            return variants
        if kind == "ADD_CHOSEN_MANA":
            return tuple({"mana_color": str(color)} for color in effect.get("choices", ()))
        if kind == "SCRY":
            return ({"scry_to_bottom": False}, {"scry_to_bottom": True})
        return ({},)

    @staticmethod
    def _ability_choice_variants(ability: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        return ActionBroker._effect_choice_variants(dict(ability.get("effect", {})))

    @staticmethod
    def _public_choice_metadata(choices: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in ("mana_color", "scry_to_bottom"):
            if key in choices:
                metadata[key] = choices[key]
        return metadata

    def _land_choice_variants(self, obj: GameObject) -> tuple[dict[str, Any], ...]:
        variants: list[dict[str, Any]] = [{}]
        for ability in obj.current_characteristics.get("abilities", []):
            if ability.get("kind") != "REPLACEMENT" or ability.get("event") != "ENTERS_BATTLEFIELD":
                continue
            effect = dict(ability.get("effect", {}))
            kind = str(effect.get("kind", ""))
            if kind == "ENTER_TAPPED":
                continue
            if kind == "CHOOSE_COLOR_ENTER_TAPPED":
                excluded = {str(value) for value in effect.get("excluded", ())}
                colors = [value for value in ("W", "U", "B", "R", "G") if value not in excluded]
                variants = [
                    {**base, "chosen_color": color} for base in variants for color in colors
                ]
                continue
            if kind == "REVEAL_OR_ENTER_TAPPED":
                allowed = {str(value) for value in effect.get("subtypes", ())}
                reveals = [
                    candidate
                    for candidate in self.executor.state.objects.values()
                    if not candidate.retired
                    and candidate.object_id != obj.object_id
                    and candidate.zone is Zone.HAND
                    and candidate.owner == self.player_id
                    and allowed.intersection(
                        str(value)
                        for value in candidate.current_characteristics.get("subtypes", [])
                    )
                ]
                options: list[dict[str, Any]] = [{}]
                options.extend({"reveal_object_id": candidate.object_id} for candidate in reveals)
                variants = [{**base, **option} for base in variants for option in options]
                continue
            return ()
        return tuple(variants)

    def _public_land_metadata(self, choices: dict[str, Any]) -> dict[str, Any]:
        metadata = self._public_choice_metadata(choices)
        if "chosen_color" in choices:
            metadata["chosen_color"] = str(choices["chosen_color"])
        reveal_id = choices.get("reveal_object_id")
        if reveal_id is not None:
            obj = self.executor.state.objects[str(reveal_id)]
            handle = self.observations.handle_for_object(
                self.player_id, self.generation, obj.object_id
            )
            if handle is None:
                raise IllegalAction("land reveal card is not visible to the acting policy")
            metadata["reveal_handle"] = handle
            metadata["reveal_identity"] = str(obj.current_characteristics.get("name", ""))
        else:
            metadata["reveal_identity"] = None
        return metadata

    def _candidate_casts(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for obj in self.executor.state.objects.values():
            if obj.retired or obj.ceased_to_exist or obj.owner != self.player_id:
                continue
            if obj.zone not in {Zone.HAND, Zone.COMMAND, Zone.GRAVEYARD, Zone.EXILE}:
                continue
            faces = obj.current_characteristics.get("faces", [])
            for face_index, face in enumerate(faces):
                card_types = set(str(value) for value in face.get("card_types", ()))
                if card_types.intersection(
                    PERMANENT_TYPES
                ) and not object_automatic_execution_supported(obj, entering=True):
                    continue
                modes = list(face.get("spell_modes", [])) or [self._permanent_spell_ability()]
                for raw_ability in modes:
                    ability = dict(raw_ability)
                    if not effect_execution_supported(dict(ability.get("effect", {}))):
                        continue
                    schema = dict(ability.get("target_schema", {}))
                    for targets in self._target_sets(self.player_id, schema):
                        for choices in self._ability_choice_variants(ability):
                            arguments = {
                                "actor": self.player_id,
                                "card_object_id": obj.object_id,
                                "targets": targets,
                                "face": face_index,
                                "x_value": 0,
                                "mode": ability.get("mode"),
                                "choices": choices,
                            }
                            if not self._probe("cast", arguments):
                                continue
                            target_handles = self._public_target_handles(targets)
                            public = ObservedAction(
                                "",
                                "CAST",
                                str(obj.current_characteristics.get("name")),
                                int(face.get("mana_value", 0)),
                                self._tags(obj, ability),
                                len(targets),
                                {
                                    "face": face_index,
                                    "mode": ability.get("mode"),
                                    "target_handles": target_handles,
                                    "cast_permission": ability.get("cast_permission", "NORMAL"),
                                    **self._public_choice_metadata(choices),
                                },
                            )
                            result.append(_InternalAction("cast", arguments, public))
        return result

    def _candidate_activations(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for obj in self.executor.state.objects.values():
            if obj.retired or obj.zone is not Zone.BATTLEFIELD or obj.controller != self.player_id:
                continue
            for raw_ability in obj.current_characteristics.get("abilities", []):
                ability = dict(raw_ability)
                if ability.get("kind") != "ACTIVATED":
                    continue
                if not effect_execution_supported(dict(ability.get("effect", {}))):
                    continue
                schema = dict(ability.get("target_schema", {}))
                for targets in self._target_sets(self.player_id, schema):
                    for choices in self._ability_choice_variants(ability):
                        arguments = {
                            "actor": self.player_id,
                            "source_id": obj.object_id,
                            "ability": str(ability["ability_id"]),
                            "targets": targets,
                            "choices": choices,
                        }
                        if not self._probe("activate", arguments):
                            continue
                        target_handles = self._public_target_handles(targets)
                        public = ObservedAction(
                            "",
                            "ACTIVATE",
                            str(obj.current_characteristics.get("name")),
                            0,
                            self._tags(obj, ability),
                            len(targets),
                            {
                                "ability_id": ability["ability_id"],
                                "target_handles": target_handles,
                                **self._public_choice_metadata(choices),
                            },
                        )
                        result.append(_InternalAction("activate", arguments, public))
        return result

    def _candidate_hand_activations(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        hand = self.executor.state.zones.get(f"{Zone.HAND.value}:{self.player_id}", [])
        for object_id in hand:
            obj = self.executor.state.objects[object_id]
            for raw_ability in obj.current_characteristics.get("abilities", []):
                ability = dict(raw_ability)
                if ability.get("kind") != "ACTIVATED":
                    continue
                cost = dict(ability.get("cost", {}))
                if int(cost.get("discard", 0)) != 1:
                    continue
                effect = dict(ability.get("effect", {}))
                if not effect_execution_supported(effect):
                    continue
                kind = str(effect.get("kind", ""))
                if kind in {"TRANSMUTE", "TYPECYCLE"}:
                    names = legal_tutor_names(self.executor, self.player_id, effect)
                    choice_variants = tuple({"tutor_name": name} for name in names) + (
                        {"tutor_name": "FAIL_TO_FIND"},
                    )
                else:
                    choice_variants = self._ability_choice_variants(ability)
                schema = dict(ability.get("target_schema", {}))
                for targets in self._target_sets(self.player_id, schema):
                    for choices in choice_variants:
                        arguments = {
                            "actor": self.player_id,
                            "source_id": obj.object_id,
                            "ability_id": str(ability["ability_id"]),
                            "targets": targets,
                            "choices": choices,
                        }
                        if not self._probe("activate_hand", arguments):
                            continue
                        metadata: dict[str, Any] = {
                            "ability_id": ability["ability_id"],
                            "target_handles": self._public_target_handles(targets),
                        }
                        if "tutor_name" in choices:
                            metadata["tutor_identity"] = choices["tutor_name"]
                        result.append(
                            _InternalAction(
                                "activate_hand",
                                arguments,
                                ObservedAction(
                                    "",
                                    "ACTIVATE_HAND",
                                    str(obj.current_characteristics.get("name", "")),
                                    0,
                                    self._tags(obj, ability),
                                    len(targets),
                                    metadata,
                                ),
                            )
                        )
        return result

    def _candidate_attack_declarations(self) -> list[_InternalAction]:
        """Expose a bounded set of legal multiplayer attack declarations.

        Attacker declaration is a simultaneous turn-based action, so the broker
        publishes complete legal plans rather than one attacker at a time.  The
        exact-deck no-blocker model needs single-attacker probes, all-in plans,
        and a spread plan that can damage multiple opponents for Pirate triggers.
        """
        if (
            self.executor.state.turn.active_player_id != self.player_id
            or self.executor.state.turn.step != "DECLARE_ATTACKERS"
        ):
            return []
        if any(
            event.kind == "ATTACKERS_DECLARED"
            and int(event.payload.get("turn_number", -1)) == self.executor.state.turn.number
            for event in self.executor.state.events
        ):
            return []
        attackers = sorted(
            (
                obj
                for obj in self.executor.state.objects.values()
                if self.executor._attack_eligible(self.player_id, obj)
            ),
            key=lambda obj: (str(obj.current_characteristics.get("name", "")), obj.object_id),
        )
        opponents = sorted(
            player.player_id
            for player in self.executor.state.players.values()
            if player.in_game and player.player_id != self.player_id
        )
        if not opponents:
            return []

        raw_plans: list[dict[str, str]] = [{}]
        for attacker in attackers:
            for opponent in opponents:
                raw_plans.append({attacker.object_id: opponent})
        if attackers:
            for opponent in opponents:
                raw_plans.append({attacker.object_id: opponent for attacker in attackers})
            raw_plans.append(
                {
                    attacker.object_id: opponents[index % len(opponents)]
                    for index, attacker in enumerate(attackers)
                }
            )

        seen: set[tuple[tuple[str, str], ...]] = set()
        result: list[_InternalAction] = []
        for plan in raw_plans:
            key = tuple(sorted(plan.items()))
            if key in seen:
                continue
            seen.add(key)
            arguments = {"actor": self.player_id, "assignments": dict(plan)}
            if not self._probe("declare_attackers", arguments):
                continue
            attacker_handles: list[str] = []
            identities: list[str] = []
            pirates = 0
            public_assignments: list[dict[str, str]] = []
            for object_id, opponent in sorted(plan.items()):
                obj = self.executor.state.objects[object_id]
                handle = self.observations.handle_for_object(
                    self.player_id, self.generation, object_id
                )
                if handle is None:
                    raise UnsupportedCapability("legal attacker is not publicly observable")
                identity = str(obj.current_characteristics.get("name", ""))
                attacker_handles.append(handle)
                identities.append(identity)
                if "Pirate" in obj.current_characteristics.get("subtypes", ()):
                    pirates += 1
                public_assignments.append({"attacker_handle": handle, "opponent": opponent})
            result.append(
                _InternalAction(
                    "declare_attackers",
                    arguments,
                    ObservedAction(
                        "",
                        "DECLARE_ATTACKERS",
                        None,
                        0,
                        ("COMBAT", "DECLARE_ATTACKERS"),
                        0,
                        {
                            "attacker_count": len(plan),
                            "attacker_handles": tuple(attacker_handles),
                            "attacker_identities": tuple(identities),
                            "pirate_count": pirates,
                            "opponent_count": len(set(plan.values())),
                            "assignments": tuple(public_assignments),
                        },
                    ),
                )
            )
        return result

    def _candidate_commander_choices(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        for object_id in self.executor.state.pending_commander_choices:
            obj = self.executor.state.objects[object_id]
            if obj.owner != self.player_id:
                continue
            handle = self.observations.handle_for_object(self.player_id, self.generation, object_id)
            if handle is None:
                raise UnsupportedCapability("pending commander choice is not visible to its owner")
            for return_to_command in (False, True):
                arguments = {
                    "player_id": self.player_id,
                    "object_id": object_id,
                    "return_to_command": return_to_command,
                }
                if not self._probe("commander_return_choice", arguments):
                    continue
                result.append(
                    _InternalAction(
                        "commander_return_choice",
                        arguments,
                        ObservedAction(
                            "",
                            "COMMANDER_RETURN",
                            str(obj.current_characteristics.get("name", "")),
                            0,
                            ("COMMANDER_CHOICE",),
                            0,
                            {
                                "object_handle": handle,
                                "destination": "COMMAND" if return_to_command else obj.zone.value,
                            },
                        ),
                    )
                )
        return result

    def _candidate_special_actions(self) -> list[_InternalAction]:
        result: list[_InternalAction] = []
        hand = self.executor.state.zones.get(f"{Zone.HAND.value}:{self.player_id}", [])
        for object_id in hand:
            obj = self.executor.state.objects[object_id]
            for raw_ability in obj.current_characteristics.get("abilities", []):
                ability = dict(raw_ability)
                if ability.get("kind") != "SPECIAL_ACTION":
                    continue
                if dict(ability.get("effect", {})).get("kind") != "FORETELL":
                    continue
                arguments = {
                    "actor": self.player_id,
                    "card_object_id": obj.object_id,
                    "ability_id": str(ability["ability_id"]),
                }
                if not self._probe("foretell", arguments):
                    continue
                result.append(
                    _InternalAction(
                        "foretell",
                        arguments,
                        ObservedAction(
                            "",
                            "FORETELL",
                            str(obj.current_characteristics.get("name", "")),
                            0,
                            self._tags(obj, ability),
                            0,
                            {"ability_id": ability["ability_id"]},
                        ),
                    )
                )
        return result

    def refresh(self) -> tuple[dict[str, Any], tuple[ObservedAction, ...]]:
        observation = self.observations.observe_for_policy(self.player_id)
        self.generation = int(observation["generation"])
        self._state_token = state_hash(self.executor.state)
        combat_declarations = self._candidate_attack_declarations()
        attack_declaration_pending = (
            self.executor.state.turn.step == "DECLARE_ATTACKERS"
            and not any(
                event.kind == "ATTACKERS_DECLARED"
                and int(event.payload.get("turn_number", -1)) == self.executor.state.turn.number
                for event in self.executor.state.events
            )
        )
        if attack_declaration_pending:
            candidates = combat_declarations
        else:
            candidates = self._candidate_commander_choices()
        if attack_declaration_pending:
            pass
        elif self.executor.state.pending_commander_choices:
            if not candidates:
                raise UnsupportedCapability("a pending commander choice requires its owning policy")
        else:
            unsafe = [
                obj
                for obj in self.executor.state.objects.values()
                if not obj.retired
                and not obj.ceased_to_exist
                and obj.zone is Zone.BATTLEFIELD
                and not object_automatic_execution_supported(obj, entering=False)
            ]
            if unsafe:
                raise UnsupportedCapability("battlefield contains unverified automatic behavior")
            hand = self.executor.state.zones.get(f"{Zone.HAND.value}:{self.player_id}", [])
            for object_id in hand:
                obj = self.executor.state.objects[object_id]
                if "Land" not in obj.current_characteristics.get("card_types", []):
                    continue
                if not object_automatic_execution_supported(obj, entering=True):
                    continue
                for choices in self._land_choice_variants(obj):
                    arguments = {
                        "actor": self.player_id,
                        "card_object_id": object_id,
                        "choices": choices,
                    }
                    if self._probe("play_land", arguments):
                        candidates.append(
                            _InternalAction(
                                "play_land",
                                arguments,
                                ObservedAction(
                                    "",
                                    "PLAY_LAND",
                                    str(obj.current_characteristics.get("name")),
                                    0,
                                    self._tags(obj),
                                    0,
                                    self._public_land_metadata(choices),
                                ),
                            )
                        )
            candidates.extend(self._candidate_casts())
            candidates.extend(self._candidate_activations())
            candidates.extend(self._candidate_hand_activations())
            candidates.extend(self._candidate_special_actions())
            pass_arguments = {"player_id": self.player_id}
            if self._probe("pass_priority", pass_arguments):
                candidates.append(
                    _InternalAction(
                        "pass_priority",
                        pass_arguments,
                        ObservedAction("", "PASS_PRIORITY", None, 0, (), 0, {}),
                    )
                )

        self._actions.clear()
        public: list[ObservedAction] = []
        for index, item in enumerate(candidates):
            handle = self._handle(index, item.operation)
            observed = ObservedAction(
                handle,
                item.public.kind,
                item.public.identity,
                item.public.mana_value,
                item.public.tags,
                item.public.target_count,
                dict(item.public.metadata),
            )
            self._actions[handle] = _InternalAction(item.operation, item.arguments, observed)
            public.append(observed)
        return observation, tuple(public)

    def execute(self, generation: int, action_handle: str) -> None:
        if generation != self.generation or state_hash(self.executor.state) != self._state_token:
            raise IllegalAction("legal-action handles have been revoked")
        item = self._actions.get(action_handle)
        if item is None:
            raise IllegalAction("unknown legal-action handle")
        self._invoke(self.executor, item.operation, item.arguments, record=True)
        self._actions.clear()
        self._state_token = ""
