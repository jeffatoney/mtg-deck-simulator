from hypothesis import given, strategies as st
import pytest

from mtg_sim.phase5a_cards import (
    MANA,
    CardGameState,
    CardImplementationError,
    OpponentManaProfile,
    Permanent,
    activate_basic_fetch,
    activate_demolition_field,
    activate_izzet_signet,
    activate_mind_stone_draw,
    activate_prismatic_lens_filter,
    activate_scavenger_grounds,
    ash_barrens_basic_landcycling,
    chart_a_course,
    expedite,
    fact_or_fiction,
    faithless_looting,
    frantic_search,
    impulse,
    opt,
    play_land,
    sleight_of_hand,
    spectral_sailor_enters,
    storm_fleet_sprinter_enters,
    tap_for_mana,
    wily_goblin_enters,
)


def test_lands_and_opponent_mana_metadata_are_explicit():
    s = CardGameState(
        library=["Island", "Mountain"],
        hand=["Island"],
        opponent_mana_profile=OpponentManaProfile(frozenset({"G", "B"})),
    )
    tower = play_land(s, "Command Tower")
    tap_for_mana(s, tower, "U")
    assert s.mana_pool["U"] == 1
    orchard = Permanent("Exotic Orchard", {"Land"})
    s.battlefield.append(orchard)
    tap_for_mana(s, orchard, "G")
    assert s.mana_pool["G"] == 1
    with pytest.raises(CardImplementationError, match="metadata"):
        tap_for_mana(s, Permanent("Exotic Orchard", {"Land"}, controller="opponent_metadata"), "G")


def test_special_lands_entry_and_activated_abilities():
    s = CardGameState(library=["A", "Island", "Mountain"], hand=["Island"])
    snarl = play_land(s, "Frostboil Snarl", reveal_from_hand="Island")
    assert not snarl.tapped
    temple = play_land(s, "Temple of Epiphany", scry_bottom=True)
    assert temple.tapped and s.library[-1] == "A"
    island = Permanent("Island", {"Land"})
    s.battlefield.append(island)
    boiler = play_land(s, "Izzet Boilerworks", return_land=island)
    assert boiler.tapped and "Island" in s.hand and island not in s.battlefield
    thriving = play_land(s, "Thriving Isle", thriving_color="R")
    thriving.tapped = False
    tap_for_mana(s, thriving, "R")
    assert s.mana_pool["R"] == 1


def test_fetch_cycle_scavenger_demolition_and_filters():
    s = CardGameState(library=["Island", "Mountain", "X"], hand=["Ash Barrens"])
    s.mana_pool["C"] = 5
    ash_barrens_basic_landcycling(s, "Island")
    assert "Island" in s.hand and "Ash Barrens" in s.graveyard
    wilds = Permanent("Evolving Wilds", {"Land"})
    s.battlefield.append(wilds)
    activate_basic_fetch(s, wilds, "Mountain")
    assert any(p.name == "Mountain" and p.tapped for p in s.battlefield)
    desert = Permanent("Scavenger Grounds", {"Land"}, {"Desert"})
    s.battlefield.append(desert)
    s.graveyard.append("Card")
    activate_scavenger_grounds(s, desert, desert)
    assert s.graveyard == []
    demo = Permanent("Demolition Field", {"Land"})
    s.battlefield.append(demo)
    s.library.append("Island")
    activate_demolition_field(s, demo, "Island")
    assert any(p.name == "Island" and not p.tapped for p in s.battlefield)


def test_mana_rocks_and_creatures():
    s = CardGameState(library=["Drawn"])
    sol = Permanent("Sol Ring", {"Artifact"})
    s.battlefield.append(sol)
    tap_for_mana(s, sol, "C")
    assert s.mana_pool["C"] == 2
    signet = Permanent("Izzet Signet", {"Artifact"})
    s.battlefield.append(signet)
    activate_izzet_signet(s, signet)
    assert s.mana_pool["U"] == 1 and s.mana_pool["R"] == 1
    lens = Permanent("Prismatic Lens", {"Artifact"})
    s.battlefield.append(lens)
    activate_prismatic_lens_filter(s, lens, "G")
    assert s.mana_pool["G"] == 1
    mind = Permanent("Mind Stone", {"Artifact"})
    s.battlefield.append(mind)
    activate_mind_stone_draw(s, mind)
    assert "Drawn" in s.hand and "Mind Stone" in s.graveyard
    wily_goblin_enters(s)
    sailor = spectral_sailor_enters(s)
    sprinter = storm_fleet_sprinter_enters(s)
    assert s.treasures_created == 1 and sailor.flying and sprinter.haste and sprinter.unblockable


def test_draw_selection_and_flashback_cards():
    s = CardGameState(library=list("ABCDEFGHIJKLM"), hand=["Faithless Looting", "x", "y", "z"])
    chart_a_course(s, discard_name="A")
    assert "A" in s.graveyard
    target = Permanent("Storm Fleet Sprinter", {"Creature"})
    s.battlefield.append(target)
    expedite(s, target)
    assert target.haste
    opt(s, bottom=True)
    assert s.scry_count >= 1
    sleight_of_hand(s, 1)
    faithless_looting(s, ["x", "y"])
    assert "Faithless Looting" in s.graveyard
    s.graveyard.remove("Faithless Looting")
    s.graveyard.append("Faithless Looting")
    s.hand.extend(["m", "n"])
    faithless_looting(s, ["m", "n"], flashback=True)
    assert "Faithless Looting" in s.exile
    l1 = Permanent("Island", {"Land"}, tapped=True)
    s.battlefield.append(l1)
    s.hand.extend(["p", "q"])
    frantic_search(s, ["p", "q"], [l1])
    assert not l1.tapped
    impulse(s, 0)
    assert len(s.hand) > 0


def test_fact_or_fiction_uses_minimizing_opponent_policy():
    s = CardGameState(library=["best", "good", "bad", "land", "combo"])
    hand, grave = fact_or_fiction(s, {"best": 10, "combo": 9, "good": 3, "bad": 0, "land": 1})
    assert hand == ()
    assert set(grave) == {"best", "good", "bad", "land", "combo"}


@given(st.lists(st.sampled_from(list(MANA)), min_size=1, max_size=6, unique=True))
def test_opponent_mana_profile_property(colors):
    s = CardGameState(opponent_mana_profile=OpponentManaProfile(frozenset(colors)))
    p = Permanent("Fellwar Stone", {"Artifact"})
    s.battlefield.append(p)
    tap_for_mana(s, p, colors[0])
    assert s.mana_pool[colors[0]] == 1
