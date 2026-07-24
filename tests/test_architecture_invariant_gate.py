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
        "phase_attributes": ["phase", "step"],
        "terminal_attributes": ["won", "lost", "game_over", "terminal_status"],
        "forbidden_import_prefixes": ["mtg_sim"],
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


def _write(root: Path, content: str) -> subprocess.CompletedProcess[str]:
    path = root / "src/mtg_kernel/executor.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _run(root)


def _fixture(tmp_path: Path) -> None:
    _config(tmp_path)
    _required_files(tmp_path)


def test_architecture_gate_accepts_authorized_services(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_rejects_zone_access_and_alias_origin(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def bad(state, card):\n    cards = state.hand\n    cards.append(card)\n",
    )
    assert result.returncode == 1
    assert "ZONE_ACCESS" in result.stdout


def test_architecture_gate_rejects_stack_access(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, "def bad(state):\n    return state.stack\n")
    assert result.returncode == 1
    assert "STACK_ACCESS" in result.stdout


def test_architecture_gate_allows_unrelated_local_names(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def okay():\n"
        "    library = []\n"
        "    stack = []\n"
        "    phase = 'main'\n"
        "    step = 'draw'\n"
        "    won = False\n"
        "    return library, stack, phase, step, won\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_rejects_protected_assignments(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def bad(state):\n"
        "    state.library = []\n"
        "    state.stack = []\n"
        "    state.phase = 'main'\n"
        "    state.won = True\n",
    )
    assert result.returncode == 1
    assert "ZONE_ACCESS" in result.stdout
    assert "STACK_ACCESS" in result.stdout
    assert "PHASE_ASSIGNMENT" in result.stdout
    assert "TERMINAL_ASSIGNMENT" in result.stdout


def test_architecture_gate_rejects_all_reflective_mutation_forms(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def bad(state, field, value):\n"
        "    alias = state\n"
        "    setattr(alias, 'library', value)\n"
        "    alias.__setattr__('phase', value)\n"
        "    object.__setattr__(state, 'stack', value)\n"
        "    setattr(state, field, value)\n",
    )
    assert result.returncode == 1
    assert result.stdout.count("REFLECTIVE_MUTATION") >= 4


def test_architecture_gate_rejects_reflective_access(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def bad(state, field):\n"
        "    first = getattr(state, 'hand')\n"
        "    second = getattr(state, field)\n"
        "    third = vars(state)\n"
        "    return first, second, third\n",
    )
    assert result.returncode == 1
    assert "ZONE_ACCESS" in result.stdout
    assert "DYNAMIC_REFLECTION" in result.stdout
    assert "STATE_REFLECTION" in result.stdout


def test_architecture_gate_rejects_legacy_import_aliases(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "from mtg_sim import engine as legacy_engine\nfrom mtg_sim import pilot\n",
    )
    assert result.returncode == 1
    assert result.stdout.count("LEGACY_IMPORT") >= 2


def test_architecture_gate_rejects_card_name_in_kernel(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, "NAME = 'Sol Ring'\n")
    assert result.returncode == 1
    assert "CARD_NAME_IN_KERNEL" in result.stdout


def test_architecture_gate_rejects_fake_trigger_event(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(
        tmp_path,
        "def bad(log):\n    log.record_event('trigger_put_on_stack')\n",
    )
    assert result.returncode == 1
    assert "FAKE_TRIGGER_EVENT" in result.stdout


def test_architecture_gate_rejects_aliased_test_suppression(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "import pytest as pt\n"
        "from pytest import mark as m\n\n"
        "@pt.mark.xfail\n"
        "def test_A1():\n    assert False\n\n"
        "@m.skip\n"
        "def test_A2():\n    assert False\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("SKIPPED_TEST") >= 2


def test_architecture_gate_rejects_dynamic_or_star_test_suppression(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from pytest import *\nimport pytest\nmarker = getattr(pytest.mark, 'xfail')\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "SKIPPED_TEST" in result.stdout
