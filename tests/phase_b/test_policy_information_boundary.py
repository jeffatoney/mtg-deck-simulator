from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import runpy
import subprocess
import sys
from typing import Any

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.engine import GameExecutor
from mtg_kernel.factory import add_card
from mtg_kernel.models import GameState, PlayerState, TurnState, Zone
from mtg_measure import bind_combo_access_tracker
from mtg_policy.broker import ActionBroker
from mtg_policy.config import load_policy_matrix
from mtg_policy.public_actions import policy_action_view, public_action_classes
from mtg_policy.standard import StandardPolicy

ROOT = Path(__file__).resolve().parents[2]


def _state_with_cards(*hand: str, library: tuple[str, ...] = ()) -> GameState:
    state = GameState(
        "policy-noninterference-test",
        {player: PlayerState(player) for player in ("P0", "P1", "P2", "P3")},
        TurnState("P0", priority_holder_id="P0"),
    )
    executor = GameExecutor(state, "policy-noninterference-test")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    for name in hand:
        add_card(executor, specs[name], Zone.HAND)
    for name in library:
        add_card(executor, specs[name], Zone.LIBRARY, visible_to=set())
    return state


def _policy(*, opponent_interaction_modeled: bool) -> StandardPolicy:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    return StandardPolicy(bundle, opponent_interaction_modeled=opponent_interaction_modeled)


def _normalized_public_observation(value: Any, *, key: str | None = None) -> Any:
    if key is not None and (key == "handle" or key.endswith("_handle") or key.endswith("_handles")):
        return "<PUBLIC_HANDLE>"
    if isinstance(value, dict):
        return {
            str(item_key): _normalized_public_observation(item_value, key=str(item_key))
            for item_key, item_value in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        normalized = [_normalized_public_observation(item) for item in value]
        if key == "objects":
            return sorted(normalized, key=lambda item: repr(item))
        return normalized
    return value


def test_distinct_public_action_selection_ignores_hidden_library_order_and_action_handles() -> None:
    base = _state_with_cards(
        "Island",
        "Mountain",
        library=("Twinflame", "Curiosity"),
    )
    mutated = deepcopy(base)
    library_key = f"{Zone.LIBRARY.value}:P0"
    mutated.zones[library_key] = list(reversed(mutated.zones[library_key]))

    broker_a = ActionBroker(GameExecutor(base, "policy-noninterference-test"), "P0")
    broker_b = ActionBroker(GameExecutor(mutated, "policy-noninterference-test"), "P0")
    observation_a, actions_a = broker_a.refresh()
    observation_b, actions_b = broker_b.refresh()

    assert observation_a == observation_b
    keys_a = {policy_action_view(action).key for action in actions_a}
    keys_b = {policy_action_view(action).key for action in actions_b}
    assert keys_a == keys_b
    handles_a = {policy_action_view(action).key: action.handle for action in actions_a}
    handles_b = {policy_action_view(action).key: action.handle for action in actions_b}
    assert handles_a != handles_b

    for modeled in (False, True):
        policy = _policy(opponent_interaction_modeled=modeled)
        assert policy.select_public_action_key(
            observation_a, actions_a
        ) == policy.select_public_action_key(observation_b, tuple(reversed(actions_b)))


def test_identical_public_representatives_are_execution_equivalent_for_supported_basic_land_class() -> (
    None
):
    base = _state_with_cards(
        "Island",
        "Island",
        library=("Twinflame", "Curiosity"),
    )
    state_a = deepcopy(base)
    state_b = deepcopy(base)
    executor_a = GameExecutor(state_a, "policy-noninterference-test")
    executor_b = GameExecutor(state_b, "policy-noninterference-test")
    tracker_a = bind_combo_access_tracker(
        executor_a, "P0", {"dualcaster_twinflame": ("Dualcaster Mage", "Twinflame")}
    )
    tracker_b = bind_combo_access_tracker(
        executor_b, "P0", {"dualcaster_twinflame": ("Dualcaster Mage", "Twinflame")}
    )
    broker_a = ActionBroker(executor_a, "P0")
    broker_b = ActionBroker(executor_b, "P0")
    observation_a, actions_a = broker_a.refresh()
    observation_b, actions_b = broker_b.refresh()
    island_a = [
        action for action in actions_a if action.kind == "PLAY_LAND" and action.identity == "Island"
    ]
    island_b = [
        action for action in actions_b if action.kind == "PLAY_LAND" and action.identity == "Island"
    ]
    assert len(island_a) == len(island_b) == 2
    assert policy_action_view(island_a[0]).key == policy_action_view(island_a[1]).key
    classes = public_action_classes(tuple(island_a))
    assert len(classes) == 1
    assert classes[0].representative_count == 2

    broker_a.execute(int(observation_a["generation"]), island_a[0].handle)
    broker_b.execute(int(observation_b["generation"]), island_b[1].handle)
    successor_a, continuation_a = broker_a.refresh()
    successor_b, continuation_b = broker_b.refresh()

    assert _normalized_public_observation(successor_a) == _normalized_public_observation(
        successor_b
    )
    assert tracker_a.records == tracker_b.records
    policy = _policy(opponent_interaction_modeled=False)
    assert policy.select_public_action_key(
        successor_a, continuation_a
    ) == policy.select_public_action_key(successor_b, tuple(reversed(continuation_b)))


def test_public_action_key_rejects_private_execution_identity() -> None:
    from mtg_policy.broker_core import ObservedAction

    action = ObservedAction(
        "opaque-capability",
        "CAST",
        "Opt",
        1,
        ("Instant",),
        0,
        {"source_object_id": "private-object"},
    )
    try:
        policy_action_view(action)
    except ValueError as exc:
        assert "private field" in str(exc)
    else:
        raise AssertionError("private object identity entered the public action key")


def test_standing_policy_information_boundary_gate_passes_and_rejects_bad_patterns() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_policy_information_boundary.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    namespace = runpy.run_path(
        str(ROOT / "scripts/check_policy_information_boundary.py"),
        run_name="policy_boundary_test",
    )
    find_violations = namespace["find_policy_boundary_violations"]
    bad_ranking = """
from mtg_policy.broker_core import ObservedAction

def score(action: ObservedAction) -> str:
    return action.handle
"""
    violations = find_violations(Path("src/mtg_policy/bad_ranking.py"), bad_ranking)
    assert any("capability handle" in item for item in violations)

    bad_runner = """
def mutate(broker):
    broker._actions.clear()
"""
    violations = find_violations(Path("src/mtg_runs/bad_runner.py"), bad_runner)
    assert any("ActionBroker._actions" in item for item in violations)
