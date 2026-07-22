"""Phase 5A deck-scoped card implementations for mana, lands, and selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

COLORS = ("W", "U", "B", "R", "G")
MANA = ("C", *COLORS)
COMMANDER_COLOR_IDENTITY = frozenset({"U", "R"})
COMMANDER_TYPES = frozenset({"Siren", "Pirate", "Goblin"})
BASIC_LANDS = {"Island": "U", "Mountain": "R"}
ASSIGNED_CARDS = frozenset(
    {
        "Ash Barrens",
        "Cascade Bluffs",
        "Command Tower",
        "Demolition Field",
        "Evolving Wilds",
        "Exotic Orchard",
        "Frostboil Snarl",
        "Island",
        "Izzet Boilerworks",
        "Mountain",
        "Path of Ancestry",
        "Scavenger Grounds",
        "Shivan Reef",
        "Temple of Epiphany",
        "Terramorphic Expanse",
        "Thriving Isle",
        "Arcane Signet",
        "Fellwar Stone",
        "Izzet Signet",
        "Mind Stone",
        "Prismatic Lens",
        "Sol Ring",
        "Wily Goblin",
        "Chart a Course",
        "Expedite",
        "Fact or Fiction",
        "Faithless Looting",
        "Frantic Search",
        "Impulse",
        "Opt",
        "Sleight of Hand",
        "Spectral Sailor",
        "Storm Fleet Sprinter",
        "Abrade",
        "Aetherize",
        "Arcane Denial",
        "Brotherhood's End",
        "By Force",
        "Change the Equation",
        "Curse of the Swine",
        "Dispel",
        "Echoing Truth",
        "Fading Hope",
        "Fiery Cannonade",
        "Into the Roil",
        "Introduction to Annihilation",
        "Lazotep Plating",
        "Negate",
        "Prismari Command",
        "Ravenform",
        "Reality Ripple",
        "Reality Shift",
        "Resculpt",
        "Sentinel Totem",
        "Siren Stormtamer",
        "Soul-Guide Lantern",
        "Spell Pierce",
        "Syncopate",
        "Vandalblast",
        "Wash Away",
    }
)


class CardImplementationError(ValueError):
    """Raised when a Phase 5A card action is illegal or not explicitly modeled."""


@dataclass(slots=True)
class Permanent:
    name: str
    types: set[str]
    subtypes: set[str] = field(default_factory=set)
    tapped: bool = False
    chosen_color: str | None = None
    haste: bool = False
    flying: bool = False
    unblockable: bool = False
    controller: Literal["self", "opponent_metadata"] = "self"


@dataclass(frozen=True, slots=True)
class OpponentManaProfile:
    colors: frozenset[str]

    def __post_init__(self) -> None:
        invalid = self.colors.difference(MANA)
        if invalid:
            raise CardImplementationError(f"invalid opponent mana colors: {sorted(invalid)}")


@dataclass(slots=True)
class CardGameState:
    library: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    battlefield: list[Permanent] = field(default_factory=list)
    graveyard: list[str] = field(default_factory=list)
    exile: list[str] = field(default_factory=list)
    mana_pool: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MANA, 0))
    life: int = 40
    attacked_this_turn: bool = False
    scry_count: int = 0
    treasures_created: int = 0
    opponent_mana_profile: OpponentManaProfile = field(
        default_factory=lambda: OpponentManaProfile(frozenset({"U", "R"}))
    )

    def draw(self, count: int) -> None:
        if count < 0 or count > len(self.library):
            raise CardImplementationError("cannot draw requested number of cards")
        for _ in range(count):
            self.hand.append(self.library.pop(0))


def _check_color(color: str, allowed: frozenset[str] | tuple[str, ...] = MANA) -> None:
    if color not in allowed:
        raise CardImplementationError(f"illegal mana color: {color}")


def _tap(permanent: Permanent) -> None:
    if permanent.controller != "self":
        raise CardImplementationError("opponent mana metadata is not a targetable permanent")
    if permanent.tapped:
        raise CardImplementationError("permanent is already tapped")
    permanent.tapped = True


def _pay_generic(state: CardGameState, amount: int) -> None:
    if sum(state.mana_pool.values()) < amount:
        raise CardImplementationError("insufficient mana")
    remaining = amount
    for color in MANA:
        spent = min(state.mana_pool[color], remaining)
        state.mana_pool[color] -= spent
        remaining -= spent
        if remaining == 0:
            return


def play_land(
    state: CardGameState,
    name: str,
    *,
    reveal_from_hand: str | None = None,
    thriving_color: str | None = None,
    return_land: Permanent | None = None,
    scry_bottom: bool = False,
) -> Permanent:
    tapped = name in {
        "Izzet Boilerworks",
        "Path of Ancestry",
        "Temple of Epiphany",
        "Thriving Isle",
    }
    chosen = None
    if name == "Frostboil Snarl":
        if reveal_from_hand is not None and (
            reveal_from_hand not in state.hand or reveal_from_hand not in {"Island", "Mountain"}
        ):
            raise CardImplementationError(
                "Frostboil Snarl reveal requires Island or Mountain in hand"
            )
        tapped = reveal_from_hand is None
    if name == "Thriving Isle":
        if thriving_color is None or thriving_color == "U":
            raise CardImplementationError("Thriving Isle must choose a nonblue color")
        _check_color(thriving_color, COLORS)
        chosen = thriving_color
    permanent = Permanent(name, {"Land"}, tapped=tapped, chosen_color=chosen)
    state.battlefield.append(permanent)
    if name == "Temple of Epiphany":
        scry(state, 1, bottom=scry_bottom)
    if name == "Izzet Boilerworks":
        if (
            return_land is None
            or return_land not in state.battlefield
            or "Land" not in return_land.types
        ):
            raise CardImplementationError(
                "Izzet Boilerworks trigger must return a land you control"
            )
        state.battlefield.remove(return_land)
        state.hand.append(return_land.name)
    return permanent


def tap_for_mana(state: CardGameState, permanent: Permanent, color: str = "C") -> None:
    _check_color(color)
    name = permanent.name
    allowed: frozenset[str]
    amount = 1
    pain = False
    if name == "Island":
        allowed = frozenset({"U"})
    elif name == "Mountain":
        allowed = frozenset({"R"})
    elif name in {"Command Tower", "Arcane Signet", "Path of Ancestry"}:
        allowed = COMMANDER_COLOR_IDENTITY
    elif name in {"Exotic Orchard", "Fellwar Stone"}:
        allowed = permanent_mana_metadata_colors(state)
    elif name in {"Ash Barrens", "Scavenger Grounds", "Demolition Field", "Prismatic Lens"}:
        allowed = frozenset({"C"})
    elif name == "Sol Ring":
        allowed, amount = frozenset({"C"}), 2
    elif name in {"Frostboil Snarl", "Temple of Epiphany"}:
        allowed = COMMANDER_COLOR_IDENTITY
    elif name == "Shivan Reef":
        allowed = frozenset({"C", "U", "R"})
        pain = color in {"U", "R"}
    elif name == "Thriving Isle":
        if permanent.chosen_color is None:
            raise CardImplementationError("Thriving Isle has no chosen color")
        allowed = frozenset({"U", permanent.chosen_color})
    else:
        raise CardImplementationError(f"no mana implementation for {name}")
    if color not in allowed:
        raise CardImplementationError(f"{name} cannot produce {color}")
    _tap(permanent)
    state.mana_pool[color] += amount
    if pain:
        state.life -= 1


def permanent_mana_metadata_colors(state: CardGameState) -> frozenset[str]:
    return state.opponent_mana_profile.colors


def activate_cascade_bluffs(
    state: CardGameState, permanent: Permanent, output: tuple[str, str]
) -> None:
    if output not in {("U", "U"), ("U", "R"), ("R", "R")}:
        raise CardImplementationError("Cascade Bluffs must produce UU, UR, or RR")
    if state.mana_pool["U"] + state.mana_pool["R"] < 1:
        raise CardImplementationError("Cascade Bluffs filter requires U/R input")
    if state.mana_pool["U"]:
        state.mana_pool["U"] -= 1
    else:
        state.mana_pool["R"] -= 1
    _tap(permanent)
    for c in output:
        state.mana_pool[c] += 1


def activate_izzet_signet(state: CardGameState, permanent: Permanent) -> None:
    _pay_generic(state, 1)
    _tap(permanent)
    state.mana_pool["U"] += 1
    state.mana_pool["R"] += 1


def activate_prismatic_lens_filter(state: CardGameState, permanent: Permanent, color: str) -> None:
    _check_color(color)
    _pay_generic(state, 1)
    _tap(permanent)
    state.mana_pool[color] += 1


def activate_mind_stone_draw(state: CardGameState, permanent: Permanent) -> None:
    _pay_generic(state, 1)
    _tap(permanent)
    if permanent not in state.battlefield:
        raise CardImplementationError("Mind Stone must be on battlefield")
    state.battlefield.remove(permanent)
    state.graveyard.append("Mind Stone")
    state.draw(1)


def activate_basic_fetch(state: CardGameState, permanent: Permanent, basic_name: str) -> None:
    if basic_name not in BASIC_LANDS or basic_name not in state.library:
        raise CardImplementationError("fetch requires a basic land in library")
    _tap(permanent)
    state.battlefield.remove(permanent)
    state.graveyard.append(permanent.name)
    state.library.remove(basic_name)
    state.battlefield.append(Permanent(basic_name, {"Land"}, {basic_name}, tapped=True))


def ash_barrens_basic_landcycling(state: CardGameState, basic_name: str) -> None:
    _pay_generic(state, 1)
    if (
        "Ash Barrens" not in state.hand
        or basic_name not in BASIC_LANDS
        or basic_name not in state.library
    ):
        raise CardImplementationError(
            "basic landcycling requires Ash Barrens in hand and a basic in library"
        )
    state.hand.remove("Ash Barrens")
    state.graveyard.append("Ash Barrens")
    state.library.remove(basic_name)
    state.hand.append(basic_name)


def activate_scavenger_grounds(
    state: CardGameState, permanent: Permanent, desert: Permanent
) -> None:
    _pay_generic(state, 2)
    _tap(permanent)
    if desert not in state.battlefield or "Desert" not in desert.subtypes:
        raise CardImplementationError("Scavenger Grounds requires sacrificing a Desert")
    state.battlefield.remove(desert)
    state.graveyard.clear()


def activate_demolition_field(state: CardGameState, permanent: Permanent, basic_name: str) -> None:
    _pay_generic(state, 2)
    _tap(permanent)
    if basic_name not in BASIC_LANDS or basic_name not in state.library:
        raise CardImplementationError("Demolition Field self-search requires a basic land")
    state.battlefield.remove(permanent)
    state.graveyard.append("Demolition Field")
    state.library.remove(basic_name)
    state.battlefield.append(Permanent(basic_name, {"Land"}, {basic_name}))


def scry(state: CardGameState, count: int, *, bottom: bool) -> None:
    if count != 1 or not state.library:
        if count < 0:
            raise CardImplementationError("negative scry")
        return
    state.scry_count += count
    if bottom:
        state.library.append(state.library.pop(0))


def cast_creature_with_path_mana(state: CardGameState, creature_types: set[str]) -> None:
    if creature_types & COMMANDER_TYPES:
        scry(state, 1, bottom=False)


def wily_goblin_enters(state: CardGameState) -> Permanent:
    p = Permanent("Wily Goblin", {"Creature"}, {"Goblin", "Pirate"})
    state.battlefield.append(p)
    state.treasures_created += 1
    state.battlefield.append(Permanent("Treasure", {"Artifact"}, {"Treasure"}))
    return p


def spectral_sailor_enters(state: CardGameState) -> Permanent:
    p = Permanent("Spectral Sailor", {"Creature"}, {"Spirit", "Pirate"}, flying=True)
    state.battlefield.append(p)
    return p


def activate_spectral_sailor_draw(state: CardGameState) -> None:
    _pay_generic(state, 3)
    if state.mana_pool["U"] < 1:
        raise CardImplementationError("Spectral Sailor draw requires U")
    state.mana_pool["U"] -= 1
    state.draw(1)


def storm_fleet_sprinter_enters(state: CardGameState) -> Permanent:
    p = Permanent(
        "Storm Fleet Sprinter", {"Creature"}, {"Human", "Pirate"}, haste=True, unblockable=True
    )
    state.battlefield.append(p)
    return p


def discard(state: CardGameState, names: list[str]) -> None:
    for name in names:
        if name not in state.hand:
            raise CardImplementationError(f"cannot discard missing card: {name}")
        state.hand.remove(name)
        state.graveyard.append(name)


def chart_a_course(state: CardGameState, discard_name: str | None = None) -> None:
    state.draw(2)
    if not state.attacked_this_turn:
        if discard_name is None:
            raise CardImplementationError("Chart a Course requires a discard without raid")
        discard(state, [discard_name])


def expedite(state: CardGameState, target: Permanent) -> None:
    if target not in state.battlefield or "Creature" not in target.types:
        raise CardImplementationError("Expedite requires target creature")
    target.haste = True
    state.draw(1)


def opt(state: CardGameState, *, bottom: bool) -> None:
    scry(state, 1, bottom=bottom)
    state.draw(1)


def sleight_of_hand(state: CardGameState, choose_index: int) -> None:
    if len(state.library) < 2 or choose_index not in {0, 1}:
        raise CardImplementationError("Sleight of Hand needs two cards and a legal choice")
    seen = [state.library.pop(0), state.library.pop(0)]
    state.hand.append(seen[choose_index])
    state.library.append(seen[1 - choose_index])


def faithless_looting(
    state: CardGameState, discards: list[str], *, flashback: bool = False
) -> None:
    zone = state.graveyard if flashback else state.hand
    if "Faithless Looting" not in zone:
        raise CardImplementationError("Faithless Looting is not in the required zone")
    zone.remove("Faithless Looting")
    state.draw(2)
    discard(state, discards)
    (state.exile if flashback else state.graveyard).append("Faithless Looting")


def frantic_search(
    state: CardGameState, discards: list[str], lands_to_untap: list[Permanent]
) -> None:
    state.draw(2)
    discard(state, discards)
    if len(lands_to_untap) > 3 or any(
        p not in state.battlefield or "Land" not in p.types for p in lands_to_untap
    ):
        raise CardImplementationError("Frantic Search untaps up to three lands you control")
    for land in lands_to_untap:
        land.tapped = False


def impulse(state: CardGameState, choose_index: int) -> None:
    seen_count = min(4, len(state.library))
    if choose_index < 0 or choose_index >= seen_count:
        raise CardImplementationError("Impulse choice outside looked-at cards")
    seen = [state.library.pop(0) for _ in range(seen_count)]
    state.hand.append(seen.pop(choose_index))
    state.library.extend(seen)


def fact_or_fiction(
    state: CardGameState, values: dict[str, int]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    seen = [state.library.pop(0) for _ in range(min(5, len(state.library)))]
    best_hand: tuple[str, ...] | None = None
    best_grave: tuple[str, ...] | None = None
    best_value: int | None = None
    for r in range(len(seen) + 1):
        for idxs in combinations(range(len(seen)), r):
            pile_a = tuple(seen[i] for i in idxs)
            pile_b = tuple(c for i, c in enumerate(seen) if i not in idxs)
            chosen = min(
                (pile_a, pile_b),
                key=lambda pile: (sum(values.get(c, 0) for c in pile), len(pile), pile),
            )
            value = sum(values.get(c, 0) for c in chosen)
            if best_value is None or (value, len(chosen), chosen) < (
                best_value,
                len(best_hand or ()),
                best_hand or (),
            ):  # minimizing opponent
                best_value = value
                best_hand = chosen
                best_grave = pile_b if chosen == pile_a else pile_a
    assert best_hand is not None and best_grave is not None
    state.hand.extend(best_hand)
    state.graveyard.extend(best_grave)
    return best_hand, best_grave
