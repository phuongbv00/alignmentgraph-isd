from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import HarnessRunConfig
from .graph import AlignmentGraph
from .schema import DesignBrief


REPAIR_OWNER_MAP = {
    "bloom": "ObjectiveDesignAgent",
    "coverage": "AssessmentDesignAgent",
    "measures": "AssessmentDesignAgent",
    "activity_support": "ActivityMaterialAgent",
    "supports": "ActivityMaterialAgent",
    "feasibility": "ImplementationConstraintAgent",
    "constrains": "ImplementationConstraintAgent",
    "evaluates": "EvaluationRevisionAgent",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemorySession:
    training_program_id: str
    storage_id: str
    session_id: str
    entrypoint_mode: str
    session_type: str
    execution_context: str
    persist: bool
    base_graph_version: int
    graph: AlignmentGraph
    design_brief: dict[str, Any]
    current_messages: list[dict[str, Any]]
    message_history: list[dict[str, Any]]
    working: dict[str, Any]
    semantic: dict[str, Any]
    episodic: dict[str, Any]
    procedural: dict[str, Any]
    store: "HarnessMemory"

    def augment_context_pack(self, context_pack: dict) -> dict:
        augmented = dict(context_pack or {})
        memory_context = {
            "working": self.working,
            "episodic": self.episodic,
            "procedural": self.procedural,
            "semantic": self.semantic,
        }
        augmented["memory_context"] = memory_context
        return augmented

    def commit(
        self,
        *,
        design_brief: DesignBrief,
        graph: AlignmentGraph,
        trajectory: dict,
        final_state: dict,
        addie_output: dict,
    ) -> dict:
        return self.store.commit_session(
            self,
            design_brief=design_brief,
            graph=graph,
            trajectory=trajectory,
            final_state=final_state,
            addie_output=addie_output,
        )


class HarnessMemory:
    """Four-layer memory facade for benchmark init runs and app tuning sessions."""

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config
        self.memory_config = config.memory
        self.root_dir = Path(self.memory_config.root_dir)

    def begin_session(self, design_brief: DesignBrief) -> MemorySession:
        training_program_id = self._training_program_id()
        configured_session_id = self._session_id()
        if configured_session_id and not training_program_id:
            raise ValueError("session_id requires training_program_id; omit both for a pure benchmark-style run.")

        entrypoint_mode = self._entrypoint_mode(training_program_id, configured_session_id)
        persist = self._should_persist(training_program_id)
        storage_id = _safe_id(training_program_id) if training_program_id else ""
        session_id = configured_session_id
        if training_program_id and not session_id:
            session_id = str(uuid.uuid4())
        execution_context = "app" if training_program_id else "benchmark"

        graph, base_graph_version = self._initial_graph(storage_id, persist)
        session_type = "tuning" if base_graph_version > 0 else "init"
        design_brief_snapshot = _design_brief_snapshot(design_brief)
        current_messages = _messages_from_design_brief(design_brief)
        message_history = self._working_message_history(
            storage_id,
            session_id,
            persist,
            current_messages,
        )
        working = self._working_layer(
            design_brief,
            design_brief_snapshot,
            current_messages,
            training_program_id,
            storage_id,
            session_id,
            entrypoint_mode,
            session_type,
            execution_context,
            persist,
            base_graph_version,
            message_history,
        )
        semantic = self._semantic_layer()
        episodic = self._episodic_layer(storage_id, persist)
        procedural = self._procedural_layer()

        return MemorySession(
            training_program_id=training_program_id,
            storage_id=storage_id,
            session_id=session_id,
            entrypoint_mode=entrypoint_mode,
            session_type=session_type,
            execution_context=execution_context,
            persist=persist,
            base_graph_version=base_graph_version,
            graph=graph,
            design_brief=design_brief_snapshot,
            current_messages=current_messages,
            message_history=message_history,
            working=working,
            semantic=semantic,
            episodic=episodic,
            procedural=procedural,
            store=self,
        )

    def commit_session(
        self,
        session: MemorySession,
        *,
        design_brief: DesignBrief,
        graph: AlignmentGraph,
        trajectory: dict,
        final_state: dict,
        addie_output: dict,
    ) -> dict:
        committed_version = session.base_graph_version + 1
        event = {
            "event_type": "alignment_graph_session",
            "timestamp": utc_now(),
            "training_program_id": session.training_program_id,
            "storage_id": session.storage_id,
            "session_id": session.session_id,
            "entrypoint_mode": session.entrypoint_mode,
            "session_type": session.session_type,
            "execution_context": session.execution_context,
            "design_brief_id": design_brief.id,
            "design_brief": session.design_brief,
            "current_messages": session.current_messages,
            "base_graph_version": session.base_graph_version,
            "committed_graph_version": committed_version,
            "graph_summary": _graph_summary(graph),
            "audit_summary": final_state.get("audit", {}).get("summary", ""),
            "violations": final_state.get("violations", []),
            "planner_decisions": final_state.get("planner_decisions", []),
            "repair_rounds": final_state.get("repair_rounds", 0),
            "trajectory_summary": _trajectory_summary(trajectory),
        }

        persisted = False
        persist_error = ""
        if session.persist:
            try:
                self._write_program_state(session, graph, addie_output, event)
                persisted = True
            except Exception as exc:  # don't lose a completed run because of a disk write
                persist_error = f"{type(exc).__name__}: {exc}"

        return {
            "enabled": self.memory_config.enabled,
            "persisted": persisted,
            "persist_error": persist_error,
            "root_dir": str(self.root_dir) if persisted else "",
            "training_program_id": session.training_program_id,
            "storage_id": session.storage_id,
            "session_id": session.session_id,
            "entrypoint_mode": session.entrypoint_mode,
            "session_type": session.session_type,
            "execution_context": session.execution_context,
            "benchmark_semantics": (
                "pure new run; no training_program_id/session_id supplied and no persistent memory is loaded"
                if session.execution_context == "benchmark"
                else ""
            ),
            "base_graph_version": session.base_graph_version,
            "committed_graph_version": committed_version,
            "layers": {
                "working": {
                    "scope": "active session",
                    "persisted": False,
                    "injected": True,
                    "keys": sorted(session.working.keys()),
                },
                "semantic": {
                    "scope": "global stable knowledge",
                    "persisted": persisted,
                    "injected": True,
                    "keys": sorted(session.semantic.keys()),
                },
                "episodic": {
                    "scope": "training program/session history",
                    "persisted": persisted,
                    "injected": True,
                    "recent_event_count": len(session.episodic.get("recent_events", [])),
                },
                "procedural": {
                    "scope": "versioned harness policy",
                    "persisted": persisted,
                    "injected": True,
                    "keys": sorted(session.procedural.keys()),
                },
            },
        }

    def _initial_graph(self, storage_id: str, persist: bool) -> tuple[AlignmentGraph, int]:
        if not persist or not storage_id:
            return AlignmentGraph(), 0
        loaded = self._load_latest_graph(storage_id)
        if loaded is None:
            return AlignmentGraph(), 0
        return loaded

    def _working_layer(
        self,
        design_brief: DesignBrief,
        design_brief_snapshot: dict[str, Any],
        current_messages: list[dict[str, Any]],
        training_program_id: str,
        storage_id: str,
        session_id: str,
        entrypoint_mode: str,
        session_type: str,
        execution_context: str,
        persist: bool,
        base_graph_version: int,
        message_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "training_program_id": training_program_id,
            "storage_id": storage_id,
            "session_id": session_id,
            "entrypoint_mode": entrypoint_mode,
            "session_type": session_type,
            "execution_context": execution_context,
            "persist": persist,
            "design_brief_id": design_brief.id,
            "design_brief": design_brief_snapshot,
            "current_messages": current_messages,
            "base_graph_version": base_graph_version,
            "message_history": message_history,
            "current_message_count": len(current_messages),
            "message_count": len(message_history),
            "current_graph_role": "working graph for this session; committed as training program graph after aggregate",
        }

    def _semantic_layer(self) -> dict[str, Any]:
        return {
            "stable_sources": [
                "ADDIE phase contract",
                "Bloom measurable verbs",
                "constructive alignment checklist",
                "assessment/rubric design templates",
                "implementation and evaluation quality criteria",
            ],
            "retrieval_role": "global knowledge injected into the context pack for every session",
        }

    def _episodic_layer(self, storage_id: str, persist: bool) -> dict[str, Any]:
        recent_events = []
        if persist and storage_id:
            recent_events = self._read_recent_events(storage_id, self.memory_config.max_episodic_events)
        return {
            "recent_events": recent_events,
            "use_policy": "training program history only; benchmark/test runs are not persisted unless explicitly enabled",
        }

    def _procedural_layer(self) -> dict[str, Any]:
        return {
            "ablation": self.config.ablation.model_dump(),
            "repair_owner_map": REPAIR_OWNER_MAP,
            "impact_policy": {key: list(value) for key, value in AlignmentGraph.IMPACT_POLICY.items()},
            "session_policy": {
                "no_ids": "pure new run; benchmark default; no persistent graph or working memory is loaded",
                "training_program_id_only": "start a new session on the latest graph for that training program",
                "training_program_id_and_session_id": "resume a session and load its working memory/message history",
            },
        }

    def _training_program_id(self) -> str:
        return str(self.memory_config.training_program_id or "").strip()

    def _session_id(self) -> str:
        return str(self.memory_config.session_id or "").strip()

    def _entrypoint_mode(self, training_program_id: str, session_id: str) -> str:
        if training_program_id and session_id:
            return "resume_session"
        if training_program_id:
            return "new_session"
        return "pure_new_run"

    def _should_persist(self, training_program_id: str) -> bool:
        if not self.memory_config.enabled or not training_program_id:
            return False
        if self.memory_config.persist is not None:
            return bool(self.memory_config.persist)
        return True

    def _program_dir(self, storage_id: str) -> Path:
        return self.root_dir / "programs" / storage_id

    def _session_dir(self, storage_id: str, session_id: str) -> Path:
        return self._program_dir(storage_id) / "sessions" / _safe_id(session_id)

    def _load_latest_graph(self, storage_id: str) -> tuple[AlignmentGraph, int] | None:
        graph_dir = self._program_dir(storage_id) / "graph_versions"
        # Single source of truth for ordering: the version parsed from the filename
        # (avoids string-sort breaking on unpadded/legacy names or >9999 versions).
        candidates: list[tuple[int, Path]] = []
        for path in graph_dir.glob("alignment_graph_v*.json"):
            parsed = _parse_version(path.name)
            if parsed is not None:
                candidates.append((parsed, path))
        if not candidates:
            return None
        version, latest = max(candidates, key=lambda item: item[0])
        try:
            payload = json.loads(latest.read_text(encoding="utf-8"))
        except Exception:
            return None
        graph_payload = payload.get("graph", payload)
        return AlignmentGraph.from_dict(graph_payload), version

    def _read_recent_events(self, storage_id: str, limit: int) -> list[dict]:
        events_path = self._program_dir(storage_id) / "episodic" / "session_events.jsonl"
        if not events_path.exists():
            return []
        lines = events_path.read_text(encoding="utf-8").splitlines()
        events: list[dict] = []
        for line in lines[-limit:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _working_message_history(
        self,
        storage_id: str,
        session_id: str,
        persist: bool,
        current_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        if persist and storage_id and session_id:
            working_path = self._session_dir(storage_id, session_id) / "working_memory.json"
            if working_path.exists():
                try:
                    payload = json.loads(working_path.read_text(encoding="utf-8"))
                    stored_history = payload.get("message_history", [])
                    if isinstance(stored_history, list):
                        history.extend(item for item in stored_history if isinstance(item, dict))
                except Exception:
                    history = []

        for message in current_messages:
            if message not in history:
                history.append(message)
        return history

    def _write_program_state(
        self,
        session: MemorySession,
        graph: AlignmentGraph,
        addie_output: dict,
        event: dict,
    ) -> None:
        program_dir = self._program_dir(session.storage_id)
        graph_dir = program_dir / "graph_versions"
        episodic_dir = program_dir / "episodic"
        session_dir = self._session_dir(session.storage_id, session.session_id)
        semantic_dir = self.root_dir / "semantic"
        procedural_dir = self.root_dir / "procedural"
        for directory in (graph_dir, episodic_dir, session_dir, semantic_dir, procedural_dir):
            directory.mkdir(parents=True, exist_ok=True)

        version = event["committed_graph_version"]
        graph_payload = {
            "version": version,
            "training_program_id": session.training_program_id,
            "storage_id": session.storage_id,
            "session_id": session.session_id,
            "created_at": utc_now(),
            "graph": graph.to_dict(),
            "addie_output": addie_output,
        }
        _write_json(graph_dir / f"alignment_graph_v{version:04d}.json", graph_payload)
        _write_json(program_dir / "program.json", {
            "training_program_id": session.training_program_id,
            "storage_id": session.storage_id,
            "latest_graph_version": version,
            "latest_session_id": session.session_id,
            "updated_at": utc_now(),
        })
        _write_json(session_dir / "working_memory.json", {
            "training_program_id": session.training_program_id,
            "storage_id": session.storage_id,
            "session_id": session.session_id,
            "entrypoint_mode": session.entrypoint_mode,
            "session_type": session.session_type,
            "design_brief": session.design_brief,
            "current_messages": session.current_messages,
            "message_history": session.message_history,
            "base_graph_version": session.base_graph_version,
            "latest_graph_version": version,
            "last_design_brief_id": event["design_brief_id"],
            "updated_at": utc_now(),
        })
        _append_jsonl(episodic_dir / "session_events.jsonl", event)
        _write_json(semantic_dir / "semantic_index.json", self._semantic_layer())
        _write_json(procedural_dir / "harness_policy.json", self._procedural_layer())

        repair_events = _repair_events(event)
        if repair_events:
            repair_path = episodic_dir / "repair_cases.jsonl"
            for repair_event in repair_events:
                _append_jsonl(repair_path, repair_event)


def _parse_version(filename: str) -> int | None:
    match = re.search(r"alignment_graph_v(\d+)\.json$", filename)
    return int(match.group(1)) if match else None


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return safe or "alignment-program"


def _design_brief_snapshot(design_brief: DesignBrief) -> dict[str, Any]:
    payload = design_brief.model_dump(exclude={"user_message", "message"})
    return _drop_empty(payload)


def _messages_from_design_brief(design_brief: DesignBrief) -> list[dict[str, str]]:
    text = (design_brief.user_message or getattr(design_brief, "message", "") or "").strip()
    return [{"role": "user", "content": text}] if text else []


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {
            key: _drop_empty(item)
            for key, item in value.items()
            if item not in ("", None, [], {})
        }
        return {key: item for key, item in cleaned.items() if item not in ("", None, [], {})}
    if isinstance(value, list):
        return [_drop_empty(item) for item in value if item not in ("", None, [], {})]
    return value


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(payload), ensure_ascii=False) + "\n")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)


def _graph_summary(graph: AlignmentGraph) -> dict:
    nodes = graph.get_nodes()
    edges = graph.get_edges()
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": {
            node_type: len(graph.get_nodes(node_type))
            for node_type in sorted(AlignmentGraph.NODE_TYPES)
        },
        "stale_nodes": [node["id"] for node in nodes if node.get("stale")],
        "stale_edges": len([edge for edge in edges if edge.get("stale")]),
    }


def _trajectory_summary(trajectory: dict) -> dict:
    return {
        "agent_steps": len(trajectory.get("agent_steps", [])),
        "node_edits": len(trajectory.get("node_edits", [])),
        "edge_edits": len(trajectory.get("edge_edits", [])),
        "planner_decisions": len(trajectory.get("planner_decisions", [])),
        "llm_calls": trajectory.get("llm_calls", 0),
        "token_usage": trajectory.get("token_usage", {}),
        "latency_ms": trajectory.get("latency_ms", 0),
    }


def _repair_events(event: dict) -> list[dict]:
    repair_events: list[dict] = []
    for decision in event.get("planner_decisions", []):
        selected = decision.get("selected_task") or {}
        task_type = selected.get("type", "")
        if task_type.endswith("_repair"):
            repair_events.append({
                "event_type": "specialist_repair_case",
                "timestamp": event["timestamp"],
                "training_program_id": event["training_program_id"],
                "storage_id": event["storage_id"],
                "session_id": event["session_id"],
                "graph_version": event["committed_graph_version"],
                "task_type": task_type,
                "target": selected.get("target", ""),
                "reason": selected.get("reason", decision.get("reason", "")),
            })
    return repair_events
