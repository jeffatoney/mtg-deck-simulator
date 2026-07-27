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

    def profile(self, frame: FrameType, event: str, arg: object) -> None:
        if event not in {"call", "return", "exception"}:
            return
        module = str(frame.f_globals.get("__name__", ""))
        if not module.startswith(("mtg_kernel", "mtg_cards")):
            return
        self.order += 1
        caller = frame.f_back
        local = frame.f_locals
        self.records.append(
            {
                "order": self.order,
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
    observer = CallObserver()
    previous = sys.getprofile()
    sys.setprofile(observer.profile)
    try:
        from mtg_kernel.executor import GameExecutor

        factory = getattr(GameExecutor, "from_reference_state", None)
        if not callable(factory):
            raise AssertionError("GameExecutor.from_reference_state is required")
        executor = factory(json.loads(json.dumps(scenario)))
        result = executor.run()
    finally:
        sys.setprofile(previous)
    if not isinstance(result, dict):
        raise AssertionError("GameExecutor.run must return a raw artifact mapping")
    reject_candidate_verdicts(result)
    assert "_referee_calls" not in result, "candidate profiler records are prohibited"
    result["_referee_calls"] = observer.records
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
    assert result["initial_state"] == scenario["initial_state"]
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
    previous = canonical_hash(result["initial_state"])
    terminal_seen = False
    for event in events:
        assert event["pre_state_hash"] == previous
        assert event["post_state_hash"]
        assert event.get("parent_action_id") is None or event["parent_action_id"] in actions
        assert event.get("parent_event_id") is None or event["parent_event_id"] in event_ids
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
    first_run = min(r["order"] for r in run_calls if r["kind"] == "call")
    last_run = max(r["order"] for r in run_calls if r["kind"] in {"return", "exception"})
    beneath = [r for r in calls if first_run < r["order"] < last_run and r["kind"] == "call"]
    observed = {r["qualname"].split(".")[0] for r in beneath}
    assert REQUIRED_SERVICES <= observed
    transitions = {
        (e["parent_action_id"], e["pre_state_hash"], e["post_state_hash"]) for e in result["events"]
    }
    receipt_services = set()
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
        assert (
            receipt["action_id"],
            receipt["pre_state_hash"],
            receipt["post_state_hash"],
        ) in transitions
        assert any(
            r["action_id"] == receipt["action_id"]
            and r["qualname"].startswith(receipt["service"] + ".")
            for r in beneath
        )
        receipt_services.add(receipt["service"])
    assert REQUIRED_SERVICES <= receipt_services


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
    for event in events:
        payload = event["payload"]
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
    assert mapping["assertion_id"] == scenario["assertion_id"]
    assertion = globals().get(str(mapping["assertion_id"]))
    assert callable(assertion), f"missing protected assertion: {mapping['assertion_id']}"
    assertion(result, scenario)
    assert_causally_live(result)


def _assert_requirement(
    result: dict[str, Any], scenario: dict[str, Any], assertion_id: str
) -> None:
    """Apply frozen predicates and any requirement-specific semantic proof."""
    assert_predicates(result, scenario["expected_state_transition_predicates"])
    assert_predicates(result, scenario["expected_final_state_predicates"])
    special = {
        "assert_a1": _assert_sol_ring,
        "assert_b1": _assert_lantern,
        "assert_c6": _assert_glint_horn,
        "assert_e2": _assert_commit_external,
        "assert_f2": _assert_dualcaster_twinflame,
    }.get(assertion_id)
    if special:
        special(result)


def _ordered(result: dict[str, Any], *types: str) -> list[dict[str, Any]]:
    positions = []
    for event_type in types:
        event = next(e for e in result["events"] if e["event_type"] == event_type)
        positions.append(event)
    assert [e["sequence"] for e in positions] == sorted(e["sequence"] for e in positions)
    return positions


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


# Explicit frozen acceptance assertions. Each manifest entry resolves to one.


def assert_a1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a1")


def assert_a2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a2")


def assert_a3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a3")


def assert_a4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a4")


def assert_a5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a5")


def assert_a6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a6")


def assert_a7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_a7")


def assert_b1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b1")


def assert_b2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b2")


def assert_b3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b3")


def assert_b4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b4")


def assert_b5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b5")


def assert_b6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_b6")


def assert_c1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c1")


def assert_c2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c2")


def assert_c3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c3")


def assert_c4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c4")


def assert_c5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c5")


def assert_c6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c6")


def assert_c7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c7")


def assert_c8(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_c8")


def assert_d1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d1")


def assert_d2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d2")


def assert_d3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d3")


def assert_d4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d4")


def assert_d5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d5")


def assert_d6(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d6")


def assert_d7(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d7")


def assert_d8(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d8")


def assert_d9(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_d9")


def assert_e1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_e1")


def assert_e2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_e2")


def assert_e3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_e3")


def assert_e4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_e4")


def assert_e5(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_e5")


def assert_f1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_f1")


def assert_f2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_f2")


def assert_f3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_f3")


def assert_g1(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_g1")


def assert_g2(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_g2")


def assert_g3(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_g3")


def assert_g4(result: dict[str, Any], scenario: dict[str, Any]) -> None:
    _assert_requirement(result, scenario, "assert_g4")
