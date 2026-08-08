from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel import add_card, new_game
from mtg_kernel.models import ObjectKind, Zone
from mtg_policy import (
    ContextualEvaluator,
    bind_policy_strategic_choices,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_runs.phase_c_runner import run_phase_c_game_execution


FAILED_STANDARD_SHARD_FOUR_SEED = 1496936466758975315


def _anchor_policy(executor):
    bundle = next(
        value for value in load_policy_matrix() if value.policy_config_id == "anchor_balanced"
    )
    evaluator = ContextualEvaluator(load_evaluator_config())
    return bind_policy_strategic_choices(executor, bundle, evaluator)


def test_niv_draw_trigger_records_explicit_opponent_target_choice() -> None:
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="niv-trigger-target-choice")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    add_card(executor, specs["Niv-Mizzet, the Firemind"], Zone.BATTLEFIELD)
    add_card(executor, specs["Island"], Zone.LIBRARY)
    _anchor_policy(executor)

    executor.draw_card("P0")

    selections = [
        choice
        for choice in state.choices
        if choice.kind == "CARD_SELECTION"
        and isinstance(choice.selected, dict)
        and choice.selected.get("purpose") == "TRIGGER_TARGET:DAMAGE_ANY_TARGET"
    ]
    assert len(selections) == 1
    target_choices = [choice for choice in state.choices if choice.kind == "TRIGGER_TARGETS"]
    assert len(target_choices) == 1
    selected_ids = target_choices[0].selected
    assert isinstance(selected_ids, list) and len(selected_ids) == 1
    target = state.objects[selected_ids[0]]
    assert target.object_kind is ObjectKind.EXTERNAL_PUBLIC_OBJECT
    assert target.current_characteristics.get("target_kind") == "PLAYER"
    assert target.current_characteristics.get("player_id") == "P1"


def test_failed_standard_shard_four_seed_completes_with_recorded_trigger_targets() -> None:
    execution = run_phase_c_game_execution(
        seed=FAILED_STANDARD_SHARD_FOUR_SEED,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    selections = [
        choice
        for choice in execution.replay_transcript["choices"]
        if choice.get("kind") == "CARD_SELECTION"
        and isinstance(choice.get("selected"), dict)
        and str(choice["selected"].get("purpose", "")).startswith("TRIGGER_TARGET:")
    ]
    assert selections
    assert execution.technical_game.controlled_turns_completed == 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )