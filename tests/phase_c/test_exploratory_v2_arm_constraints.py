from __future__ import annotations

from types import SimpleNamespace

from mtg_kernel.strategic_choices import PublicCard, TutorChoiceRequest, TutorChoiceSelection
from mtg_policy.exploratory_v2 import ExploratoryStrategicChoiceProvider, GLINT_HORN
from mtg_search.directed_v2 import (
    AGGRESSIVE_ARM,
    ALT_PACKAGE_ARM,
    load_directed_arm_config,
)


class _FakeEvaluator:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            combo_packages={
                "malcolm_glint_horn": (
                    "Malcolm, Keen-Eyed Navigator",
                    "Glint-Horn Buccaneer",
                ),
                "dualcaster_twinflame": ("Dualcaster Mage", "Twinflame"),
            }
        )


class _FakeBaseline:
    evaluator_id = "baseline"
    evaluator_sha256 = "a" * 64

    def __init__(self) -> None:
        self.bundle = SimpleNamespace(policy_config_id="anchor_balanced")
        self.evaluator = _FakeEvaluator()

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        return TutorChoiceSelection(GLINT_HORN, self.evaluator_id, self.evaluator_sha256, {})


def _request() -> TutorChoiceRequest:
    glint = PublicCard("g", GLINT_HORN, 3, ("Creature",), ())
    dualcaster = PublicCard("d", "Dualcaster Mage", 3, ("Creature",), ())
    return TutorChoiceRequest(
        request_id="request-1",
        actor_id="P0",
        ability_id="test:tutor",
        turn_number=3,
        observation={
            "objects": (
                {
                    "identity": "Malcolm, Keen-Eyed Navigator",
                    "zone": "BATTLEFIELD",
                },
            )
        },
        eligible_identities=(GLINT_HORN, "Dualcaster Mage"),
        eligible_cards=(glint, dualcaster),
    )


def test_arm_1_may_tutor_glint_horn() -> None:
    provider = ExploratoryStrategicChoiceProvider(
        _FakeBaseline(),  # type: ignore[arg-type]
        load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=1,
        environment_seed=2,
        game_index=1,
    )
    selected = provider.choose_tutor(_request())
    assert selected.selected_identity in {GLINT_HORN, "Dualcaster Mage"}
    assert not any(
        item.get("reason") == "ARM_CONSTRAINT_NO_GLINT_HORN_TUTOR"
        for record in provider.records
        for item in record.get("arm_specific_exclusions", ())
    )


def test_arm_2_never_selects_glint_horn_as_tutor_target() -> None:
    provider = ExploratoryStrategicChoiceProvider(
        _FakeBaseline(),  # type: ignore[arg-type]
        load_directed_arm_config(ALT_PACKAGE_ARM),
        exploration_seed=1,
        environment_seed=2,
        game_index=1,
    )
    selected = provider.choose_tutor(_request())
    assert selected.selected_identity == "Dualcaster Mage"
    record = provider.records[-1]
    assert record["standard_baseline_handle"] == f"TUTOR:{GLINT_HORN}"
    assert record["selected_action"] != f"TUTOR:{GLINT_HORN}"
    assert record["arm_specific_exclusions"][0]["identity"] == GLINT_HORN
