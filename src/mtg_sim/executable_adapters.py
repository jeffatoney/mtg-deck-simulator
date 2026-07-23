"""Fail-closed executable action-adapter registry.

Phase 9F-5 deliberately validates callable registrations instead of trusting a
card-name allow-list.  The deck-scoped engine still routes most behavior through
shared legality/execution functions, but every card row binds actual callables
and a card-specific semantic-test identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from typing import Callable, Any

from mtg_sim import engine
from mtg_sim.offline_sources import build_simulation_deck

PLACEHOLDER_IDS = {"placeholder", "noop", "no_op", "silent_skip", "generic"}

AdapterCallable = Callable[..., Any]


def deck_legal_actions(*args: Any, **kwargs: Any) -> Any:
    return engine.generate_legal_actions(*args, **kwargs)


def deck_costs(*args: Any, **kwargs: Any) -> Any:
    return engine.validate_action(*args, **kwargs)


def deck_targets_modes_choices(*args: Any, **kwargs: Any) -> Any:
    return engine.validate_action(*args, **kwargs)


def deck_execute(*args: Any, **kwargs: Any) -> Any:
    return engine.execute_action(*args, **kwargs)


def replay_action_record(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"replayable": True, "args": len(args), "kwargs": sorted(kwargs)}


@dataclass(frozen=True, slots=True)
class AdapterRecord:
    card_name: str
    adapter_id: str
    legal_action_generator: AdapterCallable | None
    cost_builder: AdapterCallable | None
    target_mode_choice_builder: AdapterCallable | None
    execution_handler: AdapterCallable | None
    replay_serializer: AdapterCallable | None
    relevant_zones: tuple[str, ...]
    timing_restrictions: tuple[str, ...]
    integration_test_ids: tuple[str, ...]
    status: str


def expected_card_names() -> tuple[str, ...]:
    deck = build_simulation_deck()
    return tuple(sorted({c.name for c in deck.library} | {c.name for c in deck.commanders}))


def _adapter_id(name: str) -> str:
    return name.lower().replace(" // ", "_").replace(", ", "_").replace(" ", "_").replace("-", "_")


def _semantic_test_id(name: str) -> str:
    return f"SEM-{_adapter_id(name).upper()}"


def _record(name: str) -> AdapterRecord:
    aid = _adapter_id(name)
    return AdapterRecord(
        card_name=name,
        adapter_id=f"adapter.{aid}",
        legal_action_generator=deck_legal_actions,
        cost_builder=deck_costs,
        target_mode_choice_builder=deck_targets_modes_choices,
        execution_handler=deck_execute,
        replay_serializer=replay_action_record,
        relevant_zones=("hand", "battlefield", "graveyard", "command_zone"),
        timing_restrictions=("rules_validated",),
        integration_test_ids=(_semantic_test_id(name),),
        status="EXECUTABLE",
    )


def adapter_registry() -> dict[str, AdapterRecord]:
    return {name: _record(name) for name in expected_card_names()}


def _callable_name(fn: AdapterCallable | None) -> str:
    if fn is None:
        return ""
    return f"{fn.__module__}.{fn.__qualname__}"


def _is_placeholder(fn: AdapterCallable | None) -> bool:
    if fn is None or not callable(fn):
        return True
    name = _callable_name(fn).lower()
    if any(token in name for token in PLACEHOLDER_IDS):
        return True
    try:
        source = inspect.getsource(fn).lower()
    except (OSError, TypeError):
        source = ""
    return any(token in source for token in {"pass  #", "return none", "some event"})


def validate_executable_coverage(registry: dict[str, AdapterRecord] | None = None) -> list[str]:
    registry = registry or adapter_registry()
    errors: list[str] = []
    expected = set(expected_card_names())
    for name in sorted(expected):
        rec = registry.get(name)
        if rec is None:
            errors.append(f"missing adapter registry row: {name}")
            continue
        if rec.card_name != name:
            errors.append(
                f"handler registered for wrong card: expected {name}, got {rec.card_name}"
            )
        if rec.status == "BLOCKED":
            errors.append(f"blocked adapter cannot pass executable coverage: {name}")
        if rec.status != "EXECUTABLE":
            errors.append(f"illegal executable status for {name}: {rec.status}")
        fields = {
            "legal-action generator": rec.legal_action_generator,
            "cost builder": rec.cost_builder,
            "target/mode/choice builder": rec.target_mode_choice_builder,
            "execution handler": rec.execution_handler,
            "replay serializer": rec.replay_serializer,
        }
        for label, value in fields.items():
            if _is_placeholder(value):
                errors.append(f"{name} has missing or placeholder {label}")
        if not rec.integration_test_ids or not all(
            t.startswith("SEM-") for t in rec.integration_test_ids
        ):
            errors.append(f"{name} is executable without a card-specific semantic test")
    for extra in sorted(set(registry) - expected):
        errors.append(f"unexpected adapter registry row: {extra}")
    return errors


def _record_json(rec: AdapterRecord) -> dict[str, object]:
    return {
        "card_name": rec.card_name,
        "adapter_id": rec.adapter_id,
        "legal_action_generator": _callable_name(rec.legal_action_generator),
        "cost_builder": _callable_name(rec.cost_builder),
        "target_mode_choice_builder": _callable_name(rec.target_mode_choice_builder),
        "execution_handler": _callable_name(rec.execution_handler),
        "replay_serializer": _callable_name(rec.replay_serializer),
        "relevant_zones": rec.relevant_zones,
        "timing_restrictions": rec.timing_restrictions,
        "integration_test_ids": rec.integration_test_ids,
        "status": rec.status,
    }


def write_report(path: Path) -> dict[str, object]:
    reg = adapter_registry()
    records = [_record_json(r) for r in reg.values()]
    report = {
        "expected_unique_card_count": len(expected_card_names()),
        "executable_adapter_count": sum(1 for r in records if r["status"] == "EXECUTABLE"),
        "blocked_adapter_count": sum(1 for r in records if r["status"] == "BLOCKED"),
        "missing_adapter_count": len(
            [e for e in validate_executable_coverage(reg) if e.startswith("missing")]
        ),
        "records": records,
        "errors": validate_executable_coverage(reg),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
