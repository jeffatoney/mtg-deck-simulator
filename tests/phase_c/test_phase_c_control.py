from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from mtg_cards.full_deck import load_full_deck_specs
from mtg_kernel.errors import IllegalAction, UnsupportedCapability
from mtg_kernel.factory import add_card, new_game
from mtg_kernel.hashing import state_hash
from mtg_kernel.models import TargetRef, Zone
from mtg_kernel.replay import transcript, validate_replay
from mtg_kernel.strategic_choices import CardSelectionRequest, PublicCard
from mtg_measure import bind_combo_access_tracker
from mtg_policy import (
    ContextualEvaluator,
    PolicyStrategicChoiceProvider,
    load_evaluator_config,
    load_policy_matrix,
)
from mtg_runs.phase_c import (
    CONFIRMATION_TOKEN,
    DEFAULT_APPROVAL,
    DEFAULT_CONFIG,
    DEFAULT_WORKFLOW,
    PhaseCAuthorizationContext,
    PhaseCControlError,
    build_pilot_seed_plan,
    build_pilot_shard_assignment,
    dry_run_phase_c,
    load_phase_c_approval,
    load_phase_c_config,
    validate_execution_authorization,
)
from mtg_runs.phase_c_runner import (
    _bound_policy,
    _cleanup_discard_ids,
    run_phase_c_combat_smoke,
    run_phase_c_exploratory_smoke,
    run_phase_c_paired_environment_smoke,
    run_phase_c_technical_game,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _config_payload() -> dict[str, object]:
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def test_locked_config_binds_exact_policy_counts_depth_and_information_boundary() -> None:
    config = load_phase_c_config()
    approval = load_phase_c_approval()
    policy = next(
        bundle
        for bundle in load_policy_matrix()
        if bundle.policy_config_id == config.policy_config_id
    )
    expected_status = {
        False: "LOCKED_PENDING_OWNER_APPROVAL",
        True: "AUTHORIZED",
    }
    assert config.authorization_status == expected_status[config.execution_allowed]
    if config.execution_allowed:
        assert approval.status == "APPROVED"
        assert approval.approved_by == "Jeff Toney"
        assert approval.approved_at is not None
    else:
        assert approval.status == "PENDING_OWNER_APPROVAL"
    assert (config.standard_games, config.exploratory_games) == (500, 200)
    assert config.exploratory_production_decision_layer_depth == 1
    assert policy.config_hash == config.policy_config_hash
    assert policy.evaluator_snapshot_id == config.evaluator_snapshot_id
    assert policy.evaluator_snapshot_sha256 == config.evaluator_snapshot_sha256
    assert policy.value("learning_plan_sha256") == config.learning_plan_sha256


def test_seed_plan_is_deterministic_exact_and_paired() -> None:
    config = load_phase_c_config()
    first = build_pilot_seed_plan(config)
    second = build_pilot_seed_plan(config)
    assert first == second
    assert len(first.standard) == 500
    assert len(first.exploratory) == 200
    assert set(first.exploratory).issubset(first.standard)
    assert len(first.exploratory_search) == 200
    assert not set(first.exploratory_search).intersection(first.standard)
    assert len(set(first.pair_ids)) == 200
    assert len(first.paired_standard_game_indexes) == 200
    for shard_index in range(10):
        standard_assignment = build_pilot_shard_assignment(
            config, first, mode="STANDARD", shard_index=shard_index
        )
        exploratory_assignment = build_pilot_shard_assignment(
            config, first, mode="EXPLORATORY", shard_index=shard_index
        )
        assert len([value for value in standard_assignment.pair_ids if value is not None]) == 20
        assert exploratory_assignment.seeds == tuple(
            seed
            for seed, pair_id in zip(
                standard_assignment.seeds, standard_assignment.pair_ids, strict=True
            )
            if pair_id is not None
        )
        assert all(value is not None for value in exploratory_assignment.search_seeds)


def test_paired_modes_share_environment_but_not_search_rng() -> None:
    smoke = run_phase_c_paired_environment_smoke(environment_seed=505, search_seed=606)
    assert smoke["status"] == "PASS"
    assert smoke["opening_environment_equal"] is True
    assert smoke["standard_search_seed"] is None
    assert smoke["exploratory_search_seed"] == 606


def test_dry_run_derives_readiness_from_real_smokes_and_creates_no_result() -> None:
    config = load_phase_c_config()
    report = dry_run_phase_c()
    assert report.status == "READY_FOR_OWNER_REVIEW"
    assert report.execution_allowed is config.execution_allowed
    assert report.authorization_status == config.authorization_status
    assert report.game_results_created == 0
    assert report.full_study_execution_allowed is False
    assert report.readiness_blockers == ()
    assert report.exploratory_production_decision_layer_depth == 1
    assert report.paired_game_count == 200
    assert report.exploratory_search_seed_sha256 != report.exploratory_seed_sha256
    assert set(report.readiness_evidence) == {
        "CONTROLLED_TURN_DRIVER_NOT_IMPLEMENTED",
        "COMBAT_ACTION_PATH_NOT_IMPLEMENTED",
        "EXPLORATORY_PRODUCTION_EXPANSION_NOT_IMPLEMENTED",
        "PAIRED_EXPLORATORY_DESIGN_NOT_IMPLEMENTED",
        "COMBO_ACCESS_DETECTORS_INCOMPLETE",
    }
    assert all(value["status"] == "PASS" for value in report.readiness_evidence.values())
    assert report.config_sha256 == hashlib.sha256(DEFAULT_CONFIG.read_bytes()).hexdigest()
    assert (
        report.approval_record_sha256 == hashlib.sha256(DEFAULT_APPROVAL.read_bytes()).hexdigest()
    )
    assert report.workflow_sha256 == hashlib.sha256(DEFAULT_WORKFLOW.read_bytes()).hexdigest()


def test_config_rejects_count_future_information_depth_and_full_study_drift(tmp_path: Path) -> None:
    payload = _config_payload()
    pilot = payload["pilot"]
    assert isinstance(pilot, dict)
    pilot["standard_games"] = 499
    with pytest.raises(PhaseCControlError, match="standard pilot count"):
        load_phase_c_config(_write_json(tmp_path / "wrong-count.json", payload))

    payload = _config_payload()
    search = payload["exploratory_search"]
    assert isinstance(search, dict)
    search["future_information_allowed"] = True
    with pytest.raises(PhaseCControlError, match="future information"):
        load_phase_c_config(_write_json(tmp_path / "future.json", payload))

    payload = _config_payload()
    search = payload["exploratory_search"]
    assert isinstance(search, dict)
    search["production_decision_layer_depth"] = 2
    with pytest.raises(PhaseCControlError, match="decision-layer depth"):
        load_phase_c_config(_write_json(tmp_path / "depth.json", payload))

    payload = _config_payload()
    full_study = payload["full_study"]
    assert isinstance(full_study, dict)
    full_study["execution_allowed"] = True
    with pytest.raises(PhaseCControlError, match="full-study flag"):
        load_phase_c_config(_write_json(tmp_path / "full-study.json", payload))


def test_turn_ten_exact_deck_driver_and_fresh_replay() -> None:
    game = run_phase_c_technical_game(
        seed=101,
        mode="STANDARD",
        through_turn=10,
        validate_fresh_replay=True,
        policy_actions=False,
    )
    assert game.controlled_turns_completed == 10
    assert game.final_state_hash == game.fresh_replay_state_hash
    assert game.command_count > 100
    assert game.opening_hands[-1].kept is True
    assert game.pilot_result is False and game.authorized_pilot_result is False


def test_combat_and_exploratory_smokes_use_production_paths() -> None:
    combat = run_phase_c_combat_smoke(seed=303)
    assert combat["status"] == "PASS"
    assert combat["broker_action_kind"] == "DECLARE_ATTACKERS"
    assert combat["life_after"] == 38
    assert combat["commander_damage"] == 2

    exploratory = run_phase_c_exploratory_smoke(seed=404)
    assert exploratory["status"] == "PASS"
    assert exploratory["production_decision_layer_depth"] == 1
    assert exploratory["nodes_evaluated"] >= 1
    assert exploratory["game_nodes_used"] <= 5_000


def test_look_select_is_exact_deterministic_and_evaluator_bound() -> None:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    evaluator = ContextualEvaluator(load_evaluator_config())
    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    cards = tuple(
        PublicCard(f"h{i}", name, mv, types, ())
        for i, (name, mv, types) in enumerate(
            (
                ("Island", 0, ("Land",)),
                ("Sol Ring", 1, ("Artifact",)),
                ("Twinflame", 2, ("Sorcery",)),
            )
        )
    )
    request = CardSelectionRequest(
        request_id="look-select-test",
        actor_id="P0",
        ability_id="impulse",
        purpose="LOOK_SELECT",
        turn_number=3,
        observation={"generation": 1, "player": "P0", "objects": [], "turn": {"number": 3}},
        candidates=cards,
        minimum=1,
        maximum=1,
    )
    first = provider.choose_cards(request)
    second = provider.choose_cards(request)
    assert first == second
    assert len(first.selected_handles) == 1
    assert first.evaluator_id == evaluator.config.evaluator_id
    assert first.evaluator_sha256 == evaluator.config.config_sha256
    with pytest.raises(Exception):
        provider.choose_cards(
            CardSelectionRequest(**{**request.__dict__, "minimum": 0, "maximum": 1})
        )


def test_tutor_card_selection_is_deterministic_exact_and_evaluator_bound() -> None:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    evaluator = ContextualEvaluator(load_evaluator_config())
    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    cards = (
        PublicCard("h1", "Mountain", 0, ("Land",), ()),
        PublicCard("h2", "Twinflame", 2, ("Sorcery",), ()),
        PublicCard("h3", "Opt", 1, ("Instant",), ()),
    )
    exact = CardSelectionRequest(
        request_id="long-term-plans",
        actor_id="P0",
        ability_id="ltp",
        purpose="TUTOR_THIRD_FROM_TOP",
        turn_number=8,
        observation={},
        candidates=cards,
        minimum=1,
        maximum=1,
    )
    first = provider.choose_cards(exact)
    assert first == provider.choose_cards(exact)
    assert len(first.selected_handles) == 1
    assert first.evaluator_id == evaluator.config.evaluator_id
    assert first.evaluator_sha256 == evaluator.config.config_sha256
    assert first.diagnostics["purpose"] == "TUTOR_THIRD_FROM_TOP"
    optional = CardSelectionRequest(
        request_id="invent",
        actor_id="P0",
        ability_id="invent",
        purpose="TUTOR_INSTANT",
        turn_number=8,
        observation={},
        candidates=(cards[2],),
        minimum=0,
        maximum=1,
    )
    assert provider.choose_cards(optional).selected_handles == ("h3",)


def test_atomic_rollback_preserves_state_hash_and_replay_sequence() -> None:
    state, executor = new_game(("P0", "P1"), seed="phase-c-rollback")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    add_card(executor, specs["Malcolm, Keen-Eyed Navigator"], Zone.BATTLEFIELD)
    before_hash = state_hash(state)
    before_commands = deepcopy(state.replay_commands)
    with pytest.raises(IllegalAction, match="declare attackers"):
        executor.declare_attackers("P0", {})
    assert state_hash(state) == before_hash
    assert state.replay_commands == before_commands
    executor.begin_step("BEGIN_COMBAT")
    assert len(state.replay_commands) == len(before_commands) + 1
    assert validate_replay(transcript(state, seed="phase-c-rollback"))


def test_cleanup_policy_bookkeeping_does_not_consume_identity_or_rng_and_replays() -> None:
    state, executor = new_game(("P0", "P1"), seed="phase-c-cleanup")
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    for name in (
        "Island",
        "Mountain",
        "Opt",
        "Twinflame",
        "Curiosity",
        "Abrade",
        "Negate",
        "Dispel",
    ):
        add_card(executor, specs[name], Zone.HAND)
    _policy, provider, _ = _bound_policy(executor, "anchor_balanced")
    allocation_before = dict(state.allocation)
    rng_before = {
        key: (value.draw_count, value.state_digest) for key, value in state.rng_streams.items()
    }
    discard = _cleanup_discard_ids(executor, provider)
    assert len(discard) == 1
    assert state.allocation == allocation_before
    assert {
        key: (value.draw_count, value.state_digest) for key, value in state.rng_streams.items()
    } == rng_before
    executor.begin_step("CLEANUP", {"discard_ids": list(discard)})
    assert len(state.zones[executor.zones.zone_key(Zone.HAND, "P0")]) == 7
    replayed = validate_replay(transcript(state, seed="phase-c-cleanup"))
    assert state_hash(replayed) == state_hash(state)


def test_all_six_combo_packages_have_executable_detectors_and_no_tutor_double_count() -> None:
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}
    state, executor = new_game(("P0", "P1", "P2", "P3"), seed="phase-c-combos")
    state.turn.number = 3
    state.turn.phase = "PRECOMBAT_MAIN"
    state.turn.step = "PRECOMBAT_MAIN"
    state.turn.active_player_id = "P0"
    state.turn.priority_holder_id = "P0"
    state.players["P0"].mana_pool.update({"R": 5, "U": 5, "C": 10})
    for name in (
        "Dualcaster Mage",
        "Twinflame",
        "Electroduplicate",
        "Glint-Horn Buccaneer",
        "Curiosity",
        "Psychosis Crawler",
        "Opt",
    ):
        add_card(executor, specs[name], Zone.HAND)
    for name in ("Malcolm, Keen-Eyed Navigator", "Lightning-Rig Crew", "Niv-Mizzet, the Firemind"):
        obj = add_card(executor, specs[name], Zone.BATTLEFIELD)
        assert obj.permanent_status is not None
        obj.permanent_status["controller_since_turn"] = "1"
    crew = next(
        obj
        for obj in state.objects.values()
        if obj.current_characteristics.get("name") == "Lightning-Rig Crew"
    )
    aura = add_card(executor, specs["Crab Umbra"], Zone.BATTLEFIELD)
    aura.attached_to_ref = TargetRef(crew.object_id)
    tracker = bind_combo_access_tracker(executor, "P0", load_evaluator_config().combo_packages)
    records = tracker.observe(executor)
    assert {record.package for record in records} == set(load_evaluator_config().combo_packages)
    assert all("UNIMPLEMENTED" not in blocker for record in records for blocker in record.blockers)
    # Access is based on actual pieces in state; a tutor identity by itself is never
    # counted as simultaneous access to several missing combo cards.
    empty_state, empty_executor = new_game(("P0", "P1", "P2", "P3"), seed="phase-c-tutor")
    add_card(empty_executor, specs["Muddle the Mixture"], Zone.HAND)
    empty_tracker = bind_combo_access_tracker(
        empty_executor, "P0", load_evaluator_config().combo_packages
    )
    assert not any(record.pieces_assembled for record in empty_tracker.observe(empty_executor))


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _activation_repo(tmp_path: Path) -> tuple[Path, Path, Path, str, str, str, str]:
    root = tmp_path / "repo"
    config = root / "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
    approval = root / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
    workflow = root / ".github/workflows/phase-c-pilot.yml"
    config_payload = json.loads(DEFAULT_CONFIG.read_text())
    authorization = config_payload["authorization"]
    assert isinstance(authorization, dict)
    authorization.update(
        {
            "approved_at": None,
            "approved_by": None,
            "execution_allowed": False,
            "status": "LOCKED_PENDING_OWNER_APPROVAL",
        }
    )
    _write_json(config, config_payload)
    approval_payload = json.loads(DEFAULT_APPROVAL.read_text())
    approval_payload.update(
        {
            "approval_statement": None,
            "approved_at": None,
            "approved_by": None,
            "implementation_commit": None,
            "implementation_tree": None,
            "locked_pilot_config_sha256": None,
            "status": "PENDING_OWNER_APPROVAL",
            "workflow_sha256": None,
        }
    )
    _write_json(approval, approval_payload)
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_bytes(DEFAULT_WORKFLOW.read_bytes())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "phase-c@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Phase C Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "implementation"], cwd=root, check=True)
    implementation = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    locked_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    workflow_sha = hashlib.sha256(workflow.read_bytes()).hexdigest()
    return root, config, approval, implementation, tree, locked_sha, workflow_sha


def test_activation_is_governance_only_descendant_not_self_referential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, config_path, approval_path, implementation, tree, locked_sha, workflow_sha = (
        _activation_repo(tmp_path)
    )
    config = json.loads(config_path.read_text())
    config["authorization"].update(
        {
            "execution_allowed": True,
            "status": "AUTHORIZED",
            "approved_by": "Jeff Toney",
            "approved_at": "2026-08-06T23:00:00Z",
        }
    )
    _write_json(config_path, config)
    approval = json.loads(approval_path.read_text())
    statement = " ".join(
        [
            implementation,
            tree,
            locked_sha,
            workflow_sha,
            approval["confirmation_token_sha256"],
            "500",
            "200",
            "1",
            "standard_shards=10",
            "exploratory_shards=10",
        ]
    )
    approval.update(
        {
            "status": "APPROVED",
            "approved_by": "Jeff Toney",
            "approved_at": "2026-08-06T23:00:00Z",
            "implementation_commit": implementation,
            "implementation_tree": tree,
            "locked_pilot_config_sha256": locked_sha,
            "workflow_sha256": workflow_sha,
            "approval_statement": statement,
        }
    )
    _write_json(approval_path, approval)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "owner activation"], cwd=root, check=True)
    activation = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr("mtg_runs.phase_c.current_engine_blockers", lambda: ())
    _, loaded_approval, _, context = validate_execution_authorization(
        confirmation=CONFIRMATION_TOKEN,
        implementation_commit=implementation,
        activation_commit=activation,
        expected_locked_config_sha256=locked_sha,
        expected_workflow_sha256=workflow_sha,
        config_path=config_path,
        approval_path=approval_path,
        workflow_path=root / ".github/workflows/phase-c-pilot.yml",
        root=root,
    )
    assert loaded_approval.implementation_commit == implementation
    assert context.implementation_tree == tree
    assert activation != implementation


def test_activation_rejects_unexpected_code_change_and_git_sha256_domain_mix(
    tmp_path: Path,
) -> None:
    with pytest.raises(PhaseCControlError, match="40-character Git object ID"):
        PhaseCAuthorizationContext("a" * 64, "b" * 40, "c" * 40, "d" * 64, "e" * 64)

    root, config_path, approval_path, implementation, _tree, locked_sha, workflow_sha = (
        _activation_repo(tmp_path)
    )
    (root / "src").mkdir()
    (root / "src/unexpected.py").write_text("unexpected = True\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "unexpected code"], cwd=root, check=True)
    activation = _git(root, "rev-parse", "HEAD")
    with pytest.raises(PhaseCControlError, match="non-governance files"):
        validate_execution_authorization(
            confirmation=CONFIRMATION_TOKEN,
            implementation_commit=implementation,
            activation_commit=activation,
            expected_locked_config_sha256=locked_sha,
            expected_workflow_sha256=workflow_sha,
            config_path=config_path,
            approval_path=approval_path,
            workflow_path=root / ".github/workflows/phase-c-pilot.yml",
            root=root,
        )


def test_order_library_bottom_is_exact_deterministic_and_evaluator_bound() -> None:
    bundle = next(
        item for item in load_policy_matrix() if item.policy_config_id == "anchor_balanced"
    )
    evaluator = ContextualEvaluator(load_evaluator_config())
    provider = PolicyStrategicChoiceProvider(bundle, evaluator)
    cards = (
        PublicCard("bottom-a", "Island", 0, ("Land",), ()),
        PublicCard("bottom-b", "Twinflame", 2, ("Sorcery",), ()),
        PublicCard("bottom-c", "Opt", 1, ("Instant",), ()),
    )
    request = CardSelectionRequest(
        request_id="order-library-bottom",
        actor_id="P0",
        ability_id="impulse",
        purpose="ORDER_LIBRARY_BOTTOM",
        turn_number=3,
        observation={"generation": 1, "player": "P0", "objects": [], "turn": {"number": 3}},
        candidates=cards,
        minimum=3,
        maximum=3,
    )
    evaluations = {
        card.handle: evaluator.evaluate_pile((card,), request.observation).score for card in cards
    }
    expected = tuple(
        card.handle
        for card in sorted(
            cards,
            key=lambda card: (evaluations[card.handle], card.identity, card.handle),
        )
    )
    first = provider.choose_cards(request)
    second = provider.choose_cards(request)
    assert first == second
    assert first.selected_handles == expected
    assert set(first.selected_handles) == {card.handle for card in cards}
    assert first.evaluator_id == evaluator.config.evaluator_id
    assert first.evaluator_sha256 == evaluator.config.config_sha256
    assert first.diagnostics["purpose"] == "ORDER_LIBRARY_BOTTOM"
    with pytest.raises(UnsupportedCapability, match="exact ordering"):
        provider.choose_cards(
            CardSelectionRequest(
                request_id="bad-bottom-order",
                actor_id="P0",
                ability_id="impulse",
                purpose="ORDER_LIBRARY_BOTTOM",
                turn_number=3,
                observation=request.observation,
                candidates=cards,
                minimum=2,
                maximum=3,
            )
        )
