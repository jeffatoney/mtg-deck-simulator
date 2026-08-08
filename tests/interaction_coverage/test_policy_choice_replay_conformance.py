from scripts.audit_policy_choice_replay_conformance import audit_conformance


def test_policy_and_replay_implement_the_same_strategic_protocol() -> None:
    report = audit_conformance()
    protocol = set(report["protocol_methods"])
    assert protocol
    assert protocol <= set(report["production_policy_methods"])
    assert protocol <= set(report["recorded_replay_methods"])


def test_mandatory_trigger_target_effects_have_explicit_policy_support() -> None:
    report = audit_conformance()
    assert report["targeted_trigger_effects"]
    assert report["missing_trigger_policy_effects"] == []


def test_source_legality_and_exact_replay_invariants_are_present() -> None:
    report = audit_conformance()
    failures = [item for item in report["source_invariants"] if item["missing_tokens"]]
    assert failures == []


def test_unrouted_surface_choices_are_reported_as_blockers() -> None:
    report = audit_conformance()
    violations = tuple(report["violations"])
    for choice in report["unrouted_surface_choices"]:
        prefix = (
            "interaction choice has no reviewed policy/replay route: "
            f"{choice['timing']}:{choice['purpose']} [{choice['policy_class']}]"
        )
        assert prefix in violations


def test_unfrozen_surface_cannot_be_reported_as_frozen_proof() -> None:
    report = audit_conformance()
    if report["surface_frozen"]:
        assert report["proof_status"] == "FROZEN_SURFACE"
    else:
        assert report["proof_status"] == "PROVISIONAL_UNTIL_COORDINATOR_FREEZE"
