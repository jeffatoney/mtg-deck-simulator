from __future__ import annotations

import pytest

from mtg_deck import build_exact_game
from mtg_kernel.models import Zone
from mtg_policy.broker import ActionBroker
from mtg_runs import phase_c_runner

PLAYER_IDS = ("P0", "P1", "P2", "P3")


def _put_named_permanent_on_battlefield(executor, name: str):
    source = next(
        obj
        for obj in executor.state.objects.values()
        if not obj.retired
        and obj.owner == "P0"
        and str(obj.current_characteristics.get("name", "")) == name
    )
    event = executor._event("STAGE2_TEST_SETUP")
    moved = executor.zones.move(
        source.object_id,
        Zone.BATTLEFIELD,
        "STAGE2_TEST_SETUP",
        event,
        controller="P0",
        face=0,
    )
    assert moved is not None
    return moved


@pytest.mark.parametrize("name", ("Command Tower", "Arcane Signet"))
def test_commander_color_resource_sources_are_production_broker_executable(name: str) -> None:
    _state, executor, _ = build_exact_game(f"stage2-commander-color-broker:{name}", PLAYER_IDS)
    executor.state.turn.active_player_id = "P0"
    executor.state.turn.priority_holder_id = "P0"
    executor.state.turn.phase = "PRECOMBAT_MAIN"
    executor.state.turn.step = "PRECOMBAT_MAIN"
    source = _put_named_permanent_on_battlefield(executor, name)

    broker = ActionBroker(executor, "P0")
    observation, actions = broker.refresh()
    matches = [
        action
        for action in actions
        if action.kind == "ACTIVATE"
        and action.identity == name
        and action.metadata.get("mana_color") in {"U", "R"}
    ]
    assert {str(action.metadata["mana_color"]) for action in matches} == {"U", "R"}

    blue = next(action for action in matches if action.metadata["mana_color"] == "U")
    before = int(executor.state.players["P0"].mana_pool.get("U", 0))
    broker.execute(int(observation["generation"]), blue.handle)
    assert int(executor.state.players["P0"].mana_pool.get("U", 0)) == before + 1
    current = executor.state.objects[source.object_id]
    if current.retired:
        current = next(
            obj
            for obj in executor.state.objects.values()
            if not obj.retired
            and obj.owner == "P0"
            and str(obj.current_characteristics.get("name", "")) == name
            and obj.zone is Zone.BATTLEFIELD
        )
    assert (current.permanent_status or {}).get("tap") == "TAPPED"


class _ProfileBound(RuntimeError):
    pass


def test_phase_c_runner_threads_explicit_opponent_mana_profile(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_bind(executor, player_id, package_definitions, *, opponent_mana_profile):
        del executor, player_id, package_definitions
        captured["profile"] = str(opponent_mana_profile)
        raise _ProfileBound

    monkeypatch.setattr(phase_c_runner, "bind_combo_access_tracker", fake_bind)
    with pytest.raises(_ProfileBound):
        phase_c_runner.run_phase_c_game_execution(
            seed=101,
            mode="STANDARD",
            through_turn=1,
            opponent_mana_profile="no_known_colors",
        )
    assert captured == {"profile": "no_known_colors"}
