"""Single legality, payment, stack, priority, resolution, trigger, SBA, and turn path."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.identity import IdentityService
from mtg_kernel.mana import add_mana, combine_costs, multiply_cost, parse_mana_cost, pay_mana
from mtg_kernel.models import (
    Action,
    Choice,
    CopyKind,
    Event,
    GameObject,
    GameState,
    ObjectKind,
    ReferenceMode,
    TargetRef,
    Zone,
)
from mtg_kernel.serialization import state_to_data
from mtg_kernel.zones import ZoneService

PERMANENT_TYPES = {"Artifact", "Creature", "Enchantment"}
MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}


class GameExecutor:
    """Deck-scoped executor whose control flow dispatches only declarative primitives."""

    def __init__(
        self,
        state: GameState,
        seed: str = "phase-a",
        *,
        replaying: bool = False,
    ) -> None:
        self.state = state
        self.seed = seed
        self.replaying = replaying
        self.identity = IdentityService(state, seed)
        self.zones = ZoneService(state, self.identity)
        self._resolution_depth = 0

    def _event(self, kind: str, action: Action | None = None, **payload: Any) -> Event:
        event = Event(
            self.identity.new_id("event"),
            kind,
            action.action_id if action else None,
            payload,
        )
        self.state.events.append(event)
        return event

    def _ensure_active(self) -> None:
        if self.state.terminal.status != "ACTIVE":
            raise IllegalAction("game is terminal")

    def _begin_atomic(self) -> GameState:
        before = deepcopy(self.state)
        if not self.replaying and self.state.replay_initial_state is None:
            self.state.replay_initial_state = state_to_data(self.state)
        return before

    def _rollback(self, before: GameState) -> None:
        self.state.__dict__.clear()
        self.state.__dict__.update(before.__dict__)

    def _record_command(self, operation: str, **arguments: Any) -> None:
        if not self.replaying:
            self.state.replay_commands.append({"operation": operation, "arguments": arguments})

    @staticmethod
    def _target_data(ref: TargetRef) -> dict[str, Any]:
        return {
            "object_id": ref.object_id,
            "mode": ref.mode.value,
            "capability": ref.capability,
            "authority": ref.authority,
        }

    @staticmethod
    def _target_from_data(data: dict[str, Any]) -> TargetRef:
        return TargetRef(
            str(data["object_id"]),
            ReferenceMode(str(data.get("mode", ReferenceMode.CURRENT_OBJECT_REQUIRED.value))),
            data.get("capability"),
            data.get("authority"),
        )

    def _created_action(self, obj: GameObject) -> Action:
        if obj.created_by_event_id is None:
            raise IllegalAction("stack object has no causal creation event")
        event = next(
            (item for item in self.state.events if item.event_id == obj.created_by_event_id),
            None,
        )
        if event is None or event.cause_action_id is None:
            raise IllegalAction("stack object is not linked to an action")
        return next(
            action for action in self.state.actions if action.action_id == event.cause_action_id
        )

    @staticmethod
    def _types(obj: GameObject) -> set[str]:
        return set(obj.current_characteristics.get("card_types", []))

    @staticmethod
    def _is_permanent(obj: GameObject) -> bool:
        return obj.zone is Zone.BATTLEFIELD and obj.object_kind in {
            ObjectKind.PERMANENT,
            ObjectKind.TOKEN_OBJECT,
            ObjectKind.EXTERNAL_PUBLIC_OBJECT,
        }

    def _target_matches(self, actor: str, obj: GameObject, kind: str) -> bool:
        types = self._types(obj)
        if kind == "NONE":
            return False
        if kind == "CREATURE":
            return self._is_permanent(obj) and "Creature" in types
        if kind == "ARTIFACT":
            return self._is_permanent(obj) and "Artifact" in types
        if kind == "GRAVEYARD_CARD":
            return obj.zone is Zone.GRAVEYARD and bool(obj.component_card_instance_ids)
        if kind == "SPELL_OR_NONLAND_PERMANENT":
            return (
                obj.zone is Zone.STACK
                and obj.object_kind in {ObjectKind.SPELL, ObjectKind.SPELL_COPY}
            ) or (self._is_permanent(obj) and "Land" not in types)
        if kind == "INSTANT_OR_SORCERY_SPELL":
            return (
                obj.zone is Zone.STACK
                and obj.object_kind in {ObjectKind.SPELL, ObjectKind.SPELL_COPY}
                and bool(types.intersection({"Instant", "Sorcery"}))
            )
        if kind == "CONTROLLED_CREATURE":
            return self._is_permanent(obj) and obj.controller == actor and "Creature" in types
        raise UnsupportedCapability(f"unsupported target schema: {kind}")

    def _validate_targets(
        self,
        actor: str,
        targets: tuple[TargetRef, ...],
        schema: dict[str, Any],
    ) -> list[GameObject]:
        kind = str(schema.get("kind", "NONE"))
        minimum = int(schema.get("min", 0))
        maximum_value = schema.get("max")
        maximum = int(maximum_value) if maximum_value is not None else None
        if len(targets) < minimum or (maximum is not None and len(targets) > maximum):
            raise IllegalAction("target count does not match the declared schema")
        if schema.get("unique", False) and len({target.object_id for target in targets}) != len(
            targets
        ):
            raise IllegalAction("targets must be distinct")
        if kind == "NONE" and targets:
            raise IllegalAction("this action has no targets")
        resolved: list[GameObject] = []
        for ref in targets:
            value = self.identity.resolve_reference(ref)
            if not isinstance(value, GameObject) or not self._target_matches(actor, value, kind):
                raise IllegalAction(f"illegal {kind} target")
            resolved.append(value)
        return resolved

    def _legal_candidates(self, actor: str, schema: dict[str, Any]) -> list[GameObject]:
        kind = str(schema.get("kind", "NONE"))
        if kind == "NONE":
            return []
        return [
            obj
            for obj in self.state.objects.values()
            if not obj.retired
            and not obj.ceased_to_exist
            and self._target_matches(actor, obj, kind)
        ]

    def _selected_face(self, card: GameObject, face: int) -> dict[str, Any]:
        faces = card.current_characteristics.get("faces")
        if not isinstance(faces, list) or not 0 <= face < len(faces):
            raise IllegalAction("selected card face does not exist")
        selected = faces[face]
        if not isinstance(selected, dict):
            raise IllegalAction("selected card face is malformed")
        return selected

    @staticmethod
    def _selected_spell_ability(face_data: dict[str, Any], mode: str | None) -> dict[str, Any]:
        spell_modes = list(face_data.get("spell_modes", []))
        if not spell_modes:
            if mode not in {None, "default"}:
                raise IllegalAction("permanent spell has no selectable mode")
            return {
                "ability_id": "rules:permanent-spell",
                "kind": "SPELL",
                "mode": "default",
                "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
                "effect": {"kind": "NONE"},
            }
        if mode is None:
            if len(spell_modes) != 1:
                raise IllegalAction("an explicit spell mode is required")
            return dict(spell_modes[0])
        matches = [ability for ability in spell_modes if ability.get("mode") == mode]
        if len(matches) != 1:
            raise IllegalAction("selected spell mode is unavailable")
        return dict(matches[0])

    def _validate_cast_timing(
        self,
        actor: str,
        card: GameObject,
        face_data: dict[str, Any],
        spell_ability: dict[str, Any],
    ) -> None:
        if self.state.turn.priority_holder_id != actor:
            raise IllegalAction("the casting player does not have priority")
        if card.owner != actor:
            raise IllegalAction("a player may not cast another player's physical card")
        card_types = set(face_data.get("card_types", []))
        if "Land" in card_types:
            raise IllegalAction("lands are played, not cast")
        permission = spell_ability.get("cast_permission", "NORMAL")
        if card.zone is Zone.GRAVEYARD and permission not in {"AFTERMATH", "FLASHBACK"}:
            raise IllegalAction("no graveyard casting permission")
        if permission in {"AFTERMATH", "FLASHBACK"} and card.zone is not Zone.GRAVEYARD:
            raise IllegalAction("this face may be cast only from the graveyard")
        if card.zone is Zone.COMMAND:
            if not card.component_card_instance_ids:
                raise IllegalAction("command-zone card has no physical identity")
            instance = self.state.card_instances[card.component_card_instance_ids[0]]
            if not instance.commander_designation or instance.owner_id != actor:
                raise IllegalAction("only a designated commander may be cast from command")
        if card.zone not in {Zone.HAND, Zone.COMMAND, Zone.GRAVEYARD}:
            raise IllegalAction("card is not castable from its current zone")
        instant_speed = "Instant" in card_types or "Flash" in face_data.get("keywords", [])
        if not instant_speed:
            if actor != self.state.turn.active_player_id:
                raise IllegalAction("sorcery-speed spell requires the active player")
            if self.state.turn.phase not in MAIN_PHASES or self.state.stack:
                raise IllegalAction("sorcery-speed timing is not available")

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
        self._ensure_active()
        before = self._begin_atomic()
        choices = dict(choices or {})
        try:
            card = self.state.objects[card_object_id]
            if card.retired or card.ceased_to_exist:
                raise IllegalAction("card object is unavailable")
            face_data = self._selected_face(card, face)
            spell_ability = self._selected_spell_ability(face_data, mode)
            self._validate_cast_timing(actor, card, face_data, spell_ability)
            schema = dict(spell_ability.get("target_schema", {}))
            self._validate_targets(actor, targets, schema)

            base_cost = parse_mana_cost(str(face_data.get("mana_cost", "")), x_value=x_value)
            extra_cost = {symbol: 0 for symbol in (*("W", "U", "B", "R", "G", "C"), "GENERIC")}
            per_target = spell_ability.get("additional_cost", {}).get("per_target_beyond_first")
            if per_target:
                extra_cost = multiply_cost(
                    parse_mana_cost(str(per_target)), max(0, len(targets) - 1)
                )
            commander_tax = {"GENERIC": 0}
            old_zone = card.zone
            if old_zone is Zone.COMMAND:
                instance_id = card.component_card_instance_ids[0]
                commander_tax["GENERIC"] = 2 * self.state.commander_cast_counts.get(instance_id, 0)
            total_cost = combine_costs(base_cost, extra_cost, commander_tax)
            payment = pay_mana(self.state.players[actor].mana_pool, total_cost)

            action = Action(
                self.identity.new_id("action"),
                "CAST",
                actor,
                card_object_id,
                targets,
                (str(spell_ability.get("mode", "default")),),
                x_value,
                {"mana": payment, "cost": total_cost},
                {
                    "face": face,
                    "ability_id": spell_ability["ability_id"],
                    "target_schema": schema,
                    "choices": choices,
                },
            )
            self.state.actions.append(action)
            self.state.target_records.append(
                {
                    "action_id": action.action_id,
                    "targets": [self._target_data(target) for target in targets],
                }
            )
            event = self._event("SPELL_CAST", action, payment=payment)
            spell = self.zones.move(
                card.object_id,
                Zone.STACK,
                "CAST",
                event,
                object_kind=ObjectKind.SPELL,
                controller=actor,
                face=face,
                explicit_characteristics={
                    "selected_face_index": face,
                    "cast_choices": choices,
                    "cast_payment": payment,
                    "modes": list(action.modes),
                    "x_value": x_value,
                },
            )
            if spell is None:
                raise IllegalAction("a physical card is required to cast")
            spell.was_cast = True
            self.state.pending_actions.append(action.action_id)
            if old_zone is Zone.COMMAND:
                instance_id = spell.component_card_instance_ids[0]
                self.state.commander_cast_counts[instance_id] = (
                    self.state.commander_cast_counts.get(instance_id, 0) + 1
                )
            self.state.turn.priority_holder_id = actor
            self.state.turn.consecutive_priority_passes = 0
            if _record:
                self._record_command(
                    "cast",
                    actor=actor,
                    card_object_id=card_object_id,
                    targets=[self._target_data(target) for target in targets],
                    face=face,
                    x_value=x_value,
                    mode=mode,
                    choices=choices,
                )
            return spell
        except Exception:
            self._rollback(before)
            raise

    def _ability_by_id(self, source: GameObject, ability_id: str) -> dict[str, Any]:
        abilities = source.current_characteristics.get("abilities", [])
        matches = [ability for ability in abilities if ability.get("ability_id") == ability_id]
        if len(matches) != 1 or matches[0].get("kind") != "ACTIVATED":
            raise IllegalAction("activated ability is unavailable")
        return dict(matches[0])

    def _discard_card(self, player_id: str, object_id: str, action: Action) -> GameObject:
        card = self.state.objects[object_id]
        if card.owner != player_id or card.zone is not Zone.HAND or card.retired:
            raise IllegalAction("discard cost requires a card in the player's hand")
        event = self._event("CARD_DISCARDED", action, player_id=player_id, object_id=object_id)
        successor = self.zones.move(object_id, Zone.GRAVEYARD, "DISCARD_COST", event)
        if successor is None:
            raise IllegalAction("discarded physical card did not reach the graveyard")
        self._scan_discard_triggers(player_id, action, event)
        return successor

    def activate(
        self,
        actor: str,
        source_id: str,
        ability: str | dict[str, Any],
        targets: tuple[TargetRef, ...] = (),
        choices: dict[str, Any] | None = None,
        *,
        _record: bool = True,
    ) -> GameObject | None:
        self._ensure_active()
        before = self._begin_atomic()
        choices = dict(choices or {})
        try:
            source = self.state.objects[source_id]
            if source.retired or source.ceased_to_exist or source.zone is not Zone.BATTLEFIELD:
                raise IllegalAction("activated ability source is unavailable")
            if source.controller != actor:
                raise IllegalAction("a player may activate only an ability they control")
            ability_id = str(ability.get("ability_id")) if isinstance(ability, dict) else ability
            selected = self._ability_by_id(source, ability_id)
            if self.state.turn.priority_holder_id != actor:
                raise IllegalAction("the activating player does not have priority")
            mana_ability = bool(selected.get("mana_ability"))
            if selected.get(
                "restriction"
            ) == "SOURCE_ATTACKING" and not source.current_characteristics.get("attacking", False):
                raise IllegalAction("this ability may be activated only while the source attacks")
            schema = dict(
                selected.get("target_schema", {"kind": "NONE", "min": 0, "max": 0, "unique": True})
            )
            self._validate_targets(actor, targets, schema)
            cost = dict(selected.get("cost", {}))
            mana_cost = parse_mana_cost(str(cost.get("mana", "")))
            payment = pay_mana(self.state.players[actor].mana_pool, mana_cost)
            if cost.get("tap"):
                status = source.permanent_status
                if status is None or status.get("tap") != "UNTAPPED":
                    raise IllegalAction("tap cost requires an untapped permanent")
                status["tap"] = "TAPPED"

            action = Action(
                self.identity.new_id("action"),
                "ACTIVATE",
                actor,
                source_id,
                targets,
                (),
                0,
                {"mana": payment, "cost": mana_cost},
                {"ability_id": ability_id, "target_schema": schema, "choices": choices},
            )
            self.state.actions.append(action)
            self.state.target_records.append(
                {
                    "action_id": action.action_id,
                    "targets": [self._target_data(target) for target in targets],
                }
            )
            activated_event = self._event("ABILITY_ACTIVATED", action, ability_id=ability_id)
            ability_object: GameObject | None = None
            if not mana_ability:
                ability_object = GameObject(
                    self.identity.new_id("object"),
                    ObjectKind.ACTIVATED_ABILITY,
                    Zone.STACK,
                    None,
                    actor,
                    source_object_id=source_id,
                    created_by_event_id=activated_event.event_id,
                    current_characteristics={"ability": selected},
                    was_cast=False,
                )
                self.state.objects[ability_object.object_id] = ability_object
                self.zones.register(ability_object)
                self.state.pending_actions.append(action.action_id)

            discard_count = int(cost.get("discard", 0))
            discard_ids = list(choices.get("discard_ids", []))
            if len(discard_ids) != discard_count:
                raise IllegalAction("activation requires explicit discard-cost choices")
            for discard_id in discard_ids:
                self._discard_card(actor, str(discard_id), action)
            if cost.get("sacrifice_source"):
                self.zones.move(
                    source_id,
                    Zone.GRAVEYARD,
                    "ACTIVATION_COST_SACRIFICE",
                    self._event("SOURCE_SACRIFICED", action),
                )

            if mana_ability:
                self._apply_effect(None, action, dict(selected.get("effect", {})), [], choices)
                self.check_state_based_actions()
            else:
                self.put_waiting_triggers_on_stack()
                self.state.turn.priority_holder_id = actor
                self.state.turn.consecutive_priority_passes = 0
            if _record:
                self._record_command(
                    "activate",
                    actor=actor,
                    source_id=source_id,
                    ability_id=ability_id,
                    targets=[self._target_data(target) for target in targets],
                    choices=choices,
                )
            return ability_object
        except Exception:
            self._rollback(before)
            raise

    def pass_priority(self, player_id: str, *, _record: bool = True) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        try:
            if self.state.turn.priority_holder_id != player_id:
                raise IllegalAction("player does not have priority")
            players = [player.player_id for player in self.state.players.values() if player.in_game]
            self.state.turn.consecutive_priority_passes += 1
            self._event("PRIORITY_PASSED", player_id=player_id)
            if self.state.turn.consecutive_priority_passes == len(players):
                self.state.turn.consecutive_priority_passes = 0
                if self.state.stack:
                    self._resolve_top_after_priority_passes()
                elif self.state.turn.cleanup_repeat_pending:
                    self._cleanup_iteration(())
                else:
                    self._event("EMPTY_STACK_PRIORITY_PASSED")
                    self.state.turn.priority_holder_id = self.state.turn.active_player_id
            else:
                self.state.turn.priority_holder_id = players[
                    (players.index(player_id) + 1) % len(players)
                ]
            if _record:
                self._record_command("pass_priority", player_id=player_id)
        except Exception:
            self._rollback(before)
            raise

    def _remove_pending_action(self, action: Action) -> None:
        if action.action_id in self.state.pending_actions:
            self.state.pending_actions.remove(action.action_id)

    def counter(self, object_id: str, *, _record: bool = True) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        try:
            obj = self.state.objects[object_id]
            if obj.zone is not Zone.STACK or obj.object_kind is ObjectKind.MANA_ABILITY:
                raise IllegalAction("only a stack object can be countered")
            action = self._created_action(obj)
            event = self._event("STACK_OBJECT_COUNTERED", action, object_id=object_id)
            if obj.component_card_instance_ids:
                self.zones.move(object_id, Zone.GRAVEYARD, "COUNTERED", event)
            else:
                self.zones.move(object_id, Zone.NONE, "COUNTERED", event)
            self._remove_pending_action(action)
            self.check_state_based_actions()
            self.put_waiting_triggers_on_stack()
            if _record:
                self._record_command("counter", object_id=object_id)
        except Exception:
            self._rollback(before)
            raise

    def _revalidate_targets(self, action: Action) -> list[GameObject]:
        schema = dict(action.metadata.get("target_schema", {}))
        kind = str(schema.get("kind", "NONE"))
        legal: list[GameObject] = []
        for ref in action.targets:
            try:
                value = self.identity.resolve_reference(ref)
            except IllegalAction:
                continue
            if isinstance(value, GameObject) and self._target_matches(action.actor_id, value, kind):
                legal.append(value)
        return legal

    def resolve_top(self, *, _record: bool = True) -> None:
        del _record
        self._ensure_active()
        raise IllegalAction("the stack resolves only after all players pass priority")

    def _resolve_top_after_priority_passes(self) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        try:
            if not self.state.stack:
                raise IllegalAction("stack is empty")
            obj = self.state.objects[self.state.stack[-1]]
            action = self._created_action(obj)
            legal_targets = self._revalidate_targets(action)

            self._resolution_depth += 1
            try:
                if action.targets and not legal_targets:
                    self.counter(obj.object_id, _record=False)
                else:
                    if obj.object_kind in {ObjectKind.SPELL, ObjectKind.SPELL_COPY}:
                        face = int(action.metadata.get("face", 0))
                        abilities = obj.current_characteristics.get("abilities", [])
                        selected = next(
                            (
                                ability
                                for ability in abilities
                                if ability.get("ability_id") == action.metadata.get("ability_id")
                            ),
                            {"effect": {"kind": "NONE"}},
                        )
                        effect = dict(selected.get("effect", {}))
                    else:
                        selected = dict(obj.current_characteristics.get("ability", {}))
                        effect = dict(selected.get("effect", {}))
                        face = int(action.metadata.get("face", 0))
                    choices = dict(action.metadata.get("choices", {}))
                    if selected.get("optional") and not bool(
                        action.metadata.get("optional_selected", False)
                    ):
                        effect = {"kind": "NONE"}

                    aura_effect = effect.get("kind") == "ATTACH_AURA"
                    if not aura_effect:
                        self._apply_effect(obj, action, effect, legal_targets, choices)
                    resolved_event = self._event(
                        "STACK_OBJECT_RESOLVED", action, object_id=obj.object_id
                    )

                    if obj.object_kind in {
                        ObjectKind.ACTIVATED_ABILITY,
                        ObjectKind.TRIGGERED_ABILITY,
                        ObjectKind.ABILITY_COPY,
                    }:
                        self.zones.move(
                            obj.object_id, Zone.NONE, "ABILITY_RESOLVED", resolved_event
                        )
                    elif obj.object_kind is ObjectKind.SPELL_COPY:
                        self.zones.move(
                            obj.object_id,
                            Zone.GRAVEYARD,
                            "SPELL_COPY_RESOLVED",
                            resolved_event,
                        )
                    else:
                        card_types = self._types(obj)
                        if card_types.intersection(PERMANENT_TYPES):
                            permanent = self.zones.move(
                                obj.object_id,
                                Zone.BATTLEFIELD,
                                "RESOLVED",
                                resolved_event,
                                object_kind=ObjectKind.PERMANENT,
                                controller=obj.controller,
                                face=face,
                                explicit_characteristics={
                                    "selected_face_index": face,
                                    "cast_choices": choices,
                                    "cast_payment": action.payments,
                                    "modes": list(action.modes),
                                    "x_value": action.x_value,
                                },
                            )
                            if permanent is None:
                                raise IllegalAction("permanent spell did not create a permanent")
                            if aura_effect:
                                if len(legal_targets) != 1:
                                    raise IllegalAction("Aura resolution requires one legal target")
                                permanent.attached_to_ref = TargetRef(legal_targets[0].object_id)
                                self._event(
                                    "AURA_ATTACHED",
                                    action,
                                    aura_object_id=permanent.object_id,
                                    attached_to=legal_targets[0].object_id,
                                )
                            self._queue_etb(permanent)
                        else:
                            permission = selected.get("cast_permission", "NORMAL")
                            destination = (
                                Zone.EXILE
                                if permission in {"AFTERMATH", "FLASHBACK"}
                                else Zone.GRAVEYARD
                            )
                            self.zones.move(obj.object_id, destination, "RESOLVED", resolved_event)
                    self._remove_pending_action(action)
            finally:
                self._resolution_depth -= 1

            self.check_state_based_actions()
            if self.state.terminal.status == "ACTIVE":
                self.put_waiting_triggers_on_stack()
                self.state.turn.priority_holder_id = self.state.turn.active_player_id
                self.state.turn.consecutive_priority_passes = 0
        except Exception:
            self._rollback(before)
            raise

    def _apply_effect(
        self,
        source: GameObject | None,
        action: Action,
        effect: dict[str, Any],
        targets: list[GameObject],
        choices: dict[str, Any],
    ) -> None:
        kind = str(effect.get("kind", "NONE"))
        if kind == "NONE":
            return
        if kind == "SEQUENCE":
            for child in effect.get("effects", []):
                self._apply_effect(source, action, dict(child), targets, choices)
            return
        if kind == "ADD_MANA":
            add_mana(self.state.players[action.actor_id].mana_pool, effect.get("mana", {}))
            self._event("MANA_ADDED", action, mana=effect.get("mana", {}))
            return
        if kind == "ADD_CHOSEN_MANA":
            allowed = tuple(str(value) for value in effect.get("choices", ()))
            selected = str(choices.get("mana_color", ""))
            if selected not in allowed:
                raise IllegalAction("mana ability requires an explicit legal color choice")
            add_mana(self.state.players[action.actor_id].mana_pool, {selected: 1})
            self._event("MANA_ADDED", action, mana={selected: 1})
            return
        if kind == "DRAW":
            for _ in range(int(effect.get("count", 1))):
                self.draw_card(action.actor_id, action=action)
            return
        if kind == "SCRY":
            self.scry(
                action.actor_id,
                int(effect.get("count", 1)),
                bool(choices.get("scry_to_bottom", False)),
                action,
            )
            return
        if kind == "DAMAGE" and targets:
            self._damage_batch(source, [(targets[0], int(effect["amount"]))], action, combat=False)
            return
        if kind == "DESTROY" and targets:
            self.zones.move(
                targets[0].object_id,
                Zone.GRAVEYARD,
                "DESTROY",
                self._event("PERMANENT_DESTROYED", action),
            )
            return
        if kind == "EXILE_TARGET" and targets:
            self.zones.move(
                targets[0].object_id,
                Zone.EXILE,
                "EXILE",
                self._event("OBJECT_EXILED", action),
            )
            return
        if kind == "LIBRARY_SECOND" and targets:
            target = targets[0]
            if target.zone is Zone.STACK and target.object_kind in {
                ObjectKind.SPELL,
                ObjectKind.SPELL_COPY,
            }:
                self._remove_pending_action(self._created_action(target))
            destination = Zone.LIBRARY
            commander_choice_id: str | None = None
            if target.component_card_instance_ids:
                instance = self.state.card_instances[target.component_card_instance_ids[0]]
                if instance.commander_designation:
                    if "commander_to_command" not in choices:
                        raise IllegalAction(
                            "Commit requires an explicit commander replacement choice"
                        )
                    commander_to_command = bool(choices["commander_to_command"])
                    choice_event = self._event("COMMANDER_LIBRARY_REPLACEMENT_CHOICE", action)
                    choice = Choice(
                        self.identity.new_id("choice"),
                        instance.owner_id,
                        "COMMANDER_LIBRARY_REPLACEMENT",
                        "COMMAND" if commander_to_command else "LIBRARY",
                        choice_event.event_id,
                    )
                    self.state.choices.append(choice)
                    commander_choice_id = choice.choice_id
                    if commander_to_command:
                        destination = Zone.COMMAND
            moved = self.zones.move(
                target.object_id,
                destination,
                "COMMANDER_REPLACEMENT" if destination is Zone.COMMAND else "COMMIT",
                self._event(
                    "PUT_IN_LIBRARY" if destination is Zone.LIBRARY else "PUT_IN_COMMAND", action
                ),
                commander_choice_id=commander_choice_id,
            )
            if moved is not None and destination is Zone.LIBRARY:
                key = self.zones.zone_key(Zone.LIBRARY, moved.owner)
                zone = self.state.zones[key]
                zone.remove(moved.object_id)
                zone.insert(max(0, len(zone) - 1), moved.object_id)
            return
        if kind == "CREATE_SPELL_COPY" and targets:
            new_targets_data = choices.get("copy_targets")
            new_targets = (
                tuple(self._target_from_data(dict(item)) for item in new_targets_data)
                if isinstance(new_targets_data, list)
                else None
            )
            self.copy_spell(targets[0], action.actor_id, new_targets, action)
            return
        if kind == "CREATE_TOKEN_COPIES":
            for target in targets:
                self.copy_permanent_token(
                    target,
                    action.actor_id,
                    action,
                    haste=bool(effect.get("haste")),
                    delayed=str(effect.get("delayed", "")),
                )
            return
        if kind == "MEMORY":
            self._memory(action, choices)
            return
        if kind == "EXILE_OPPONENT_GRAVEYARDS":
            for obj in list(self.state.objects.values()):
                if not obj.retired and obj.zone is Zone.GRAVEYARD and obj.owner != action.actor_id:
                    self.zones.move(
                        obj.object_id,
                        Zone.EXILE,
                        "LANTERN_EXILE_GRAVEYARDS",
                        self._event("GRAVEYARD_CARD_EXILED", action),
                    )
            return
        if kind == "DAMAGE_EACH_OPPONENT":
            amount = int(effect.get("amount", 1))
            damage_source = self._rules_source(source)
            assignments: list[tuple[str, int]] = [
                (player_id, amount)
                for player_id, player in self.state.players.items()
                if player.in_game and player_id != action.actor_id
            ]
            self._damage_players(damage_source, assignments, action, combat=False)
            return
        if kind == "CREATE_TREASURES_FOR_DAMAGED_OPPONENTS":
            damaged = (
                list(source.current_characteristics.get("trigger_context", {}).get("opponents", []))
                if source
                else []
            )
            for _ in damaged:
                self.create_treasure(action.actor_id, action)
            return
        if kind == "EXILE_OBJECTS":
            for ref_data in effect.get("objects", []):
                ref = self._target_from_data(dict(ref_data))
                try:
                    resolved_ref = self.identity.resolve_reference(ref)
                except IllegalAction:
                    continue
                if isinstance(resolved_ref, GameObject):
                    self.zones.move(
                        resolved_ref.object_id,
                        Zone.EXILE,
                        "DELAYED_TRIGGER",
                        self._event("DELAYED_EXILE", action),
                    )
            return
        raise UnsupportedCapability(f"unsupported effect primitive: {kind}")

    def _rules_source(self, stack_object: GameObject | None) -> GameObject | None:
        if stack_object is None:
            return None
        source_id = stack_object.source_object_id
        if source_id is None:
            return stack_object
        return self.state.objects.get(source_id, stack_object)

    def _memory(self, action: Action, choices: dict[str, Any]) -> None:
        replacement_choices = dict(choices.get("commander_replacements", {}))
        for player_id in self.state.players:
            for zone in (Zone.HAND, Zone.GRAVEYARD):
                key = self.zones.zone_key(zone, player_id)
                for object_id in list(self.state.zones.get(key, [])):
                    obj = self.state.objects[object_id]
                    instance = (
                        self.state.card_instances[obj.component_card_instance_ids[0]]
                        if obj.component_card_instance_ids
                        else None
                    )
                    if instance is not None and instance.commander_designation:
                        if object_id not in replacement_choices:
                            raise IllegalAction(
                                "Memory requires an explicit commander replacement choice"
                            )
                        selected = bool(replacement_choices[object_id])
                        choice_event = self._event("COMMANDER_LIBRARY_REPLACEMENT_CHOICE", action)
                        choice = Choice(
                            self.identity.new_id("choice"),
                            player_id,
                            "COMMANDER_LIBRARY_REPLACEMENT",
                            "COMMAND" if selected else "LIBRARY",
                            choice_event.event_id,
                        )
                        self.state.choices.append(choice)
                        if selected:
                            self.zones.move(
                                object_id,
                                Zone.COMMAND,
                                "COMMANDER_REPLACEMENT",
                                choice_event,
                                commander_choice_id=choice.choice_id,
                            )
                            continue
                    self.zones.move(
                        object_id,
                        Zone.LIBRARY,
                        "MEMORY_SHUFFLE_IN",
                        self._event("MEMORY_CARD_TO_LIBRARY", action),
                    )
            self.shuffle_library(player_id, action)
        for player_id in self.state.players:
            for _ in range(7):
                self.draw_card(player_id, action=action)

    def draw_card(self, player_id: str, *, action: Action | None = None) -> GameObject | None:
        key = self.zones.zone_key(Zone.LIBRARY, player_id)
        library = self.state.zones.get(key, [])
        if not library:
            self.state.players[player_id].failed_draw_count += 1
            self._event("DRAW_FAILED", action, player_id=player_id)
            self.check_state_based_actions()
            return None
        top_id = library[-1]
        moved = self.zones.move(
            top_id,
            Zone.HAND,
            "DRAW",
            self._event("CARD_DRAWN", action, player_id=player_id),
        )
        return moved

    def scry(self, player_id: str, count: int, to_bottom: bool, action: Action) -> None:
        if count != 1:
            raise UnsupportedCapability("Phase A scry supports exactly one card")
        key = self.zones.zone_key(Zone.LIBRARY, player_id)
        library = self.state.zones.get(key, [])
        if not library:
            return
        top_id = library[-1]
        event = self._event("SCRY_CHOICE", action, player_id=player_id)
        choice = Choice(
            self.identity.new_id("choice"),
            player_id,
            "SCRY_1",
            "BOTTOM" if to_bottom else "TOP",
            event.event_id,
        )
        self.state.choices.append(choice)
        if to_bottom:
            library.pop()
            library.insert(0, top_id)

    def shuffle_library(self, player_id: str, action: Action | None = None) -> None:
        key = self.zones.zone_key(Zone.LIBRARY, player_id)
        library = self.state.zones.setdefault(key, [])
        for index in range(len(library) - 1, 0, -1):
            selected = self.identity.random_index(
                "shuffle", index + 1, f"shuffle:{player_id}:{index}"
            )
            library[index], library[selected] = library[selected], library[index]
        self._event("LIBRARY_SHUFFLED", action, player_id=player_id)

    def create_treasure(self, controller: str, action: Action) -> GameObject:
        event = self._event("TREASURE_CREATED", action, controller=controller)
        token = GameObject(
            self.identity.new_id("object"),
            ObjectKind.TOKEN_OBJECT,
            Zone.BATTLEFIELD,
            controller,
            controller,
            created_by_event_id=event.event_id,
            current_characteristics={
                "name": "Treasure",
                "card_types": ["Artifact"],
                "subtypes": ["Treasure"],
                "abilities": [
                    {
                        "ability_id": "token:treasure-mana",
                        "kind": "ACTIVATED",
                        "mana_ability": True,
                        "cost": {"tap": True, "sacrifice_source": True},
                        "effect": {
                            "kind": "ADD_CHOSEN_MANA",
                            "choices": ["W", "U", "B", "R", "G"],
                        },
                    }
                ],
            },
            permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"},
            identity_visible_to=set(self.state.players),
        )
        self.state.objects[token.object_id] = token
        self.zones.register(token)
        return token

    def _queue_trigger(
        self,
        source: GameObject,
        ability: dict[str, Any],
        context: dict[str, Any],
        choice_hints: dict[str, Any] | None = None,
    ) -> GameObject:
        controller = source.controller or source.owner
        if controller is None:
            raise IllegalAction("triggered ability source has neither controller nor owner")
        event = self._event(
            "ABILITY_TRIGGERED", source_object_id=source.object_id, ability_id=ability["ability_id"]
        )
        trigger = GameObject(
            self.identity.new_id("object"),
            ObjectKind.TRIGGERED_ABILITY,
            Zone.NONE,
            None,
            controller,
            source_object_id=source.object_id,
            created_by_event_id=event.event_id,
            current_characteristics={
                "ability": dict(ability),
                "trigger_context": dict(context),
                "choice_hints": dict(choice_hints or {}),
            },
            was_cast=False,
        )
        self.state.objects[trigger.object_id] = trigger
        self.state.waiting_triggers.append(trigger.object_id)
        return trigger

    def _queue_etb(self, permanent: GameObject) -> None:
        choices = dict(permanent.current_characteristics.get("cast_choices", {}))
        for ability in permanent.current_characteristics.get("abilities", []):
            if ability.get("kind") == "TRIGGERED" and ability.get("trigger") == "ETB":
                self._queue_trigger(permanent, dict(ability), {}, choices)

    def _scan_discard_triggers(self, player_id: str, action: Action, event: Event) -> None:
        for source in list(self.state.objects.values()):
            if (
                source.retired
                or source.zone is not Zone.BATTLEFIELD
                or source.controller != player_id
            ):
                continue
            for ability in source.current_characteristics.get("abilities", []):
                if (
                    ability.get("kind") == "TRIGGERED"
                    and ability.get("trigger") == "CONTROLLER_DISCARDS"
                ):
                    self._queue_trigger(
                        source,
                        dict(ability),
                        {"discard_event_id": event.event_id},
                        dict(action.metadata.get("choices", {})),
                    )

    def _choose_trigger_targets(
        self, trigger: GameObject, ability: dict[str, Any]
    ) -> tuple[TargetRef, ...]:
        schema = dict(
            ability.get("target_schema", {"kind": "NONE", "min": 0, "max": 0, "unique": True})
        )
        candidates = self._legal_candidates(trigger.controller or "", schema)
        minimum = int(schema.get("min", 0))
        if minimum and not candidates:
            trigger.retired = True
            trigger.ceased_to_exist = True
            self._event(
                "TRIGGER_REMOVED_NO_LEGAL_TARGETS", source_object_id=trigger.source_object_id
            )
            return ()
        hints = dict(trigger.current_characteristics.get("choice_hints", {}))
        target_hints = dict(hints.get("trigger_targets", {}))
        selected_raw = target_hints.get(ability["ability_id"])
        if selected_raw is None:
            if not candidates:
                return ()
            if len(candidates) != 1:
                raise IllegalAction("explicit trigger target choice is required")
            selected_ids = [candidates[0].object_id]
        elif isinstance(selected_raw, list):
            selected_ids = [str(value) for value in selected_raw]
        else:
            selected_ids = [str(selected_raw)]
        refs = tuple(TargetRef(object_id) for object_id in selected_ids)
        self._validate_targets(trigger.controller or "", refs, schema)
        choice_event = self._event(
            "TRIGGER_TARGETS_CHOSEN", source_object_id=trigger.source_object_id
        )
        choice = Choice(
            self.identity.new_id("choice"),
            trigger.controller or "",
            "TRIGGER_TARGETS",
            selected_ids,
            choice_event.event_id,
        )
        self.state.choices.append(choice)
        return refs

    def put_waiting_triggers_on_stack(self) -> None:
        if self._resolution_depth:
            return
        if not self.state.waiting_triggers:
            return
        player_order = list(self.state.players)
        active = self.state.turn.active_player_id
        ordered_players = [active] + [player for player in player_order if player != active]
        waiting = [self.state.objects[object_id] for object_id in self.state.waiting_triggers]
        self.state.waiting_triggers.clear()
        waiting.sort(key=lambda obj: ordered_players.index(obj.controller or active))
        for trigger in waiting:
            ability = dict(trigger.current_characteristics["ability"])
            targets = self._choose_trigger_targets(trigger, ability)
            if trigger.retired:
                continue
            hints = dict(trigger.current_characteristics.get("choice_hints", {}))
            optional_selected = True
            if ability.get("optional"):
                optional_choices = dict(hints.get("optional", {}))
                if ability["ability_id"] not in optional_choices:
                    raise IllegalAction("optional trigger requires an explicit recorded choice")
                optional_selected = bool(optional_choices[ability["ability_id"]])
                choice_event = self._event("OPTIONAL_TRIGGER_CHOICE")
                self.state.choices.append(
                    Choice(
                        self.identity.new_id("choice"),
                        trigger.controller or "",
                        "OPTIONAL_TRIGGER",
                        optional_selected,
                        choice_event.event_id,
                    )
                )
            action = Action(
                self.identity.new_id("action"),
                "TRIGGER",
                trigger.controller or "",
                trigger.source_object_id,
                targets,
                (),
                0,
                {},
                {
                    "ability_id": ability["ability_id"],
                    "target_schema": dict(ability.get("target_schema", {})),
                    "optional_selected": optional_selected,
                    "choices": hints,
                },
            )
            self.state.actions.append(action)
            event = self._event("TRIGGER_PUT_ON_STACK", action)
            trigger.zone = Zone.STACK
            trigger.created_by_event_id = event.event_id
            self.zones.register(trigger)
            self.state.pending_actions.append(action.action_id)
        if self.state.stack:
            self.state.turn.priority_holder_id = self.state.turn.active_player_id
            self.state.turn.consecutive_priority_passes = 0

    def copy_spell(
        self,
        original: GameObject,
        controller: str,
        new_targets: tuple[TargetRef, ...] | None,
        cause_action: Action,
    ) -> GameObject:
        if original.zone is not Zone.STACK or original.object_kind not in {
            ObjectKind.SPELL,
            ObjectKind.SPELL_COPY,
        }:
            raise IllegalAction("spell-copy source must be a spell on the stack")
        original_action = self._created_action(original)
        targets = new_targets if new_targets is not None else original_action.targets
        schema = dict(original_action.metadata.get("target_schema", {}))
        self._validate_targets(controller, targets, schema)
        choice_event = self._event("COPY_TARGET_DECISION", cause_action)
        choice = Choice(
            self.identity.new_id("choice"),
            controller,
            "COPY_TARGETS",
            [target.object_id for target in targets]
            if new_targets is not None
            else "RETAIN_ORIGINAL_TARGETS",
            choice_event.event_id,
        )
        self.state.choices.append(choice)
        action = Action(
            self.identity.new_id("action"),
            "COPY_SPELL",
            controller,
            original.object_id,
            targets,
            original_action.modes,
            original_action.x_value,
            {},
            {
                "ability_id": original_action.metadata.get("ability_id"),
                "face": original_action.metadata.get("face", 0),
                "target_schema": schema,
                "choices": dict(original_action.metadata.get("choices", {})),
            },
        )
        self.state.actions.append(action)
        event = self._event("SPELL_COPIED", action, copied_from=original.object_id)
        copy = GameObject(
            self.identity.new_id("object"),
            ObjectKind.SPELL_COPY,
            Zone.STACK,
            controller,
            controller,
            copied_from_object_id=original.object_id,
            copy_kind=CopyKind.SPELL_COPY,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=event.event_id,
            copy_target_choice_id=choice.choice_id,
            created_by_event_id=event.event_id,
            current_characteristics=deepcopy(original.current_characteristics),
            identity_visible_to=set(self.state.players),
            was_cast=False,
        )
        self.state.objects[copy.object_id] = copy
        self.zones.register(copy)
        self.state.pending_actions.append(action.action_id)
        return copy

    def copy_permanent_token(
        self,
        original: GameObject,
        controller: str,
        cause_action: Action,
        *,
        haste: bool,
        delayed: str,
    ) -> GameObject:
        if not self._is_permanent(original):
            raise IllegalAction("token-copy source must be a permanent")
        event = self._event("TOKEN_COPY_CREATED", cause_action, copied_from=original.object_id)
        characteristics = deepcopy(original.current_characteristics)
        if haste:
            keywords = set(characteristics.get("keywords", []))
            keywords.add("Haste")
            characteristics["keywords"] = sorted(keywords)
        token = GameObject(
            self.identity.new_id("object"),
            ObjectKind.TOKEN_OBJECT,
            Zone.BATTLEFIELD,
            controller,
            controller,
            copy_kind=CopyKind.TOKEN_COPY,
            copied_from_object_id=original.object_id,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=event.event_id,
            current_characteristics=characteristics,
            permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"},
            identity_visible_to=set(self.state.players),
        )
        self.state.objects[token.object_id] = token
        self.zones.register(token)
        if delayed == "EXILE_AT_NEXT_END_STEP":
            delayed_event = self._event("DELAYED_TRIGGER_CREATED", cause_action)
            trigger = GameObject(
                self.identity.new_id("object"),
                ObjectKind.TRIGGERED_ABILITY,
                Zone.NONE,
                None,
                controller,
                source_object_id=token.object_id,
                created_by_event_id=delayed_event.event_id,
                current_characteristics={
                    "ability": {
                        "ability_id": "twinflame:delayed-exile",
                        "kind": "TRIGGERED",
                        "trigger": "NEXT_END_STEP",
                        "target_schema": {"kind": "NONE", "min": 0, "max": 0, "unique": True},
                        "effect": {
                            "kind": "EXILE_OBJECTS",
                            "objects": [self._target_data(TargetRef(token.object_id))],
                        },
                    },
                    "trigger_context": {},
                    "choice_hints": {},
                },
                was_cast=False,
            )
            self.state.objects[trigger.object_id] = trigger
            self.state.delayed_triggers.append(trigger.object_id)
        return token

    def _damage_players(
        self,
        source: GameObject | None,
        assignments: list[tuple[str, int]],
        action: Action | None,
        *,
        combat: bool,
        choices: dict[str, Any] | None = None,
    ) -> None:
        choices = dict(choices or {})
        damaged_opponents: list[str] = []
        for player_id, amount in assignments:
            if amount < 0 or not self.state.players[player_id].in_game:
                raise IllegalAction("invalid damage assignment")
            self.state.players[player_id].life -= amount
            damaged_opponents.append(player_id)
            if source and source.component_card_instance_ids:
                instance = self.state.card_instances[source.component_card_instance_ids[0]]
                if instance.commander_designation and combat:
                    by_commander = self.state.commander_damage.setdefault(
                        instance.card_instance_id, {}
                    )
                    by_commander[player_id] = by_commander.get(player_id, 0) + amount
        event = self._event(
            "DAMAGE_DEALT",
            action,
            source_object_id=source.object_id if source else None,
            players=damaged_opponents,
            amounts={player: amount for player, amount in assignments},
            combat=combat,
        )
        if source is not None:
            self._scan_damage_triggers(source, damaged_opponents, event, choices)
        self.check_state_based_actions()
        self.put_waiting_triggers_on_stack()

    def _damage_batch(
        self,
        source: GameObject | None,
        assignments: list[tuple[GameObject, int]],
        action: Action | None,
        *,
        combat: bool,
    ) -> None:
        for obj, amount in assignments:
            if not self._is_permanent(obj) or amount < 0:
                raise IllegalAction("damage target is not a permanent")
            obj.marked_damage += amount
        self._event(
            "DAMAGE_DEALT_TO_OBJECTS",
            action,
            source_object_id=source.object_id if source else None,
            assignments={obj.object_id: amount for obj, amount in assignments},
            combat=combat,
        )
        self.check_state_based_actions()
        self.put_waiting_triggers_on_stack()

    def _scan_damage_triggers(
        self,
        source: GameObject,
        opponents: list[str],
        event: Event,
        choices: dict[str, Any],
    ) -> None:
        pirate_damage = "Pirate" in source.current_characteristics.get("subtypes", [])
        for permanent in list(self.state.objects.values()):
            if permanent.retired or permanent.zone is not Zone.BATTLEFIELD:
                continue
            for ability in permanent.current_characteristics.get("abilities", []):
                trigger = ability.get("trigger")
                if (
                    trigger == "PIRATE_DAMAGE_TO_OPPONENTS"
                    and pirate_damage
                    and permanent.controller == source.controller
                ):
                    self._queue_trigger(
                        permanent,
                        dict(ability),
                        {"opponents": list(opponents), "damage_event_id": event.event_id},
                        choices,
                    )
                if (
                    trigger == "ENCHANTED_CREATURE_DAMAGE_TO_OPPONENT"
                    and permanent.attached_to_ref is not None
                    and permanent.attached_to_ref.object_id == source.object_id
                ):
                    for opponent in opponents:
                        self._queue_trigger(
                            permanent,
                            dict(ability),
                            {"opponent": opponent, "damage_event_id": event.event_id},
                            choices,
                        )

    def deal_damage_to_player(
        self,
        source_id: str,
        player_id: str,
        amount: int,
        *,
        combat: bool = False,
        choices: dict[str, Any] | None = None,
        _record: bool = True,
    ) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        try:
            source = self.state.objects[source_id]
            if source.retired or source.zone is not Zone.BATTLEFIELD:
                raise IllegalAction("damage source is unavailable")
            self._damage_players(
                source, [(player_id, amount)], None, combat=combat, choices=choices
            )
            if _record:
                self._record_command(
                    "deal_damage_to_player",
                    source_id=source_id,
                    player_id=player_id,
                    amount=amount,
                    combat=combat,
                    choices=dict(choices or {}),
                )
        except Exception:
            self._rollback(before)
            raise

    def check_state_based_actions(self) -> None:
        if self._resolution_depth:
            return
        while True:
            changed = False
            for obj in list(self.state.objects.values()):
                if obj.retired or obj.ceased_to_exist:
                    continue
                if obj.pending_cease:
                    self.zones.cease(obj.object_id, self._event("SBA_SYNTHETIC_CEASE"))
                    changed = True
                    continue
                if self._is_permanent(obj) and "Creature" in self._types(obj):
                    toughness = obj.current_characteristics.get("toughness")
                    if isinstance(toughness, int) and (
                        toughness <= 0 or obj.marked_damage >= toughness
                    ):
                        self.zones.move(
                            obj.object_id,
                            Zone.GRAVEYARD,
                            "STATE_BASED_CREATURE_DEATH",
                            self._event("SBA_CREATURE_TO_GRAVEYARD"),
                        )
                        changed = True
                        continue
                if obj.attached_to_ref is not None:
                    try:
                        attached = self.identity.resolve_reference(obj.attached_to_ref)
                    except IllegalAction:
                        attached = None
                    if attached is None and "Aura" in obj.current_characteristics.get(
                        "subtypes", []
                    ):
                        self.zones.move(
                            obj.object_id,
                            Zone.GRAVEYARD,
                            "STATE_BASED_AURA",
                            self._event("SBA_AURA_TO_GRAVEYARD"),
                        )
                        changed = True
            for obj in list(self.state.objects.values()):
                if (
                    obj.retired
                    or obj.zone not in {Zone.GRAVEYARD, Zone.EXILE}
                    or not obj.component_card_instance_ids
                ):
                    continue
                instance = self.state.card_instances[obj.component_card_instance_ids[0]]
                if (
                    instance.commander_designation
                    and obj.object_id not in self.state.pending_commander_choices
                ):
                    self.state.pending_commander_choices.append(obj.object_id)
            for player in self.state.players.values():
                if player.in_game and (player.life <= 0 or player.failed_draw_count > 0):
                    player.in_game = False
                    player.loss_reasons.append(
                        "FAILED_DRAW" if player.failed_draw_count else "LIFE_TOTAL"
                    )
                    if player.player_id not in self.state.terminal.losers:
                        self.state.terminal.losers.append(player.player_id)
                    changed = True
            for damage in self.state.commander_damage.values():
                for player_id, amount in damage.items():
                    player = self.state.players[player_id]
                    if player.in_game and amount >= 21:
                        player.in_game = False
                        player.loss_reasons.append("COMMANDER_DAMAGE")
                        if player_id not in self.state.terminal.losers:
                            self.state.terminal.losers.append(player_id)
                        changed = True
            active = [player.player_id for player in self.state.players.values() if player.in_game]
            if len(active) <= 1 and self.state.terminal.status == "ACTIVE":
                terminal_event = self._event("GAME_TERMINATED")
                self.state.terminal.status = "TERMINAL"
                self.state.terminal.winners = active
                self.state.terminal.cause_event_ids.append(terminal_event.event_id)
                changed = True
            if not changed:
                break

    def commander_return_choice(
        self,
        player_id: str,
        object_id: str,
        return_to_command: bool,
        *,
        _record: bool = True,
    ) -> GameObject:
        before = self._begin_atomic()
        try:
            if object_id not in self.state.pending_commander_choices:
                raise IllegalAction("no commander return choice is pending")
            obj = self.state.objects[object_id]
            if obj.owner != player_id:
                raise IllegalAction("only the commander's owner makes this choice")
            event = self._event("COMMANDER_RETURN_CHOICE")
            choice = Choice(
                self.identity.new_id("choice"),
                player_id,
                "COMMANDER_RETURN",
                "RETURN" if return_to_command else "DECLINE",
                event.event_id,
            )
            self.state.choices.append(choice)
            self.state.pending_commander_choices.remove(object_id)
            if return_to_command:
                successor = self.zones.move(
                    object_id,
                    Zone.COMMAND,
                    "COMMANDER_SBA",
                    event,
                    commander_choice_id=choice.choice_id,
                )
                if successor is None:
                    raise IllegalAction("commander physical card is missing")
            else:
                successor = obj
            if _record:
                self._record_command(
                    "commander_return_choice",
                    player_id=player_id,
                    object_id=object_id,
                    return_to_command=return_to_command,
                )
            return successor
        except Exception:
            self._rollback(before)
            raise

    def _cleanup_iteration(self, discard_ids: tuple[str, ...]) -> None:
        self.state.turn.cleanup_iteration += 1
        active = self.state.players[self.state.turn.active_player_id]
        hand_key = self.zones.zone_key(Zone.HAND, active.player_id)
        hand = self.state.zones.get(hand_key, [])
        excess = max(0, len(hand) - active.maximum_hand_size)
        if len(discard_ids) != excess or any(object_id not in hand for object_id in discard_ids):
            raise IllegalAction("cleanup requires an explicit legal discard set")
        cleanup_action = Action(
            self.identity.new_id("action"),
            "CLEANUP_DISCARD",
            active.player_id,
            metadata={"discard_ids": list(discard_ids)},
        )
        self.state.actions.append(cleanup_action)
        for object_id in discard_ids:
            self._discard_card(active.player_id, object_id, cleanup_action)
        for obj in self.state.objects.values():
            if not obj.retired:
                obj.marked_damage = 0
                obj.current_characteristics.pop("until_end_of_turn", None)
                obj.current_characteristics.pop("attacking", None)
        self.check_state_based_actions()
        if self.state.waiting_triggers:
            self.put_waiting_triggers_on_stack()
            self.state.turn.cleanup_repeat_pending = True
            self._event("CLEANUP_PRIORITY_REQUIRED", cleanup_action)
        else:
            self.state.turn.cleanup_repeat_pending = False
            self._event("CLEANUP_COMPLETED", cleanup_action)

    def cleanup(self, discard_ids: tuple[str, ...] = (), *, _record: bool = True) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        try:
            self.state.turn.phase = "ENDING"
            self.state.turn.step = "CLEANUP"
            self._cleanup_iteration(discard_ids)
            if _record:
                self._record_command("cleanup", discard_ids=list(discard_ids))
        except Exception:
            self._rollback(before)
            raise

    def begin_step(
        self,
        step: str,
        choices: dict[str, Any] | None = None,
        *,
        _record: bool = True,
    ) -> None:
        self._ensure_active()
        before = self._begin_atomic()
        choices = dict(choices or {})
        try:
            self.state.turn.step = step
            if step in {"UNTAP", "UPKEEP", "DRAW"}:
                self.state.turn.phase = "BEGINNING"
            elif step in MAIN_PHASES:
                self.state.turn.phase = step
            elif step in {
                "BEGIN_COMBAT",
                "DECLARE_ATTACKERS",
                "DECLARE_BLOCKERS",
                "COMBAT_DAMAGE",
                "END_COMBAT",
            }:
                self.state.turn.phase = "COMBAT"
            else:
                self.state.turn.phase = "ENDING"
            self._event("STEP_BEGAN", step=step)
            if step == "UNTAP":
                for obj in self.state.objects.values():
                    if (
                        not obj.retired
                        and obj.zone is Zone.BATTLEFIELD
                        and obj.controller == self.state.turn.active_player_id
                    ):
                        if obj.permanent_status is not None:
                            obj.permanent_status["tap"] = "UNTAPPED"
                            obj.permanent_status["phase"] = "PHASED_IN"
                self.state.players[self.state.turn.active_player_id].land_plays_remaining = 1
            elif step == "DRAW":
                self.draw_card(self.state.turn.active_player_id)
            elif step == "END":
                while self.state.delayed_triggers:
                    self.state.waiting_triggers.append(self.state.delayed_triggers.pop(0))
                self.put_waiting_triggers_on_stack()
            elif step == "CLEANUP":
                discard_ids = tuple(str(value) for value in choices.get("discard_ids", []))
                self._cleanup_iteration(discard_ids)
            if step not in {"UNTAP", "CLEANUP"} and not self.state.stack:
                self.state.turn.priority_holder_id = self.state.turn.active_player_id
            if _record:
                self._record_command("begin_step", step=step, choices=choices)
        except Exception:
            self._rollback(before)
            raise

    def execute_replay_command(self, command: dict[str, Any]) -> None:
        operation = str(command["operation"])
        arguments = dict(command.get("arguments", {}))
        if operation == "cast":
            self.cast(
                str(arguments["actor"]),
                str(arguments["card_object_id"]),
                tuple(
                    self._target_from_data(dict(value)) for value in arguments.get("targets", [])
                ),
                int(arguments.get("face", 0)),
                int(arguments.get("x_value", 0)),
                arguments.get("mode"),
                dict(arguments.get("choices", {})),
                _record=False,
            )
        elif operation == "activate":
            self.activate(
                str(arguments["actor"]),
                str(arguments["source_id"]),
                str(arguments["ability_id"]),
                tuple(
                    self._target_from_data(dict(value)) for value in arguments.get("targets", [])
                ),
                dict(arguments.get("choices", {})),
                _record=False,
            )
        elif operation == "pass_priority":
            self.pass_priority(str(arguments["player_id"]), _record=False)
        elif operation == "resolve_top":
            self.resolve_top(_record=False)
        elif operation == "counter":
            self.counter(str(arguments["object_id"]), _record=False)
        elif operation == "deal_damage_to_player":
            self.deal_damage_to_player(
                str(arguments["source_id"]),
                str(arguments["player_id"]),
                int(arguments["amount"]),
                combat=bool(arguments.get("combat", False)),
                choices=dict(arguments.get("choices", {})),
                _record=False,
            )
        elif operation == "commander_return_choice":
            self.commander_return_choice(
                str(arguments["player_id"]),
                str(arguments["object_id"]),
                bool(arguments["return_to_command"]),
                _record=False,
            )
        elif operation == "cleanup":
            self.cleanup(tuple(arguments.get("discard_ids", [])), _record=False)
        elif operation == "begin_step":
            self.begin_step(
                str(arguments["step"]), dict(arguments.get("choices", {})), _record=False
            )
        else:
            raise IllegalAction(f"unknown replay command: {operation}")
