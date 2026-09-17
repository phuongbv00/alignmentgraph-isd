"""Pooling token and wall-clock cost per (model, agent) cell.

Cost is reported, never used to adjust a quality score: the proposed system is
far more expensive than the baselines and that trade-off is a finding, not a
confound to be normalised away.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..runs import iter_scenario_dirs
from ..util import mean as _mean
from ..util import sd as _sd

def pool_tokens(run_dirs_by_model: dict[str, list[Path]],
                agents: list[str]) -> Optional[dict]:
    """Pool per-agent token usage / runtime from *_trajectory.json metadata.

    (Absorbed from the deleted 5_aggregate_benchmark_results.py "tokens"
    section, in pooled form: mean across runs per scenario, then across
    scenarios.) Operational metadata only -- never part of Total or the
    alignment endpoints.
    """
    out_models = {}
    found_any = False
    for label, run_dirs in run_dirs_by_model.items():
        # vals[agent][field][scenario] = [per-run values]
        vals: dict[str, dict[str, dict[str, list[float]]]] = {}
        for run_dir in run_dirs:
            for sid, scen_dir in iter_scenario_dirs(run_dir):
                for agent in agents:
                    traj = scen_dir / f"{agent}_trajectory.json"
                    if not traj.exists():
                        continue
                    try:
                        md = json.loads(traj.read_text(encoding="utf-8")).get("metadata") or {}
                    except (json.JSONDecodeError, OSError):
                        continue
                    tu = md.get("token_usage") or {}
                    fields = {
                        "prompt_tokens": tu.get("prompt_tokens"),
                        "completion_tokens": tu.get("completion_tokens"),
                        "total_tokens": tu.get("total_tokens"),
                        "llm_calls": tu.get("llm_calls"),
                        "execution_time_seconds": md.get("execution_time_seconds"),
                    }
                    for field, v in fields.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            found_any = True
                            vals.setdefault(agent, {}).setdefault(field, {}) \
                                .setdefault(sid, []).append(float(v))
        if vals:
            out_models[label] = {
                agent: {
                    field: {
                        "n_scenarios": len(by_scen),
                        "mean": _mean([_mean(v) for v in by_scen.values()]),
                        "sd_across_scenarios": _sd([_mean(v) for v in by_scen.values()]),
                    }
                    for field, by_scen in sorted(fields_map.items())
                }
                for agent, fields_map in sorted(vals.items())
            }
    if not found_any:
        return None
    return {
        "source": "*_trajectory.json metadata (token_usage + execution_time), "
                  "pooled mean across runs then scenarios; operational metadata only",
        "models": out_models,
    }
