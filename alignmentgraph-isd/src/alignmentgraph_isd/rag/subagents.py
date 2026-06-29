"""Registry that discovers and routes external retrieval subagents per task."""
from __future__ import annotations

from ..schema import DesignBrief
from .corpus import RetrievalSubagent


class RetrievalSubagentRegistry:
    """Holds external retrieval subagents and selects them by task relevance.

    The registry is the discovery/routing layer the docs describe: for each
    task it asks every subagent ``can_handle`` and runs only the matches,
    merging their results. The benchmark constructs an empty registry, so a
    benchmark run never reaches an external corpus.
    """

    def __init__(self, subagents: list[RetrievalSubagent] | None = None) -> None:
        self._subagents: list[RetrievalSubagent] = list(subagents or [])

    def register(self, subagent: RetrievalSubagent) -> None:
        self._subagents.append(subagent)

    def __len__(self) -> int:
        return len(self._subagents)

    def select(self, design_brief: DesignBrief, task_name: str) -> list[RetrievalSubagent]:
        selected: list[RetrievalSubagent] = []
        for subagent in self._subagents:
            try:
                if subagent.can_handle(design_brief, task_name):
                    selected.append(subagent)
            except Exception:
                continue
        return selected

    def retrieve(self, design_brief: DesignBrief, task_name: str, graph_context: str = "") -> list[dict]:
        results: list[dict] = []
        for subagent in self.select(design_brief, task_name):
            try:
                result = subagent.retrieve(design_brief, task_name, graph_context)
            except Exception:
                continue
            if result and result.get("content"):
                results.append(result)
        return results
