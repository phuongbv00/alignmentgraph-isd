"""Execution sandbox for retrieval agents.

Retrieval agents run user-supplied code (corpus tools) and model-driven loops,
so they execute behind a boundary that the design workflow can trust:

- **error isolation** — an agent that raises yields an empty result plus an
  error event; it can never abort the design run;
- **budgets** — per-result output size cap and a wall-clock timeout per agent
  (the agent's own tool loop is bounded by its ``max_tool_calls``);
- **read-only inputs** — agents receive the query text and the design brief,
  never the alignment graph or memory handles;
- **strategies** — a plan chooses ``single`` (one agent), ``sequential`` (each
  agent sees the previous results appended to its query — refinement), or
  ``parallel`` (independent agents fan out on threads).

The sandbox is deliberately in-process: the trust boundary here is about fault
and scope containment for pluggable retrieval code, not OS-level isolation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from ..brief import DesignBrief
from .agent import RetrievalAgent

STRATEGIES = ("single", "sequential", "parallel")


class RetrievalSandbox:
    def __init__(
        self,
        llm_factory=None,
        *,
        log_llm_call=None,
        max_output_chars: int = 4000,
        timeout_s: float = 120.0,
    ) -> None:
        self._llm_factory = llm_factory
        self._log_llm_call = log_llm_call
        self._max_output_chars = max_output_chars
        self._timeout_s = timeout_s

    def execute(
        self,
        design_brief: DesignBrief,
        task_name: str,
        plan: dict,
        agents: list[RetrievalAgent],
    ) -> tuple[list[dict], list[dict]]:
        """Run the plan; returns (results, events). Never raises."""
        strategy = plan.get("strategy", "single")
        if strategy not in STRATEGIES:
            strategy = "single"
        queries = plan.get("queries") or {}
        events: list[dict] = []
        results: list[dict] = []

        if not agents:
            return results, events

        if strategy == "single":
            agents = agents[:1]

        if strategy == "parallel" and len(agents) > 1:
            with ThreadPoolExecutor(max_workers=len(agents)) as executor:
                futures = {
                    executor.submit(self._run_one, agent, design_brief, task_name, self._query_for(agent, queries, task_name)): agent
                    for agent in agents
                }
                for future, agent in futures.items():
                    result, event = self._collect(future, agent)
                    events.append(event)
                    if result:
                        results.append(result)
            return results, events

        # single / sequential
        carried = ""
        for agent in agents:
            query = self._query_for(agent, queries, task_name)
            if carried:
                query = f"{query}\n\nMaterial already retrieved (refine, don't repeat):\n{carried}"
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_one, agent, design_brief, task_name, query)
                result, event = self._collect(future, agent)
            events.append(event)
            if result:
                results.append(result)
                carried = "\n".join(result.get("content", []))[:800]
        return results, events

    # ── internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _query_for(agent: RetrievalAgent, queries: dict, task_name: str) -> str:
        name = getattr(agent, "name", "")
        return str(queries.get(name) or queries.get("*") or task_name)

    def _run_one(self, agent: RetrievalAgent, design_brief: DesignBrief, task_name: str, query: str) -> dict:
        if agent.system_prompt and agent.tools and self._llm_factory is not None:
            llm = self._llm_factory()
            return agent.run_agentic(llm, query, task_name, log_llm_call=self._log_llm_call)
        return agent.retrieve(design_brief, task_name, query)

    def _collect(self, future, agent: RetrievalAgent) -> tuple[dict | None, dict]:
        name = getattr(agent, "name", type(agent).__name__)
        try:
            result = future.result(timeout=self._timeout_s)
        except FutureTimeoutError:
            return None, {"agent": name, "status": "timeout"}
        except Exception as exc:
            return None, {"agent": name, "status": "error", "detail": str(exc)[:200]}
        if not result or not result.get("content"):
            return None, {"agent": name, "status": "empty", "tool_calls": (result or {}).get("tool_calls", 0)}
        result["content"] = self._truncate(result.get("content", []))
        return result, {
            "agent": name,
            "status": "ok",
            "snippets": len(result["content"]),
            "tool_calls": result.get("tool_calls", 0),
        }

    def _truncate(self, content: list) -> list[str]:
        out: list[str] = []
        used = 0
        for item in content:
            text = str(item)
            if used + len(text) > self._max_output_chars:
                text = text[: max(0, self._max_output_chars - used)]
            if text:
                out.append(text)
                used += len(text)
            if used >= self._max_output_chars:
                break
        return out


__all__ = ["RetrievalSandbox", "STRATEGIES"]
