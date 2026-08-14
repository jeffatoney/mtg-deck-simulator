from __future__ import annotations

from types import SimpleNamespace

from mtg_kernel.strategic_choices import CardSelection, CardSelectionRequest, PublicCard
from mtg_policy.exploratory_v2 import GLINT_HORN, PublicProjection, score_priority_candidate
from mtg_policy.exploratory_v2_strategic import ExploratoryStrategicChoiceProviderV2
from mtg_policy.broker_core import ObservedAction
from mtg_search.directed_v2 import ALT_PACKAGE_ARM, load_directed_arm_config


class _Evaluator:
    config = SimpleNamespace(
        combo_packages={
            "malcolm_glint_horn": ("Malcolm, Keen-Eyed Navigator", GLINT_HORN),
            "dualcaster_twinflame": ("Dualcaster Mage", "Twinflame"),
        }
    )


class _OptionalBaseline:
    evaluator_id = "baseline"
    evaluator_sha256 = "a" * 64
    evaluator = _Evaluator()
    bundle = SimpleNamespace(policy_config_id="anchor_balanced")

    def choose_cards(self, request: CardSelectionRequest) -> CardSelection:
        return CardSelection(
            (request.candidates[0].handle,), self.evaluator_id, self.evaluator_sha256, {}
        )


def test_arm_2_optional_search_excludes_glint_and_retains_fail_to_find() -> None:
    provider = ExploratoryStrategicChoiceProviderV2(
        _OptionalBaseline(),  # type: ignore[arg-type]
        load_directed_arm_config(ALT_PACKAGE_ARM),
        exploration_seed=982001,
        environment_seed=882001,
        game_index=1,
    )
    request = CardSelectionRequest(
        request_id="optional-search",
        actor_id="P0",
        ability_id="test:search",
        turn_number=2,
        observation={"objects": ()},
        purpose="TUTOR_OPTIONAL_SEARCH",
        candidates=(
            PublicCard("g", GLINT_HORN, 3, ("Creature",), ()),
            PublicCard("d", "Dualcaster Mage", 3, ("Creature",), ()),
        ),
        minimum=0,
        maximum=1,
    )
    selected = provider.choose_cards(request)
    assert selected.selected_handles != ("g",)
    diagnostics = selected.diagnostics
    assert "__LEGAL_FAIL_TO_FIND__" in diagnostics["legal_candidate_handles"]
    assert diagnostics["arm_specific_exclusions"][0]["identity"] == GLINT_HORN


def test_arm_2_does_not_suppress_naturally_drawn_glint_cast_action() -> None:
    config = load_directed_arm_config(ALT_PACKAGE_ARM)
    glint = ObservedAction("cast-g", "CAST", GLINT_HORN, 3, ("CREATURE",), 0, {})
    score, prune, _package = score_priority_candidate(
        action=glint,
        observation={"phase": "PRECOMBAT_MAIN", "step": "PRECOMBAT_MAIN", "objects": ()},
        all_actions=(glint,),
        config=config,
        projection=PublicProjection(False, False, None, (), "STANDARD_PASS", 0),
        novelty_value=0,
        combo_packages={"malcolm_glint_horn": ("Malcolm, Keen-Eyed Navigator", GLINT_HORN)},
    )
    assert score.arm_constraint_status == "ALLOWED"
    assert prune is None


def test_modal_and_activated_actions_remain_distinct_strategic_candidates() -> None:
    config = load_directed_arm_config(ALT_PACKAGE_ARM)
    modal_a = ObservedAction(
        "m1",
        "CAST",
        "Prismari Command",
        3,
        ("INSTANT",),
        0,
        {"modes": ("DRAW_DISCARD", "TREASURE")},
    )
    modal_b = ObservedAction(
        "m2", "CAST", "Prismari Command", 3, ("INSTANT",), 0, {"modes": ("DAMAGE", "TREASURE")}
    )
    activation = ObservedAction(
        "a1", "ACTIVATE", "Lightning-Rig Crew", 0, ("ACTIVATED_ABILITY",), 3, {}
    )
    from mtg_policy.exploratory_v2 import semantic_action_key

    assert semantic_action_key(modal_a) != semantic_action_key(modal_b)
    score, prune, _ = score_priority_candidate(
        action=activation,
        observation={"phase": "PRECOMBAT_MAIN", "step": "PRECOMBAT_MAIN", "objects": ()},
        all_actions=(activation,),
        config=config,
        projection=PublicProjection(False, False, None, (), "STANDARD_PASS", 0),
        novelty_value=1,
        combo_packages={},
    )
    assert score.reason_codes[0] == "ACTION_KIND_ACTIVATE"
    assert prune is None
