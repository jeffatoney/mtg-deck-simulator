"""Clean-engine verification and separately authorized Phase C commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from mtg_runs.phase_c import (
    PhaseCControlError,
    aggregate_phase_c_pilot_artifacts,
    dry_run_phase_c,
    execute_phase_c_shard,
    validate_execution_authorization,
)
from mtg_verify.phase_a import verify_phase_a_run
from mtg_verify.phase_b import verify_phase_b_run

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Clean-engine verification and locked Phase C commands."""


@app.command("verify-phase-a")
def verify_phase_a() -> None:
    """Run the clean Phase A gate and write one immutable result."""
    status = verify_phase_a_run()
    if status:
        raise typer.Exit(status)


@app.command("verify-phase-b")
def verify_phase_b() -> None:
    """Run the complete Phase B gate and write one immutable result."""
    status = verify_phase_b_run()
    if status:
        raise typer.Exit(status)


@app.command("phase-c-dry-run")
def phase_c_dry_run() -> None:
    """Validate the locked Phase C control plane without running a game."""
    try:
        report = dry_run_phase_c()
    except PhaseCControlError as exc:
        typer.echo(json.dumps({"status": "FAIL", "reason": str(exc)}, indent=2))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))


@app.command("phase-c-authorization-check")
def phase_c_authorization_check(
    confirmation: str = typer.Option(...),
    implementation_commit: str = typer.Option(...),
    activation_commit: str = typer.Option(...),
    expected_locked_config_sha256: str = typer.Option(...),
    expected_workflow_sha256: str = typer.Option(...),
) -> None:
    """Validate owner activation and exact implementation bindings without running a game."""
    try:
        config, approval, seeds, context = validate_execution_authorization(
            confirmation=confirmation,
            implementation_commit=implementation_commit,
            activation_commit=activation_commit,
            expected_locked_config_sha256=expected_locked_config_sha256,
            expected_workflow_sha256=expected_workflow_sha256,
        )
    except PhaseCControlError as exc:
        typer.echo(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        raise typer.Exit(2) from exc
    typer.echo(
        json.dumps(
            {
                "status": "PASS",
                "implementation_commit": context.implementation_commit,
                "implementation_tree": context.implementation_tree,
                "activation_commit": context.activation_commit,
                "locked_config_sha256": context.locked_config_sha256,
                "workflow_sha256": context.workflow_sha256,
                "approval_sha256": approval.sha256,
                "standard_seed_sha256": seeds.standard_sha256,
                "exploratory_seed_sha256": seeds.exploratory_sha256,
                "standard_shards": config.standard_shards,
                "exploratory_shards": config.exploratory_shards,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("phase-c-pilot")
def phase_c_pilot(
    confirmation: str = typer.Option(...),
    implementation_commit: str = typer.Option(...),
    activation_commit: str = typer.Option(...),
    expected_locked_config_sha256: str = typer.Option(...),
    expected_workflow_sha256: str = typer.Option(...),
    mode: str = typer.Option(...),
    shard_index: int = typer.Option(...),
    output_root: Path = typer.Option(...),
) -> None:
    """Run one exact owner-authorized Phase C pilot shard through the clean engine."""
    try:
        report = execute_phase_c_shard(
            confirmation=confirmation,
            implementation_commit=implementation_commit,
            activation_commit=activation_commit,
            expected_locked_config_sha256=expected_locked_config_sha256,
            expected_workflow_sha256=expected_workflow_sha256,
            mode=mode.upper(),
            shard_index=shard_index,
            output_root=output_root,
        )
    except (PhaseCControlError, ValueError) as exc:
        typer.echo(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(dict(report), indent=2, sort_keys=True))


@app.command("phase-c-aggregate")
def phase_c_aggregate(
    confirmation: str = typer.Option(...),
    implementation_commit: str = typer.Option(...),
    activation_commit: str = typer.Option(...),
    expected_locked_config_sha256: str = typer.Option(...),
    expected_workflow_sha256: str = typer.Option(...),
    shard_root: Path = typer.Option(...),
    output_root: Path = typer.Option(...),
) -> None:
    """Validate the exact 500/200 shard set and write one immutable aggregate."""
    try:
        report = aggregate_phase_c_pilot_artifacts(
            confirmation=confirmation,
            implementation_commit=implementation_commit,
            activation_commit=activation_commit,
            expected_locked_config_sha256=expected_locked_config_sha256,
            expected_workflow_sha256=expected_workflow_sha256,
            shard_root=shard_root,
            output_root=output_root,
        )
    except (PhaseCControlError, ValueError) as exc:
        typer.echo(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(dict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
