"""Where a run's files live, and how to read and write them.

Layout mirrors the benchmark's results tree closely enough to be familiar:

    <data_root>/programs/<program_id>/runs/<run_id>/
        brief.json  addie_output.json  trajectory.json
        metadata.json  graph.json  graph.dot  events.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

from .settings import Settings

# The API exposes artifacts by name; this is the whole allowed set, which also
# keeps `GET /artifacts/{name}` from being a path-traversal hole.
ARTIFACT_FILES: dict[str, str] = {
    "brief": "brief.json",
    "addie_output": "addie_output.json",
    "trajectory": "trajectory.json",
    "trajectory_deep": "trajectory_deep.json",
    "metadata": "metadata.json",
    "graph": "graph.json",
    "graph_dot": "graph.dot",
}

EVENTS_FILE = "events.jsonl"


def run_dir(settings: Settings, program_id: str, run_id: str) -> Path:
    return settings.programs_dir / program_id / "runs" / run_id


def relative_run_dir(program_id: str, run_id: str) -> str:
    return str(Path("programs") / program_id / "runs" / run_id)


def resolve(settings: Settings, relative: str) -> Path:
    return settings.data_root / relative


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_result(directory: Path, brief: dict, result: dict) -> None:
    """Persist one finished harness result as separate files.

    Separate rather than one blob because the UI fetches them independently —
    the graph is polled for the visualization while the ADDIE output is only
    read when someone opens it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / ARTIFACT_FILES["brief"], brief)
    write_json(directory / ARTIFACT_FILES["addie_output"], result.get("addie_output", {}))
    write_json(directory / ARTIFACT_FILES["trajectory"], result.get("trajectory", {}))
    write_json(directory / ARTIFACT_FILES["trajectory_deep"], result.get("trajectory_deep", {}))
    write_json(directory / ARTIFACT_FILES["metadata"], result.get("metadata", {}))
    write_json(directory / ARTIFACT_FILES["graph"], result.get("graph", {}))
    write_text(directory / ARTIFACT_FILES["graph_dot"], result.get("graph_dot", ""))


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_events(directory: Path, after: int = 0) -> list[dict]:
    """Replay a finished run's events from disk, from `after` exclusive.

    Tolerates a truncated final line: the flusher appends as the run proceeds,
    so a crash mid-write leaves a partial record rather than corrupting the rest.
    """
    path = directory / EVENTS_FILE
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("seq", 0) > after:
            events.append(event)
    return events
