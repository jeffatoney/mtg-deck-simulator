"""Complete raw measurement and exact-denominator tests."""

from __future__ import annotations

from mtg_measure import (
    CardMeasurement,
    ComboMeasurement,
    GameMeasurement,
    OpeningHandMeasurement,
    aggregate_measurements,
    measurement_digest,
)


def game(index: int, *, access: bool) -> GameMeasurement:
    return GameMeasurement(
        schema_version="phase-b-game-measurement-v1",
        game_index=index,
        seed=1000 + index,
        mode="STANDARD" if index == 1 else "EXPLORATORY",
        policy_config_id="anchor_balanced",
        opening_hands=(
            OpeningHandMeasurement(1, 7, ("Island",) * 7, True),
        ),
        kept_at=7,
        checkpoint_table_win_access={5: False, 6: False, 8: access, 10: access},
        failure_labels={
            5: ("mana_shortage",),
            6: ("action_density_shortage",),
            8: (),
            10: (),
        },
        primary_failure={5: "mana_shortage", 6: "action_density_shortage", 8: None, 10: None},
        combo_records=(
            ComboMeasurement(
                "dualcaster_twinflame",
                8,
                True,
                access,
                access,
                False,
                access,
                access,
                access,
                False,
            ),
        ),
        earliest_legal_attempt_turn=8 if access else None,
        actual_first_attempt_turn=8 if access else None,
        attempt_package="dualcaster_twinflame" if access else None,
        attempt_timing="IMMEDIATE" if access else None,
        usable_protection_count=0,
        protection_in_hand_not_payable=False,
        protection_category_mismatch=False,
        independent_second_line_available=False,
        card_records=(CardMeasurement("Twinflame", drawn=1, cast=int(access)),),
        future_information_rejections=index - 1,
        post_result_optimization_rejections=0,
        terminal_status="WIN" if access else "ACTIVE",
        terminal_turn=8 if access else None,
    )


def test_measurements_preserve_all_raw_fields_and_exact_denominators() -> None:
    records = (game(1, access=False), game(2, access=True))
    summary = aggregate_measurements(records)
    assert summary.game_denominator == 2
    assert summary.mode_denominators == {"EXPLORATORY": 1, "STANDARD": 1}
    assert summary.checkpoint_access_numerators == {5: 0, 6: 0, 8: 1, 10: 1}
    assert summary.checkpoint_access_denominators == {5: 2, 6: 2, 8: 2, 10: 2}
    assert summary.combo_attempt_counts["dualcaster_twinflame"] == 1
    assert summary.combo_kill_counts["dualcaster_twinflame"] == 1
    assert summary.future_information_rejections == 1
    assert summary.raw_measurement_sha256 == measurement_digest(records)
    assert measurement_digest(tuple(reversed(records))) == measurement_digest(records)
