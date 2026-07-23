"""Minimal deck-scoped rules engine for Malcolm/Breeches competency tests.

This is intentionally not a general Magic engine. It models only the zones,
legality checks, stack ordering, and card behaviors needed by the repository's
rules-competency gate. Unsupported placeholders fail closed when executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Callable, Literal, TypeAlias


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
    if not state.resolving:
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
    "Vedalken Aethermage": {"Creature"},
    "Step Through": {"Sorcery"},
    "Long-Term Plans": {"Instant"},
    "Rebuild": {"Instant"},
    "Muddle the Mixture": {"Instant"},
    "Dizzy Spell": {"Instant"},
    "Drift of Phantasms": {"Creature"},
    "Commit // Memory": {"Instant", "Sorcery"},
    "Invert // Invent": {"Instant"},
}
CARD_SUBTYPES = {
    "Dualcaster Mage": {"Human", "Wizard"},
    "Niv-Mizzet, the Firemind": {"Dragon", "Wizard"},
    "Vedalken Aethermage": {"Vedalken", "Wizard"},
    "Siren Stormtamer": {"Siren", "Pirate", "Wizard"},
    "Spectral Sailor": {"Spirit", "Pirate"},
}
MANA_VALUES = {"Twinflame": 2, "Electroduplicate": 3, "Curiosity": 1, "Niv-Mizzet, the Firemind": 6}
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


LAND_MANA = {"Island": "U", "Mountain": "R", "Command Tower": "U", "Shivan Reef": "U"}
TAPPED_LANDS = {"Izzet Boilerworks"}


def play_land(state: GameState, name: str) -> Permanent:
    if state.land_played:
        raise RulesError("only one land play per turn")
    land = Permanent(name, {"Land"}, tapped=name in TAPPED_LANDS)
    state.battlefield.append(land)
    state.land_played = True
    return land


def tap_for_mana(state: GameState, permanent: Permanent, color: str | None = None) -> None:
    ensure_not_terminal(state)
    if permanent.tapped:
        raise RulesError("permanent is already tapped")
    if color is not None and color not in MANA_TYPES:
        raise RulesError("illegal mana choice")
    produced = color or permanent.mana_abilities.get("tap") or LAND_MANA.get(permanent.name)
    if produced is None:
        raise RulesError(f"no mana behavior for {permanent.name}")
    permanent.tapped = True
    state.mana_pool[produced] += 1


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


def declare_attackers(state: GameState, attackers: list[Permanent]) -> None:
    ensure_not_terminal(state)
    if state.phase is not Phase.COMBAT:
        raise RulesError("attackers are declared only during combat")
    for attacker in attackers:
        if attacker not in state.battlefield or "Creature" not in attacker.types:
            raise RulesError("only battlefield creatures can attack")
        if attacker.tapped:
            raise RulesError("tapped creatures cannot attack")
        if attacker.summoning_sick and not attacker.haste:
            raise RulesError("creature cannot attack due to summoning sickness")
    for attacker in attackers:
        attacker.attacking = True
        attacker.tapped = True
    state.record_event("declare_attackers", ",".join(p.name for p in attackers))
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


def validate_action(state: GameState, action: Action) -> ValidationResult:
    errors: list[str] = []
    refs: list[str] = ["CR 117.5"]
    if action.action_type in {ActionType.CAST_SPELL, ActionType.ACTIVATE_ABILITY}:
        errors.extend(validate_timing(state, action.timing))
        refs.extend(TIMING_RULES_REFS)
    if action.action_type is ActionType.CAST_SPELL:
        if action.source_name not in state.hand:
            errors.append(f"{action.source_name} is not in hand")
        if action.source_name in {"Twinflame", "Electroduplicate"} and not _is_creature_target(
            state, list(action.targets)
        ):
            errors.append(f"{action.source_name} requires one legal creature target")
            refs.extend(TARGET_RULES_REFS)
    elif action.action_type is ActionType.ACTIVATE_ABILITY:
        if action.source_name == "Glint-Horn Buccaneer":
            source = next((p for p in state.battlefield if p.name == "Glint-Horn Buccaneer"), None)
            if source is None or not source.attacking:
                errors.append("Glint-Horn Buccaneer can activate only while attacking")
            if not state.hand:
                errors.append("Glint-Horn activation requires a discarded card")
        else:
            errors.append(f"unsupported activated ability: {action.source_name}")
    elif action.action_type is ActionType.PLAY_LAND:
        if action.source_name not in state.hand:
            errors.append(f"{action.source_name} is not in hand")
        if action.source_name not in LAND_MANA and action.source_name not in TAPPED_LANDS:
            errors.append(f"unsupported land play: {action.source_name}")
        if state.land_played:
            errors.append("only one land play per turn")
    elif action.action_type is ActionType.ACTIVATE_MANA_ABILITY:
        source = next((p for p in state.battlefield if p.name == action.source_name), None)
        if source is None:
            errors.append(f"{action.source_name} is not on battlefield")
        elif source.tapped:
            errors.append("permanent is already tapped")
        elif source.name not in LAND_MANA and not source.mana_abilities:
            errors.append(f"no mana behavior for {source.name}")
    elif action.action_type is not ActionType.PASS_PRIORITY:
        errors.append(f"unsupported action type: {action.action_type}")
    return ValidationResult(
        not errors, tuple(errors), tuple(dict.fromkeys(refs)), action if not errors else None
    )


def generate_legal_actions(state: GameState) -> list[Action]:
    if state.terminal:
        return []
    actions = [Action(ActionType.PASS_PRIORITY)]
    for card in state.hand:
        if card in {"Twinflame", "Electroduplicate"}:
            for permanent in state.battlefield:
                candidate = Action(ActionType.CAST_SPELL, card, (permanent,), timing="sorcery")
                if validate_action(state, candidate).accepted:
                    actions.append(candidate)
    if any(p.name == "Glint-Horn Buccaneer" for p in state.battlefield):
        candidate = Action(ActionType.ACTIVATE_ABILITY, "Glint-Horn Buccaneer")
        if validate_action(state, candidate).accepted:
            actions.append(candidate)
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
        state.hand.remove(action.source_name)
        state.pay_mana(action.mana_cost or {})
        state.record_event("action", f"cast:{action.source_name}")
        effect = action.effect or (lambda _s: None)
        state.stack.append(
            StackObject(
                action.source_name,
                "spell",
                effect,
                list(action.targets),
                legal_targets=_is_creature_target,
            )
        )
        state.would_receive_priority()
        return
    if action.action_type is ActionType.PLAY_LAND:
        assert action.source_name is not None
        state.hand.remove(action.source_name)
        play_land(state, action.source_name)
        state.record_event("action", f"play_land:{action.source_name}")
        return
    if action.action_type is ActionType.ACTIVATE_MANA_ABILITY:
        source = next(p for p in state.battlefield if p.name == action.source_name)
        tap_for_mana(state, source, action.mana_choice)
        state.record_event("action", f"activate_mana:{action.source_name}")
        return
    if action.action_type is ActionType.ACTIVATE_ABILITY:
        source = next(p for p in state.battlefield if p.name == action.source_name)
        state.record_event("action", f"activate:{action.source_name}")
        activate_glint_horn(state, source)
        state.would_receive_priority()


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
    if source not in state.battlefield or source.tapped or source.name != "Soul-Guide Lantern":
        raise RulesError("Soul-Guide Lantern draw ability requires untapped source on battlefield")
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
