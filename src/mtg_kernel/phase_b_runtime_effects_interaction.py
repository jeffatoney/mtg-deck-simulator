"""Interaction, continuous-duration, and exile Phase B effects."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.models import Action, Choice, GameObject, ObjectKind, Zone
from mtg_kernel.phase_b_runtime_helpers import (
    _counter_to,
    _mark_eot_original,
    _spell_satisfies,
)
from mtg_kernel.resource_execution import execute_resource_payment_during_resolution
from mtg_kernel.resource_payment import PaymentStep, PaymentWindow
from mtg_kernel.resource_sources import solve_state_payment
from mtg_kernel.strategic_choices import (
    CounterPaymentRequest,
    CounterPaymentTarget,
    require_provider,
)


def _counter_payment_step(amount: int) -> PaymentStep:
    return PaymentStep(
        label="counter-payment",
        mana_cost=f"{{{amount}}}",
        window=PaymentWindow(0, "counter-payment-resolution"),
        context_tags=("COUNTER_PAYMENT",),
    )


def _resolve_counter_unless_pay(
    self: Any,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
    *,
    destination: Zone,
) -> None:
    if len(targets) != 1:
        raise IllegalAction("counter-unless-pay effect requires one target")
    target = targets[0]
    payer = target.controller or target.owner
    if payer is None or payer not in self.state.players:
        raise IllegalAction("counter-unless-pay target has no available controller")

    amount = action.x_value if effect.get("amount_from_x") else int(effect.get("amount", 0))
    if amount < 0:
        raise IllegalAction("counter payment amount cannot be negative")
    effect_kind = str(effect.get("kind", "COUNTER_UNLESS_PAY"))
    step = _counter_payment_step(amount)
    payment_result = solve_state_payment(self.state, payer, (step,))
    legal_outcomes = ("PAY", "DECLINE") if payment_result.feasible else ("DECLINE",)
    target_public = CounterPaymentTarget(
        identity=str(target.current_characteristics.get("name", "")),
        mana_value=int(target.current_characteristics.get("mana_value", 0)),
        card_types=tuple(
            str(value) for value in target.current_characteristics.get("card_types", ())
        ),
        effect_kinds=self._strategic_effect_kinds(target),
    )

    raw_decision = choices.get("counter_payment")
    evaluator_id = "explicit-rules-choice"
    evaluator_sha256 = "0" * 64
    diagnostics: dict[str, Any] = {}
    decision_source = "EXPLICIT_ACTION_CHOICE"
    if isinstance(raw_decision, dict):
        if raw_decision.get("player_id") != payer:
            raise IllegalAction(
                "counter payment decision must be anchored to the target controller"
            )
        pay = raw_decision.get("pay")
        if not isinstance(pay, bool):
            raise IllegalAction("counter payment decision must record a boolean pay value")
        outcome = "PAY" if pay else "DECLINE"
        if outcome not in legal_outcomes:
            raise IllegalAction("counter payment was selected but cannot be paid legally")
    else:
        # The injected Phase C provider controls the actor, not an arbitrary target
        # controller.  Never invent an unmodeled opponent's resolution choice.
        if payer != action.actor_id:
            raise UnsupportedCapability(
                "counter-unless-pay requires an explicit decision from an unmodeled opponent"
            )
        provider = require_provider(
            getattr(self, "strategic_choice_provider", None),
            "counter-unless-pay payment",
        )
        chooser = getattr(provider, "choose_counter_payment", None)
        if not callable(chooser):
            raise UnsupportedCapability(
                "the strategic provider has no authorized counter-payment selection policy"
            )
        request = CounterPaymentRequest(
            request_id=self.identity.new_id("strategic-request"),
            actor_id=payer,
            effect_kind=effect_kind,
            turn_number=int(self.state.turn.number),
            observation=self._strategic_observation(payer),
            target=target_public,
            payment_amount=amount,
            legal_outcomes=legal_outcomes,
            payment_result=payment_result,
        )
        selection = chooser(request)
        outcome = selection.outcome
        if outcome not in legal_outcomes:
            raise IllegalAction(
                "strategic provider selected an unavailable counter-payment outcome"
            )
        evaluator_id = selection.evaluator_id
        evaluator_sha256 = selection.evaluator_sha256
        diagnostics = dict(selection.diagnostics)
        decision_source = "STRATEGIC_PROVIDER"

    payment: dict[str, int] = {}
    if outcome == "PAY":
        payment = execute_resource_payment_during_resolution(
            self,
            payer,
            step,
            payment_result,
        )

    decision_event = self._event(
        "COUNTER_PAYMENT_DECISION",
        action,
        payer=payer,
        pay=outcome == "PAY",
        outcome=outcome,
        amount=amount,
        payment=payment,
        target_object_id=target.object_id,
    )
    self.state.choices.append(
        Choice(
            self.identity.new_id("choice"),
            payer,
            "COUNTER_UNLESS_PAY",
            {
                "schema_version": "counter-payment-choice-v3",
                "choice_kind": "COUNTER_PAYMENT",
                "effect_kind": effect_kind,
                "decision_owner": payer,
                "target_identity": target_public.identity,
                "target_mana_value": target_public.mana_value,
                "target_card_types": list(target_public.card_types),
                "target_effect_kinds": list(target_public.effect_kinds),
                "amount": amount,
                "legal_modeled_alternatives": list(legal_outcomes),
                "pay_legally_available": payment_result.feasible,
                "resource_payment": asdict(payment_result),
                "outcome": outcome,
                "pay": outcome == "PAY",
                "payment": payment,
                "reason_code": str(
                    diagnostics.get("reason_code", f"SELECTED_COUNTER_PAYMENT_{outcome}")
                ),
                "evaluator_id": evaluator_id,
                "evaluator_sha256": evaluator_sha256,
                "diagnostics": diagnostics,
                "decision_source": decision_source,
                "chosen_at": "RESOLUTION",
            },
            decision_event.event_id,
        )
    )
    if outcome == "DECLINE":
        _counter_to(self, target, action, destination)


def apply_effect_interaction(
    self: Any,
    source: GameObject | None,
    action: Action,
    effect: dict[str, Any],
    targets: list[GameObject],
    choices: dict[str, Any],
) -> bool:
    kind = str(effect.get("kind", "NONE"))

    if kind == "DAMAGE_ANY_TARGET":
        if len(targets) != 1:
            raise IllegalAction("damage-any-target effect requires one target")
        target = targets[0]
        amount = int(effect.get("amount", 1))
        damage_source = self._rules_source(source)
        if (
            target.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
            and target.current_characteristics.get("target_kind") == "PLAYER"
        ):
            player_id = str(target.current_characteristics.get("player_id", ""))
            if player_id not in self.state.players or not self.state.players[player_id].in_game:
                raise IllegalAction("damage player target is unavailable")
            self._damage_players(damage_source, [(player_id, amount)], action, combat=False)
        else:
            self._damage_batch(damage_source, [(target, amount)], action, combat=False)
        return True

    if kind == "GRANT_HASTE":
        if len(targets) != 1:
            raise IllegalAction("haste effect requires one target")
        target = targets[0]
        _mark_eot_original(target)
        keywords = set(str(value) for value in target.current_characteristics.get("keywords", ()))
        keywords.add("Haste")
        target.current_characteristics["keywords"] = sorted(keywords)
        self._event("KEYWORD_GRANTED", action, object_id=target.object_id, keyword="Haste")
        return True

    if kind == "MODIFY_POWER_TOUGHNESS":
        if len(targets) != 1:
            raise IllegalAction("power/toughness effect requires one target")
        target = targets[0]
        power = target.current_characteristics.get("power")
        toughness = target.current_characteristics.get("toughness")
        if not isinstance(power, int) or not isinstance(toughness, int):
            raise IllegalAction("power/toughness modification requires numeric characteristics")
        _mark_eot_original(target)
        target.current_characteristics["power"] = power + int(effect.get("power", 0))
        target.current_characteristics["toughness"] = toughness + int(effect.get("toughness", 0))
        self._event("POWER_TOUGHNESS_MODIFIED", action, object_id=target.object_id)
        return True

    if kind == "SWITCH_POWER_TOUGHNESS":
        for target in targets:
            power = target.current_characteristics.get("power")
            toughness = target.current_characteristics.get("toughness")
            if not isinstance(power, int) or not isinstance(toughness, int):
                raise IllegalAction("switch effect requires numeric power and toughness")
            _mark_eot_original(target)
            target.current_characteristics["power"] = toughness
            target.current_characteristics["toughness"] = power
        self._event("POWER_TOUGHNESS_SWITCHED", action, count=len(targets))
        return True

    if kind == "PHASE_OUT":
        if len(targets) != 1:
            raise IllegalAction("phase-out effect requires one target")
        target = targets[0]
        if target.permanent_status is None:
            raise IllegalAction("phase-out target has no permanent status")
        affected = [target]
        affected_ids = {target.object_id}
        for permanent in affected:
            for candidate in self.state.objects.values():
                if (
                    candidate.retired
                    or candidate.ceased_to_exist
                    or candidate.zone is not Zone.BATTLEFIELD
                    or candidate.object_id in affected_ids
                    or candidate.attached_to_ref is None
                    or candidate.attached_to_ref.object_id != permanent.object_id
                ):
                    continue
                affected.append(candidate)
                affected_ids.add(candidate.object_id)
        for permanent in affected:
            if permanent.permanent_status is None:
                raise IllegalAction("attached phase-out object has no permanent status")
            indirect = permanent.object_id != target.object_id
            permanent.permanent_status["phase"] = "PHASED_OUT"
            if indirect:
                permanent.current_characteristics["phased_out_with"] = target.object_id
            self._event(
                "PERMANENT_PHASED_OUT",
                action,
                object_id=permanent.object_id,
                indirect=indirect,
                phased_out_with=target.object_id if indirect else None,
            )
        return True

    if kind in {"COUNTER", "COUNTER_IF"}:
        if len(targets) != 1:
            raise IllegalAction("counter effect requires one target")
        target = targets[0]
        if kind == "COUNTER" or _spell_satisfies(target, dict(effect.get("predicate", {}))):
            _counter_to(self, target, action, Zone.GRAVEYARD)
        return True

    if kind == "COUNTER_UNLESS_PAY":
        _resolve_counter_unless_pay(
            self,
            action,
            effect,
            targets,
            choices,
            destination=Zone.GRAVEYARD,
        )
        return True

    if kind == "COUNTER_UNLESS_PAY_EXILE":
        _resolve_counter_unless_pay(
            self,
            action,
            effect,
            targets,
            choices,
            destination=Zone.EXILE,
        )
        return True

    if kind == "COUNTER_TARGETING_CONTROLLER":
        if len(targets) != 1:
            raise IllegalAction("Stormtamer counter requires one stack target")
        target = targets[0]
        created = self._created_action(target)
        protected = action.actor_id
        targets_controller = any(
            ref.object_id in self.state.objects
            and (
                self.state.objects[ref.object_id].controller == protected
                or self.state.objects[ref.object_id].owner == protected
            )
            for ref in created.targets
        )
        if not targets_controller:
            raise IllegalAction("target spell or ability does not target the protected player")
        _counter_to(self, target, action, Zone.GRAVEYARD)
        return True

    if kind == "EXILE_THEN_CONTROLLER_DRAWS":
        if len(targets) != 1:
            raise IllegalAction("exile-and-draw requires one target")
        controller = targets[0].controller or targets[0].owner
        self.zones.move(
            targets[0].object_id,
            Zone.EXILE,
            kind,
            self._event("OBJECT_EXILED", action, object_id=targets[0].object_id),
        )
        if controller is not None:
            self.draw_card(controller, action=action)
        return True

    if kind == "EXILE_CREATURES_CREATE_BOARS":
        for target in targets:
            controller = target.controller or target.owner
            self.zones.move(
                target.object_id,
                Zone.EXILE,
                kind,
                self._event("OBJECT_EXILED", action, object_id=target.object_id),
            )
            if controller is None:
                continue
            event = self._event("TOKEN_CREATED", action, controller=controller, token_name="Boar")
            token = GameObject(
                self.identity.new_id("object"),
                ObjectKind.TOKEN_OBJECT,
                Zone.BATTLEFIELD,
                controller,
                controller,
                created_by_event_id=event.event_id,
                current_characteristics={
                    "name": "Boar",
                    "card_types": ["Creature"],
                    "subtypes": ["Boar"],
                    "colors": ["G"],
                    "keywords": [],
                    "abilities": [],
                    "power": 2,
                    "toughness": 2,
                },
                permanent_status={
                    "tap": "UNTAPPED",
                    "face": "FACE_UP",
                    "phase": "PHASED_IN",
                },
                identity_visible_to=set(self.state.players),
            )
            self.state.objects[token.object_id] = token
            self.zones.register(token)
        return True

    if kind == "EXILE_ALL_GRAVEYARDS":
        for obj in list(self.state.objects.values()):
            if not obj.retired and obj.zone is Zone.GRAVEYARD:
                self.zones.move(
                    obj.object_id,
                    Zone.EXILE,
                    kind,
                    self._event("GRAVEYARD_CARD_EXILED", action, object_id=obj.object_id),
                )
        return True

    return False
