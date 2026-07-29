"""Phase 5D commander and combo behavior layered onto the shared rules engine.

This module keeps Phase 5D changes separate from the Phase 5C engine additions so
both phases can be composed without replacing or discarding earlier behavior.
"""

from __future__ import annotations

from . import engine as _engine
from .engine import GameState, Permanent, RulesError, StackObject

ASSIGNED_CARDS = frozenset(
    {
        "Malcolm, Keen-Eyed Navigator",
        "Breeches, Brazen Plunderer",
        "Glint-Horn Buccaneer",
        "Dualcaster Mage",
        "Twinflame",
        "Electroduplicate",
        "Curiosity",
        "Niv-Mizzet, the Firemind",
        "Lightning-Rig Crew",
        "Crab Umbra",
        "Psychosis Crawler",
    }
)


def create_malcolm_treasures_for_pirate_damage(
    state: GameState,
    damaged_by_pirate: dict[int, int],
    prevented: set[int] | None = None,
    eligible_opponents: set[int] | None = None,
) -> int:
    """Create one Treasure per unique eligible opponent actually damaged."""
    prevented = prevented or set()
    eligible = (
        eligible_opponents if eligible_opponents is not None else set(state.active_opponents())
    )
    count = sum(1 for idx in eligible if damaged_by_pirate.get(idx, 0) > 0 and idx not in prevented)
    _engine.create_treasure(state, count)
    state.record_event("malcolm_treasures", str(count))
    return count


def record_breeches_triggers_for_pirate_damage(
    state: GameState,
    damaged_opponents: set[int],
    eligible_opponents: set[int] | None = None,
) -> int:
    """Record Breeches triggers without inventing unknown opponent cards."""
    eligible = (
        eligible_opponents if eligible_opponents is not None else set(state.active_opponents())
    )
    count = len([idx for idx in damaged_opponents if idx in eligible])
    if count:
        state.record_event(
            "breeches_trigger",
            f"unknown_opponent_cards_exiled:{count}:not_deterministic",
        )
    return count


def _queue_curiosity_trigger(state: GameState) -> None:
    """Queue Curiosity safely when damage is dealt during resolution."""
    if state.resolving:
        state.pending_triggers.append(
            StackObject(
                "Curiosity optional draw",
                "trigger",
                lambda current: current.draw(1, optional=True, decline=False),
                cast=False,
            )
        )
        state.record_event("trigger_detected", "Curiosity optional draw")
    else:
        _engine.curiosity_trigger(state, decline=False)


def pirate_damage_event(
    state: GameState,
    assignments: list[tuple[Permanent, int, int]],
    *,
    prevented_opponents: set[int] | None = None,
) -> int:
    """Resolve one simultaneous Pirate damage event and recalculate per event."""
    _engine.ensure_not_terminal(state)
    prevented_opponents = prevented_opponents or set()
    eligible_opponents = set(state.active_opponents())
    damaged_by_pirate: dict[int, int] = {}
    actually_damaged: set[int] = set()

    for source, opponent, amount in assignments:
        if opponent not in eligible_opponents or amount <= 0:
            continue
        if (
            "Pirate" not in source.subtypes
            or source.damage_prevented
            or opponent in prevented_opponents
        ):
            continue
        state.opponent_life[opponent] -= amount
        damaged_by_pirate[opponent] = damaged_by_pirate.get(opponent, 0) + 1
        actually_damaged.add(opponent)
        if source.enchanted_by_curiosity:
            _queue_curiosity_trigger(state)

    treasures = create_malcolm_treasures_for_pirate_damage(
        state,
        damaged_by_pirate,
        prevented_opponents,
        eligible_opponents,
    )
    record_breeches_triggers_for_pirate_damage(
        state,
        actually_damaged,
        eligible_opponents,
    )
    if not state.resolving:
        state.would_receive_priority()
    return treasures


def deal_noncombat_damage(
    state: GameState,
    opponents: list[int],
    amount: int,
    *,
    source_name: str = "source",
) -> None:
    """Deal noncombat damage and process Curiosity/Malcolm/Breeches hooks."""
    source = next((p for p in state.battlefield if p.name == source_name), None)
    eligible_opponents = set(state.active_opponents())
    actually_damaged: set[int] = set()

    for opponent in opponents:
        if opponent not in eligible_opponents or amount <= 0:
            continue
        state.opponent_life[opponent] -= amount
        actually_damaged.add(opponent)
        if source is not None and source.enchanted_by_curiosity:
            _queue_curiosity_trigger(state)

    state.record_event("noncombat_damage", f"{source_name}:{amount}")
    if source is not None and "Pirate" in source.subtypes:
        create_malcolm_treasures_for_pirate_damage(
            state,
            {opponent: 1 for opponent in actually_damaged},
            set(),
            eligible_opponents,
        )
        record_breeches_triggers_for_pirate_damage(
            state,
            actually_damaged,
            eligible_opponents,
        )
    if not state.resolving:
        state.would_receive_priority()


def activate_niv_mizzet_draw(state: GameState, niv: Permanent) -> None:
    """Activate Niv-Mizzet's tap-to-draw ability with tap restrictions."""
    _engine.ensure_not_terminal(state)
    if niv not in state.battlefield or niv.name != "Niv-Mizzet, the Firemind":
        raise RulesError("Niv-Mizzet activated ability requires Niv-Mizzet on battlefield")
    if niv.tapped:
        raise RulesError("Niv-Mizzet is already tapped")
    if niv.summoning_sick and not niv.haste:
        raise RulesError("Niv-Mizzet activated ability is restricted by summoning sickness")
    niv.tapped = True
    state.stack.append(
        StackObject(
            "Niv-Mizzet draw ability",
            "ability",
            lambda current: current.draw(1),
            cast=False,
        )
    )
    state.would_receive_priority()


def psychosis_crawler_draw_trigger(state: GameState) -> None:
    """Queue Psychosis Crawler life loss, which is not damage."""

    def effect(current: GameState) -> None:
        for idx in current.active_opponents():
            current.opponent_life[idx] -= 1
        current.record_event("life_loss", "Psychosis Crawler:1")

    state.pending_triggers.append(
        StackObject("Psychosis Crawler life loss", "trigger", effect, cast=False)
    )
    state.record_event("trigger_detected", "Psychosis Crawler life loss")
    state.would_receive_priority()


def activate_lightning_rig_crew(state: GameState, crew: Permanent) -> None:
    """Activate Lightning-Rig Crew while enforcing tap restrictions."""
    _engine.ensure_not_terminal(state)
    if crew not in state.battlefield or crew.name != "Lightning-Rig Crew":
        raise RulesError("Lightning-Rig Crew must be on battlefield")
    if crew.tapped:
        raise RulesError("Lightning-Rig Crew is already tapped")
    if crew.summoning_sick and not crew.haste:
        raise RulesError("Lightning-Rig Crew activated ability is restricted by summoning sickness")
    crew.tapped = True

    def effect(current: GameState) -> None:
        deal_noncombat_damage(
            current,
            list(current.active_opponents()),
            1,
            source_name="Lightning-Rig Crew",
        )

    state.stack.append(
        StackObject(
            "Lightning-Rig Crew damage ability",
            "ability",
            effect,
            cast=False,
        )
    )
    state.would_receive_priority()


def _fund_cost_from_treasures(state: GameState, cost: dict[str, int]) -> None:
    """Sacrifice Treasures only when the current mana pool cannot pay a cost."""
    if _engine.solve_mana_payment(state.mana_pool, cost) is not None:
        return

    red_needed = max(0, cost.get("R", 0) - state.mana_pool.get("R", 0))
    blue_needed = max(0, cost.get("U", 0) - state.mana_pool.get("U", 0))
    for _ in range(red_needed):
        _engine.sacrifice_treasure_for_mana(state, "R")
    for _ in range(blue_needed):
        _engine.sacrifice_treasure_for_mana(state, "U")

    while _engine.solve_mana_payment(state.mana_pool, cost) is None and state.treasures > 0:
        _engine.sacrifice_treasure_for_mana(state, "C")


def activate_crab_umbra_untap(
    state: GameState,
    enchanted_creature: Permanent,
) -> None:
    """Pay {2}{U} and put Crab Umbra's untap ability on the stack."""
    _engine.ensure_not_terminal(state)
    if enchanted_creature not in state.battlefield:
        raise RulesError("Crab Umbra requires enchanted creature on battlefield")
    cost = {"generic": 2, "U": 1}
    _fund_cost_from_treasures(state, cost)
    state.pay_mana(cost)

    def untap(_current: GameState) -> None:
        enchanted_creature.tapped = False

    state.stack.append(
        StackObject(
            "Crab Umbra untap ability",
            "ability",
            untap,
            cast=False,
        )
    )
    state.would_receive_priority()


def run_glint_horn_iterations(
    state: GameState,
    glint_horn: Permanent,
    max_iterations: int,
) -> int:
    """Execute a finite Glint-Horn sequence until a terminal or illegal state."""
    completed = 0
    cost = {"generic": 1, "R": 1}
    for _ in range(max_iterations):
        if state.terminal or not state.hand:
            break
        try:
            _fund_cost_from_treasures(state, cost)
        except RulesError:
            break
        if _engine.solve_mana_payment(state.mana_pool, cost) is None:
            break
        _engine.activate_glint_horn(state, glint_horn)
        state.resolve_all()
        completed += 1
    return completed


def install() -> None:
    """Install Phase 5D functions into the shared engine module."""
    functions = {
        "create_malcolm_treasures_for_pirate_damage": (create_malcolm_treasures_for_pirate_damage),
        "record_breeches_triggers_for_pirate_damage": (record_breeches_triggers_for_pirate_damage),
        "pirate_damage_event": pirate_damage_event,
        "deal_noncombat_damage": deal_noncombat_damage,
        "activate_niv_mizzet_draw": activate_niv_mizzet_draw,
        "psychosis_crawler_draw_trigger": psychosis_crawler_draw_trigger,
        "activate_lightning_rig_crew": activate_lightning_rig_crew,
        "activate_crab_umbra_untap": activate_crab_umbra_untap,
        "run_glint_horn_iterations": run_glint_horn_iterations,
    }
    for name, function in functions.items():
        setattr(_engine, name, function)
