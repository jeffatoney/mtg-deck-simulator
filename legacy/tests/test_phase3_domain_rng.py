from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mtg_sim.domain import DomainError, TerminalStatus, Zone, new_game
from mtg_sim.mulligan import perform_league_mulligan
from mtg_sim.replay import event_log_hash, replay_events
from mtg_sim.rng import ScenarioSeed, deterministic_fixture, paired_shuffle_schedule

DECK = [f"Card {i}" for i in range(20)]


class KeepAt:
    def __init__(self, round_to_keep: int) -> None:
        self.round_to_keep = round_to_keep
        self.seen: list[tuple[str, ...]] = []

    def keep(self, visible_hand, hand_size: int, round_index: int) -> bool:  # noqa: ANN001
        assert hand_size == len(visible_hand)
        self.seen.append(tuple(card.value for card in visible_hand))
        return round_index == self.round_to_keep


def test_unique_card_instances_for_physical_cards_and_commanders() -> None:
    state = new_game(["Island", "Island", "Mountain"])
    assert len(state.cards) == 5
    assert len({cid.value for cid in state.cards}) == 5
    assert [state.cards[cid].name for cid in state.zones[Zone.LIBRARY]].count("Island") == 2


def test_replaying_same_seed_produces_same_state_and_events() -> None:
    shuffled = ScenarioSeed(123).shuffled(DECK, "library_shuffle", 0)
    state = new_game(DECK, library_order=shuffled)
    card = state.zones[Zone.LIBRARY][0]
    state.move_card(card, Zone.LIBRARY, Zone.HAND, "fixture draw")
    state.terminate(TerminalStatus.WON, "fixture")

    replayed = replay_events(new_game(DECK, library_order=shuffled), state.events)
    assert replayed.state_hash() == state.state_hash()
    assert event_log_hash(replayed.events) == event_log_hash(state.events)


def test_worker_count_does_not_change_deterministic_fixtures() -> None:
    one_worker = [deterministic_fixture(99, 1, i, DECK) for i in range(5)]
    four_workers = [deterministic_fixture(99, 4, i, DECK) for i in range(5)]
    assert one_worker == four_workers


def test_standard_and_exploratory_games_receive_paired_mulligan_randomness() -> None:
    seed = ScenarioSeed(456)
    assert paired_shuffle_schedule(seed, 7, 2, DECK) == paired_shuffle_schedule(seed, 7, 2, DECK)
    assert paired_shuffle_schedule(seed, 7, 2, DECK) != paired_shuffle_schedule(seed, 7, 3, DECK)


def test_league_mulligan_refill_is_hidden_until_after_keep() -> None:
    state = new_game(DECK)
    policy = KeepAt(2)
    result = perform_league_mulligan(state, ScenarioSeed(777), policy)
    assert result.opening_hand_size == 6
    assert result.kept_round == 2
    assert len(state.zones[Zone.HAND]) == 7
    assert [len(seen) for seen in policy.seen] == [7, 7, 6]
    assert all("refill" not in card for seen in policy.seen for card in seen)


def test_observation_cannot_access_future_library_order_or_rng() -> None:
    state = new_game(DECK)
    obs = state.observation()
    assert obs.library_size == len(DECK)
    assert obs.known_top_library == ()
    assert not hasattr(obs, "library")
    assert not hasattr(obs, "rng")
    with pytest.raises(FrozenInstanceError):
        obs.turn = 99  # type: ignore[misc]


def test_no_action_occurs_after_game_termination() -> None:
    state = new_game(DECK)
    state.terminate(TerminalStatus.WON, "fixture")
    with pytest.raises(DomainError):
        state.move_card(state.zones[Zone.LIBRARY][0], Zone.LIBRARY, Zone.HAND, "illegal")
    assert len(state.events) == 1


@given(st.permutations(DECK[:8]))
def test_all_physical_cards_are_conserved_across_zones(order: tuple[str, ...]) -> None:
    state = new_game(order)
    for _ in range(3):
        state.move_card(state.zones[Zone.LIBRARY][0], Zone.LIBRARY, Zone.HAND, "draw")
    state.move_card(state.zones[Zone.HAND][0], Zone.HAND, Zone.GRAVEYARD, "discard")
    state.move_card(state.zones[Zone.HAND][0], Zone.HAND, Zone.EXILE, "exile fixture")
    state.validate_invariants()
    all_zone_cards = [cid for zone in Zone for cid in state.zones[zone]]
    assert len(all_zone_cards) == len(state.cards)
    assert len(set(all_zone_cards)) == len(state.cards)


def test_replay_rejects_tampered_event_hash() -> None:
    state = new_game(DECK)
    state.move_card(state.zones[Zone.LIBRARY][0], Zone.LIBRARY, Zone.HAND, "fixture draw")
    event = state.events[0]
    tampered = type(event)(event.sequence, event.event_type, event.payload, "bad", event.after_hash)
    with pytest.raises(DomainError):
        replay_events(new_game(DECK), [tampered])
