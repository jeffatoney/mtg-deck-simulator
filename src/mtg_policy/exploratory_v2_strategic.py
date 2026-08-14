"""Complete strategic-choice coverage for Phase C Exploratory V2."""

from __future__ import annotations

from typing import Any

from mtg_kernel.strategic_choices import CardSelection, CardSelectionRequest
from mtg_policy.exploratory_v2 import (
    GLINT_HORN,
    ExploratoryStrategicChoiceProvider,
    _public_card_score,
    canonical_interaction_signature,
)
from mtg_search.directed_v2 import (
    CandidateScoreVector,
    DirectedCandidate,
    select_directed_candidate,
)

_FAIL_TO_FIND = "__LEGAL_FAIL_TO_FIND__"
_SEARCH_PURPOSE_MARKERS = ("TUTOR", "SEARCH", "TRANSMUTE", "TYPECYCLE", "LANDCYCLE")


class ExploratoryStrategicChoiceProviderV2(ExploratoryStrategicChoiceProvider):
    """Adds bounded optional zero-or-one selection to the base V2 provider.

    Rules still define the eligible candidates and whether fail-to-find is legal. This
    wrapper only ranks that complete policy-facing set and applies arm constraints.
    """

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        if request.maximum != 1 or request.minimum != 0:
            return super().choose_cards(request)

        baseline = self.baseline.choose_cards(request)
        if len(baseline.selected_handles) > 1:
            raise ValueError("optional zero-or-one selection produced an invalid STANDARD baseline")
        baseline_handle = (
            baseline.selected_handles[0] if baseline.selected_handles else _FAIL_TO_FIND
        )
        purpose_upper = request.purpose.upper()
        glint_restricted = self.config.no_glint_horn_tutoring and any(
            marker in purpose_upper for marker in _SEARCH_PURPOSE_MARKERS
        )
        exclusions: list[dict[str, Any]] = []
        cards_by_handle = {card.handle: card for card in request.candidates}
        candidates: list[DirectedCandidate] = []
        for card in request.candidates:
            signature = canonical_interaction_signature(
                purpose=request.purpose,
                action_kind="CARD_SELECTION",
                identity=card.identity,
                metadata={"ability_id": request.ability_id},
            )
            prohibited = glint_restricted and card.identity == GLINT_HORN
            status = "PROHIBITED_NO_GLINT_TUTOR" if prohibited else "ALLOWED"
            prune = "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR" if prohibited else None
            if prohibited:
                exclusions.append(
                    {
                        "identity": GLINT_HORN,
                        "reason": "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR",
                        "legal_alternative_identities": sorted(
                            candidate.identity
                            for candidate in request.candidates
                            if candidate.identity != GLINT_HORN
                        ),
                        "fail_to_find_legally_available": True,
                    }
                )
            candidates.append(
                DirectedCandidate(
                    handle=card.handle,
                    semantic_key=f"{card.identity}:{request.purpose}",
                    score=_public_card_score(
                        card,
                        request.observation,
                        self.combo_packages,
                        purpose=request.purpose,
                        novelty_value=self.novelty.novelty_value(signature),
                        constraint_status=status,
                        baseline_selected=card.handle == baseline_handle,
                    ),
                    pruned_reason=prune,
                )
            )

        fail_signature = canonical_interaction_signature(
            purpose=request.purpose,
            action_kind="CARD_SELECTION_FAIL_TO_FIND",
            identity=None,
            metadata={"ability_id": request.ability_id},
        )
        candidates.append(
            DirectedCandidate(
                handle=_FAIL_TO_FIND,
                semantic_key=f"FAIL_TO_FIND:{request.purpose}",
                score=CandidateScoreVector(
                    immediate_deterministic_access=False,
                    projected_deterministic_access=False,
                    earliest_projected_access_turn=None,
                    known_package_progress=0,
                    mana_development_value=0,
                    relevant_resource_preservation=100,
                    card_selection_or_tutor_value=0,
                    conditional_access_status="NONE",
                    novelty_value=self.novelty.novelty_value(fail_signature),
                    arm_constraint_status="ALLOWED",
                    action_cost=0,
                    reason_codes=("LEGAL_FAIL_TO_FIND",),
                ),
            )
        )
        if baseline_handle not in {candidate.handle for candidate in candidates}:
            raise ValueError("STANDARD optional-selection baseline is absent from legal candidates")

        decision_id = self._decision_id(request.request_id, request.purpose)
        selection = select_directed_candidate(
            self.config,
            candidates,
            baseline_handle=baseline_handle,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
        )
        if selection.selected_handle == _FAIL_TO_FIND:
            selected_handles: tuple[str, ...] = ()
            selected_identity: str | None = None
            selected_signature = fail_signature
        else:
            selected_card = cards_by_handle[selection.selected_handle]
            selected_handles = (selection.selected_handle,)
            selected_identity = selected_card.identity
            selected_signature = canonical_interaction_signature(
                purpose=request.purpose,
                action_kind="CARD_SELECTION",
                identity=selected_identity,
                metadata={"ability_id": request.ability_id},
            )
        self.novelty.visit(selected_signature)
        self._record_selection(
            request_id=request.request_id,
            purpose=request.purpose,
            baseline_handle=baseline_handle,
            selection=selection,
            exclusions=exclusions,
        )
        ranked = {candidate.handle: candidate for candidate in selection.candidates}
        legal_handles = tuple(card.handle for card in request.candidates) + (_FAIL_TO_FIND,)
        return CardSelection(
            selected_handles,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_selected_handles": list(baseline.selected_handles),
                "legal_candidate_handles": list(legal_handles),
                "selected_identity": selected_identity,
                "selection_reason": selection.selection_reason,
                "candidate_evaluations": [
                    {
                        "identity": cards_by_handle[handle].identity
                        if handle in cards_by_handle
                        else None,
                        "handle": handle,
                        "score": ranked[handle].score.to_dict(),
                        "pruned_reason": ranked[handle].pruned_reason,
                    }
                    for handle in legal_handles
                ],
                "arm_specific_exclusions": exclusions,
            },
        )


__all__ = ["ExploratoryStrategicChoiceProviderV2"]
