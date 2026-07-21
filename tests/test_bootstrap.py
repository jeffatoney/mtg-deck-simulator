"""Bootstrap-level tests only; no game simulations are executed here."""

from mtg_sim import __version__


def test_package_imports() -> None:
    assert __version__ == "0.1.0"
