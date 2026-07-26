from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


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
        "allowed_zone_initializers": {"src/mtg_kernel/state.py": ["__init__"]},
        "kernel_paths": ["src/mtg_kernel/"],
        "test_paths": ["tests/phase_a_acceptance/"],
        "zone_attributes": ["battlefield", "hand", "library", "graveyard", "exile"],
        "protected_zone_container_attributes": ["zones", "_zones"],
        "state_reference_names": ["state", "game_state"],
        "phase_attributes": ["phase", "step"],
        "terminal_attributes": ["won", "lost", "game_over", "terminal_status"],
        "forbidden_import_prefixes": ["mtg_sim"],
        "forbidden_dynamic_import_modules": ["importlib", "builtins"],
        "forbidden_patch_target_tokens": [
            "mtg_kernel",
            "gameexecutor",
            "turnengine",
            "zoneservice",
            "stackservice",
            "triggerengine",
            "replay",
        ],
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


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('mtg_sim.engine')\n",
        "__import__('mtg_sim.engine')\n",
        "import importlib as il\nil.import_module('mtg_sim.engine')\n",
        "from importlib import import_module\nimport_module('mtg_sim.engine')\n",
        "import importlib\nmodule_name = 'json'\nimportlib.import_module(module_name)\n",
    ],
    ids=[
        "importlib-literal",
        "builtin-import",
        "aliased-importlib",
        "from-import-helper",
        "nonliteral-module",
    ],
)
def test_architecture_gate_rejects_dynamic_legacy_imports(tmp_path: Path, source: str) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, source)
    assert result.returncode == 1
    assert "LEGACY_DYNAMIC_IMPORT" in result.stdout


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


@pytest.mark.parametrize(
    "source",
    [
        "def bad(state, card):\n    state.zones[Zone.HAND].append(card)\n",
        "def bad(state, card):\n    state.zones[Zone.HAND] = [card]\n",
        "def bad(state):\n    del state.zones[Zone.HAND]\n",
        "def bad(state, card):\n    zones = state.zones\n    zones[Zone.HAND].append(card)\n",
        "def bad(state, card):\n    state._zones[Zone.LIBRARY].insert(0, card)\n",
    ],
    ids=[
        "method-mutation",
        "item-assignment",
        "item-deletion",
        "mapping-alias",
        "private-container",
    ],
)
def test_architecture_gate_rejects_protected_zone_container_access(
    tmp_path: Path, source: str
) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, source)
    assert result.returncode == 1
    assert "ZONE_CONTAINER_ACCESS" in result.stdout


def test_architecture_gate_allows_ordinary_local_zones_dictionary(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, "def okay():\n    zones = {}\n    return zones\n")
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_limits_state_zone_initialization(tmp_path: Path) -> None:
    _fixture(tmp_path)
    state = tmp_path / "src/mtg_kernel/state.py"
    state.write_text(
        "class GameState:\n"
        "    def __init__(self):\n        self._zones = {}\n"
        "    def cheat(self, card):\n        self._zones['hand'].append(card)\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "ZONE_CONTAINER_ACCESS" in result.stdout


@pytest.mark.parametrize(
    "source",
    [
        "def bad(log):\n    log.record_event('trigger_put_on_stack')\n",
        "def bad(log):\n    log.record_event(event_type='trigger_put_on_stack')\n",
        "def bad(log):\n    log.record_event(event='trigger_put_on_stack')\n",
        "def bad(log):\n    log.record_event(name='trigger_put_on_stack')\n",
        "def bad(log, event_type):\n    log.record_event(event_type=event_type)\n",
    ],
    ids=["positional", "event-type-keyword", "event-keyword", "name-keyword", "nonliteral"],
)
def test_architecture_gate_rejects_protected_trigger_event_forms(
    tmp_path: Path, source: str
) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, source)
    assert result.returncode == 1
    assert "FAKE_TRIGGER_EVENT" in result.stdout


def test_architecture_gate_allows_stack_service_trigger_emission(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "src/mtg_kernel/stack.py"
    path.write_text(
        "def push(state, obj, log):\n"
        "    trigger = TriggeredAbilityObject(obj)\n"
        "    state.stack.append(trigger)\n"
        "    log.record_event(event_type='trigger_put_on_stack')\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_gate_rejects_stack_service_event_without_real_trigger(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "src/mtg_kernel/stack.py"
    path.write_text(
        "def fake(state, log):\n"
        "    state.stack.append(object())\n"
        "    log.record_event(event_type='trigger_put_on_stack')\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
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


@pytest.mark.parametrize(
    "source",
    [
        "def test_patch(monkeypatch, replacement):\n"
        "    monkeypatch.setattr('mtg_kernel.executor.GameExecutor.run', replacement)\n",
        "from unittest import mock\n\n"
        "def test_patch():\n"
        "    mock.patch('mtg_kernel.turns.TurnEngine.cleanup')\n",
        "from unittest.mock import patch as p\n"
        "from mtg_kernel.executor import GameExecutor as Executor\n\n"
        "def test_patch(replacement):\n"
        "    p.object(Executor, 'run', replacement)\n",
        "from unittest.mock import patch\n\n"
        "def test_patch(target, replacement):\n"
        "    patch(target, replacement)\n",
    ],
    ids=[
        "monkeypatch-string-target",
        "mock-patch-target",
        "aliased-patch-object",
        "nonliteral-patch-target",
    ],
)
def test_architecture_gate_rejects_kernel_patching(tmp_path: Path, source: str) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "FORBIDDEN_TEST_PATCH" in result.stdout


@pytest.mark.parametrize(
    "source",
    [
        "def test_patch(monkeypatch, executor, replacement):\n"
        "    patcher = monkeypatch\n    patcher.setattr(executor, 'run', replacement)\n",
        "from unittest import mock\nfirst = mock.patch\n"
        "def test_patch():\n    first('mtg_kernel.stack.StackService.push')\n",
        "from unittest.mock import patch\nhelper = patch\n"
        "def test_patch(replacement):\n    helper.object(GameExecutor, 'run', replacement)\n",
        "def test_patch(mocker):\n    helper = mocker.patch\n"
        "    helper('mtg_kernel.turns.TurnEngine.cleanup')\n",
        "from unittest import mock\nfirst = mock.patch\nsecond = first\n"
        "def test_patch():\n    second('mtg_kernel.replay.ReplayEngine.run')\n",
        "from unittest.mock import patch\nhelper = patch\n"
        "def test_patch(target):\n    helper(target)\n",
        "from unittest import mock\n"
        "def test_patch(condition):\n"
        "    helper = mock.patch if condition else mock.patch.object\n"
        "    helper('mtg_kernel.triggers.TriggerEngine.run')\n",
    ],
    ids=[
        "monkeypatch-object-alias",
        "mock-patch-helper-alias",
        "patch-object-helper-alias",
        "mocker-patch-alias",
        "transitive-helper-alias",
        "nonliteral-target",
        "unresolved-patch-capable-callee",
    ],
)
def test_architecture_gate_rejects_assignment_aliased_patch_helpers(
    tmp_path: Path, source: str
) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "FORBIDDEN_TEST_PATCH" in result.stdout


def test_architecture_gate_allows_clean_acceptance_test(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    source = (
        "def test_clean():\n"
        "    message = 'mtg_kernel.executor.GameExecutor.run'\n"
        "    assert message.startswith('mtg_kernel')\n"
    )
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "from mtg_kernel.executor import GameExecutor\nGameExecutor.run = fake_run\n",
        "from mtg_kernel.executor import GameExecutor\nGameExecutor.run: object = fake_run\n",
        "from mtg_kernel.executor import GameExecutor\nGameExecutor.run += wrapper\n",
        "from mtg_kernel.executor import GameExecutor\ndel GameExecutor.run\n",
        "from mtg_kernel.triggers import TriggerEngine as Engine\n"
        "alias = Engine\nsecond = alias\nsecond.emit = fake_emit\n",
    ],
    ids=[
        "direct-assignment",
        "annotated-assignment",
        "augmented-assignment",
        "deletion",
        "transitive-object-alias",
    ],
)
def test_architecture_gate_rejects_direct_kernel_member_replacement(
    tmp_path: Path, source: str
) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "FORBIDDEN_TEST_REPLACEMENT" in result.stdout


@pytest.mark.parametrize(
    "source",
    [
        "import sys\nsys.modules['mtg_kernel.executor'] = fake_module\n",
        "import sys\nsys.modules.update({'mtg_kernel.executor': fake_module})\n",
        "import sys\nsys.modules.setdefault('mtg_sim.engine', fake_module)\n",
        "import sys\ndel sys.modules['mtg_sim.engine']\n",
    ],
    ids=["assignment", "update", "setdefault-legacy", "deletion-legacy"],
)
def test_architecture_gate_rejects_protected_module_injection(tmp_path: Path, source: str) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "FORBIDDEN_MODULE_REPLACEMENT" in result.stdout


@pytest.mark.parametrize(
    "source",
    [
        "def test_fake(helper):\n    helper('mtg_kernel.executor.GameExecutor.run')\n",
        "def test_fake(helper):\n    helper(target='mtg_kernel.turns.TurnEngine.cleanup')\n",
        "def test_fake(helper):\n"
        "    first = helper\n    second = first\n"
        "    second('mtg_kernel.replay.Replay.run')\n",
    ],
    ids=["unknown-positional", "unknown-keyword", "transitive-unknown-alias"],
)
def test_architecture_gate_rejects_unresolved_protected_target_calls(
    tmp_path: Path, source: str
) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "UNRESOLVED_PROTECTED_TARGET" in result.stdout


def test_architecture_gate_allows_local_object_assignment(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "class Fixture:\n    pass\n\nfixture = Fixture()\nfixture.run = fake_run\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "exec('import mtg_sim.engine')\n",
        "eval(\"__import__('mtg_sim.engine')\")\n",
        "compile('import mtg_sim.engine', '<string>', 'exec')\n",
        "from builtins import exec as runner\nrunner('pass')\n",
        "runner = exec\nrunner('pass')\n",
        "first = eval\nsecond = first\nsecond('1 + 1')\n",
        "def bad(condition):\n    runner = exec if condition else compile\n    runner('pass')\n",
    ],
    ids=[
        "direct-exec",
        "direct-eval",
        "direct-compile",
        "builtins-alias",
        "assignment-alias",
        "transitive-alias",
        "unresolved-alias",
    ],
)
def test_architecture_gate_rejects_dynamic_code_execution(tmp_path: Path, source: str) -> None:
    _fixture(tmp_path)
    result = _write(tmp_path, source)
    assert result.returncode == 1
    assert "DYNAMIC_CODE_EXECUTION" in result.stdout


def test_architecture_gate_rejects_dynamic_code_execution_in_test_paths(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "tests/phase_a_acceptance/test_gate.py"
    path.parent.mkdir(parents=True)
    path.write_text("runner = exec\nrunner('pass')\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "DYNAMIC_CODE_EXECUTION" in result.stdout
