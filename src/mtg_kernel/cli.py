"""Clean-engine verification and separately authorized Phase C commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from mtg_runs.phase_c import PhaseCControlError, dry_run_phase_c, execute_phase_c_pilot
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


@app.command("phase-c-pilot")
def phase_c_pilot(
    confirmation: str = typer.Option(...),
    authorized_commit: str = typer.Option(...),
    expected_config_sha256: str = typer.Option(...),
    expected_workflow_sha256: str = typer.Option(...),
    output_root: Path = typer.Option(...),
) -> None:
    """Run only an exact owner-authorized 500/200 pilot through the clean engine."""
    del output_root  # The control plane must validate before creating this path.
    try:
        execute_phase_c_pilot(
            confirmation=confirmation,
            authorized_commit=authorized_commit,
            expected_config_sha256=expected_config_sha256,
            expected_workflow_sha256=expected_workflow_sha256,
        )
    except PhaseCControlError as exc:
        typer.echo(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        raise typer.Exit(2) from exc


if __name__ == "__main__":
    app()
