"""Where a run's files live, and how to read and write them.

Layout mirrors the benchmark's results tree closely enough to be familiar:

    <data_root>/programs/<program_id>/runs/<run_id>/
        brief.json  addie_output.json  trajectory.json  trajectory_deep.json
        metadata.json  graph.json  graph.dot  contexts.json  events.jsonl
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
    "contexts": "contexts.json",
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
    write_json(directory / ARTIFACT_FILES["contexts"], result.get("contexts", []))


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_transcript(contexts: list[dict]) -> str:
    """Agent contexts as Markdown, for reading.

    Markdown and not JSON, deliberately: ``GET /contexts`` already serves the
    JSON a tool would want, and a transcript is the one artifact a PERSON reads
    end to end. A 27-message conversation as a JSON array is not that.

    Every part is kept — the system turn, each message in order, the bound tool
    schemas — because the point of downloading a transcript is to read exactly
    what the model was shown, and a summary would defeat it.
    """
    out: list[str] = []
    for entry in contexts:
        label = str(entry.get("label") or "?")
        attempt = int(entry.get("attempt") or 1)
        head = f"## {entry.get('agent', '?')} — {label}"
        if attempt > 1:
            head += f" (retry #{attempt})"
        out.append(head)
        tokens = entry.get("tokens") or {}
        if tokens:
            out.append(
                f"*{entry.get('total_tokens', '?')} of {entry.get('token_budget', '?')} tokens "
                f"— system {tokens.get('system', 0)}, messages {tokens.get('messages', 0)}, "
                f"tools {tokens.get('tools', 0)}, schemas {entry.get('schema_tokens', 0)}*")
        out.append("")
        for index, message in enumerate(entry.get("messages") or []):
            role = str(message.get("role") or "?")
            name = message.get("name")
            out.append(f"### {index}. {role}" + (f" · {name}" if name else ""))
            content = str(message.get("content") or "").strip()
            if content:
                out.append("")
                out.append(content)
            for call in message.get("tool_calls") or []:
                out.append("")
                out.append("```json")
                out.append(json.dumps(call, ensure_ascii=False, indent=2))
                out.append("```")
            out.append("")
        tools = entry.get("tools") or []
        if tools:
            out.append("### bound tool schemas")
            out.append("")
            out.append("```json")
            out.append(json.dumps(tools, ensure_ascii=False, indent=2))
            out.append("```")
            out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out) or "(this run published no agent context)\n"


def has_trajectory(directory: Path) -> bool:
    return (directory / ARTIFACT_FILES["trajectory"]).exists()


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
