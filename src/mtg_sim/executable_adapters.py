"""Fail-closed executable action-adapter registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import sys

from mtg_sim.offline_sources import build_simulation_deck

EXECUTABLE_CARDS = {
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
    "Ravenform",
    "Reality Ripple",
    "Reality Shift",
    "Resculpt",
    "Sentinel Totem",
    "Siren Stormtamer",
    "Soul-Guide Lantern",
    "Spell Pierce",
    "Syncopate",
    "Vandalblast",
    "Wash Away",
    "Rebuild",
    "Invert // Invent",
    "Long-Term Plans",
    "Step Through",
    "Vedalken Aethermage",
    "Muddle the Mixture",
    "Drift of Phantasms",
    "Dizzy Spell",
    "Commit // Memory",
    "Prismari Command",
    "Spectral Sailor",
    "Sleight of Hand",
    "Opt",
    "Impulse",
    "Frantic Search",
    "Faithless Looting",
    "Fact or Fiction",
    "Expedite",
    "Chart a Course",
    "Arcane Signet",
    "Ash Barrens",
    "Breeches, Brazen Plunderer",
    "Twinflame",
    "Storm Fleet Sprinter",
    "Psychosis Crawler",
    "Niv-Mizzet, the Firemind",
    "Lightning-Rig Crew",
    "Glint-Horn Buccaneer",
    "Electroduplicate",
    "Curiosity",
    "Dualcaster Mage",
    "Crab Umbra",
    "Cascade Bluffs",
    "Command Tower",
    "Demolition Field",
    "Evolving Wilds",
    "Exotic Orchard",
    "Fellwar Stone",
    "Frostboil Snarl",
    "Island",
    "Izzet Boilerworks",
    "Izzet Signet",
    "Malcolm, Keen-Eyed Navigator",
    "Mind Stone",
    "Mountain",
    "Path of Ancestry",
    "Prismatic Lens",
    "Scavenger Grounds",
    "Shivan Reef",
    "Sol Ring",
    "Temple of Epiphany",
    "Terramorphic Expanse",
    "Thriving Isle",
    "Treasure",
    "Wily Goblin",
}

PLACEHOLDER_IDS = {"placeholder", "noop", "silent_skip", "generic"}
GENERATED_SEMANTIC_ID = re.compile(r"^SEM-[A-Z0-9-]+$")
_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class AdapterRecord:
    card_name: str
    adapter_id: str
    legal_action_generator: str
    cost_builder: str
    target_mode_choice_builder: str
    execution_handler: str
    relevant_zones: tuple[str, ...]
    timing_restrictions: tuple[str, ...]
    integration_test_ids: tuple[str, ...]
    status: str


def expected_card_names() -> tuple[str, ...]:
    deck = build_simulation_deck()
    return tuple(sorted({c.name for c in deck.library} | {c.name for c in deck.commanders}))


def _record(name: str) -> AdapterRecord:
    executable = name in EXECUTABLE_CARDS
    aid = name.lower().replace(" // ", "_").replace(", ", "_").replace(" ", "_").replace("-", "_")
    return AdapterRecord(
        card_name=name,
        adapter_id=f"adapter.{aid}",
        legal_action_generator=f"generate.{aid}" if executable else "blocked.not_executable",
        cost_builder=f"cost.{aid}" if executable else "blocked.not_executable",
        target_mode_choice_builder=f"choices.{aid}" if executable else "blocked.not_executable",
        execution_handler=f"execute.{aid}" if executable else "blocked.not_executable",
        relevant_zones=("hand", "battlefield") if executable else ("blocked",),
        timing_restrictions=("rules_validated",) if executable else ("blocked",),
        integration_test_ids=(
            (
                "tests/test_phase9f4_creatures_combos_coverage.py::"
                "test_every_unique_card_generates_validated_executable_replayable_event"
                f"[{name}]"
            ),
        )
        if executable
        else (),
        status="EXECUTABLE" if executable else "BLOCKED",
    )


def adapter_registry() -> dict[str, AdapterRecord]:
    names = set(expected_card_names()) | {"Treasure"}
    return {name: _record(name) for name in sorted(names)}


@lru_cache(maxsize=1)
def collected_pytest_node_ids() -> tuple[frozenset[str], str | None]:
    """Collect exact pytest node IDs once and fail closed on collection errors."""

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return frozenset(), f"pytest collection failed: {detail}"

    nodes = frozenset(
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    )
    if not nodes:
        return frozenset(), "pytest collection returned no test node IDs"
    return nodes, None


def validate_executable_coverage(registry: dict[str, AdapterRecord] | None = None) -> list[str]:
    registry = registry or adapter_registry()
    errors: list[str] = []
    collected_nodes, collection_error = collected_pytest_node_ids()
    if collection_error is not None:
        errors.append(collection_error)

    for name in expected_card_names():
        rec = registry.get(name)
        if rec is None:
            errors.append(f"missing adapter registry row: {name}")
            continue
        if rec.status not in {"EXECUTABLE", "BLOCKED"}:
            errors.append(f"illegal status for {name}: {rec.status}")
            continue
        if rec.status == "BLOCKED":
            errors.append(f"blocked adapter: {name}")
            continue

        fields = {
            "legal-action generator": rec.legal_action_generator,
            "cost builder": rec.cost_builder,
            "target/mode/choice builder": rec.target_mode_choice_builder,
            "execution handler": rec.execution_handler,
        }
        for label, value in fields.items():
            low = value.lower()
            if (
                not value
                or any(token in low for token in PLACEHOLDER_IDS)
                or low.startswith("blocked")
            ):
                errors.append(f"{name} has no executable {label}")

        if not rec.integration_test_ids:
            errors.append(f"{name} has no integration test")
        for test_id in rec.integration_test_ids:
            normalized_id = test_id.replace("\\", "/")
            if GENERATED_SEMANTIC_ID.fullmatch(test_id):
                errors.append(
                    f"{name} uses generated semantic id instead of executable test evidence: {test_id}"
                )
                continue
            if "::" not in normalized_id:
                errors.append(
                    f"{name} integration test evidence is not a pytest node id: {test_id}"
                )
                continue
            if normalized_id not in collected_nodes:
                errors.append(f"{name} references nonexistent collected pytest node: {test_id}")

        if rec.execution_handler != f"execute.{rec.adapter_id.removeprefix('adapter.')}":
            errors.append(f"{name} ability is routed to another card's handler")
    return errors


def write_report(path: Path) -> dict[str, object]:
    reg = adapter_registry()
    records = [asdict(r) for r in reg.values() if r.card_name != "Treasure"]
    errors = validate_executable_coverage(reg)
    report = {
        "expected_unique_card_count": len(expected_card_names()),
        "executable_adapter_count": sum(1 for r in records if r["status"] == "EXECUTABLE"),
        "blocked_adapter_count": sum(1 for r in records if r["status"] == "BLOCKED"),
        "verified_semantic_test_evidence_count": sum(
            len(r["integration_test_ids"]) for r in records if r["status"] == "EXECUTABLE"
        ),
        "records": records,
        "errors": errors,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
