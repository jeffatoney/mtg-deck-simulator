# Lovable Health API Boundary

## Purpose

This endpoint is the first network boundary between the Lovable front end and the Python simulator repository. It is intentionally read-only.

The endpoint may report repository certification and governance state, but it must not execute Magic rules, mutate game state, run policy search, start the Phase C pilot, or start the full study.

## Endpoints

- `GET /healthz` returns a minimal process-liveness response.
- `GET /api/health` returns the front-end health contract.

The detailed health response includes the fields already consumed by the Lovable `HealthStatus` interface:

- `engineVersion`
- `phase`
- `phaseLabel`
- `productionRunsEnabled`
- `fullStudyEnabled`
- `gateReason`
- `mode`
- `checkedAt`

It also reports repository provenance, certification summaries, governance summaries, the status source, and a `statusIntegrity` object.

## Authority, freshness, and conflict detection

The preferred status source is the generated machine handoff at:

`handoff/current:docs/audit/handoff/CURRENT_HANDOFF.json`

The server does not present that handoff as authoritative merely because it is reachable. It independently checks two repository signals:

1. The handoff `repository.subject_commit` must equal the current `main` head commit.
2. The handoff pilot approval state and approved game counts must agree with the Phase C pilot-activation approval record at `phase-c/pilot-activation:docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json`.

These remote checks are cached briefly to avoid excessive unauthenticated GitHub API traffic.

`statusIntegrity.state` is one of:

- `CURRENT`: independent signals agree with the handoff. `statusIntegrity.authoritative` is `true`.
- `STALE`: the handoff subject commit is behind or otherwise differs from current `main`.
- `CONFLICT`: durable governance signals disagree, such as a handoff saying owner approval is pending while the pilot-activation approval record says `APPROVED`.
- `UNVERIFIED`: one or more independent signals could not be checked.

For `STALE`, `CONFLICT`, or `UNVERIFIED`, the top-level `status` is `degraded`, `statusIntegrity.authoritative` is `false`, and `gateReason` explicitly says handoff governance is not being treated as authoritative. The response still includes the handoff values for diagnosis, but callers must not present them as current repository truth.

If the handoff cannot be reached or parsed, the service falls back to committed local certification and Phase C approval files and identifies the response as `local-repository-fallback`. That fallback is `UNVERIFIED` unless independent signals establish otherwise.

## Fail-closed behavior

The API remains fail-closed regardless of governance state or status integrity:

- `productionRunsEnabled` is `false`.
- `fullStudyEnabled` is `false`.
- No simulation execution route exists in this milestone.

A future change must separately implement and review execution endpoints before the UI may enable them. Repository governance authorization alone does not create an executable API.

## Local run

From the repository root:

```bash
python scripts/serve_health_api.py
```

Defaults:

- host: `0.0.0.0`
- port: `8000`

Environment variables:

- `HOST`: bind host
- `PORT`: bind port
- `MTG_API_ALLOWED_ORIGIN`: CORS origin, default `*`
- `MTG_API_QUIET=1`: suppress request logging

Example:

```bash
curl http://127.0.0.1:8000/api/health
```

## Deployment contract

Any HTTPS host that can clone the repository and run Python 3.12 can serve this milestone. The start command is:

```bash
python scripts/serve_health_api.py
```

The host must expose its assigned port through the `PORT` environment variable.

The Lovable app should configure a single base URL and use that URL only for `getHealth()` in the first integration milestone. Deck data and simulation outputs remain on their existing source-backed/mock paths until separately migrated.
