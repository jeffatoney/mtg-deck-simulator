from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "repository-handoff-v1"
DEFAULT_OWNER_ISSUE = 51
BINDING_PATHS = (
    "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json",
    "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json",
    "docs/spec/phase-c/PHASE_C_PILOT_AUTHORIZATION.md",
    ".github/workflows/phase-c-pilot.yml",
    ".github/workflows/phase-c-diagnostic.yml",
    "docs/audit/phase-a-certification/CERTIFICATION.json",
    "docs/audit/phase-b-certification/CERTIFICATION.json",
)


class HandoffError(RuntimeError):
    pass


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HandoffError(f"expected JSON object in {path}")
    return value


def _github_get(repo: str, endpoint: str, token: str) -> Any:
    url = f"https://api.github.com/repos/{repo}{endpoint}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mtg-deck-simulator-handoff-generator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HandoffError(f"GitHub API {endpoint} failed: {exc.code} {detail}") from exc


def _github_snapshot(
    repo: str, subject_commit: str, token: str, owner_issue: int
) -> dict[str, Any]:
    repo_data = _github_get(repo, "", token)
    pulls = _github_get(repo, "/pulls?state=open&per_page=100", token)
    issue = _github_get(repo, f"/issues/{owner_issue}", token)
    comments = _github_get(repo, f"/issues/{owner_issue}/comments?per_page=100", token)
    query = urllib.parse.urlencode({"head_sha": subject_commit, "per_page": 100})
    runs = _github_get(repo, f"/actions/runs?{query}", token)

    open_pulls = []
    for pull in pulls:
        open_pulls.append(
            {
                "number": pull["number"],
                "title": pull["title"],
                "draft": bool(pull.get("draft", False)),
                "base": pull["base"]["ref"],
                "head": pull["head"]["ref"],
                "head_sha": pull["head"]["sha"],
                "updated_at": pull["updated_at"],
                "url": pull["html_url"],
            }
        )

    latest_comments = []
    for comment in comments[-5:]:
        body = str(comment.get("body") or "").strip().replace("\r\n", "\n")
        latest_comments.append(
            {
                "id": comment["id"],
                "created_at": comment["created_at"],
                "updated_at": comment["updated_at"],
                "url": comment["html_url"],
                "excerpt": body[:600],
            }
        )

    subject_runs = []
    for run in runs.get("workflow_runs", []):
        subject_runs.append(
            {
                "id": run["id"],
                "name": run["name"],
                "run_number": run["run_number"],
                "event": run["event"],
                "status": run["status"],
                "conclusion": run["conclusion"],
                "head_sha": run["head_sha"],
                "created_at": run["created_at"],
                "updated_at": run["updated_at"],
                "url": run["html_url"],
            }
        )

    return {
        "default_branch": repo_data["default_branch"],
        "open_pull_requests": sorted(open_pulls, key=lambda item: item["number"]),
        "owner_review_issue": {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "updated_at": issue["updated_at"],
            "url": issue["html_url"],
            "latest_comments": latest_comments,
        },
        "subject_workflow_runs": subject_runs,
    }


def _governance_snapshot(config: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    authorization = config.get("authorization")
    full_study = config.get("full_study")
    pilot = config.get("pilot")
    game_model = config.get("game_model")
    paired = config.get("paired_analysis")
    sections = (authorization, full_study, pilot, game_model, paired)
    if not all(isinstance(value, dict) for value in sections):
        raise HandoffError("Phase C config is missing required machine-readable sections")

    pilot_allowed = authorization.get("execution_allowed")
    full_allowed = full_study.get("execution_allowed")
    if not isinstance(pilot_allowed, bool) or not isinstance(full_allowed, bool):
        raise HandoffError("execution_allowed values must be booleans")

    approval_status = approval.get("status")
    if pilot_allowed and approval_status != "APPROVED":
        raise HandoffError("pilot execution is allowed without an APPROVED approval record")
    if full_allowed and not pilot_allowed:
        raise HandoffError("full study is allowed while the pilot remains locked")

    return {
        "pilot": {
            "execution_allowed": pilot_allowed,
            "authorization_status": authorization.get("status"),
            "approval_status": approval_status,
            "approved_by": approval.get("approved_by"),
            "approved_at": approval.get("approved_at"),
            "standard_games": pilot.get("standard_games"),
            "exploratory_games": pilot.get("exploratory_games"),
            "standard_shards": pilot.get("standard_shards"),
            "exploratory_shards": pilot.get("exploratory_shards"),
        },
        "full_study": {
            "execution_allowed": full_allowed,
            "authorization_status": full_study.get("authorization_status"),
            "standard_games": full_study.get("standard_games"),
            "exploratory_games": full_study.get("exploratory_games"),
        },
        "study_model": {
            "opponent_interaction_modeled": game_model.get("opponent_interaction_modeled"),
            "blocking_modeled": game_model.get("blocking_modeled"),
            "opponent_wins_modeled": game_model.get("opponent_wins_modeled"),
            "through_turn": game_model.get("end_after_controlled_turn"),
            "paired_game_count": paired.get("paired_game_count"),
            "primary_outcome": paired.get("primary_outcome"),
            "secondary_outcome": paired.get("secondary_outcome"),
        },
    }


def _certification_snapshot(record: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "status": record.get("status"),
        "certified_content_commit": record.get("certified_content_commit"),
        "certified_repository_tree_sha": record.get("certified_repository_tree_sha"),
        "covered_content_sha256": record.get("covered_content_sha256"),
        "github_run_id": record.get("github_run_id"),
        "github_run_url": record.get("github_run_url"),
        "verifier_run_id": record.get("verifier_run_id"),
        "counts": record.get("counts"),
        "file_sha256": _sha256(path),
    }


def build_handoff(
    root: Path,
    repo: str,
    subject_ref: str,
    github_token: str | None,
    owner_issue: int = DEFAULT_OWNER_ISSUE,
) -> dict[str, Any]:
    subject_commit = _run_git(root, "rev-parse", f"{subject_ref}^{{commit}}")
    subject_tree = _run_git(root, "rev-parse", f"{subject_commit}^{{tree}}")
    status = _run_git(root, "status", "--porcelain", "--untracked-files=no")

    config_path = root / "docs/spec/phase-c/PHASE_C_PILOT_CONFIG.json"
    approval_path = root / "docs/spec/phase-c/PHASE_C_PILOT_APPROVAL.json"
    phase_a_path = root / "docs/audit/phase-a-certification/CERTIFICATION.json"
    phase_b_path = root / "docs/audit/phase-b-certification/CERTIFICATION.json"
    for relative in BINDING_PATHS:
        if not (root / relative).is_file():
            raise HandoffError(f"required handoff source is missing: {relative}")

    config = _load_json(config_path)
    approval = _load_json(approval_path)
    phase_a = _load_json(phase_a_path)
    phase_b = _load_json(phase_b_path)

    bindings = {
        relative: {"sha256": _sha256(root / relative)}
        for relative in BINDING_PATHS
    }

    github: dict[str, Any] | None = None
    if github_token:
        github = _github_snapshot(repo, subject_commit, github_token, owner_issue)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "generated_from_machine_state": True,
        "do_not_hand_edit": True,
        "repository": {
            "name": repo,
            "subject_ref": subject_ref,
            "subject_commit": subject_commit,
            "subject_tree": subject_tree,
            "tracked_worktree_dirty": bool(status),
        },
        "governance": _governance_snapshot(config, approval),
        "certifications": {
            "phase_a": _certification_snapshot(phase_a, phase_a_path),
            "phase_b": _certification_snapshot(phase_b, phase_b_path),
        },
        "bindings": bindings,
        "github": github,
    }


def _render_markdown(data: dict[str, Any]) -> str:
    repo = data["repository"]
    governance = data["governance"]
    phase_a = data["certifications"]["phase_a"]
    phase_b = data["certifications"]["phase_b"]
    github = data.get("github") or {}

    lines = [
        "# Current Repository Handoff",
        "",
        "> **Machine generated. Do not hand edit.** Regenerate from repository/GitHub state.",
        "",
        f"- Generated: `{data['generated_at_utc']}`",
        f"- Repository: `{repo['name']}`",
        f"- Subject ref: `{repo['subject_ref']}`",
        f"- Subject commit: `{repo['subject_commit']}`",
        f"- Subject tree: `{repo['subject_tree']}`",
        f"- Tracked worktree dirty: `{str(repo['tracked_worktree_dirty']).lower()}`",
        "",
        "## Governance locks",
        "",
        f"- Pilot execution allowed: `{str(governance['pilot']['execution_allowed']).lower()}`",
        f"- Pilot authorization status: `{governance['pilot']['authorization_status']}`",
        f"- Approval status: `{governance['pilot']['approval_status']}`",
        "- Full-study execution allowed: "
        f"`{str(governance['full_study']['execution_allowed']).lower()}`",
        f"- Full-study authorization status: `{governance['full_study']['authorization_status']}`",
        "",
        "## Frozen study model",
        "",
        "- STANDARD / EXPLORATORY: "
        f"`{governance['pilot']['standard_games']} / "
        f"{governance['pilot']['exploratory_games']}`",
        "- Shards: "
        f"`{governance['pilot']['standard_shards']} / "
        f"{governance['pilot']['exploratory_shards']}`",
        "- Opponent interaction modeled: "
        f"`{str(governance['study_model']['opponent_interaction_modeled']).lower()}`",
        f"- Blocking modeled: `{str(governance['study_model']['blocking_modeled']).lower()}`",
        "- Opponent wins modeled: "
        f"`{str(governance['study_model']['opponent_wins_modeled']).lower()}`",
        f"- Through controlled turn: `{governance['study_model']['through_turn']}`",
        f"- Paired environments: `{governance['study_model']['paired_game_count']}`",
        f"- Primary outcome: `{governance['study_model']['primary_outcome']}`",
        "",
        "## Durable certifications",
        "",
        f"- Phase A: `{phase_a['status']}`; "
        f"certified content `{phase_a['certified_content_commit']}`; "
        f"run `{phase_a['github_run_id']}`",
        f"- Phase B: `{phase_b['status']}`; "
        f"certified content `{phase_b['certified_content_commit']}`; "
        f"run `{phase_b['github_run_id']}`",
    ]

    if github:
        lines.extend(["", "## GitHub machine state", ""])
        default_branch = github.get("default_branch")
        if default_branch:
            lines.append(f"- Default branch: `{default_branch}`")
        runs = github.get("subject_workflow_runs", [])
        if runs:
            lines.append("- Workflow runs for subject commit:")
            for run in runs[:8]:
                lines.append(
                    f"  - `{run['name']}` #{run['run_number']} — "
                    f"`{run['status']}` / `{run['conclusion']}` — {run['url']}"
                )
        else:
            lines.append("- Workflow runs for subject commit: none returned")

        pulls = github.get("open_pull_requests", [])
        lines.extend(["", "### Open pull requests", ""])
        if pulls:
            for pull in pulls:
                lines.append(
                    f"- #{pull['number']} `{pull['head']}` -> `{pull['base']}` "
                    f"at `{pull['head_sha']}`"
                    f" — {'draft' if pull['draft'] else 'ready'} — {pull['title']}"
                )
        else:
            lines.append("- None")

        issue = github.get("owner_review_issue")
        if issue:
            lines.extend(
                [
                    "",
                    "### Owner review issue",
                    "",
                    f"- #{issue['number']} `{issue['state']}` — {issue['title']}",
                    f"- Updated: `{issue['updated_at']}`",
                    f"- URL: {issue['url']}",
                ]
            )
            comments = issue.get("latest_comments", [])
            if comments:
                comment_ids = ", ".join(str(item["id"]) for item in comments)
                lines.append(f"- Latest comment IDs: {comment_ids}")

    lines.extend(["", "## Binding digests", ""])
    for path, binding in data["bindings"].items():
        lines.append(f"- `{path}`: `{binding['sha256']}`")

    lines.extend(
        [
            "",
            "## Audit rule",
            "",
            "This handoff is evidence, not authorization and not a substitute for an "
            "independent repository refresh. An auditor must verify current main/PR "
            "heads, CI, certifications, governance locks, and owner decisions before "
            "recommending the next action.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_outputs(data: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "CURRENT_HANDOFF.json"
    md_path = output_dir / "CURRENT_HANDOFF.md"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(data), encoding="utf-8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the current repository handoff from machine state."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name form")
    parser.add_argument(
        "--subject-ref", default="HEAD", help="Git ref/commit the handoff describes"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--owner-issue", type=int, default=DEFAULT_OWNER_ISSUE)
    parser.add_argument(
        "--require-github",
        action="store_true",
        help="fail if GITHUB_TOKEN is unavailable instead of emitting a local-only handoff",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(_run_git(Path.cwd(), "rev-parse", "--show-toplevel"))
    token = os.environ.get("GITHUB_TOKEN")
    if args.require_github and not token:
        raise HandoffError("GITHUB_TOKEN is required for a repository handoff")
    data = build_handoff(root, args.repo, args.subject_ref, token, args.owner_issue)
    _write_outputs(data, args.output_dir)
    print(f"generated {args.output_dir / 'CURRENT_HANDOFF.json'}")
    print(f"generated {args.output_dir / 'CURRENT_HANDOFF.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
