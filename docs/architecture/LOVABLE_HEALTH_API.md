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

It also reports repository provenance, certification summaries, governance summaries, and the status source.

## Authority and fail-closed behavior

The preferred status source is the generated machine handoff at:

`handoff/current:docs/audit/handoff/CURRENT_HANDOFF.json`

The server fetches that public repository artifact over HTTPS. If the handoff cannot be reached or parsed, it falls back to committed local certification and Phase C approval files and identifies the response as `local-repository-fallback`.

The API remains fail-closed regardless of governance state:

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

The Lovable app should configure a single base URL (for example `SIMULATOR_API_URL`) and use that URL only for `getHealth()` in the first integration milestone. Deck data and simulation outputs remain on their existing source-backed/mock paths until separately migrated.
