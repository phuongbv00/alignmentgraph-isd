"""What a run attempted: its scenarios, and which agents ran in each.

failure = 0 needs one definition of a failure, and this module is it: an agent
FAILED a scenario of a run when it was attempted there and left no scorable
output. The runner writes ``<agent>_log.txt`` whether the agent succeeds or
not and ``<agent>_output.json`` only on success, so "attempted" is the log (or
the output). An agent that was never run in a scenario -- a targeted repeat
that runs a subset of the roster, say -- did not fail it; that run is simply
not part of its series there.

A scenario is the run's when any agent was attempted in it, judged or not: a
scenario in which every agent failed has nothing to judge and no report, and
it still counts 0 for each of them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..judge import rundirs


@lru_cache(maxsize=None)
def _scan(run_dir: Path) -> tuple[tuple[str, Path, frozenset[str], frozenset[str]], ...]:
    out = []
    for scen_dir in rundirs.scenario_dirs(run_dir):
        attempted = frozenset(rundirs.attempted_agents(scen_dir))
        produced = frozenset(rundirs.produced_agents(scen_dir))
        out.append((scen_dir.name, scen_dir, attempted, produced))
    return tuple(out)


def scenarios(run_dir: Path) -> dict[str, Path]:
    """scenario id -> its directory, for every scenario any agent was attempted in."""
    return {sid: d for sid, d, _a, _p in _scan(Path(run_dir))}


def attempted(run_dir: Path, sid: str, agent: str) -> bool:
    return any(s == sid and agent in a for s, _d, a, _p in _scan(Path(run_dir)))


def produced(run_dir: Path, sid: str, agent: str) -> bool:
    return any(s == sid and agent in p for s, _d, _a, p in _scan(Path(run_dir)))


def forget() -> None:
    """Drop the cache, for a caller that writes run dirs and reads them again."""
    _scan.cache_clear()
