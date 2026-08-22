from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Iterable
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

    gate_reason = (
        f"{governance_prefix} Read-only API only; simulation execution endpoints are not exposed. "
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


def _type_line(
    supertypes: Iterable[str], card_types: Iterable[str], subtypes: Iterable[str]
) -> str:
    left = " ".join((*supertypes, *card_types)).strip()
    right = " ".join(subtypes).strip()
    return f"{left} — {right}" if right else left


def _face_type_line(face: dict[str, Any]) -> str:
    supertypes = tuple(str(value) for value in face.get("supertypes", ()))
    card_types = tuple(str(value) for value in face.get("card_types", face.get("types", ())))
    subtypes = tuple(str(value) for value in face.get("subtypes", ()))
    return _type_line(supertypes, card_types, subtypes)


def _display_oracle_text(spec: Any) -> str:
    if isinstance(spec.oracle_text, str):
        return spec.oracle_text
    sections: list[str] = []
    for face in spec.faces:
        name = str(face.get("name", "")).strip()
        mana_cost = str(face.get("mana_cost", "")).strip()
        oracle_text = face.get("oracle_text")
        if not name or not isinstance(oracle_text, str) or not oracle_text.strip():
            raise ValueError(f"incomplete display face for {spec.name}")
        header = f"{name} — {_face_type_line(face)}"
        if mana_cost:
            header = f"{header} {mana_cost}"
        sections.append(f"{header}\n{oracle_text}")
    if not sections:
        raise ValueError(f"card has no display Oracle text: {spec.name}")
    return "\n\n".join(sections)


def _display_type_line(spec: Any) -> str:
    if len(spec.faces) > 1:
        return " // ".join(_face_type_line(face) for face in spec.faces)
    return _type_line(spec.supertypes, spec.card_types, spec.subtypes)


def _primary_card_type(spec: Any) -> str:
    supported = (
        "Land",
        "Creature",
        "Artifact",
        "Enchantment",
        "Instant",
        "Sorcery",
        "Planeswalker",
    )
    types = set(str(value) for value in spec.card_types)
    for card_type in supported:
        if card_type in types:
            return card_type
    raise ValueError(f"unsupported display card type for {spec.name}: {sorted(types)}")


def _serialize_deck_card(spec: Any, *, card_id: str, commander: bool = False) -> dict[str, Any]:
    return {
        "id": card_id,
        "name": spec.name,
        "type": "Commander" if commander else _primary_card_type(spec),
        "manaValue": int(spec.mana_value),
        "colors": list(spec.colors),
        "roles": [],
        "oracleText": _display_oracle_text(spec),
        "manaCost": spec.mana_cost,
        "typeLine": _display_type_line(spec),
        "oracleId": spec.oracle_id,
        **({"isCommander": True} if commander else {}),
    }


def build_deck_payload() -> dict[str, Any]:
    """Serialize the exact clean-engine deck package without creating a game."""

    from mtg_cards.full_deck import load_full_deck_specs
    from mtg_deck import load_exact_deck_package

    package = load_exact_deck_package()
    specs = {spec.name: spec for spec in load_full_deck_specs().values()}

    cards: list[dict[str, Any]] = []
    library_position = 0
    for entry in package.library:
        spec = specs.get(entry.name)
        if spec is None:
            raise ValueError(f"missing frozen Oracle-backed spec for {entry.name}")
        for _ in range(entry.quantity):
            cards.append(
                _serialize_deck_card(
                    spec,
                    card_id=f"library-{library_position:03d}-{spec.oracle_id}",
                )
            )
            library_position += 1

    commanders: list[dict[str, Any]] = []
    commander_identity: set[str] = set()
    for commander_position, entry in enumerate(package.commanders):
        spec = specs.get(entry.name)
        if spec is None:
            raise ValueError(f"missing frozen Oracle-backed commander spec for {entry.name}")
        commanders.append(
            _serialize_deck_card(
                spec,
                card_id=f"commander-{commander_position}-{spec.oracle_id}",
                commander=True,
            )
        )
        commander_identity.update(spec.color_identity)

    if len(cards) != package.library_count or len(cards) != 98:
        raise ValueError("deck API did not serialize exactly 98 library cards")
    if len(commanders) != package.commander_count or len(commanders) != 2:
        raise ValueError("deck API did not serialize exactly two commanders")
    physical_ids = [card["id"] for card in (*cards, *commanders)]
    if len(physical_ids) != len(set(physical_ids)):
        raise ValueError("deck API produced duplicate physical card IDs")

    ordered_colors = [color for color in "WUBRG" if color in commander_identity]
    source_versions = sorted({spec.source_version for spec in specs.values()})
    if len(source_versions) != 1:
        raise ValueError("exact deck contains mixed Oracle source versions")

    return {
        "apiVersion": "deck-v1",
        "id": "deck-malcolm-breeches",
        "name": "Malcolm & Breeches",
        "identityLabel": "Malcolm and Breeches",
        "colorIdentity": ordered_colors,
        "format": "Commander (Partner)",
        "commanders": commanders,
        "cards": cards,
        "counts": {
            "library": package.library_count,
            "commanders": package.commander_count,
            "physicalCards": package.physical_card_count,
            "uniqueLibraryNames": len(package.library),
        },
        "source": {
            "package": "mtg_deck.load_exact_deck_package",
            "decklist": "docs/source/decklist.txt",
            "commanders": "docs/source/commanders.txt",
            "oracleSourceVersion": source_versions[0],
        },
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "MTGReadOnlyAPI/1"

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
        if path == "/api/deck":
            try:
                payload = build_deck_payload()
            except Exception as exc:  # noqa: BLE001 - fail closed at the HTTP boundary
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "status": "unavailable",
                        "apiVersion": "deck-v1",
                        "error": type(exc).__name__,
                    },
                )
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        if os.getenv("MTG_API_QUIET") == "1":
            return
        super().log_message(format, *args)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"MTG read-only API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
