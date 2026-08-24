from __future__ import annotations

from datetime import UTC, datetime

from scripts.serve_health_api import build_health_payload


def _handoff(*, pilot_allowed: bool, subject_commit: str = "abc123") -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-20T02:43:08+00:00",
        "repository": {
            "name": "jeffatoney/mtg-deck-simulator",
            "subject_commit": subject_commit,
            "subject_tree": "tree123",
        },
        "certifications": {
            "phase_a": {
                "status": "PASS",
                "certified_content_commit": "phase-a-commit",
                "verifier_run_id": "phase-a-run",
            },
            "phase_b": {
                "status": "PASS",
                "certified_content_commit": "phase-b-commit",
                "verifier_run_id": "phase-b-run",
            },
        },
        "governance": {
            "pilot": {
                "approval_status": "APPROVED" if pilot_allowed else "PENDING_OWNER_APPROVAL",
                "authorization_status": (
                    "AUTHORIZED" if pilot_allowed else "LOCKED_PENDING_OWNER_APPROVAL"
                ),
                "execution_allowed": pilot_allowed,
                "standard_games": 500,
                "exploratory_games": 200,
            },
            "full_study": {
                "authorization_status": "LOCKED_PENDING_POST_PILOT_REVIEW",
                "execution_allowed": False,
                "standard_games": 20000,
                "exploratory_games": 5000,
            },
        },
    }


def _activation_approval(*, approved: bool = True) -> dict[str, object]:
    return {
        "status": "APPROVED" if approved else "PENDING_OWNER_APPROVAL",
        "approved_at": "2026-08-13T21:34:51Z" if approved else None,
        "approved_by": "Jeff Toney" if approved else None,
        "authorized_counts": {"standard": 500, "exploratory": 200},
    }


def test_health_reports_current_status_when_independent_signals_agree() -> None:
    payload = build_health_payload(
        handoff=_handoff(pilot_allowed=True),
        fetch_remote_handoff=False,
        current_main_commit="abc123",
        pilot_activation_approval=_activation_approval(),
        fetch_remote_signals=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "ok"
    assert payload["apiVersion"] == "health-v2"
    assert payload["phase"] == "phase-c"
    assert payload["mode"] == "live"
    assert payload["statusSource"] == "handoff/current"
    assert payload["statusIntegrity"]["state"] == "CURRENT"
    assert payload["statusIntegrity"]["authoritative"] is True
    assert payload["governance"]["pilot"]["executionAllowed"] is True
    assert payload["productionRunsEnabled"] is False
    assert payload["fullStudyEnabled"] is False
    assert "simulation execution endpoints are not exposed" in payload["gateReason"]


def test_health_degrades_when_handoff_subject_commit_is_behind_main() -> None:
    payload = build_health_payload(
        handoff=_handoff(pilot_allowed=True, subject_commit="old-head"),
        fetch_remote_handoff=False,
        current_main_commit="new-head",
        pilot_activation_approval=_activation_approval(),
        fetch_remote_signals=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "degraded"
    assert payload["statusIntegrity"]["state"] == "STALE"
    assert payload["statusIntegrity"]["authoritative"] is False
    assert any(
        issue["code"] == "HANDOFF_BEHIND_MAIN" for issue in payload["statusIntegrity"]["issues"]
    )
    assert payload["productionRunsEnabled"] is False


def test_health_degrades_when_pilot_approval_sources_conflict() -> None:
    payload = build_health_payload(
        handoff=_handoff(pilot_allowed=False),
        fetch_remote_handoff=False,
        current_main_commit="abc123",
        pilot_activation_approval=_activation_approval(approved=True),
        fetch_remote_signals=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "degraded"
    assert payload["statusIntegrity"]["state"] == "CONFLICT"
    assert payload["statusIntegrity"]["authoritative"] is False
    assert payload["statusIntegrity"]["handoffPilotApprovalStatus"] == "PENDING_OWNER_APPROVAL"
    assert payload["statusIntegrity"]["pilotActivationApprovalStatus"] == "APPROVED"
    assert any(
        issue["code"] == "PILOT_APPROVAL_CONFLICT" for issue in payload["statusIntegrity"]["issues"]
    )
    assert "not treated as authoritative" in payload["gateReason"]
    assert payload["productionRunsEnabled"] is False
    assert payload["fullStudyEnabled"] is False


def test_health_is_unverified_when_independent_signals_are_unavailable() -> None:
    payload = build_health_payload(
        fetch_remote_handoff=False,
        fetch_remote_signals=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "degraded"
    assert payload["statusSource"] == "local-repository-fallback"
    assert payload["statusIntegrity"]["state"] == "UNVERIFIED"
    assert payload["statusIntegrity"]["authoritative"] is False
    assert payload["productionRunsEnabled"] is False
    assert payload["fullStudyEnabled"] is False
