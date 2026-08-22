from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

REPOSITORY = "jeffatoney/mtg-deck-simulator"
HANDOFF_URL = (
    "https://raw.githubusercontent.com/jeffatoney/mtg-deck-simulator/"
    "handoff/current/docs/audit/handoff/CURRENT_HANDOFF.json"
)
ROOT = Path(__file__).resolve().parents[1]
PILOT_APPROVAL_PATH = ROOT / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
PHASE_A_CERT_PATH = ROOT / "docs/audit/phase-a-certification/CERTIFICATION.json"
PHASE_B_CERT_PATH = ROOT / "docs/audit/phase-b-certification/CERTIFICATION.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return value


def _fetch_handoff(timeout_seconds: float = 2.5) -> dict[str, Any]:
    request = Request(HANDOFF_URL, headers={"User-Agent": "mtg-deck-simulator-health/1"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed HTTPS URL
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("Current handoff was not a JSON object")
    return value


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


def build_health_payload(
    *,
    handoff: dict[str, Any] | None = None,
    fetch_remote_handoff: bool = True,
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

    pilot = governance_summary["pilot"]
    full_study = governance_summary["fullStudy"]
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()

    # This milestone exposes health only. Governance authorization is reported separately;
    # it never enables simulation execution through this API.
    gate_reason = (
        "Read-only health API only; simulation execution endpoints are not exposed. "
        f"Pilot governance: {pilot.get('authorizationStatus', 'UNKNOWN')}. "
        f"Full-study governance: {full_study.get('authorizationStatus', 'UNKNOWN')}."
    )

    return {
        "service": "mtg-deck-simulator-api",
        "status": "ok",
        "apiVersion": "health-v1",
        "engineVersion": "malcolm-breeches-sim 0.1.0",
        "phase": "phase-c",
        "phaseLabel": "Phase C · Read-only API",
        "productionRunsEnabled": False,
        "fullStudyEnabled": False,
        "gateReason": gate_reason,
        "mode": "live",
        "checkedAt": timestamp,
        "statusSource": status_source,
        "handoffGeneratedAt": handoff_generated_at,
        "handoffFetchError": handoff_error,
        "repository": repository_summary,
        "certifications": certification_summary,
        "governance": governance_summary,
    }


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "MTGHealth/1"

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
