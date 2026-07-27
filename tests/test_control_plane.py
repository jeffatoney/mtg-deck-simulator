from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECOVERY_BRANCH = "recovery/phase-a-rules-kernel"


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


def workflow_job_condition(path: str, job: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(
        rf"^  {re.escape(job)}:\n(?:.*\n)*?    if: >-\n(?P<condition>(?:      .*\n)+)",
        text,
        flags=re.MULTILINE,
    )
    assert match, f"missing condition for {job} in {path}"
    return " ".join(line.strip() for line in match.group("condition").splitlines())


def lifecycle_allows(*, event: str, base: str, head: str) -> bool:
    return event == "pull_request" and base == "main" and head == RECOVERY_BRANCH


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ("recovery/phase-a-setup", False),
        (RECOVERY_BRANCH, True),
        ("feature/unrelated", False),
    ],
)
def test_isolated_reference_suite_branch_lifecycle(head: str, expected: bool) -> None:
    condition = workflow_job_condition(
        ".github/workflows/phase-a-isolated-acceptance.yml", "isolated-reference-suite"
    )
    assert "github.event_name == 'pull_request'" in condition
    assert "github.event.pull_request.base.ref == 'main'" in condition
    assert f"github.event.pull_request.head.ref == '{RECOVERY_BRANCH}'" in condition
    assert lifecycle_allows(event="pull_request", base="main", head=head) is expected


def test_recovery_control_plane_jobs_freeze_exact_branch_lifecycle() -> None:
    workflows = [
        (".github/workflows/architecture-gate.yml", "invariants", "pull_request"),
        (
            ".github/workflows/architecture-referee.yml",
            "immutable-referee",
            "pull_request_target",
        ),
    ]
    for path, job, event in workflows:
        condition = workflow_job_condition(path, job)
        assert f"github.event_name == '{event}'" in condition
        assert "github.event.pull_request.base.ref == 'main'" in condition
        assert f"github.event.pull_request.head.ref == '{RECOVERY_BRANCH}'" in condition
        assert "recovery/phase-a-setup" not in condition


def test_isolated_reference_suite_uses_only_protected_main_runner() -> None:
    text = (ROOT / ".github/workflows/phase-a-isolated-acceptance.yml").read_text(encoding="utf-8")
    assert "ref: main\n          path: referee" in text
    assert "python referee/scripts/run_phase_a_reference_tests.py" in text
    assert "candidate/scripts/run_phase_a_reference_tests.py" not in text


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
            {
                "scripts/go.py": 'import subprocess\nsubprocess.run(["mtg-sim", "pilot", "--config", "configs/pilot.toml"])\n'
            },
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


def test_immutable_referee_freezes_acceptance_workflow_lifecycle(tmp_path: Path) -> None:
    referee, candidate = control_trees(tmp_path)
    relative = ".github/workflows/phase-a-isolated-acceptance.yml"
    frozen_workflow = (ROOT / relative).read_text(encoding="utf-8")
    (referee / relative).write_text(frozen_workflow, encoding="utf-8")
    workflow_path = candidate / ".github/workflows/phase-a-isolated-acceptance.yml"
    assert workflow_path.is_file()
    workflow_path.write_text(
        frozen_workflow.replace("recovery/phase-a-rules-kernel", "recovery/phase-a-setup"),
        encoding="utf-8",
    )
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


def test_control_plane_bootstrap_positive_path(tmp_path: Path) -> None:
    referee = tmp_path / "referee"
    candidate = tmp_path / "candidate"
    output = tmp_path / "artifacts"
    for relative in ("scripts/run_phase_a_reference_tests.py", "scripts/phase_a_runtime_guard.py"):
        target = referee / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    reference = referee / "tests/phase_a_acceptance"
    reference.mkdir(parents=True)
    reference.joinpath("test_bootstrap.py").write_text(
        "import dataclasses, enum, json, pathlib, sys, typing, pytest\n"
        "def test_protected_runner_bootstrap():\n"
        "    from mtg_kernel.executor import GameExecutor\n"
        "    import mtg_cards\n"
        "    assert GameExecutor().run() == 'live'\n"
        "    assert 'mtg_sim' not in sys.modules\n",
        encoding="utf-8",
    )
    executor = candidate / "src/mtg_kernel/executor.py"
    executor.parent.mkdir(parents=True)
    executor.write_text("class GameExecutor:\n    def run(self): return 'live'\n", encoding="utf-8")
    cards = candidate / "src/mtg_cards/__init__.py"
    cards.parent.mkdir(parents=True)
    cards.write_text("CARD = 'approved'\n", encoding="utf-8")
    excluded = [
        "src/mtg_sim/engine.py",
        "src/escape/helper.py",
        "tests/test_fake.py",
        "tests/conftest.py",
        "helpers.py",
        ".github/workflows/evil.yml",
        "scripts/evil.py",
    ]
    for relative in excluded:
        path = candidate / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("raise RuntimeError('candidate escape loaded')\n", encoding="utf-8")
    sha = "0123456789abcdef0123456789abcdef01234567"
    result = subprocess.run(
        [
            sys.executable,
            str(referee / "scripts/run_phase_a_reference_tests.py"),
            "--candidate",
            str(candidate),
            "--referee",
            str(referee),
            "--candidate-sha",
            sha,
            "--output",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    runs = list(output.iterdir())
    assert len(runs) == 1
    manifest = json.loads((runs[0] / "manifest.json").read_text())
    assert manifest["candidate_sha"] == sha
    assert manifest["run_id"] == runs[0].name
    assert manifest["collected_node_ids"] == [
        "tests/phase_a_acceptance/test_bootstrap.py::test_protected_runner_bootstrap"
    ]
    assert (runs[0] / "pytest.log").is_file()
    assert (runs[0] / "collection.log").is_file()
    staged = manifest["staged_files"]
    assert "src/mtg_kernel/executor.py" in staged and "src/mtg_cards/__init__.py" in staged
    assert all(
        not any(
            token in path for token in ("mtg_sim", "evil", "conftest", "helpers.py", "test_fake")
        )
        for path in staged
    )


def test_runtime_guard_preserves_standard_library_and_pytest(tmp_path: Path) -> None:
    program = (
        "from pathlib import Path; import runpy; "
        f"g=runpy.run_path({str(ROOT / 'scripts/phase_a_runtime_guard.py')!r}); "
        "g['install'](Path('.')); "
        "import dataclasses,enum,json,pathlib,typing,pytest; print('imports-ok')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imports-ok"


def test_runtime_guard_rejects_legacy_after_install(tmp_path: Path) -> None:
    program = (
        "from pathlib import Path; import runpy; "
        f"g=runpy.run_path({str(ROOT / 'scripts/phase_a_runtime_guard.py')!r}); "
        "g['install'](Path('.')); import mtg_sim.engine"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Phase A closed world rejects mtg_sim" in result.stderr


@pytest.mark.parametrize(
    "workflow,extra",
    [
        ("run: uv run mtg-sim pilot --config configs/pilot.toml # --dry-run", {}),
        ("run: uv run mtg-sim pilot --config configs/pilot.toml ; echo --dry-run", {}),
        ("run: echo --dry-run; uv run mtg-sim pilot --config configs/pilot.toml", {}),
        ("run: >\n  uv run mtg-sim pilot --config\n  configs/pilot.toml", {}),
        ("run: bash scripts/go.sh", {"scripts/go.sh": "mtg-sim pilot --config configs/pilot.toml"}),
        (
            "run: python scripts/go.py",
            {
                "scripts/go.py": "import subprocess\nsubprocess.run(['mtg-sim','pilot','--config','configs/pilot.toml'])\n"
            },
        ),
        ("run: uv run mtg-sim pilot --config configs/pilot.toml --dry-run", {}),
    ],
)
def test_pilot_lock_has_no_phase_ab_dry_run_exception(
    tmp_path: Path, workflow: str, extra: dict[str, str]
) -> None:
    write_workflow(tmp_path, workflow)
    for relative, content in extra.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert run("check_production_pilot_lock.py", "--root", str(tmp_path)).returncode == 1


def test_pilot_lock_ignores_comments_and_unrelated_commands(tmp_path: Path) -> None:
    write_workflow(tmp_path, "run: echo unrelated # mtg-sim pilot --config configs/pilot.toml")
    assert run("check_production_pilot_lock.py", "--root", str(tmp_path)).returncode == 0


def test_malicious_all_claims_facade_is_rejected() -> None:
    from tests.phase_a_acceptance.reference_adapter import REQUIRED_SERVICES, validate_raw_artifact

    facade = {
        "satisfied_acceptance_ids": [
            f"{group}{number}" for group in "ABCDEFG" for number in range(1, 10)
        ],
        "postconditions": {"everything": True},
        "trace_invariants": {"everything": True},
        "referee_observations": {
            "call_trees": True,
            "state_transitions": True,
            "receipt_correlations": True,
        },
        "receipts": [{"service": name} for name in REQUIRED_SERVICES],
        "replay": json.loads((ROOT / "tests/fixtures/golden-replays/sol-ring.json").read_text()),
    }
    with pytest.raises(AssertionError):
        validate_raw_artifact(facade, {"initial_state": {}})


@pytest.mark.parametrize(
    "mode", ["setup-probe", "disconnected-kernel", "receipts-only", "no-transition"]
)
def test_referee_liveness_rejects_disconnected_evidence(mode: str) -> None:
    from scripts.check_kernel_liveness import validate

    data = {
        "events": [],
        "receipts": [
            {
                "service": "ZoneService",
                "action_id": "a",
                "pre_state_hash": "x",
                "post_state_hash": "x",
            }
        ],
        "_referee_calls": [
            {
                "order": 1,
                "kind": "call",
                "module": "mtg_kernel.executor",
                "qualname": "GameExecutor.run",
            },
            {
                "order": 2,
                "kind": "return",
                "module": "mtg_kernel.executor",
                "qualname": "GameExecutor.run",
            },
            {
                "order": 3,
                "kind": "call",
                "module": "mtg_kernel.zones",
                "qualname": "ZoneService.move",
                "action_id": "a",
            },
        ],
    }
    assert validate(data), mode


@pytest.mark.parametrize(
    "defect",
    ["empty-events", "empty-decisions", "missing-field", "duplicate-id", "strategic-label"],
)
def test_analytics_referee_rejects_invalid_artifacts(defect: str) -> None:
    from tests.phase_a_acceptance.reference_adapter import _validate_analytics

    event = {
        "schema_version": 1,
        "run_id": "r",
        "game_id": "g",
        "event_id": "e",
        "sequence": 1,
        "turn": 1,
        "phase": "main",
        "step": "main",
        "priority_window_id": "p",
        "actor": "p1",
        "event_type": "pass",
        "source_object_ids": [],
        "target_object_ids": [],
        "parent_action_id": None,
        "parent_event_id": None,
        "pre_state_hash": "a",
        "post_state_hash": "b",
        "payload": {},
    }
    decision = {
        "decision_id": "d",
        "observation_hash": "o",
        "legal_actions": [{"action_id": "pass"}],
        "selected_action_id": "pass",
        "policy_id": "p",
        "policy_version": "1",
        "action_set_hash": "h",
        "future_information_used": False,
    }
    artifact = {"events": [event], "decisions": [decision]}
    if defect == "empty-events":
        artifact["events"] = []
    elif defect == "empty-decisions":
        artifact["decisions"] = []
    elif defect == "missing-field":
        del event["pre_state_hash"]
    elif defect == "duplicate-id":
        artifact["decisions"] = [decision, decision.copy()]
    else:
        event["payload"]["combo_access"] = True
    with pytest.raises(AssertionError):
        _validate_analytics(artifact)


def test_golden_fixtures_are_honestly_unreviewed() -> None:
    fixtures = list((ROOT / "tests/fixtures/golden-replays").glob("*.json"))
    assert len(fixtures) == 9
    assert all(
        json.loads(path.read_text())["review_status"] == "draft-unreviewed" for path in fixtures
    )


def test_candidate_verdict_fields_are_rejected_recursively() -> None:
    from tests.phase_a_acceptance.reference_adapter import reject_candidate_verdicts

    for field in (
        "satisfied_acceptance_ids",
        "postconditions",
        "trace_invariants",
        "referee_observations",
        "production_entrypoint",
        "passed",
        "valid",
        "legal",
        "correct",
    ):
        with pytest.raises(AssertionError):
            reject_candidate_verdicts({"payload": {field: True}})


def test_reference_manifest_uses_exact_acceptance_nodes() -> None:
    manifest = json.loads((ROOT / "automation/phase-a-reference-manifest.json").read_text())
    mappings = manifest["mappings"]
    assert len(mappings) == 42
    assert len({item["acceptance_id"] for item in mappings}) == len(mappings)
    assert len({item["reference_node_id"] for item in mappings}) == len(mappings)
    for item in mappings:
        expected = (
            f"tests/phase_a_acceptance/test_reference_contract.py::test_{item['acceptance_id']}_"
        )
        assert item["reference_node_id"].startswith(expected)


@pytest.mark.parametrize(
    "field", ["actions", "events", "rng_streams", "external_ledger", "objects", "final_state"]
)
def test_replay_tampering_is_rejected(field: str) -> None:
    from tests.phase_a_acceptance.reference_adapter import validate_replay_artifact

    original = {name: [] for name in ("actions", "events", "external_ledger", "objects")}
    original.update({"rng_streams": {"game": 1}, "final_state": {"life_totals": {"p1": 40}}})
    replay = json.loads(json.dumps(original))
    replay[field] = ["tampered"] if isinstance(replay[field], list) else {"tampered": True}
    with pytest.raises(AssertionError):
        validate_replay_artifact(original, replay)


def test_candidate_input_is_physically_separated_from_referee_oracle() -> None:
    document = json.loads((ROOT / "automation/reference-scenarios.json").read_text())
    forbidden = {
        "assertion_id",
        "acceptance_requirement",
        "requirement_text",
        "expected_state_transition_predicates",
        "expected_final_state_predicates",
        "semantic_assertion_plan",
        "required_call_contract",
    }
    for scenario in document["scenarios"]:
        assert set(scenario) == {
            "scenario_id",
            "scenario_version",
            "schema_version",
            "candidate_input",
            "referee_oracle",
        }
        serialized = json.dumps(scenario["candidate_input"])
        assert forbidden.isdisjoint(scenario["candidate_input"])
        assert scenario["referee_oracle"]["requirement_text"] not in serialized


def test_candidate_scripts_use_only_closed_driver_commands() -> None:
    document = json.loads((ROOT / "automation/reference-scenarios.json").read_text())
    allowed = {
        "cast_spell",
        "activate_ability",
        "pass_priority",
        "choose_target",
        "choose_mode",
        "choose_payment",
        "declare_attacker",
        "choose_optional_action",
        "choose_commander_replacement",
        "inject_external_spell",
        "advance_step",
        "play_land",
        "take_game_action",
    }
    for scenario in document["scenarios"]:
        commands = scenario["candidate_input"]["action_script"]
        assert commands
        assert {command["command"] for command in commands} <= allowed
        assert all("action_type" not in command for command in commands)


def test_every_acceptance_has_two_semantic_near_misses() -> None:
    document = json.loads((ROOT / "automation/phase-a-semantic-mutation-matrix.json").read_text())
    families = document["families"]
    assert len(families) == 42
    assert len({family["acceptance_id"] for family in families}) == 42
    assert all(len(family["near_misses"]) >= 2 for family in families)
    assert all(
        case["preserves_event_types"] is True
        for family in families
        for case in family["near_misses"]
    )
    assert all(
        case["mutation_function_id"] and case["clause_id"] and case["attacks_clause"]
        for family in families
        for case in family["near_misses"]
    )


def test_phase_a_semantic_mutation_matrix_executes_every_near_miss() -> None:
    from scripts.check_phase_a_semantic_mutations import execute

    executed, errors = execute()
    assert executed == 84
    assert errors == []


def test_liveness_rejects_fake_service_names_in_executor_module() -> None:
    from scripts.check_kernel_liveness import validate

    data = {
        "events": [
            {
                "event_type": "zone_moved",
                "parent_action_id": "a",
                "pre_state_hash": "before",
                "post_state_hash": "after",
            }
        ],
        "receipts": [],
        "_referee_call_contract": [
            {
                "module": "mtg_kernel.zones",
                "qualname": "ZoneService.move",
                "causal_event_type": "zone_moved",
            }
        ],
        "_referee_calls": [
            {
                "order": 1,
                "kind": "call",
                "module": "mtg_kernel.executor",
                "qualname": "GameExecutor.run",
            },
            {
                "order": 2,
                "kind": "call",
                "module": "mtg_kernel.executor",
                "qualname": "ZoneService.move",
            },
            {
                "order": 3,
                "kind": "return",
                "module": "mtg_kernel.executor",
                "qualname": "GameExecutor.run",
            },
        ],
    }
    errors = validate(data)
    assert any("mtg_kernel.zones.ZoneService.move" in error for error in errors)


def test_replay_contract_does_not_repair_candidate_output() -> None:
    source = (ROOT / "tests/phase_a_acceptance/test_replay_contract.py").read_text()
    assert 'replay["actions"] =' not in source
    assert 'replay["rng_streams"] =' not in source
