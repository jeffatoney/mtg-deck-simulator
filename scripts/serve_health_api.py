from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

REPOSITORY = "jeffatoney/mtg-deck-simulator"
HANDOFF_URL = (
    "https://raw.githubusercontent.com/jeffatoney/mtg-deck-simulator/"
    "handoff/current/docs/audit/handoff/CURRENT_HANDOFF.json"
)
MAIN_BRANCH_URL = "https://api.github.com/repos/jeffatoney/mtg-deck-simulator/branches/main"
PILOT_ACTIVATION_APPROVAL_URL = (
    "https://raw.githubusercontent.com/jeffatoney/mtg-deck-simulator/"
    "phase-c/pilot-activation/docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
)
ROOT = Path(__file__).resolve().parents[1]
PILOT_APPROVAL_PATH = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
PHASE_A_CERT_PATH = ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json"
PHASE_B_CERT_PATH = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"
REMOTE_SIGNAL_CACHE_SECONDS = 300.0
_REMOTE_SIGNAL_CACHE: tuple[float, dict[str, Any]] | None = None
_REMOTE_SIGNAL_LOCK = Lock()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return value


def _fetch_json_url(url: str, *, timeout_seconds: float = 2.5) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "mtg-deck-simulator-health/2"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS URLs
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return value


def _fetch_handoff(timeout_seconds: float = 2.5) -> dict[str, Any]:
    return _fetch_json_url(HANDOFF_URL, timeout_seconds=timeout_seconds)


def _fetch_remote_signals(*, timeout_seconds: float = 2.5) -> dict[str, Any]:
    global _REMOTE_SIGNAL_CACHE

    now = monotonic()
    with _REMOTE_SIGNAL_LOCK:
        if _REMOTE_SIGNAL_CACHE is not None:
            cached_at, cached_value = _REMOTE_SIGNAL_CACHE
            if now - cached_at < REMOTE_SIGNAL_CACHE_SECONDS:
                return cached_value

        signals: dict[str, Any] = {
            "currentMainCommit": None,
            "mainHeadFetchError": None,
            "pilotActivationApproval": None,
            "pilotActivationFetchError": None,
        }
        try:
            branch = _fetch_json_url(MAIN_BRANCH_URL, timeout_seconds=timeout_seconds)
            commit = branch.get("commit")
            if isinstance(commit, dict) and isinstance(commit.get("sha"), str):
                signals["currentMainCommit"] = commit["sha"]
            else:
                signals["mainHeadFetchError"] = "MissingCommitSha"
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            signals["mainHeadFetchError"] = type(exc).__name__

        try:
            signals["pilotActivationApproval"] = _fetch_json_url(
                PILOT_ACTIVATION_APPROVAL_URL,
                timeout_seconds=timeout_seconds,
            )
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            signals["pilotActivationFetchError"] = type(exc).__name__

        _REMOTE_SIGNAL_CACHE = (now, signals)
        return signals


def _certification_summary(path: Path) -> dict[str, Any]:
    try:
        cert = _load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "UNAVAILABLE", "error": type(exc).__name__}
    return {
        "status": cert.get("status", "UNKNOWN"),
        "certifiedContentCommit": cert.get("certified_content_commit"),
        "verifierRunId": cert.get("verifier_run_id"),
    }


def _fallback_governance() -> dict[str, Any]:
    try:
        approval = _load_json(PILOT_APPROVAL_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "pilot": {
                "approvalStatus": "UNAVAILABLE",
                "authorizationStatus": "UNKNOWN",
                "executionAllowed": False,
                "error": type(exc).__name__,
            },
            "fullStudy": {
                "authorizationStatus": "UNKNOWN",
                "executionAllowed": False,
            },
        }

    status = str(approval.get("status", "UNKNOWN"))
    approved = status == "APPROVED" and bool(approval.get("approved_at"))
    return {
        "pilot": {
            "approvalStatus": status,
            "authorizationStatus": "AUTHORIZED" if approved else "LOCKED_BY_LOCAL_APPROVAL_FILE",
            "executionAllowed": approved,
        },
        "fullStudy": {
            "authorizationStatus": "UNKNOWN_LOCAL_FALLBACK",
            "executionAllowed": False,
        },
    }


def _build_status_integrity(
    *,
    handoff: dict[str, Any] | None,
    governance_summary: dict[str, Any],
    current_main_commit: str | None,
    main_head_fetch_error: str | None,
    pilot_activation_approval: dict[str, Any] | None,
    pilot_activation_fetch_error: str | None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    stale = False
    conflict = False
    handoff_subject_commit: str | None = None

    if handoff is not None:
        repository = handoff.get("repository")
        if isinstance(repository, dict):
            subject = repository.get("subject_commit")
            if isinstance(subject, str):
                handoff_subject_commit = subject

    if current_main_commit is None:
        issues.append(
            {
                "code": "MAIN_HEAD_UNVERIFIED",
                "message": "Current main commit could not be independently verified.",
            }
        )
    elif handoff_subject_commit is None:
        issues.append(
            {
                "code": "HANDOFF_SUBJECT_UNVERIFIED",
                "message": "The handoff does not identify a subject commit.",
            }
        )
    elif current_main_commit != handoff_subject_commit:
        stale = True
        issues.append(
            {
                "code": "HANDOFF_BEHIND_MAIN",
                "message": (
                    "The handoff subject commit does not match the current main head; "
                    "handoff governance is stale for repository status reporting."
                ),
            }
        )

    pilot = governance_summary.get("pilot", {})
    handoff_approval_status = pilot.get("approvalStatus") if isinstance(pilot, dict) else None
    handoff_standard_games = pilot.get("standardGames") if isinstance(pilot, dict) else None
    handoff_exploratory_games = pilot.get("exploratoryGames") if isinstance(pilot, dict) else None

    activation_status: str | None = None
    activation_approved_at: str | None = None
    activation_standard_games: int | None = None
    activation_exploratory_games: int | None = None
    if pilot_activation_approval is not None:
        status = pilot_activation_approval.get("status")
        if isinstance(status, str):
            activation_status = status
        approved_at = pilot_activation_approval.get("approved_at")
        if isinstance(approved_at, str):
            activation_approved_at = approved_at
        counts = pilot_activation_approval.get("authorized_counts")
        if isinstance(counts, dict):
            standard = counts.get("standard")
            exploratory = counts.get("exploratory")
            if isinstance(standard, int):
                activation_standard_games = standard
            if isinstance(exploratory, int):
                activation_exploratory_games = exploratory

        if activation_status is not None and handoff_approval_status is not None:
            handoff_approved = handoff_approval_status == "APPROVED"
            activation_approved = (
                activation_status == "APPROVED" and activation_approved_at is not None
            )
            if handoff_approved != activation_approved:
                conflict = True
                issues.append(
                    {
                        "code": "PILOT_APPROVAL_CONFLICT",
                        "message": (
                            "The handoff pilot approval state conflicts with the Phase C "
                            "pilot-activation approval record. Neither governance value is "
                            "treated as authoritative by this API."
                        ),
                    }
                )

        if (
            activation_standard_games is not None
            and handoff_standard_games is not None
            and activation_standard_games != handoff_standard_games
        ) or (
            activation_exploratory_games is not None
            and handoff_exploratory_games is not None
            and activation_exploratory_games != handoff_exploratory_games
        ):
            conflict = True
            issues.append(
                {
                    "code": "PILOT_COUNT_CONFLICT",
                    "message": (
                        "The handoff pilot game counts conflict with the Phase C "
                        "pilot-activation approval record."
                    ),
                }
            )
    else:
        issues.append(
            {
                "code": "PILOT_ACTIVATION_UNVERIFIED",
                "message": "The Phase C pilot-activation approval record could not be verified.",
            }
        )

    if conflict:
        state = "CONFLICT"
    elif stale:
        state = "STALE"
    elif issues:
        state = "UNVERIFIED"
    else:
        state = "CURRENT"

    return {
        "state": state,
        "authoritative": state == "CURRENT",
        "handoffSubjectCommit": handoff_subject_commit,
        "currentMainCommit": current_main_commit,
        "mainHeadFetchError": main_head_fetch_error,
        "handoffPilotApprovalStatus": handoff_approval_status,
        "pilotActivationApprovalStatus": activation_status,
        "pilotActivationApprovedAt": activation_approved_at,
        "pilotActivationFetchError": pilot_activation_fetch_error,
        "issues": issues,
    }


def build_health_payload(
    *,
    handoff: dict[str, Any] | None = None,
    fetch_remote_handoff: bool = True,
    current_main_commit: str | None = None,
    pilot_activation_approval: dict[str, Any] | None = None,
    fetch_remote_signals: bool = True,
    main_head_fetch_error: str | None = None,
    pilot_activation_fetch_error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the read-only health response without importing the rules engine."""

    status_source = "handoff/current"
    handoff_error: str | None = None

    if handoff is None and fetch_remote_handoff:
        try:
            handoff = _fetch_handoff()
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            handoff_error = type(exc).__name__

    if fetch_remote_signals and current_main_commit is None and pilot_activation_approval is None:
        remote_signals = _fetch_remote_signals()
        current_main_commit = remote_signals.get("currentMainCommit")
        main_head_fetch_error = remote_signals.get("mainHeadFetchError")
        pilot_activation_approval = remote_signals.get("pilotActivationApproval")
        pilot_activation_fetch_error = remote_signals.get("pilotActivationFetchError")

    if handoff is not None:
        governance = handoff.get("governance", {})
        pilot = governance.get("pilot", {}) if isinstance(governance, dict) else {}
        full_study = governance.get("full_study", {}) if isinstance(governance, dict) else {}
        repository = handoff.get("repository", {})
        certifications = handoff.get("certifications", {})
        phase_a = certifications.get("phase_a", {}) if isinstance(certifications, dict) else {}
        phase_b = certifications.get("phase_b", {}) if isinstance(certifications, dict) else {}
        governance_summary = {
            "pilot": {
                "approvalStatus": pilot.get("approval_status", "UNKNOWN"),
                "authorizationStatus": pilot.get("authorization_status", "UNKNOWN"),
                "executionAllowed": bool(pilot.get("execution_allowed", False)),
                "standardGames": pilot.get("standard_games"),
                "exploratoryGames": pilot.get("exploratory_games"),
            },
            "fullStudy": {
                "authorizationStatus": full_study.get("authorization_status", "UNKNOWN"),
                "executionAllowed": bool(full_study.get("execution_allowed", False)),
                "standardGames": full_study.get("standard_games"),
                "exploratoryGames": full_study.get("exploratory_games"),
            },
        }
        certification_summary = {
            "phaseA": {
                "status": phase_a.get("status", "UNKNOWN"),
                "certifiedContentCommit": phase_a.get("certified_content_commit"),
                "verifierRunId": phase_a.get("verifier_run_id"),
            },
            "phaseB": {
                "status": phase_b.get("status", "UNKNOWN"),
                "certifiedContentCommit": phase_b.get("certified_content_commit"),
                "verifierRunId": phase_b.get("verifier_run_id"),
            },
        }
        repository_summary = {
            "name": repository.get("name", REPOSITORY)
            if isinstance(repository, dict)
            else REPOSITORY,
            "subjectCommit": repository.get("subject_commit")
            if isinstance(repository, dict)
            else None,
            "subjectTree": repository.get("subject_tree") if isinstance(repository, dict) else None,
        }
        handoff_generated_at = handoff.get("generated_at_utc")
    else:
        status_source = "local-repository-fallback"
        governance_summary = _fallback_governance()
        certification_summary = {
            "phaseA": _certification_summary(PHASE_A_CERT_PATH),
            "phaseB": _certification_summary(PHASE_B_CERT_PATH),
        }
        repository_summary = {"name": REPOSITORY, "subjectCommit": None, "subjectTree": None}
        handoff_generated_at = None

    integrity = _build_status_integrity(
        handoff=handoff,
        governance_summary=governance_summary,
        current_main_commit=current_main_commit,
        main_head_fetch_error=main_head_fetch_error,
        pilot_activation_approval=pilot_activation_approval,
        pilot_activation_fetch_error=pilot_activation_fetch_error,
    )
    pilot = governance_summary["pilot"]
    full_study = governance_summary["fullStudy"]
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()

    if integrity["authoritative"]:
        governance_prefix = "Repository status verified current."
    else:
        governance_prefix = (
            f"Repository status integrity is {integrity['state']}; handoff governance is "
            "not treated as authoritative."
        )

    # This milestone exposes health only. Governance authorization is reported separately;
    # it never enables simulation execution through this API.
    gate_reason = (
        f"{governance_prefix} Read-only health API only; simulation execution endpoints "
        "are not exposed. "
        f"Handoff pilot governance: {pilot.get('authorizationStatus', 'UNKNOWN')}. "
        f"Handoff full-study governance: {full_study.get('authorizationStatus', 'UNKNOWN')}."
    )

    return {
        "service": "mtg-deck-simulator-api",
        "status": "ok" if integrity["authoritative"] else "degraded",
        "apiVersion": "health-v2",
        "engineVersion": "malcolm-breeches-sim 0.1.0",
        "phase": "phase-c",
        "phaseLabel": "Phase C · Read-only API",
        "productionRunsEnabled": False,
        "fullStudyEnabled": False,
        "gateReason": gate_reason,
        "mode": "live",
        "checkedAt": timestamp,
        "statusSource": status_source,
        "statusIntegrity": integrity,
        "handoffGeneratedAt": handoff_generated_at,
        "handoffFetchError": handoff_error,
        "repository": repository_summary,
        "certifications": certification_summary,
        "governance": governance_summary,
    }


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "MTGHealth/2"

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", os.getenv("MTG_API_ALLOWED_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0]
        if path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, build_health_payload())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        if os.getenv("MTG_API_QUIET") == "1":
            return
        super().log_message(format, *args)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), HealthHandler)
    print(f"MTG health API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
