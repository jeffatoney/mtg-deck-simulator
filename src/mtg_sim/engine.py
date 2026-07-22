"""Minimal deck-scoped rules engine for Malcolm/Breeches competency tests.

This is intentionally not a general Magic engine. It models only the zones,
legality checks, stack ordering, and card behaviors needed by the repository's
rules-competency gate. Unsupported placeholders fail closed when executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Callable, Literal


class RulesError(ValueError):
    """Raised when a requested game action is illegal or unsupported."""


class Phase(str, Enum):
    BEGINNING = "beginning"
    PRECOMBAT_MAIN = "precombat_main"
    COMBAT = "combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    ENDING = "ending"
    CLEANUP = "cleanup"


@dataclass(slots=True)
class Permanent:
    name: str
    types: set[str] = field(default_factory=set)
    subtypes: set[str] = field(default_factory=set)
    tapped: bool = False
    summoning_sick: bool = True
    attacking: bool = False
    enchanted_by_curiosity: bool = False
    damage_prevented: bool = False


@dataclass(slots=True)
class StackObject:
    name: str
    kind: Literal["spell", "ability", "trigger", "copy"]
    effect: Callable[["GameState"], None]
    targets: list[Permanent] = field(default_factory=list)
    cast: bool = True
    mana_value: int | None = None


@dataclass(slots=True)
class GameState:
    library: list[str] = field(default_factory=list)
    hand: list[str] = field(default_factory=list)
    battlefield: list[Permanent] = field(default_factory=list)
    graveyard: list[str] = field(default_factory=list)
    exile: list[str] = field(default_factory=list)
    command_zone: list[str] = field(
        default_factory=lambda: ["Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"]
    )
    stack: list[StackObject] = field(default_factory=list)
    phase: Phase = Phase.PRECOMBAT_MAIN
    turn: int = 1
    mana_pool: dict[str, int] = field(
        default_factory=lambda: {"C": 0, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0}
    )
    land_played: bool = False
    opponent_life: list[int] = field(default_factory=lambda: [40, 40, 40])
    treasures: int = 0
    attempted_empty_draw: bool = False
    lost: bool = False
    won: bool = False
    commander_casts: dict[str, int] = field(default_factory=dict)
    cards_drawn: int = 0
    cleanup_steps: int = 0
    event_log: list[str] = field(default_factory=list)

    def active_opponents(self) -> list[int]:
        return [idx for idx, life in enumerate(self.opponent_life) if life > 0]

    def check_state_based_actions(self) -> None:
        if self.attempted_empty_draw:
            self.lost = True
            self.event_log.append("state_based_action:empty_library_loss")
        for idx, life in enumerate(self.opponent_life):
            if life <= 0:
                self.event_log.append(f"state_based_action:opponent_{idx}_lost")
        if self.opponent_life and all(life <= 0 for life in self.opponent_life):
            self.won = True
            self.stack.clear()
            self.event_log.append("state_based_action:table_win")

    def draw(self, count: int = 1, *, optional: bool = False, decline: bool = False) -> None:
        for _ in range(count):
            if optional and decline:
                self.event_log.append("optional_draw_declined")
                continue
            if not self.library:
                self.attempted_empty_draw = True
                self.event_log.append("draw_attempt_empty_library")
                continue
            self.hand.append(self.library.pop(0))
            self.cards_drawn += 1
            self.event_log.append("draw")

    def resolve_top(self) -> None:
        if self.won or self.lost:
            return
        obj = self.stack.pop()
        self.event_log.append(f"resolve:{obj.name}")
        obj.effect(self)
        self.check_state_based_actions()

    def resolve_all(self) -> None:
        while self.stack and not (self.won or self.lost):
            self.resolve_top()

    def pay_mana(self, cost: dict[str, int]) -> None:
        pool = self.mana_pool
        generic = cost.get("C", 0)
        for color in ("U", "R", "W", "B", "G"):
            needed = cost.get(color, 0)
            if pool.get(color, 0) < needed:
                raise RulesError(f"insufficient {color} mana")
            pool[color] -= needed
        available_generic = sum(pool.values())
        if available_generic < generic:
            raise RulesError("insufficient generic mana")
        for color in ("C", "U", "R", "W", "B", "G"):
            spend = min(pool[color], generic)
            pool[color] -= spend
            generic -= spend
            if generic == 0:
                break


def shuffled_library(cards: list[str], seed: int) -> list[str]:
    result = list(cards)
    random.Random(seed).shuffle(result)
    return result


def create_malcolm_treasures_for_pirate_damage(
    state: GameState, damaged_by_pirate: dict[int, int], prevented: set[int] | None = None
) -> int:
    prevented = prevented or set()
    count = sum(
        1
        for idx in state.active_opponents()
        if damaged_by_pirate.get(idx, 0) > 0 and idx not in prevented
    )
    state.treasures += count
    state.event_log.append(f"malcolm_treasures:{count}")
    return count


def deal_pirate_combat_damage(
    state: GameState, sources: list[Permanent], opponents: list[int], amount: int = 1
) -> int:
    damaged: dict[int, int] = {}
    prevented: set[int] = set()
    for source, opponent in zip(sources, opponents, strict=True):
        if opponent not in state.active_opponents():
            continue
        if source.damage_prevented:
            prevented.add(opponent)
            continue
        state.opponent_life[opponent] -= amount
        damaged[opponent] = damaged.get(opponent, 0) + 1
    treasures = create_malcolm_treasures_for_pirate_damage(state, damaged, prevented)
    state.check_state_based_actions()
    return treasures


def activate_glint_horn(state: GameState, glint_horn: Permanent) -> None:
    if not glint_horn.attacking:
        raise RulesError("Glint-Horn Buccaneer can activate only while attacking")
    if not state.hand:
        raise RulesError("Glint-Horn activation requires a discarded card")
    state.pay_mana({"C": 1, "R": 1})
    discarded = state.hand.pop(0)
    state.graveyard.append(discarded)
    state.event_log.append("cost:discard")

    def draw_effect(s: GameState) -> None:
        s.draw(1)

    def damage_effect(s: GameState) -> None:
        for idx in s.active_opponents():
            s.opponent_life[idx] -= 1
        s.event_log.append("glint_horn_discard_damage")

    state.stack.append(StackObject("Glint-Horn draw ability", "ability", draw_effect, cast=False))
    state.stack.append(
        StackObject("Glint-Horn discard damage trigger", "trigger", damage_effect, cast=False)
    )


def curiosity_trigger(state: GameState, *, decline: bool) -> None:
    state.stack.append(
        StackObject(
            "Curiosity optional draw",
            "trigger",
            lambda s: s.draw(1, optional=True, decline=decline),
            cast=False,
        )
    )


def cleanup_step(state: GameState) -> None:
    state.phase = Phase.CLEANUP
    state.cleanup_steps += 1
    had_trigger = any(p.enchanted_by_curiosity for p in state.battlefield)
    if had_trigger:
        curiosity_trigger(state, decline=True)
        state.resolve_all()
        state.cleanup_steps += 1


def cast_twinflame(state: GameState, target: Permanent | None) -> StackObject:
    if target is None or target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Twinflame requires a legal original creature target")
    obj = StackObject("Twinflame", "spell", lambda _s: None, targets=[target], mana_value=2)
    state.stack.append(obj)
    return obj


def cast_dualcaster_mage(state: GameState) -> Permanent:
    if not any(obj.name in {"Twinflame", "Electroduplicate"} for obj in state.stack):
        raise RulesError("Dualcaster Mage must be cast while a copyable spell is on the stack")
    dualcaster = Permanent("Dualcaster Mage", {"Creature"}, {"Human", "Wizard"})
    state.battlefield.append(dualcaster)
    original = next(
        obj for obj in reversed(state.stack) if obj.name in {"Twinflame", "Electroduplicate"}
    )
    state.stack.append(
        StackObject(
            f"Copy of {original.name}",
            "copy",
            lambda _s: None,
            targets=[dualcaster],
            cast=False,
            mana_value=original.mana_value,
        )
    )
    return dualcaster


def flashback_electroduplicate(state: GameState, target: Permanent) -> None:
    if "Electroduplicate" not in state.graveyard:
        raise RulesError("Electroduplicate must be in graveyard to flash back")
    if target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Electroduplicate flashback requires a creature target")
    state.graveyard.remove("Electroduplicate")
    state.stack.append(
        StackObject("Electroduplicate", "spell", lambda _s: None, targets=[target], mana_value=3)
    )
    state.exile.append("Electroduplicate")


TRANSMUTE_VALUES = {"Drift of Phantasms": 3, "Muddle the Mixture": 2, "Dizzy Spell": 1}
WIZARDS = {"Dualcaster Mage", "Niv-Mizzet, the Firemind", "Vedalken Aethermage"}
MANA_VALUES = {"Twinflame": 2, "Electroduplicate": 3, "Curiosity": 1, "Niv-Mizzet, the Firemind": 6}


def transmute(state: GameState, card_name: str, target_name: str) -> str:
    if state.phase is not Phase.PRECOMBAT_MAIN and state.phase is not Phase.POSTCOMBAT_MAIN:
        raise RulesError("Transmute is sorcery speed")
    required = TRANSMUTE_VALUES[card_name]
    if MANA_VALUES.get(target_name) != required:
        raise RulesError(f"{card_name} can find only mana value {required}")
    return target_name


def wizardcycle(_state: GameState, target_name: str) -> str:
    if target_name not in WIZARDS:
        raise RulesError("Wizardcycling finds only Wizards")
    return target_name


def long_term_plans(state: GameState, target_name: str) -> None:
    if target_name not in state.library:
        raise RulesError("Long-Term Plans target must be in library")
    state.library.remove(target_name)
    state.library.insert(2, target_name)


def commander_cost(name: str, base_generic: int, state: GameState) -> int:
    return base_generic + 2 * state.commander_casts.get(name, 0)


def cast_commander(name: str, base_generic: int, state: GameState) -> int:
    cost = commander_cost(name, base_generic, state)
    state.commander_casts[name] = state.commander_casts.get(name, 0) + 1
    return cost


def cast_split_card(face: str) -> int:
    values = {"Invert": 1, "Invent": 6, "Commit": 4, "Memory": 6}
    if face not in values:
        raise RulesError("unknown split-card face")
    return values[face]


LAND_MANA = {"Island": "U", "Mountain": "R", "Command Tower": "U", "Shivan Reef": "U"}


def play_land(state: GameState, name: str) -> Permanent:
    if state.land_played:
        raise RulesError("only one land play per turn")
    land = Permanent(name, {"Land"})
    state.battlefield.append(land)
    state.land_played = True
    return land


def tap_for_mana(state: GameState, permanent: Permanent, color: str | None = None) -> None:
    if permanent.tapped:
        raise RulesError("permanent is already tapped")
    produced = color or LAND_MANA.get(permanent.name)
    if produced is None:
        raise RulesError(f"no mana behavior for {permanent.name}")
    permanent.tapped = True
    state.mana_pool[produced] += 1


def use_single_tutor_for_combo_halves() -> None:
    raise RulesError("one tutor cannot provide both halves of a combo")


def execute_placeholder(card_name: str) -> None:
    raise RulesError(f"placeholder behavior cannot be selected for deterministic line: {card_name}")
