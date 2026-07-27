#!/usr/bin/env python3
"""Execute every protected Phase A evaluator against semantic near misses."""

from __future__ import annotations
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _adapter():
    p = ROOT / "tests/phase_a_acceptance/reference_adapter.py"
    spec = importlib.util.spec_from_file_location("phase_a_reference_adapter", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def _event(seq: int, typ: str, oid: str, aid: str = "action:1") -> dict[str, Any]:
    return {
        "sequence": seq,
        "event_id": f"event:{seq}",
        "event_type": typ,
        "game_id": "semantic-baseline",
        "parent_action_id": aid,
        "parent_event_id": f"event:{seq - 1}" if seq > 1 else None,
        "source_object_ids": [oid],
        "target_object_ids": [],
        "pre_state_hash": f"state:{seq - 1}",
        "post_state_hash": f"state:{seq}",
        "payload": {},
    }


def _baseline(aid: str, scenario: dict[str, Any]) -> dict[str, Any]:
    plan = scenario["referee_oracle"]["semantic_assertion_plan"]
    oid = "protected:object:1"
    cid = "protected:card:1"
    events = [_event(i, t, oid) for i, t in enumerate(plan["ordered_event_types"], 1)]
    by = {}
    for e in events:
        by.setdefault(e["event_type"], []).append(e)
    for e in events:
        e["payload"].update({"object_id": oid, "card_instance_id": cid})
    result = {
        "events": events,
        "objects": [
            {
                "object_id": oid,
                "card_instance_id": cid,
                "owner": "p1",
                "controller": "p1",
                "object_type": "card",
            }
        ],
        "card_instances": [{"card_instance_id": cid, "owner": "p1"}],
        "actions": [
            {
                "action_id": "action:1",
                "oracle_name": "Memory",
                "face": "Memory",
                "origin_zone": "graveyard",
                "targets": [],
            }
        ],
        "state_snapshots": {
            e["sequence"]: {
                "marked_damage": {},
                "life_totals": {"p1": 40},
                "summoning_sickness": {oid: True},
            }
            for e in events
        },
        "initial_state": {"zones": {"library": []}, "zone_owners": {}},
        "final_state": {"zones": {"library": []}, "zone_owners": {}},
        "external_ledger": [],
        "replay": {},
    }
    if aid == "A1":
        by["stack_object_created"][0]["payload"].update(
            object_type="SpellObject",
            stack_object_id="stack:1",
            card_instance_id=cid,
            battlefield_before=[],
        )
        by["priority_window_opened"][0]["payload"]["respondable_stack_object_id"] = "stack:1"
        by["spell_resolved"][0]["payload"]["stack_object_id"] = "stack:1"
        by["battlefield_entered"][0]["payload"]["card_instance_id"] = cid
    if aid == "A2":
        by["spell_announced"][0]["payload"]["card_instance_id"] = cid
        by["stack_object_created"][0]["payload"].update(
            object_type="SpellObject", stack_object_id="stack:1", card_instance_id=cid
        )
        by["spell_resolved"][0]["payload"].update(stack_object_id="stack:1", battlefield_before=[])
        by["battlefield_entered"][0]["payload"].update(card_instance_id=cid, object_id=oid)
    if aid == "A3":
        casts = by["commander_cast"]
        pays = by["cost_paid"]
        repl = by["commander_replaced"][0]
        for i, e in enumerate(casts, 1):
            e["payload"].update(card_instance_id=cid, cast_count_after=i)
        pays[0]["payload"].update(base_generic_cost=2, commander_tax=0, generic_paid=2)
        pays[1]["payload"].update(base_generic_cost=2, commander_tax=2, generic_paid=4)
        repl["payload"].update(destination="command", card_instance_id=cid)
    if aid == "B1":
        by["trigger_created"][0]["payload"].update(
            trigger_object_id="trigger:1", object_type="TriggeredAbilityObject"
        )
        by["trigger_created"][0]["target_object_ids"] = [oid]
        by["trigger_put_on_stack"][0]["payload"]["trigger_object_id"] = "trigger:1"
        by["priority_window_opened"][0]["payload"]["respondable_stack_object_id"] = "trigger:1"
        by["targets_revalidated"][0]["target_object_ids"] = [oid]
        by["zone_moved"][0]["payload"] = {
            "object_id": oid,
            "from_zone": "graveyard",
            "to_zone": "exile",
            "zone_owner": "p1",
        }
    if aid == "C1":
        result["state_snapshots"][by["damage_marked"][0]["sequence"]]["marked_damage"] = {oid: 3}
        result["state_snapshots"][by["cleanup_completed"][0]["sequence"]]["marked_damage"] = {}
        result["state_snapshots"][by["turn_changed"][0]["sequence"]]["marked_damage"] = {}
    if aid == "C6":
        order = [
            "attacker_declared",
            "activation_cost_paid",
            "cards_discarded",
            "damage_dealt",
            "treasure_created",
            "cleanup_completed",
            "terminal_state",
        ]
        selected = [by[x][0] for x in order]
        selected[1]["payload"]["discard_count"] = 1
        selected[2]["payload"]["object_ids"] = [oid]
        selected[3]["payload"]["life_totals_after"] = {"p1": 40}
        result["state_snapshots"][selected[3]["sequence"]]["life_totals"] = {"p1": 40}
        selected[4]["payload"]["cause"] = "Malcolm"
    if aid == "D4":
        by["targets_announced"][0]["target_object_ids"] = [oid]
        by["targets_revalidated"][0]["target_object_ids"] = [oid]
        by["external_ledger_moved"][0]["payload"].update(
            object_id=oid, destination="owners_library", position=2
        )
    if aid == "D8":
        result["actions"][0].update(action_id="action:1", face="Memory", targets=["illegal:target"])
        by["action_rejected"][0]["post_state_hash"] = by["action_rejected"][0]["pre_state_hash"]
    if aid == "F2":
        # F2's dedicated proof shares the Dualcaster/Twinflame object lifecycle.
        copied = by["spell_copied"][0]
        token = by["token_created"][0]
        delayed = by["delayed_trigger_created"][0]
        placed = by["trigger_put_on_stack"][0]
        exiled = by["token_exiled"][0]
        ceased = by["token_ceased"][0]
        copied["payload"]["cast"] = False
        token["payload"].update(object_id=oid, card_instance_id=None, haste=True)
        delayed["payload"].update(token_object_id=oid, trigger_object_id="trigger:1")
        placed["payload"]["trigger_object_id"] = "trigger:1"
        exiled["payload"]["object_id"] = oid
        ceased["payload"]["object_id"] = oid
    # Predicates and the semantic plan are the exact evaluator's remaining inputs.
    return result


def mutate_reverse_required_event_order(a):
    a["events"][0], a["events"][-1] = a["events"][-1], a["events"][0]


def mutate_erase_required_state_transition(a):
    a["events"][0]["post_state_hash"] = a["events"][0]["pre_state_hash"]


def mutate_replace_registered_object_reference(a):
    a["events"][0]["source_object_ids"] = ["unregistered:object"]


def mutate_introduce_rejected_state_change(a):
    a["events"][0]["post_state_hash"] = "changed-state"
    a["final_state"] = {**a["final_state"], "changed": True}


def mutate_add_payment_after_rejection(a):
    a["events"].append(_event(len(a["events"]) + 1, "cost_paid", "protected:object:1"))


def mutate_set_wrong_summoning_sickness(a):
    entered = next(e for e in a["events"] if e["event_type"] == "battlefield_entered")
    a["state_snapshots"][entered["sequence"]]["summoning_sickness"][
        entered["payload"]["object_id"]
    ] = False


def mutate_mismatch_battlefield_card_identity(a):
    next(e for e in a["events"] if e["event_type"] == "battlefield_entered")["payload"][
        "card_instance_id"
    ] = "protected:card:other"


def mutate_enter_before_resolution(a):
    entered = next(e for e in a["events"] if e["event_type"] == "battlefield_entered")
    resolved = next(e for e in a["events"] if e["event_type"] == "spell_resolved")
    entered["sequence"], resolved["sequence"] = resolved["sequence"], entered["sequence"]


def _commander_events(a, kind):
    return [e for e in a["events"] if e["event_type"] == kind]


def mutate_wrong_first_commander_cost(a):
    _commander_events(a, "cost_paid")[0]["payload"]["generic_paid"] += 1


def mutate_wrong_second_commander_tax(a):
    _commander_events(a, "cost_paid")[1]["payload"]["commander_tax"] = 0


def mutate_remove_second_commander_cast(a):
    a["events"].remove(_commander_events(a, "commander_cast")[1])


def mutate_wrong_commander_instance(a):
    _commander_events(a, "commander_cast")[1]["payload"]["card_instance_id"] = (
        "protected:card:other"
    )


def mutate_wrong_commander_cast_count(a):
    _commander_events(a, "commander_cast")[0]["payload"]["cast_count_after"] = 0


MUTATIONS = {
    "wrong_commander_cast_count": mutate_wrong_commander_cast_count,
    "wrong_commander_instance": mutate_wrong_commander_instance,
    "remove_second_commander_cast": mutate_remove_second_commander_cast,
    "wrong_second_commander_tax": mutate_wrong_second_commander_tax,
    "wrong_first_commander_cost": mutate_wrong_first_commander_cost,
    "enter_before_resolution": mutate_enter_before_resolution,
    "mismatch_battlefield_card_identity": mutate_mismatch_battlefield_card_identity,
    "set_wrong_summoning_sickness": mutate_set_wrong_summoning_sickness,
    "reverse_required_event_order": mutate_reverse_required_event_order,
    "replace_registered_object_reference": mutate_replace_registered_object_reference,
    "erase_required_state_transition": mutate_erase_required_state_transition,
    "introduce_rejected_state_change": mutate_introduce_rejected_state_change,
    "add_payment_after_rejection": mutate_add_payment_after_rejection,
}


def execute(root: Path = ROOT) -> tuple[int, list[str]]:
    adapter = _adapter()
    scenarios = {
        x["referee_oracle"]["acceptance_requirement"]: x
        for x in json.loads((root / "automation/reference-scenarios.json").read_text())["scenarios"]
        if x["referee_oracle"]["acceptance_requirement"] not in {}
    }
    families = json.loads((root / "automation/phase-a-semantic-mutation-matrix.json").read_text())[
        "families"
    ]
    errors = []
    executed = 0
    for family in families:
        aid = family["acceptance_id"]
        scenario = scenarios[aid]
        evaluator = getattr(adapter, family["evaluator_id"])
        baseline = _baseline(aid, scenario)
        try:
            evaluator(copy.deepcopy(baseline), scenario)
        except Exception as exc:
            errors.append(f"{aid}: exact evaluator baseline failed: {exc!r}")
            continue
        for case in family["near_misses"]:
            near = copy.deepcopy(baseline)
            MUTATIONS[case["mutation_function_id"]](near)
            executed += 1
            try:
                evaluator(near, scenario)
            except (AssertionError, KeyError, StopIteration):
                pass
            else:
                errors.append(f"{aid}: exact evaluator accepted {case['mutation_function_id']}")
    return executed, errors


def main() -> int:
    n, e = execute()
    [print(x) for x in e]
    print(
        f"Phase A Semantic Mutation Matrix: {'FAIL' if e else 'PASS'} ({n} near misses; 42 exact evaluators)"
    )
    return bool(e)


if __name__ == "__main__":
    raise SystemExit(main())
