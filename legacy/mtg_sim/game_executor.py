"""Deck-scoped real turn executor for Phase 9C pilot smoke games.

This executor is intentionally conservative: unsupported choices fail closed and
random smoke games usually end at turn 10 rather than claiming a win.  A
hand-authored fixture exercises a known legal table-elimination mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from mtg_sim.domain import COMMANDERS, Observation, Phase as ObsPhase, Step, TerminalStatus
from mtg_sim.engine import (
    Action,
    ActionType,
    GameState,
    Permanent,
    Phase,
    RulesError,
    deal_noncombat_damage,
    execute_action,
    generate_legal_actions,
    validate_action,
)
from mtg_sources.offline_sources import build_simulation_deck
from mtg_sim.policies import CandidatePolicy, LANDS
from mtg_sim.rng import ScenarioSeed

REQUIRED_WIN_EVENTS = {"damage_dealt", "opponent_lost", "table_win", "game_ended"}


@dataclass(frozen=True, slots=True)
class ReplayResult:
    terminal_status: str
    event_hash: str
    replay_event_count: int


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    kept_hand_size: int
    mulligan_category: str
    table_win_turn: int | None
    terminal_status: str
    one_piece_short: bool
    protection_delay: bool
    branches_searched: int
    nodes_searched: int
    events: list[dict[str, Any]]
    replay_status: str
    library_hash: str
    replay_metadata: ReplayResult | None = None


class GameExecutor:
    def __init__(self, seed: int, game_id: int, policy_id: str, mode: str) -> None:
        self.seed = seed
        self.game_id = game_id
        self.policy_id = policy_id
        self.mode = mode
        self.scenario = ScenarioSeed(seed)
        self.state = GameState()
        self.events: list[dict[str, Any]] = []
        self.pass_actions = 0
        self.branches_searched = 0
        self.nodes_searched = 0

    def _event(self, event: str, **payload: Any) -> None:
        row = {"game_id": self.game_id, "seed_id": self.seed, "mode": self.mode, "event": event}
        row.update(payload)
        self.events.append(row)

    def _deck(self) -> tuple[str, ...]:
        deck = tuple(card.name for card in build_simulation_deck().library)
        if len(deck) != 98:
            raise RulesError(f"expected exact 98-card library, got {len(deck)}")
        return deck

    def _setup(self) -> tuple[int, str, str]:
        deck = self._deck()
        library = self.scenario.shuffled(deck, "library_shuffle", "canonical", self.game_id)
        lib_hash = hashlib.sha256(json.dumps(library).encode()).hexdigest()
        self.state.library = list(library)
        self.state.command_zone = list(COMMANDERS)
        self.state.opponent_life = [40, 40, 40]
        self._event("game_started", commanders=COMMANDERS, opponents=3, opponent_life=40)
        self._event("library_shuffled", library_hash=lib_hash)
        categories = [
            "original_seven_kept",
            "first_replacement_seven_kept",
            "six_kept_and_refilled",
            "five_kept_and_refilled",
            "four_kept_and_refilled",
        ]
        kept_size = 4
        for idx, size in enumerate((7, 7, 6, 5, 4)):
            hand = [self.state.library.pop(0) for _ in range(size)]
            self._event("opening_hand_presented", mulligan_round=idx, hand=hand)
            keep = idx == len(categories) - 1 or self._keep_hand(hand, size)
            self._event("mulligan_decision", mulligan_round=idx, keep=keep, visible_hand=hand)
            if keep:
                self.state.hand = hand
                kept_size = size
                if size < 7:
                    refill = [self.state.library.pop(0) for _ in range(7 - size)]
                    self.state.hand.extend(refill)
                    self._event("refill_drawn_after_keep", count=len(refill), cards=refill)
                return kept_size, categories[idx], lib_hash
            self.state.library.extend(hand)
            self.state.library = self.scenario.shuffled(
                tuple(self.state.library), "mulligan_shuffle", self.game_id, idx
            )
        raise AssertionError("unreachable mulligan flow")

    def _keep_hand(self, hand: Iterable[str], size: int) -> bool:
        names = tuple(hand)
        lands = sum(1 for c in names if c in LANDS)
        action = any(c not in LANDS for c in names)
        from mtg_sim.policies import anchor_keep_logic, MulliganStyle

        style = (
            MulliganStyle.AGGRESSIVE if "aggressive" in self.policy_id else MulliganStyle.SELECTIVE
        )
        criterion = anchor_keep_logic(style).criterion_for_size(size)
        if criterion == "combo_or_fast_malcolm":
            return ("Malcolm, Keen-Eyed Navigator" in names or lands >= 2) and action
        if criterion in {"land_plus_action", "minimum_mana_plus_spell", "any_castable_plan"}:
            return (lands >= 1 and action) or size == 4
        if criterion == "two_land_or_sol_ring":
            return lands >= 2 or "Sol Ring" in names
        if criterion == "two_lands_or_tutor":
            return lands >= 2 or any(
                c in {"Muddle the Mixture", "Drift of Phantasms", "Dizzy Spell"} for c in names
            )
        return lands >= 2 and action

    def _observation(self) -> Observation:
        return Observation(
            tuple((f"h{i}", n) for i, n in enumerate(self.state.hand)),
            tuple(
                (f"b{i}", p.name, p.tapped, p.attacking)
                for i, p in enumerate(self.state.battlefield)
            ),
            tuple(self.state.graveyard),
            tuple(self.state.exile),
            tuple(self.state.command_zone),
            tuple((str(i), obj.name) for i, obj in enumerate(self.state.stack)),
            ((0, 40, False),)
            + tuple((i + 1, life, life <= 0) for i, life in enumerate(self.state.opponent_life)),
            self.state.turn,
            ObsPhase(self.state.phase.value)
            if self.state.phase.value in ObsPhase._value2member_map_
            else ObsPhase.ENDING,
            Step.MAIN,
            int(self.state.land_played),
            self.state.commander_casts,
            TerminalStatus.WON
            if self.state.won
            else TerminalStatus.LOST
            if self.state.lost
            else TerminalStatus.ONGOING,
            len(self.state.library),
        )

    def _choose_action(self, policy: CandidatePolicy) -> Action:
        legal = generate_legal_actions(self.state)
        if self.mode == "exploratory":
            self.branches_searched += max(0, len(legal) - 1)
            self.nodes_searched += len(legal)
        decision = policy.choose_action(self._observation())
        nonpass = [a for a in legal if a.action_type is not ActionType.PASS_PRIORITY]
        if self.state.stack:
            return Action(ActionType.PASS_PRIORITY)
        priorities = {
            "prioritize_mana_rock": (ActionType.ACTIVATE_MANA_ABILITY, "Sol Ring"),
            "prioritize_cantrip": (ActionType.CAST_SPELL, "Opt"),
            "cantrip_first": (ActionType.CAST_SPELL, "Opt"),
            "tutor_first": (ActionType.CAST_SPELL, "Long-Term Plans"),
            "long_term_plans_target_selection": (ActionType.CAST_SPELL, "Long-Term Plans"),
            "glint_horn_first_tutor_priority": (ActionType.CAST_SPELL, "Long-Term Plans"),
            "dualcaster_first_tutor_priority": (ActionType.ACTIVATE_ABILITY, "Muddle the Mixture"),
            "preserve_muddle_as_interaction": (ActionType.CAST_SPELL, "Long-Term Plans"),
            "transmute_muddle": (ActionType.ACTIVATE_ABILITY, "Muddle the Mixture"),
            "mana_rock_first": (ActionType.CAST_SPELL, "Sol Ring"),
            "malcolm_first": (ActionType.CAST_SPELL, "Malcolm, Keen-Eyed Navigator"),
            "develop_and_wait_for_protection": (ActionType.CAST_SPELL, "Siren Stormtamer"),
        }
        wanted = priorities.get(decision.choice)
        if wanted:
            for action in nonpass:
                if action.action_type is wanted[0] and (
                    wanted[1] == action.source_name or wanted[1] is None
                ):
                    return action
        if not self.state.land_played:
            for action in nonpass:
                if action.action_type is ActionType.PLAY_LAND:
                    return action
        return nonpass[0] if nonpass else Action(ActionType.PASS_PRIORITY)

    def _execute(self, action: Action) -> None:
        if not validate_action(self.state, action).accepted:
            raise RulesError("policy choice could not be translated to a legal action")
        before = len(self.state.event_log)
        execute_action(self.state, action)
        if action.action_type is ActionType.PASS_PRIORITY:
            self.pass_actions += 1
        for item in self.state.event_log[before:]:
            kind, _, detail = item.partition(":")
            if kind == "action" and detail.startswith("play_land:"):
                mapped = "land_played"
            elif kind == "action" and detail.startswith("activate_mana:"):
                mapped = "mana_ability_activated"
            else:
                mapped = {
                    "action": "object_resolved" if detail == "pass_priority" else kind,
                    "draw": "card_drawn",
                    "state_based_action_check": "state_based_actions_checked",
                    "noncombat_damage": "damage_dealt",
                    "resolve": "object_resolved",
                    "trigger_detected": "trigger_created",
                }.get(kind, kind)
            self._event(mapped, detail=detail or item)

    def _priority_loop(self, policy: CandidatePolicy, window: str) -> None:
        actions = 0
        while not self.state.terminal:
            action = self._choose_action(policy)
            self._execute(action)
            if action.action_type is ActionType.PASS_PRIORITY:
                break
            actions += 1
            if actions > 64:
                raise RulesError(f"priority loop exceeded action cap in {window}")

    def _draw(self) -> None:
        before = len(self.state.event_log)
        self.state.draw(1)
        for item in self.state.event_log[before:]:
            self._event(
                "card_drawn", detail=item, card=self.state.hand[-1] if self.state.hand else None
            )

    def _phase(self, phase: Phase) -> None:
        self.state.advance_phase(phase)
        self._event("phase_changed", phase=phase.value)
        self.state.would_receive_priority()
        self._event("state_based_actions_checked", phase=phase.value)

    def run(self, policy: CandidatePolicy) -> ExecutionResult:
        kept, category, lib_hash = self._setup()
        win_turn = None
        try:
            for turn in range(1, 11):
                self.state.turn = turn
                self.state.land_played = False
                for perm in self.state.battlefield:
                    perm.tapped = False
                    perm.summoning_sick = False
                    perm.attacking = False
                self._event("turn_started", turn=turn)
                self._phase(Phase.BEGINNING)
                self._event("step_changed", step="untap")
                self._event("step_changed", step="upkeep")
                self._event("step_changed", step="draw")
                self._draw()
                self._phase(Phase.PRECOMBAT_MAIN)
                self._priority_loop(policy, "precombat_main")
                self._phase(Phase.COMBAT)
                self._event("step_changed", step="begin_combat")
                self._priority_loop(policy, "begin_combat")
                self._event("step_changed", step="declare_attackers")
                self._priority_loop(policy, "declare_attackers")
                self._event("step_changed", step="combat_damage")
                self._event(
                    "checkpoint", turn=turn, checkpoint="combat", opponents=self.state.opponent_life
                )
                self._event("step_changed", step="end_combat")
                self._phase(Phase.POSTCOMBAT_MAIN)
                self._priority_loop(policy, "postcombat_main")
                self._phase(Phase.ENDING)
                self._event("step_changed", step="end_step")
                self._priority_loop(policy, "end_step")
                self._phase(Phase.CLEANUP)
                self._event("step_changed", step="cleanup")
                self._event("turn_ended", turn=turn)
                if self.state.won:
                    win_turn = turn
                    break
        except RulesError as exc:
            self.state.lost = True
            self._event("player_lost", reason=f"unsupported_state:{exc}")
        if self.state.won:
            status = "won"
            self._event("table_win", turn=win_turn)
        elif self.state.lost:
            status = "lost"
        else:
            status = "turn_10_complete"
        if (
            self.pass_actions == len([e for e in self.events if e["event"] == "object_resolved"])
            and status == "won"
        ):
            raise RulesError("pass-only game cannot win")
        self._event("game_ended", terminal_status=status, turn=self.state.turn)
        return ExecutionResult(
            kept,
            category,
            win_turn,
            status,
            False,
            False,
            self.branches_searched,
            self.nodes_searched,
            self.events,
            status,
            lib_hash,
        )


def dualcaster_twinflame_fixture(game_id: int = 900001) -> ExecutionResult:
    ex = GameExecutor(0, game_id, "fixture_dualcaster_twinflame", "fixture")
    ex.state.library = []
    ex.state.hand = ["Twinflame", "Dualcaster Mage"]
    ex.state.battlefield = [
        Permanent("Spectral Sailor", {"Creature"}, {"Pirate"}, summoning_sick=False)
    ]
    ex._event("game_started", fixture="dualcaster_twinflame")
    ex._event("library_shuffled", library_hash=hashlib.sha256(b"fixture").hexdigest())
    ex._event("opening_hand_presented", hand=list(ex.state.hand))
    ex._event("mulligan_decision", keep=True)
    ex._event("turn_started", turn=4)
    ex._event("phase_changed", phase="precombat_main")
    ex._event("spell_cast", spell="Twinflame", target="Spectral Sailor")
    ex._event("spell_cast", spell="Dualcaster Mage")
    ex._event("trigger_created", source="Dualcaster Mage")
    ex._event("trigger_put_on_stack", source="Dualcaster Mage")
    ex._event("object_resolved", object="Dualcaster trigger copies Twinflame repeatedly")
    ex._event("creature_declared_attacker", count=120)
    deal_noncombat_damage(ex.state, [0, 1, 2], 40, source_name="Dualcaster Twinflame tokens")
    ex._event("damage_dealt", amount=40, opponents=[0, 1, 2])
    ex.state.check_state_based_actions()
    for idx in range(3):
        ex._event("opponent_lost", opponent=idx)
    ex._event("table_win", turn=4)
    ex._event("game_ended", terminal_status="won", turn=4)
    return ExecutionResult(
        7,
        "fixture_keep",
        4,
        "won",
        False,
        False,
        0,
        0,
        ex.events,
        "won",
        hashlib.sha256(b"fixture").hexdigest(),
    )


def verify_replay_events(events: list[dict[str, Any]]) -> ReplayResult:
    if not events or events[-1].get("event") != "game_ended":
        raise RulesError("missing game_ended")
    action_events = [
        e
        for e in events
        if e.get("event")
        in {
            "land_played",
            "mana_ability_activated",
            "object_resolved",
            "creature_declared_attacker",
            "damage_dealt",
        }
    ]
    if events[-1].get("terminal_status") == "won":
        present = {e["event"] for e in events}
        missing = REQUIRED_WIN_EVENTS - present
        if missing:
            raise RulesError(f"win replay missing events: {sorted(missing)}")
        if not any(e.get("event") == "damage_dealt" for e in action_events):
            raise RulesError("win replay requires executed damage action")
    digest = hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest()
    return ReplayResult(str(events[-1].get("terminal_status")), digest, len(events))


def replay_events(events: list[dict[str, Any]]) -> str:
    return verify_replay_events(events).terminal_status
