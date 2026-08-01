"""Dedicated Phase A clean-engine acceptance command."""

from __future__ import annotations

import typer

from mtg_verify.phase_a import verify_phase_a_run
from mtg_verify.phase_b import verify_phase_b_run

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Clean-engine verification commands."""


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


if __name__ == "__main__":
    app()
