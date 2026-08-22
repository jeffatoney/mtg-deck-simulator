from __future__ import annotations

from datetime import UTC, datetime

from scripts.serve_health_api import build_health_payload


def _handoff(*, pilot_allowed: bool) -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-20T02:43:08+00:00",
        "repository": {
            "name": "jeffatoney/mtg-deck-simulator",
            "subject_commit": "abc123",
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
                "authorization_status": "AUTHORIZED"
                if pilot_allowed
                else "LOCKED_PENDING_OWNER_APPROVAL",
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


def test_health_reports_live_status_but_keeps_api_execution_fail_closed() -> None:
    payload = build_health_payload(
        handoff=_handoff(pilot_allowed=True),
        fetch_remote_handoff=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "ok"
    assert payload["phase"] == "phase-c"
    assert payload["mode"] == "live"
    assert payload["statusSource"] == "handoff/current"
    assert payload["governance"]["pilot"]["executionAllowed"] is True
    assert payload["productionRunsEnabled"] is False
    assert payload["fullStudyEnabled"] is False
    assert "simulation execution endpoints are not exposed" in payload["gateReason"]


def test_health_can_fall_back_to_local_repository_governance() -> None:
    payload = build_health_payload(
        fetch_remote_handoff=False,
        now=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "ok"
    assert payload["statusSource"] == "local-repository-fallback"
    assert payload["productionRunsEnabled"] is False
    assert payload["fullStudyEnabled"] is False
    assert payload["governance"]["pilot"]["approvalStatus"]
