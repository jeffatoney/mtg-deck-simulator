"""League draw-back-to-seven mulligan acceptance tests."""

from __future__ import annotations

import pytest

from mtg_policy.mulligan import draw_back_to_seven


def test_league_mulligan_keeps_at_7_6_5_or_4_then_draws_back_to_seven() -> None:
    for keep_size in (7, 6, 5, 4):
        kept = tuple(f"kept-{index}" for index in range(keep_size))
        refill = tuple(f"refill-{index}" for index in range(7 - keep_size))
        result = draw_back_to_seven(kept, refill, nominal_keep_size=keep_size)
        assert result.nominal_keep_size == keep_size
        assert result.kept_cards == kept
        assert result.refill_cards == refill
        assert result.final_hand == kept + refill
        assert len(result.final_hand) == 7

    with pytest.raises(ValueError, match="stop at four"):
        draw_back_to_seven(("a", "b", "c"), ("d",) * 4, nominal_keep_size=3)
