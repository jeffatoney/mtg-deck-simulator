"""Command-line entry point for repository tooling."""

from __future__ import annotations

import csv
from pathlib import Path

import typer

from mtg_sim.phase5a_cards import ASSIGNED_CARDS
from mtg_sim.rules_competency import run_competency
from mtg_sim.offline_sources import build_simulation_deck
from mtg_sim.pilot import dry_run as run_pilot_dry_run
from mtg_sim.pilot import run as run_pilot
from mtg_sim.source_validation import validate_sources as run_source_validation
from mtg_sim.executable_adapters import validate_executable_coverage as run_executable_coverage
from mtg_sim.executable_adapters import write_report as write_executable_report
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
    deck = build_simulation_deck()
    commander_names = {entry.name for entry in deck.commanders}
    library_missing = [card.name for card in deck.library if card.name not in by_name]
    commander_missing = [name for name in commander_names if name not in by_name]
    blocked = [row["card_name"] for row in rows if row["coverage_status"] == "BLOCKED"]
    silent_fallbacks = [row["card_name"] for row in rows if not row["handler_id"]]
    if library_missing or commander_missing or blocked or silent_fallbacks:
        typer.echo("Coverage validation failed:", err=True)
        for name in sorted(set(library_missing + commander_missing)):
            typer.echo(f"- missing coverage row: {name}", err=True)
        for name in blocked:
            typer.echo(f"- blocked coverage row: {name}", err=True)
        for name in silent_fallbacks:
            typer.echo(f"- silent fallback row: {name}", err=True)
        raise typer.Exit(1)
    typer.echo(
        "Coverage validation passed: "
        f"{len(deck.library)} of {len(deck.library)} library cards covered; "
        f"{len(deck.commanders)} of {len(deck.commanders)} commanders covered; "
        "0 blocked; 0 missing; 0 silent fallbacks."
    )


@app.command("validate-executable-coverage")
def validate_executable_coverage(
    output: Path = typer.Option(
        Path("artifacts/coverage/full-executable-coverage.json"), "--output"
    ),
) -> None:
    """Validate executable action-adapter coverage fail-closed and write report."""
    report = write_executable_report(output)
    errors = run_executable_coverage()
    if errors:
        typer.echo("Executable coverage validation failed:", err=True)
        for error in errors:
            typer.echo(f"- {error}", err=True)
        raise typer.Exit(1)
    typer.echo(
        "Executable coverage validation passed: "
        f"{report['expected_unique_card_count']} expected unique cards; "
        f"{report['executable_adapter_count']} executable; "
        f"{report['blocked_adapter_count']} blocked. "
        f"Report written to {output}"
    )


@app.command("verify-rules")
def verify_rules(output: Path = typer.Option(..., "--output")) -> None:
    """Run the complete Phase 6 rules competency gate and write an immutable report."""
    run_dir = run_competency(output)
    typer.echo(f"Rules competency report written to {run_dir / 'rules_competency_report.json'}")


@app.command("pilot")
def pilot(
    config: Path = typer.Option(..., "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    smoke: bool = typer.Option(False, "--smoke"),
) -> None:
    """Plan or execute the Phase 9B pilot pipeline."""
    if dry_run:
        if smoke:
            typer.echo("--dry-run and --smoke are mutually exclusive", err=True)
            raise typer.Exit(1)
        manifest_path = run_pilot_dry_run(config)
        typer.echo(f"Pilot dry-run manifest written to {manifest_path}")
        return
    manifest_path = run_pilot(config, smoke=smoke)
    typer.echo(f"Pilot execution artifacts written under {manifest_path.parent}")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo("0.1.0")


if __name__ == "__main__":
    app()
