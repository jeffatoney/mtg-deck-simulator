import pytest

from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    RulesError,
    execute_action,
    generate_legal_actions,
)
from mtg_sim.executable_adapters import adapter_registry, write_report


def pool(c=10, u=10, r=10):
    return {"C": c, "U": u, "R": r, "W": 0, "B": 0, "G": 0}


ASSIGNED = [
    "Chart a Course",
    "Expedite",
    "Fact or Fiction",
    "Faithless Looting",
    "Frantic Search",
    "Impulse",
    "Opt",
    "Sleight of Hand",
    "Prismari Command",
    "Long-Term Plans",
    "Dizzy Spell",
    "Drift of Phantasms",
    "Muddle the Mixture",
    "Vedalken Aethermage",
    "Step Through",
    "Rebuild",
]


@pytest.mark.parametrize("card", ASSIGNED)
def test_assigned_cards_have_legal_actions_and_handlers(card):
    s = GameState(
        hand=[card, "x", "y"],
        library=["Curiosity", "Twinflame", "Dualcaster Mage", "Island", "Mountain", "Opt"],
        battlefield=[
            Permanent("Storm Fleet Sprinter", {"Creature"}, power=1, toughness=3),
            Permanent("Island", {"Land"}, tapped=True),
        ],
        mana_pool=pool(),
    )
    actions = [a for a in generate_legal_actions(s) if a.source_name == card]
    assert actions, card
    execute_action(s, actions[0])
    needle = actions[0].ability_id or card
    assert any(needle in e for e in s.event_log)


def test_tutor_restrictions_and_one_card_only():
    s = GameState(hand=["Muddle the Mixture"], library=["Twinflame", "Curiosity"], mana_pool=pool())
    execute_action(s, next(a for a in generate_legal_actions(s) if a.choice == "Twinflame"))
    assert "Twinflame" in s.hand and "Curiosity" not in s.hand
    with pytest.raises(RulesError):
        execute_action(
            GameState(hand=["Muddle the Mixture"], library=["Curiosity"], mana_pool=pool()),
            Action(
                ActionType.ACTIVATE_ABILITY,
                "Muddle the Mixture",
                mana_cost={"generic": 1, "U": 2},
                ability_id="transmute",
                choice="Curiosity",
                timing="sorcery",
            ),
        )


def test_long_term_plans_exact_third_from_top_no_placeholder():
    s = GameState(
        hand=["Long-Term Plans"], library=["A", "B", "Dualcaster Mage", "C"], mana_pool=pool()
    )
    execute_action(
        s,
        next(
            a
            for a in generate_legal_actions(s)
            if a.source_name == "Long-Term Plans" and a.choice == "Dualcaster Mage"
        ),
    )
    s.resolve_all()
    assert s.library[2] == "Dualcaster Mage"
    assert all("placeholder" not in c.lower() and "empty slot" not in c.lower() for c in s.library)


def test_flashback_aftermath_and_split_faces():
    s = GameState(
        graveyard=["Faithless Looting"], hand=["a", "b"], library=["c", "d"], mana_pool=pool()
    )
    execute_action(
        s, next(a for a in generate_legal_actions(s) if a.source_name == "Faithless Looting")
    )
    s.resolve_all()
    assert "Faithless Looting" in s.exile
    s = GameState(graveyard=["Commit // Memory"], library=list("abcdefghij"), mana_pool=pool())
    a = next(a for a in generate_legal_actions(s) if a.source_name == "Commit // Memory")
    execute_action(s, a)
    assert s.stack[-1].chosen_face == "Memory" and s.stack[-1].mana_value == 6
    s.resolve_all()
    assert "Commit // Memory" in s.exile


def test_fact_or_fiction_records_partitions_and_future_hidden_selection():
    s = GameState(
        hand=["Fact or Fiction"],
        library=["best", "good", "bad", "land", "combo", "hidden"],
        mana_pool=pool(),
    )
    execute_action(
        s, next(a for a in generate_legal_actions(s) if a.source_name == "Fact or Fiction")
    )
    s.resolve_all()
    assert any(
        e.startswith("fact_or_fiction_revealed:best,good,bad,land,combo") for e in s.event_log
    )
    assert sum(e.startswith("fact_or_fiction_partition") for e in s.event_log) == 32
    assert not any("hidden" in e for e in s.event_log if "selection" in e or "partition" in e)


def test_adapter_coverage_executable(tmp_path):
    reg = adapter_registry()
    for card in [
        *ASSIGNED,
        "Commit // Memory",
        "Invert // Invent",
        "Ash Barrens",
        "Demolition Field",
        "Evolving Wilds",
        "Terramorphic Expanse",
        "Mind Stone",
        "Spectral Sailor",
    ]:
        assert reg[card].status == "EXECUTABLE"
    report = write_report(tmp_path / "coverage.json")
    assert report["executable_adapter_count"] >= 44
