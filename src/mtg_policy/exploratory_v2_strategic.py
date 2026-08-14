"""Complete rules-defined strategic-choice coverage for Phase C Exploratory V2."""

from __future__ import annotations

import json
from dataclasses import replace
from itertools import combinations
from typing import Any, Mapping, Sequence

from mtg_kernel.strategic_choices import (
    CardSelection,
    CardSelectionRequest,
    FactOrFictionRequest,
    FactOrFictionSelection,
    OptionalTriggerRequest,
    OptionalTriggerSelection,
    PublicCard,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy.exploratory_v2 import (
    GLINT_HORN,
    ExploratoryStrategicChoiceProvider,
    canonical_interaction_signature,
    visible_identities,
)
from mtg_search.directed_v2 import (
    CandidateScoreVector,
    DirectedCandidate,
    DirectedSelection,
    canonical_sha256,
    select_directed_candidate,
)

_FAIL_TO_FIND = "__LEGAL_FAIL_TO_FIND__"
_SEARCH_PURPOSE_MARKERS = ("TUTOR", "SEARCH", "TRANSMUTE", "TYPECYCLE", "LANDCYCLE")
_MAX_ENUMERATED_CARD_SELECTIONS = 64


def _phase(observation: Mapping[str, Any]) -> str:
    return str(observation.get("phase") or observation.get("step") or "STRATEGIC_CHOICE")


def _semantic_key(
    *,
    purpose: str,
    action_kind: str,
    identities: Sequence[str],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "purpose": purpose,
            "action_kind": action_kind,
            "identities": sorted(str(identity) for identity in identities),
            "metadata": dict(metadata or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _combo_progress(
    observation: Mapping[str, Any],
    identities: Sequence[str],
    packages: Mapping[str, Sequence[str]],
) -> tuple[int, str | None, bool]:
    visible = set(visible_identities(observation))
    visible.update(str(identity) for identity in identities)
    best_progress = 0
    best_package: str | None = None
    conditional = False
    for package, raw_cards in packages.items():
        cards = {str(card) for card in raw_cards}
        if not cards:
            continue
        progress = len(cards.intersection(visible)) * 100 // len(cards)
        if progress > best_progress:
            best_progress = progress
            best_package = str(package)
            conditional = "psychosis" in str(package).lower()
    return best_progress, best_package, conditional


def _selection_score(
    *,
    observation: Mapping[str, Any],
    identities: Sequence[str],
    cards: Sequence[PublicCard],
    packages: Mapping[str, Sequence[str]],
    purpose: str,
    novelty_value: int,
    constraint_status: str,
    baseline_selected: bool,
    reason_code: str,
) -> tuple[CandidateScoreVector, str | None]:
    progress, package_id, conditional = _combo_progress(observation, identities, packages)
    mana_values = [max(0, int(card.mana_value)) for card in cards]
    selection_value = min(100, 40 + progress // 2 + len(cards) * 5)
    if any(marker in purpose.upper() for marker in _SEARCH_PURPOSE_MARKERS):
        selection_value = min(100, selection_value + 25)
    if baseline_selected:
        selection_value = min(100, selection_value + 10)
    conditional_status = "NONE"
    if conditional and progress >= 100:
        conditional_status = "AVAILABLE"
    elif conditional and progress > 0:
        conditional_status = "PROGRESS"
    return (
        CandidateScoreVector(
            immediate_deterministic_access=False,
            projected_deterministic_access=False,
            earliest_projected_access_turn=None,
            known_package_progress=progress,
            mana_development_value=0,
            relevant_resource_preservation=max(0, 100 - min(100, sum(mana_values) * 5)),
            card_selection_or_tutor_value=selection_value,
            conditional_access_status=conditional_status,
            novelty_value=novelty_value,
            arm_constraint_status=constraint_status,
            action_cost=0,
            reason_codes=(reason_code,),
        ),
        package_id,
    )


def _neutral_score(
    *,
    novelty_value: int,
    baseline_selected: bool,
    reason_code: str,
    value: int = 0,
    constraint_status: str = "ALLOWED",
) -> CandidateScoreVector:
    return CandidateScoreVector(
        immediate_deterministic_access=False,
        projected_deterministic_access=False,
        earliest_projected_access_turn=None,
        known_package_progress=0,
        mana_development_value=0,
        relevant_resource_preservation=100,
        card_selection_or_tutor_value=min(100, value + (10 if baseline_selected else 0)),
        conditional_access_status="NONE",
        novelty_value=novelty_value,
        arm_constraint_status=constraint_status,
        action_cost=0,
        reason_codes=(reason_code,),
    )


class ExploratoryStrategicChoiceProviderV2(ExploratoryStrategicChoiceProvider):
    """Directed V2 policy for every rules-defined strategic-choice contract.

    The kernel remains the sole source of legality. This provider consumes only the
    observation-safe candidate sets exposed by the kernel, retains frozen STANDARD as
    the explicit baseline, records every evaluated or pruned candidate, and never
    reads the hidden library or future environment RNG.
    """

    def _select(
        self,
        *,
        request_id: str,
        purpose: str,
        turn_number: int,
        observation: Mapping[str, Any],
        candidates: Sequence[DirectedCandidate],
        baseline_handle: str,
        novelty_before: Mapping[str, int],
        exclusions: Sequence[Mapping[str, Any]] = (),
        extra_pruning: Sequence[Mapping[str, Any]] = (),
        replay_binding: Mapping[str, Any] | None = None,
    ) -> DirectedSelection:
        decision_id = self._decision_id(request_id, purpose)
        selection = select_directed_candidate(
            self.config,
            candidates,
            baseline_handle=baseline_handle,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
        )
        by_handle = {candidate.handle: candidate for candidate in selection.candidates}
        baseline = by_handle[baseline_handle]
        selected = by_handle[selection.selected_handle]
        pruned = [
            {"handle": candidate.handle, "reason": candidate.pruned_reason}
            for candidate in selection.candidates
            if candidate.pruned_reason is not None
        ]
        pruned.extend(dict(item) for item in extra_pruning)
        self.records.append(
            {
                "schema_version": "phase-c-exploratory-v2-decision-v1",
                "arm_id": self.config.arm_id,
                "game_index": self.game_index,
                "environment_seed": self.environment_seed,
                "exploration_seed": self.exploration_seed,
                "decision_id": decision_id,
                "turn": int(turn_number),
                "phase": _phase(observation),
                "public_observation_digest": canonical_sha256(observation),
                "strategic_choice_purpose": purpose,
                "legal_candidate_handles": [candidate.handle for candidate in candidates],
                "standard_baseline_handle": baseline_handle,
                "standard_baseline_score_vector": baseline.score.to_dict(),
                "candidate_evaluations": [
                    {
                        "handle": candidate.handle,
                        "semantic_key": candidate.semantic_key,
                        "score": candidate.score.to_dict(),
                        "pruned_reason": candidate.pruned_reason,
                    }
                    for candidate in selection.candidates
                ],
                "pruned_candidates": pruned,
                "arm_specific_exclusions": [dict(item) for item in exclusions],
                "novelty_state_before": dict(novelty_before),
                "equivalence_window": dict(self.config.equivalence_window),
                "eligible_top_k": list(selection.eligible_top_k),
                "selected_action": selection.selected_handle,
                "selection_reason": selection.selection_reason,
                "randomness_affected_selection": selection.randomness_affected_selection,
                "selected_plan_or_package_id": self._package_for_candidate(selected),
                "continuation_method": "RULES_DEFINED_STRATEGIC_CHOICE_RETURN_TO_ENGINE",
                "continuation_horizon": {
                    "hidden_future_consumed": False,
                    "strategic_choice_only": True,
                },
                "plan_termination_or_fallback_reason": "RETURN_TO_ENGINE",
                "resulting_public_state_digest": None,
                "replay_binding": {
                    "request_id": request_id,
                    **dict(replay_binding or {}),
                },
                "exploration_seed_digest": selection.exploration_seed_digest,
            }
        )
        return selection

    def _package_for_candidate(self, candidate: DirectedCandidate) -> str | None:
        progress = candidate.score.known_package_progress
        if progress <= 0:
            return None
        semantic = json.loads(candidate.semantic_key)
        identities = semantic.get("identities", ()) if isinstance(semantic, Mapping) else ()
        if not isinstance(identities, Sequence):
            return None
        _progress, package_id, _conditional = _combo_progress(
            {}, tuple(str(value) for value in identities), self.combo_packages
        )
        return package_id

    def _card_combo_candidate(
        self,
        *,
        request: CardSelectionRequest,
        selected_cards: Sequence[PublicCard],
        handle: str,
        baseline_handle: str,
        glint_restricted: bool,
    ) -> tuple[DirectedCandidate, Mapping[str, Any] | None, str]:
        identities = tuple(card.identity for card in selected_cards)
        signature = canonical_interaction_signature(
            purpose=request.purpose,
            action_kind="CARD_SELECTION",
            identity="|".join(sorted(identities)) or None,
            metadata={"ability_id": request.ability_id, "count": len(selected_cards)},
        )
        prohibited = glint_restricted and GLINT_HORN in identities
        status = "PROHIBITED_NO_GLINT_TUTOR" if prohibited else "ALLOWED"
        prune = "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR" if prohibited else None
        score, _package = _selection_score(
            observation=request.observation,
            identities=identities,
            cards=selected_cards,
            packages=self.combo_packages,
            purpose=request.purpose,
            novelty_value=self.novelty.novelty_value(signature),
            constraint_status=status,
            baseline_selected=handle == baseline_handle,
            reason_code=f"STRATEGIC_CARD_SELECTION_{request.purpose}",
        )
        exclusion: Mapping[str, Any] | None = None
        if prohibited:
            exclusion = {
                "identity": GLINT_HORN,
                "candidate_handle": handle,
                "reason": "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR",
            }
        semantic = _semantic_key(
            purpose=request.purpose,
            action_kind="CARD_SELECTION",
            identities=identities,
            metadata={"ability_id": request.ability_id, "count": len(selected_cards)},
        )
        return DirectedCandidate(handle, semantic, score, prune), exclusion, signature

    @staticmethod
    def _selection_handle(handles: Sequence[str]) -> str:
        if not handles:
            return _FAIL_TO_FIND
        return "SELECT:" + "|".join(sorted(str(handle) for handle in handles))

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        baseline = self.baseline.choose_cards(request)
        baseline_handle = self._selection_handle(baseline.selected_handles)
        purpose_upper = request.purpose.upper()
        glint_restricted = self.config.no_glint_horn_tutoring and any(
            marker in purpose_upper for marker in _SEARCH_PURPOSE_MARKERS
        )
        novelty_before = self.novelty.snapshot()
        combinations_to_consider: list[tuple[PublicCard, ...]] = []
        overflow = False
        for count in range(request.minimum, request.maximum + 1):
            for choice in combinations(request.candidates, count):
                combinations_to_consider.append(choice)
                if len(combinations_to_consider) > _MAX_ENUMERATED_CARD_SELECTIONS:
                    overflow = True
                    break
            if overflow:
                break

        exclusions: list[Mapping[str, Any]] = []
        signatures: dict[str, str] = {}
        selected_handles_by_candidate: dict[str, tuple[str, ...]] = {}
        directed: list[DirectedCandidate] = []
        extra_pruning: list[Mapping[str, Any]] = []

        if not overflow:
            for selected_cards in combinations_to_consider:
                raw_handles = tuple(card.handle for card in selected_cards)
                handle = self._selection_handle(raw_handles)
                candidate, exclusion, signature = self._card_combo_candidate(
                    request=request,
                    selected_cards=selected_cards,
                    handle=handle,
                    baseline_handle=baseline_handle,
                    glint_restricted=glint_restricted,
                )
                directed.append(candidate)
                signatures[handle] = signature
                selected_handles_by_candidate[handle] = raw_handles
                if exclusion is not None:
                    exclusions.append(exclusion)
        else:
            cards_by_handle = {card.handle: card for card in request.candidates}
            baseline_cards = tuple(
                cards_by_handle[handle]
                for handle in baseline.selected_handles
                if handle in cards_by_handle
            )
            candidate, exclusion, signature = self._card_combo_candidate(
                request=request,
                selected_cards=baseline_cards,
                handle=baseline_handle,
                baseline_handle=baseline_handle,
                glint_restricted=glint_restricted,
            )
            directed.append(candidate)
            signatures[baseline_handle] = signature
            selected_handles_by_candidate[baseline_handle] = tuple(baseline.selected_handles)
            if exclusion is not None:
                exclusions.append(exclusion)
            extra_pruning.append(
                {
                    "scope": "CARD_SELECTION_COMBINATIONS",
                    "candidate_count_lower_bound": len(combinations_to_consider),
                    "reason": "COMBINATORIAL_SET_EXCEEDS_V2_ENUMERATION_BOUND",
                }
            )
            if candidate.pruned_reason is not None:
                filtered = tuple(
                    card for card in request.candidates if card.identity != GLINT_HORN
                )
                if len(filtered) < request.minimum:
                    raise ValueError("Arm 2 has no legal non-Glint selection inside bounded choice")
                alternative_request = replace(request, candidates=filtered)
                alternative = self.baseline.choose_cards(alternative_request)
                alternative_handle = self._selection_handle(alternative.selected_handles)
                alternative_cards = tuple(
                    card for card in filtered if card.handle in set(alternative.selected_handles)
                )
                alt_candidate, _exclusion, alt_signature = self._card_combo_candidate(
                    request=request,
                    selected_cards=alternative_cards,
                    handle=alternative_handle,
                    baseline_handle=baseline_handle,
                    glint_restricted=True,
                )
                if alternative_handle != baseline_handle:
                    directed.append(alt_candidate)
                    signatures[alternative_handle] = alt_signature
                    selected_handles_by_candidate[alternative_handle] = tuple(
                        alternative.selected_handles
                    )

        if baseline_handle not in {candidate.handle for candidate in directed}:
            raise ValueError("STANDARD card-selection baseline was not retained")
        selection = self._select(
            request_id=request.request_id,
            purpose=request.purpose,
            turn_number=request.turn_number,
            observation=request.observation,
            candidates=directed,
            baseline_handle=baseline_handle,
            novelty_before=novelty_before,
            exclusions=exclusions,
            extra_pruning=extra_pruning,
            replay_binding={"ability_id": request.ability_id},
        )
        selected_handles = selected_handles_by_candidate[selection.selected_handle]
        self.novelty.visit(signatures[selection.selected_handle])
        return CardSelection(
            selected_handles,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_selected_handles": list(baseline.selected_handles),
                "selected_handles": list(selected_handles),
                "selection_reason": selection.selection_reason,
                "arm_specific_exclusions": [dict(item) for item in exclusions],
            },
        )

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        baseline = self.baseline.choose_tutor(request)
        baseline_handle = f"TUTOR:{baseline.selected_identity}"
        novelty_before = self.novelty.snapshot()
        cards_by_identity: dict[str, PublicCard] = {}
        for card in request.eligible_cards:
            cards_by_identity.setdefault(card.identity, card)
        if baseline.selected_identity == "FAIL_TO_FIND":
            cards_by_identity.setdefault(
                "FAIL_TO_FIND",
                PublicCard(_FAIL_TO_FIND, "FAIL_TO_FIND", 0, (), ()),
            )
        directed: list[DirectedCandidate] = []
        exclusions: list[Mapping[str, Any]] = []
        signatures: dict[str, str] = {}
        for identity, card in sorted(cards_by_identity.items()):
            handle = f"TUTOR:{identity}"
            signature = canonical_interaction_signature(
                purpose="TUTOR",
                action_kind="TUTOR_TARGET",
                identity=None if identity == "FAIL_TO_FIND" else identity,
                metadata={"ability_id": request.ability_id},
            )
            prohibited = self.config.no_glint_horn_tutoring and identity == GLINT_HORN
            status = "PROHIBITED_NO_GLINT_TUTOR" if prohibited else "ALLOWED"
            prune = "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR" if prohibited else None
            score, _package = _selection_score(
                observation=request.observation,
                identities=() if identity == "FAIL_TO_FIND" else (identity,),
                cards=() if identity == "FAIL_TO_FIND" else (card,),
                packages=self.combo_packages,
                purpose="TUTOR",
                novelty_value=self.novelty.novelty_value(signature),
                constraint_status=status,
                baseline_selected=handle == baseline_handle,
                reason_code="STRATEGIC_TUTOR_TARGET",
            )
            directed.append(
                DirectedCandidate(
                    handle=handle,
                    semantic_key=_semantic_key(
                        purpose="TUTOR",
                        action_kind="TUTOR_TARGET",
                        identities=() if identity == "FAIL_TO_FIND" else (identity,),
                        metadata={"ability_id": request.ability_id},
                    ),
                    score=score,
                    pruned_reason=prune,
                )
            )
            signatures[handle] = signature
            if prohibited:
                exclusions.append(
                    {
                        "identity": GLINT_HORN,
                        "candidate_handle": handle,
                        "reason": "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR",
                        "legal_alternative_identities": sorted(
                            value for value in cards_by_identity if value != GLINT_HORN
                        ),
                    }
                )
        if baseline_handle not in {candidate.handle for candidate in directed}:
            raise ValueError("STANDARD tutor baseline was not retained")
        selection = self._select(
            request_id=request.request_id,
            purpose="TUTOR",
            turn_number=request.turn_number,
            observation=request.observation,
            candidates=directed,
            baseline_handle=baseline_handle,
            novelty_before=novelty_before,
            exclusions=exclusions,
            replay_binding={"ability_id": request.ability_id},
        )
        selected_identity = selection.selected_handle.removeprefix("TUTOR:")
        self.novelty.visit(signatures[selection.selected_handle])
        return TutorChoiceSelection(
            selected_identity,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_selected_identity": baseline.selected_identity,
                "selected_identity": selected_identity,
                "selection_reason": selection.selection_reason,
                "arm_specific_exclusions": [dict(item) for item in exclusions],
            },
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        baseline = self.baseline.choose_fact_or_fiction(request)
        baseline_handle = f"FOF:{baseline.split_index}:{baseline.chosen_pile}"
        novelty_before = self.novelty.snapshot()
        cards_by_handle = {card.handle: card for card in request.revealed_cards}
        directed: list[DirectedCandidate] = []
        signatures: dict[str, str] = {}
        selection_by_handle: dict[str, tuple[int, str]] = {}
        for split in request.legal_splits:
            for pile_name, pile_handles in (
                ("A", split.pile_a_handles),
                ("B", split.pile_b_handles),
            ):
                chosen_cards = tuple(
                    cards_by_handle[handle]
                    for handle in pile_handles
                    if handle in cards_by_handle
                )
                identities = tuple(card.identity for card in chosen_cards)
                handle = f"FOF:{split.split_index}:{pile_name}"
                signature = canonical_interaction_signature(
                    purpose="FACT_OR_FICTION",
                    action_kind="PILE_SELECTION",
                    identity="|".join(sorted(identities)) or None,
                    metadata={"split_index": split.split_index, "pile": pile_name},
                )
                score, _package = _selection_score(
                    observation=request.observation,
                    identities=identities,
                    cards=chosen_cards,
                    packages=self.combo_packages,
                    purpose="FACT_OR_FICTION",
                    novelty_value=self.novelty.novelty_value(signature),
                    constraint_status="ALLOWED",
                    baseline_selected=handle == baseline_handle,
                    reason_code="STRATEGIC_FACT_OR_FICTION_PILE",
                )
                directed.append(
                    DirectedCandidate(
                        handle,
                        _semantic_key(
                            purpose="FACT_OR_FICTION",
                            action_kind="PILE_SELECTION",
                            identities=identities,
                            metadata={"split_index": split.split_index, "pile": pile_name},
                        ),
                        score,
                    )
                )
                signatures[handle] = signature
                selection_by_handle[handle] = (split.split_index, pile_name)
        selection = self._select(
            request_id=request.request_id,
            purpose="FACT_OR_FICTION",
            turn_number=request.turn_number,
            observation=request.observation,
            candidates=directed,
            baseline_handle=baseline_handle,
            novelty_before=novelty_before,
            replay_binding={"opponent_id": request.opponent_id},
        )
        split_index, chosen_pile = selection_by_handle[selection.selected_handle]
        self.novelty.visit(signatures[selection.selected_handle])
        return FactOrFictionSelection(
            split_index,
            chosen_pile,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_split_index": baseline.split_index,
                "baseline_chosen_pile": baseline.chosen_pile,
                "selection_reason": selection.selection_reason,
            },
        )

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        baseline = self.baseline.choose_spell_copy_targets(request)
        baseline_handle = self._selection_handle(baseline.target_handles)
        novelty_before = self.novelty.snapshot()
        cards_by_handle = {card.handle: card for card in request.legal_targets}
        directed: list[DirectedCandidate] = []
        targets_by_handle: dict[str, tuple[str, ...]] = {}
        signatures: dict[str, str] = {}
        for target_set in request.legal_target_sets:
            handle = self._selection_handle(target_set)
            target_cards = tuple(
                cards_by_handle[target] for target in target_set if target in cards_by_handle
            )
            identities = tuple(card.identity for card in target_cards)
            signature = canonical_interaction_signature(
                purpose="SPELL_COPY_TARGETS",
                action_kind="COPY_TARGET_SELECTION",
                identity="|".join(sorted(identities)) or None,
                metadata={
                    "source_identity": request.source_identity,
                    "copied_spell_identity": request.copied_spell_identity,
                    "target_count": len(target_set),
                },
            )
            score, _package = _selection_score(
                observation=request.observation,
                identities=identities,
                cards=target_cards,
                packages=self.combo_packages,
                purpose="SPELL_COPY_TARGETS",
                novelty_value=self.novelty.novelty_value(signature),
                constraint_status="ALLOWED",
                baseline_selected=handle == baseline_handle,
                reason_code="STRATEGIC_SPELL_COPY_TARGET",
            )
            directed.append(
                DirectedCandidate(
                    handle,
                    _semantic_key(
                        purpose="SPELL_COPY_TARGETS",
                        action_kind="COPY_TARGET_SELECTION",
                        identities=identities,
                        metadata={
                            "source_identity": request.source_identity,
                            "copied_spell_identity": request.copied_spell_identity,
                            "target_count": len(target_set),
                        },
                    ),
                    score,
                )
            )
            targets_by_handle[handle] = tuple(target_set)
            signatures[handle] = signature
        selection = self._select(
            request_id=request.request_id,
            purpose="SPELL_COPY_TARGETS",
            turn_number=request.turn_number,
            observation=request.observation,
            candidates=directed,
            baseline_handle=baseline_handle,
            novelty_before=novelty_before,
            replay_binding={
                "source_identity": request.source_identity,
                "copied_spell_identity": request.copied_spell_identity,
            },
        )
        selected_targets = targets_by_handle[selection.selected_handle]
        self.novelty.visit(signatures[selection.selected_handle])
        return SpellCopyTargetSelection(
            selected_targets,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_target_handles": list(baseline.target_handles),
                "selection_reason": selection.selection_reason,
            },
        )

    def choose_optional_trigger(self, request: OptionalTriggerRequest) -> OptionalTriggerSelection:
        baseline = self.baseline.choose_optional_trigger(request)
        baseline_handle = "OPTIONAL_TRIGGER:TAKE" if baseline.take else "OPTIONAL_TRIGGER:SKIP"
        novelty_before = self.novelty.snapshot()
        effect = request.effect_kind.upper()
        take_value = 70 if any(marker in effect for marker in ("DRAW", "MANA", "TREASURE")) else 40
        directed: list[DirectedCandidate] = []
        signatures: dict[str, str] = {}
        for take in (True, False):
            handle = "OPTIONAL_TRIGGER:TAKE" if take else "OPTIONAL_TRIGGER:SKIP"
            signature = canonical_interaction_signature(
                purpose="OPTIONAL_TRIGGER",
                action_kind=handle,
                identity=None,
                metadata={"ability_id": request.ability_id, "effect_kind": request.effect_kind},
            )
            score = _neutral_score(
                novelty_value=self.novelty.novelty_value(signature),
                baseline_selected=handle == baseline_handle,
                reason_code=f"STRATEGIC_{handle}",
                value=take_value if take else 0,
            )
            directed.append(
                DirectedCandidate(
                    handle,
                    _semantic_key(
                        purpose="OPTIONAL_TRIGGER",
                        action_kind=handle,
                        identities=(),
                        metadata={
                            "ability_id": request.ability_id,
                            "effect_kind": request.effect_kind,
                        },
                    ),
                    score,
                )
            )
            signatures[handle] = signature
        selection = self._select(
            request_id=request.request_id,
            purpose="OPTIONAL_TRIGGER",
            turn_number=request.turn_number,
            observation=request.observation,
            candidates=directed,
            baseline_handle=baseline_handle,
            novelty_before=novelty_before,
            replay_binding={
                "ability_id": request.ability_id,
                "effect_kind": request.effect_kind,
            },
        )
        take = selection.selected_handle == "OPTIONAL_TRIGGER:TAKE"
        self.novelty.visit(signatures[selection.selected_handle])
        return OptionalTriggerSelection(
            take,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_take": baseline.take,
                "selection_reason": selection.selection_reason,
            },
        )


__all__ = ["ExploratoryStrategicChoiceProviderV2"]
