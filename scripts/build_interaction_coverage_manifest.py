#!/usr/bin/env python3
"""Build and lock the finite exact-deck interaction coverage surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_cards.full_deck import RULES_BY_NAME, load_full_deck_specs  # noqa: E402
from mtg_deck import load_exact_deck_package  # noqa: E402

CHOICE_CONTRACTS = ROOT / "automation/interaction-choice-contracts.json"
LOCK_PATH = ROOT / "automation/interaction-coverage-lock.json"
SOURCE_PATHS = (
    "src/mtg_cards/full_deck.py",
    "docs/source/oracle/snapshot_v1.json",
    "docs/source/decklist.txt",
    "docs/source/commanders.txt",
    "docs/source/MagicCompRules_2026-06-19.txt",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_choice_contracts() -> dict[str, Any]:
    raw = json.loads(CHOICE_CONTRACTS.read_text(encoding="utf-8"))
    contracts = raw.get("effect_contracts")
    if raw.get("default_for_unknown_effect") != "UNMAPPED_BLOCKING" or not isinstance(
        contracts, dict
    ):
        raise ValueError("interaction choice contracts must fail closed for unknown effects")
    return raw


def _choice(
    purpose: str,
    timing: str,
    *,
    actor: str = "CONTROLLER",
    legality_owner: str = "ENGINE_SHARED_VALIDATOR",
    policy_class: str = "STRATEGIC_WHEN_MULTIPLE",
    rules_refs: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "purpose": purpose,
        "timing": timing,
        "actor": actor,
        "legality_owner": legality_owner,
        "policy_class": policy_class,
        "replay_required": True,
        "rules_refs": list(rules_refs),
    }


def _base_stage(ability_kind: str) -> str:
    return {
        "SPELL": "CAST_PROPOSAL",
        "ACTIVATED": "ACTIVATION_PROPOSAL",
        "TRIGGERED": "TRIGGER_STACKING",
        "REPLACEMENT": "REPLACEMENT_APPLICATION",
        "SPECIAL_ACTION": "SPECIAL_ACTION",
        "STATIC": "CONTINUOUS",
    }.get(ability_kind, "RESOLUTION")


def _base_rules(ability_kind: str) -> tuple[str, ...]:
    return {
        "SPELL": ("601.2",),
        "ACTIVATED": ("602.2",),
        "TRIGGERED": ("603.3",),
        "REPLACEMENT": ("614",),
        "SPECIAL_ACTION": ("116.2",),
        "STATIC": ("611.3",),
    }.get(ability_kind, ("608",))


def _structural_choices(
    behavior: dict[str, Any], *, spell_sibling_count: int
) -> list[dict[str, Any]]:
    ability_kind = str(behavior.get("kind", "UNKNOWN"))
    choices: list[dict[str, Any]] = []

    if ability_kind == "SPELL" and spell_sibling_count > 1:
        choices.append(_choice("CAST_PATH", "CAST_PROPOSAL", rules_refs=("601.2b",)))

    target_schema = behavior.get("target_schema")
    if isinstance(target_schema, dict):
        target_kind = str(target_schema.get("kind", "NONE"))
        minimum = target_schema.get("min", 0)
        maximum = target_schema.get("max", 0)
        if target_kind != "NONE" and maximum != 0:
            timing = {
                "SPELL": "CAST_PROPOSAL",
                "ACTIVATED": "ACTIVATION_PROPOSAL",
                "TRIGGERED": "TRIGGER_STACKING",
            }.get(ability_kind, _base_stage(ability_kind))
            rules = {
                "SPELL": ("601.2c", "115.1a"),
                "ACTIVATED": ("602.2b", "115.1c"),
                "TRIGGERED": ("603.3d", "115.1d"),
            }.get(ability_kind, ("115",))
            if maximum is None or minimum != maximum:
                choices.append(
                    _choice(
                        "TARGET_COUNT",
                        timing,
                        legality_owner="ENGINE_TARGET_SCHEMA",
                        rules_refs=rules,
                    )
                )
            choices.append(
                _choice(
                    "TARGET_SELECTION",
                    timing,
                    legality_owner="ENGINE_TARGET_SCHEMA",
                    rules_refs=rules,
                )
            )

    effect = behavior.get("effect")
    if isinstance(effect, dict):
        if bool(effect.get("target_count_from_x")) or bool(effect.get("amount_from_x")):
            choices.append(_choice("X_VALUE", "CAST_PROPOSAL", rules_refs=("601.2b", "107.3")))
        if effect.get("kicker") is not None:
            choices.append(
                _choice(
                    "KICKER_PAYMENT",
                    "CAST_PROPOSAL",
                    rules_refs=("601.2b", "118.8", "702.33"),
                )
            )

    if behavior.get("alternative_cost") is not None:
        choices.append(
            _choice(
                "ALTERNATIVE_COST_DECLARATION",
                "CAST_PROPOSAL",
                rules_refs=("601.2b", "118.9"),
            )
        )
    if behavior.get("additional_cost") is not None:
        choices.append(
            _choice(
                "ADDITIONAL_COST_CONFIGURATION",
                "CAST_PROPOSAL",
                rules_refs=("601.2b", "601.2f", "118.8"),
            )
        )
    if ability_kind == "TRIGGERED" and bool(behavior.get("optional")):
        choices.append(
            _choice(
                "OPTIONAL_EFFECT_DECISION",
                "RESOLUTION",
                legality_owner="ENGINE_RESOLUTION_VALIDATOR",
                rules_refs=("608.2d",),
            )
        )
    return choices


def _walk_effects(effect: dict[str, Any], path: str) -> list[tuple[str, dict[str, Any]]]:
    result = [(path, effect)]
    nested = effect.get("effects")
    if isinstance(nested, (list, tuple)):
        for index, child in enumerate(nested):
            if isinstance(child, dict):
                result.extend(_walk_effects(child, f"{path}.effects[{index}]"))
    return result


def _deduplicate_choices(choices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for choice in choices:
        key = (str(choice["purpose"]), str(choice["timing"]), str(choice["actor"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(choice)
    return sorted(result, key=lambda item: (item["timing"], item["purpose"], item["actor"]))


def _card_records(
    choice_contracts: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    package = load_exact_deck_package()
    coverage_by_name = {record.name: record for record in package.coverage}
    specs_by_name = {spec.name: spec for spec in load_full_deck_specs().values()}
    effect_contracts = choice_contracts["effect_contracts"]
    records: list[dict[str, Any]] = []
    observed_effect_kinds: set[str] = set()
    observed_event_kinds: set[str] = set()

    if set(specs_by_name) != set(RULES_BY_NAME) or set(coverage_by_name) != set(RULES_BY_NAME):
        raise ValueError("Oracle specs, coverage inventory, and behavior inventory must match exactly")

    for card_name in sorted(RULES_BY_NAME):
        behaviors = RULES_BY_NAME[card_name]
        coverage = coverage_by_name[card_name]
        spec = specs_by_name[card_name]
        if coverage.composition_status != "REVIEWED_COMPOSITION":
            raise ValueError(f"card composition is not reviewed: {card_name}")
        if coverage.oracle_id != spec.oracle_id:
            raise ValueError(f"Oracle identity mismatch for {card_name}")
        spell_sibling_count = sum(1 for item in behaviors if item.get("kind") == "SPELL")
        for behavior_index, behavior in enumerate(behaviors):
            ability_id = str(behavior.get("ability_id", ""))
            ability_kind = str(behavior.get("kind", "UNKNOWN"))
            effect = behavior.get("effect")
            if not ability_id or not isinstance(effect, dict) or not effect.get("kind"):
                raise ValueError(
                    f"behavior lacks stable ability/effect identity: {card_name}[{behavior_index}]"
                )
            event_kind = str(behavior.get("trigger") or behavior.get("event") or ability_kind)
            observed_event_kinds.add(event_kind)
            structural = _structural_choices(behavior, spell_sibling_count=spell_sibling_count)
            for effect_path, effect_node in _walk_effects(effect, "effect"):
                effect_kind = str(effect_node.get("kind", ""))
                observed_effect_kinds.add(effect_kind)
                contract = effect_contracts.get(effect_kind)
                if not isinstance(contract, dict):
                    raise ValueError(
                        f"UNMAPPED effect kind {effect_kind!r} at "
                        f"{card_name}:{ability_id}:{effect_path}"
                    )
                extra_choices = contract.get("choices")
                if not isinstance(extra_choices, list):
                    raise ValueError(f"effect contract {effect_kind} lacks explicit choices list")
                choices = deepcopy(extra_choices)
                if effect_path == "effect":
                    choices.extend(deepcopy(structural))
                rules_refs = set(_base_rules(ability_kind))
                for choice in choices:
                    rules_refs.update(str(value) for value in choice.get("rules_refs", ()))
                parameters = {key: value for key, value in effect_node.items() if key != "effects"}
                record_id = (
                    f"CARD:{coverage.oracle_id}:{behavior_index}:{ability_id}:"
                    f"{effect_path.replace('.', '/').replace('[', ':').replace(']', '')}"
                )
                records.append(
                    {
                        "record_id": record_id,
                        "record_class": "CARD_EFFECT",
                        "card": {
                            "name": card_name,
                            "oracle_id": coverage.oracle_id,
                            "oracle_record_sha256": "sha256:" + spec.oracle_record_sha256,
                            "composition_status": coverage.composition_status,
                            "ability_id": ability_id,
                            "ability_kind": ability_kind,
                            "behavior_index": behavior_index,
                        },
                        "effect": {
                            "path": effect_path,
                            "kind": effect_kind,
                            "parameters_sha256": _sha256_value(parameters),
                        },
                        "event": {"kind": event_kind, "choice_stage": _base_stage(ability_kind)},
                        "choices": _deduplicate_choices(choices),
                        "authority": {
                            "oracle_source": coverage.source,
                            "rules_refs": sorted(rules_refs),
                        },
                        "implementation": {
                            "engine_handler": None,
                            "policy_handler": None,
                            "replay_handler": None,
                        },
                        "evidence": {
                            "positive_tests": [],
                            "negative_tests": [],
                            "fresh_replay_tests": [],
                        },
                        "status": "MAPPED",
                    }
                )
    return records, observed_effect_kinds, observed_event_kinds


def _global_record(
    record_id: str,
    effect_kind: str,
    stage: str,
    rules_refs: tuple[str, ...],
    choices: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_class": "GLOBAL_RULE",
        "card": None,
        "effect": {
            "path": "global",
            "kind": effect_kind,
            "parameters_sha256": _sha256_value(
                {"choice_stage": stage, "rules_refs": rules_refs, "choices": choices}
            ),
        },
        "event": {"kind": effect_kind, "choice_stage": stage},
        "choices": _deduplicate_choices(choices),
        "authority": {"oracle_source": "NONE_GLOBAL_RULE", "rules_refs": list(rules_refs)},
        "implementation": {
            "engine_handler": None,
            "policy_handler": None,
            "replay_handler": None,
        },
        "evidence": {"positive_tests": [], "negative_tests": [], "fresh_replay_tests": []},
        "status": "MAPPED",
    }


def _global_records() -> list[dict[str, Any]]:
    return [
        _global_record(
            "GLOBAL-TRIGGER-ORDERING",
            "TRIGGER_ORDERING",
            "TRIGGER_STACKING",
            ("603.3b", "101.4"),
            [
                _choice(
                    "TRIGGER_ORDER",
                    "TRIGGER_STACKING",
                    legality_owner="ENGINE_SHARED_VALIDATOR",
                    rules_refs=("603.3b", "101.4"),
                )
            ],
        ),
        _global_record(
            "GLOBAL-REPLACEMENT-ORDERING",
            "REPLACEMENT_ORDERING",
            "REPLACEMENT_APPLICATION",
            ("616.1",),
            [
                _choice(
                    "REPLACEMENT_EFFECT_SELECTION",
                    "REPLACEMENT_APPLICATION",
                    actor="AFFECTED_PLAYER",
                    legality_owner="ENGINE_REPLACEMENT_VALIDATOR",
                    rules_refs=("616.1",),
                )
            ],
        ),
        _global_record(
            "GLOBAL-CLEANUP-REENTRY",
            "CLEANUP_REENTRY",
            "TURN_BASED_ACTION",
            ("514.1", "514.3a", "703.4n"),
            [
                _choice(
                    "CLEANUP_DISCARD_SELECTION",
                    "TURN_BASED_ACTION",
                    actor="ACTIVE_PLAYER",
                    legality_owner="ENGINE_TURN_BASED_ACTION_VALIDATOR",
                    rules_refs=("514.1", "703.4n"),
                )
            ],
        ),
        _global_record(
            "GLOBAL-ILLEGAL-ACTION-ROLLBACK",
            "ILLEGAL_ACTION_ROLLBACK",
            "CAST_PROPOSAL",
            ("601.2", "733"),
            [],
        ),
        _global_record(
            "GLOBAL-SBA-TIMING",
            "SBA_TIMING",
            "STATE_BASED_ACTION",
            ("704.3", "704.4", "704.5j"),
            [
                _choice(
                    "LEGEND_RULE_KEEP_SELECTION",
                    "STATE_BASED_ACTION",
                    legality_owner="ENGINE_STATE_BASED_ACTION_VALIDATOR",
                    rules_refs=("704.5j",),
                )
            ],
        ),
        _global_record(
            "GLOBAL-COMMANDER-GRAVEYARD-EXILE-RETURN",
            "COMMANDER_GRAVEYARD_EXILE_RETURN",
            "STATE_BASED_ACTION",
            ("903.9a", "704.3"),
            [
                _choice(
                    "COMMANDER_RETURN_FROM_GRAVEYARD_OR_EXILE",
                    "STATE_BASED_ACTION",
                    actor="OWNER",
                    legality_owner="ENGINE_STATE_BASED_ACTION_VALIDATOR",
                    rules_refs=("903.9a",),
                )
            ],
        ),
        _global_record(
            "GLOBAL-COMMANDER-HAND-LIBRARY-REPLACEMENT",
            "COMMANDER_HAND_LIBRARY_REPLACEMENT",
            "REPLACEMENT_APPLICATION",
            ("903.9b", "614"),
            [
                _choice(
                    "COMMANDER_HAND_LIBRARY_REPLACEMENT",
                    "REPLACEMENT_APPLICATION",
                    actor="OWNER",
                    legality_owner="ENGINE_REPLACEMENT_VALIDATOR",
                    rules_refs=("903.9b",),
                )
            ],
        ),
        _global_record(
            "GLOBAL-PRIORITY-STACK-LIFO",
            "PRIORITY_STACK_LIFO",
            "PRIORITY_WINDOW",
            ("117", "405.5"),
            [
                _choice(
                    "PRIORITY_ACTION_OR_PASS",
                    "PRIORITY_WINDOW",
                    actor="PRIORITY_HOLDER",
                    legality_owner="ENGINE_SHARED_VALIDATOR",
                    rules_refs=("117",),
                )
            ],
        ),
    ]


def build_manifest() -> dict[str, Any]:
    choice_contracts = _load_choice_contracts()
    card_records, observed_effect_kinds, observed_event_kinds = _card_records(choice_contracts)
    declared_effect_kinds = set(choice_contracts["effect_contracts"])
    undeclared = sorted(observed_effect_kinds - declared_effect_kinds)
    unused = sorted(declared_effect_kinds - observed_effect_kinds)
    if undeclared or unused:
        raise ValueError(
            f"effect choice classification mismatch: undeclared={undeclared}, unused={unused}"
        )

    package = load_exact_deck_package()
    records = sorted((*card_records, *_global_records()), key=lambda item: item["record_id"])
    record_ids = [record["record_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        duplicates = sorted({record_id for record_id in record_ids if record_ids.count(record_id) > 1})
        raise ValueError(f"interaction record IDs are not unique: {duplicates}")

    choice_purposes = sorted(
        {choice["purpose"] for record in records for choice in record.get("choices", [])}
    )
    manifest: dict[str, Any] = {
        "schema_version": "interaction-coverage-surface-v1",
        "card_definition_count": len(package.coverage),
        "physical_card_count": package.physical_card_count,
        "card_effect_record_count": len(card_records),
        "global_rule_record_count": len(records) - len(card_records),
        "record_count": len(records),
        "observed_effect_kinds": sorted(observed_effect_kinds),
        "observed_event_kinds": sorted(observed_event_kinds),
        "choice_purposes": choice_purposes,
        "source_digests": {relative: _sha256_file(ROOT / relative) for relative in SOURCE_PATHS},
        "choice_contract_sha256": _sha256_file(CHOICE_CONTRACTS),
        "records": records,
    }
    manifest["manifest_sha256"] = _sha256_value(manifest)
    return manifest


def check_lock(manifest: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    expected = {
        "card_definition_count": lock.get("card_definition_count"),
        "physical_card_count": lock.get("physical_card_count"),
        "card_effect_record_count": lock.get("card_effect_record_count"),
        "global_rule_record_count": lock.get("global_rule_record_count"),
        "record_count": lock.get("record_count"),
        "manifest_sha256": lock.get("manifest_sha256"),
    }
    actual = {key: manifest.get(key) for key in expected}
    return expected == actual, {
        "expected": expected,
        "actual": actual,
        "observed_effect_kinds": manifest["observed_effect_kinds"],
        "observed_event_kinds": manifest["observed_event_kinds"],
        "choice_purposes": manifest["choice_purposes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-lock", action="store_true")
    args = parser.parse_args()

    try:
        manifest = build_manifest()
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2))
        return 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.check_lock:
        passed, detail = check_lock(manifest)
        print(
            json.dumps(
                {"status": "PASS" if passed else "FAIL", **detail},
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if passed else 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "card_definition_count": manifest["card_definition_count"],
                "physical_card_count": manifest["physical_card_count"],
                "card_effect_record_count": manifest["card_effect_record_count"],
                "global_rule_record_count": manifest["global_rule_record_count"],
                "record_count": manifest["record_count"],
                "manifest_sha256": manifest["manifest_sha256"],
                "observed_effect_kinds": manifest["observed_effect_kinds"],
                "observed_event_kinds": manifest["observed_event_kinds"],
                "choice_purposes": manifest["choice_purposes"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
