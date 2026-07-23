"""Minimal deck-scoped rules engine for Malcolm/Breeches competency tests.

This is intentionally not a general Magic engine. It models only the zones,
legality checks, stack ordering, and card behaviors needed by the repository's
rules-competency gate. Unsupported placeholders fail closed when executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Callable, Literal, TypeAlias, cast


class RulesError(ValueError):
    """Raised when a requested game action is illegal or unsupported."""


MANA_TYPES = ("C", "U", "R", "W", "B", "G")
COLORED_MANA = ("U", "R", "W", "B", "G")
ManaCost: TypeAlias = dict[str, int]


class ActionType(str, Enum):
    CAST_SPELL = "cast_spell"
    ACTIVATE_ABILITY = "activate_ability"
    PLAY_LAND = "play_land"
    ACTIVATE_MANA_ABILITY = "activate_mana_ability"
    PASS_PRIORITY = "pass_priority"
    DECLARE_ATTACKERS = "declare_attackers"
    COMBAT_DAMAGE = "combat_damage"


@dataclass(frozen=True, slots=True)
class Action:
    action_type: ActionType
    source_name: str | None = None
    targets: tuple[Permanent, ...] = ()
    mana_cost: ManaCost | None = None
    additional_costs: tuple[str, ...] = ()
    timing: Literal["instant", "sorcery"] = "instant"
    effect: Callable[["GameState"], None] | None = None
    optional_draw_decline: bool = False
    mana_choice: str | None = None
    ability_id: str | None = None
    origin_zone: str | None = None
    choice: str | None = None
    modes: tuple[str, ...] = ()
    stack_target: StackObject | None = None
    x_value: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    errors: tuple[str, ...] = ()
    rules_refs: tuple[str, ...] = ()
    normalized_action: Action | None = None


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
    haste: bool = False
    is_token: bool = False
    mana_abilities: dict[str, str] = field(default_factory=dict)
    power: int | None = None
    toughness: int | None = None
    mana_value: int = 0
    controller: int = 0
    damage: int = 0
    flying: bool = False
    phased_out: bool = False
    hexproof_until_eot: bool = False
    manifested_card: str | None = None
    chosen_color: str | None = None
    entered_turn: int = 0
    defending_opponent: int = 0


@dataclass(slots=True)
class StackObject:
    name: str
    kind: Literal["spell", "ability", "trigger", "copy"]
    effect: Callable[["GameState"], None]
    targets: list[Permanent] = field(default_factory=list)
    cast: bool = True
    mana_value: int | None = None
    legal_targets: Callable[["GameState", list[Permanent]], bool] | None = None
    types: set[str] = field(default_factory=set)
    colors: set[str] = field(default_factory=set)
    cast_from_hand: bool = True
    targets_player: bool = False
    chosen_face: str | None = None


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
    mana_pool: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MANA_TYPES, 0))
    land_played: bool = False
    opponent_life: list[int] = field(default_factory=lambda: [40, 40, 40])
    treasures: int = 0
    command_zone_replacements: dict[str, bool] = field(default_factory=dict)
    attempted_empty_draw: bool = False
    lost: bool = False
    won: bool = False
    commander_casts: dict[str, int] = field(default_factory=dict)
    cards_drawn: int = 0
    cleanup_steps: int = 0
    event_log: list[str] = field(default_factory=list)
    pending_triggers: list[StackObject] = field(default_factory=list)
    resolving: bool = False
    priority_player: int = 0
    self_hexproof_until_eot: bool = False
    breeches_unknown_exiled: list[str] = field(default_factory=list)

    def record_event(self, event_type: str, detail: str = "") -> None:
        self.event_log.append(f"{event_type}:{detail}" if detail else event_type)

    @property
    def terminal(self) -> bool:
        return self.won or self.lost

    def active_opponents(self) -> list[int]:
        return [idx for idx, life in enumerate(self.opponent_life) if life > 0]

    def check_state_based_actions(self) -> None:
        if self.resolving:
            raise RulesError("state-based actions cannot be checked during resolution")
        self.record_event("state_based_action_check")
        if self.attempted_empty_draw:
            self.lost = True
            self.record_event("state_based_action", "empty_library_loss")
        for permanent in list(self.battlefield):
            if "Creature" in permanent.types:
                toughness = permanent.toughness
                if toughness is None and permanent.name in CREATURE_STATS:
                    toughness = CREATURE_STATS[permanent.name][1]
                if toughness is not None and (toughness <= 0 or permanent.damage >= toughness):
                    self.battlefield.remove(permanent)
                    if permanent.is_token:
                        self.record_event(
                            "state_based_action", f"token_creature_removed:{permanent.name}"
                        )
                    else:
                        self.graveyard.append(permanent.name)
                        self.record_event(
                            "state_based_action", f"creature_destroyed:{permanent.name}"
                        )
        for idx, life in enumerate(self.opponent_life):
            if life <= 0:
                self.record_event("state_based_action", f"opponent_{idx}_lost")
        if self.opponent_life and all(life <= 0 for life in self.opponent_life):
            self.won = True
            self.stack.clear()
            self.record_event("state_based_action", "table_win")

    def draw(self, count: int = 1, *, optional: bool = False, decline: bool = False) -> None:
        for _ in range(count):
            if optional and decline:
                self.record_event("optional_draw_declined")
                continue
            if not self.library:
                self.attempted_empty_draw = True
                self.record_event("draw_attempt_empty_library")
                continue
            self.hand.append(self.library.pop(0))
            self.cards_drawn += 1
            self.record_event("draw")
            for permanent in list(self.battlefield):
                if permanent.name == "Psychosis Crawler":
                    for opponent in self.active_opponents():
                        self.opponent_life[opponent] -= 1
                    self.record_event("life_lost", "Psychosis Crawler:1")
                if permanent.name == "Niv-Mizzet, the Firemind":
                    target = self.active_opponents()[:1]
                    if target:
                        deal_noncombat_damage(
                            self, target, 1, source_name="Niv-Mizzet, the Firemind"
                        )

    def would_receive_priority(self) -> None:
        if self.terminal:
            return
        self.check_state_based_actions()
        while self.pending_triggers and not self.terminal:
            self.place_pending_triggers_on_stack()
            self.check_state_based_actions()
        self.record_event("priority", f"player_{self.priority_player}")

    def place_pending_triggers_on_stack(self) -> None:
        while self.pending_triggers:
            trigger = self.pending_triggers.pop(0)
            self.stack.append(trigger)
            self.record_event("trigger_put_on_stack", trigger.name)

    def resolve_top(self) -> None:
        if self.won or self.lost:
            return
        obj = self.stack.pop()
        if obj.legal_targets is not None and not obj.legal_targets(self, obj.targets):
            self.record_event("resolution_countered_illegal_targets", obj.name)
            self.would_receive_priority()
            return
        self.record_event("resolve", obj.name)
        self.resolving = True
        try:
            obj.effect(self)
        finally:
            self.resolving = False
        if (
            obj.kind == "spell"
            and ("Creature" in obj.types or "Artifact" in obj.types)
            and obj.name not in self.graveyard
            and obj.name not in self.exile
        ):
            self.battlefield.append(_permanent_for_card(obj.name))
            if obj.name == "Wily Goblin":
                create_treasure(self, 1)
            if obj.name == "Dualcaster Mage":
                self.pending_triggers.append(
                    StackObject(
                        "Dualcaster Mage copy trigger",
                        "trigger",
                        lambda ss: ss.record_event("dualcaster_trigger_resolved"),
                        cast=False,
                    )
                )
        elif obj.kind == "spell" and obj.name not in self.graveyard and obj.name not in self.exile:
            self.graveyard.append(obj.name)
        self.would_receive_priority()

    def resolve_all(self) -> None:
        while self.stack and not (self.won or self.lost):
            self.resolve_top()

    def pay_mana(self, cost: ManaCost) -> None:
        payment = solve_mana_payment(self.mana_pool, cost)
        if payment is None:
            raise RulesError("insufficient mana")
        for mana_type, amount in payment.items():
            self.mana_pool[mana_type] -= amount
        self.record_event("mana_paid", str(normalize_mana(cost)))

    def empty_mana_pool(self) -> None:
        if any(self.mana_pool.values()):
            self.record_event("mana_pool_emptied")
        self.mana_pool = dict.fromkeys(MANA_TYPES, 0)

    def advance_phase(self, phase: Phase) -> None:
        if phase is not self.phase:
            self.empty_mana_pool()
        self.phase = phase

    def advance_step(self) -> None:
        self.empty_mana_pool()


def normalize_mana(cost: ManaCost | None) -> ManaCost:
    normalized = {mana_type: 0 for mana_type in MANA_TYPES}
    normalized["generic"] = 0
    for mana_type, amount in (cost or {}).items():
        if mana_type not in normalized:
            raise RulesError(f"unknown mana symbol: {mana_type}")
        if amount < 0:
            raise RulesError("mana costs cannot be negative")
        normalized[mana_type] += amount
    return normalized


def solve_mana_payment(pool: ManaCost, cost: ManaCost) -> ManaCost | None:
    normalized_pool = {mana_type: pool.get(mana_type, 0) for mana_type in MANA_TYPES}
    normalized_cost = normalize_mana(cost)
    payment = {mana_type: 0 for mana_type in MANA_TYPES}
    for mana_type in MANA_TYPES:
        required = normalized_cost[mana_type]
        if normalized_pool[mana_type] < required:
            return None
        payment[mana_type] = required
        normalized_pool[mana_type] -= required
    generic = normalized_cost["generic"]
    for mana_type in MANA_TYPES:
        spend = min(normalized_pool[mana_type], generic)
        payment[mana_type] += spend
        generic -= spend
        if generic == 0:
            return payment
    return None


def ensure_not_terminal(state: GameState) -> None:
    if state.terminal:
        raise RulesError("No action is legal after a terminal game state")


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
    create_treasure(state, count)
    state.record_event("malcolm_treasures", str(count))
    return count


def deal_pirate_combat_damage(
    state: GameState, sources: list[Permanent], opponents: list[int], amount: int | None = None
) -> int:
    ensure_not_terminal(state)
    damaged: dict[int, int] = {}
    prevented: set[int] = set()
    for source, opponent in zip(sources, opponents, strict=True):
        if state.terminal:
            break
        if opponent not in state.active_opponents():
            continue
        if source.damage_prevented:
            prevented.add(opponent)
            continue
        damage = source.power if amount is None else amount
        if damage is None and source.name in CREATURE_STATS:
            damage = CREATURE_STATS[source.name][0]
        if damage is None:
            damage = 1
        state.opponent_life[opponent] -= damage
        damaged[opponent] = damaged.get(opponent, 0) + damage
    treasures = create_malcolm_treasures_for_pirate_damage(state, damaged, prevented)
    if not state.resolving and not state.terminal:
        state.would_receive_priority()
    return treasures


def activate_glint_horn(state: GameState, glint_horn: Permanent) -> None:
    ensure_not_terminal(state)
    if not glint_horn.attacking:
        raise RulesError("Glint-Horn Buccaneer can activate only while attacking")
    if not state.hand:
        raise RulesError("Glint-Horn activation requires a discarded card")
    state.pay_mana({"generic": 1, "R": 1})
    discarded = state.hand.pop(0)
    state.graveyard.append(discarded)
    state.record_event("cost", "discard")

    def draw_effect(s: GameState) -> None:
        s.draw(1)

    def damage_effect(s: GameState) -> None:
        deal_noncombat_damage(s, list(s.active_opponents()), 1, source_name="Glint-Horn Buccaneer")
        s.record_event("glint_horn_discard_damage")

    state.stack.append(StackObject("Glint-Horn draw ability", "ability", draw_effect, cast=False))
    state.pending_triggers.append(
        StackObject("Glint-Horn discard damage trigger", "trigger", damage_effect, cast=False)
    )
    state.record_event("trigger_detected", "Glint-Horn discard damage trigger")
    state.would_receive_priority()


def curiosity_trigger(state: GameState, *, decline: bool) -> None:
    state.pending_triggers.append(
        StackObject(
            "Curiosity optional draw",
            "trigger",
            lambda s: s.draw(1, optional=True, decline=decline),
            cast=False,
        )
    )
    state.record_event("trigger_detected", "Curiosity optional draw")
    state.would_receive_priority()


def cleanup_step(state: GameState) -> None:
    state.phase = Phase.CLEANUP
    state.cleanup_steps += 1
    had_trigger = any(p.enchanted_by_curiosity for p in state.battlefield)
    if had_trigger:
        curiosity_trigger(state, decline=False)
        state.cleanup_steps += 1


def cast_twinflame(state: GameState, target: Permanent | None) -> StackObject:
    if target is None or target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Twinflame requires a legal original creature target")
    obj = StackObject("Twinflame", "spell", lambda _s: None, targets=[target], mana_value=2)
    obj.legal_targets = _is_creature_target
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
            targets=retarget_copy(state, original, [dualcaster]),
            cast=False,
            mana_value=original.mana_value,
            legal_targets=original.legal_targets,
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
        StackObject(
            "Electroduplicate",
            "spell",
            lambda _s: None,
            targets=[target],
            mana_value=3,
            legal_targets=_is_creature_target,
        )
    )
    state.exile.append("Electroduplicate")


TRANSMUTE_VALUES = {"Drift of Phantasms": 3, "Muddle the Mixture": 2, "Dizzy Spell": 1}
WIZARDCYCLING_COSTS: dict[str, ManaCost] = {
    "Step Through": {"generic": 2},
    "Vedalken Aethermage": {"generic": 3},
}
CYCLING_COSTS: dict[str, ManaCost] = {"Rebuild": {"generic": 2}}
CARD_TYPES = {
    "Curiosity": {"Enchantment"},
    "Twinflame": {"Sorcery"},
    "Electroduplicate": {"Sorcery"},
    "Dualcaster Mage": {"Creature"},
    "Niv-Mizzet, the Firemind": {"Creature"},
    "Psychosis Crawler": {"Artifact", "Creature"},
    "Glint-Horn Buccaneer": {"Creature"},
    "Lightning-Rig Crew": {"Creature"},
    "Storm Fleet Sprinter": {"Creature"},
    "Wily Goblin": {"Creature"},
    "Crab Umbra": {"Enchantment"},
    "Vedalken Aethermage": {"Creature"},
    "Step Through": {"Sorcery"},
    "Long-Term Plans": {"Instant"},
    "Rebuild": {"Instant"},
    "Muddle the Mixture": {"Instant"},
    "Dizzy Spell": {"Instant"},
    "Drift of Phantasms": {"Creature"},
    "Commit // Memory": {"Instant", "Sorcery"},
    "Invert // Invent": {"Instant"},
    "Abrade": {"Instant"},
    "Aetherize": {"Instant"},
    "Arcane Denial": {"Instant"},
    "Brotherhood's End": {"Sorcery"},
    "By Force": {"Sorcery"},
    "Change the Equation": {"Instant"},
    "Curse of the Swine": {"Sorcery"},
    "Dispel": {"Instant"},
    "Echoing Truth": {"Instant"},
    "Fading Hope": {"Instant"},
    "Fiery Cannonade": {"Instant"},
    "Into the Roil": {"Instant"},
    "Introduction to Annihilation": {"Sorcery"},
    "Lazotep Plating": {"Instant"},
    "Negate": {"Instant"},
    "Ravenform": {"Sorcery"},
    "Reality Ripple": {"Instant"},
    "Reality Shift": {"Instant"},
    "Resculpt": {"Instant"},
    "Sentinel Totem": {"Artifact"},
    "Soul-Guide Lantern": {"Artifact"},
    "Spell Pierce": {"Instant"},
    "Syncopate": {"Instant"},
    "Vandalblast": {"Sorcery"},
    "Wash Away": {"Instant"},
}

CARD_COLORS = {
    "Malcolm, Keen-Eyed Navigator": {"U"},
    "Breeches, Brazen Plunderer": {"R"},
    "Dualcaster Mage": {"R"},
    "Niv-Mizzet, the Firemind": {"U", "R"},
    "Glint-Horn Buccaneer": {"R"},
    "Lightning-Rig Crew": {"R"},
    "Storm Fleet Sprinter": {"U", "R"},
    "Wily Goblin": {"R"},
    "Crab Umbra": {"U"},
    "Curiosity": {"U"},
    "Twinflame": {"R"},
    "Electroduplicate": {"R"},
    "Abrade": {"R"},
    "Aetherize": {"U"},
    "Arcane Denial": {"U"},
    "Brotherhood's End": {"R"},
    "By Force": {"R"},
    "Change the Equation": {"U"},
    "Curse of the Swine": {"U"},
    "Dispel": {"U"},
    "Echoing Truth": {"U"},
    "Expedite": {"R"},
    "Fading Hope": {"U"},
    "Fact or Fiction": {"U"},
    "Faithless Looting": {"R"},
    "Fiery Cannonade": {"R"},
    "Frantic Search": {"U"},
    "Into the Roil": {"U"},
    "Lazotep Plating": {"U"},
    "Long-Term Plans": {"U"},
    "Muddle the Mixture": {"U"},
    "Negate": {"U"},
    "Opt": {"U"},
    "Prismari Command": {"U", "R"},
    "Ravenform": {"U"},
    "Reality Ripple": {"U"},
    "Reality Shift": {"U"},
    "Rebuild": {"U"},
    "Resculpt": {"U"},
    "Sleight of Hand": {"U"},
    "Spell Pierce": {"U"},
    "Step Through": {"U"},
    "Syncopate": {"U"},
    "Vedalken Aethermage": {"U"},
    "Wash Away": {"U"},
}
CARD_SUBTYPES = {
    "Dualcaster Mage": {"Human", "Wizard"},
    "Niv-Mizzet, the Firemind": {"Dragon", "Wizard"},
    "Vedalken Aethermage": {"Vedalken", "Wizard"},
    "Siren Stormtamer": {"Siren", "Pirate", "Wizard"},
    "Spectral Sailor": {"Spirit", "Pirate"},
    "Malcolm, Keen-Eyed Navigator": {"Siren", "Pirate"},
    "Breeches, Brazen Plunderer": {"Goblin", "Pirate"},
    "Glint-Horn Buccaneer": {"Minotaur", "Pirate"},
    "Lightning-Rig Crew": {"Goblin", "Pirate"},
    "Storm Fleet Sprinter": {"Human", "Pirate"},
    "Wily Goblin": {"Goblin", "Pirate"},
    "Drift of Phantasms": {"Spirit"},
}
MANA_VALUES = {
    "Malcolm, Keen-Eyed Navigator": 3,
    "Breeches, Brazen Plunderer": 4,
    "Twinflame": 2,
    "Electroduplicate": 3,
    "Curiosity": 1,
    "Niv-Mizzet, the Firemind": 6,
    "Chart a Course": 2,
    "Expedite": 1,
    "Fact or Fiction": 4,
    "Faithless Looting": 1,
    "Frantic Search": 3,
    "Impulse": 2,
    "Opt": 1,
    "Sleight of Hand": 1,
    "Prismari Command": 3,
    "Spectral Sailor": 1,
    "Dualcaster Mage": 3,
    "Glint-Horn Buccaneer": 3,
    "Siren Stormtamer": 1,
    "Lightning-Rig Crew": 3,
    "Abrade": 2,
    "Aetherize": 4,
    "Arcane Denial": 2,
    "Brotherhood's End": 3,
    "By Force": 1,
    "Change the Equation": 2,
    "Curse of the Swine": 2,
    "Dispel": 1,
    "Echoing Truth": 2,
    "Fading Hope": 1,
    "Fiery Cannonade": 3,
    "Into the Roil": 2,
    "Introduction to Annihilation": 5,
    "Lazotep Plating": 2,
    "Negate": 2,
    "Ravenform": 3,
    "Reality Ripple": 2,
    "Reality Shift": 2,
    "Resculpt": 2,
    "Sentinel Totem": 1,
    "Soul-Guide Lantern": 1,
    "Spell Pierce": 1,
    "Syncopate": 1,
    "Vandalblast": 1,
    "Wash Away": 1,
    "Crab Umbra": 1,
    "Psychosis Crawler": 5,
    "Storm Fleet Sprinter": 3,
    "Wily Goblin": 2,
}
SPLIT_FACE_MANA_VALUES = {"Invert": 1, "Invent": 6, "Commit": 4, "Memory": 6}
SPLIT_CARD_FACES = {
    "Invert // Invent": ("Invert", "Invent"),
    "Commit // Memory": ("Commit", "Memory"),
}


def mana_value(card_name: str, *, zone: str = "library", face: str | None = None) -> int:
    if card_name in SPLIT_CARD_FACES:
        if zone == "stack":
            if face not in SPLIT_CARD_FACES[card_name]:
                raise RulesError("split spell on stack requires the chosen half")
            return SPLIT_FACE_MANA_VALUES[face]
        return sum(SPLIT_FACE_MANA_VALUES[part] for part in SPLIT_CARD_FACES[card_name])
    if card_name in SPLIT_FACE_MANA_VALUES:
        return SPLIT_FACE_MANA_VALUES[card_name]
    if card_name in TRANSMUTE_VALUES:
        return TRANSMUTE_VALUES[card_name]
    if card_name == "Rebuild" or card_name == "Long-Term Plans":
        return 3
    if card_name in {"Step Through"}:
        return 5
    if card_name == "Vedalken Aethermage":
        return 2
    try:
        return MANA_VALUES[card_name]
    except KeyError as exc:
        raise RulesError(f"unknown mana value for {card_name}") from exc


def _search_one(state: GameState, target_name: str) -> str:
    if target_name not in state.library:
        raise RulesError(f"tutor target is not in library: {target_name}")
    state.library.remove(target_name)
    state.hand.append(target_name)
    state.record_event("tutor_found", target_name)
    state.record_event("shuffle_library")
    return target_name


def transmute(state: GameState, card_name: str, target_name: str) -> str:
    if state.phase not in {Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN} or state.stack:
        raise RulesError("Transmute is sorcery speed")
    if card_name not in state.hand:
        raise RulesError("Transmute source must be in hand")
    required = TRANSMUTE_VALUES[card_name]
    if mana_value(target_name, zone="library") != required:
        raise RulesError(f"{card_name} can find only mana value {required}")
    state.pay_mana({"generic": 1, "U": 2})
    state.hand.remove(card_name)
    state.graveyard.append(card_name)
    state.record_event("cost", f"discard:{card_name}")
    return _search_one(state, target_name)


def wizardcycle(state: GameState, target_name: str, source_name: str = "Step Through") -> str:
    if source_name not in WIZARDCYCLING_COSTS or source_name not in state.hand:
        raise RulesError("Wizardcycling source must be in hand")
    if "Wizard" not in CARD_SUBTYPES.get(target_name, set()):
        raise RulesError("Wizardcycling finds only Wizards")
    state.pay_mana(WIZARDCYCLING_COSTS[source_name])
    state.hand.remove(source_name)
    state.graveyard.append(source_name)
    state.record_event("cost", f"discard:{source_name}")
    return _search_one(state, target_name)


def cycle(state: GameState, source_name: str) -> None:
    if source_name not in CYCLING_COSTS or source_name not in state.hand:
        raise RulesError("Cycling source must be in hand")
    state.pay_mana(CYCLING_COSTS[source_name])
    state.hand.remove(source_name)
    state.graveyard.append(source_name)
    state.record_event("cost", f"discard:{source_name}")
    state.draw(1)


def long_term_plans(state: GameState, target_name: str) -> None:
    if target_name not in state.library:
        raise RulesError("Long-Term Plans target must be in library")
    state.library.remove(target_name)
    while len(state.library) < 2:
        state.library.append("<empty slot after Long-Term Plans shuffle>")
    state.library.insert(2, target_name)
    state.record_event("tutor_found_third_from_top", target_name)


DRAW_SELECTION_SPELLS = {
    "Chart a Course",
    "Expedite",
    "Fact or Fiction",
    "Faithless Looting",
    "Frantic Search",
    "Impulse",
    "Opt",
    "Sleight of Hand",
    "Prismari Command",
}


def _discard_named(state: GameState, names: tuple[str, ...]) -> None:
    for name in names:
        if name not in state.hand:
            raise RulesError(f"cannot discard unavailable card: {name}")
    for name in names:
        state.hand.remove(name)
        state.graveyard.append(name)
        state.record_event("discard", name)


def _select_from_revealed(
    state: GameState, count: int, keep: int, choice: str | None
) -> tuple[str, ...]:
    revealed = tuple(state.library[:count])
    state.record_event("reveal", ",".join(revealed))
    if not revealed:
        return ()
    selected = choice or revealed[0]
    if selected not in revealed:
        raise RulesError("selection must be from legally revealed cards")
    state.library.remove(selected)
    state.hand.append(selected)
    for card in list(revealed):
        if card != selected and card in state.library:
            state.library.remove(card)
            state.library.append(card)
    state.record_event("selection", f"picked:{selected}:from:{','.join(revealed)}")
    return (selected,)


def _fact_or_fiction_effect(state: GameState, values: dict[str, int] | None = None) -> None:
    values = values or {}
    revealed = tuple(state.library[:5])
    del state.library[: len(revealed)]
    state.record_event("fact_or_fiction_revealed", ",".join(revealed))
    best: tuple[int, tuple[str, ...], tuple[str, ...]] | None = None
    n = len(revealed)
    for mask in range(1 << n):
        pile_a = tuple(revealed[i] for i in range(n) if mask & (1 << i))
        pile_b = tuple(card for card in revealed if card not in pile_a)
        score = max(sum(values.get(c, 0) for c in pile_a), sum(values.get(c, 0) for c in pile_b))
        state.record_event("fact_or_fiction_partition", f"{pile_a}|{pile_b}|max={score}")
        if best is None or score < best[0]:
            best = (score, pile_a, pile_b)
    assert best is not None
    _, pile_a, pile_b = best
    chosen = (
        pile_a
        if sum(values.get(c, 0) for c in pile_a) >= sum(values.get(c, 0) for c in pile_b)
        else pile_b
    )
    state.record_event("fact_or_fiction_minimizing_partition", f"{pile_a}|{pile_b}")
    state.record_event("fact_or_fiction_player_chosen_pile", ",".join(chosen))
    for card in chosen:
        state.hand.append(card)
    for card in revealed:
        if card not in chosen:
            state.graveyard.append(card)


def _spell_effect_for_action(action: Action) -> Callable[[GameState], None]:
    name = action.source_name
    discards = tuple(
        x.removeprefix("discard:") for x in action.additional_costs if x.startswith("discard:")
    )

    def effect(s: GameState) -> None:
        if name == "Chart a Course":
            s.draw(2)
            _discard_named(s, discards[:1])
        elif name == "Expedite":
            for target in action.targets:
                target.haste = True
            s.draw(1)
        elif name == "Fact or Fiction":
            _fact_or_fiction_effect(s)
        elif name == "Faithless Looting":
            s.draw(2)
            _discard_named(s, discards[:2])
            if action.origin_zone == "graveyard":
                s.exile.append("Faithless Looting")
                s.record_event("flashback_exile", "Faithless Looting")
        elif name == "Frantic Search":
            s.draw(2)
            _discard_named(s, discards[:2])
            lands = [p for p in s.battlefield if "Land" in p.types and p.tapped][:3]
            for land in lands:
                land.tapped = False
            s.record_event("untap_lands", ",".join(p.name for p in lands))
        elif name == "Impulse":
            _select_from_revealed(s, 4, 1, action.choice)
        elif name == "Opt":
            s.record_event("scry", action.choice or "top")
            s.draw(1)
        elif name == "Sleight of Hand":
            _select_from_revealed(s, 2, 1, action.choice)
        elif name == "Prismari Command":
            modes = tuple("draw_discard" if m == "loot" else m for m in action.modes)
            prismari_command(s, cast(tuple[str, str], modes), treasure_player=0)
            if "draw_discard" in modes:
                _discard_named(s, discards[:2])
        elif name == "Long-Term Plans":
            long_term_plans(s, action.choice or (s.library[0] if s.library else ""))
        elif name == "Commit // Memory":
            if action.choice == "Memory":
                if "Commit // Memory" not in s.graveyard:
                    s.graveyard.append("Commit // Memory")
                memory(s)
            elif action.stack_target is not None:
                commit(s, action.stack_target)
            elif action.targets:
                commit(s, action.targets[0])
            else:
                raise RulesError("Commit requires a target")
        elif name == "Abrade":
            abrade(
                s,
                cast(Literal["damage_creature", "destroy_artifact"], action.modes[0]),
                action.targets[0],
            )
        elif name == "Aetherize":
            aetherize(s)
        elif name == "Arcane Denial":
            assert action.stack_target is not None
            arcane_denial(s, action.stack_target, target_controller_draws=2)
        elif name == "Brotherhood's End":
            brotherhoods_end(s, cast(Literal["damage", "artifacts"], action.modes[0]))
        elif name == "By Force":
            by_force(s, list(action.targets), action.x_value or 0)
        elif name == "Change the Equation":
            assert action.stack_target is not None
            change_the_equation(
                s, action.stack_target, cast(Literal["small", "red_green"], action.modes[0])
            )
        elif name == "Curse of the Swine":
            curse_of_the_swine(s, list(action.targets), action.x_value or 0)
        elif name == "Dispel":
            assert action.stack_target is not None
            dispel(s, action.stack_target)
        elif name == "Echoing Truth":
            echoing_truth(s, action.targets[0])
        elif name == "Fading Hope":
            fading_hope(s, action.targets[0])
        elif name == "Fiery Cannonade":
            fiery_cannonade(s)
        elif name == "Into the Roil":
            into_the_roil(s, action.targets[0], kicked="kicker" in action.additional_costs)
        elif name == "Introduction to Annihilation":
            introduction_to_annihilation(s, action.targets[0])
        elif name == "Lazotep Plating":
            lazotep_plating(s)
        elif name == "Negate":
            assert action.stack_target is not None
            negate(s, action.stack_target)
        elif name == "Ravenform":
            ravenform(s, action.targets[0])
        elif name == "Reality Ripple":
            reality_ripple(s, action.targets[0])
        elif name == "Reality Shift":
            reality_shift(s, action.targets[0])
        elif name == "Rebuild":
            rebuild(s)
        elif name == "Resculpt":
            resculpt(s, action.targets[0])
        elif name == "Spell Pierce":
            assert action.stack_target is not None
            spell_pierce(s, action.stack_target, pays=False)
        elif name == "Syncopate":
            assert action.stack_target is not None
            syncopate(s, action.stack_target, action.x_value or 0, pays=False)
        elif name == "Vandalblast":
            vandalblast(
                s,
                action.targets[0] if action.targets else None,
                overload="overload" in action.additional_costs,
            )
        elif name == "Wash Away":
            assert action.stack_target is not None
            wash_away(s, action.stack_target, cleave="cleave" in action.additional_costs)
        elif name == "Twinflame":
            token_copy(s, action.targets[0])
        elif name == "Electroduplicate":
            token_copy(s, action.targets[0])
            if action.origin_zone == "graveyard":
                s.exile.append("Electroduplicate")
                s.record_event("flashback_exile", "Electroduplicate")
        elif name == "Curiosity":
            action.targets[0].enchanted_by_curiosity = True
            s.record_event("aura_attached", "Curiosity")
        elif name == "Crab Umbra":
            action.targets[0].damage_prevented = True
            s.record_event("aura_attached", "Crab Umbra")
        elif name == "Invert // Invent":
            if action.choice == "Invert":
                invert(s, list(action.targets))
            else:
                inst = next(
                    (
                        x.removeprefix("instant:")
                        for x in action.additional_costs
                        if x.startswith("instant:")
                    ),
                    None,
                )
                sorc = next(
                    (
                        x.removeprefix("sorcery:")
                        for x in action.additional_costs
                        if x.startswith("sorcery:")
                    ),
                    None,
                )
                invent(s, instant=inst, sorcery=sorc)

    return effect


def commander_cost(name: str, base_generic: int, state: GameState) -> int:
    return base_generic + 2 * state.commander_casts.get(name, 0)


def cast_commander(name: str, base_generic: int, state: GameState) -> int:
    cost = commander_cost(name, base_generic, state)
    state.commander_casts[name] = state.commander_casts.get(name, 0) + 1
    return cost


def cast_split_card(face: str) -> int:
    if face not in SPLIT_FACE_MANA_VALUES:
        raise RulesError("unknown split-card face")
    return SPLIT_FACE_MANA_VALUES[face]


def invent(
    state: GameState, *, instant: str | None = None, sorcery: str | None = None
) -> tuple[str, ...]:
    choices = tuple(name for name in (instant, sorcery) if name is not None)
    if not choices or len(set(choices)) != len(choices):
        raise RulesError("Invent must choose separate instant and/or sorcery branches")
    for name in choices:
        types = CARD_TYPES.get(name, set())
        if name == instant and "Instant" not in types:
            raise RulesError("Invent instant choice must be an instant card")
        if name == sorcery and "Sorcery" not in types:
            raise RulesError("Invent sorcery choice must be a sorcery card")
        _search_one(state, name)
    return choices


def invert(_state: GameState, targets: list[Permanent]) -> None:
    if len(targets) > 2:
        raise RulesError("Invert targets up to two creatures")
    for target in targets:
        if "Creature" not in target.types or target.power is None or target.toughness is None:
            raise RulesError("Invert target must be a creature with modeled power/toughness")
    for target in targets:
        target.power, target.toughness = target.toughness, target.power


def commit(state: GameState, target: StackObject | Permanent) -> None:
    if isinstance(target, StackObject):
        if target not in state.stack:
            raise RulesError("Commit spell target must be on stack")
        state.stack.remove(target)
        state.library.insert(1, target.name)
    else:
        if target not in state.battlefield or "Land" in target.types:
            raise RulesError("Commit permanent target must be a nonland permanent")
        state.battlefield.remove(target)
        state.library.insert(1, target.name)
    state.record_event("commit_second_from_top", target.name)


def memory(state: GameState) -> None:
    if "Commit // Memory" not in state.graveyard:
        raise RulesError("Memory can be cast only from graveyard due to aftermath")
    state.graveyard.remove("Commit // Memory")
    state.library.extend(state.hand)
    state.library.extend(state.graveyard)
    state.hand.clear()
    state.graveyard.clear()
    state.exile.append("Commit // Memory")
    state.record_event("aftermath_exile", "Commit // Memory")
    state.draw(7)


def rebuild(state: GameState) -> None:
    for permanent in list(state.battlefield):
        if "Artifact" in permanent.types:
            state.battlefield.remove(permanent)
            if permanent.is_token:
                state.record_event("token_ceased_to_exist", permanent.name)
            else:
                state.hand.append(permanent.name)
                state.record_event("artifact_returned", permanent.name)


LAND_MANA = {
    "Island": "U",
    "Mountain": "R",
    "Command Tower": "U",
    "Shivan Reef": "U",
    "Exotic Orchard": "U",
    "Cascade Bluffs": "U",
    "Temple of Epiphany": "U",
    "Frostboil Snarl": "U",
    "Thriving Isle": "U",
    "Scavenger Grounds": "C",
    "Demolition Field": "C",
    "Path of Ancestry": "U",
    "Ash Barrens": "C",
    "Izzet Boilerworks": "U",
}
TAPPED_LANDS = {
    "Izzet Boilerworks",
    "Temple of Epiphany",
    "Thriving Isle",
    "Path of Ancestry",
    "Frostboil Snarl",
}
MANA_ROCK_MANA = {
    "Sol Ring": "C",
    "Arcane Signet": "U",
    "Fellwar Stone": "U",
    "Mind Stone": "C",
    "Prismatic Lens": "C",
    "Izzet Signet": "U",
}
CARD_COSTS: dict[str, ManaCost] = {
    "Sol Ring": {"generic": 1},
    "Arcane Signet": {"generic": 2},
    "Fellwar Stone": {"generic": 2},
    "Mind Stone": {"generic": 2},
    "Prismatic Lens": {"generic": 2},
    "Izzet Signet": {"generic": 2},
    "Malcolm, Keen-Eyed Navigator": {"generic": 2, "U": 1},
    "Breeches, Brazen Plunderer": {"generic": 3, "R": 1},
    "Glint-Horn Buccaneer": {"generic": 1, "R": 2},
    "Dualcaster Mage": {"generic": 1, "R": 2},
    "Twinflame": {"generic": 1, "R": 1},
    "Electroduplicate": {"generic": 2, "R": 1},
    "Curiosity": {"U": 1},
    "Niv-Mizzet, the Firemind": {"generic": 2, "U": 3, "R": 1},
    "Lightning-Rig Crew": {"generic": 2, "R": 1},
    "Crab Umbra": {"U": 1},
    "Wily Goblin": {"generic": 1, "R": 1},
    "Psychosis Crawler": {"generic": 5},
    "Chart a Course": {"generic": 1, "U": 1},
    "Expedite": {"R": 1},
    "Fact or Fiction": {"generic": 3, "U": 1},
    "Faithless Looting": {"R": 1},
    "Frantic Search": {"generic": 2, "U": 1},
    "Impulse": {"generic": 1, "U": 1},
    "Opt": {"U": 1},
    "Sleight of Hand": {"U": 1},
    "Prismari Command": {"generic": 1, "U": 1, "R": 1},
    "Long-Term Plans": {"generic": 2, "U": 1},
    "Rebuild": {"generic": 2, "U": 1},
    "Commit // Memory": {"generic": 3, "U": 1},
    "Invert // Invent": {"U": 1},
    "Abrade": {"generic": 1, "R": 1},
    "Aetherize": {"generic": 3, "U": 1},
    "Arcane Denial": {"generic": 1, "U": 1},
    "Brotherhood's End": {"generic": 1, "R": 2},
    "By Force": {"R": 1},
    "Change the Equation": {"generic": 1, "U": 1},
    "Curse of the Swine": {"U": 2},
    "Dispel": {"U": 1},
    "Echoing Truth": {"generic": 1, "U": 1},
    "Fading Hope": {"U": 1},
    "Fiery Cannonade": {"generic": 2, "R": 1},
    "Into the Roil": {"generic": 1, "U": 1},
    "Introduction to Annihilation": {"generic": 5},
    "Lazotep Plating": {"generic": 1, "U": 1},
    "Negate": {"generic": 1, "U": 1},
    "Ravenform": {"generic": 2, "U": 1},
    "Reality Ripple": {"generic": 1, "U": 1},
    "Reality Shift": {"generic": 1, "U": 1},
    "Resculpt": {"generic": 1, "U": 1},
    "Sentinel Totem": {"generic": 1},
    "Soul-Guide Lantern": {"generic": 1},
    "Spell Pierce": {"U": 1},
    "Syncopate": {"U": 1},
    "Vandalblast": {"R": 1},
    "Wash Away": {"U": 1},
}
CREATURES = {
    "Malcolm, Keen-Eyed Navigator",
    "Breeches, Brazen Plunderer",
    "Glint-Horn Buccaneer",
    "Dualcaster Mage",
    "Niv-Mizzet, the Firemind",
    "Lightning-Rig Crew",
    "Siren Stormtamer",
    "Spectral Sailor",
    "Storm Fleet Sprinter",
    "Wily Goblin",
    "Drift of Phantasms",
    "Vedalken Aethermage",
    "Psychosis Crawler",
}
PIRATES = {
    "Malcolm, Keen-Eyed Navigator",
    "Breeches, Brazen Plunderer",
    "Glint-Horn Buccaneer",
    "Siren Stormtamer",
    "Spectral Sailor",
    "Storm Fleet Sprinter",
    "Lightning-Rig Crew",
    "Wily Goblin",
}


CREATURE_STATS = {
    "Malcolm, Keen-Eyed Navigator": (2, 2),
    "Breeches, Brazen Plunderer": (3, 3),
    "Glint-Horn Buccaneer": (2, 4),
    "Dualcaster Mage": (2, 2),
    "Niv-Mizzet, the Firemind": (4, 4),
    "Lightning-Rig Crew": (0, 5),
    "Siren Stormtamer": (1, 1),
    "Spectral Sailor": (1, 1),
    "Storm Fleet Sprinter": (2, 2),
    "Wily Goblin": (1, 1),
    "Drift of Phantasms": (0, 5),
    "Vedalken Aethermage": (1, 2),
    "Psychosis Crawler": (0, 0),
}


COMMANDER_BASE_COSTS: dict[str, ManaCost] = {
    "Malcolm, Keen-Eyed Navigator": {"generic": 2, "U": 1},
    "Breeches, Brazen Plunderer": {"generic": 3, "R": 1},
}


def commander_action_cost(name: str, state: GameState, origin_zone: str | None) -> ManaCost:
    base = dict(COMMANDER_BASE_COSTS[name])
    if origin_zone == "command_zone":
        base["generic"] = base.get("generic", 0) + 2 * state.commander_casts.get(name, 0)
    return base


def _costs_equal(left: ManaCost | None, right: ManaCost | None) -> bool:
    return normalize_mana(left) == normalize_mana(right)


def play_land(
    state: GameState, name: str, *, chosen_color: str | None = None, reveal: str | None = None
) -> Permanent:
    if state.land_played:
        raise RulesError("only one land play per turn")
    tapped = name in TAPPED_LANDS
    if name == "Frostboil Snarl" and reveal in state.hand and reveal in {"Island", "Mountain"}:
        tapped = False
        state.record_event("land_revealed", reveal)
    if name == "Thriving Isle":
        if chosen_color not in COLORED_MANA or chosen_color == "U":
            raise RulesError("Thriving Isle requires a nonblue secondary color choice")
    land = Permanent(
        name, {"Land"}, {name}, tapped=tapped, chosen_color=chosen_color, entered_turn=state.turn
    )
    state.battlefield.append(land)
    state.land_played = True
    if name == "Temple of Epiphany":
        state.record_event("scry", "Temple of Epiphany:bottom")
    if name == "Izzet Boilerworks":
        target = next((p for p in state.battlefield if "Land" in p.types and p is not land), land)
        state.battlefield.remove(target)
        state.hand.append(target.name)
        state.record_event("land_returned", target.name)
    return land


def _permanent_for_card(name: str) -> Permanent:
    if name in MANA_ROCK_MANA:
        return Permanent(name, {"Artifact"}, mana_abilities={"tap": MANA_ROCK_MANA[name]})
    if name in CREATURES:
        power, toughness = CREATURE_STATS[name]
        types = {"Artifact", "Creature"} if name == "Psychosis Crawler" else {"Creature"}
        return Permanent(
            name,
            types,
            set(CARD_SUBTYPES.get(name, {"Pirate"} if name in PIRATES else set())),
            power=power,
            toughness=toughness,
            haste=name == "Storm Fleet Sprinter",
            mana_value=mana_value(name),
        )
    return Permanent(name, {"Noncreature"})


def _legal_mana_outputs(permanent: Permanent) -> tuple[str, ...]:
    if permanent.name in {
        "Island",
        "Command Tower",
        "Exotic Orchard",
        "Fellwar Stone",
        "Arcane Signet",
    }:
        return (
            ("U", "R")
            if permanent.name
            in {"Command Tower", "Exotic Orchard", "Fellwar Stone", "Arcane Signet"}
            else ("U",)
        )
    if permanent.name == "Mountain":
        return ("R",)
    if permanent.name == "Shivan Reef":
        return ("C", "U", "R")
    if permanent.name == "Cascade Bluffs":
        return ("C", "U", "R", "UU", "UR", "RR")
    if permanent.name == "Izzet Boilerworks":
        return ("U", "R")
    if permanent.name in {"Temple of Epiphany", "Frostboil Snarl", "Path of Ancestry"}:
        return ("U", "R")
    if permanent.name == "Thriving Isle":
        return tuple(dict.fromkeys(("U", permanent.chosen_color or "R")))
    if permanent.name == "Prismatic Lens":
        return ("C", "U", "R", "W", "B", "G")
    if permanent.name in {
        "Scavenger Grounds",
        "Demolition Field",
        "Ash Barrens",
        "Mind Stone",
    }:
        return ("C",)
    if permanent.name == "Sol Ring":
        return ("C",)
    return tuple(permanent.mana_abilities.values())


def tap_for_mana(state: GameState, permanent: Permanent, color: str | None = None) -> None:
    ensure_not_terminal(state)
    if permanent.tapped:
        raise RulesError("permanent is already tapped")
    outputs = _legal_mana_outputs(permanent)
    produced = color or (outputs[0] if outputs else None)
    if produced not in outputs:
        raise RulesError(f"illegal mana choice for {permanent.name}")
    if permanent.name == "Cascade Bluffs" and produced in {"UU", "UR", "RR"}:
        if state.mana_pool.get("U", 0) + state.mana_pool.get("R", 0) < 1:
            raise RulesError("Cascade Bluffs requires blue or red input mana")
        state.pay_mana({"U": 1} if state.mana_pool.get("U", 0) else {"R": 1})
    if permanent.name == "Izzet Signet":
        state.pay_mana({"generic": 1})
        permanent.tapped = True
        state.mana_pool["U"] += 1
        state.mana_pool["R"] += 1
        state.record_event("mana_produced", "Izzet Signet:UR")
        return
    if permanent.name == "Prismatic Lens" and color in COLORED_MANA:
        state.pay_mana({"generic": 1})
    permanent.tapped = True
    amount = 2 if permanent.name == "Sol Ring" and produced == "C" else 1
    if permanent.name == "Cascade Bluffs" and produced in {"UU", "UR", "RR"}:
        for symbol in produced:
            state.mana_pool[symbol] += 1
    else:
        state.mana_pool[produced] += amount
    if permanent.name == "Shivan Reef" and produced in {"U", "R"}:
        state.record_event("life_lost", "Shivan Reef:1")
    state.record_event("mana_produced", f"{permanent.name}:{produced}:{amount}")


def create_treasure(state: GameState, count: int = 1) -> None:
    if count <= 0:
        return
    state.treasures += count
    for _ in range(count):
        state.battlefield.append(Permanent("Treasure", {"Artifact"}, {"Treasure"}, is_token=True))
    state.record_event("treasure_created", str(count))


def sacrifice_treasure_for_mana(state: GameState, color: str) -> None:
    ensure_not_terminal(state)
    if color not in MANA_TYPES:
        raise RulesError("Treasure can produce one mana of a legal type")
    treasure = next((p for p in state.battlefield if p.name == "Treasure" and p.is_token), None)
    if treasure is None or state.treasures <= 0:
        raise RulesError("no Treasure available to sacrifice")
    state.battlefield.remove(treasure)
    state.treasures -= 1
    state.mana_pool[color] += 1
    state.record_event("treasure_sacrificed", color)


def declare_attackers(
    state: GameState, attackers: list[Permanent], defending_opponent: int | None = None
) -> None:
    ensure_not_terminal(state)
    if state.phase is not Phase.COMBAT:
        raise RulesError("attackers are declared only during combat")
    if defending_opponent is not None and defending_opponent not in state.active_opponents():
        raise RulesError("attackers require a legal defending opponent")
    for attacker in attackers:
        if attacker not in state.battlefield or "Creature" not in attacker.types:
            raise RulesError("only battlefield creatures can attack")
        if attacker.tapped:
            raise RulesError("tapped creatures cannot attack")
        if attacker.summoning_sick and not attacker.haste:
            raise RulesError("creature cannot attack due to summoning sickness")
    for idx, attacker in enumerate(attackers):
        attacker.attacking = True
        assigned_defender = (
            int(defending_opponent)
            if defending_opponent is not None
            else idx % len(state.active_opponents())
        )
        attacker.defending_opponent = assigned_defender
        attacker.tapped = True
    state.record_event(
        "declare_attackers", f"opponent_{defending_opponent}:" + ",".join(p.name for p in attackers)
    )
    state.would_receive_priority()


def deal_noncombat_damage(
    state: GameState, opponents: list[int], amount: int, *, source_name: str = "source"
) -> None:
    for opponent in opponents:
        if opponent in state.active_opponents():
            state.opponent_life[opponent] -= amount
    state.record_event("noncombat_damage", f"{source_name}:{amount}")
    if not state.resolving:
        state.would_receive_priority()


def move_to_graveyard_or_command_zone(
    state: GameState, permanent: Permanent, *, use_command_zone: bool = True
) -> None:
    if permanent not in state.battlefield:
        raise RulesError("permanent is not on battlefield")
    state.battlefield.remove(permanent)
    if (
        permanent.name in {"Malcolm, Keen-Eyed Navigator", "Breeches, Brazen Plunderer"}
        and use_command_zone
    ):
        state.command_zone.append(permanent.name)
        state.command_zone_replacements[permanent.name] = True
        state.record_event("command_zone_replacement", permanent.name)
    elif not permanent.is_token:
        state.graveyard.append(permanent.name)
        state.record_event("move_to_graveyard", permanent.name)
    else:
        state.record_event("token_ceased_to_exist", permanent.name)


def retarget_copy(
    state: GameState, original: StackObject, targets: list[Permanent]
) -> list[Permanent]:
    if original.legal_targets is not None and not original.legal_targets(state, targets):
        raise RulesError("copy retargeting requires legal targets")
    return list(targets)


def use_single_tutor_for_combo_halves() -> None:
    raise RulesError("one tutor cannot provide both halves of a combo")


def execute_placeholder(card_name: str) -> None:
    raise RulesError(f"placeholder behavior cannot be selected for deterministic line: {card_name}")


TARGET_RULES_REFS = ("CR 601.2c", "CR 603.3d")
TIMING_RULES_REFS = ("CR 117.1a", "CR 117.1b", "CR 602.5d")
STACK_RULES_REFS = ("CR 117.4", "CR 117.7")
SBA_RULES_REFS = ("CR 117.5", "CR 704.3", "CR 704.4", "CR 704.5b")


def _is_creature_target(state: GameState, targets: list[Permanent]) -> bool:
    return len(targets) == 1 and targets[0] in state.battlefield and "Creature" in targets[0].types


def validate_timing(state: GameState, timing: str) -> tuple[str, ...]:
    if state.terminal:
        return ("No action is legal after a terminal game state",)
    if timing == "sorcery" and (
        state.phase not in {Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN} or state.stack
    ):
        return ("Sorcery-speed actions require a main phase with an empty stack",)
    return ()


ABILITY_COSTS: dict[tuple[str, str], ManaCost] = {
    ("Glint-Horn Buccaneer", "draw_discard_damage"): {"generic": 1, "R": 1},
    ("Lightning-Rig Crew", "tap_damage_each_opponent"): {},
    ("Mind Stone", "draw"): {"generic": 1},
    ("Soul-Guide Lantern", "exile_opponents_graveyards"): {},
    ("Soul-Guide Lantern", "draw"): {"generic": 1},
    ("Sentinel Totem", "exile_all_graveyards"): {},
    ("Siren Stormtamer", "sacrifice_counter"): {"U": 1},
    ("Spectral Sailor", "draw"): {"generic": 3, "U": 1},
    ("Niv-Mizzet, the Firemind", "tap_draw"): {},
    ("Crab Umbra", "untap_enchanted"): {"generic": 2, "U": 1},
    ("Evolving Wilds", "basic_fetch"): {},
    ("Terramorphic Expanse", "basic_fetch"): {},
    ("Ash Barrens", "basic_landcycling"): {"generic": 1},
    ("Scavenger Grounds", "exile_graveyards"): {"generic": 2},
    ("Demolition Field", "destroy_nonbasic"): {"generic": 2},
    ("Dizzy Spell", "transmute"): {"generic": 1, "U": 2},
    ("Drift of Phantasms", "transmute"): {"generic": 1, "U": 2},
    ("Muddle the Mixture", "transmute"): {"generic": 1, "U": 2},
    ("Step Through", "wizardcycling"): {"generic": 2},
    ("Vedalken Aethermage", "wizardcycling"): {"generic": 3},
    ("Rebuild", "cycling"): {"generic": 2},
}


def _default_ability_id(name: str | None) -> str | None:
    if name is None:
        return None
    return {
        "Glint-Horn Buccaneer": "draw_discard_damage",
        "Lightning-Rig Crew": "tap_damage_each_opponent",
        "Mind Stone": "draw",
        "Sentinel Totem": "exile_all_graveyards",
    }.get(name)


def _stack_target_action(
    card: str,
    target: StackObject,
    cost: ManaCost,
    *,
    modes: tuple[str, ...] = (),
    x_value: int | None = None,
    choice: str | None = None,
) -> Action:
    return Action(
        ActionType.CAST_SPELL,
        card,
        mana_cost=cost,
        timing="instant",
        origin_zone="hand",
        modes=modes,
        stack_target=target,
        x_value=x_value,
        choice=choice,
    )


def _x_cost(base: ManaCost, x_value: int) -> ManaCost:
    cost = dict(base)
    cost["generic"] = cost.get("generic", 0) + x_value
    return cost


def _spell_action_is_legal_by_text(state: GameState, action: Action) -> bool:
    card = action.source_name
    targets = list(action.targets)
    st = action.stack_target
    mode = action.modes[0] if action.modes else None
    try:
        if card in {"Arcane Denial", "Syncopate"}:
            return st is not None and st in state.stack and _is_spell(st)
        if card == "Negate":
            return (
                st is not None
                and st in state.stack
                and _is_spell(st)
                and "Creature" not in _spell_types(st)
            )
        if card == "Dispel":
            return (
                st is not None
                and st in state.stack
                and _is_spell(st)
                and "Instant" in _spell_types(st)
            )
        if card == "Spell Pierce":
            return (
                st is not None
                and st in state.stack
                and _is_spell(st)
                and "Creature" not in _spell_types(st)
            )
        if card == "Wash Away":
            return (
                st is not None
                and st in state.stack
                and _is_spell(st)
                and ("cleave" in action.additional_costs or not getattr(st, "cast_from_hand", True))
            )
        if card == "Change the Equation":
            return (
                st is not None
                and st in state.stack
                and _is_spell(st)
                and (
                    (mode == "small" and (st.mana_value or 99) <= 2)
                    or (
                        mode == "red_green"
                        and (st.mana_value or 99) <= 6
                        and bool(_spell_colors(st) & {"R", "G"})
                    )
                )
            )
        if card == "Abrade":
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and (
                    (mode == "damage_creature" and "Creature" in targets[0].types)
                    or (mode == "destroy_artifact" and "Artifact" in targets[0].types)
                )
            )
        if card == "Aetherize":
            return any("Creature" in p.types and p.attacking for p in state.battlefield)
        if card == "Brotherhood's End":
            return mode in {"damage", "artifacts"}
        if card == "By Force":
            return (
                action.x_value == len(targets)
                and action.x_value is not None
                and action.x_value > 0
                and all(t in state.battlefield and "Artifact" in t.types for t in targets)
                and len({id(t) for t in targets}) == len(targets)
            )
        if card == "Curse of the Swine":
            return (
                action.x_value == len(targets)
                and action.x_value is not None
                and action.x_value > 0
                and all(t in state.battlefield and "Creature" in t.types for t in targets)
                and len({id(t) for t in targets}) == len(targets)
            )
        if card in {"Echoing Truth", "Into the Roil", "Introduction to Annihilation"}:
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and "Land" not in targets[0].types
            )
        if card in {"Fading Hope", "Reality Shift"}:
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and "Creature" in targets[0].types
            )
        if card == "Reality Ripple":
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and bool(targets[0].types & {"Artifact", "Creature", "Land"})
            )
        if card in {"Ravenform", "Resculpt"}:
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and bool(targets[0].types & {"Artifact", "Creature"})
            )
        if card == "Vandalblast":
            if "overload" in action.additional_costs:
                return any(
                    "Artifact" in p.types and not _controlled_by_us(p) for p in state.battlefield
                )
            return (
                len(targets) == 1
                and targets[0] in state.battlefield
                and "Artifact" in targets[0].types
                and not _controlled_by_us(targets[0])
            )
        if card in {"Fiery Cannonade", "Lazotep Plating", "Rebuild"}:
            return True
        if card == "Prismari Command":
            return (
                len(action.modes) == 2
                and len(set(action.modes)) == 2
                and all(
                    m in {"damage", "draw_discard", "loot", "treasure", "destroy_artifact"}
                    for m in action.modes
                )
            )
    except Exception:
        return False
    return True


def validate_action(state: GameState, action: Action) -> ValidationResult:
    errors: list[str] = []
    refs: list[str] = ["CR 117.5"]
    if action.action_type in {ActionType.CAST_SPELL, ActionType.ACTIVATE_ABILITY}:
        errors.extend(validate_timing(state, action.timing))
        refs.extend(TIMING_RULES_REFS)
    if action.action_type is ActionType.CAST_SPELL:
        origin = action.origin_zone
        if action.source_name in state.hand and origin is None:
            origin = "hand"
        elif action.source_name in state.command_zone and origin is None:
            origin = "command_zone"
        elif action.source_name in state.graveyard and origin is None:
            origin = "graveyard"
        if origin == "hand":
            if action.source_name not in state.hand:
                errors.append(f"{action.source_name} is not in hand")
        elif origin == "command_zone":
            if action.source_name not in state.command_zone:
                errors.append(f"{action.source_name} is not in command zone")
        elif origin == "graveyard":
            if (
                action.source_name != "Faithless Looting"
                and not (action.source_name == "Commit // Memory" and action.choice == "Memory")
                and not action.source_name == "Electroduplicate"
            ):
                errors.append(f"{action.source_name} cannot be cast from graveyard")
            if action.source_name not in state.graveyard:
                errors.append(f"{action.source_name} is not in graveyard")
        else:
            errors.append(f"{action.source_name} is not in hand, graveyard, or command zone")
        if action.source_name in COMMANDER_BASE_COSTS:
            expected = commander_action_cost(action.source_name, state, origin)
            if not _costs_equal(action.mana_cost, expected):
                errors.append(
                    f"incorrect commander cost for {action.source_name}: expected {expected}"
                )
        elif action.source_name is not None and action.mana_cost is not None:
            expected_cost = CARD_COSTS.get(action.source_name, {})
            if action.source_name == "Faithless Looting" and origin == "graveyard":
                expected_cost = {"generic": 2, "R": 1}
            if action.source_name == "Commit // Memory" and action.choice == "Memory":
                expected_cost = {"generic": 4, "U": 2}
            if action.source_name == "Electroduplicate" and origin == "graveyard":
                expected_cost = {"generic": 3, "R": 2}
            if action.source_name == "Invert // Invent" and action.choice == "Invent":
                expected_cost = {"generic": 4, "U": 1, "R": 1}
            if action.source_name == "Syncopate" and action.x_value is not None:
                expected_cost = _x_cost(CARD_COSTS["Syncopate"], action.x_value)
            if (
                action.source_name in {"By Force", "Curse of the Swine"}
                and action.x_value is not None
            ):
                expected_cost = _x_cost(CARD_COSTS[action.source_name], action.x_value)
            if action.source_name == "Wash Away" and "cleave" in action.additional_costs:
                expected_cost = {"generic": 2, "U": 1}
            if action.source_name == "Into the Roil" and "kicker" in action.additional_costs:
                expected_cost = {"generic": 3, "U": 1}
            if action.source_name == "Vandalblast" and "overload" in action.additional_costs:
                expected_cost = {"generic": 4, "R": 1}
            if not _costs_equal(action.mana_cost, expected_cost):
                errors.append(f"incorrect spell cost for {action.source_name}")
        if action.source_name in {
            "Twinflame",
            "Electroduplicate",
            "Curiosity",
            "Crab Umbra",
            "Expedite",
        } and not _is_creature_target(state, list(action.targets)):
            errors.append(f"{action.source_name} requires one legal creature target")
            refs.extend(TARGET_RULES_REFS)
        interaction_cards = {
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
            "Rebuild",
            "Resculpt",
            "Spell Pierce",
            "Syncopate",
            "Vandalblast",
            "Wash Away",
        }
        if action.source_name in interaction_cards and not _spell_action_is_legal_by_text(
            state, action
        ):
            errors.append(f"{action.source_name} has no legal mode or target")
            refs.extend(TARGET_RULES_REFS)
        if action.source_name == "Commit // Memory" and action.choice != "Memory":
            if action.choice != "Commit" or (action.stack_target is None and not action.targets):
                errors.append("Commit requires choosing Commit and a legal target")
        if (
            action.source_name == "Commit // Memory"
            and action.choice == "Commit"
            and action.stack_target is not None
            and action.stack_target not in state.stack
        ):
            errors.append("Commit stack target must be on the stack")
        if solve_mana_payment(state.mana_pool, action.mana_cost or {}) is None:
            errors.append("insufficient mana")
    elif action.action_type is ActionType.ACTIVATE_ABILITY:
        ability_id = action.ability_id or _default_ability_id(action.source_name)
        key = (action.source_name or "", ability_id or "")
        if key not in ABILITY_COSTS:
            errors.append(f"unsupported activated ability: {action.source_name}:{ability_id}")
        else:
            if not _costs_equal(action.mana_cost, ABILITY_COSTS[key]):
                errors.append(f"incorrect ability cost for {action.source_name}:{ability_id}")
            if solve_mana_payment(state.mana_pool, action.mana_cost or {}) is None:
                errors.append("insufficient mana")
            source = next((p for p in state.battlefield if p.name == action.source_name), None)
            hand_ability_sources = {
                "Ash Barrens",
                "Dizzy Spell",
                "Drift of Phantasms",
                "Muddle the Mixture",
                "Step Through",
                "Vedalken Aethermage",
                "Rebuild",
            }
            if action.source_name in hand_ability_sources:
                if action.source_name not in state.hand:
                    errors.append(f"{action.source_name} ability source must be in hand")
                if ability_id == "transmute":
                    errors.extend(validate_timing(state, "sorcery"))
                    try:
                        exact_mv = (
                            action.choice is not None
                            and mana_value(action.choice, zone="library")
                            == TRANSMUTE_VALUES[action.source_name or ""]
                        )
                    except RulesError:
                        exact_mv = False
                    if not exact_mv:
                        errors.append("transmute target must have exact mana value")
                if ability_id == "wizardcycling" and (
                    action.choice is None or "Wizard" not in CARD_SUBTYPES.get(action.choice, set())
                ):
                    errors.append("Wizardcycling finds only Wizards")
            elif source is None:
                errors.append(f"{action.source_name} is not on battlefield")
            elif source.tapped and action.source_name != "Glint-Horn Buccaneer":
                errors.append("activated ability source is already tapped")
            if action.source_name == "Glint-Horn Buccaneer":
                if source is None or not source.attacking:
                    errors.append("Glint-Horn Buccaneer can activate only while attacking")
                if not state.hand:
                    errors.append("Glint-Horn activation requires a discarded card")
            if (
                action.source_name in {"Lightning-Rig Crew", "Niv-Mizzet, the Firemind"}
                and source is not None
                and source.summoning_sick
                and not source.haste
            ):
                errors.append(
                    f"{action.source_name} activated ability is restricted by summoning sickness"
                )
            if action.source_name == "Siren Stormtamer" and ability_id == "sacrifice_counter":
                if action.stack_target is None or action.stack_target not in state.stack:
                    errors.append("Siren Stormtamer requires a legal stack target")
                elif not (
                    getattr(action.stack_target, "targets_player", False)
                    or any(
                        _controlled_by_us(t) and "Creature" in t.types
                        for t in action.stack_target.targets
                    )
                ):
                    errors.append("Siren Stormtamer target must target you or your creature")
            if action.source_name in {
                "Evolving Wilds",
                "Terramorphic Expanse",
                "Ash Barrens",
            } and not any(c in {"Island", "Mountain"} for c in state.library):
                errors.append("fetch ability requires an Island or Mountain in library")
            if action.source_name == "Scavenger Grounds" and not any(
                "Desert" in p.subtypes or p.name == "Scavenger Grounds" for p in state.battlefield
            ):
                errors.append("Scavenger Grounds requires sacrificing a Desert")
            if action.source_name == "Demolition Field":
                if not action.targets or not any(
                    t in state.battlefield
                    and "Land" in t.types
                    and t.name not in {"Island", "Mountain"}
                    for t in action.targets
                ):
                    errors.append("Demolition Field requires a legal nonbasic land target")
                if action.choice not in {"Island", "Mountain", None}:
                    errors.append("Demolition Field can search only a legal basic land")
    elif action.action_type is ActionType.PLAY_LAND:
        if action.source_name not in state.hand:
            errors.append(f"{action.source_name} is not in hand")
        if action.source_name not in LAND_MANA and action.source_name not in {
            "Evolving Wilds",
            "Terramorphic Expanse",
        }:
            errors.append(f"unsupported land play: {action.source_name}")
        if state.land_played:
            errors.append("only one land play per turn")
    elif action.action_type is ActionType.ACTIVATE_MANA_ABILITY:
        source = next((p for p in state.battlefield if p.name == action.source_name), None)
        if source is None:
            errors.append(f"{action.source_name} is not on battlefield")
        elif source.tapped:
            errors.append("permanent is already tapped")
        elif source.name == "Treasure":
            pass
        elif (
            source.name not in LAND_MANA
            and source.name not in MANA_ROCK_MANA
            and not source.mana_abilities
        ):
            errors.append(f"no mana behavior for {source.name}")
        elif action.mana_choice and action.mana_choice not in _legal_mana_outputs(source):
            errors.append(f"illegal mana choice for {source.name}")
        elif (
            source.name == "Cascade Bluffs"
            and state.mana_pool.get("U", 0) + state.mana_pool.get("R", 0) < 1
        ):
            errors.append("Cascade Bluffs requires blue or red input mana")
        elif (
            source.name in {"Izzet Signet", "Prismatic Lens"}
            and action.mana_choice in COLORED_MANA
            and solve_mana_payment(state.mana_pool, {"generic": 1}) is None
        ):
            errors.append(f"{source.name} requires input mana")
    elif action.action_type is ActionType.DECLARE_ATTACKERS:
        if state.phase is not Phase.COMBAT:
            errors.append("attackers are declared only during combat")
        for target in action.targets:
            if target not in state.battlefield or "Creature" not in target.types:
                errors.append("only battlefield creatures can attack")
            elif target.tapped or (target.summoning_sick and not target.haste):
                errors.append("creature cannot legally attack")
    elif action.action_type is ActionType.COMBAT_DAMAGE:
        if state.phase is not Phase.COMBAT:
            errors.append("combat damage occurs only during combat")
        if not any(p.attacking for p in state.battlefield):
            errors.append("combat damage requires attacking creatures")
    elif action.action_type is not ActionType.PASS_PRIORITY:
        errors.append(f"unsupported action type: {action.action_type}")
    normalized = action
    if (
        not errors
        and action.action_type is ActionType.ACTIVATE_ABILITY
        and action.ability_id is None
    ):
        normalized = Action(
            action.action_type,
            action.source_name,
            action.targets,
            action.mana_cost,
            action.additional_costs,
            action.timing,
            action.effect,
            action.optional_draw_decline,
            action.mana_choice,
            _default_ability_id(action.source_name),
            action.origin_zone,
        )
    return ValidationResult(
        not errors, tuple(errors), tuple(dict.fromkeys(refs)), normalized if not errors else None
    )


def generate_legal_actions(state: GameState) -> list[Action]:
    if state.terminal:
        return []
    actions: list[Action] = [Action(ActionType.PASS_PRIORITY)]
    for card in sorted(set(state.hand)):
        if card in LAND_MANA or card in {"Evolving Wilds", "Terramorphic Expanse"}:
            choice = "R" if card == "Thriving Isle" else None
            candidate = Action(ActionType.PLAY_LAND, card, timing="sorcery", mana_choice=choice)
            if validate_action(state, candidate).accepted:
                actions.append(candidate)
        if card in TRANSMUTE_VALUES:
            for target in sorted(set(state.library)):
                candidate = Action(
                    ActionType.ACTIVATE_ABILITY,
                    card,
                    mana_cost={"generic": 1, "U": 2},
                    ability_id="transmute",
                    timing="sorcery",
                    choice=target,
                )
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)
        if card in WIZARDCYCLING_COSTS:
            for target in sorted(set(state.library)):
                candidate = Action(
                    ActionType.ACTIVATE_ABILITY,
                    card,
                    mana_cost=WIZARDCYCLING_COSTS[card],
                    ability_id="wizardcycling",
                    choice=target,
                )
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)
        if card == "Rebuild":
            candidate = Action(
                ActionType.ACTIVATE_ABILITY,
                card,
                mana_cost=CYCLING_COSTS[card],
                ability_id="cycling",
            )
            if validate_action(state, candidate).accepted:
                actions.append(candidate)
        if card in CARD_COSTS or card in CREATURES or card in MANA_ROCK_MANA:
            target_options: tuple[tuple[Permanent, ...], ...] = ((),)
            if card in {"Twinflame", "Electroduplicate", "Curiosity", "Crab Umbra", "Expedite"}:
                target_options = tuple(
                    (p,) for p in state.battlefield if "Creature" in p.types
                ) or ((),)
            if card == "Invert // Invent":
                for p in state.battlefield:
                    if "Creature" in p.types:
                        candidate = Action(
                            ActionType.CAST_SPELL,
                            card,
                            (p,),
                            {"U": 1},
                            timing="instant",
                            origin_zone="hand",
                            choice="Invert",
                        )
                        if validate_action(state, candidate).accepted:
                            actions.append(candidate)
                for inst in sorted(
                    c for c in set(state.library) if "Instant" in CARD_TYPES.get(c, set())
                ):
                    candidate = Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost={"generic": 4, "U": 1, "R": 1},
                        timing="instant",
                        origin_zone="hand",
                        choice="Invent",
                        additional_costs=(f"instant:{inst}",),
                    )
                    if validate_action(state, candidate).accepted:
                        actions.append(candidate)
                continue
            if card == "Long-Term Plans":
                for target in sorted(set(state.library)):
                    candidate = Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost=CARD_COSTS[card],
                        timing="instant",
                        origin_zone="hand",
                        choice=target,
                    )
                    if validate_action(state, candidate).accepted:
                        actions.append(candidate)
                continue
            for target_tuple in target_options:
                candidate = Action(
                    ActionType.CAST_SPELL,
                    card,
                    target_tuple,
                    CARD_COSTS.get(card, {}),
                    timing="sorcery"
                    if card
                    not in {
                        "Opt",
                        "Expedite",
                        "Impulse",
                        "Fact or Fiction",
                        "Frantic Search",
                        "Prismari Command",
                        "Commit // Memory",
                        "Dualcaster Mage",
                    }
                    else "instant",
                    origin_zone="hand",
                    choice="Commit" if card == "Commit // Memory" else None,
                    stack_target=state.stack[-1]
                    if card == "Commit // Memory" and state.stack
                    else None,
                )
                if card in {
                    "Chart a Course",
                    "Faithless Looting",
                    "Frantic Search",
                    "Prismari Command",
                }:
                    candidate = Action(
                        candidate.action_type,
                        candidate.source_name,
                        candidate.targets,
                        candidate.mana_cost,
                        tuple(f"discard:{x}" for x in state.hand if x != card)[:2],
                        candidate.timing,
                        candidate.effect,
                        False,
                        None,
                        None,
                        candidate.origin_zone,
                        candidate.choice,
                        ("loot", "treasure") if card == "Prismari Command" else (),
                    )
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)

        # Phase 9F-3 interaction adapters. They generate only when legal targets exist.
        if card in {
            "Arcane Denial",
            "Dispel",
            "Negate",
            "Spell Pierce",
            "Syncopate",
            "Wash Away",
            "Change the Equation",
        }:
            for obj in list(state.stack):
                variants: list[Action] = []
                if card == "Arcane Denial":
                    variants.append(
                        _stack_target_action(card, obj, CARD_COSTS[card], choice="target_draw_2")
                    )
                elif card == "Dispel":
                    variants.append(_stack_target_action(card, obj, CARD_COSTS[card]))
                elif card == "Negate":
                    variants.append(_stack_target_action(card, obj, CARD_COSTS[card]))
                elif card == "Spell Pierce":
                    variants.append(
                        _stack_target_action(
                            card, obj, CARD_COSTS[card], choice="opponent_declines_pay"
                        )
                    )
                elif card == "Syncopate":
                    for x in range(1, 7):
                        variants.append(
                            _stack_target_action(
                                card,
                                obj,
                                _x_cost(CARD_COSTS[card], x),
                                x_value=x,
                                choice="opponent_declines_pay",
                            )
                        )
                elif card == "Wash Away":
                    variants.append(
                        _stack_target_action(card, obj, CARD_COSTS[card], choice="base")
                    )
                    variants.append(
                        _stack_target_action(
                            card,
                            obj,
                            {"generic": 2, "U": 1},
                            choice="cleave",
                            modes=("cleave",),
                            x_value=None,
                        )
                    )
                    variants[-1] = Action(
                        variants[-1].action_type,
                        variants[-1].source_name,
                        variants[-1].targets,
                        variants[-1].mana_cost,
                        ("cleave",),
                        variants[-1].timing,
                        variants[-1].effect,
                        variants[-1].optional_draw_decline,
                        variants[-1].mana_choice,
                        variants[-1].ability_id,
                        variants[-1].origin_zone,
                        variants[-1].choice,
                        variants[-1].modes,
                        variants[-1].stack_target,
                        variants[-1].x_value,
                    )
                elif card == "Change the Equation":
                    variants.extend(
                        [
                            _stack_target_action(card, obj, CARD_COSTS[card], modes=("small",)),
                            _stack_target_action(card, obj, CARD_COSTS[card], modes=("red_green",)),
                        ]
                    )
                for candidate in variants:
                    if validate_action(state, candidate).accepted:
                        actions.append(candidate)
            continue
        if card in {
            "Abrade",
            "Aetherize",
            "Brotherhood's End",
            "By Force",
            "Curse of the Swine",
            "Echoing Truth",
            "Fading Hope",
            "Fiery Cannonade",
            "Into the Roil",
            "Introduction to Annihilation",
            "Lazotep Plating",
            "Ravenform",
            "Reality Ripple",
            "Reality Shift",
            "Rebuild",
            "Resculpt",
            "Vandalblast",
        }:
            variants = []
            if card == "Aetherize":
                variants.append(
                    Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost=CARD_COSTS[card],
                        timing="instant",
                        origin_zone="hand",
                    )
                )
            elif card == "Brotherhood's End":
                variants += [
                    Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost=CARD_COSTS[card],
                        timing="sorcery",
                        origin_zone="hand",
                        modes=("damage",),
                    ),
                    Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost=CARD_COSTS[card],
                        timing="sorcery",
                        origin_zone="hand",
                        modes=("artifacts",),
                    ),
                ]
            elif card in {"Fiery Cannonade", "Lazotep Plating", "Rebuild"}:
                variants.append(
                    Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost=CARD_COSTS[card],
                        timing="instant",
                        origin_zone="hand",
                    )
                )
            elif card == "Vandalblast":
                for t in state.battlefield:
                    variants.append(
                        Action(
                            ActionType.CAST_SPELL,
                            card,
                            (t,),
                            CARD_COSTS[card],
                            timing="sorcery",
                            origin_zone="hand",
                        )
                    )
                variants.append(
                    Action(
                        ActionType.CAST_SPELL,
                        card,
                        mana_cost={"generic": 4, "R": 1},
                        additional_costs=("overload",),
                        timing="sorcery",
                        origin_zone="hand",
                    )
                )
            elif card in {"By Force", "Curse of the Swine"}:
                pool = [
                    p
                    for p in state.battlefield
                    if ("Artifact" in p.types if card == "By Force" else "Creature" in p.types)
                ]
                for x, t in enumerate(pool[:6], start=1):
                    variants.append(
                        Action(
                            ActionType.CAST_SPELL,
                            card,
                            tuple(pool[:x]),
                            _x_cost(CARD_COSTS[card], x),
                            timing="sorcery",
                            origin_zone="hand",
                            x_value=x,
                        )
                    )
            else:
                for t in state.battlefield:
                    modes = (
                        (("damage_creature",), ("destroy_artifact",)) if card == "Abrade" else ((),)
                    )
                    for m in modes:
                        cost = CARD_COSTS[card]
                        if card == "Into the Roil":
                            variants.append(
                                Action(
                                    ActionType.CAST_SPELL,
                                    card,
                                    (t,),
                                    cost,
                                    timing="instant",
                                    origin_zone="hand",
                                )
                            )
                            variants.append(
                                Action(
                                    ActionType.CAST_SPELL,
                                    card,
                                    (t,),
                                    {"generic": 3, "U": 1},
                                    additional_costs=("kicker",),
                                    timing="instant",
                                    origin_zone="hand",
                                )
                            )
                        else:
                            variants.append(
                                Action(
                                    ActionType.CAST_SPELL,
                                    card,
                                    (t,),
                                    cost,
                                    timing="instant"
                                    if "Instant" in CARD_TYPES.get(card, set())
                                    else "sorcery",
                                    origin_zone="hand",
                                    modes=m,
                                )
                            )
            for candidate in variants:
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)
            continue
    if "Faithless Looting" in state.graveyard:
        candidate = Action(
            ActionType.CAST_SPELL,
            "Faithless Looting",
            mana_cost={"generic": 2, "R": 1},
            additional_costs=tuple(f"discard:{x}" for x in state.hand)[:2],
            timing="sorcery",
            origin_zone="graveyard",
        )
        if validate_action(state, candidate).accepted:
            actions.append(candidate)
    if "Electroduplicate" in state.graveyard:
        for pmt in state.battlefield:
            if "Creature" in pmt.types:
                candidate = Action(
                    ActionType.CAST_SPELL,
                    "Electroduplicate",
                    (pmt,),
                    mana_cost={"generic": 3, "R": 2},
                    timing="sorcery",
                    origin_zone="graveyard",
                )
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)
    if "Commit // Memory" in state.graveyard:
        candidate = Action(
            ActionType.CAST_SPELL,
            "Commit // Memory",
            mana_cost={"generic": 4, "U": 2},
            timing="sorcery",
            origin_zone="graveyard",
            choice="Memory",
        )
        if validate_action(state, candidate).accepted:
            actions.append(candidate)
    for commander in sorted(set(state.command_zone)):
        if commander in COMMANDER_BASE_COSTS:
            candidate = Action(
                ActionType.CAST_SPELL,
                commander,
                mana_cost=commander_action_cost(commander, state, "command_zone"),
                timing="sorcery",
                origin_zone="command_zone",
            )
            if validate_action(state, candidate).accepted:
                actions.append(candidate)
    for permanent in state.battlefield:
        for output in _legal_mana_outputs(permanent):
            candidate = Action(ActionType.ACTIVATE_MANA_ABILITY, permanent.name, mana_choice=output)
            if validate_action(state, candidate).accepted:
                actions.append(candidate)
        for ability_id, cost in sorted(
            (aid, cost) for (name, aid), cost in ABILITY_COSTS.items() if name == permanent.name
        ):
            if permanent.name == "Siren Stormtamer" and ability_id == "sacrifice_counter":
                for obj in state.stack:
                    ability = Action(
                        ActionType.ACTIVATE_ABILITY,
                        permanent.name,
                        mana_cost=cost,
                        ability_id=ability_id,
                        stack_target=obj,
                    )
                    if validate_action(state, ability).accepted:
                        actions.append(ability)
                continue
            ability = Action(
                ActionType.ACTIVATE_ABILITY, permanent.name, mana_cost=cost, ability_id=ability_id
            )
            if validate_action(state, ability).accepted:
                actions.append(ability)
    attackers = tuple(
        p
        for p in state.battlefield
        if "Creature" in p.types and not p.tapped and (not p.summoning_sick or p.haste)
    )
    if attackers:
        candidate = Action(ActionType.DECLARE_ATTACKERS, "attack", attackers)
        if validate_action(state, candidate).accepted:
            actions.append(candidate)
    damage = Action(ActionType.COMBAT_DAMAGE, "combat_damage")
    if validate_action(state, damage).accepted:
        actions.append(damage)
    return actions


def execute_action(state: GameState, action: Action) -> None:
    result = validate_action(state, action)
    if not result.accepted:
        raise RulesError("; ".join(result.errors))
    if action.action_type is ActionType.PASS_PRIORITY:
        state.record_event("action", "pass_priority")
        if state.stack:
            state.resolve_top()
        else:
            state.would_receive_priority()
        return
    if action.action_type is ActionType.CAST_SPELL:
        assert action.source_name is not None
        normalized = result.normalized_action or action
        origin_zone = normalized.origin_zone
        if origin_zone == "hand":
            state.hand.remove(action.source_name)
        elif origin_zone == "command_zone":
            state.command_zone.remove(action.source_name)
        elif origin_zone == "graveyard":
            state.graveyard.remove(action.source_name)
        state.pay_mana(normalized.mana_cost or {})
        if origin_zone == "command_zone":
            state.commander_casts[action.source_name] = (
                state.commander_casts.get(action.source_name, 0) + 1
            )
        state.record_event("action", f"cast:{action.source_name}:from:{origin_zone}")
        effect = action.effect or _spell_effect_for_action(normalized)
        state.stack.append(
            StackObject(
                action.source_name,
                "spell",
                effect,
                list(action.targets),
                legal_targets=_is_creature_target
                if action.targets
                and action.source_name
                not in {
                    "Commit // Memory",
                    "Invert // Invent",
                    "Abrade",
                    "By Force",
                    "Curse of the Swine",
                    "Echoing Truth",
                    "Fading Hope",
                    "Into the Roil",
                    "Introduction to Annihilation",
                    "Ravenform",
                    "Reality Ripple",
                    "Reality Shift",
                    "Resculpt",
                    "Vandalblast",
                }
                else None,
                mana_value=mana_value(
                    action.source_name,
                    zone="stack",
                    face=action.choice or SPLIT_CARD_FACES[action.source_name][0],
                )
                if action.source_name in SPLIT_CARD_FACES
                else mana_value(action.source_name)
                if action.source_name in MANA_VALUES or action.source_name in TRANSMUTE_VALUES
                else None,
                types=set(
                    CARD_TYPES.get(
                        action.source_name,
                        {"Artifact"} if action.source_name in MANA_ROCK_MANA else set(),
                    )
                ),
                colors=set(CARD_COLORS.get(action.source_name, set())),
                cast_from_hand=origin_zone == "hand",
                chosen_face=action.choice,
            )
        )
        state.would_receive_priority()
        return
    if action.action_type is ActionType.PLAY_LAND:
        assert action.source_name is not None
        state.hand.remove(action.source_name)
        play_land(
            state,
            action.source_name,
            chosen_color=action.mana_choice,
            reveal=action.targets[0].name if action.targets else None,
        )
        state.record_event("action", f"play_land:{action.source_name}")
        return
    if action.action_type is ActionType.ACTIVATE_MANA_ABILITY:
        source = next(p for p in state.battlefield if p.name == action.source_name)
        if source.name == "Treasure":
            sacrifice_treasure_for_mana(state, action.mana_choice or "U")
        else:
            tap_for_mana(state, source, action.mana_choice)
        state.record_event("action", f"activate_mana:{action.source_name}")
        return
    if action.action_type is ActionType.DECLARE_ATTACKERS:
        declare_attackers(
            state, list(action.targets), None if action.choice is None else int(action.choice)
        )
        return
    if action.action_type is ActionType.COMBAT_DAMAGE:
        ensure_not_terminal(state)
        attackers = [p for p in state.battlefield if p.attacking]
        damaged_by_pirate: dict[int, int] = {}
        prevented: set[int] = set()
        for attacker in attackers:
            if state.terminal:
                break
            opponent = int(getattr(attacker, "defending_opponent", 0))
            if opponent not in state.active_opponents():
                continue
            damage = attacker.power
            if damage is None and attacker.name in CREATURE_STATS:
                damage = CREATURE_STATS[attacker.name][0]
            if damage is None:
                raise RulesError(f"combat damage source has no modeled power: {attacker.name}")
            if attacker.damage_prevented:
                if "Pirate" in attacker.subtypes:
                    prevented.add(opponent)
                continue
            state.opponent_life[opponent] -= damage
            state.record_event(
                "combat_damage_dealt", f"{attacker.name}:opponent_{opponent}:{damage}"
            )
            if "Pirate" in attacker.subtypes:
                damaged_by_pirate[opponent] = damaged_by_pirate.get(opponent, 0) + damage
        if (
            damaged_by_pirate
            and not state.terminal
            and any(p.name == "Malcolm, Keen-Eyed Navigator" for p in state.battlefield)
        ):
            create_malcolm_treasures_for_pirate_damage(state, damaged_by_pirate, prevented)
        if (
            damaged_by_pirate
            and not state.terminal
            and any(p.name == "Breeches, Brazen Plunderer" for p in state.battlefield)
        ):
            for opponent in damaged_by_pirate:
                unknown = f"unknown_opponent_{opponent}_top_card"
                state.breeches_unknown_exiled.append(unknown)
                state.record_event("breeches_unknown_exiled", unknown)
        for attacker in attackers:
            attacker.attacking = False
        if not state.terminal:
            state.record_event("combat_damage", "unblocked")
            state.would_receive_priority()
        return
    if action.action_type is ActionType.ACTIVATE_ABILITY:
        normalized = result.normalized_action or action
        ability_source: Permanent | None = next(
            (p for p in state.battlefield if p.name == action.source_name), None
        )
        if (
            ability_source is None
            and action.source_name == "Ash Barrens"
            and normalized.ability_id == "basic_landcycling"
        ):
            ability_source = Permanent("Ash Barrens", {"Land"})
        if ability_source is None and action.source_name in {
            "Dizzy Spell",
            "Drift of Phantasms",
            "Muddle the Mixture",
            "Step Through",
            "Vedalken Aethermage",
            "Rebuild",
        }:
            ability_source = Permanent(action.source_name, {"Card"})
        if ability_source is None:
            raise RulesError(f"{action.source_name} is not on battlefield")
        state.record_event("action", f"activate:{action.source_name}:{normalized.ability_id}")
        execute_activated_ability(state, ability_source, normalized)
        state.would_receive_priority()


def _activate_lightning_rig_crew(state: GameState, crew: Permanent) -> None:
    if crew not in state.battlefield or crew.name != "Lightning-Rig Crew":
        raise RulesError("Lightning-Rig Crew must be on battlefield")
    if crew.tapped:
        raise RulesError("Lightning-Rig Crew is already tapped")
    if crew.summoning_sick and not crew.haste:
        raise RulesError("Lightning-Rig Crew activated ability is restricted by summoning sickness")
    crew.tapped = True

    def effect(current: GameState) -> None:
        deal_noncombat_damage(
            current, list(current.active_opponents()), 1, source_name="Lightning-Rig Crew"
        )

    state.stack.append(
        StackObject("Lightning-Rig Crew damage ability", "ability", effect, cast=False)
    )


def _activate_mind_stone_draw(state: GameState, source: Permanent) -> None:
    state.pay_mana({"generic": 1})
    if source.tapped or source not in state.battlefield or source.name != "Mind Stone":
        raise RulesError("Mind Stone draw ability requires untapped source on battlefield")
    source.tapped = True
    state.battlefield.remove(source)
    state.graveyard.append("Mind Stone")
    state.draw(1)


def _activate_fetch_land(state: GameState, source: Permanent) -> None:
    if (
        source.tapped
        or source not in state.battlefield
        or source.name not in {"Evolving Wilds", "Terramorphic Expanse"}
    ):
        raise RulesError("fetch ability requires untapped source on battlefield")
    basic = next((card for card in state.library if card in {"Island", "Mountain"}), None)
    if basic is None:
        raise RulesError("fetch ability requires an Island or Mountain in library")
    source.tapped = True
    state.battlefield.remove(source)
    state.graveyard.append(source.name)
    state.library.remove(basic)
    state.battlefield.append(Permanent(basic, {"Land"}, {basic}, tapped=True, summoning_sick=False))
    random.Random(0).shuffle(state.library)
    state.record_event("shuffle", source.name)


def execute_activated_ability(state: GameState, source: Permanent, action: Action) -> None:
    ability_id = action.ability_id
    if source.name == "Glint-Horn Buccaneer" and ability_id == "draw_discard_damage":
        activate_glint_horn(state, source)
    elif source.name == "Lightning-Rig Crew" and ability_id == "tap_damage_each_opponent":
        _activate_lightning_rig_crew(state, source)
    elif source.name == "Mind Stone" and ability_id == "draw":
        _activate_mind_stone_draw(state, source)
    elif source.name == "Soul-Guide Lantern" and ability_id == "exile_opponents_graveyards":
        soul_guide_lantern_exile_opponents(state, source)
    elif source.name == "Soul-Guide Lantern" and ability_id == "draw":
        soul_guide_lantern_draw(state, source)
    elif source.name == "Sentinel Totem" and ability_id == "exile_all_graveyards":
        sentinel_totem_exile_all_graveyards(state, source)
    elif source.name in {"Evolving Wilds", "Terramorphic Expanse"} and ability_id == "basic_fetch":
        _activate_fetch_land(state, source)
    elif source.name == "Ash Barrens" and ability_id == "basic_landcycling":
        state.pay_mana({"generic": 1})
        if "Ash Barrens" not in state.hand:
            raise RulesError("Ash Barrens basic landcycling source must be in hand")
        state.hand.remove("Ash Barrens")
        state.graveyard.append("Ash Barrens")
        _search_one(state, "Island" if "Island" in state.library else "Mountain")
    elif source.name == "Scavenger Grounds" and ability_id == "exile_graveyards":
        state.pay_mana({"generic": 2})
        desert = next(
            (
                p
                for p in state.battlefield
                if "Desert" in p.subtypes or p.name == "Scavenger Grounds"
            ),
            None,
        )
        if desert is None:
            raise RulesError("Scavenger Grounds requires sacrificing a Desert")
        source.tapped = True
        state.battlefield.remove(desert)
        state.graveyard.append(desert.name)
        state.graveyard.clear()
        state.record_event("graveyards_exiled", "Scavenger Grounds")
    elif source.name == "Demolition Field" and ability_id == "destroy_nonbasic":
        state.pay_mana({"generic": 2})
        target = action.targets[0] if action.targets else None
        if (
            target is None
            or target not in state.battlefield
            or "Land" not in target.types
            or target.name in {"Island", "Mountain"}
        ):
            raise RulesError("Demolition Field requires a legal nonbasic land target")
        source.tapped = True
        state.battlefield.remove(source)
        state.graveyard.append(source.name)
        state.battlefield.remove(target)
        state.graveyard.append(target.name)
        state.record_event("nonbasic_destroyed", target.name)
        if action.choice in state.library and action.choice in {"Island", "Mountain"}:
            state.library.remove(action.choice)
            state.battlefield.append(Permanent(action.choice, {"Land"}, {action.choice}))
            state.record_event("tutor_found", action.choice)
            state.record_event("shuffle_library")
    elif ability_id == "transmute" and source.name in TRANSMUTE_VALUES:
        transmute(state, source.name, action.choice or "")
    elif ability_id == "wizardcycling" and source.name in WIZARDCYCLING_COSTS:
        wizardcycle(state, action.choice or "", source.name)
    elif ability_id == "cycling" and source.name == "Rebuild":
        cycle(state, "Rebuild")
    elif source.name == "Siren Stormtamer" and ability_id == "sacrifice_counter":
        state.pay_mana({"U": 1})
        if action.stack_target is None:
            raise RulesError("Siren Stormtamer ability requires a stack target")
        siren_stormtamer_counter(state, source, action.stack_target)
    elif source.name == "Spectral Sailor" and ability_id == "draw":
        state.pay_mana({"generic": 3, "U": 1})
        state.stack.append(
            StackObject(
                "Spectral Sailor draw ability", "ability", lambda ss: ss.draw(1), cast=False
            )
        )
    elif source.name == "Niv-Mizzet, the Firemind" and ability_id == "tap_draw":
        if source.tapped or (source.summoning_sick and not source.haste):
            raise RulesError("Niv-Mizzet tap ability is restricted by summoning sickness")
        source.tapped = True
        state.stack.append(
            StackObject("Niv-Mizzet draw ability", "ability", lambda ss: ss.draw(1), cast=False)
        )
    elif source.name == "Crab Umbra" and ability_id == "untap_enchanted":
        state.pay_mana({"generic": 2, "U": 1})
        enchanted = next((p for p in state.battlefield if p.damage_prevented and p.tapped), None)
        if enchanted is None:
            raise RulesError("Crab Umbra requires a tapped enchanted creature")
        enchanted.tapped = False
        state.record_event("untap", enchanted.name)
    else:
        raise RulesError(f"unregistered activated ability handler: {source.name}:{ability_id}")


# Phase 5C deck-scoped interaction and zone-changing primitives.


def _controlled_by_us(permanent: Permanent) -> bool:
    return getattr(permanent, "controller", 0) == 0


def _is_spell(obj: StackObject) -> bool:
    return obj.kind in {"spell", "copy"}


def _spell_types(obj: StackObject) -> set[str]:
    return getattr(obj, "types", set())


def _spell_colors(obj: StackObject) -> set[str]:
    return getattr(obj, "colors", set())


def _put_spell_in_graveyard(state: GameState, obj: StackObject) -> None:
    if obj in state.stack:
        state.stack.remove(obj)
    if obj.kind != "copy":
        state.graveyard.append(obj.name)
    state.record_event("spell_countered", obj.name)


def counter_spell(state: GameState, target: StackObject, *, exile: bool = False) -> None:
    if target not in state.stack or not _is_spell(target):
        raise RulesError("counter target must be a spell on the stack")
    state.stack.remove(target)
    if target.kind != "copy":
        (state.exile if exile else state.graveyard).append(target.name)
    state.record_event("spell_countered_exiled" if exile else "spell_countered", target.name)


def counter_unless_pays(
    state: GameState, target: StackObject, amount: int, *, exile: bool = False, pays: bool = False
) -> bool:
    if amount < 0:
        raise RulesError("conditional counter amount cannot be negative")
    if target not in state.stack or not _is_spell(target):
        raise RulesError("counter target must be a spell on the stack")
    if pays:
        state.record_event("conditional_counter_paid", target.name)
        return False
    counter_spell(state, target, exile=exile)
    return True


def arcane_denial(
    state: GameState, target: StackObject, *, target_controller_draws: int = 0
) -> None:
    if target_controller_draws not in {0, 1, 2}:
        raise RulesError("Arcane Denial target controller may draw up to two cards")
    counter_spell(state, target)
    state.record_event(
        "delayed_draw", f"Arcane Denial:self:1:target_controller:{target_controller_draws}"
    )


def negate(state: GameState, target: StackObject) -> None:
    if "Creature" in _spell_types(target):
        raise RulesError("Negate targets only noncreature spells")
    counter_spell(state, target)


def dispel(state: GameState, target: StackObject) -> None:
    if "Instant" not in _spell_types(target):
        raise RulesError("Dispel targets only instant spells")
    counter_spell(state, target)


def spell_pierce(state: GameState, target: StackObject, *, pays: bool = False) -> bool:
    if "Creature" in _spell_types(target):
        raise RulesError("Spell Pierce targets only noncreature spells")
    return counter_unless_pays(state, target, 2, pays=pays)


def syncopate(state: GameState, target: StackObject, x_value: int, *, pays: bool = False) -> bool:
    if x_value < 0:
        raise RulesError("Syncopate X must be nonnegative")
    return counter_unless_pays(state, target, x_value, exile=True, pays=pays)


def wash_away(state: GameState, target: StackObject, *, cleave: bool = False) -> None:
    if not cleave and getattr(target, "cast_from_hand", True):
        raise RulesError("Wash Away without cleave targets only spells not cast from hand")
    counter_spell(state, target)


def change_the_equation(
    state: GameState, target: StackObject, mode: Literal["small", "red_green"]
) -> None:
    mv = target.mana_value
    if mv is None:
        raise RulesError("target spell must have modeled mana value")
    if mode == "small":
        if mv > 2:
            raise RulesError("Change the Equation small mode requires mana value 2 or less")
    elif mode == "red_green":
        if mv > 6 or not (_spell_colors(target) & {"R", "G"}):
            raise RulesError(
                "Change the Equation color mode requires red or green spell mana value 6 or less"
            )
    else:
        raise RulesError("unsupported Change the Equation mode")
    counter_spell(state, target)


def _destroy_permanent(state: GameState, permanent: Permanent) -> None:
    if permanent not in state.battlefield:
        raise RulesError("target permanent is not on battlefield")
    state.battlefield.remove(permanent)
    if permanent.is_token:
        state.record_event("token_ceased_to_exist", permanent.name)
    else:
        state.graveyard.append(permanent.name)
        state.record_event("destroy", permanent.name)


def _bounce_permanent(state: GameState, permanent: Permanent) -> None:
    if permanent not in state.battlefield:
        raise RulesError("target permanent is not on battlefield")
    state.battlefield.remove(permanent)
    if permanent.is_token:
        state.record_event("token_ceased_to_exist", permanent.name)
    else:
        state.hand.append(permanent.name)
        state.record_event("bounce", permanent.name)


def _exile_permanent(state: GameState, permanent: Permanent) -> bool:
    if permanent not in state.battlefield:
        raise RulesError("target permanent is not on battlefield")
    state.battlefield.remove(permanent)
    if permanent.is_token:
        state.record_event("token_ceased_to_exist", permanent.name)
        return False
    state.exile.append(permanent.name)
    state.record_event("exile", permanent.name)
    return True


def abrade(
    state: GameState, mode: Literal["damage_creature", "destroy_artifact"], target: Permanent
) -> None:
    if mode == "damage_creature":
        if target not in state.battlefield or "Creature" not in target.types:
            raise RulesError("Abrade damage mode targets a creature")
        setattr(target, "damage", getattr(target, "damage", 0) + 3)
        state.record_event("damage", f"Abrade:{target.name}:3")
    elif mode == "destroy_artifact":
        if "Artifact" not in target.types:
            raise RulesError("Abrade destroy mode targets an artifact")
        _destroy_permanent(state, target)
    else:
        raise RulesError("unsupported Abrade mode")


def aetherize(state: GameState) -> None:
    for permanent in list(state.battlefield):
        if "Creature" in permanent.types and permanent.attacking:
            _bounce_permanent(state, permanent)


def echoing_truth(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or "Land" in target.types:
        raise RulesError("Echoing Truth targets a nonland permanent")
    name = target.name
    for permanent in list(state.battlefield):
        if permanent.name == name and "Land" not in permanent.types:
            _bounce_permanent(state, permanent)


def fading_hope(state: GameState, target: Permanent, *, bottom: bool = False) -> None:
    if target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Fading Hope targets a creature")
    mv = target.mana_value if hasattr(target, "mana_value") else None
    _bounce_permanent(state, target)
    if mv is not None and mv <= 3:
        state.record_event("scry", "1_bottom" if bottom else "1_top")


def into_the_roil(state: GameState, target: Permanent, *, kicked: bool = False) -> None:
    if target not in state.battlefield or "Land" in target.types:
        raise RulesError("Into the Roil targets a nonland permanent")
    _bounce_permanent(state, target)
    if kicked:
        state.draw(1)


def reality_ripple(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or not (target.types & {"Artifact", "Creature", "Land"}):
        raise RulesError("Reality Ripple targets an artifact, creature, or land")
    setattr(target, "phased_out", True)
    state.record_event("phase_out", target.name)


def token_copy(state: GameState, target: Permanent) -> Permanent:
    if target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("token-copy effect requires a creature target")
    token = Permanent(
        target.name,
        set(target.types),
        set(target.subtypes),
        is_token=True,
        power=target.power,
        toughness=target.toughness,
        haste=True,
        summoning_sick=False,
        mana_value=target.mana_value,
    )
    state.battlefield.append(token)
    state.record_event("token_created", f"copy:{target.name}")
    return token


def _create_token(
    state: GameState, name: str, types: set[str], subtypes: set[str], power: int, toughness: int
) -> Permanent:
    token = Permanent(name, types, subtypes, is_token=True, power=power, toughness=toughness)
    state.battlefield.append(token)
    state.record_event("token_created", name)
    return token


def ravenform(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or not (target.types & {"Artifact", "Creature"}):
        raise RulesError("Ravenform targets an artifact or creature")
    _exile_permanent(state, target)
    _create_token(state, "Bird", {"Creature"}, {"Bird"}, 1, 1).flying = True


def reality_shift(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or "Creature" not in target.types:
        raise RulesError("Reality Shift targets a creature")
    _exile_permanent(state, target)
    manifested = state.library.pop(0) if state.library else None
    token = _create_token(state, "Manifest", {"Creature"}, set(), 2, 2)
    setattr(token, "manifested_card", manifested)


def resculpt(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or not (target.types & {"Artifact", "Creature"}):
        raise RulesError("Resculpt targets an artifact or creature")
    _exile_permanent(state, target)
    _create_token(state, "Elemental", {"Creature"}, {"Elemental"}, 4, 4)


def curse_of_the_swine(state: GameState, targets: list[Permanent], x_value: int) -> None:
    if x_value != len(targets) or x_value < 0 or len(set(map(id, targets))) != len(targets):
        raise RulesError("Curse of the Swine requires X distinct target creatures")
    for target in targets:
        if target not in state.battlefield or "Creature" not in target.types:
            raise RulesError("Curse of the Swine targets only creatures")
    for target in list(targets):
        if _exile_permanent(state, target):
            pass
        _create_token(state, "Boar", {"Creature"}, {"Boar"}, 2, 2)


def introduction_to_annihilation(state: GameState, target: Permanent) -> None:
    if target not in state.battlefield or "Land" in target.types:
        raise RulesError("Introduction to Annihilation targets a nonland permanent")
    _exile_permanent(state, target)
    state.record_event("opponent_draw_or_self_draw", target.name)


def by_force(state: GameState, targets: list[Permanent], x_value: int) -> None:
    if x_value != len(targets) or x_value < 0 or len(set(map(id, targets))) != len(targets):
        raise RulesError("By Force requires X distinct target artifacts")
    for target in targets:
        if target not in state.battlefield or "Artifact" not in target.types:
            raise RulesError("By Force targets only artifacts")
    for target in list(targets):
        _destroy_permanent(state, target)


def vandalblast(
    state: GameState, target: Permanent | None = None, *, overload: bool = False
) -> None:
    if overload:
        for permanent in list(state.battlefield):
            if "Artifact" in permanent.types and not _controlled_by_us(permanent):
                _destroy_permanent(state, permanent)
        return
    if (
        target is None
        or target not in state.battlefield
        or "Artifact" not in target.types
        or _controlled_by_us(target)
    ):
        raise RulesError("Vandalblast targets an artifact you don't control")
    _destroy_permanent(state, target)


def brotherhoods_end(state: GameState, mode: Literal["damage", "artifacts"]) -> None:
    if mode == "damage":
        for permanent in state.battlefield:
            if permanent.types & {"Creature", "Planeswalker"}:
                setattr(permanent, "damage", getattr(permanent, "damage", 0) + 3)
        state.record_event("sweeper_damage", "Brotherhood's End:3")
    elif mode == "artifacts":
        for permanent in list(state.battlefield):
            if "Artifact" in permanent.types and getattr(permanent, "mana_value", 0) <= 3:
                _destroy_permanent(state, permanent)
    else:
        raise RulesError("unsupported Brotherhood's End mode")


def fiery_cannonade(state: GameState) -> None:
    for permanent in state.battlefield:
        if "Creature" in permanent.types and "Pirate" not in permanent.subtypes:
            setattr(permanent, "damage", getattr(permanent, "damage", 0) + 2)
    state.record_event("sweeper_damage", "Fiery Cannonade:2")


def prismari_command(
    state: GameState,
    modes: tuple[str, str],
    *,
    damage_target: Permanent | int | None = None,
    draw_discard: tuple[int, int] | None = None,
    treasure_player: int | None = None,
    artifact_target: Permanent | None = None,
) -> None:
    if len(modes) != 2 or len(set(modes)) != 2:
        raise RulesError("Prismari Command must choose two different modes")
    for mode in modes:
        if mode == "damage":
            if damage_target is None:
                raise RulesError("Prismari damage mode requires any target")
            if isinstance(damage_target, Permanent):
                if damage_target not in state.battlefield:
                    raise RulesError("Prismari damage permanent target must be on battlefield")
                setattr(damage_target, "damage", getattr(damage_target, "damage", 0) + 2)
            else:
                state.opponent_life[damage_target] -= 2
            state.record_event("damage", "Prismari Command:2")
        elif mode == "draw_discard":
            state.draw(2)
            state.record_event("discard", "2")
        elif mode == "treasure":
            if treasure_player not in {0, None}:
                state.record_event("opponent_create_treasure", str(treasure_player))
            else:
                create_treasure(state, 1)
        elif mode == "destroy_artifact":
            if artifact_target is None or "Artifact" not in artifact_target.types:
                raise RulesError("Prismari destroy mode targets an artifact")
            _destroy_permanent(state, artifact_target)
        else:
            raise RulesError("unsupported Prismari Command mode")


def lazotep_plating(state: GameState) -> Permanent:
    army = next((p for p in state.battlefield if "Army" in p.subtypes), None)
    if army is None:
        army = _create_token(state, "Zombie Army", {"Creature"}, {"Zombie", "Army"}, 0, 0)
    army.power = (army.power or 0) + 1
    army.toughness = (army.toughness or 0) + 1
    setattr(state, "self_hexproof_until_eot", True)
    for permanent in state.battlefield:
        if _controlled_by_us(permanent):
            setattr(permanent, "hexproof_until_eot", True)
    state.record_event("hexproof_until_eot", "self_and_permanents")
    return army


def sentinel_totem_etb(state: GameState, *, bottom: bool = False) -> None:
    state.record_event("scry", "1_bottom" if bottom else "1_top")


def sentinel_totem_exile_all_graveyards(state: GameState, source: Permanent) -> None:
    if source not in state.battlefield or source.tapped or source.name != "Sentinel Totem":
        raise RulesError("Sentinel Totem ability requires untapped source on battlefield")
    state.battlefield.remove(source)
    state.exile.append(source.name)
    state.exile.extend(state.graveyard)
    state.graveyard.clear()
    state.record_event("exile_all_graveyards", "Sentinel Totem")


def soul_guide_lantern_etb(state: GameState, card_name: str) -> None:
    if card_name not in state.graveyard:
        raise RulesError("Soul-Guide Lantern ETB targets a card in a graveyard")
    state.graveyard.remove(card_name)
    state.exile.append(card_name)
    state.record_event("exile_graveyard_card", card_name)


def soul_guide_lantern_exile_opponents(state: GameState, source: Permanent) -> None:
    if source not in state.battlefield or source.tapped or source.name != "Soul-Guide Lantern":
        raise RulesError("Soul-Guide Lantern ability requires untapped source on battlefield")
    state.battlefield.remove(source)
    state.graveyard.append(source.name)
    state.record_event("exile_opponents_graveyards", "Soul-Guide Lantern")


def soul_guide_lantern_draw(state: GameState, source: Permanent) -> None:
    state.pay_mana({"generic": 1})
    if source not in state.battlefield or source.tapped or source.name != "Soul-Guide Lantern":
        raise RulesError("Soul-Guide Lantern draw ability requires untapped source on battlefield")
    source.tapped = True
    state.battlefield.remove(source)
    state.graveyard.append(source.name)
    state.draw(1)


def siren_stormtamer_counter(state: GameState, source: Permanent, target: StackObject) -> None:
    if source not in state.battlefield or source.name != "Siren Stormtamer":
        raise RulesError("Siren Stormtamer ability requires source on battlefield")
    if not (
        getattr(target, "targets_player", False)
        or any(_controlled_by_us(t) and "Creature" in t.types for t in target.targets)
    ):
        raise RulesError(
            "Siren Stormtamer targets only spells or abilities targeting you or your creature"
        )
    state.battlefield.remove(source)
    state.graveyard.append(source.name)
    counter_spell(state, target)
