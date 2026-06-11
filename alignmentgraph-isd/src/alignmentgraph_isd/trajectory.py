from __future__ import annotations
import time
from datetime import datetime, timezone


class TrajectoryLogger:
    def __init__(self) -> None:
        self._start = time.time()
        self.agent_steps: list[dict] = []
        self.node_edits: list[dict] = []
        self.edge_edits: list[dict] = []
        self.llm_calls: int = 0
        self.token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}
        self.latency_ms: float = 0.0

    def log_step(self, agent_name: str, action: str, input_summary: str, output_summary: str) -> None:
        self.agent_steps.append({
            "agent_name": agent_name,
            "action": action,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_node_edit(self, op: str, node_id: str, node_type: str) -> None:
        self.node_edits.append({"op": op, "node_id": node_id, "node_type": node_type})

    def log_edge_edit(self, op: str, source_id: str, target_id: str, edge_type: str) -> None:
        self.edge_edits.append({"op": op, "source_id": source_id, "target_id": target_id, "edge_type": edge_type})

    def log_llm_call(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.llm_calls += 1
        self.token_usage["prompt_tokens"] += prompt_tokens
        self.token_usage["completion_tokens"] += completion_tokens

    def finalize(self) -> dict:
        self.latency_ms = (time.time() - self._start) * 1000
        return self.to_dict()

    def to_dict(self) -> dict:
        return {
            "agent_steps": self.agent_steps,
            "node_edits": self.node_edits,
            "edge_edits": self.edge_edits,
            "llm_calls": self.llm_calls,
            "token_usage": self.token_usage,
            "latency_ms": self.latency_ms,
        }
