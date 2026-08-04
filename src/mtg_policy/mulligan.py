"""The owner-specified league draw-back-to-seven mulligan procedure."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

LEAGUE_CANDIDATE_HAND_SIZES = (7, 7, 6, 5, 4)
LEGAL_KEEP_SIZES = frozenset({7, 6, 5, 4})
REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE = True


@dataclass(frozen=True)
class LeagueMulliganResult:
    nominal_keep_size: int
    kept_cards: tuple[str, ...]
    refill_cards: tuple[str, ...]
    final_hand: tuple[str, ...]


@dataclass(frozen=True)
class LeagueMulliganProcedureResult:
    presented_hands: tuple[tuple[str, ...], ...]
    rejected_hands: tuple[tuple[str, ...], ...]
    shuffled_libraries: tuple[tuple[str, ...], ...]
    keep_result: LeagueMulliganResult
    remaining_library: tuple[str, ...]

    @property
    def shuffle_count(self) -> int:
        return len(self.shuffled_libraries)


def draw_back_to_seven(
    kept_cards: tuple[str, ...],
    refill_cards: tuple[str, ...],
    *,
    nominal_keep_size: int,
) -> LeagueMulliganResult:
    """Validate a 7/6/5/4 keep and apply the league refill after the keep."""
    if nominal_keep_size not in LEGAL_KEEP_SIZES:
        raise ValueError("league mulligans stop at four")
    if len(kept_cards) != nominal_keep_size:
        raise ValueError("kept-card count does not match the nominal keep size")
    required = 7 - nominal_keep_size
    if len(refill_cards) != required:
        raise ValueError("league refill must draw exactly back to seven")
    final = kept_cards + refill_cards
    if len(final) != 7:
        raise AssertionError("league refill failed to create a seven-card hand")
    return LeagueMulliganResult(nominal_keep_size, kept_cards, refill_cards, final)


def execute_league_mulligan(
    library: tuple[str, ...],
    *,
    keep_attempt: int,
    shuffle: Callable[[tuple[str, ...]], tuple[str, ...]],
) -> LeagueMulliganProcedureResult:
    """Execute the complete 7/7/6/5/4 league procedure on one library."""
    if keep_attempt < 0 or keep_attempt >= len(LEAGUE_CANDIDATE_HAND_SIZES):
        raise ValueError("league keep attempt must identify one candidate hand")
    current = tuple(library)
    presented: list[tuple[str, ...]] = []
    rejected: list[tuple[str, ...]] = []
    shuffled_libraries: list[tuple[str, ...]] = []

    for attempt, nominal_size in enumerate(LEAGUE_CANDIDATE_HAND_SIZES):
        if len(current) < nominal_size:
            raise ValueError("library cannot present the next league mulligan hand")
        hand = current[:nominal_size]
        current = current[nominal_size:]
        presented.append(hand)
        if attempt == keep_attempt:
            refill_count = 7 - nominal_size
            if len(current) < refill_count:
                raise ValueError("library cannot supply the league refill")
            refill = current[:refill_count]
            current = current[refill_count:]
            keep_result = draw_back_to_seven(
                hand,
                refill,
                nominal_keep_size=nominal_size,
            )
            return LeagueMulliganProcedureResult(
                tuple(presented),
                tuple(rejected),
                tuple(shuffled_libraries),
                keep_result,
                current,
            )

        rejected.append(hand)
        if not REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE:
            raise AssertionError("league procedure requires rejected-hand shuffling")
        returned = current + hand
        shuffled = tuple(shuffle(returned))
        if Counter(shuffled) != Counter(returned):
            raise ValueError("shuffle must preserve the complete library multiset")
        current = shuffled
        shuffled_libraries.append(current)

    raise AssertionError("league mulligan procedure did not reach the configured keep")
