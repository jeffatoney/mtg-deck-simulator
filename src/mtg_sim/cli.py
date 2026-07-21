"""Command-line entry point for repository bootstrap validation."""

from __future__ import annotations

import typer

app = typer.Typer(help="Malcolm and Breeches simulator tooling.")


@app.callback()
def main() -> None:
    """Malcolm and Breeches simulator tooling."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo("0.1.0")


if __name__ == "__main__":
    app()
