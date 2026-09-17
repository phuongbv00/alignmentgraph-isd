"""Where a run's files live, and how to read and write them.

Layout mirrors the benchmark's results tree closely enough to be familiar:

    <data_root>/programs/<program_id>/runs/<run_id>/
        brief.json  addie_output.json  trajectory.json  trajectory_deep.json
        metadata.json  graph.json  contexts.json  plans.json
        violations.json  events.jsonl

Each file answers one question, and a fact has ONE of them as its owner.
``graph.json`` is the whole of the alignment graph — it carries the display
semantics too, so the DOT rendering is reproducible from it
(``alignmentgraph-isd dot graph.json``) and is not written here — and it owns
every measurement OF the graph, which is why ``metadata.json``'s audit block
carries the verdict and not a second copy of the coverage. ``violations.json``
owns every finding and what became of it. ``trajectory.json`` and
``trajectory_deep.json`` own the trace.

``events.jsonl`` is the odd one and is not an artifact of the result at all: it
is the wire log, written as the run goes so that a viewer can follow one and
resume after a disconnect. It is therefore the record of a run that has no
other record, and it is deleted the moment the run has one — see
``discard_events``, which lists what carries each of its frames instead.
"""
from __future__ import annotations

import csv
import io
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
    "contexts": "contexts.json",
    "plans": "plans.json",
    "violations": "violations.json",
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
    write_json(directory / ARTIFACT_FILES["contexts"], result.get("contexts", []))
    # How each family's work was divided, round by round, with the whole work
    # set each Developer was handed. The `dev_plan` trajectory event keeps a
    # SUMMARY of the same decision (set ids and their objectives, the source,
    # what the harness dropped or split) and that is what the timeline reads;
    # this is the payload itself — the obligations, the themes, the expected
    # counts — which nothing else on disk holds, so without it "what exactly
    # was this Developer asked for" is answerable only while the run is alive.
    write_json(directory / ARTIFACT_FILES["plans"], result.get("plans", []))
    write_json(directory / ARTIFACT_FILES["violations"], result.get("violations", []))


def discard_events(directory: Path) -> bool:
    """Delete ``events.jsonl`` once the run it belongs to has a result.

    The log is the record of a run that has NO other record. While a run is in
    flight it is the only thing on disk — ``write_result`` runs at the end — so
    it carries everything, including one ``action`` frame per entry of the deep
    trajectory. The moment the harness returns a result, the result's own
    artifacts carry all of it, kind for kind:

    * ``action`` → ``trajectory_deep.json``'s ``actions``, item for item: every
      ``TrajectoryLogger.log_action`` appends to the list that file dumps AND
      emits one frame here.
    * ``agent_step``, ``llm_call``, ``phase_started``, ``phase_finished`` →
      the same actions, in the same file.
    * ``node_edit``, ``check_event``, ``repair_event``, ``validation_event`` →
      ``trajectory.json``'s ``events``, under their taxonomy names
      (``node_edit`` is ``node_add``/``node_update``, and so on): every
      ``_record_event`` writes there and emits here.
    * ``llm_started``/``llm_finished`` → nothing, by design. They are
      ``TrajectoryLogger.emit`` progress signals, the only sign of life during
      the ~50 s a model call takes, and they RECORD nothing; the ``llm_call``
      action holds strictly more (the same ``duration_ms`` and
      ``prompt_chars``, plus the tokens and the ``finish_reason``).
    * ``run_started``/``run_finished`` → the ``Run`` row, which is what a
      finished run's replay already opens with (``sse.replay_stream``'s
      ``hello``) and what synthesizes its closing frame.

    Verified kind by kind on run 16cef50d: 4.5 MB, of which 4.3 MB was the
    ``action`` frames, and not one kind that the artifacts did not already
    hold.

    So a run that ends WITHOUT a result — cancelled, failed, or interrupted
    with the process — keeps its log whole, actions included: there the file is
    the only trace of what happened, which is the whole reason it is written
    incrementally rather than at the end.

    Returns whether a file was removed.
    """
    path = directory / EVENTS_FILE
    if not path.exists() or not (directory / ARTIFACT_FILES["trajectory_deep"]).exists():
        return False
    path.unlink()
    return True


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
                f"*{entry.get('total_tokens', '?')} of {entry.get('token_budget', '?')} "
                f"prompt-budget tokens "
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
            reasoning = str(message.get("reasoning") or "").strip()
            if reasoning:
                # A blockquote under an italic marker rather than a heading of
                # its own: the headings are the message index, and a reasoning
                # block is part of the turn above it, not another turn.
                out.append("")
                out.append("*reasoning — recorded, never sent back to the model*")
                out.append("")
                out.extend(f"> {line}" for line in reasoning.splitlines() or [""])
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


# One row per finding, in the order the ledger keeps them. The columns are the
# `Finding` fields themselves, not a friendlier subset: the questions a reader
# takes to a spreadsheet — how many are still open, by reason, by owner, by
# check — are each one column, and a column dropped here is a question that
# cannot be asked of the file.
VIOLATION_COLUMNS: tuple[str, ...] = (
    "key",
    "type",
    "node_id",
    "severity",
    "outcome",
    "open_reason",
    "report_only",
    "target_designer",
    "first_phase",
    "first_round",
    "last_round",
    "sightings",
    "shown_to_agent",
    "repaired_by",
    "repaired_at_round",
    "converged_at_round",
    "messages",
    "repair_hint",
    "metadata",
)


def render_violations_csv(findings: list[dict]) -> str:
    """The violation ledger as CSV, for reading in a spreadsheet.

    CSV and not JSON, deliberately: ``GET /runs/{id}/violations`` already
    serves the JSON a tool would want, byte for byte what is on disk. What it
    does not give is the shape the ledger is actually read in — one row per
    finding, sorted and filtered and counted by outcome, by open reason, by
    owning agent — and rebuilding that from a nested array by hand is the work
    this exists to remove.

    The two nested fields travel whole rather than being dropped or split
    across rows: ``messages`` newline-joined inside its cell (one finding can
    be reported more than one way and both wordings are kept), ``metadata`` as
    compact JSON, because it is what says WHICH item or objective the finding
    is about and a row without it cannot be traced back to the design.
    """
    buffer = io.StringIO()
    # QUOTE_ALL: every text cell here can hold a comma or a newline, and a file
    # that parses differently depending on what a check happened to say is not
    # an export.
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(VIOLATION_COLUMNS)
    for finding in findings:
        row = []
        for column in VIOLATION_COLUMNS:
            value = finding.get(column)
            if column == "messages":
                value = "\n".join(str(message) for message in value or [])
            elif column == "metadata":
                value = json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            row.append("" if value is None else str(value))
        writer.writerow(row)
    return buffer.getvalue()


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
