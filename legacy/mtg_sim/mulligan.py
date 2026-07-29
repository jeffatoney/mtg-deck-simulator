"""League mulligan procedure using paired deterministic shuffle schedules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mtg_sim.domain import CardInstanceId, DomainError, GameState, Zone
from mtg_sim.rng import ScenarioSeed, paired_shuffle_schedule

HAND_SIZES = (7, 7, 6, 5, 4)


class MulliganPolicy(Protocol):
    def keep(
        self, visible_hand: tuple[CardInstanceId, ...], hand_size: int, round_index: int
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class MulliganResult:
    kept_round: int
    opening_hand_size: int
    events: tuple[str, ...]


def perform_league_mulligan(
    state: GameState, seed: ScenarioSeed, policy: MulliganPolicy, *, game_index: int = 0
) -> MulliganResult:
    events: list[str] = []
    all_library = list(state.zones[Zone.LIBRARY])
    kept_round = len(HAND_SIZES) - 1
    kept_size = 4
    for round_index, hand_size in enumerate(HAND_SIZES):
        schedule = paired_shuffle_schedule(seed, game_index, round_index, all_library)
        visible = tuple(schedule[:hand_size])
        events.append(f"candidate:{round_index}:{hand_size}:" + ",".join(c.value for c in visible))
        if round_index == len(HAND_SIZES) - 1 or policy.keep(visible, hand_size, round_index):
            kept_round = round_index
            kept_size = hand_size
            state.zones[Zone.LIBRARY] = list(schedule[hand_size:])
            state.zones[Zone.HAND] = list(visible)
            break
    if len(state.zones[Zone.HAND]) != kept_size:
        raise DomainError("mulligan failed to set kept hand")
    if kept_size < 7:
        refill = seed.shuffled(
            state.zones[Zone.LIBRARY], "mulligan_shuffle", "refill", game_index, kept_round
        )
        needed = 7 - kept_size
        state.zones[Zone.HAND].extend(refill[:needed])
        state.zones[Zone.LIBRARY] = refill[needed:]
        events.append(f"refill:{needed}")
    state.validate_invariants()
    return MulliganResult(kept_round, kept_size, tuple(events))
