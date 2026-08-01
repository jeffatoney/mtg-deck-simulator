"""The owner-specified league draw-back-to-seven mulligan procedure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueMulliganResult:
    nominal_keep_size: int
    kept_cards: tuple[str, ...]
    refill_cards: tuple[str, ...]
    final_hand: tuple[str, ...]


def draw_back_to_seven(
    kept_cards: tuple[str, ...],
    refill_cards: tuple[str, ...],
    *,
    nominal_keep_size: int,
) -> LeagueMulliganResult:
    """Validate a 7/6/5/4 keep and apply the league refill after the keep."""
    if nominal_keep_size not in {7, 6, 5, 4}:
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
