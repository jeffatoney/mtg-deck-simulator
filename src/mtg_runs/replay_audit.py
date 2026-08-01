"""Fresh-process replay and worker-count invariance without policy decision code."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class FreshProcessReplayResult:
    state_hash: str
    transcript_sha256: str
    process_stdout: str


def replay_in_fresh_process(
    transcript: Mapping[str, Any] | Path,
    *,
    cwd: Path,
) -> FreshProcessReplayResult:
    """Re-execute a transcript in a new interpreter through the production replay path."""
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if isinstance(transcript, Path):
        path = transcript
        body = json.loads(path.read_text(encoding="utf-8"))
    else:
        body = dict(transcript)
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "transcript.json"
        path.write_bytes(_canonical(body) + b"\n")
    code = (
        "import json,sys;"
        "from mtg_kernel.hashing import state_hash;"
        "from mtg_kernel.replay import validate_replay;"
        "payload=json.load(open(sys.argv[1],encoding='utf-8'));"
        "print(state_hash(validate_replay(payload)))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if temporary is not None:
        temporary.cleanup()
    if completed.returncode != 0:
        raise ValueError(f"fresh-process replay failed: {completed.stdout}{completed.stderr}")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1 or len(lines[0]) != 64:
        raise ValueError("fresh-process replay did not return one state hash")
    return FreshProcessReplayResult(
        state_hash=lines[0],
        transcript_sha256=hashlib.sha256(_canonical(body)).hexdigest(),
        process_stdout=completed.stdout,
    )


def verify_worker_invariance(
    worker_outputs: Mapping[int, Sequence[Mapping[str, Any]]],
) -> str:
    """Require every worker count to produce the same canonical ordered raw records."""
    if not worker_outputs:
        raise ValueError("worker-invariance verification requires outputs")
    digests: dict[int, str] = {}
    for workers, records in worker_outputs.items():
        if workers < 1:
            raise ValueError("worker count must be positive")
        ordered = sorted(
            (dict(record) for record in records), key=lambda row: int(row["game_index"])
        )
        digests[workers] = hashlib.sha256(_canonical(ordered)).hexdigest()
    unique = set(digests.values())
    if len(unique) != 1:
        raise ValueError(f"worker-count outputs diverge: {digests}")
    return next(iter(unique))
