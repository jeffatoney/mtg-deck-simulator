"""Source-validation CLI.

Exposes only frozen-source validation. Every rules-execution, coverage, and pilot
command that previously lived on the ``mtg-sim`` entry point is intentionally gone:
those commands ran the quarantined legacy engine, and the artifacts they produced are
classified ``PROHIBITED_AS_PHASE_A_EVIDENCE``.
"""

from __future__ import annotations

import typer

from mtg_sources.source_validation import validate_sources as run_source_validation
from mtg_sources.source_validation import write_inventory

app = typer.Typer(help="Frozen-source validation for the Malcolm and Breeches study.")


@app.callback()
def main() -> None:
    """Frozen-source validation for the Malcolm and Breeches study."""


@app.command("validate-sources")
def validate_sources(write_inventory_flag: bool = typer.Option(False, "--write-inventory")) -> None:
    """Validate frozen source inputs fail-closed."""
    if write_inventory_flag:
        write_inventory()
    result = run_source_validation()
    if not result.ok:
        typer.echo("Source validation failed:", err=True)
        for error in result.errors:
            typer.echo(f"- {error}", err=True)
        raise typer.Exit(1)
    typer.echo("Source validation passed.")
