from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def write_workflow(root: Path, text: str) -> None:
    path = root / ".github/workflows/check.yml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "workflow", "extra"),
    [
        ("active", "run: uv run mtg-sim pilot --config configs/pilot.toml", {}),
        (
            "workflow-call",
            "uses: ./.github/workflows/reuse.yml",
            {".github/workflows/reuse.yml": "run: mtg-sim pilot --config configs/pilot.toml"},
        ),
        (
            "shell",
            "run: bash scripts/go.sh",
            {"scripts/go.sh": "mtg-sim pilot --config configs/pilot.toml"},
        ),
        (
            "python",
            "run: uv run python scripts/go.py",
            {"scripts/go.py": "# mtg-sim pilot --config configs/pilot.toml"},
        ),
        ("yaml-lines", "run: >\n  uv run mtg-sim pilot --config\n  configs/pilot.toml", {}),
        ("prefix", "run: poetry run mtg-sim pilot --config configs/pilot.toml", {}),
    ],
)
def test_pilot_lock_rejects_reachable_production_paths(
    tmp_path: Path, name: str, workflow: str, extra: dict[str, str]
) -> None:
    del name
    write_workflow(tmp_path, workflow)
    for relative, content in extra.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert run("check_production_pilot_lock.py", "--root", str(tmp_path)).returncode == 1


@pytest.mark.parametrize(
    "command",
    [
        "run: uv run mtg-sim pilot --config configs/pilot.toml --dry-run",
        "run: uv run mtg-sim validate-sources",
    ],
)
def test_pilot_lock_allows_negative_controls(tmp_path: Path, command: str) -> None:
    write_workflow(tmp_path, command)
    assert run("check_production_pilot_lock.py", "--root", str(tmp_path)).returncode == 0


def control_trees(tmp_path: Path) -> tuple[Path, Path]:
    referee, candidate = tmp_path / "referee", tmp_path / "candidate"
    frozen = (ROOT / "scripts/validate_phase_a_control_plane.py").read_text(encoding="utf-8")
    start = frozen.index("FROZEN = (") + len("FROZEN = (")
    end = frozen.index("\n)\n", start)
    relatives = [
        value for line in frozen[start:end].splitlines() if (value := line.strip().strip('",'))
    ]
    for relative in relatives:
        for tree in (referee, candidate):
            path = tree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
    return referee, candidate


@pytest.mark.parametrize("attack", ["modify", "delete", "replace", "symlink", "path-substitution"])
def test_immutable_referee_rejects_candidate_control_plane(tmp_path: Path, attack: str) -> None:
    referee, candidate = control_trees(tmp_path)
    target = candidate / "scripts/check_architecture_invariants.py"
    if attack == "modify":
        target.write_text("changed", encoding="utf-8")
    elif attack == "delete":
        target.unlink()
    elif attack == "replace":
        target.unlink()
        target.mkdir()
    elif attack == "symlink":
        target.unlink()
        target.symlink_to(candidate / "automation/architecture-invariants.json")
    else:
        target.unlink()
        (candidate / "scripts/check_architecture_invariants.py.txt").write_text("x")
    result = run(
        "validate_phase_a_control_plane.py",
        "--referee",
        str(referee),
        "--candidate",
        str(candidate),
        "--protected-main-sha",
        "base",
        "--candidate-sha",
        "head",
    )
    assert result.returncode == 1


def test_immutable_referee_clean_control() -> None:
    result = run(
        "validate_phase_a_control_plane.py",
        "--referee",
        str(ROOT),
        "--candidate",
        str(ROOT),
        "--protected-main-sha",
        "base",
        "--candidate-sha",
        "head",
    )
    assert result.returncode == 0


def test_closed_world_staging_excludes_candidate_escape_paths() -> None:
    text = (ROOT / "scripts/run_phase_a_reference_tests.py").read_text(encoding="utf-8")
    assert 'package in ("mtg_kernel", "mtg_cards")' in text
    assert "src/mtg_sim" not in text
    assert "tests/conftest.py" not in text
    assert "symlinks=False" in text


def test_runtime_guard_rejects_static_and_dynamic_imports(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "guard", ROOT / "scripts/phase_a_runtime_guard.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    guard = module.PhaseAImportGuard()
    with pytest.raises(ImportError):
        guard.find_spec("mtg_sim.engine")
    assert guard.find_spec("json") is None


def test_runtime_guard_rejects_prepopulated_legacy_module() -> None:
    program = (
        "import runpy,sys,types; from pathlib import Path; "
        "sys.modules['mtg_sim.engine']=types.ModuleType('mtg_sim.engine'); "
        "runpy.run_path('scripts/phase_a_runtime_guard.py')['install'](Path('.'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode != 0
    assert "mtg_sim was present" in result.stderr


@pytest.mark.parametrize("loader", ["spec-loader", "runpy"])
def test_runtime_provenance_rejects_modules_loaded_outside_stage(
    tmp_path: Path, loader: str
) -> None:
    del loader
    spec = importlib.util.spec_from_file_location(
        "guard", ROOT / "scripts/phase_a_runtime_guard.py"
    )
    assert spec and spec.loader
    guard_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_module)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    candidate_spec = importlib.util.spec_from_file_location("mtg_kernel.escape", outside)
    assert candidate_spec and candidate_spec.loader
    candidate = importlib.util.module_from_spec(candidate_spec)
    candidate_spec.loader.exec_module(candidate)
    sys.modules["mtg_kernel.escape"] = candidate
    try:
        with pytest.raises(RuntimeError, match="unapproved module provenance"):
            guard_module.verify_loaded(tmp_path / "stage")
    finally:
        sys.modules.pop("mtg_kernel.escape", None)


def test_liveness_rejects_disconnected_facade(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"receipts": [], "referee_observations": {}}))
    assert run("check_kernel_liveness.py", str(trace)).returncode == 1


def test_attack_matrix_families_are_nonempty() -> None:
    data = json.loads((ROOT / "automation/architecture-attack-matrix.json").read_text())
    assert len(data["families"]) >= 7
    assert all(data["families"].values())
