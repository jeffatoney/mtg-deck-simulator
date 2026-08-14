from __future__ import annotations

from mtg_deck import build_exact_game
from mtg_kernel.models import Zone
from mtg_kernel.observation import ObservationService
from mtg_measure import bind_combo_access_tracker
from mtg_policy import ActionBroker
from mtg_policy.exploratory_v2 import NoveltyLedger, semantic_action_key
from mtg_runs.phase_c_exploratory_v2 import DirectedExplorerV2
from mtg_runs.phase_c_runner import CONTROLLED_PLAYER, PLAYER_IDS, _bound_policy
from mtg_search.directed_v2 import AGGRESSIVE_ARM, load_directed_arm_config


def _prepared_executor(seed_text: str):
    state, executor, _ = build_exact_game(seed_text, PLAYER_IDS)
    executor.league_mulligan(CONTROLLED_PLAYER, 0)
    state.turn.number = 1
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = CONTROLLED_PLAYER
    state.turn.priority_holder_id = CONTROLLED_PLAYER
    policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    bind_combo_access_tracker(executor, CONTROLLED_PLAYER, evaluator.combo_packages)
    return executor, policy


def test_reordering_hidden_future_library_does_not_change_semantic_priority_choice() -> None:
    seed_text = "phase-c:standard:881001"
    first_executor, first_policy = _prepared_executor(seed_text)
    second_executor, second_policy = _prepared_executor(seed_text)
    library = second_executor.zones.zone_key(Zone.LIBRARY, CONTROLLED_PLAYER)
    second_executor.state.zones[library] = list(reversed(second_executor.state.zones[library]))
    first_observation = ObservationService(first_executor.state).observe_for_policy(
        CONTROLLED_PLAYER
    )
    second_observation = ObservationService(second_executor.state).observe_for_policy(
        CONTROLLED_PLAYER
    )
    assert first_observation == second_observation

    config = load_directed_arm_config(AGGRESSIVE_ARM)
    first_broker = ActionBroker(first_executor, CONTROLLED_PLAYER)
    obs1, actions1 = first_broker.refresh()
    standard1 = first_policy.select_action(dict(obs1), actions1)
    first_explorer = DirectedExplorerV2(
        policy_config_id="anchor_balanced",
        config=config,
        exploration_seed=981001,
        environment_seed=881001,
        game_index=1,
        novelty=NoveltyLedger(),
    )
    selected1 = first_explorer.choose(first_executor, obs1, actions1, standard1)

    second_broker = ActionBroker(second_executor, CONTROLLED_PLAYER)
    obs2, actions2 = second_broker.refresh()
    standard2 = second_policy.select_action(dict(obs2), actions2)
    second_explorer = DirectedExplorerV2(
        policy_config_id="anchor_balanced",
        config=config,
        exploration_seed=981001,
        environment_seed=881001,
        game_index=1,
        novelty=NoveltyLedger(),
    )
    selected2 = second_explorer.choose(second_executor, obs2, actions2, standard2)
    key1 = semantic_action_key(next(action for action in actions1 if action.handle == selected1))
    key2 = semantic_action_key(next(action for action in actions2 if action.handle == selected2))
    assert key1 == key2
