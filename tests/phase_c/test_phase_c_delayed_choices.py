from mtg_runs.phase_c_runner import run_phase_c_game_execution


FAILED_STANDARD_SHARD_ZERO_SEED = 6304405178442445102


def test_failed_standard_seed_avoids_arcane_denial_self_interaction() -> None:
    execution = run_phase_c_game_execution(
        seed=FAILED_STANDARD_SHARD_ZERO_SEED,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=True,
    )

    selected_actions = tuple(execution.measurement.extra["selected_actions"])
    assert not any(
        action.get("kind") == "CAST" and action.get("identity") == "Arcane Denial"
        for action in selected_actions
    )

    arcane_choices: list[dict[str, object]] = []
    for command in execution.replay_transcript["commands"]:
        if command.get("operation") != "begin_step":
            continue
        arguments = command.get("arguments", {})
        if arguments.get("step") != "UPKEEP":
            continue
        choices = arguments.get("choices", {})
        per_trigger = choices.get("delayed_trigger_choices", {})
        for trigger_choice in per_trigger.values():
            value = trigger_choice.get("arcane_denial_draw_count")
            if isinstance(value, dict):
                arcane_choices.append(value)

    assert arcane_choices == []
    assert execution.technical_game.controlled_turns_completed == 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )
