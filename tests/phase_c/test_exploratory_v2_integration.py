from __future__ import annotations

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.models import Zone
from mtg_measure import bind_combo_access_tracker
from mtg_policy import ActionBroker
from mtg_policy.exploratory_v2 import NoveltyLedger
from mtg_runs.phase_c_exploratory_v2 import DirectedExplorerV2
from mtg_runs.phase_c_runner import CONTROLLED_PLAYER, PLAYER_IDS, _bound_policy
from mtg_search.directed_v2 import ARM_IDS, AGGRESSIVE_ARM, load_directed_arm_config


def _specs():
    return {spec.name: spec for spec in load_full_deck_specs().values()}


def _turn_one_land_state() -> tuple[object, object]:
    specs = _specs()
    state, executor = new_game(PLAYER_IDS, "exploratory-v2-land-golden")
    state.turn.number = 1
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = CONTROLLED_PLAYER
    state.turn.priority_holder_id = CONTROLLED_PLAYER
    add_card(executor, specs["Island"], Zone.HAND, owner=CONTROLLED_PLAYER)
    return state, executor


def _turn_two_development_state() -> tuple[object, object]:
    specs = _specs()
    state, executor = new_game(PLAYER_IDS, "exploratory-v2-development-golden")
    state.turn.number = 2
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = CONTROLLED_PLAYER
    state.turn.priority_holder_id = CONTROLLED_PLAYER
    add_card(executor, specs["Island"], Zone.BATTLEFIELD, owner=CONTROLLED_PLAYER)
    add_card(executor, specs["Mountain"], Zone.HAND, owner=CONTROLLED_PLAYER)
    add_card(executor, specs["Izzet Signet"], Zone.HAND, owner=CONTROLLED_PLAYER)
    return state, executor


def test_targeted_turn_one_land_scenario_does_not_collapse_to_pass() -> None:
    _state, executor = _turn_one_land_state()
    policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    bind_combo_access_tracker(executor, CONTROLLED_PLAYER, evaluator.combo_packages)
    broker = ActionBroker(executor, CONTROLLED_PLAYER)
    observation, actions = broker.refresh()
    standard = policy.select_action(dict(observation), actions)
    explorer = DirectedExplorerV2(
        policy_config_id="anchor_balanced",
        config=load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=100,
        environment_seed=200,
        game_index=1,
        novelty=NoveltyLedger(),
    )
    selected = explorer.choose(executor, observation, actions, standard)
    action = next(item for item in actions if item.handle == selected)
    assert action.kind == "PLAY_LAND"
    assert all(
        item.get("pruned_reason") != "MAIN_PHASE_LAND_AVAILABLE_WITHOUT_VALID_HOLD_REASON"
        or item.get("handle") != selected
        for item in explorer.records[-1].candidate_evaluations
    )


def test_one_deviation_then_standard_continuation_values_development() -> None:
    _state, executor = _turn_two_development_state()
    _policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    bind_combo_access_tracker(executor, CONTROLLED_PLAYER, evaluator.combo_packages)
    _observation, actions = ActionBroker(executor, CONTROLLED_PLAYER).refresh()
    land = next(action for action in actions if action.kind == "PLAY_LAND")
    explorer = DirectedExplorerV2(
        policy_config_id="anchor_balanced",
        config=load_directed_arm_config(AGGRESSIVE_ARM),
        exploration_seed=101,
        environment_seed=201,
        game_index=1,
        novelty=NoveltyLedger(),
    )
    projection = explorer._project_candidate(executor, land)
    assert projection.action_count >= 1
    assert any("Izzet Signet" in action for action in projection.continuation_actions)
    assert projection.stop_reason in {
        "STANDARD_PASS",
        "HIDDEN_INFORMATION_BOUNDARY",
        "CONTINUATION_ACTION_LIMIT",
    }


def test_evaluator_retains_all_required_known_package_definitions() -> None:
    _state, executor = _turn_one_land_state()
    _policy, _provider, evaluator = _bound_policy(executor, "anchor_balanced")
    required = {
        "malcolm_glint_horn",
        "dualcaster_twinflame",
        "dualcaster_electroduplicate",
        "niv_mizzet_curiosity",
        "lightning_rig_crab_umbra_malcolm",
        "psychosis_crawler_draw",
    }
    assert required.issubset(evaluator.combo_packages)


def test_all_three_arm_configs_are_diagnostic_only_and_separate() -> None:
    configs = [load_directed_arm_config(arm) for arm in sorted(ARM_IDS)]
    assert {config.arm_id for config in configs} == set(ARM_IDS)
    assert all(config.pilot_activation is False for config in configs)
    assert len({config.config_sha256 for config in configs}) == 3
