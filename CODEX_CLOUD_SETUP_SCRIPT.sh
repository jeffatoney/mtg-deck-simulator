#!/usr/bin/env bash
set -euo pipefail
python --version
python -m pip install --upgrade pip uv
if [[ -f uv.lock ]]; then
  uv sync --frozen --all-extras
else
  uv sync --all-extras
fi
uv run pytest --collect-only -q || true
