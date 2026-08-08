"""Policy decisions for mandatory triggered-ability target choices."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from mtg_kernel.errors import UnsupportedCapability
from mtg_kernel.strategic_choices import CardSelection, CardSelectionRequest
from mtg_policy.choices import PolicyStrategicChoiceProvider as _BaseProvider
from mtg_policy.config import PolicyBundle
from mtg_policy.evaluation import ContextualEvaluator, score_to_microunits

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor


class PolicyStrategicChoiceProvider(_BaseProvider):
    """Extend the frozen provider to exact-deck trigger and actor-owned choices."""

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        if request.purpose == "PRISMARI_DISCARD":
            delegated = super().choose_cards(replace(request, purpose="DISCARD"))
            diagnostics = dict(delegated.diagnostics)
            diagnostics.update(
                {
                    "purpose": request.purpose,
                    "delegated_purpose": "DISCARD",
                    "actor_id": request.actor_id,
                }
            )
            return CardSelection(
                delegated.selected_handles,
                delegated.evaluator_id,
                delegated.evaluator_sha256,
                diagnostics,
            )

        if not request.purpose.startswith("TRIGGER_TARGET:"):
            return super().choose_cards(request)
        if request.minimum != 1 or request.maximum != 1 or not request.candidates:
            raise UnsupportedCapability(
                "mandatory trigger target policy requires exactly one legal candidate selection"
            )

        effect_kind = request.purpose.split(":", 1)[1]
        evaluations = {
            card.handle: (
                0.0
                if "PLAYER" in card.card_types
                else self.evaluator.evaluate_pile((card,), request.observation).score
            )
            for card in request.candidates
        }

        if effect_kind == "DAMAGE_ANY_TARGET":
            life_raw = request.observation.get("life", {})
            life = life_raw if isinstance(life_raw, Mapping) else {}
            opponents = [
                card
                for card in request.candidates
                if "PLAYER" in card.card_types and card.identity != f"Player {request.actor_id}"
            ]
            if opponents:

                def opponent_key(card: Any) -> tuple[int, str, str]:
                    player_id = card.identity.removeprefix("Player ")
                    raw = life.get(player_id, 10**9)
                    value = raw if isinstance(raw, int) and not isinstance(raw, bool) else 10**9
                    return value, player_id, card.handle

                chosen = min(opponents, key=opponent_key)
                strategy = "LOWEST_LIFE_OPPONENT"
            else:
                chosen = min(
                    request.candidates,
                    key=lambda card: (evaluations[card.handle], card.identity, card.handle),
                )
                strategy = "LOWEST_VALUE_LEGAL_TARGET"
        elif effect_kind in {"BOUNCE_TARGET", "RETURN_CONTROLLED_LAND", "EXILE_TARGET"}:
            chosen = min(
                request.candidates,
                key=lambda card: (evaluations[card.handle], card.identity, card.handle),
            )
            strategy = "LOWEST_CONTEXTUAL_VALUE"
        elif effect_kind == "CREATE_SPELL_COPY":
            combo_spells = {"Twinflame", "Electroduplicate"}
            chosen = max(
                request.candidates,
                key=lambda card: (
                    card.identity in combo_spells,
                    evaluations[card.handle],
                    card.identity,
                    card.handle,
                ),
            )
            strategy = "COMBO_THEN_HIGHEST_CONTEXTUAL_VALUE"
        else:
            raise UnsupportedCapability(
                f"mandatory trigger target policy is unsupported for effect: {effect_kind}"
            )

        return CardSelection(
            (chosen.handle,),
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "purpose": request.purpose,
                "strategy": strategy,
                "candidate_evaluation_microunits": {
                    handle: score_to_microunits(value) for handle, value in evaluations.items()
                },
            },
        )


def bind_policy_strategic_choices(
    executor: GameExecutor,
    bundle: PolicyBundle,
    evaluator: ContextualEvaluator,
) -> PolicyStrategicChoiceProvider:
    """Bind the frozen policy plus exact-deck extensions to one executor."""

    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    executor.bind_strategic_choice_provider(provider)
    return provider


__all__ = ["PolicyStrategicChoiceProvider", "bind_policy_strategic_choices"]
