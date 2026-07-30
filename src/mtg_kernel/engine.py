"""Single legality, payment, stack, priority, resolution, SBA, and trigger path."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mtg_kernel.errors import IllegalAction
from mtg_kernel.identity import IdentityService
from mtg_kernel.models import (
    Action,
    Choice,
    CopyKind,
    Event,
    GameObject,
    GameState,
    ObjectKind,
    TargetRef,
    Zone,
)
from mtg_kernel.zones import ZoneService


class GameExecutor:
    """Deck-scoped executor; effect behavior is data-driven and never selected by card name."""

    def __init__(self, state: GameState, seed: str = "phase-a") -> None:
        self.state = state
        self.identity = IdentityService(state, seed)
        self.zones = ZoneService(state, self.identity)

    def _event(self, kind: str, action: Action | None = None, **payload: Any) -> Event:
        event = Event(
            self.identity.new_id("event"), kind, action.action_id if action else None, payload
        )
        self.state.events.append(event)
        return event

    def _ensure_active(self) -> None:
        if self.state.terminal.status != "ACTIVE":
            raise IllegalAction("game is terminal")

    def cast(
        self,
        actor: str,
        card_object_id: str,
        targets: tuple[TargetRef, ...] = (),
        face: int = 0,
        x_value: int = 0,
    ) -> GameObject:
        self._ensure_active()
        before = deepcopy(self.state)
        try:
            card = self.state.objects[card_object_id]
            if card.retired or card.zone not in {Zone.HAND, Zone.COMMAND, Zone.GRAVEYARD}:
                raise IllegalAction("card is not castable from its current zone")
            characteristics = card.current_characteristics
            faces = characteristics.get("faces", [])
            selected = faces[face] if faces else characteristics
            permission = selected.get("cast_permission", "NORMAL")
            if card.zone is Zone.GRAVEYARD and permission not in {"AFTERMATH", "FLASHBACK"}:
                raise IllegalAction("no graveyard casting permission")
            target_schema = selected.get("target_schema", [])
            if len(targets) != len(target_schema):
                raise IllegalAction("target count does not match the selected face")
            for ref in targets:
                self.identity.resolve_reference(ref)
            action = Action(
                self.identity.new_id("action"),
                "CAST",
                actor,
                card_object_id,
                targets,
                x_value=x_value,
                metadata={"face": face, "cost": selected.get("mana_cost", "")},
            )
            # Payment is deliberately explicit and atomic for the deck-scoped mana model.
            generic_cost = int(selected.get("generic_cost", 0)) + (
                2 * self.state.commander_cast_counts.get(card.component_card_instance_ids[0], 0)
                if card.zone is Zone.COMMAND
                else 0
            )
            pool = self.state.players[actor].mana_pool
            if pool.get("GENERIC", 0) < generic_cost:
                raise IllegalAction("insufficient recorded mana")
            pool["GENERIC"] = pool.get("GENERIC", 0) - generic_cost
            self.state.actions.append(action)
            event = self._event(
                "SPELL_CAST",
                action,
                payment={"GENERIC": generic_cost},
                targets=[r.object_id for r in targets],
            )
            old_zone = card.zone
            spell = self.zones.move(card.object_id, Zone.STACK, "CAST", event)
            if spell is None:
                raise IllegalAction("a physical card is required to cast")
            spell.object_kind = ObjectKind.SPELL
            spell.controller = actor
            spell.was_cast = True
            spell.current_characteristics["selected_face"] = selected
            spell.current_characteristics["targets"] = list(targets)
            if old_zone is Zone.COMMAND:
                instance_id = spell.component_card_instance_ids[0]
                self.state.commander_cast_counts[instance_id] = (
                    self.state.commander_cast_counts.get(instance_id, 0) + 1
                )
            self.state.turn.priority_holder_id = actor
            self.state.turn.consecutive_priority_passes = 0
            return spell
        except Exception:
            self.state.__dict__.clear()
            self.state.__dict__.update(before.__dict__)
            raise

    def activate(
        self,
        actor: str,
        source_id: str,
        ability: dict[str, Any],
        targets: tuple[TargetRef, ...] = (),
    ) -> GameObject:
        self._ensure_active()
        source = self.state.objects[source_id]
        if source.retired or source.controller != actor:
            raise IllegalAction("activated ability source is unavailable")
        if len(targets) != len(ability.get("target_schema", [])):
            raise IllegalAction("invalid activated ability targets")
        for target in targets:
            self.identity.resolve_reference(target)
        action = Action(self.identity.new_id("action"), "ACTIVATE", actor, source_id, targets)
        self.state.actions.append(action)
        event = self._event("ABILITY_ACTIVATED", action)
        ability_object = GameObject(
            self.identity.new_id("object"),
            ObjectKind.ACTIVATED_ABILITY,
            Zone.STACK,
            None,
            actor,
            source_object_id=source_id,
            created_by_event_id=event.event_id,
            current_characteristics={"effect": ability.get("effect", {}), "targets": list(targets)},
            copy_kind=CopyKind.NONE,
            was_cast=False,
        )
        self.state.objects[ability_object.object_id] = ability_object
        self.zones.register(ability_object)
        self.state.turn.priority_holder_id = actor
        return ability_object

    def pass_priority(self, player_id: str) -> None:
        self._ensure_active()
        if self.state.turn.priority_holder_id != player_id:
            raise IllegalAction("player does not have priority")
        players = [p for p in self.state.players.values() if p.in_game]
        self.state.turn.consecutive_priority_passes += 1
        self._event("PRIORITY_PASSED", player_id=player_id)
        if self.state.turn.consecutive_priority_passes == len(players):
            self.state.turn.consecutive_priority_passes = 0
            if self.state.stack:
                self.resolve_top()
            else:
                self._event("EMPTY_STACK_ADVANCE")
        else:
            ids = [p.player_id for p in players]
            self.state.turn.priority_holder_id = ids[(ids.index(player_id) + 1) % len(ids)]

    def counter(self, object_id: str) -> None:
        spell = self.state.objects[object_id]
        if (
            spell.object_kind not in {ObjectKind.SPELL, ObjectKind.SPELL_COPY}
            or spell.zone is not Zone.STACK
        ):
            raise IllegalAction("only a stack spell can be countered")
        event = self._event("SPELL_COUNTERED")
        destination = Zone.NONE if spell.copy_kind is CopyKind.SPELL_COPY else Zone.GRAVEYARD
        self.zones.move(object_id, destination, "COUNTERED", event)
        self.check_state_based_actions()
        self.put_waiting_triggers_on_stack()

    def resolve_top(self) -> None:
        if not self.state.stack:
            raise IllegalAction("stack is empty")
        obj = self.state.objects[self.state.stack[-1]]
        targets: list[TargetRef] = obj.current_characteristics.get("targets", [])
        legal: list[GameObject] = []
        for ref in targets:
            try:
                resolved = self.identity.resolve_reference(ref)
                if isinstance(resolved, GameObject):
                    legal.append(resolved)
            except IllegalAction:
                continue
        if targets and not legal:
            self.counter(obj.object_id)
            return
        selected = obj.current_characteristics.get("selected_face", obj.current_characteristics)
        effect = selected.get("effect", {})
        self._apply_effect(obj, effect, legal)
        event = self._event("OBJECT_RESOLVED")
        if obj.object_kind in {
            ObjectKind.ACTIVATED_ABILITY,
            ObjectKind.TRIGGERED_ABILITY,
            ObjectKind.ABILITY_COPY,
        }:
            self.zones.move(obj.object_id, Zone.NONE, "ABILITY_RESOLVED", event)
        elif obj.copy_kind is CopyKind.SPELL_COPY:
            self.zones.move(obj.object_id, Zone.NONE, "SPELL_COPY_RESOLVED", event)
        elif "Permanent" in selected.get("resolution", "") or any(
            t in selected.get("card_types", []) for t in ("Artifact", "Creature", "Enchantment")
        ):
            permanent = self.zones.move(obj.object_id, Zone.BATTLEFIELD, "RESOLVED", event)
            if permanent:
                self._queue_etb(permanent)
        else:
            destination = (
                Zone.EXILE
                if selected.get("cast_permission") in {"AFTERMATH", "FLASHBACK"}
                else Zone.GRAVEYARD
            )
            self.zones.move(obj.object_id, destination, "RESOLVED", event)
        self.check_state_based_actions()
        self.put_waiting_triggers_on_stack()
        self.state.turn.priority_holder_id = self.state.turn.active_player_id

    def _apply_effect(
        self, source: GameObject, effect: dict[str, Any], targets: list[GameObject]
    ) -> None:
        kind = effect.get("kind", "NONE")
        if kind == "DAMAGE" and targets:
            targets[0].marked_damage += int(effect["amount"])
        elif kind == "DESTROY" and targets:
            self.zones.move(
                targets[0].object_id, Zone.GRAVEYARD, "DESTROY", self._event("DESTROYED")
            )
        elif kind == "LIBRARY_SECOND" and targets:
            target = targets[0]
            moved = self.zones.move(
                target.object_id, Zone.LIBRARY, "COMMIT", self._event("PUT_IN_LIBRARY")
            )
            if moved:
                key = self.zones.zone_key(Zone.LIBRARY, moved.owner)
                zone = self.state.zones[key]
                zone.remove(moved.object_id)
                zone.insert(max(0, len(zone) - 1), moved.object_id)
        elif kind == "CREATE_SPELL_COPY" and targets:
            self.copy_spell(targets[0], source.controller or "")
        elif kind == "CREATE_TOKEN_COPY" and targets:
            self.copy_permanent_token(targets[0], source.controller or "")
        elif kind == "EXILE_TARGET" and targets:
            self.zones.move(targets[0].object_id, Zone.EXILE, "EXILE", self._event("EXILED"))

    def _queue_etb(self, permanent: GameObject) -> None:
        selected = permanent.current_characteristics.get(
            "selected_face", permanent.current_characteristics
        )
        for ability in selected.get("abilities", []):
            if ability.get("trigger") == "ETB":
                schema = ability.get("target_schema", [])
                candidates = [
                    o
                    for o in self.state.objects.values()
                    if not o.retired
                    and (
                        (schema == ["GRAVEYARD_CARD"] and o.zone is Zone.GRAVEYARD)
                        or (
                            schema == ["INSTANT_OR_SORCERY_SPELL"]
                            and o.zone is Zone.STACK
                            and o.object_kind in {ObjectKind.SPELL, ObjectKind.SPELL_COPY}
                        )
                    )
                ]
                if ability.get("target_schema") and not candidates:
                    continue
                refs = [TargetRef(candidates[0].object_id)] if ability.get("target_schema") else []
                trigger = GameObject(
                    self.identity.new_id("object"),
                    ObjectKind.TRIGGERED_ABILITY,
                    Zone.NONE,
                    None,
                    permanent.controller,
                    source_object_id=permanent.object_id,
                    current_characteristics={"effect": ability.get("effect", {}), "targets": refs},
                    was_cast=False,
                )
                self.state.objects[trigger.object_id] = trigger
                self.state.waiting_triggers.append(trigger.object_id)

    def put_waiting_triggers_on_stack(self) -> None:
        while self.state.waiting_triggers:
            object_id = self.state.waiting_triggers.pop(0)
            trigger = self.state.objects[object_id]
            trigger.zone = Zone.STACK
            self.zones.register(trigger)
            self._event("TRIGGER_PUT_ON_STACK", source_object_id=trigger.source_object_id)
        if self.state.stack:
            self.state.turn.priority_holder_id = self.state.turn.active_player_id

    def copy_spell(self, original: GameObject, controller: str) -> GameObject:
        if original.zone is not Zone.STACK:
            raise IllegalAction("spell copy source must be on stack")
        copy = GameObject(
            self.identity.new_id("object"),
            ObjectKind.SPELL_COPY,
            Zone.STACK,
            controller,
            controller,
            copied_from_object_id=original.object_id,
            copy_kind=CopyKind.SPELL_COPY,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=self._event("SPELL_COPIED").event_id,
            current_characteristics=deepcopy(original.current_characteristics),
            was_cast=False,
        )
        self.state.objects[copy.object_id] = copy
        self.zones.register(copy)
        return copy

    def copy_permanent_token(self, original: GameObject, controller: str) -> GameObject:
        if original.zone is not Zone.BATTLEFIELD:
            raise IllegalAction("token copy source must be a permanent")
        token = GameObject(
            self.identity.new_id("object"),
            ObjectKind.PERMANENT,
            Zone.BATTLEFIELD,
            controller,
            controller,
            copy_kind=CopyKind.TOKEN_COPY,
            copied_from_object_id=original.object_id,
            copiable_values_snapshot_id=self.identity.new_id("copy-snapshot"),
            copy_creation_event_id=self._event("TOKEN_COPY_CREATED").event_id,
            current_characteristics=deepcopy(original.current_characteristics),
            permanent_status={"tap": "UNTAPPED", "face": "FACE_UP", "phase": "PHASED_IN"},
        )
        self.state.objects[token.object_id] = token
        self.zones.register(token)
        self.state.delayed_triggers.append(token.object_id)
        return token

    def check_state_based_actions(self) -> None:
        self._ensure_active()
        # Commander choices occur only after the real graveyard/exile arrival.
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
            if player.life <= 0 and player.in_game:
                player.in_game = False
                player.loss_reasons.append("LIFE_TOTAL")
                self.state.terminal.losers.append(player.player_id)
        active = [p.player_id for p in self.state.players.values() if p.in_game]
        if len(active) <= 1:
            self.state.terminal.status = "TERMINAL"
            self.state.terminal.winners = active

    def commander_return_choice(
        self, player_id: str, object_id: str, return_to_command: bool
    ) -> GameObject:
        if object_id not in self.state.pending_commander_choices:
            raise IllegalAction("no commander return choice is pending")
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
        if not return_to_command:
            return self.state.objects[object_id]
        successor = self.zones.move(object_id, Zone.COMMAND, "COMMANDER_SBA", event)
        if successor is None:
            raise IllegalAction("commander physical card is missing")
        return successor

    def cleanup(self) -> None:
        self._ensure_active()
        while True:
            self.state.turn.cleanup_iteration += 1
            active = self.state.players[self.state.turn.active_player_id]
            hand_key = self.zones.zone_key(Zone.HAND, active.player_id)
            hand = self.state.zones.get(hand_key, [])
            excess = max(0, len(hand) - active.maximum_hand_size)
            for object_id in list(hand[:excess]):
                self.zones.move(
                    object_id, Zone.GRAVEYARD, "CLEANUP_DISCARD", self._event("CARD_DISCARDED")
                )
                self._event("DISCARD_TRIGGERED")
            for obj in self.state.objects.values():
                if not obj.retired:
                    obj.marked_damage = 0
                    obj.current_characteristics.pop("until_end_of_turn", None)
            needs_priority = excess > 0 and any(
                e.kind == "DISCARD_TRIGGERED" for e in self.state.events[-excess * 2 :]
            )
            self._event("CLEANUP_COMPLETED", iteration=self.state.turn.cleanup_iteration)
            if needs_priority:
                self.state.turn.priority_holder_id = self.state.turn.active_player_id
                # A second cleanup is required after players would receive priority.
                continue
            break
