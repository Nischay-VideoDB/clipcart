"""Versioned, fixture-backed records for ClipCart's public prepared showcase."""

from __future__ import annotations

import copy
import json
from pathlib import Path

_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "public" / "prepared_runs.v1.json"


def _load_prepared_runs() -> tuple[dict, ...]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("mode") != "prepared-illustrative":
        raise RuntimeError("Prepared ClipCart fixture has an unsupported schema.")
    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) < 3:
        raise RuntimeError("Prepared ClipCart fixture must include three curated runs.")
    return tuple(runs)


PREPARED_RUNS = _load_prepared_runs()
# Compatibility export for local callers that still expect one illustrative result set.
PREPARED_ILLUSTRATIVE_CLIPS = copy.deepcopy(PREPARED_RUNS[0]["clips"])


def prepared_runs() -> list[dict]:
    """Return all immutable prepared run records without sharing mutable state."""
    return copy.deepcopy(list(PREPARED_RUNS))


def prepared_run(run_id: str | None) -> dict:
    """Return a selected prepared run, defaulting to the first curated example."""
    selected = run_id or PREPARED_RUNS[0]["id"]
    for run in PREPARED_RUNS:
        if run["id"] == selected:
            return copy.deepcopy(run)
    raise KeyError(selected)
