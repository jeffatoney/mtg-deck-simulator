#!/usr/bin/env python3
"""Documented placeholder for the approved Oracle snapshot refresh."""

from __future__ import annotations

import sys

MESSAGE = """Oracle snapshot refresh is intentionally disabled in Phase 1A.

Do not fetch live Oracle data during this phase. Follow docs/source/oracle/REFRESH_PROCESS.md
after explicit approval in a later source-refresh task.
"""


def main() -> int:
    sys.stderr.write(MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
