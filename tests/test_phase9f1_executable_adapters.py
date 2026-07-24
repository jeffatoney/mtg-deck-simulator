from pathlib import Path
from dataclasses import replace

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sim.executable_adapters import (
    adapter_registry,
    expected_card_names,
    validate_executable_coverage,
    write_report,
)
import pytest

LANDS = [
    "Island",
    "Mountain",
    "Command Tower",
    "Shivan Reef",
    "Cascade Bluffs",
    "Frostboil Snarl",
    "Temple of Epiphany",
    "Path of Ancestry",
    "Thriving Isle",
    "Izzet Boilerworks",
    "Exotic Orchard",
    "Ash Barrens",
    "Evolving Wilds",
    "Terramorphic Expanse",
    "Scavenger Grounds",
    "Demolition Field",
]
ROCKS = [
    "Sol Ring",
    "Arcane Signet",
    "Fellwar Stone",
    "Izzet Signet",
    "Mind Stone",
    "Prismatic Lens",
]


def pool(c=0, u=0, r=0):
    return {"C": c, "U": u, "R": r, "W": 0, "B": 0, "G": 0}


def test_registry_counts_and_failures(tmp_path: Path) -> None:
    report = write_report(tmp_path / "report.json")
    assert report["expected_unique_card_count"] == len(expected_card_names()) == 80
    assert report["executable_adapter_count"] >= 44
    assert report["blocked_adapter_count"] <= 36
    reg = adapter_registry()
    del reg["Island"]
    assert any("missing adapter" in e for e in validate_executable_coverage(reg))
    reg = adapter_registry()
    reg["Island"] = replace(reg["Island"], execution_handler="placeholder")
    assert any("execution handler" in e for e in validate_executable_coverage(reg))


@pytest.mark.parametrize("land", LANDS)
def test_every_land_play_is_generated(land: str) -> None:
    s = GameState(hand=[land], library=["Island", "Mountain"], mana_pool=pool())
    assert any(
        a.action_type is ActionType.PLAY_LAND and a.source_name == land
        for a in generate_legal_actions(s)
    )


def test_land_mana_and_fetch_behaviors() -> None:
    expected = {
        "Island": {"U"},
        "Mountain": {"R"},
        "Command Tower": {"U", "R"},
        "Exotic Orchard": {"U", "R"},
        "Fellwar Stone": {"U", "R"},
        "Shivan Reef": {"C", "U", "R"},
        "Path of Ancestry": {"U", "R"},
        "Thriving Isle": {"U", "R"},
    }
    for name, colors in expected.items():
        for color in colors:
            s = GameState(mana_pool=pool())
            p = Permanent(name, {"Land"}, tapped=False, chosen_color="R")
            s.battlefield.append(p)
            execute_action(s, Action(ActionType.ACTIVATE_MANA_ABILITY, name, mana_choice=color))
            assert s.mana_pool[color] >= 1
    for fetch in ["Evolving Wilds", "Terramorphic Expanse"]:
        s = GameState(hand=[fetch], library=["Island", "Mountain"])
        execute_action(s, Action(ActionType.PLAY_LAND, fetch, timing="sorcery"))
        assert not validate_action(
            s, Action(ActionType.ACTIVATE_MANA_ABILITY, fetch, mana_choice="C")
        ).accepted
        execute_action(
            s, Action(ActionType.ACTIVATE_ABILITY, fetch, mana_cost={}, ability_id="basic_fetch")
        )
        assert any(p.name in {"Island", "Mountain"} and p.tapped for p in s.battlefield)


def test_bounce_filter_and_entry_tapped() -> None:
    s = GameState(hand=["Izzet Boilerworks"], battlefield=[Permanent("Island", {"Land"})])
    execute_action(s, Action(ActionType.PLAY_LAND, "Izzet Boilerworks", timing="sorcery"))
    assert (
        "Island" in s.hand
        and next(p for p in s.battlefield if p.name == "Izzet Boilerworks").tapped
    )
    s = GameState(hand=["Izzet Boilerworks"])
    execute_action(s, Action(ActionType.PLAY_LAND, "Izzet Boilerworks", timing="sorcery"))
    assert "Izzet Boilerworks" in s.hand
    s = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool())
    assert not validate_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="U")
    ).accepted
    s.mana_pool["R"] = 1
    execute_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="UR", choice="R")
    )
    assert s.mana_pool["U"] == 1 and s.mana_pool["R"] == 1
    s = GameState(hand=["Temple of Epiphany"])
    execute_action(s, Action(ActionType.PLAY_LAND, "Temple of Epiphany", timing="sorcery"))
    assert not validate_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Temple of Epiphany", mana_choice="U")
    ).accepted


def test_rocks_treasure_and_distinct_abilities() -> None:
    for rock in ROCKS:
        s = GameState(hand=[rock], mana_pool=pool(c=3, u=1, r=1))
        execute_action(
            s,
            Action(
                ActionType.CAST_SPELL,
                rock,
                mana_cost={"generic": 1} if rock == "Sol Ring" else {"generic": 2},
                timing="sorcery",
                origin_zone="hand",
            ),
        )
        assert any(p.name == rock for p in s.battlefield)
        execute_action(
            s,
            Action(
                ActionType.ACTIVATE_MANA_ABILITY,
                rock,
                mana_choice="U"
                if rock in {"Arcane Signet", "Fellwar Stone", "Izzet Signet"}
                else "C",
            ),
        )
    s = GameState(hand=["Wily Goblin"], mana_pool=pool(c=2, r=1))
    execute_action(
        s,
        Action(
            ActionType.CAST_SPELL,
            "Wily Goblin",
            mana_cost={"generic": 1, "R": 1},
            timing="sorcery",
            origin_zone="hand",
        ),
    )
    assert s.treasures == 1
    execute_action(s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Treasure", mana_choice="R"))
    assert s.treasures == 0 and s.mana_pool["R"] >= 1
    assert not validate_action(
        s, Action(ActionType.ACTIVATE_MANA_ABILITY, "Treasure", mana_choice="R")
    ).accepted
    assert not validate_action(
        GameState(battlefield=[Permanent("Izzet Signet", {"Artifact"})], mana_pool=pool()),
        Action(ActionType.ACTIVATE_MANA_ABILITY, "Izzet Signet", mana_choice="U"),
    ).accepted
    s = GameState(
        library=["X"], battlefield=[Permanent("Mind Stone", {"Artifact"})], mana_pool=pool(c=1)
    )
    execute_action(
        s,
        Action(
            ActionType.ACTIVATE_ABILITY, "Mind Stone", mana_cost={"generic": 1}, ability_id="draw"
        ),
    )
    assert "Mind Stone" in s.graveyard
    s = GameState(hand=["Ash Barrens"], library=["Mountain"], mana_pool=pool(c=1))
    execute_action(
        s,
        Action(
            ActionType.ACTIVATE_ABILITY,
            "Ash Barrens",
            mana_cost={"generic": 1},
            ability_id="basic_landcycling",
        ),
    )
    assert "Ash Barrens" in s.graveyard and "Mountain" in s.hand


def _cascade_actions(state: GameState):
    return [
        a
        for a in generate_legal_actions(state)
        if a.action_type is ActionType.ACTIVATE_MANA_ABILITY and a.source_name == "Cascade Bluffs"
    ]


def test_cascade_bluffs_filter_variants_record_input_and_output() -> None:
    land = Permanent("Cascade Bluffs", {"Land"})
    empty = GameState(battlefield=[land], mana_pool=pool())
    assert [(a.choice, a.mana_choice) for a in _cascade_actions(empty)] == [(None, "C")]

    u_only = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(u=1))
    assert {(a.choice, a.mana_choice) for a in _cascade_actions(u_only)} == {
        (None, "C"),
        ("U", "UU"),
        ("U", "UR"),
        ("U", "RR"),
    }

    r_only = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(r=1))
    assert {(a.choice, a.mana_choice) for a in _cascade_actions(r_only)} == {
        (None, "C"),
        ("R", "UU"),
        ("R", "UR"),
        ("R", "RR"),
    }

    both = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(u=1, r=1))
    assert {a.choice for a in _cascade_actions(both) if a.mana_choice == "RR"} == {"U", "R"}

    spend_r = GameState(
        battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(u=1, r=1)
    )
    execute_action(
        spend_r,
        Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="RR", choice="R"),
    )
    assert spend_r.mana_pool["U"] == 1 and spend_r.mana_pool["R"] == 2
    assert not _cascade_actions(spend_r)

    spend_u = GameState(
        battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(u=1, r=1)
    )
    execute_action(
        spend_u,
        Action(ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="RR", choice="U"),
    )
    assert spend_u.mana_pool["U"] == 0 and spend_u.mana_pool["R"] == 3


def test_cascade_bluffs_replay_preserves_exact_filter_choice() -> None:
    action = Action(
        ActionType.ACTIVATE_MANA_ABILITY, "Cascade Bluffs", mana_choice="RR", choice="R"
    )
    state = GameState(battlefield=[Permanent("Cascade Bluffs", {"Land"})], mana_pool=pool(u=1, r=1))
    execute_action(state, action)
    assert "action:activate_mana:Cascade Bluffs:R->RR" in state.event_log
    assert "mana_produced:Cascade Bluffs:R->RR" in state.event_log


def test_executable_coverage_requires_complete_collected_pytest_nodes() -> None:
    from mtg_sim.executable_adapters import AdapterRecord, validate_executable_coverage

    good = AdapterRecord(
        "Island",
        "adapter.island",
        "generate.island",
        "cost.island",
        "choices.island",
        "execute.island",
        ("hand", "battlefield"),
        ("rules_validated",),
        (
            "tests/test_phase9f4_creatures_combos_coverage.py::test_every_unique_card_generates_validated_executable_replayable_event[Island]",
        ),
        "EXECUTABLE",
    )
    assert not any(
        "Island integration test" in e for e in validate_executable_coverage({"Island": good})
    )
    bad_function = AdapterRecord(
        "Island",
        "adapter.island",
        "generate.island",
        "cost.island",
        "choices.island",
        "execute.island",
        ("hand", "battlefield"),
        ("rules_validated",),
        ("tests/test_phase9f4_creatures_combos_coverage.py::test_does_not_exist",),
        "EXECUTABLE",
    )
    assert any("not collected" in e for e in validate_executable_coverage({"Island": bad_function}))
    bad_param = AdapterRecord(
        "Island",
        "adapter.island",
        "generate.island",
        "cost.island",
        "choices.island",
        "execute.island",
        ("hand", "battlefield"),
        ("rules_validated",),
        (
            "tests/test_phase9f4_creatures_combos_coverage.py::test_every_unique_card_generates_validated_executable_replayable_event[Nope]",
        ),
        "EXECUTABLE",
    )
    assert any("not collected" in e for e in validate_executable_coverage({"Island": bad_param}))
    file_only = AdapterRecord(
        "Island",
        "adapter.island",
        "generate.island",
        "cost.island",
        "choices.island",
        "execute.island",
        ("hand", "battlefield"),
        ("rules_validated",),
        ("tests/test_phase9f4_creatures_combos_coverage.py",),
        "EXECUTABLE",
    )
    assert any(
        "complete pytest node ID" in e for e in validate_executable_coverage({"Island": file_only})
    )
    sem = AdapterRecord(
        "Island",
        "adapter.island",
        "generate.island",
        "cost.island",
        "choices.island",
        "execute.island",
        ("hand", "battlefield"),
        ("rules_validated",),
        ("SEM-fabricated",),
        "EXECUTABLE",
    )
    assert any(
        "complete pytest node ID" in e or "semantic" in e
        for e in validate_executable_coverage({"Island": sem})
    )
