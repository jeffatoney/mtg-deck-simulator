from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_architecture_invariants.py"


def _config(root: Path) -> None:
    config = {
        "enforced_paths": ["src/mtg_kernel/", "src/mtg_cards/"],
        "required_paths": [
            "src/mtg_kernel/zones.py",
            "src/mtg_kernel/stack.py",
            "src/mtg_kernel/turns.py",
            "src/mtg_kernel/state_based_actions.py",
            "src/mtg_cards/vertical_slice.py",
        ],
        "allowed_zone_mutation_files": ["src/mtg_kernel/zones.py"],
        "allowed_stack_mutation_files": ["src/mtg_kernel/stack.py"],
        "allowed_phase_assignment_files": ["src/mtg_kernel/turns.py"],
        "allowed_terminal_assignment_files": ["src/mtg_kernel/state_based_actions.py"],
        "allowed_trigger_stack_event_files": ["src/mtg_kernel/stack.py"],
        "kernel_paths": ["src/mtg_kernel/"],
        "test_paths": ["tests/phase_a_acceptance/"],
        "zone_attributes": ["battlefield", "hand", "library", "graveyard", "exile"],
        "zone_mutator_methods": ["append", "insert", "extend", "remove", "pop", "clear"],
        "stack_mutator_methods": ["append", "insert", "extend", "remove", "pop", "clear"],
        "phase_attributes": ["phase", "step"],
        "terminal_attributes": ["won", "lost", "game_over", "terminal_status"],
        "forbidden_import_prefixes": ["mtg_sim.engine", "mtg_sim.phase"],
        "forbidden_patch_target_tokens": ["engine", "kernel"],
        "prohibited_kernel_card_names": ["Sol Ring"],
        "forbid_skipped_or_xfailed_tests": True,
        "exempt_files": [],
    }
    path = root / "automation" / "architecture-invariants.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(config), encoding="utf-8")


def _required_files(root: Path) -> None:
    files = {
        "src/mtg_kernel/zones.py": "def move(state, card):\n    state.hand.append(card)\n",
        "src/mtg_kernel/stack.py": "def push(state, obj):\n    state.stack.append(obj)\n",
        "src/mtg_kernel/turns.py": "def advance(state):\n    state.phase = 'main'\n",
        "src/mtg_kernel/state_based_actions.py": "def finish(state):\n    state.won = True\n",
        "src/mtg_cards/vertical_slice.py": "CARD_NAME = 'Sol Ring'\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_architecture_gate_accepts_mutation_only_in_authorized_services(tmp_path: Path) -> None:
    _config(tmp_path)
    _required_files(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_rejects_zone_mutation_outside_zone_service(tmp_path: Path) -> None:
    _config(tmp_path)
    _required_files(tmp_path)
    path = tmp_path / "src/mtg_kernel/executor.py"
    path.write_text("def bad(state, card):\n    state.library.append(card)\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ZONE_MUTATION" in result.stdout


def test_architecture_gate_rejects_legacy_import_and_card_name_in_kernel(tmp_path: Path) -> None:
    _config(tmp_path)
    _required_files(tmp_path)
    path = tmp_path / "src/mtg_kernel/executor.py"
    path.write_text("from mtg_sim.engine import GameState\nNAME = 'Sol Ring'\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "LEGACY_IMPORT" in result.stdout
    assert "CARD_NAME_IN_KERNEL" in result.stdout


def test_architecture_gate_rejects_skipped_or_xfailed_acceptance_tests(tmp_path: Path) -> None:
    _config(tmp_path)
    _required_files(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "import pytest\n\n@pytest.mark.xfail\ndef test_A1_placeholder():\n    assert False\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "SKIPPED_TEST" in result.stdout
