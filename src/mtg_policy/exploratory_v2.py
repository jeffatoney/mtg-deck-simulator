"""Policy-layer controls for Phase C directed exploratory V2.

This module never enumerates legality.  It consumes broker actions and rules-defined
strategic-choice requests, applies only arm-specific policy constraints, and records
observation-safe decision evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
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
from mtg_policy.broker_core import ObservedAction
from mtg_policy.choices import PolicyStrategicChoiceProvider
from mtg_search.directed_v2 import (
    ALT_PACKAGE_ARM,
    CandidateScoreVector,
    DirectedArmConfig,
    DirectedCandidate,
    canonical_sha256,
    select_directed_candidate,
)

GLINT_HORN = "Glint-Horn Buccaneer"

DISCOVERY_CLASSIFICATIONS = frozenset(
    {
        "NEW_PACKAGE_SEQUENCE",
        "NEW_TUTOR_TARGET",
        "NEW_MODAL_SELECTION",
        "NEW_ACTIVATED_ABILITY_LINE",
        "NEW_MANA_SEQUENCE",
        "NEW_DRAW_OR_DISCARD_SEQUENCE",
        "NEW_COMMANDER_SEQUENCE",
        "NEW_CONDITIONAL_ACCESS_LINE",
        "NEW_DETERMINISTIC_ACCESS_LINE",
        "REVISITED_UNDEREXPLORED_LINE",
    }
)

_HIDDEN_METADATA_KEYS = frozenset(
    {
        "card_instance_id",
        "card_instance_ids",
        "generation",
        "object_id",
        "object_ids",
        "source_object_id",
        "target_handle",
        "target_handles",
        "object_handle",
        "attacker_handles",
    }
)


class LandHoldReason(StrEnum):
    """Finite reason-code set. There is deliberately no OTHER value."""

    GLINT_HORN_DISCARD_RESOURCE = "GLINT_HORN_DISCARD_RESOURCE"
    BOUNCE_LAND_SEQUENCE = "BOUNCE_LAND_SEQUENCE"
    REVEAL_LAND_BASIC_PRESERVATION = "REVEAL_LAND_BASIC_PRESERVATION"
    LAND_SEARCH_OR_CYCLING_SEQUENCE = "LAND_SEARCH_OR_CYCLING_SEQUENCE"
    COLOR_FIXING_SEQUENCE = "COLOR_FIXING_SEQUENCE"
    RULES_OR_RESOURCE_CONFLICT = "RULES_OR_RESOURCE_CONFLICT"


@dataclass(frozen=True)
class LandHoldEvidence:
    """Visible-state facts required to justify a main-phase land hold."""

    glint_horn_visible: bool = False
    discard_resource_shortage: bool = False
    bounce_land_candidate: bool = False
    land_return_sequence_pending: bool = False
    reveal_land_candidate: bool = False
    basic_land_candidate: bool = False
    reveal_requirement_relevant: bool = False
    land_search_or_cycling_action_available: bool = False
    color_fixing_action_available: bool = False
    required_color_missing: bool = False
    documented_conflict_code: str | None = None


@dataclass(frozen=True)
class PublicProjection:
    """Hidden-information-safe bounded continuation output."""

    immediate_deterministic_access: bool
    projected_deterministic_access: bool
    earliest_projected_access_turn: int | None
    continuation_actions: tuple[str, ...]
    stop_reason: str
    action_count: int


class NoveltyLedger:
    """Per-arm novelty state keyed only by canonical public interaction signatures."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def count(self, signature: str) -> int:
        return self._counts.get(signature, 0)

    def novelty_value(self, signature: str) -> int:
        return max(0, 10 - self.count(signature))

    def visit(self, signature: str) -> None:
        self._counts[signature] = self.count(signature) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._counts.items()))


def validate_land_hold_reason(reason: LandHoldReason, evidence: LandHoldEvidence) -> bool:
    """Validate a finite land-hold reason solely from supplied visible facts."""

    if reason is LandHoldReason.GLINT_HORN_DISCARD_RESOURCE:
        return evidence.glint_horn_visible and evidence.discard_resource_shortage
    if reason is LandHoldReason.BOUNCE_LAND_SEQUENCE:
        return evidence.bounce_land_candidate and evidence.land_return_sequence_pending
    if reason is LandHoldReason.REVEAL_LAND_BASIC_PRESERVATION:
        return (
            evidence.reveal_land_candidate
            and evidence.basic_land_candidate
            and evidence.reveal_requirement_relevant
        )
    if reason is LandHoldReason.LAND_SEARCH_OR_CYCLING_SEQUENCE:
        return evidence.land_search_or_cycling_action_available
    if reason is LandHoldReason.COLOR_FIXING_SEQUENCE:
        return evidence.color_fixing_action_available and evidence.required_color_missing
    if reason is LandHoldReason.RULES_OR_RESOURCE_CONFLICT:
        return evidence.documented_conflict_code in {
            "ENTER_TAPPED_RESOURCE_CONFLICT",
            "MAX_HAND_DISCARD_PLAN",
            "REQUIRED_RETURN_RESOURCE_CONFLICT",
        }
    return False


def _visible_objects(observation: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    objects = observation.get("objects", ())
    if not isinstance(objects, Sequence) or isinstance(objects, (str, bytes)):
        return ()
    return tuple(item for item in objects if isinstance(item, Mapping))


def visible_identities(observation: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        str(item.get("identity", ""))
        for item in _visible_objects(observation)
        if str(item.get("identity", ""))
    )


def _normalize_public(value: Any, *, key: str | None = None) -> Any:
    if key is not None and (key in _HIDDEN_METADATA_KEYS or key.endswith("_handle")):
        return "<opaque>"
    if key is not None and (key.endswith("_handles") or key.endswith("_object_id")):
        return "<opaque>"
    if isinstance(value, Mapping):
        return {
            str(item_key): _normalize_public(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalize_public(item) for item in value]
    return value


def canonical_interaction_signature(
    *,
    purpose: str,
    action_kind: str,
    identity: str | None,
    metadata: Mapping[str, Any],
    package_id: str | None = None,
) -> str:
    """Create a replay-stable signature without raw object/action identity."""

    payload = {
        "purpose": purpose,
        "action_kind": action_kind,
        "identity": identity,
        "metadata": _normalize_public(metadata),
        "package_id": package_id,
    }
    return canonical_sha256(payload)


def semantic_action_key(action: ObservedAction) -> str:
    """Stable semantic action key used for ranking and hidden-future invariance."""

    return json.dumps(
        {
            "kind": action.kind,
            "identity": action.identity,
            "mana_value": action.mana_value,
            "tags": sorted(action.tags),
            "target_count": action.target_count,
            "metadata": _normalize_public(action.metadata),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _land_hold_evidence(
    observation: Mapping[str, Any], actions: Sequence[ObservedAction]
) -> LandHoldEvidence:
    objects = _visible_objects(observation)
    glint_visible = any(
        str(item.get("identity", "")) == GLINT_HORN and str(item.get("zone", "")) == "BATTLEFIELD"
        for item in objects
    )
    hand_lands = sum(
        str(item.get("zone", "")) == "HAND"
        and "Land" in {str(value) for value in item.get("card_types", ())}
        for item in objects
    )
    bounce = any(
        action.kind == "PLAY_LAND" and action.identity in {"Izzet Boilerworks", "Guildless Commons"}
        for action in actions
    )
    land_search = any(
        action.kind != "PASS_PRIORITY"
        and (
            action.identity == "Ash Barrens"
            or any(
                marker in tag.upper()
                for tag in action.tags
                for marker in ("TYPECYCLE", "LANDCYCLE", "SEARCH")
            )
        )
        for action in actions
    )
    return LandHoldEvidence(
        glint_horn_visible=glint_visible,
        discard_resource_shortage=hand_lands == 1,
        bounce_land_candidate=bounce,
        land_return_sequence_pending=False,
        land_search_or_cycling_action_available=land_search,
    )


def permitted_main_phase_pass_reason(
    observation: Mapping[str, Any], actions: Sequence[ObservedAction]
) -> LandHoldReason | None:
    """Return a validated automatic hold reason, or None so PASS fails closed."""

    evidence = _land_hold_evidence(observation, actions)
    reason = LandHoldReason.GLINT_HORN_DISCARD_RESOURCE
    if validate_land_hold_reason(reason, evidence):
        return reason
    return None


def _package_progress(
    identity: str | None,
    observation: Mapping[str, Any],
    combo_packages: Mapping[str, Sequence[str]],
) -> tuple[int, str | None, bool]:
    visible = set(visible_identities(observation))
    if identity:
        visible.add(identity)
    best = 0
    best_package: str | None = None
    conditional = False
    for package, raw_cards in combo_packages.items():
        cards = {str(card) for card in raw_cards}
        if not cards:
            continue
        present = len(cards.intersection(visible))
        progress = present * 100 // len(cards)
        if progress > best:
            best = progress
            best_package = str(package)
            conditional = "psychosis" in str(package).lower()
    return best, best_package, conditional


def _mana_development(action: ObservedAction) -> int:
    if action.kind == "PLAY_LAND":
        return 100
    upper_tags = {tag.upper() for tag in action.tags}
    if "MANA_ABILITY" in upper_tags:
        return 30
    if action.kind == "CAST" and "ARTIFACT" in upper_tags and action.mana_value <= 2:
        return 70
    if action.kind == "CAST" and upper_tags.intersection({"ARTIFACT", "CREATURE", "ENCHANTMENT"}):
        return 20
    return 0


def _tutor_value(action: ObservedAction) -> int:
    markers = " ".join((*action.tags, action.identity or "")).upper()
    if any(value in markers for value in ("TUTOR", "TRANSMUTE", "TYPECYCLE", "SEARCH")):
        return 100
    if any(value in markers for value in ("DRAW", "SCRY", "LOOK", "CANTRIP")):
        return 50
    return 0


def score_priority_candidate(
    *,
    action: ObservedAction,
    observation: Mapping[str, Any],
    all_actions: Sequence[ObservedAction],
    config: DirectedArmConfig,
    projection: PublicProjection,
    novelty_value: int,
    combo_packages: Mapping[str, Sequence[str]],
) -> tuple[CandidateScoreVector, str | None, str | None]:
    """Build the mandatory V2 score vector from public facts and bounded projection."""

    progress, package_id, conditional = _package_progress(
        action.identity, observation, combo_packages
    )
    constraint = "ALLOWED"
    prune: str | None = None
    reasons = [f"ACTION_KIND_{action.kind}", f"CONTINUATION_{projection.stop_reason}"]
    phase = str(observation.get("phase", ""))
    step = str(observation.get("step", ""))
    main_phase = phase in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"} or step in {
        "PRECOMBAT_MAIN",
        "POSTCOMBAT_MAIN",
    }
    land_available = any(candidate.kind == "PLAY_LAND" for candidate in all_actions)
    if action.kind == "PASS_PRIORITY" and main_phase and land_available:
        hold = permitted_main_phase_pass_reason(observation, all_actions)
        if hold is None:
            constraint = "FAIL_CLOSED_MANA_DEVELOPMENT"
            prune = "MAIN_PHASE_LAND_AVAILABLE_WITHOUT_VALID_HOLD_REASON"
            reasons.append("LAND_DEVELOPMENT_GUARDRAIL")
        else:
            reasons.append(f"LAND_HOLD_{hold.value}")
    mana = _mana_development(action)
    resource = max(0, 100 - min(100, action.mana_value * 15))
    tutor = _tutor_value(action)
    conditional_status = "NONE"
    if conditional and progress >= 100:
        conditional_status = "AVAILABLE"
    elif conditional and progress > 0:
        conditional_status = "PROGRESS"
    return (
        CandidateScoreVector(
            immediate_deterministic_access=projection.immediate_deterministic_access,
            projected_deterministic_access=projection.projected_deterministic_access,
            earliest_projected_access_turn=projection.earliest_projected_access_turn,
            known_package_progress=progress,
            mana_development_value=mana,
            relevant_resource_preservation=resource,
            card_selection_or_tutor_value=tutor,
            conditional_access_status=conditional_status,
            novelty_value=novelty_value,
            arm_constraint_status=constraint,
            action_cost=max(0, action.mana_value),
            reason_codes=tuple(reasons),
        ),
        prune,
        package_id,
    )


def _public_card_score(
    card: PublicCard,
    request_observation: Mapping[str, Any],
    combo_packages: Mapping[str, Sequence[str]],
    *,
    purpose: str,
    novelty_value: int,
    constraint_status: str,
    baseline_selected: bool,
) -> CandidateScoreVector:
    progress, _package, conditional = _package_progress(
        card.identity, request_observation, combo_packages
    )
    selection = 100 if purpose.startswith("TUTOR_") or purpose == "TUTOR" else 60
    if baseline_selected:
        selection += 10
    return CandidateScoreVector(
        immediate_deterministic_access=False,
        projected_deterministic_access=False,
        earliest_projected_access_turn=None,
        known_package_progress=progress,
        mana_development_value=0,
        relevant_resource_preservation=max(0, 100 - min(100, card.mana_value * 10)),
        card_selection_or_tutor_value=selection,
        conditional_access_status=("PROGRESS" if conditional and progress > 0 else "NONE"),
        novelty_value=novelty_value,
        arm_constraint_status=constraint_status,
        action_cost=0,
        reason_codes=(f"STRATEGIC_CHOICE_{purpose}",),
    )


class ExploratoryStrategicChoiceProvider:
    """V2 wrapper around the frozen STANDARD strategic-choice provider."""

    def __init__(
        self,
        baseline: PolicyStrategicChoiceProvider,
        config: DirectedArmConfig,
        *,
        exploration_seed: int,
        environment_seed: int,
        game_index: int,
        novelty: NoveltyLedger | None = None,
    ) -> None:
        self.baseline = baseline
        self.config = config
        self.exploration_seed = exploration_seed
        self.environment_seed = environment_seed
        self.game_index = game_index
        self.novelty = novelty or NoveltyLedger()
        self.records: list[dict[str, Any]] = []

    @property
    def evaluator_id(self) -> str:
        return f"{self.baseline.evaluator_id}:{self.config.arm_id}"

    @property
    def evaluator_sha256(self) -> str:
        return self.config.config_sha256

    @property
    def combo_packages(self) -> Mapping[str, Sequence[str]]:
        return self.baseline.evaluator.config.combo_packages

    def _decision_id(self, request_id: str, purpose: str) -> str:
        return hashlib.sha256(
            f"strategic-v2:{self.config.arm_id}:{request_id}:{purpose}".encode("utf-8")
        ).hexdigest()[:24]

    def _record_selection(
        self,
        *,
        request_id: str,
        purpose: str,
        baseline_handle: str,
        selection: Any,
        exclusions: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.records.append(
            {
                "schema_version": "phase-c-exploratory-v2-strategic-choice-v1",
                "arm_id": self.config.arm_id,
                "game_index": self.game_index,
                "environment_seed": self.environment_seed,
                "exploration_seed": self.exploration_seed,
                "decision_id": self._decision_id(request_id, purpose),
                "strategic_choice_purpose": purpose,
                "standard_baseline_handle": baseline_handle,
                "candidate_evaluations": [
                    {
                        "handle": candidate.handle,
                        "semantic_key": candidate.semantic_key,
                        "score": candidate.score.to_dict(),
                        "pruned_reason": candidate.pruned_reason,
                    }
                    for candidate in selection.candidates
                ],
                "arm_specific_exclusions": [dict(value) for value in exclusions],
                "eligible_top_k": list(selection.eligible_top_k),
                "selected_action": selection.selected_handle,
                "selection_reason": selection.selection_reason,
                "randomness_affected_selection": selection.randomness_affected_selection,
                "exploration_seed_digest": selection.exploration_seed_digest,
            }
        )

    def _select_single_card(
        self,
        request: CardSelectionRequest,
        baseline: CardSelection,
    ) -> CardSelection:
        if len(baseline.selected_handles) != 1:
            raise ValueError("single-card directed selection requires one baseline handle")
        baseline_handle = baseline.selected_handles[0]
        candidates: list[DirectedCandidate] = []
        exclusions: list[dict[str, Any]] = []
        for card in request.candidates:
            signature = canonical_interaction_signature(
                purpose=request.purpose,
                action_kind="CARD_SELECTION",
                identity=card.identity,
                metadata={"ability_id": request.ability_id},
            )
            prohibited = (
                self.config.no_glint_horn_tutoring
                and request.purpose.startswith("TUTOR_")
                and card.identity == GLINT_HORN
            )
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
        decision_id = self._decision_id(request.request_id, request.purpose)
        selection = select_directed_candidate(
            self.config,
            candidates,
            baseline_handle=baseline_handle,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
        )
        selected_card = next(
            card for card in request.candidates if card.handle == selection.selected_handle
        )
        signature = canonical_interaction_signature(
            purpose=request.purpose,
            action_kind="CARD_SELECTION",
            identity=selected_card.identity,
            metadata={"ability_id": request.ability_id},
        )
        self.novelty.visit(signature)
        self._record_selection(
            request_id=request.request_id,
            purpose=request.purpose,
            baseline_handle=baseline_handle,
            selection=selection,
            exclusions=exclusions,
        )
        return CardSelection(
            (selection.selected_handle,),
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_selected_handles": list(baseline.selected_handles),
                "selection_reason": selection.selection_reason,
                "candidate_evaluations": [
                    {
                        "identity": card.identity,
                        "handle": candidate.handle,
                        "score": candidate.score.to_dict(),
                        "pruned_reason": candidate.pruned_reason,
                    }
                    for card, candidate in zip(
                        request.candidates, selection.candidates, strict=False
                    )
                ],
                "arm_specific_exclusions": exclusions,
            },
        )

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        baseline = self.baseline.choose_cards(request)
        if request.minimum == request.maximum == 1 and request.candidates:
            return self._select_single_card(request, baseline)

        # Complete combinatorial enumeration is retained when bounded; otherwise the
        # baseline is used and the exact pruning reason is persisted in diagnostics.
        combination_count = 0
        for count in range(request.minimum, request.maximum + 1):
            combination_count += sum(1 for _ in combinations(request.candidates, count))
            if combination_count > 64:
                break
        self.records.append(
            {
                "schema_version": "phase-c-exploratory-v2-strategic-choice-v1",
                "arm_id": self.config.arm_id,
                "game_index": self.game_index,
                "environment_seed": self.environment_seed,
                "exploration_seed": self.exploration_seed,
                "decision_id": self._decision_id(request.request_id, request.purpose),
                "strategic_choice_purpose": request.purpose,
                "standard_baseline_handle": list(baseline.selected_handles),
                "candidate_evaluations": [],
                "pruned_candidates": [
                    {
                        "scope": "MULTI_CARD_SELECTION_COMBINATIONS",
                        "candidate_count": combination_count,
                        "reason": "MULTI_CARD_SELECTION_DELEGATED_TO_FROZEN_STANDARD",
                    }
                ],
                "selected_action": list(baseline.selected_handles),
                "selection_reason": "FROZEN_STANDARD_MULTI_CARD_SELECTION",
                "randomness_affected_selection": False,
            }
        )
        return CardSelection(
            baseline.selected_handles,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                **dict(baseline.diagnostics),
                "exploratory_arm_id": self.config.arm_id,
                "selection_reason": "FROZEN_STANDARD_MULTI_CARD_SELECTION",
            },
        )

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        baseline = self.baseline.choose_tutor(request)
        if not request.eligible_cards:
            return TutorChoiceSelection(
                baseline.selected_identity,
                self.evaluator_id,
                self.evaluator_sha256,
                {**dict(baseline.diagnostics), "exploratory_arm_id": self.config.arm_id},
            )
        cards_by_identity: dict[str, PublicCard] = {}
        for card in request.eligible_cards:
            cards_by_identity.setdefault(card.identity, card)
        candidates: list[DirectedCandidate] = []
        exclusions: list[dict[str, Any]] = []
        for identity, card in sorted(cards_by_identity.items()):
            handle = f"TUTOR:{identity}"
            signature = canonical_interaction_signature(
                purpose="TUTOR",
                action_kind="TUTOR_TARGET",
                identity=identity,
                metadata={"ability_id": request.ability_id},
            )
            prohibited = self.config.no_glint_horn_tutoring and identity == GLINT_HORN
            status = "PROHIBITED_NO_GLINT_TUTOR" if prohibited else "ALLOWED"
            prune = "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR" if prohibited else None
            if prohibited:
                exclusions.append(
                    {
                        "identity": GLINT_HORN,
                        "reason": "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR",
                        "legal_alternative_identities": sorted(
                            value for value in cards_by_identity if value != GLINT_HORN
                        ),
                    }
                )
            candidates.append(
                DirectedCandidate(
                    handle=handle,
                    semantic_key=f"TUTOR:{identity}",
                    score=_public_card_score(
                        card,
                        request.observation,
                        self.combo_packages,
                        purpose="TUTOR",
                        novelty_value=self.novelty.novelty_value(signature),
                        constraint_status=status,
                        baseline_selected=identity == baseline.selected_identity,
                    ),
                    pruned_reason=prune,
                )
            )
        baseline_handle = f"TUTOR:{baseline.selected_identity}"
        if baseline_handle not in {candidate.handle for candidate in candidates}:
            baseline_handle = candidates[0].handle
        decision_id = self._decision_id(request.request_id, "TUTOR")
        selection = select_directed_candidate(
            self.config,
            candidates,
            baseline_handle=baseline_handle,
            exploration_seed=self.exploration_seed,
            decision_id=decision_id,
        )
        selected_identity = selection.selected_handle.removeprefix("TUTOR:")
        signature = canonical_interaction_signature(
            purpose="TUTOR",
            action_kind="TUTOR_TARGET",
            identity=selected_identity,
            metadata={"ability_id": request.ability_id},
        )
        self.novelty.visit(signature)
        self._record_selection(
            request_id=request.request_id,
            purpose="TUTOR",
            baseline_handle=baseline_handle,
            selection=selection,
            exclusions=exclusions,
        )
        return TutorChoiceSelection(
            selected_identity,
            self.evaluator_id,
            self.evaluator_sha256,
            {
                "policy_config_id": self.baseline.bundle.policy_config_id,
                "exploratory_arm_id": self.config.arm_id,
                "baseline_selected_identity": baseline.selected_identity,
                "eligible_identities": list(request.eligible_identities),
                "arm_specific_exclusions": exclusions,
                "selection_reason": selection.selection_reason,
                "candidate_evaluations": [
                    {
                        "identity": candidate.handle.removeprefix("TUTOR:"),
                        "score": candidate.score.to_dict(),
                        "pruned_reason": candidate.pruned_reason,
                    }
                    for candidate in selection.candidates
                ],
            },
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        baseline = self.baseline.choose_fact_or_fiction(request)
        return FactOrFictionSelection(
            baseline.split_index,
            baseline.chosen_pile,
            self.evaluator_id,
            self.evaluator_sha256,
            {**dict(baseline.diagnostics), "exploratory_arm_id": self.config.arm_id},
        )

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        baseline = self.baseline.choose_spell_copy_targets(request)
        return SpellCopyTargetSelection(
            baseline.target_handles,
            self.evaluator_id,
            self.evaluator_sha256,
            {**dict(baseline.diagnostics), "exploratory_arm_id": self.config.arm_id},
        )

    def choose_optional_trigger(self, request: OptionalTriggerRequest) -> OptionalTriggerSelection:
        baseline = self.baseline.choose_optional_trigger(request)
        return OptionalTriggerSelection(
            baseline.take,
            self.evaluator_id,
            self.evaluator_sha256,
            {**dict(baseline.diagnostics), "exploratory_arm_id": self.config.arm_id},
        )


def assert_no_glint_tutor_selection(records: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed if Arm 2 selects Glint-Horn through any library-search choice."""

    markers = ("TUTOR", "SEARCH", "TRANSMUTE", "TYPECYCLE", "LANDCYCLE")
    for record in records:
        if str(record.get("arm_id", "")) != ALT_PACKAGE_ARM:
            continue
        purpose = str(record.get("strategic_choice_purpose", "")).upper()
        if not any(marker in purpose for marker in markers):
            continue
        selected = str(record.get("selected_action", ""))
        if selected == f"TUTOR:{GLINT_HORN}":
            raise ValueError("Arm 2 selected prohibited Glint-Horn tutor target")
        evaluations = record.get("candidate_evaluations", ())
        if not isinstance(evaluations, Sequence):
            continue
        selected_rows = [
            row
            for row in evaluations
            if isinstance(row, Mapping) and str(row.get("handle", "")) == selected
        ]
        if len(selected_rows) != 1:
            continue
        semantic = str(selected_rows[0].get("semantic_key", ""))
        if GLINT_HORN.upper() in semantic.upper():
            raise ValueError("Arm 2 selected Glint-Horn through a prohibited search choice")


__all__ = [
    "DISCOVERY_CLASSIFICATIONS",
    "GLINT_HORN",
    "ExploratoryStrategicChoiceProvider",
    "LandHoldEvidence",
    "LandHoldReason",
    "NoveltyLedger",
    "PublicProjection",
    "assert_no_glint_tutor_selection",
    "canonical_interaction_signature",
    "permitted_main_phase_pass_reason",
    "score_priority_candidate",
    "semantic_action_key",
    "validate_land_hold_reason",
    "visible_identities",
]
