import pytest

from mtg_policy.mulligan import (
    LEAGUE_CANDIDATE_HAND_SIZES,
    execute_league_mulligan,
)
from mtg_verify.transcript_evidence import audit_event, record_audit_evidence


def _rotate(cards: tuple[str, ...]) -> tuple[str, ...]:
    return cards[1:] + cards[:1] if cards else cards


def test_pb_t02_league_mulligan_evidence() -> None:
    runs = []
    for keep_attempt in range(len(LEAGUE_CANDIDATE_HAND_SIZES)):
        library = tuple(f"run-{keep_attempt}-card-{index}" for index in range(80))
        result = execute_league_mulligan(
            library,
            keep_attempt=keep_attempt,
            shuffle=_rotate,
        )
        expected_sizes = LEAGUE_CANDIDATE_HAND_SIZES[: keep_attempt + 1]
        assert tuple(len(hand) for hand in result.presented_hands) == expected_sizes
        assert result.shuffle_count == keep_attempt
        assert len(result.rejected_hands) == keep_attempt
        assert len(result.keep_result.final_hand) == 7
        assert result.keep_result.nominal_keep_size == expected_sizes[-1]
        for rejected, shuffled_library in zip(
            result.rejected_hands, result.shuffled_libraries, strict=True
        ):
            assert set(rejected).issubset(set(shuffled_library))
        runs.append(result)

    with pytest.raises(ValueError, match="identify one candidate hand"):
        execute_league_mulligan(
            tuple(f"card-{index}" for index in range(80)),
            keep_attempt=5,
            shuffle=_rotate,
        )

    record_audit_evidence(
        "PB-T02-league-mulligan",
        (
            audit_event(
                "LEAGUE_MULLIGAN_SEQUENCE_EXECUTED",
                candidate_sequences=[
                    [len(hand) for hand in result.presented_hands] for result in runs
                ],
            ),
            audit_event(
                "REJECTED_HANDS_RETURNED_AND_SHUFFLED",
                shuffle_counts=[result.shuffle_count for result in runs],
            ),
            audit_event(
                "LEAGUE_KEEP_LEVELS_EXECUTED",
                keep_sizes=[result.keep_result.nominal_keep_size for result in runs],
            ),
            audit_event(
                "LEAGUE_REFILLS_EXECUTED",
                final_sizes=[len(result.keep_result.final_hand) for result in runs],
            ),
            audit_event("FOUR_CARD_FLOOR_ENFORCED", maximum_keep_attempt=4),
        ),
        facts={
            "production_procedure_executed": True,
            "candidate_sizes": list(LEAGUE_CANDIDATE_HAND_SIZES),
            "total_shuffle_operations": sum(result.shuffle_count for result in runs),
        },
    )
