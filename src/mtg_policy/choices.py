"""Policy-layer providers for rules-defined strategic choices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mtg_kernel.errors import UnsupportedCapability

from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy.config import PolicyBundle
from mtg_policy.evaluation import ContextualEvaluator, score_to_microunits

if TYPE_CHECKING:
    from mtg_kernel.engine import GameExecutor


class PolicyStrategicChoiceProvider:
    """Make deterministic choices from a frozen policy and evaluator snapshot."""

    def __init__(self, bundle: PolicyBundle, evaluator: ContextualEvaluator) -> None:
        self.bundle = bundle
        self.evaluator = evaluator

    @property
    def evaluator_id(self) -> str:
        return self.evaluator.config.evaluator_id

    @property
    def evaluator_sha256(self) -> str:
        return self.evaluator.config.config_sha256

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        candidates = tuple(request.eligible_cards)
        if not candidates:
            selected = "FAIL_TO_FIND"
            evaluations: dict[str, float] = {}
        else:
            priority_name = str(self.bundle.value("tutor_priority"))
            order = self.evaluator.config.tutor_priority_orders.get(priority_name, ())
            rank = {name: len(order) - index for index, name in enumerate(order)}
            scored = []
            evaluations = {}
            for card in candidates:
                value = self.evaluator.evaluate_pile((card,), request.observation).score
                evaluations[card.identity] = max(evaluations.get(card.identity, value), value)
                scored.append((value, rank.get(card.identity, 0), card.identity))
            selected = max(scored)[2]
        return TutorChoiceSelection(
            selected,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "tutor_priority": self.bundle.value("tutor_priority"),
                "eligible_identities": list(request.eligible_identities),
                "candidate_evaluation_microunits": {
                    name: score_to_microunits(value) for name, value in evaluations.items()
                },
            },
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        if self.evaluator.config.opponent_choice_mode != "PERFECT_MINIMIZER":
            raise ValueError("unsupported opponent Fact or Fiction choice mode")
        cards = {card.handle: card for card in request.revealed_cards}
        candidates: list[tuple[tuple[Any, ...], int, Any, Any]] = []
        for split in request.legal_splits:
            pile_a = [cards[handle] for handle in split.pile_a_handles]
            pile_b = [cards[handle] for handle in split.pile_b_handles]
            eval_a = self.evaluator.evaluate_pile(pile_a, request.observation)
            eval_b = self.evaluator.evaluate_pile(pile_b, request.observation)
            key = (
                max(eval_a.score, eval_b.score),
                abs(eval_a.score - eval_b.score),
                tuple(sorted(split.pile_a_handles)),
                tuple(sorted(split.pile_b_handles)),
            )
            candidates.append((key, split.split_index, eval_a, eval_b))
        _, split_index, eval_a, eval_b = min(candidates, key=lambda item: item[0])
        chosen = (
            "A"
            if (
                eval_a.score,
                len(request.legal_splits[split_index].pile_a_handles),
                tuple(sorted(request.legal_splits[split_index].pile_a_handles)),
            )
            >= (
                eval_b.score,
                len(request.legal_splits[split_index].pile_b_handles),
                tuple(sorted(request.legal_splits[split_index].pile_b_handles)),
            )
            else "B"
        )
        return FactOrFictionSelection(
            split_index,
            chosen,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.bundle.policy_config_id,
                "opponent_choice_mode": self.evaluator.config.opponent_choice_mode,
                "pile_a_evaluation": eval_a.to_dict(),
                "pile_b_evaluation": eval_b.to_dict(),
                "candidate_split_count": len(candidates),
            },
        )

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        selected = request.original_target_handles
        diagnostics: dict[str, Any] = {
            "policy_config_id": self.bundle.policy_config_id,
            "strategy": "RETAIN_ORIGINAL_TARGETS",
        }
        if (
            request.source_identity == "Dualcaster Mage"
            and request.copied_spell_identity == "Twinflame"
        ):
            raise UnsupportedCapability(
                "canonical Dualcaster/Twinflame loop adjudication is not implemented; "
                "audit witnesses may use an explicit bounded test provider"
            )
        if selected not in request.legal_target_sets:
            raise ValueError("policy selected a copy target set outside the legal choices")
        return SpellCopyTargetSelection(
            selected,
            self.evaluator_id,
            self.evaluator_sha256,
            diagnostics,
        )


def bind_policy_strategic_choices(
    executor: GameExecutor,
    bundle: PolicyBundle,
    evaluator: ContextualEvaluator,
) -> PolicyStrategicChoiceProvider:
    """Attach one frozen policy/evaluator snapshot to the shared executor."""

    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    executor.bind_strategic_choice_provider(provider)
    return provider
