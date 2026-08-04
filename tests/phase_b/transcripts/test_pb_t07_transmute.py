from mtg_deck import build_exact_game
from mtg_kernel.models import Zone
from mtg_kernel.strategic_choices import (
    FactOrFictionRequest,
    FactOrFictionSelection,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy import ActionBroker, PolicyStrategicChoiceProvider
from mtg_verify.transcript_evidence import record_game_state_evidence
from tests.phase_b.transcripts.support import PLAYERS, move_named, pass_round, provider


class RecordingTutorProvider:
    def __init__(
        self,
        base: PolicyStrategicChoiceProvider,
        selected_identity: str,
    ) -> None:
        self.base = base
        self.selected_identity = selected_identity
        self.requests: list[TutorChoiceRequest] = []

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        self.requests.append(request)
        return TutorChoiceSelection(
            self.selected_identity,
            self.base.evaluator_id,
            self.base.evaluator_sha256,
            {
                "test_override": True,
                "eligible_identities": list(request.eligible_identities),
            },
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        return self.base.choose_fact_or_fiction(request)

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        return self.base.choose_spell_copy_targets(request)


def _prepare_transmute(seed: str, selected_identity: str):
    state, executor, created = build_exact_game(seed, PLAYERS)
    library = list(created["library"])
    dizzy = move_named(executor, library, "Dizzy Spell", Zone.HAND)
    base = provider()
    recording = RecordingTutorProvider(base, selected_identity)
    executor.bind_strategic_choice_provider(recording)
    state.turn.phase = "PRECOMBAT_MAIN"
    state.players["P0"].mana_pool.update({symbol: 0 for symbol in state.players["P0"].mana_pool})
    state.players["P0"].mana_pool["U"] = 2
    state.players["P0"].mana_pool["C"] = 1
    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    action = next(
        item for item in actions if item.kind == "ACTIVATE_HAND" and item.identity == "Dizzy Spell"
    )
    assert action.metadata["choice_timing"] == "RESOLUTION"
    broker.execute(int(observation["generation"]), action.handle)
    assert not any(choice.kind == "TRANSMUTE" for choice in state.choices)
    pass_round(executor)
    return state, dizzy, base, recording


def test_pb_t07_transmute_resolution_evidence() -> None:
    state, dizzy, base, recording = _prepare_transmute("golden-t07", "Sol Ring")
    assert len(recording.requests) == 1
    request = recording.requests[0]
    assert request.eligible_cards
    assert all(card.mana_value == 1 for card in request.eligible_cards)
    assert "Sol Ring" in request.eligible_identities
    assert "Twinflame" not in request.eligible_identities

    rings = [
        obj
        for obj in state.objects.values()
        if not obj.retired
        and obj.zone is Zone.HAND
        and obj.current_characteristics.get("name") == "Sol Ring"
    ]
    assert len(rings) == 1
    choice = next(item for item in state.choices if item.kind == "TRANSMUTE")
    assert choice.selected["identity"] == "Sol Ring"
    assert choice.selected["chosen_at"] == "RESOLUTION"
    assert choice.selected["evaluator_id"] == base.evaluator_id
    assert choice.selected["evaluator_sha256"] == base.evaluator_sha256
    assert len(choice.selected["evaluator_sha256"]) == 64
    assert choice.selected["diagnostics"]["test_override"] is True
    assert dizzy.retired

    fail_state, fail_dizzy, fail_base, fail_recording = _prepare_transmute(
        "golden-t07-fail-to-find",
        "FAIL_TO_FIND",
    )
    assert len(fail_recording.requests) == 1
    fail_choice = next(item for item in fail_state.choices if item.kind == "TRANSMUTE")
    assert fail_choice.selected["identity"] == "FAIL_TO_FIND"
    assert fail_choice.selected["evaluator_id"] == fail_base.evaluator_id
    assert fail_choice.selected["evaluator_sha256"] == fail_base.evaluator_sha256
    assert fail_dizzy.retired
    assert not any(
        obj.zone is Zone.HAND and obj.current_characteristics.get("name") == "Sol Ring"
        for obj in fail_state.objects.values()
        if not obj.retired
    )

    record_game_state_evidence(
        "PB-T07-tutor-one",
        state,
        facts={
            "activation_event_semantics": "ANNOUNCED_AND_STACKED_BEFORE_COST_EVENTS",
            "selected_identity": "Sol Ring",
            "wrong_mana_value_excluded": True,
            "fail_to_find_executed": True,
            "positive_selection_uses_disclosed_test_override": True,
            "evaluator_id": base.evaluator_id,
            "evaluator_sha256": base.evaluator_sha256,
        },
    )
