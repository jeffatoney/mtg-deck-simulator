"""Shared durable-certification provenance checks.

Content binding is verified locally by the phase-specific checkers.  In GitHub
Actions this module additionally proves that the recorded commit is the head of
the recorded workflow run and that the verifier/candidate producer steps
succeeded in that run.  When the exact certification-candidate artifact remains
available, its JSON must equal the committed record byte-for-semantics.
"""

from __future__ import annotations

import io
import json
import os
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any


def _request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"GitHub API response is not an object: {url}")
    return value


def _request_bytes(url: str, token: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def _job_steps(jobs_payload: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    jobs = jobs_payload.get("jobs", [])
    if not isinstance(jobs, Sequence):
        return result
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, Sequence):
            continue
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            name = str(step.get("name", ""))
            if name:
                result[name] = str(step.get("conclusion", ""))
    return result


def verify_github_actions_candidate(
    record: Mapping[str, Any],
    *,
    phase: str,
    required_steps: Sequence[str],
    allow_unpublished_current_run: bool = False,
) -> list[str]:
    """Return provenance errors; do nothing outside GitHub Actions.

    The exact candidate artifact check is best-effort only for artifact expiry:
    if the artifact is listed and not expired it must exactly match the committed
    record.  Run/head and producer-step checks are always mandatory in CI.
    """

    if os.environ.get("GITHUB_ACTIONS") != "true":
        return []
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repository:
        return ["GitHub Actions provenance check is missing GITHUB_TOKEN or GITHUB_REPOSITORY"]

    run_id = str(record.get("github_run_id", ""))
    commit = str(record.get("certified_content_commit", ""))
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    try:
        run = _request_json(f"{api}/repos/{repository}/actions/runs/{run_id}", token)
        if str(run.get("head_sha", "")) != commit:
            return ["recorded GitHub Actions run did not execute the certified content commit"]
        jobs = _request_json(
            f"{api}/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100", token
        )
        steps = _job_steps(jobs)
        errors = [
            f"recorded GitHub Actions run lacks successful producer step: {name}"
            for name in required_steps
            if steps.get(name) != "success"
        ]

        artifacts = _request_json(
            f"{api}/repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100", token
        )
        artifact_name = f"{phase}-certification-candidate-{commit}"
        raw_artifacts = artifacts.get("artifacts", [])
        candidate = None
        if isinstance(raw_artifacts, Sequence):
            candidate = next(
                (
                    item
                    for item in raw_artifacts
                    if isinstance(item, Mapping) and str(item.get("name", "")) == artifact_name
                ),
                None,
            )
        current_run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
        if candidate is None:
            if not (allow_unpublished_current_run and run_id == current_run_id):
                errors.append("certification candidate artifact is missing from the recorded run")
        elif not bool(candidate.get("expired")):
            archive_url = str(candidate.get("archive_download_url", ""))
            if not archive_url:
                errors.append("certification candidate artifact has no download URL")
            else:
                raw = _request_bytes(archive_url, token)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    names = [name for name in archive.namelist() if name.endswith("CERTIFICATION.json")]
                    if len(names) != 1:
                        errors.append("certification candidate artifact does not contain one record")
                    else:
                        candidate_record = json.loads(archive.read(names[0]).decode("utf-8"))
                        if candidate_record != dict(record):
                            errors.append(
                                "committed certification record differs from the CI-produced candidate"
                            )
        return errors
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile, urllib.error.URLError) as exc:
        return [f"unable to verify GitHub Actions certification provenance: {exc}"]
