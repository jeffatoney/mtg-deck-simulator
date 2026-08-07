from mtg_runs.phase_c_runner import run_phase_c_game_execution


FAILED_STANDARD_SHARD_ZERO_SEED = 6304405178442445102


def test_failed_standard_seed_records_arcane_denial_delayed_draw_choice() -> None:
    execution = run_phase_c_game_execution(
        seed=FAILED_STANDARD_SHARD_ZERO_SEED,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=False,
        policy_actions=True,
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

    assert arcane_choices
    assert all(
        choice["count"] == (2 if choice["player_id"] == "P0" else 0)
        for choice in arcane_choices
    )
    assert execution.technical_game.controlled_turns_completed == 10
    assert (
        execution.technical_game.fresh_replay_state_hash
        == execution.technical_game.final_state_hash
    )
