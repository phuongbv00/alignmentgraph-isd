"""Two guards on the boundary between "a run was accepted" and "a run exists".

The registry is how a run in flight is reached, so what goes into it and what
stays in it decide whether a program can be written to again and how much of a
finished run this process keeps holding.
"""
from __future__ import annotations

from alignmentgraph_isd.server import artifacts
from alignmentgraph_isd.server.events import TERMINAL_RUNS_RETAINED, RunRegistry
from alignmentgraph_isd.server.models import RunStatus


def _finished(registry: RunRegistry, run_id: str, program_id: str = "P") -> None:
    registry.create(run_id, program_id).finish(RunStatus.SUCCEEDED)


def test_the_registry_keeps_only_the_recent_finished_runs():
    """Each finished run holds its graph dump and every transcript, so keeping
    them for the life of the process is megabytes per run that nothing reads
    again. An evicted run is still served, from disk, by the replay path in the
    runs router. Eviction happens when a run is CREATED, so the one just
    finished is still there."""
    registry = RunRegistry()
    for index in range(TERMINAL_RUNS_RETAINED + 3):
        _finished(registry, f"R{index:02d}")
    registry.create("LIVE", "P")

    kept = [state.run_id for state in registry.all() if state.is_terminal]
    assert kept == [f"R{i:02d}" for i in range(3, TERMINAL_RUNS_RETAINED + 3)], (
        "the OLDEST finished runs go first")


def test_a_live_run_is_never_evicted():
    """Eviction counts terminal runs only. A live one dropped from the registry
    is a run nothing can reach, cancel, or finish."""
    registry = RunRegistry()
    live = registry.create("LIVE", "P")
    for index in range(TERMINAL_RUNS_RETAINED + 5):
        _finished(registry, f"R{index:02d}")

    assert registry.get("LIVE") is live
    assert registry.active_for_program("P") is live


def test_a_run_that_fails_to_start_blocks_nothing(client, ready_program, monkeypatch):
    """`start_run` does everything that can raise BEFORE it registers the run.
    Registered first, a failure afterwards left a RUNNING state with no worker
    behind it: nothing ever finishes it, ``active_for_program`` keeps returning
    it, and every later write to that program answers 409 until the process
    restarts.

    ``monkeypatch.undo()`` is not usable here — the same MonkeyPatch instance
    carries the ``fake_model`` fixture's own patches, so undoing takes the model
    away with it. The failure is spent on the first call instead.
    """
    real_write_json = artifacts.write_json
    calls: list[int] = []

    def write_json_failing_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("read-only data root")
        return real_write_json(*args, **kwargs)

    monkeypatch.setattr(
        "alignmentgraph_isd.server.artifacts.write_json", write_json_failing_once)

    response = client.post(f"/api/programs/{ready_program}/runs")
    assert response.status_code == 500, response.text

    # The attempt is recorded as FAILED rather than left RUNNING...
    runs = client.get(f"/api/programs/{ready_program}").json()["runs"]
    assert [r["status"] for r in runs] == [RunStatus.FAILED]
    assert "read-only" in runs[0]["error"]

    # ...and the program takes a new run.
    assert client.post(f"/api/programs/{ready_program}/runs").status_code == 202
