#!/usr/bin/env bash
set -euo pipefail

python --version
python -m pip install --upgrade pip uv

if [[ ! -f pyproject.toml ]]; then
  echo "ERROR: pyproject.toml is required at the repository root." >&2
  exit 1
fi

if [[ -f uv.lock ]]; then
  uv sync --frozen --all-extras
else
  uv sync --all-extras
fi

# Collection is a bootstrap smoke test. Once tests exist, collection failures
# are real failures and are not suppressed.
uv run pytest --collect-only -q
uv run python scripts/check_manifest.py
