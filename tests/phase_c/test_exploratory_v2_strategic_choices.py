from __future__ import annotations

from types import SimpleNamespace

from mtg_kernel.strategic_choices import (
    CardSelection,
    CardSelectionRequest,
    FactOrFictionRequest,
    FactOrFictionSelection,
    FactOrFictionSplit,
    OptionalTriggerRequest,
    OptionalTriggerSelection,
    PublicCard,
    SpellCopyTargetRequest,
    SpellCopyTargetSelection,
    TutorChoiceRequest,
    TutorChoiceSelection,
)
from mtg_policy.broker_core import ObservedAction
from mtg_policy.exploratory_v2 import (
    GLINT_HORN,
    PublicProjection,
    score_priority_candidate,
    semantic_action_key,
)
from mtg_policy.exploratory_v2_strategic import ExploratoryStrategicChoiceProviderV2
from mtg_search.directed_v2 import ALT_PACKAGE_ARM, INTERACTION_ARM, load_directed_arm_config


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

    def choose_tutor(self, request: TutorChoiceRequest) -> TutorChoiceSelection:
        return TutorChoiceSelection(
            request.eligible_identities[0], self.evaluator_id, self.evaluator_sha256, {}
        )

    def choose_fact_or_fiction(self, request: FactOrFictionRequest) -> FactOrFictionSelection:
        return FactOrFictionSelection(0, "A", self.evaluator_id, self.evaluator_sha256, {})

    def choose_spell_copy_targets(
        self, request: SpellCopyTargetRequest
    ) -> SpellCopyTargetSelection:
        return SpellCopyTargetSelection(
            request.legal_target_sets[0], self.evaluator_id, self.evaluator_sha256, {}
        )

    def choose_optional_trigger(self, request: OptionalTriggerRequest) -> OptionalTriggerSelection:
        return OptionalTriggerSelection(True, self.evaluator_id, self.evaluator_sha256, {})


def _provider(arm_id: str = ALT_PACKAGE_ARM) -> ExploratoryStrategicChoiceProviderV2:
    return ExploratoryStrategicChoiceProviderV2(
        _OptionalBaseline(),  # type: ignore[arg-type]
        load_directed_arm_config(arm_id),
        exploration_seed=982001,
        environment_seed=882001,
        game_index=1,
    )


def _assert_complete_record(record: dict[str, object]) -> None:
    required = {
        "schema_version",
        "arm_id",
        "game_index",
        "environment_seed",
        "exploration_seed",
        "decision_id",
        "turn",
        "phase",
        "public_observation_digest",
        "strategic_choice_purpose",
        "legal_candidate_handles",
        "standard_baseline_handle",
        "standard_baseline_score_vector",
        "candidate_evaluations",
        "pruned_candidates",
        "arm_specific_exclusions",
        "novelty_state_before",
        "equivalence_window",
        "eligible_top_k",
        "selected_action",
        "selection_reason",
        "randomness_affected_selection",
        "selected_plan_or_package_id",
        "continuation_method",
        "continuation_horizon",
        "plan_termination_or_fallback_reason",
        "resulting_public_state_digest",
        "replay_binding",
    }
    assert required <= set(record)
    assert record["schema_version"] == "phase-c-exploratory-v2-decision-v1"
    assert len(str(record["public_observation_digest"])) == 64
    handles = set(record["legal_candidate_handles"])  # type: ignore[arg-type]
    assert record["standard_baseline_handle"] in handles
    assert record["selected_action"] in handles
    assert len(record["candidate_evaluations"]) == len(handles)  # type: ignore[arg-type]


def test_arm_2_optional_search_excludes_glint_and_retains_fail_to_find() -> None:
    provider = _provider()
    request = CardSelectionRequest(
        request_id="optional-search",
        actor_id="P0",
        ability_id="test:search",
        turn_number=2,
        observation={"phase": "PRECOMBAT_MAIN", "objects": ()},
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
    record = provider.records[-1]
    _assert_complete_record(record)
    assert "__LEGAL_FAIL_TO_FIND__" in record["legal_candidate_handles"]
    assert record["arm_specific_exclusions"][0]["identity"] == GLINT_HORN


def test_arm_2_tutor_records_glint_exclusion_and_selects_an_alternative() -> None:
    provider = _provider()
    request = TutorChoiceRequest(
        request_id="tutor",
        actor_id="P0",
        ability_id="test:tutor",
        turn_number=3,
        observation={"phase": "PRECOMBAT_MAIN", "objects": ()},
        eligible_identities=(GLINT_HORN, "Dualcaster Mage"),
        eligible_cards=(
            PublicCard("g", GLINT_HORN, 3, ("Creature",), ()),
            PublicCard("d", "Dualcaster Mage", 3, ("Creature",), ()),
        ),
    )
    selected = provider.choose_tutor(request)
    assert selected.selected_identity == "Dualcaster Mage"
    record = provider.records[-1]
    _assert_complete_record(record)
    assert record["standard_baseline_handle"] == f"TUTOR:{GLINT_HORN}"
    assert record["selected_action"] == "TUTOR:Dualcaster Mage"


def test_fact_or_fiction_keeps_the_standard_opponent_split_fixed() -> None:
    provider = _provider(INTERACTION_ARM)
    cards = (
        PublicCard("a", "Dualcaster Mage", 3, ("Creature",), ()),
        PublicCard("b", "Twinflame", 2, ("Sorcery",), ()),
        PublicCard("c", "Island", 0, ("Land",), ()),
    )
    request = FactOrFictionRequest(
        request_id="fof",
        actor_id="P0",
        opponent_id="P1",
        turn_number=4,
        observation={"phase": "END", "objects": ()},
        revealed_cards=cards,
        legal_splits=(
            FactOrFictionSplit(0, ("a",), ("b", "c")),
            FactOrFictionSplit(1, ("a", "b"), ("c",)),
        ),
    )
    selected = provider.choose_fact_or_fiction(request)
    assert selected.split_index == 0
    record = provider.records[-1]
    _assert_complete_record(record)
    assert set(record["legal_candidate_handles"]) == {"FOF:0:A", "FOF:0:B"}
    assert any(
        item.get("reason") == "OPPONENT_CHOICE_FIXED_TO_FROZEN_STANDARD_MINIMIZER"
        for item in record["pruned_candidates"]
    )


def test_spell_copy_targets_and_optional_trigger_emit_complete_evidence() -> None:
    provider = _provider(INTERACTION_ARM)
    targets = (
        PublicCard("x", "Target A", 1, ("Creature",), ()),
        PublicCard("y", "Target B", 2, ("Creature",), ()),
    )
    copy_request = SpellCopyTargetRequest(
        request_id="copy-target",
        actor_id="P0",
        source_identity="Dualcaster Mage",
        copied_spell_identity="Twinflame",
        turn_number=4,
        observation={"phase": "PRECOMBAT_MAIN", "objects": ()},
        original_target_handles=("x",),
        legal_targets=targets,
        legal_target_sets=(("x",), ("y",)),
    )
    provider.choose_spell_copy_targets(copy_request)
    _assert_complete_record(provider.records[-1])

    trigger_request = OptionalTriggerRequest(
        request_id="trigger",
        actor_id="P0",
        ability_id="test:optional-draw",
        effect_kind="DRAW",
        turn_number=4,
        observation={"phase": "END", "objects": ()},
    )
    provider.choose_optional_trigger(trigger_request)
    record = provider.records[-1]
    _assert_complete_record(record)
    assert set(record["legal_candidate_handles"]) == {
        "OPTIONAL_TRIGGER:TAKE",
        "OPTIONAL_TRIGGER:SKIP",
    }


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
        "m2",
        "CAST",
        "Prismari Command",
        3,
        ("INSTANT",),
        0,
        {"modes": ("DAMAGE", "TREASURE")},
    )
    activation = ObservedAction(
        "a1", "ACTIVATE", "Lightning-Rig Crew", 0, ("ACTIVATED_ABILITY",), 3, {}
    )
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
