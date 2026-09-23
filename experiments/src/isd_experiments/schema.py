"""The pooled-JSON contract: what pooling writes and every generator reads.

Eight consumers reach into this structure (`pooled["models"][i]["agents"][a]
["mean_addie"]` and deeper). None of them checked its shape, so a pooled file
written by an older version, or truncated by an interrupted run, failed several
hundred lines later with a KeyError naming a leaf -- which says nothing about
the actual problem. ``load`` fails at the door instead, naming what is missing.
"""

from __future__ import annotations

from . import paths

import json
from pathlib import Path
from typing import Any

from . import util

#: Bumped when a consumer would misread an older file. Not a general
#: versioning scheme -- it exists so a stale pooled file is refused rather than
#: silently half-read.
SCHEMA_VERSION = 1

#: Top-level keys pooling always writes. `comparisons` is NOT among them --
#: it is per-model, because every comparison is made within one model size.
REQUIRED_TOP = ("generated_at", "config", "models")

#: Per-model keys. `comparisons` holds the paired tests for that size.
REQUIRED_MODEL = ("label", "agents", "comparisons")

#: Per-agent keys the table and figure generators index directly.
REQUIRED_AGENT = (
    "mean_addie", "mean_total", "mean_traj",
    "sd_addie_across_scenarios", "sd_total_across_scenarios", "sd_traj_across_scenarios",
    "n_scenarios_complete",
)


class PooledError(SystemExit):
    """A pooled file that cannot be read the way the generators read it."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise PooledError(message)


def validate(pooled: dict, source: str = "<pooled>") -> dict:
    """Check the shape every consumer assumes. Returns the document."""
    _require(isinstance(pooled, dict), f"{source}: not a JSON object")
    missing = [k for k in REQUIRED_TOP if k not in pooled]
    _require(not missing, f"{source}: missing top-level key(s): {', '.join(missing)}")
    _require(isinstance(pooled["models"], list) and pooled["models"],
             f"{source}: 'models' is empty -- nothing was pooled")


    for i, model in enumerate(pooled["models"]):
        where = f"{source}: models[{i}]"
        _require(isinstance(model, dict), f"{where}: not an object")
        gaps = [k for k in REQUIRED_MODEL if k not in model]
        _require(not gaps, f"{where}: missing {', '.join(gaps)}")
        agents = model.get("agents")
        _require(isinstance(agents, dict) and agents,
                 f"{where} ({model.get('label')}): 'agents' is empty")
        for agent, row in agents.items():
            gaps = [k for k in REQUIRED_AGENT if k not in row]
            _require(not gaps,
                     f"{where} agent {agent!r}: missing {', '.join(gaps)}. "
                     f"This file was written by a different pooling version; re-pool it.")
    return pooled


def optional_layers(pooled: dict) -> list[str]:
    """Layers present only because their input was: alignment scoring ran,
    trajectories carried token counts. Absence is a state to report, not an
    error -- pooling before those steps is a legitimate partial run.
    """
    return [k for k in ("alignment", "token_usage", "interaction", "failure_rates")
            if pooled.get(k)]


def load(path: Path) -> dict:
    """Read and validate a pooled file."""
    if not path.exists():
        raise PooledError(
            f"No pooled file at {path}.\n"
            f"  Produce it with `{paths.cli()} pool comparison` (or `pool ablation`)."
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PooledError(f"{path}: not valid JSON ({exc}). Re-pool it.") from None
    return validate(doc, str(path))


def write(path: Path, payload: dict) -> None:
    """Write a pooled file: atomic, strict JSON, non-finite floats as null.

    ``allow_nan=False`` is the point. ``json.dumps`` otherwise emits bare
    ``NaN``/``Infinity`` tokens, which Python reads back but jq, most JS and
    most typed loaders reject -- and NaN reaches this structure legitimately,
    whenever a cell has nothing to average.
    """
    util.write_json_atomic(path, payload)


def agent_row(pooled: dict, label: str, agent: str) -> dict[str, Any]:
    """One (model, agent) cell, or {} when that cell was never scored."""
    for model in pooled.get("models", []):
        if model.get("label") == label:
            return model.get("agents", {}).get(agent, {})
    return {}


def labels(pooled: dict) -> list[str]:
    """Model labels in pooled order (smallest model first)."""
    return [m["label"] for m in pooled.get("models", [])]
