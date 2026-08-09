"""Kernel-side contracts for injected strategic decisions.

The rules engine owns legality, revelation, and state changes. A provider receives
only an observation-safe request and returns one of the legal choices. Production
policy providers live outside the kernel. Replay uses the recorded provider below
and never imports policy decision code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from mtg_kernel.errors import IllegalAction, ReplayError


@dataclass(frozen=True)
class PublicCard:
    handle: str
    identity: str
    mana_value: int
    card_types: tuple[str, ...]
    effect_kinds: tuple[str, ...]


@dataclass(frozen=True)
class CardSelectionRequest:
    request_id: str
    actor_id: str
    ability_id: str
    purpose: str
    turn_number: int
    observation: Mapping[str, Any]
    candidates: tuple[PublicCard, ...]
    minimum: int
    maximum: int


@dataclass(frozen=True)
class CardSelection:
    selected_handles: tuple[str, ...]
    evaluator_id: str
    evaluator_sha256: str
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class TutorChoiceRequest:
    request_id: str
    actor_id: str
    ability_id: str
    turn_number: int
    observation: Mapping[str, Any]
    eligible_identities: tuple[str, ...]
    eligible_cards: tuple[PublicCard, ...]


@dataclass(frozen=True)
class TutorChoiceSelection:
    selected_identity: str
    evaluator_id: str
    evaluator_sha256: str
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class FactOrFictionSplit:
    split_index: int
    pile_a_handles: tuple[str, ...]
    pile_b_handles: tuple[str, ...]


@dataclass(frozen=True)
class FactOrFictionRequest:
    request_id: str
    actor_id: str
    opponent_id: str
    turn_number: int
    observation: Mapping[str, Any]
    revealed_cards: tuple[PublicCard, ...]
    legal_splits: tuple[FactOrFictionSplit, ...]


@dataclass(frozen=True)
class FactOrFictionSelection:
    split_index: int
    chosen_pile: str
    evaluator_id: str
    evaluator_sha256: str
    diagnostics: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.chosen_pile not in {"A", "B"}:
            raise ValueError("Fact or Fiction chosen pile must be A or B")


@dataclass(frozen=True)
class SpellCopyTargetRequest:
    request_id: str
    actor_id: str
    source_identity: str
    copied_spell_identity: str
    turn_number: int
    observation: Mapping[str, Any]
    original_target_handles: tuple[str, ...]
    legal_targets: tuple[PublicCard, ...]
    legal_target_sets: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class SpellCopyTargetSelection:
    target_handles: tuple[str, ...]
    evaluator_id: str
    evaluator_sha256: str
    diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class OptionalTriggerRequest:
    request_id: str
    actor_id: str
    ability_id: str
    effect_kind: str
    turn_number: int
    observation: Mapping[str, Any]


@dataclass(frozen=True)
class OptionalTriggerSelection:
    take: bool
    evaluator_id: str
    evaluator_sha256: str
    diagnostics: Mapping[str, Any]


class StrategicChoiceProvider(Protocol):
    """Observation-only policy interface called at rules-defined choice times."""

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection: ...

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection: ...

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection: ...

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection: ...

    def choose_optional_trigger(
        self, request: OptionalTriggerRequest
    ) -> OptionalTriggerSelection: ...


class RecordedStrategicChoiceProvider:
    """Replay provider that consumes recorded choices without running policy code."""

    def __init__(self, choices: Sequence[Mapping[str, Any]]) -> None:
        self._card_selections = [
            dict(choice) for choice in choices if str(choice.get("kind")) == "CARD_SELECTION"
        ]
        self._tutors = [
            dict(choice)
            for choice in choices
            if str(choice.get("kind")) in {"FETCH_BASIC", "TRANSMUTE", "TYPECYCLE"}
        ]
        splits = [
            dict(choice) for choice in choices if str(choice.get("kind")) == "FACT_OR_FICTION_SPLIT"
        ]
        piles = [
            dict(choice) for choice in choices if str(choice.get("kind")) == "FACT_OR_FICTION_PILE"
        ]
        if len(splits) != len(piles):
            raise ReplayError("recorded Fact or Fiction split and pile choices differ")
        self._facts = list(zip(splits, piles, strict=True))
        self._copy_targets = [
            dict(choice)
            for choice in choices
            if str(choice.get("kind")) == "COPY_TARGETS"
            and isinstance(choice.get("selected"), Mapping)
            and "target_handles" in choice.get("selected", {})
        ]
        self._optional_triggers = [
            dict(choice)
            for choice in choices
            if str(choice.get("kind")) == "OPTIONAL_TRIGGER"
            and isinstance(choice.get("selected"), Mapping)
        ]

    @staticmethod
    def _metadata(selected: Mapping[str, Any]) -> tuple[str, str, Mapping[str, Any]]:
        evaluator_id = str(selected.get("evaluator_id", "recorded-replay"))
        evaluator_sha = str(selected.get("evaluator_sha256", "0" * 64))
        raw_diagnostics = selected.get("diagnostics", {})
        diagnostics: Mapping[str, Any]
        if isinstance(raw_diagnostics, Mapping):
            diagnostics = raw_diagnostics
        else:
            diagnostics = {}
        return evaluator_id, evaluator_sha, diagnostics

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        if not self._card_selections:
            raise ReplayError("replay transcript omits a recorded card selection")
        recorded = self._card_selections.pop(0)
        selected = recorded.get("selected")
        if not isinstance(selected, Mapping):
            raise ReplayError("recorded card selection is malformed")
        purpose = str(selected.get("purpose", ""))
        if purpose != request.purpose:
            raise ReplayError("recorded card selection purpose differs in replay")
        handles = tuple(str(value) for value in selected.get("selected_handles", ()))
        legal = {card.handle for card in request.candidates}
        if len(handles) != len(set(handles)) or not set(handles) <= legal:
            raise ReplayError("recorded card selection contains an illegal handle")
        if not request.minimum <= len(handles) <= request.maximum:
            raise ReplayError("recorded card selection count is not legal in replay")
        evaluator_id, evaluator_sha, diagnostics = self._metadata(selected)
        return CardSelection(handles, evaluator_id, evaluator_sha, diagnostics)

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        if not self._tutors:
            raise ReplayError("replay transcript omits a recorded tutor choice")
        recorded = self._tutors.pop(0)
        selected = recorded.get("selected")
        if isinstance(selected, Mapping):
            identity = str(selected.get("identity", "FAIL_TO_FIND"))
            evaluator_id, evaluator_sha, diagnostics = self._metadata(selected)
        else:
            identity = str(selected)
            evaluator_id, evaluator_sha, diagnostics = "legacy-recorded", "0" * 64, {}
        if identity != "FAIL_TO_FIND" and identity not in request.eligible_identities:
            raise ReplayError("recorded tutor choice is not eligible in replay")
        return TutorChoiceSelection(identity, evaluator_id, evaluator_sha, diagnostics)

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        if not self._facts:
            raise ReplayError("replay transcript omits a recorded Fact or Fiction choice")
        split_record, pile_record = self._facts.pop(0)
        split_selected = split_record.get("selected")
        pile_selected = pile_record.get("selected")
        if not isinstance(split_selected, Mapping) or not isinstance(pile_selected, Mapping):
            raise ReplayError("recorded Fact or Fiction choice is malformed")
        split_index = int(split_selected.get("split_index", -1))
        chosen_pile = str(pile_selected.get("selected", ""))
        evaluator_id, evaluator_sha, diagnostics = self._metadata(pile_selected)
        if split_index not in {split.split_index for split in request.legal_splits}:
            raise ReplayError("recorded Fact or Fiction split is not legal in replay")
        return FactOrFictionSelection(
            split_index,
            chosen_pile,
            evaluator_id,
            evaluator_sha,
            diagnostics,
        )

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        if not self._copy_targets:
            raise ReplayError("replay transcript omits a recorded copy-target choice")
        recorded = self._copy_targets.pop(0)
        selected = recorded.get("selected")
        diagnostics: Mapping[str, Any]
        if selected == "RETAIN_ORIGINAL_TARGETS":
            handles = request.original_target_handles
            evaluator_id, evaluator_sha, diagnostics = "legacy-recorded", "0" * 64, {}
        elif isinstance(selected, Mapping):
            handles = tuple(str(value) for value in selected.get("target_handles", ()))
            evaluator_id, evaluator_sha, diagnostics = self._metadata(selected)
        else:
            raise ReplayError("recorded copy targets do not use opaque handles")
        if handles != request.original_target_handles and handles not in request.legal_target_sets:
            raise ReplayError("recorded copy target set is not legal in replay")
        return SpellCopyTargetSelection(handles, evaluator_id, evaluator_sha, diagnostics)

    def choose_optional_trigger(self, request: OptionalTriggerRequest) -> OptionalTriggerSelection:
        if not self._optional_triggers:
            raise ReplayError("replay transcript omits a recorded optional-trigger choice")
        recorded = self._optional_triggers.pop(0)
        selected = recorded.get("selected")
        if not isinstance(selected, Mapping):
            raise ReplayError("recorded optional-trigger choice is malformed")
        if str(selected.get("actor_id", "")) != request.actor_id:
            raise ReplayError("recorded optional-trigger actor differs in replay")
        if str(selected.get("ability_id", "")) != request.ability_id:
            raise ReplayError("recorded optional-trigger ability differs in replay")
        if str(selected.get("effect_kind", "")) != request.effect_kind:
            raise ReplayError("recorded optional-trigger effect differs in replay")
        take = selected.get("take")
        if not isinstance(take, bool):
            raise ReplayError("recorded optional-trigger choice omits a boolean decision")
        evaluator_id, evaluator_sha, diagnostics = self._metadata(selected)
        return OptionalTriggerSelection(take, evaluator_id, evaluator_sha, diagnostics)


def require_provider(
    provider: StrategicChoiceProvider | None, purpose: str
) -> StrategicChoiceProvider:
    if provider is None:
        raise IllegalAction(f"{purpose} requires an injected strategic choice provider")
    return provider
