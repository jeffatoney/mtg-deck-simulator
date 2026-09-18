"""Class-level Stage 3 choice-authority matrix for live, explicit, and replay sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import ReplayError, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.serialization import state_to_data
from mtg_kernel.strategic_choices import (
    CardSelection,
    CardSelectionRequest,
    CounterPaymentRequest,
    CounterPaymentSelection,
    RecordedStrategicChoiceProvider,
    TutorChoiceRequest,
    TutorChoiceSelection,
)

PLAYERS = ("P0", "P1", "P2", "P3")
MANA_SYMBOLS = ("W", "U", "B", "R", "G", "C")
REPO_ROOT = Path(__file__).resolve().parents[2]
CROSS_PLAYER_EXPLICIT_INGRESS = (
    REPO_ROOT / "src/mtg_kernel/phase_b_runtime_effects_prismari.py",
    REPO_ROOT / "src/mtg_kernel/phase_b_runtime_effects_demolition.py",
    REPO_ROOT / "src/mtg_kernel/phase_b_runtime_effects_interaction.py",
)


@dataclass
class _RecordingProvider:
    tutor_by_owner: dict[str, str] = field(default_factory=dict)
    discard_names: tuple[str, ...] = ()
    counter_outcome: str = "DECLINE"
    calls: list[tuple[str, str]] = field(default_factory=list)
    counter_requests: list[CounterPaymentRequest] = field(default_factory=list)

    def choose_counter_payment(self, request: CounterPaymentRequest) -> CounterPaymentSelection:
        self.calls.append(("counter", request.actor_id))
        self.counter_requests.append(request)
        selected = (
            self.counter_outcome if self.counter_outcome in request.legal_outcomes else "DECLINE"
        )
        return CounterPaymentSelection(
            selected,
            "stage3-authority-test",
            "1" * 64,
            {"reason_code": f"STAGE3_AUTHORITY_{selected}"},
        )

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        self.calls.append(("cards", request.actor_id))
        selected: list[str] = []
        remaining = list(self.discard_names)
        for identity in remaining:
            match = next(
                (
                    card
                    for card in request.candidates
                    if card.identity == identity and card.handle not in selected
                ),
                None,
            )
            if match is None:
                raise AssertionError(f"test provider could not find {identity}")
            selected.append(match.handle)
        return CardSelection(
            tuple(selected),
            "stage3-authority-test",
            "1" * 64,
            {"purpose": request.purpose},
        )

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        self.calls.append(("tutor", request.actor_id))
        return TutorChoiceSelection(
            self.tutor_by_owner.get(request.actor_id, "FAIL_TO_FIND"),
            "stage3-authority-test",
            "1" * 64,
            {"actor_id": request.actor_id},
        )


def _specs() -> dict[str, object]:
    return {spec.name: spec for spec in load_full_deck_specs().values()}


def _pass_until_resolution(executor: object) -> None:
    in_game = [player_id for player_id in PLAYERS if executor.state.players[player_id].in_game]
    for _ in in_game[:-1]:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _resolve_one_stack_object(executor: object) -> None:
    for _ in PLAYERS:
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)


def _assert_unmodeled_resolution(executor: object, spy: _RecordingProvider, state: object) -> None:
    _pass_until_resolution(executor)
    before = _snapshot(state)
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)
    assert spy.calls == []
    assert _snapshot(state) == before


def _snapshot(state: object) -> tuple[str, int, dict[str, dict[str, int]], int]:
    return (
        state_hash(state),
        len(state.choices),
        {player_id: dict(player.mana_pool) for player_id, player in state.players.items()},
        len(state.events),
    )


def _fund_table(seed: str) -> tuple[object, object, dict[str, object]]:
    state, executor = new_game(PLAYERS, seed)
    state.turn.phase = "PRECOMBAT_MAIN"
    for player in state.players.values():
        player.mana_pool.update({symbol: 0 for symbol in MANA_SYMBOLS})
        player.mana_pool["U"] = 4
        player.mana_pool["R"] = 4
        player.mana_pool["C"] = 4
    return state, executor, _specs()


def _unbound_live_provider(executor: object, provider: _RecordingProvider) -> None:
    executor.strategic_choice_provider = provider
    executor.strategic_choice_binding = None
    executor.replaying = False
    assert executor.controlled_player_id is None


def test_live_unbound_provider_cannot_decide_counter_or_search() -> None:
    state, executor, specs = _fund_table("stage3-unbound-live-counter")
    spy = _RecordingProvider(counter_outcome="PAY")
    _unbound_live_provider(executor, spy)
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.turn.priority_holder_id = "P1"
    target = executor.cast("P1", opt.object_id, choices={"scry_to_bottom": False})
    state.turn.priority_holder_id = "P0"
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    _assert_unmodeled_resolution(executor, spy, state)

    state, executor, specs = _fund_table("stage3-unbound-live-search")
    spy = _RecordingProvider(tutor_by_owner={"P0": "Mountain", "P1": "Island"})
    _unbound_live_provider(executor, spy)
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Mountain"], Zone.LIBRARY, owner="P0")
    executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
    )
    _pass_until_resolution(executor)
    before = _snapshot(state)
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        holder = executor.state.turn.priority_holder_id
        assert holder is not None
        executor.pass_priority(holder)
    assert spy.calls == []
    assert _snapshot(state) == before
    assert target.zone is Zone.BATTLEFIELD


def test_bound_provider_may_decide_only_for_its_owner() -> None:
    state, executor, specs = _fund_table("stage3-bound-owner-ok")
    spy = _RecordingProvider(counter_outcome="DECLINE")
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    _resolve_one_stack_object(executor)
    assert spy.calls == [("counter", "P0")]

    state, executor, specs = _fund_table("stage3-bound-owner-blocked")
    spy = _RecordingProvider(counter_outcome="PAY")
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P1")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.turn.priority_holder_id = "P1"
    target = executor.cast("P1", opt.object_id, choices={"scry_to_bottom": False})
    state.turn.priority_holder_id = "P0"
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
    assert spy.calls == []

    state, executor, specs = _fund_table("stage3-bound-owner-p2-blocked")
    spy = _RecordingProvider(counter_outcome="PAY")
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P2")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.turn.priority_holder_id = "P2"
    target = executor.cast("P2", opt.object_id, choices={"scry_to_bottom": False})
    state.turn.priority_holder_id = "P0"
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
    assert spy.calls == []


def test_recorded_replay_round_trips_and_rejects_wrong_owner() -> None:
    state, executor, specs = _fund_table("stage3-replay-authority")
    spy = _RecordingProvider(counter_outcome="DECLINE")
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    executor.opponent_mana_profile = "no_known_colors"
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    state.replay_initial_state = state_to_data(state)
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    _resolve_one_stack_object(executor)
    body = transcript(state, seed=executor.seed)
    replayed = validate_replay(body)
    assert state_hash(replayed) == state_hash(state)

    request = spy.counter_requests[0]
    recorded = RecordedStrategicChoiceProvider(
        [
            {
                "kind": "COUNTER_UNLESS_PAY",
                "selected": {
                    "schema_version": "counter-payment-choice-v4",
                    "decision_source": "STRATEGIC_PROVIDER",
                    "decision_owner": "P2",
                    "effect_kind": request.effect_kind,
                    "target_identity": request.target.identity,
                    "amount": request.payment_amount,
                    "actual_required_payment": request.payment_amount,
                    "counter_destination": "GRAVEYARD",
                    "outcome": "DECLINE",
                    "evaluator_id": "recorded-test",
                    "evaluator_sha256": "3" * 64,
                    "diagnostics": {},
                },
            }
        ]
    )
    with pytest.raises(ReplayError, match="recorded counter-payment actor differs"):
        recorded.choose_counter_payment(request)


def test_replay_mode_does_not_authorize_unbound_live_provider() -> None:
    _state, executor, specs = _fund_table("stage3-replay-live-spy")
    spy = _RecordingProvider(counter_outcome="DECLINE")
    _unbound_live_provider(executor, spy)
    executor.replaying = True
    opt = add_card(executor, specs["Opt"], Zone.HAND, owner="P0")
    pierce = add_card(executor, specs["Spell Pierce"], Zone.HAND, owner="P0")
    target = executor.cast("P0", opt.object_id, choices={"scry_to_bottom": False})
    executor.cast("P0", pierce.object_id, targets=(TargetRef(target.object_id),))
    with pytest.raises(UnsupportedCapability, match="unmodeled opponent"):
        _resolve_one_stack_object(executor)
    assert spy.calls == []


def test_explicit_self_prismari_discard_and_demolition_search_remain_valid() -> None:
    state, executor, specs = _fund_table("stage3-explicit-self-prismari")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P0")
    add_card(executor, specs["Island"], Zone.HAND, owner="P0")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P0")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P0")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P0"},
                "CREATE_TREASURE": {"player_id": "P0"},
            },
            "prismari_discard": {"P0": ["Mountain", "Island"]},
        },
    )
    _resolve_one_stack_object(executor)
    discard = next(
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION" and choice.selected["purpose"] == "PRISMARI_DISCARD"
    )
    assert discard.player_id == "P0"
    assert discard.selected["evaluator_id"] == "explicit-rules-choice"

    state, executor, specs = _fund_table("stage3-explicit-self-demolition")
    spy = _RecordingProvider(tutor_by_owner={"P1": "FAIL_TO_FIND"})
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P1")
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Mountain"], Zone.LIBRARY, owner="P0")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
        choices={"library_search": {"P0": "Mountain"}},
    )
    _resolve_one_stack_object(executor)
    searches = [choice for choice in state.choices if choice.kind == "FETCH_BASIC"]
    assert [choice.player_id for choice in searches] == ["P1", "P0"]
    assert [choice.selected["identity"] for choice in searches] == ["FAIL_TO_FIND", "Mountain"]
    assert spy.calls == [("tutor", "P1")]


def test_explicit_opponent_choice_is_rejected_and_does_not_bypass_provider() -> None:
    state, executor, specs = _fund_table("stage3-explicit-p1-prismari")
    spy = _RecordingProvider(discard_names=("Mountain", "Island"))
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P1")
    add_card(executor, specs["Island"], Zone.HAND, owner="P1")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P1")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P1"},
                "CREATE_TREASURE": {"player_id": "P1"},
            },
            "prismari_discard": {"P1": ["Mountain", "Island"]},
        },
    )
    _assert_unmodeled_resolution(executor, spy, state)

    state, executor, specs = _fund_table("stage3-explicit-p1-demolition")
    spy = _RecordingProvider(tutor_by_owner={"P0": "Mountain", "P1": "Island"})
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P0")
    field = add_card(executor, specs["Demolition Field"], Zone.BATTLEFIELD, owner="P0")
    target = add_card(executor, specs["Thriving Isle"], Zone.BATTLEFIELD, owner="P1")
    add_card(executor, specs["Island"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Mountain"], Zone.LIBRARY, owner="P0")
    executor.activate(
        "P0",
        field.object_id,
        "demolition-field:destroy",
        targets=(TargetRef(target.object_id),),
        choices={"library_search": {"P1": "Island", "P0": "Mountain"}},
    )
    _assert_unmodeled_resolution(executor, spy, state)
    assert target.zone is Zone.BATTLEFIELD


def test_authorized_opponent_provider_may_choose_for_that_owner() -> None:
    state, executor, specs = _fund_table("stage3-authorized-p1-prismari")
    spy = _RecordingProvider(discard_names=("Mountain", "Island"))
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P1")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P1")
    add_card(executor, specs["Island"], Zone.HAND, owner="P1")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P1")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P1")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P1"},
                "CREATE_TREASURE": {"player_id": "P1"},
            },
            "prismari_discard": {"P1": ["Opt", "Sol Ring"]},
        },
    )
    _resolve_one_stack_object(executor)
    assert spy.calls == [("cards", "P1")]
    discard = next(
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION" and choice.selected["purpose"] == "PRISMARI_DISCARD"
    )
    assert discard.player_id == "P1"
    assert discard.selected["evaluator_id"] == "stage3-authority-test"


def test_third_player_matrix_follows_decision_owner_not_actor_vs_opponent() -> None:
    state, executor, specs = _fund_table("stage3-p2-prismari-authorized")
    spy = _RecordingProvider(discard_names=("Mountain", "Island"))
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P2")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P2")
    add_card(executor, specs["Island"], Zone.HAND, owner="P2")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P2")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P2")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P2"},
                "CREATE_TREASURE": {"player_id": "P2"},
            },
            "prismari_discard": {"P2": ["Mountain", "Island"]},
        },
    )
    _resolve_one_stack_object(executor)
    assert spy.calls == [("cards", "P2")]

    state, executor, specs = _fund_table("stage3-p2-prismari-blocked")
    spy = _RecordingProvider(discard_names=("Mountain", "Island"))
    executor.bind_strategic_choice_provider(spy, controlled_player_id="P1")
    add_card(executor, specs["Mountain"], Zone.HAND, owner="P2")
    add_card(executor, specs["Island"], Zone.HAND, owner="P2")
    add_card(executor, specs["Opt"], Zone.LIBRARY, owner="P2")
    add_card(executor, specs["Sol Ring"], Zone.LIBRARY, owner="P2")
    command = add_card(executor, specs["Prismari Command"], Zone.HAND, owner="P0")
    executor.cast(
        "P0",
        command.object_id,
        choices={
            "prismari_modes": ["CREATE_TREASURE", "DRAW_DISCARD"],
            "prismari_targets": {
                "DRAW_DISCARD": {"player_id": "P2"},
                "CREATE_TREASURE": {"player_id": "P2"},
            },
            "prismari_discard": {"P2": ["Mountain", "Island"]},
        },
    )
    _assert_unmodeled_resolution(executor, spy, state)


def test_cross_player_explicit_ingresses_use_shared_authority_helper() -> None:
    for path in CROSS_PLAYER_EXPLICIT_INGRESS:
        source = path.read_text(encoding="utf-8")
        assert "explicit_action_choice_is_authorized" in source
        assert "require_executor_authorized_provider" in source
        assert "decision_owner_id=" in source
