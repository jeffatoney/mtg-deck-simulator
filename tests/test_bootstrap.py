"""Bootstrap-level tests only; no game simulations are executed here."""

from mtg_sources import __version__


def test_package_imports() -> None:
    assert __version__ == "2.0.0"
