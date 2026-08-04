import pytest

from mtg_policy.mulligan import (
    LEAGUE_CANDIDATE_HAND_SIZES,
    REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE,
    LeagueMulliganResult,
    draw_back_to_seven,
)
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence


def test_pb_t02_league_mulligan_evidence() -> None:
    assert LEAGUE_CANDIDATE_HAND_SIZES == (7, 7, 6, 5, 4)
    assert REJECTED_HANDS_RETURN_TO_LIBRARY_AND_SHUFFLE is True
    results: list[LeagueMulliganResult] = []
    for keep_size in (7, 6, 5, 4):
        result = draw_back_to_seven(
            tuple(f"kept-{index}" for index in range(keep_size)),
            tuple(f"refill-{index}" for index in range(7 - keep_size)),
            nominal_keep_size=keep_size,
        )
        assert len(result.final_hand) == 7
        results.append(result)
    with pytest.raises(ValueError, match="stop at four") as floor_error:
        draw_back_to_seven(("a", "b", "c"), ("d",) * 4, nominal_keep_size=3)
    record_audit_evidence(
        "PB-T02-league-mulligan",
        (
            audit_event(
                "LEAGUE_MULLIGAN_SEQUENCE_VALIDATED",
                candidate_sizes=list(LEAGUE_CANDIDATE_HAND_SIZES),
            ),
            audit_event(
                "REJECTED_HAND_SHUFFLE_POLICY_VALIDATED",
                returned_to_library=True,
                shuffled_before_next_hand=True,
            ),
            audit_event(
                "LEAGUE_KEEP_LEVELS_VALIDATED",
                keep_sizes=[result.nominal_keep_size for result in results],
            ),
            audit_event(
                "LEAGUE_REFILL_VALIDATED",
                final_sizes=[len(result.final_hand) for result in results],
            ),
            audit_event("FOUR_CARD_FLOOR_ENFORCED", reason=str(floor_error.value)),
        ),
    )
