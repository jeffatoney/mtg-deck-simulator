"""Protected adapter and referee for Phase A candidate artifacts.

Candidates supply only a raw transcript.  Every verdict in this module is
derived from that transcript or from calls observed by the protected profiler.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any

ENTRYPOINT = "mtg_kernel.executor.GameExecutor.run"
ROOT = Path(__file__).resolve().parents[2]

# Receipt vocabulary retained for artifact validation and adversarial fixtures.
# Causal liveness is governed by each oracle's exact module/qualname contract,
# never by these class-name strings alone.
REQUIRED_SERVICES = {
    "ActionGenerator",
    "ActionValidator",
    "CostService",
    "StackService",
    "PriorityEngine",
    "ResolutionEngine",
    "TargetValidator",
    "ZoneService",
    "StateBasedActions",
    "TriggerEngine",
    "TurnEngine",
    "ExternalZoneLedger",
    "ReplayEngine",
}

TRUST_BEARING_FIELDS = {
    "satisfied_acceptance_ids",
    "postconditions",
    "trace_invariants",
    "referee_observations",
    "production_entrypoint",
    "passed",
    "valid",
    "legal",
    "correct",
    "verdict",
    "compliant",
    "satisfied",
    "success",
    "status",
}


def reject_candidate_verdicts(value: object, path: str = "result") -> None:
    """Reject verdicts at any depth; candidates may emit objective facts only."""
    if isinstance(value, dict):
        forbidden = TRUST_BEARING_FIELDS.intersection(value)
        assert not forbidden, f"candidate verdict fields at {path}: {sorted(forbidden)}"
        for key, child in value.items():
            reject_candidate_verdicts(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_candidate_verdicts(child, f"{path}[{index}]")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class CallObserver:
    """Referee-owned call/return trace installed before candidate import."""

    records: list[dict[str, Any]] = field(default_factory=list)
    order: int = 0
    frame_calls: dict[int, int] = field(default_factory=dict)

    def profile(self, frame: FrameType, event: str, arg: object) -> None:
        if event not in {"call", "return", "exception"}:
            return
        module = str(frame.f_globals.get("__name__", ""))
        if not module.startswith(("mtg_kernel", "mtg_cards")):
            return
        self.order += 1
        frame_id = id(frame)
        if event == "call":
            self.frame_calls[frame_id] = self.order
        caller = frame.f_back
        local = frame.f_locals
        self.records.append(
            {
                "order": self.order,
                "call_id": self.frame_calls.get(frame_id),
                "parent_call_id": self.frame_calls.get(id(caller)) if caller else None,
                "kind": event,
                "module": module,
                "qualname": frame.f_code.co_qualname,
                "filename": str(Path(frame.f_code.co_filename).resolve()),
                "caller_module": str(caller.f_globals.get("__name__", "")) if caller else None,
                "caller_qualname": caller.f_code.co_qualname if caller else None,
                "game_id": local.get("game_id") or getattr(local.get("self"), "game_id", None),
                "action_id": local.get("action_id")
                or getattr(local.get("self"), "action_id", None),
            }
        )


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    candidate_input = json.loads(json.dumps(scenario["candidate_input"]))
    observer = CallObserver()
    previous = sys.getprofile()
    sys.setprofile(observer.profile)
    try:
        from mtg_kernel.executor import GameExecutor

        factory = getattr(GameExecutor, "from_reference_state", None)
        if not callable(factory):
            raise AssertionError("GameExecutor.from_reference_state is required")
        executor = factory(candidate_input)
        result = executor.run()
    finally:
        sys.setprofile(previous)
    if not isinstance(result, dict):
        raise AssertionError("GameExecutor.run must return a raw artifact mapping")
    reject_candidate_verdicts(result)
    assert "_referee_calls" not in result, "candidate profiler records are prohibited"
    result["_referee_calls"] = observer.records
    result["_referee_call_contract"] = json.loads(
        json.dumps(scenario["referee_oracle"]["required_call_contract"])
    )
    validate_raw_artifact(result, scenario)
    return result


def validate_raw_artifact(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    reject_candidate_verdicts(result)
    assert "_referee_calls_candidate" not in result
    required = {
        "initial_state",
        "actions",
        "events",
        "decisions",
        "card_instances",
        "objects",
        "state_snapshots",
        "receipts",
        "final_state",
        "external_ledger",
        "replay",
        "run_manifest",
        "rng_streams",
    }
    assert required <= result.keys()
    candidate_input = scenario["candidate_input"]
    assert result["initial_state"] == candidate_input["initial_state"]
    assert result["actions"] and result["events"] and result["decisions"]
    assert result["run_manifest"]["scenario_id"] == scenario["scenario_id"]
    assert result["run_manifest"]["scenario_version"] == scenario["scenario_version"]
    _validate_hash_chain(result)
    _validate_analytics(result)


def _validate_hash_chain(result: dict[str, Any]) -> None:
    events = result["events"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert len({e["event_id"] for e in events}) == len(events)
    actions = {a["action_id"] for a in result["actions"]}
    event_ids = {e["event_id"] for e in events}
    event_order = {e["event_id"]: e["sequence"] for e in events}
    previous = canonical_hash(result["initial_state"])
    terminal_seen = False
    for event in events:
        assert event["pre_state_hash"] == previous
        assert event["post_state_hash"]
        snapshot = result["state_snapshots"][event["sequence"]]
        assert canonical_hash(snapshot) == event["post_state_hash"]
        assert event.get("parent_action_id") is None or event["parent_action_id"] in actions
        assert event.get("parent_event_id") is None or event["parent_event_id"] in event_ids
        if event.get("parent_event_id") is not None:
            assert event_order[event["parent_event_id"]] < event["sequence"]
        assert not terminal_seen, "event after terminal state"
        terminal_seen = event["event_type"] == "terminal_state"
        previous = event["post_state_hash"]
    assert previous == canonical_hash(result["final_state"])


def _validate_analytics(result: dict[str, Any]) -> None:
    assert result["events"] and result["decisions"]
    event_fields = {
        "schema_version",
        "run_id",
        "game_id",
        "event_id",
        "sequence",
        "turn",
        "phase",
        "step",
        "priority_window_id",
        "actor",
        "event_type",
        "source_object_ids",
        "target_object_ids",
        "parent_action_id",
        "parent_event_id",
        "pre_state_hash",
        "post_state_hash",
        "payload",
    }
    decision_fields = {
        "decision_id",
        "observation_hash",
        "legal_actions",
        "selected_action_id",
        "policy_id",
        "policy_version",
        "action_set_hash",
        "future_information_used",
    }
    assert all(event_fields <= e.keys() for e in result["events"])
    assert all(decision_fields <= d.keys() for d in result["decisions"])
    assert all(d["future_information_used"] is False for d in result["decisions"])
    forbidden = {
        "combo_access",
        "protection_access",
        "second_line_access",
        "strandedness",
        "high_value_draw",
        "strategic_optimality",
    }
    assert all(
        forbidden.isdisjoint(e) and forbidden.isdisjoint(e["payload"]) for e in result["events"]
    )
    assert len({d["decision_id"] for d in result["decisions"]}) == len(result["decisions"])
    for decision in result["decisions"]:
        assert decision["legal_actions"] or decision.get("forced_pass_reason")
        assert canonical_hash(decision["legal_actions"]) == decision["action_set_hash"]
        legal_ids = {action["action_id"] for action in decision["legal_actions"]}
        assert decision["selected_action_id"] in legal_ids
        assert "library_order" not in decision.get("policy_observation", {})
    if "run_manifest" in result:
        manifest = result["run_manifest"]
        assert {
            "schema_version",
            "run_id",
            "game_id",
            "scenario_id",
            "scenario_version",
            "source_hashes",
            "event_schema_version",
            "replay_provenance",
        } <= manifest.keys()
        assert manifest["source_hashes"] and manifest["replay_provenance"]


def assert_causally_live(result: dict[str, Any]) -> None:
    from scripts.check_kernel_liveness import validate as validate_liveness

    assert not validate_liveness(result)
    calls = result["_referee_calls"]
    run_calls = [
        r
        for r in calls
        if r["module"] == "mtg_kernel.executor" and r["qualname"].endswith("GameExecutor.run")
    ]
    assert run_calls
    run_call = min((r for r in run_calls if r["kind"] == "call"), key=lambda r: r["order"])
    by_call_id = {r.get("call_id"): r for r in calls if r["kind"] == "call"}

    def beneath_run(call: dict[str, Any]) -> bool:
        parent = call.get("parent_call_id")
        seen: set[object] = set()
        while parent is not None and parent not in seen:
            if parent == run_call["call_id"]:
                return True
            seen.add(parent)
            parent = by_call_id.get(parent, {}).get("parent_call_id")
        return False

    beneath = [r for r in calls if r["kind"] == "call" and beneath_run(r)]
    transitions = {
        (e["parent_action_id"], e["pre_state_hash"], e["post_state_hash"]) for e in result["events"]
    }
    event_ids = {e["event_id"] for e in result["events"]}
    game_ids = {e["game_id"] for e in result["events"]}
    staged_source = (ROOT / "src").resolve()
    for call in beneath:
        assert Path(call["filename"]).resolve().is_relative_to(staged_source)
    contracts = result["_referee_call_contract"]
    for contract in contracts:
        matches = [
            call
            for call in beneath
            if call["module"] == contract["module"] and call["qualname"] == contract["qualname"]
        ]
        assert matches, f"missing canonical call: {contract['module']}.{contract['qualname']}"
        assert contract["qualname"].endswith(f".{contract['operation']}")
        if event_type := contract.get("causal_event_type"):
            assert any(
                event["event_type"] == event_type
                and call["game_id"] == event["game_id"]
                and call["action_id"] == event["parent_action_id"]
                and event["pre_state_hash"] != event["post_state_hash"]
                for call in matches
                for event in result["events"]
            )
    for receipt in result["receipts"]:
        assert {
            "run_id",
            "game_id",
            "action_id",
            "service",
            "operation",
            "source_object_id",
            "pre_state_hash",
            "post_state_hash",
            "causal_event_ids",
        } <= receipt.keys()
        assert receipt["game_id"] in game_ids
        assert receipt["causal_event_ids"]
        assert set(receipt["causal_event_ids"]) <= event_ids
        assert (
            receipt["action_id"],
            receipt["pre_state_hash"],
            receipt["post_state_hash"],
        ) in transitions
        assert receipt["pre_state_hash"] != receipt["post_state_hash"]
        assert any(
            r["action_id"] == receipt["action_id"]
            and r["game_id"] == receipt["game_id"]
            and any(
                r["module"] == contract["module"]
                and r["qualname"] == contract["qualname"]
                and receipt["operation"] == contract["operation"]
                for contract in contracts
            )
            for r in beneath
        )


def assert_predicates(result: dict[str, Any], predicates: list[dict[str, Any]]) -> None:
    events = result["events"]
    for predicate in predicates:
        matching = [e for e in events if e["event_type"] == predicate["event_type"]]
        assert len(matching) >= predicate.get("minimum", 1), predicate["predicate_id"]
        if "source_object_id" in predicate:
            assert any(predicate["source_object_id"] in e["source_object_ids"] for e in matching)
        for key, value in predicate.get("payload_equals", {}).items():
            assert any(e["payload"].get(key) == value for e in matching), predicate["predicate_id"]


def assert_trace_invariants(result: dict[str, Any]) -> None:
    """Compute every frozen invariant from the complete raw stream."""
    events = result["events"]
    objects = {item["object_id"]: item for item in result["objects"]}
    cards = {item["card_instance_id"]: item for item in result["card_instances"]}
    receipts = result["receipts"]
    causal_entries = {
        "land_played",
        "permanent_spell_resolved",
        "token_created",
        "put_effect_resolved",
    }
    stack_ids: set[str] = set()
    trigger_ids: set[str] = set()
    announced_targets: dict[str, list[str]] = {}
    registered = set(objects) | set(cards)
    for event in events:
        payload = event["payload"]
        assert set(event["source_object_ids"]) <= registered
        assert set(event["target_object_ids"]) <= registered
        if event["event_type"] == "stack_object_created":
            stack_ids.add(payload["stack_object_id"])
        elif event["event_type"] == "spell_resolved":
            assert payload["stack_object_id"] in stack_ids
        elif event["event_type"] == "trigger_created":
            trigger_ids.add(payload["trigger_object_id"])
        elif event["event_type"] == "trigger_put_on_stack":
            assert payload["trigger_object_id"] in trigger_ids
        elif event["event_type"] == "targets_announced":
            announced_targets[payload["stack_object_id"]] = event["target_object_ids"]
        elif event["event_type"] == "targets_revalidated":
            assert payload["stack_object_id"] in announced_targets
            announced = announced_targets[payload["stack_object_id"]]
            removed = payload.get("illegal_target_object_ids", [])
            assert event["target_object_ids"] == [item for item in announced if item not in removed]
        elif event["event_type"] == "battlefield_entered":
            assert payload["causal_category"] in causal_entries
        elif event["event_type"] == "cleanup_completed":
            assert not result["state_snapshots"][event["sequence"]]["marked_damage"]
        elif event["event_type"] == "zone_moved":
            oid = payload["object_id"]
            assert oid in objects
            obj = objects[oid]
            if obj.get("card_instance_id") is not None:
                assert obj["card_instance_id"] in cards
            if payload["to_zone"] in {"hand", "library", "graveyard"}:
                assert obj["owner"] == payload["zone_owner"]
            assert any(
                r["service"] == "ZoneService" and event["event_id"] in r["causal_event_ids"]
                for r in receipts
            )
        elif event["event_type"] == "stack_mutated":
            assert any(
                r["service"] == "StackService" and event["event_id"] in r["causal_event_ids"]
                for r in receipts
            )
        elif event["event_type"] == "turn_changed":
            assert any(
                r["service"] == "TurnEngine" and event["event_id"] in r["causal_event_ids"]
                for r in receipts
            )
        elif event["event_type"] == "terminal_state":
            assert payload["cause_category"] in {
                "state_based_action",
                "explicit_game_ending_effect",
            }
    for obj in objects.values():
        if obj["object_type"] in {"token", "copy"}:
            assert obj.get("card_instance_id") is None
    for zone_name, zone_objects in result["final_state"]["zones"].items():
        for object_id in zone_objects:
            assert object_id in objects
            if zone_name in {"hand", "library", "graveyard"}:
                zone_owner = result["final_state"].get("zone_owners", {}).get(zone_name)
                if zone_owner is not None:
                    assert objects[object_id]["owner"] == zone_owner
    replay = result["replay"]
    for replay_field in ("actions", "events", "rng_streams", "external_ledger", "final_state"):
        assert replay[replay_field] == result[replay_field]


def validate_replay_artifact(original: dict[str, Any], replay: dict[str, Any]) -> None:
    for replay_field in (
        "actions",
        "events",
        "rng_streams",
        "external_ledger",
        "objects",
        "final_state",
    ):
        assert replay[replay_field] == original[replay_field]
    assert canonical_hash(replay["final_state"]) == canonical_hash(original["final_state"])


def assert_acceptance(
    result: dict[str, Any], mapping: dict[str, Any], scenario: dict[str, Any]
) -> None:
    assert mapping["referee_evaluator_id"] == scenario["referee_oracle"]["assertion_id"]
    assertion = globals().get(str(mapping["referee_evaluator_id"]))
    assert callable(assertion), f"missing protected evaluator: {mapping['referee_evaluator_id']}"
    assertion(result, scenario)
    assert_causally_live(result)


def _assert_requirement(
    result: dict[str, Any], scenario: dict[str, Any], assertion_id: str
) -> None:
    """Apply frozen predicates and any requirement-specific semantic proof."""
    oracle = scenario["referee_oracle"]
    _assert_forbidden_transitions(result, oracle.get("forbidden_transitions", []))
    assert_predicates(result, oracle["expected_state_transition_predicates"])
    assert_predicates(result, oracle["expected_final_state_predicates"])
    _assert_semantic_plan(result, oracle["semantic_assertion_plan"])
    special = {
        "evaluate_a1": _assert_sol_ring,
        "evaluate_a2": _assert_glint_horn_cast,
        "evaluate_a3": _assert_commander_tax,
        "evaluate_b1": _assert_lantern,
        "evaluate_c1": _assert_cleanup_damage,
        "evaluate_c6": _assert_glint_horn,
        "evaluate_d4": _assert_commit_external,
        "evaluate_d7": _assert_memory_actions,
        "evaluate_d8": _assert_memory_rejection,
        "evaluate_f2": _assert_twinflame_token,
        "evaluate_g4": _assert_pilot_lock,
    }.get(assertion_id)
    if special:
        special(result)


def _assert_forbidden_transitions(result: dict[str, Any], forbidden: list[dict[str, Any]]) -> None:
    """Reject forbidden transitions, optionally within a bounded event window."""
    events = result["events"]
    for rule in forbidden:
        start = 0
        end = len(events)
        if before := rule.get("before_event_type"):
            end = next(
                (index for index, event in enumerate(events) if event["event_type"] == before),
                end,
            )
        if after := rule.get("after_event_type"):
            start = next(
                (index + 1 for index, event in enumerate(events) if event["event_type"] == after),
                start,
            )
        assert not any(event["event_type"] == rule["event_type"] for event in events[start:end]), (
            rule.get("predicate_id", rule["event_type"])
        )


def _assert_semantic_plan(result: dict[str, Any], plan: dict[str, Any]) -> None:
    """Apply non-presence semantic checks shared by every frozen evaluator."""
    events = result["events"]
    required = plan["ordered_event_types"]
    cursor = 0
    selected: list[dict[str, Any]] = []
    for event_type in required:
        match = next(
            (event for event in events[cursor:] if event["event_type"] == event_type),
            None,
        )
        assert match is not None
        selected.append(match)
        cursor = events.index(match) + 1
    assert [event["sequence"] for event in selected] == sorted(
        event["sequence"] for event in selected
    )
    if plan["require_non_noop_transitions"]:
        assert all(event["pre_state_hash"] != event["post_state_hash"] for event in selected)
    registered = {item["object_id"] for item in result["objects"]}
    registered.update(item["card_instance_id"] for item in result["card_instances"])
    if plan["require_registered_object_references"]:
        for event in selected:
            assert set(event["source_object_ids"]) <= registered
            assert set(event["target_object_ids"]) <= registered


def _ordered(result: dict[str, Any], *types: str) -> list[dict[str, Any]]:
    positions = []
    for event_type in types:
        event = next(e for e in result["events"] if e["event_type"] == event_type)
        positions.append(event)
    assert [e["sequence"] for e in positions] == sorted(e["sequence"] for e in positions)
    return positions


def _assert_cleanup_damage(result: dict[str, Any]) -> None:
    marked, cleanup, next_turn = _ordered(
        result, "damage_marked", "cleanup_completed", "turn_changed"
    )
    assert result["state_snapshots"][marked["sequence"]]["marked_damage"]
    assert not result["state_snapshots"][cleanup["sequence"]]["marked_damage"]
    assert not result["state_snapshots"][next_turn["sequence"]]["marked_damage"]


def _assert_memory_actions(result: dict[str, Any]) -> None:
    memory = [
        action
        for action in result["actions"]
        if action.get("oracle_name") == "Memory" or action.get("face") == "Memory"
    ]
    assert memory
    assert all(action.get("origin_zone") == "graveyard" for action in memory)
    assert all(action.get("targets") in ([], ()) for action in memory)
    assert all("target" not in action or action["target"] is None for action in memory)


def _assert_memory_rejection(result: dict[str, Any]) -> None:
    rejected = _ordered(result, "action_rejected")[0]
    attempted = next(
        action
        for action in result["actions"]
        if action["action_id"] == rejected["parent_action_id"]
    )
    assert attempted.get("face") == "Memory"
    assert len(attempted.get("targets", [])) >= 1
    assert rejected["pre_state_hash"] == rejected["post_state_hash"]
    assert canonical_hash(result["initial_state"]) == canonical_hash(result["final_state"])
    assert not any(event["event_type"] in {"cost_paid", "zone_moved"} for event in result["events"])


def _assert_pilot_lock(result: dict[str, Any]) -> None:
    # G4 is grounded in the protected workflow tree, not candidate metadata.
    import runpy

    check = runpy.run_path(str(ROOT / "scripts/check_production_pilot_lock.py"))["check"]
    assert check(ROOT)["status"] == "PASS"
    assert not (ROOT / ".github/workflows/pilot-simulation.yml").exists()


def _assert_sol_ring(result: dict[str, Any]) -> None:
    created, priority, resolved, entered = _ordered(
        result,
        "stack_object_created",
        "priority_window_opened",
        "spell_resolved",
        "battlefield_entered",
    )
    stack_id = created["payload"]["stack_object_id"]
    card_id = created["payload"]["card_instance_id"]
    assert created["payload"]["object_type"] == "SpellObject"
    assert resolved["payload"]["stack_object_id"] == stack_id
    assert entered["payload"]["card_instance_id"] == card_id
    assert card_id not in created["payload"]["battlefield_before"]
    assert priority["payload"]["respondable_stack_object_id"] == stack_id


def _assert_glint_horn_cast(result: dict[str, Any]) -> None:
    announced, created, resolved, entered = _ordered(
        result, "spell_announced", "stack_object_created", "spell_resolved", "battlefield_entered"
    )
    card_id = announced["payload"]["card_instance_id"]
    stack_id = created["payload"]["stack_object_id"]
    assert created["payload"]["object_type"] == "SpellObject"
    assert created["payload"]["card_instance_id"] == card_id
    assert resolved["payload"]["stack_object_id"] == stack_id
    assert entered["payload"]["card_instance_id"] == card_id
    assert card_id not in resolved["payload"].get("battlefield_before", [])
    snapshot = result["state_snapshots"][entered["sequence"]]
    assert snapshot["summoning_sickness"][entered["payload"]["object_id"]] is True


def _assert_commander_tax(result: dict[str, Any]) -> None:
    casts = [event for event in result["events"] if event["event_type"] == "commander_cast"]
    payments = [event for event in result["events"] if event["event_type"] == "cost_paid"]
    replacements = [
        event for event in result["events"] if event["event_type"] == "commander_replaced"
    ]
    assert len(casts) == len(payments) == 2
    commander_id = casts[0]["payload"]["card_instance_id"]
    assert all(event["payload"]["card_instance_id"] == commander_id for event in casts)
    assert [event["payload"]["cast_count_after"] for event in casts] == [1, 2]
    assert casts[0]["sequence"] < replacements[0]["sequence"] < casts[1]["sequence"]
    base = payments[0]["payload"]["base_generic_cost"]
    assert payments[0]["payload"]["commander_tax"] == 0
    assert payments[1]["payload"]["commander_tax"] == 2
    assert payments[0]["payload"]["generic_paid"] == base
    assert payments[1]["payload"]["generic_paid"] == base + 2
    assert replacements[0]["payload"]["destination"] == "command"
    assert replacements[0]["payload"]["card_instance_id"] == commander_id


def _assert_lantern(result: dict[str, Any]) -> None:
    created, placed, priority, revalidated, moved = _ordered(
        result,
        "trigger_created",
        "trigger_put_on_stack",
        "priority_window_opened",
        "targets_revalidated",
        "zone_moved",
    )
    trigger_id = created["payload"]["trigger_object_id"]
    target_id = created["target_object_ids"][0]
    assert created["payload"]["object_type"] == "TriggeredAbilityObject"
    assert placed["payload"]["trigger_object_id"] == trigger_id
    assert revalidated["target_object_ids"] == [target_id]
    assert moved["payload"] == {
        "object_id": target_id,
        "from_zone": "graveyard",
        "to_zone": "exile",
        "zone_owner": moved["payload"]["zone_owner"],
    }
    assert priority["payload"]["respondable_stack_object_id"] == trigger_id


def _assert_commit_external(result: dict[str, Any]) -> None:
    announced, revalidated, moved = _ordered(
        result, "targets_announced", "targets_revalidated", "external_ledger_moved"
    )
    target = announced["target_object_ids"][0]
    assert revalidated["target_object_ids"] == [target]
    assert moved["payload"]["object_id"] == target
    assert moved["payload"]["destination"] == "owners_library"
    assert moved["payload"]["position"] == 2
    assert target not in result["final_state"]["zones"]["library"]


def _assert_twinflame_token(result: dict[str, Any]) -> None:
    copied, token, delayed, placed, exiled, ceased = _ordered(
        result,
        "spell_copied",
        "token_created",
        "delayed_trigger_created",
        "trigger_put_on_stack",
        "token_exiled",
        "token_ceased",
    )
    token_id = token["payload"]["object_id"]
    assert token["payload"]["card_instance_id"] is None
    assert token["payload"]["haste"] is True
    assert delayed["payload"]["token_object_id"] == token_id
    assert placed["payload"]["trigger_object_id"] == delayed["payload"]["trigger_object_id"]
    assert exiled["payload"]["object_id"] == token_id
    assert ceased["payload"]["object_id"] == token_id
    assert copied["payload"]["cast"] is False


def _assert_dualcaster_twinflame(result: dict[str, Any]) -> None:
    cast, copied, retargeted, token, cleanup = _ordered(
        result, "spell_cast", "spell_copied", "targets_revalidated", "token_created", "token_ceased"
    )
    assert cast["payload"]["cast"] is True
    assert copied["payload"]["cast"] is False
    assert copied["payload"]["stack_position"] > cast["payload"]["stack_position"]
    assert retargeted["target_object_ids"]
    assert token["payload"]["card_instance_id"] is None
    assert cleanup["payload"]["object_id"] == token["payload"]["object_id"]


def _assert_glint_horn(result: dict[str, Any]) -> None:
    attack, paid, discarded, damage, treasure, cleanup, terminal = _ordered(
        result,
        "attacker_declared",
        "activation_cost_paid",
        "cards_discarded",
        "damage_dealt",
        "treasure_created",
        "cleanup_completed",
        "terminal_state",
    )
    assert attack["source_object_ids"] == paid["source_object_ids"]
    assert paid["payload"]["discard_count"] == len(discarded["payload"]["object_ids"])
    assert (
        damage["payload"]["life_totals_after"]
        == result["state_snapshots"][damage["sequence"]]["life_totals"]
    )
    assert treasure["payload"]["cause"] == "Malcolm"
    assert not result["state_snapshots"][cleanup["sequence"]]["marked_damage"]
    assert terminal["sequence"] > cleanup["sequence"]


def load_scenario(scenario_id: str) -> dict[str, Any]:
    document = json.loads((ROOT / "automation/reference-scenarios.json").read_text())
    return next(item for item in document["scenarios"] if item["scenario_id"] == scenario_id)


def metamorphic_scenario(scenario: dict[str, Any], variant: int = 1) -> dict[str, Any]:
    """Remap candidate-visible identities without exposing or changing the oracle."""
    transformed = json.loads(json.dumps(scenario))
    candidate = transformed["candidate_input"]
    old_game_id = candidate["initial_state"]["game_id"]
    new_game_id = f"metamorphic-{variant}-{old_game_id}"

    def remap(value: object) -> object:
        if isinstance(value, str):
            return value.replace(old_game_id, new_game_id)
        if isinstance(value, list):
            return [remap(item) for item in value]
        if isinstance(value, dict):
            return {key: remap(item) for key, item in value.items()}
        return value

    transformed["candidate_input"] = remap(candidate)
    transformed["candidate_input"]["initial_state"]["game_id"] = new_game_id
    transformed["candidate_input"]["rng_streams"] = {
        name: int(seed) + 1009 * variant for name, seed in candidate["rng_streams"].items()
    }
    return transformed


# Explicit frozen acceptance assertions. Each manifest entry resolves to one.


def evaluate_a1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a1")


def evaluate_a2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a2")


def evaluate_a3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a3")


def evaluate_a4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a4")


def evaluate_a5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a5")


def evaluate_a6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a6")


def evaluate_a7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_a7")


def evaluate_b1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b1")


def evaluate_b2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b2")


def evaluate_b3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b3")


def evaluate_b4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b4")


def evaluate_b5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b5")


def evaluate_b6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_b6")


def evaluate_c1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c1")


def evaluate_c2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c2")


def evaluate_c3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c3")


def evaluate_c4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c4")


def evaluate_c5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c5")


def evaluate_c6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c6")


def evaluate_c7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c7")


def evaluate_c8(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_c8")


def evaluate_d1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d1")


def evaluate_d2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d2")


def evaluate_d3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d3")


def evaluate_d4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d4")


def evaluate_d5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d5")


def evaluate_d6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d6")


def evaluate_d7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d7")


def evaluate_d8(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d8")


def evaluate_d9(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_d9")


def evaluate_e1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_e1")


def evaluate_e2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_e2")


def evaluate_e3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_e3")


def evaluate_e4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_e4")


def evaluate_e5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_e5")


def evaluate_f1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_f1")


def evaluate_f2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_f2")


def evaluate_f3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_f3")


def evaluate_g1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_g1")


def evaluate_g2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_g2")


def evaluate_g3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_g3")


def evaluate_g4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "evaluate_g4")
