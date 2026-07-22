"""Command-line entry point for repository tooling."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import typer

from mtg_sim.phase5a_cards import ASSIGNED_CARDS
from mtg_sim.offline_sources import audit_offline_snapshot
from mtg_sim.source_validation import validate_sources as run_source_validation
from mtg_sim.source_validation import write_inventory

app = typer.Typer(help="Malcolm and Breeches simulator tooling.")


@app.callback()
def main() -> None:
    """Malcolm and Breeches simulator tooling."""


@app.command("validate-sources")
def validate_sources(write_inventory_flag: bool = typer.Option(False, "--write-inventory")) -> None:
    """Validate frozen Phase 1A source inputs fail-closed."""
    if write_inventory_flag:
        write_inventory()
    result = run_source_validation()
    if not result.ok:
        typer.echo("Source validation failed:", err=True)
        for error in result.errors:
            typer.echo(f"- {error}", err=True)
        raise typer.Exit(1)
    typer.echo("Source validation passed.")


@app.command("validate-coverage")
def validate_coverage(path: Path = typer.Option(Path("card_coverage.csv"), "--path")) -> None:
    """Validate Phase 5A card coverage declarations fail-closed."""
    if not path.exists():
        typer.echo(f"Coverage validation failed: missing {path}", err=True)
        raise typer.Exit(1)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    by_name = {row["card_name"]: row for row in rows}
    missing = sorted(ASSIGNED_CARDS.difference(by_name))
    bad = sorted(
        name
        for name in ASSIGNED_CARDS.intersection(by_name)
        if by_name[name]["coverage_status"] not in {"FULL", "BASELINE_EXPLICIT"}
        or not by_name[name]["handler_id"]
        or not by_name[name]["test_file"]
    )
    if missing or bad:
        typer.echo("Coverage validation failed:", err=True)
        for name in missing:
            typer.echo(f"- missing coverage row: {name}", err=True)
        for name in bad:
            typer.echo(f"- incomplete coverage row: {name}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Coverage validation passed for {len(ASSIGNED_CARDS)} Phase 5A cards.")


@app.command("verify-rules")
def verify_rules(output: Path = typer.Option(..., "--output")) -> None:
    """Write the current rules competency gate report without running pilots."""
    output.mkdir(parents=True, exist_ok=True)
    audit = audit_offline_snapshot()
    report = {
        "status": "NO_GO",
        "reason": "offline card-data gates pass, but the repository still lacks complete executable behavior implementations and passing rules-engine validation for every declared behavior",
        "offline_snapshot_audit": audit,
    }
    (output / "rules_competency_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    typer.echo(f"Rules competency report written to {output / 'rules_competency_report.json'}")
    raise typer.Exit(1)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo("0.1.0")


if __name__ == "__main__":
    app()
