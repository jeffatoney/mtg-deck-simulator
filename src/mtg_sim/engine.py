"""Minimal deck-scoped rules engine for Malcolm/Breeches competency tests.

This is intentionally not a general Magic engine. It models only the zones,
legality checks, stack ordering, and card behaviors needed by the repository's
rules-competency gate. Unsupported placeholders fail closed when executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable
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


MANA_TYPES = ("C", "W", "U", "B", "R", "G")
COLORED_MANA = ("W", "U", "B", "R", "G")
ManaCost = dict[str, int]


@dataclass(slots=True)
class Permanent:
    name: str
    types: set[str] = field(default_factory=set)
    subtypes: set[str] = field(default_factory=set)
    tapped: bool = False
    summoning_sick: bool = True
    haste: bool = False
    attacking: bool = False
    enchanted_by_curiosity: bool = False
    damage_prevented: bool = False
    is_token: bool = False
    mana_abilities: dict[str, tuple[str, ...]] = field(default_factory=dict)


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
    terminal: bool = False
    cleanup_trigger_pending: bool = False

    def ensure_not_terminal(self) -> None:
        if self.terminal or self.won or self.lost:
            raise RulesError("no actions are legal after terminal status")

    def active_opponents(self) -> list[int]:
        return [idx for idx, life in enumerate(self.opponent_life) if life > 0]

    def check_state_based_actions(self) -> None:
        if self.attempted_empty_draw:
            self.lost = True
            self.terminal = True
            self.event_log.append("state_based_action:empty_library_loss")
        for idx, life in enumerate(self.opponent_life):
            if life <= 0:
                self.event_log.append(f"state_based_action:opponent_{idx}_lost")
        if self.opponent_life and all(life <= 0 for life in self.opponent_life):
            self.won = True
            self.terminal = True
            self.stack.clear()
            self.event_log.append("state_based_action:table_win")

    def draw(self, count: int = 1, *, optional: bool = False, decline: bool = False) -> None:
        self.ensure_not_terminal()
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
        self.ensure_not_terminal()
        obj = self.stack.pop()
        self.event_log.append(f"resolve:{obj.name}")
        obj.effect(self)
        self.check_state_based_actions()

    def resolve_all(self) -> None:
        while self.stack and not (self.won or self.lost):
            self.resolve_top()

    def pay_mana(self, cost: ManaCost) -> None:
        self.ensure_not_terminal()
        self.mana_pool = solve_mana_payment(self.mana_pool, cost)

    def empty_mana_pool(self) -> None:
        self.mana_pool = empty_mana_pool()
        self.event_log.append("mana_pool_emptied")

    def advance_phase(self, phase: Phase) -> None:
        self.ensure_not_terminal()
        self.empty_mana_pool()
        self.phase = phase
        if phase is Phase.BEGINNING:
            self.land_played = False
            for permanent in self.battlefield:
                permanent.tapped = False
                permanent.attacking = False
                permanent.summoning_sick = False


def empty_mana_pool() -> dict[str, int]:
    return {mana_type: 0 for mana_type in MANA_TYPES}


def normalize_mana(values: ManaCost | None = None) -> dict[str, int]:
    pool = empty_mana_pool()
    if values:
        for mana_type, amount in values.items():
            if mana_type not in MANA_TYPES:
                raise RulesError(f"unsupported mana type: {mana_type}")
            if amount < 0:
                raise RulesError("mana amounts cannot be negative")
            pool[mana_type] = amount
    return pool


def solve_mana_payment(pool: ManaCost, cost: ManaCost) -> dict[str, int]:
    remaining = normalize_mana(pool)
    required = normalize_mana({k: v for k, v in cost.items() if k != "generic"})
    for color in COLORED_MANA:
        if remaining[color] < required[color]:
            raise RulesError(f"insufficient {color} mana")
        remaining[color] -= required[color]
    colorless_required = required["C"]
    if remaining["C"] < colorless_required:
        raise RulesError("insufficient colorless mana")
    remaining["C"] -= colorless_required
    generic_required = cost.get("generic", 0)
    if generic_required < 0:
        raise RulesError("generic mana cannot be negative")
    if sum(remaining.values()) < generic_required:
        raise RulesError("insufficient generic mana")
    for mana_type in MANA_TYPES:
        spent = min(remaining[mana_type], generic_required)
        remaining[mana_type] -= spent
        generic_required -= spent
        if generic_required == 0:
            return remaining
    return remaining


def shuffled_library(cards: list[str], seed: int) -> list[str]:
    result = list(cards)
    random.Random(seed).shuffle(result)
    return result


def create_treasure(state: GameState, count: int = 1) -> None:
    state.ensure_not_terminal()
    state.treasures += count
    state.event_log.append(f"treasure_created:{count}")


def sacrifice_treasure_for_mana(state: GameState, color: str) -> None:
    state.ensure_not_terminal()
    if color not in COLORED_MANA and color != "C":
        raise RulesError("Treasure can add only one mana of a legal type")
    if state.treasures <= 0:
        raise RulesError("no Treasure available to sacrifice")
    state.treasures -= 1
    state.mana_pool[color] = state.mana_pool.get(color, 0) + 1
    state.event_log.append(f"treasure_sacrificed_for:{color}")


def can_tap_creature(permanent: Permanent) -> bool:
    return not permanent.summoning_sick or permanent.haste


def declare_attackers(state: GameState, attackers: Iterable[Permanent]) -> None:
    state.ensure_not_terminal()
    state.phase = Phase.COMBAT
    for attacker in attackers:
        if attacker not in state.battlefield or "Creature" not in attacker.types:
            raise RulesError("attacker must be a creature on the battlefield")
        if attacker.tapped:
            raise RulesError("tapped creatures cannot be declared as attackers")
        if attacker.summoning_sick and not attacker.haste:
            raise RulesError("summoning sick creature cannot attack without haste")
    for attacker in attackers:
        attacker.tapped = True
        attacker.attacking = True
    state.event_log.append("declare_attackers")


def deal_damage(
    state: GameState,
    source: Permanent | str,
    opponents: Iterable[int],
    amount: int,
    *,
    combat: bool,
) -> None:
    state.ensure_not_terminal()
    if amount < 0:
        raise RulesError("damage cannot be negative")
    source_name = source.name if isinstance(source, Permanent) else source
    for opponent in opponents:
        if opponent not in state.active_opponents():
            continue
        prevented = isinstance(source, Permanent) and source.damage_prevented
        if prevented:
            state.event_log.append(f"damage_prevented:{source_name}:opponent_{opponent}")
            continue
        state.opponent_life[opponent] -= amount
        kind = "combat" if combat else "noncombat"
        state.event_log.append(f"{kind}_damage:{source_name}:opponent_{opponent}:{amount}")
    state.check_state_based_actions()


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
    state.ensure_not_terminal()
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
    state.ensure_not_terminal()
    if not glint_horn.attacking:
        raise RulesError("Glint-Horn Buccaneer can activate only while attacking")
    if not state.hand:
        raise RulesError("Glint-Horn activation requires a discarded card")
    state.pay_mana({"generic": 1, "R": 1})
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
    state.ensure_not_terminal()
    state.phase = Phase.CLEANUP
    state.cleanup_steps += 1
    had_trigger = state.cleanup_trigger_pending or any(
        p.enchanted_by_curiosity for p in state.battlefield
    )
    state.cleanup_trigger_pending = False
    if had_trigger:
        curiosity_trigger(state, decline=True)
        state.resolve_all()
        state.cleanup_steps += 1


def cast_twinflame(state: GameState, target: Permanent | None) -> StackObject:
    state.ensure_not_terminal()
    if target is None or target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Twinflame requires a legal original creature target")
    obj = StackObject("Twinflame", "spell", lambda _s: None, targets=[target], mana_value=2)
    state.stack.append(obj)
    return obj


def cast_dualcaster_mage(state: GameState) -> Permanent:
    state.ensure_not_terminal()
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
    state.ensure_not_terminal()
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
    state.ensure_not_terminal()
    if name not in state.command_zone:
        raise RulesError("commander must be in command zone to cast this helper")
    cost = commander_cost(name, base_generic, state)
    state.commander_casts[name] = state.commander_casts.get(name, 0) + 1
    state.command_zone.remove(name)
    state.stack.append(StackObject(name, "spell", lambda _s: None, mana_value=base_generic))
    return cost


def move_commander_to_zone(
    state: GameState, name: str, destination: str, *, choose_command_zone: bool
) -> None:
    state.ensure_not_terminal()
    if destination not in {"graveyard", "exile", "hand", "library"}:
        raise RulesError("unsupported commander destination")
    if choose_command_zone:
        if name not in state.command_zone:
            state.command_zone.append(name)
        state.event_log.append(f"commander_replacement:{name}:command_zone")
        return
    zone = getattr(state, destination)
    if isinstance(zone, list):
        zone.append(name)
    state.event_log.append(f"commander_moved:{name}:{destination}")


def cast_split_card(face: str) -> int:
    values = {"Invert": 1, "Invent": 6, "Commit": 4, "Memory": 6}
    if face not in values:
        raise RulesError("unknown split-card face")
    return values[face]


LAND_MANA = {
    "Island": ("U",),
    "Mountain": ("R",),
    "Command Tower": ("U", "R"),
    "Shivan Reef": ("U", "R", "C"),
}
ENTRY_TAPPED_LANDS = {"Izzet Guildgate", "Swiftwater Cliffs"}
CHOICE_TAPPED_LANDS = {"Riverglide Pathway"}


def play_land(state: GameState, name: str, *, enter_tapped: bool | None = None) -> Permanent:
    state.ensure_not_terminal()
    if state.land_played:
        raise RulesError("only one land play per turn")
    if enter_tapped is None:
        tapped = name in ENTRY_TAPPED_LANDS
    else:
        if name not in CHOICE_TAPPED_LANDS and enter_tapped:
            raise RulesError("this land has no choice-dependent tapped entry")
        tapped = enter_tapped
    land = Permanent(name, {"Land"}, tapped=tapped, summoning_sick=False)
    state.battlefield.append(land)
    state.land_played = True
    state.event_log.append(f"play_land:{name}:{'tapped' if tapped else 'untapped'}")
    return land


def tap_for_mana(state: GameState, permanent: Permanent, color: str | None = None) -> None:
    state.ensure_not_terminal()
    if permanent.tapped:
        raise RulesError("permanent is already tapped")
    possible = permanent.mana_abilities.get("tap") or LAND_MANA.get(permanent.name)
    if possible is None:
        raise RulesError(f"no mana behavior for {permanent.name}")
    produced = color or possible[0]
    if produced not in possible:
        raise RulesError(f"{permanent.name} cannot produce {produced}")
    if "Creature" in permanent.types and not can_tap_creature(permanent):
        raise RulesError("summoning sick creature cannot activate tap ability without haste")
    permanent.tapped = True
    state.mana_pool[produced] += 1
    state.event_log.append(f"tap_for_mana:{permanent.name}:{produced}")


def retarget_stack_object(
    obj: StackObject, new_targets: list[Permanent], battlefield: list[Permanent]
) -> None:
    if obj.name not in {
        "Twinflame",
        "Electroduplicate",
        "Copy of Twinflame",
        "Copy of Electroduplicate",
    }:
        raise RulesError("unsupported retargeting")
    if (
        len(new_targets) != 1
        or new_targets[0] not in battlefield
        or "Creature" not in new_targets[0].types
    ):
        raise RulesError("copy target must be a creature on the battlefield")
    obj.targets = new_targets


def use_single_tutor_for_combo_halves() -> None:
    raise RulesError("one tutor cannot provide both halves of a combo")


def execute_placeholder(card_name: str) -> None:
    raise RulesError(f"placeholder behavior cannot be selected for deterministic line: {card_name}")
