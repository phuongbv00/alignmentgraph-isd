from __future__ import annotations
from ..config import HarnessRunConfig
from ..schema import DesignBrief
from .subagents import RetrievalSubagentRegistry


class RetrievalPlanner:
    """RAG = external-corpus retrieval only.

    This planner does one thing: run registered retrieval subagents over external
    corpora and return their merged results. It does NOT build the design-brief
    context pack (that is `ContextPlanner`, not retrieval), and it does not touch
    graph-context or memory retrieval (those are core and live elsewhere).

    RAG is gated by ``use_rag``. The benchmark defaults to no_rag and registers no
    subagents, so ``retrieve`` returns a disabled, empty result there.
    """

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config
        self.registry = RetrievalSubagentRegistry(getattr(config, "retrieval_subagents", None) or [])

    def retrieve(self, design_brief: DesignBrief, task_name: str = "full_design", graph_context: str = "") -> dict:
        if not self.config.ablation.use_rag or len(self.registry) == 0:
            return {"enabled": False, "task_name": task_name, "results": [], "sources": []}
        results = self.registry.retrieve(design_brief, task_name, graph_context)
        return {
            "enabled": True,
            "task_name": task_name,
            "results": results,
            "sources": sorted({result.get("source", "") for result in results if result.get("source")}),
        }
