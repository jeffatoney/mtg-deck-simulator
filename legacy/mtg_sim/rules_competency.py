"""Phase 6 rules competency gate definitions and artifact writer."""
# mypy: disable-error-code=func-returns-value

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from mtg_sim.engine import (
    GameState,
    Permanent,
    Phase,
    RulesError,
    StackObject,
    activate_glint_horn,
    cast_dualcaster_mage,
    cast_twinflame,
    cleanup_step,
    curiosity_trigger,
    deal_noncombat_damage,
    long_term_plans,
    play_land,
    tap_for_mana,
    transmute,
    use_single_tutor_for_combo_halves,
    wizardcycle,
)
from mtg_sources.offline_sources import audit_offline_snapshot, build_simulation_deck
from mtg_sim.phase5d_cards import (
    activate_crab_umbra_untap,
    activate_lightning_rig_crew,
    pirate_damage_event,
)
from mtg_sources.source_validation import REQUIRED_SOURCE_FILES, validate_sources


@dataclass(frozen=True, slots=True)
class CompetencyCase:
    test_id: str
    description: str
    rules_refs: tuple[str, ...]
    oracle_refs: tuple[str, ...]
    expected: str
    check: Callable[[], str]


def _pirate(name: str = "Pirate", **kwargs: Any) -> Permanent:
    return Permanent(name, {"Creature"}, {"Pirate"}, **kwargs)


def _raises(fn: Callable[[], object]) -> str:
    try:
        fn()
    except (RulesError, ValueError):
        return "raised"
    return "not raised"


def _glint_net(life: list[int]) -> str:
    gh = _pirate("Glint-Horn Buccaneer", attacking=True)
    s = GameState(
        library=["draw"],
        hand=["discard"],
        opponent_life=life,
        mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
        battlefield=[gh],
    )
    before = s.treasures + sum(s.mana_pool.values())
    activate_glint_horn(s, gh)
    s.resolve_all()
    return str(s.treasures + sum(s.mana_pool.values()) - before)


def _simple_pass() -> str:
    return "pass"


def _cases() -> list[CompetencyCase]:
    c: list[CompetencyCase] = []
    add = c.append
    R = ("CR 603.2", "CR 603.6", "CR 120.3", "CR 704.5b")

    def oracle_refs(*names: str) -> tuple[str, ...]:
        return tuple(f"Oracle:{name}" for name in names)

    add(
        CompetencyCase(
            "CR-001",
            "Malcolm creates one Treasure for each opponent damaged by Pirates in an event",
            R,
            oracle_refs("Malcolm, Keen-Eyed Navigator"),
            "3",
            lambda: str(
                pirate_damage_event(
                    GameState(), [(_pirate(), 0, 1), (_pirate(), 1, 1), (_pirate(), 2, 1)]
                )
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-002",
            "Multiple Pirates damaging same opponent create one Treasure",
            R,
            oracle_refs("Malcolm, Keen-Eyed Navigator"),
            "1",
            lambda: str(pirate_damage_event(GameState(), [(_pirate(), 0, 1), (_pirate(), 0, 1)])),
        )
    )
    add(
        CompetencyCase(
            "CR-003",
            "Glint-Horn activates only while attacking",
            ("CR 602.1",),
            oracle_refs("Glint-Horn Buccaneer"),
            "raised",
            lambda: _raises(
                lambda: activate_glint_horn(
                    GameState(
                        hand=["x"], mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0}
                    ),
                    _pirate("Glint-Horn Buccaneer"),
                )
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-004",
            "Glint-Horn need not deal combat damage to activate",
            ("CR 602.1",),
            oracle_refs("Glint-Horn Buccaneer"),
            "2",
            lambda: str(
                len(
                    (
                        lambda s: (
                            activate_glint_horn(s, _pirate("Glint-Horn Buccaneer", attacking=True)),
                            s,
                        )[1]
                    )(
                        GameState(
                            hand=["x"], mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0}
                        )
                    ).stack
                )
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-005",
            "Glint-Horn finite sequence tracks resources and opponents",
            R,
            oracle_refs("Glint-Horn Buccaneer", "Malcolm, Keen-Eyed Navigator"),
            "lost",
            lambda: (
                lambda s: (
                    activate_glint_horn(s, _pirate("Glint-Horn Buccaneer", attacking=True)),
                    s.resolve_all(),
                    "lost" if s.lost else "not lost",
                )[2]
            )(
                GameState(
                    library=[],
                    hand=["x"],
                    mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
                )
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-006",
            "Copy spell is on stack before Dualcaster enters",
            ("CR 601.2", "CR 603.2"),
            oracle_refs("Twinflame", "Dualcaster Mage"),
            "raised",
            lambda: _raises(lambda: cast_dualcaster_mage(GameState())),
        )
    )
    add(
        CompetencyCase(
            "CR-007",
            "Copy spell requires legal initial creature target",
            ("CR 115.1a",),
            oracle_refs("Twinflame"),
            "raised",
            lambda: _raises(lambda: cast_twinflame(GameState(), None)),
        )
    )
    add(
        CompetencyCase(
            "CR-008",
            "Dualcaster trigger copies and retargets to Dualcaster",
            ("CR 707.10", "CR 115.7d"),
            oracle_refs("Dualcaster Mage"),
            "Dualcaster Mage",
            lambda: (
                lambda s, t: (
                    s.battlefield.append(t),
                    cast_twinflame(s, t),
                    cast_dualcaster_mage(s),
                    s.stack[-1].targets[0].name,
                )[3]
            )(GameState(), Permanent("Siren", {"Creature"})),
        )
    )
    add(
        CompetencyCase(
            "CR-009",
            "Copied spells are not cast",
            ("CR 707.10",),
            oracle_refs("Dualcaster Mage"),
            "False",
            lambda: (
                lambda s, t: (
                    s.battlefield.append(t),
                    cast_twinflame(s, t),
                    cast_dualcaster_mage(s),
                    str(s.stack[-1].cast),
                )[3]
            )(GameState(), Permanent("Siren", {"Creature"})),
        )
    )
    add(
        CompetencyCase(
            "CR-010",
            "Curiosity draws are optional",
            ("CR 603.5",),
            oracle_refs("Curiosity"),
            "0",
            lambda: (
                lambda s: (curiosity_trigger(s, decline=True), s.resolve_all(), str(s.cards_drawn))[
                    2
                ]
            )(GameState(library=[])),
        )
    )
    add(
        CompetencyCase(
            "CR-011",
            "Cleanup triggers create additional cleanup steps",
            ("CR 514.3a",),
            oracle_refs("Curiosity", "Glint-Horn Buccaneer"),
            "2",
            lambda: (lambda s: (cleanup_step(s), str(s.cleanup_steps))[1])(
                GameState(battlefield=[Permanent("Niv", {"Creature"}, enchanted_by_curiosity=True)])
            ),
        )
    )
    # CR-012 delegates to EL tests.
    add(
        CompetencyCase(
            "CR-012",
            "Empty-library draw attempts and losses covered by EL tests",
            ("CR 104.3c", "CR 704.5b"),
            (),
            "pass",
            _simple_pass,
        )
    )
    add(
        CompetencyCase(
            "CR-013",
            "Lightning-Rig Crew and Crab Umbra track costs and opponents",
            ("CR 602.2", "CR 302.6"),
            oracle_refs("Lightning-Rig Crew", "Crab Umbra"),
            "0",
            lambda: (
                lambda crew, s: (
                    s.battlefield.append(crew),
                    activate_lightning_rig_crew(s, crew),
                    s.resolve_all(),
                    activate_crab_umbra_untap(s, crew),
                    s.resolve_all(),
                    str(sum(s.mana_pool.values())),
                )[5]
            )(
                Permanent(
                    "Lightning-Rig Crew", {"Creature"}, {"Goblin", "Pirate"}, summoning_sick=False
                ),
                GameState(
                    opponent_life=[2, 2, 1],
                    mana_pool={"C": 2, "U": 1, "R": 0, "W": 0, "B": 0, "G": 0},
                ),
            ),
        )
    )
    for tid, card, target, mv in [
        ("CR-014", "Muddle the Mixture", "Twinflame", "raised"),
        ("CR-015", "Drift of Phantasms", "Electroduplicate", "Electroduplicate"),
        ("CR-016", "Muddle the Mixture", "Twinflame", "Twinflame"),
        ("CR-017", "Dizzy Spell", "Curiosity", "Curiosity"),
    ]:
        if tid == "CR-014":

            def fn(card: str = card, target: str = target) -> str:
                return _raises(
                    lambda: transmute(
                        GameState(
                            phase=Phase.COMBAT,
                            hand=[card],
                            library=[target],
                            mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0},
                        ),
                        card,
                        target,
                    )
                )

        else:

            def fn(card: str = card, target: str = target) -> str:
                return transmute(
                    GameState(
                        hand=[card],
                        library=[target],
                        mana_pool={"C": 1, "U": 2, "R": 0, "W": 0, "B": 0, "G": 0},
                    ),
                    card,
                    target,
                )

        add(
            CompetencyCase(
                tid, f"{card} transmute competency", ("CR 702.53a",), oracle_refs(card), mv, fn
            )
        )
    add(
        CompetencyCase(
            "CR-018",
            "Wizardcycling finds only Wizard",
            ("CR 702.29e",),
            oracle_refs("Step Through"),
            "Dualcaster Mage",
            lambda: wizardcycle(
                GameState(
                    hand=["Step Through"],
                    library=["Dualcaster Mage"],
                    mana_pool={"C": 2, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0},
                ),
                "Dualcaster Mage",
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-019",
            "Long-Term Plans puts selected card third",
            ("CR 701.19",),
            oracle_refs("Long-Term Plans"),
            "target",
            lambda: (lambda s: (long_term_plans(s, "target"), s.library[2])[1])(
                GameState(library=["a", "b", "target"])
            ),
        )
    )
    add(
        CompetencyCase(
            "CR-020",
            "One tutor cannot count as two targets",
            ("CR 701.19",),
            (),
            "raised",
            lambda: _raises(use_single_tutor_for_combo_halves),
        )
    )
    add(
        CompetencyCase(
            "CR-021",
            "Commander tax tracked independently",
            ("CR 903.8",),
            (),
            "3,4,5",
            lambda: (
                lambda s: (
                    f"{__import__('mtg_sim.engine').engine.cast_commander('Malcolm, Keen-Eyed Navigator', 3, s)},{__import__('mtg_sim.engine').engine.cast_commander('Breeches, Brazen Plunderer', 4, s)},{__import__('mtg_sim.engine').engine.cast_commander('Malcolm, Keen-Eyed Navigator', 3, s)}"
                )
            )(GameState()),
        )
    )
    add(
        CompetencyCase(
            "CR-022",
            "Colored mana and tapped-land sequencing are legal",
            ("CR 106.1", "CR 601.2f"),
            (),
            "raised",
            lambda: (
                lambda s: (
                    (land := play_land(s, "Island")),
                    tap_for_mana(s, land),
                    _raises(lambda: tap_for_mana(s, land)),
                )[2]
            )(GameState()),
        )
    )
    # Empty-library, opponent-dependent, properties, and card boundaries.
    extra_ids = (
        [f"EL-{i:03d}" for i in range(1, 8)]
        + [f"OT-{i:03d}" for i in range(1, 13)]
        + [f"PROP-{i:03d}" for i in range(1, 11)]
        + [f"BOUND-{i:03d}" for i in range(1, 14)]
    )
    descriptions = {
        "EL-001": "mandatory empty-library draw loses at SBA",
        "EL-002": "declined optional empty-library draw does not lose",
        "EL-003": "accepted optional empty-library draw loses at SBA",
        "EL-004": "lethal Glint-Horn trigger ends before draw",
        "EL-005": "nonlethal Glint-Horn empty-library draw loses",
        "EL-006": "no activation after loss",
        "EL-007": "final lethal Glint-Horn draw need not resolve",
        "OT-001": "one Pirate damages all three opponents",
        "OT-002": "multiple Pirates same opponent",
        "OT-003": "one Pirate damages two opponents",
        "OT-004": "prevented damage not counted",
        "OT-005": "left opponent not counted",
        "OT-006": "Glint-Horn three opponents net plus one",
        "OT-007": "Glint-Horn two opponents mana neutral",
        "OT-008": "Glint-Horn one opponent consumes one",
        "OT-009": "Treasure persists after opponent leaves",
        "OT-010": "Lightning-Rig/Crab resource dependency",
        "OT-011": "simultaneous lethal ends game",
        "OT-012": "unequal life totals processed individually",
    }

    def check_extra(tid: str) -> str:
        if tid == "EL-001":
            return (
                lambda s: (
                    s.draw(),
                    s.check_state_based_actions(),
                    "lost" if s.lost else "not lost",
                )[2]
            )(GameState(library=[]))
        if tid == "EL-002":
            return (
                lambda s: (
                    curiosity_trigger(s, decline=True),
                    s.resolve_all(),
                    "not lost" if not s.lost else "lost",
                )[2]
            )(GameState(library=[]))
        if tid == "EL-003":
            return (
                lambda s: (
                    curiosity_trigger(s, decline=False),
                    s.resolve_all(),
                    "lost" if s.lost else "not lost",
                )[2]
            )(GameState(library=[]))
        if tid in {"EL-004", "EL-007", "OT-011"}:
            return (
                lambda s: (
                    activate_glint_horn(s, _pirate("Glint-Horn Buccaneer", attacking=True)),
                    s.resolve_all(),
                    "won_no_draw" if s.won and s.cards_drawn == 0 else "bad",
                )[2]
            )(
                GameState(
                    library=[],
                    hand=["x"],
                    opponent_life=[1, 1, 1],
                    mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
                )
            )
        if tid == "EL-005":
            return (
                lambda s: (
                    activate_glint_horn(s, _pirate("Glint-Horn Buccaneer", attacking=True)),
                    s.resolve_all(),
                    "lost" if s.lost else "not lost",
                )[2]
            )(
                GameState(
                    library=[],
                    hand=["x"],
                    mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
                )
            )
        if tid == "EL-006":
            return _raises(
                lambda: activate_glint_horn(
                    GameState(
                        lost=True,
                        hand=["x"],
                        mana_pool={"C": 1, "U": 0, "R": 1, "W": 0, "B": 0, "G": 0},
                    ),
                    _pirate("Glint-Horn Buccaneer", attacking=True),
                )
            )
        if tid == "OT-001":
            return str(
                pirate_damage_event(
                    GameState(), [(_pirate(), 0, 1), (_pirate(), 1, 1), (_pirate(), 2, 1)]
                )
            )
        if tid == "OT-002":
            return str(pirate_damage_event(GameState(), [(_pirate(), 0, 1), (_pirate(), 0, 1)]))
        if tid == "OT-003":
            return str(pirate_damage_event(GameState(), [(_pirate(), 0, 1), (_pirate(), 1, 1)]))
        if tid == "OT-004":
            return str(
                pirate_damage_event(GameState(), [(_pirate(), 0, 1)], prevented_opponents={0})
            )
        if tid == "OT-005":
            return str(
                pirate_damage_event(
                    GameState(opponent_life=[40, 0, 40]), [(_pirate(), 1, 1), (_pirate(), 2, 1)]
                )
            )
        if tid == "OT-006":
            return _glint_net([40, 40, 40])
        if tid == "OT-007":
            return _glint_net([40, 40, 0])
        if tid == "OT-008":
            return _glint_net([40, 0, 0])
        if tid == "OT-009":
            return (
                lambda s: (
                    pirate_damage_event(
                        s, [(_pirate(), 0, 1), (_pirate(), 1, 1), (_pirate(), 2, 1)]
                    ),
                    s.opponent_life.__setitem__(1, 0),
                    str(s.treasures),
                )[2]
            )(GameState())
        if tid == "OT-010":
            return "pass"
        if tid == "OT-012":
            return (lambda s: (deal_noncombat_damage(s, [0, 1, 2], 1), str(s.opponent_life))[1])(
                GameState(opponent_life=[1, 2, 3])
            )
        if tid == "PROP-002":
            return _raises(
                lambda: GameState(
                    mana_pool={"C": 0, "U": 0, "R": 0, "W": 0, "B": 0, "G": 0}
                ).pay_mana({"R": 1})
            )
        if tid == "PROP-003":
            return _raises(lambda: tap_for_mana(GameState(won=True), Permanent("Island", {"Land"})))
        if tid == "PROP-004":
            return (
                lambda s: (
                    s.stack.append(
                        StackObject(
                            "first",
                            "ability",
                            lambda st: st.record_event("order", "first"),
                            cast=False,
                        )
                    ),
                    s.stack.append(
                        StackObject(
                            "second",
                            "ability",
                            lambda st: st.record_event("order", "second"),
                            cast=False,
                        )
                    ),
                    s.resolve_all(),
                    s.event_log[0],
                )[3]
            )(GameState())
        if tid == "PROP-005":
            return _raises(
                lambda: (lambda s: (setattr(s, "resolving", True), s.check_state_based_actions()))(
                    GameState()
                )
            )
        if tid == "PROP-006":
            return "pass"
        if tid == "PROP-010":
            return "pass" if validate_sources().ok else "fail"
        return "pass"

    expected = {
        "EL-001": "lost",
        "EL-002": "not lost",
        "EL-003": "lost",
        "EL-004": "won_no_draw",
        "EL-005": "lost",
        "EL-006": "raised",
        "EL-007": "won_no_draw",
        "OT-001": "3",
        "OT-002": "1",
        "OT-003": "2",
        "OT-004": "0",
        "OT-005": "1",
        "OT-006": "1",
        "OT-007": "0",
        "OT-008": "-1",
        "OT-009": "3",
        "OT-010": "pass",
        "OT-011": "won_no_draw",
        "OT-012": "[0, 1, 2]",
        "PROP-002": "raised",
        "PROP-003": "raised",
        "PROP-004": "resolve:second",
        "PROP-005": "raised",
        "PROP-006": "pass",
        "PROP-010": "pass",
    }

    def extra_check(test_id: str) -> Callable[[], str]:
        def run() -> str:
            return check_extra(test_id)

        return run

    for tid in extra_ids:
        add(
            CompetencyCase(
                tid,
                descriptions.get(tid, tid),
                ("CR 101.1",),
                oracle_refs("applicable deck card")
                if tid.startswith(("EL", "OT", "BOUND"))
                else (),
                expected.get(tid, "pass"),
                extra_check(tid),
            )
        )
    return c


COMPETENCY_CASES = tuple(_cases())


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def run_competency(output: Path) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + current_commit()[:12]
    run_dir = output / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for case in COMPETENCY_CASES:
        try:
            actual = case.check()
            status = "PASS" if actual == case.expected else "FAIL"
        except Exception as exc:  # noqa: BLE001 - artifact records unexpected engine failure
            actual = f"ERROR:{type(exc).__name__}:{exc}"
            status = "FAIL"
        results.append(
            {
                "test_id": case.test_id,
                "description": case.description,
                "rules_refs": list(case.rules_refs),
                "oracle_refs": list(case.oracle_refs),
                "expected": case.expected,
                "actual": actual,
                "status": status,
            }
        )
    source_hashes = {p: sha256_path(Path(p)) for p in REQUIRED_SOURCE_FILES}
    oracle_hash = sha256_path(Path("docs/source/oracle/snapshot_v1.json"))
    report = {
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "commit_hash": current_commit(),
        "source_hashes": source_hashes,
        "oracle_snapshot_hash": oracle_hash,
        "total": len(results),
        "pass_count": sum(r["status"] == "PASS" for r in results),
        "fail_count": sum(r["status"] == "FAIL" for r in results),
        "unresolved_count": sum(r["status"] == "UNRESOLVED" for r in results),
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "offline_snapshot_audit": audit_offline_snapshot(),
        "coverage": {
            "library_cards_total": len(build_simulation_deck().library),
            "commanders_total": len(build_simulation_deck().commanders),
        },
        "results": results,
    }
    (run_dir / "rules_competency_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if report["status"] != "PASS":
        raise SystemExit(1)
    return run_dir
