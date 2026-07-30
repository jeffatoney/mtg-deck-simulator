"""Compatibility wrapper for the packaged Phase A verifier."""

from __future__ import annotations

from mtg_verify.phase_a import verify_phase_a_run


if __name__ == "__main__":
    raise SystemExit(verify_phase_a_run())
