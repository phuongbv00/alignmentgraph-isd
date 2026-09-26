"""The baseline-corrected sensitivity arm: own-scenario minus foreign-scenario
correspondence.

WHY IT EXISTS. A neural encoder puts unrelated texts of one domain well above
zero: measured on the tune slice (bge-m3), an agent's objectives score a
mean-max rectified cosine of 0.51-0.58 against the assessment items it wrote
for OTHER scenarios. More than half of family A's [0, 1] scale is therefore a
floor, and the floor is not the same for every agent — an agent writing in one
house style is closer to its own foreign items than one that does not. So
family A reads part of an agent's style as correspondence.

WHAT IT COMPUTES. For each triad edge (C2, C3, C4), agent ``a`` and scenario
``s``::

    own     = meanmax(L_s, R_s)
    foreign = mean over s' != s of meanmax(L_s, R_s')      (same agent, same run)
    signal  = own - foreign

``meanmax`` is the panel's own operation (mean over the left set of the max
rectified cosine into the right set). The foreign pool is the SAME agent in the
SAME run, so what is subtracted is that agent's own baseline — its template and
its style — and nothing about any other agent. There is no parameter: the
subtraction needs no constant, and every other scenario of the run is used.

WHAT IT IS NOT. Not a panel signal: the panel stays raw, and this is one arm of
the sensitivity star, deviating from the primary on exactly one axis. The file
it writes is the primary configuration's artifact with the three family-A
signals replaced; the Bloom-derived signals are copied unchanged, since a
baseline correction of a cosine cannot move a Bloom level. It does not remove
lexical echo either — an item copied from its objective is specific to that
scenario and survives the subtraction; see
``details.validation.objective_item_lexical_overlap`` for that.

Degenerate input follows the panel's convention: a set the agent did not
produce scores 0.0 with a note (no specificity), and an edge with no foreign
scenario to compare against is undefined.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .protocol import (
    extract_activities,
    extract_assessment_items,
    extract_objectives,
)

#: The three family-A signals as ``(signal, left set, right set)``, in the
#: panel's order.
CONTRAST_EDGES: tuple[tuple[str, str, str], ...] = (
    ("objective_assessment_similarity", "objectives", "assessment"),   # C2
    ("objective_activity_similarity", "objectives", "activities"),     # C3
    ("activity_assessment_similarity", "activities", "assessment"),    # C4
)


def _texts(addie_output: dict) -> dict[str, list[str]]:
    if isinstance(addie_output, dict) and "addie_output" in addie_output:
        addie_output = addie_output["addie_output"] or {}
    return {
        "objectives": [o["text"] for o in extract_objectives(addie_output)],
        "assessment": extract_assessment_items(addie_output),
        "activities": extract_activities(addie_output),
    }


def _unit(vectors: list[list[float]]) -> np.ndarray:
    if not vectors:
        return np.zeros((0, 0))
    matrix = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def mean_max(left: np.ndarray, right: np.ndarray) -> float:
    """Mean over ``left`` of the max rectified cosine into ``right`` (both
    unit-normalized rows) — the panel's family-A operation."""
    sims = np.clip(left @ right.T, 0.0, 1.0)
    return float(sims.max(axis=1).mean())


def contrast_scores(sets: dict[str, dict[str, np.ndarray]]) -> dict[str, dict[str, Any]]:
    """``scenario -> {signal: value, "details": {...}, "notes": [...]}`` for
    ONE agent of one run, from its unit-normalized vectors per scenario."""
    out: dict[str, dict[str, Any]] = {}
    for scenario, own_sets in sets.items():
        row: dict[str, Any] = {"details": {}, "notes": []}
        for signal, left_name, right_name in CONTRAST_EDGES:
            left, right = own_sets[left_name], own_sets[right_name]
            if not len(left) or not len(right):
                row[signal] = 0.0
                row["notes"].append(f"{signal} = 0.0: no {left_name if not len(left) else right_name} found")
                continue
            foreign = [mean_max(left, other[right_name])
                       for name, other in sets.items()
                       if name != scenario and len(other[right_name])]
            own = mean_max(left, right)
            if not foreign:
                row[signal] = None
                row["notes"].append(f"{signal} undefined: no other scenario to compare against")
                continue
            base = sum(foreign) / len(foreign)
            row[signal] = own - base
            row["details"][signal] = {"own": round(own, 6), "foreign": round(base, 6),
                                      "n_foreign": len(foreign)}
        out[scenario] = row
    return out


def score_contrast_run(scenario_dirs: list[Path], encoder, *, primary_name: str,
                       out_name: str, arm_key: str,
                       agent_ids: Optional[set[str]] = None) -> dict[str, list[dict]]:
    """Write ``out_name`` beside every scenario's primary artifact.

    ``encoder`` is the PRIMARY arm's encoder, built over its embedding cache,
    so the vectors are the ones the primary artifact was scored with. Returns
    ``agent -> [score dict per scenario]`` for the run's summary."""
    primaries: dict[Path, dict] = {}
    vectors: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for scenario_dir in scenario_dirs:
        path = scenario_dir / primary_name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        primaries[scenario_dir] = payload
        for agent in payload.get("agents", {}):
            if agent_ids and agent not in agent_ids:
                continue
            output_path = scenario_dir / f"{agent}_output.json"
            if not output_path.exists():
                continue
            texts = _texts(json.loads(output_path.read_text(encoding="utf-8")))
            flat = [t for name in ("objectives", "assessment", "activities") for t in texts[name]]
            encoded = encoder.encode(flat) if flat else []
            cursor, per_set = 0, {}
            for name in ("objectives", "assessment", "activities"):
                n = len(texts[name])
                per_set[name] = _unit(encoded[cursor:cursor + n])
                cursor += n
            vectors.setdefault(agent, {})[scenario_dir.name] = per_set

    results = {agent: contrast_scores(sets) for agent, sets in vectors.items()}
    per_agent: dict[str, list[dict]] = {}
    for scenario_dir, payload in primaries.items():
        out = copy.deepcopy(payload)
        out["baseline"] = arm_key
        for agent, score in out.get("agents", {}).items():
            row = results.get(agent, {}).get(scenario_dir.name)
            if row is None:
                continue
            for signal, _left, _right in CONTRAST_EDGES:
                score[signal] = row[signal]
            score.setdefault("details", {})["contrast"] = row["details"]
            score["notes"] = list(score.get("notes") or []) + row["notes"]
            per_agent.setdefault(agent, []).append(score)
        tmp = scenario_dir / f".{out_name}.tmp"
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(scenario_dir / out_name)
    return per_agent
