"""Retrieval agents: single class, tools decide corpus type.

In this harness **RAG means external-corpus retrieval only**. Graph-context
retrieval (pulling the relevant subgraph from ``AlignmentGraph``) and memory
retrieval are core harness behaviour, always on, and deliberately **not** RAG.

Everything needed to plug in a retrieval agent lives here:

- ``RetrievalTool`` — a named callable a ``RetrievalAgent`` can invoke.
- ``RetrievalAgent`` — retriever with system prompt + tools + JSON loop.
  No LLM or system_prompt → deterministic fallback (runs tools once).
- ``RetrievalAgentRegistry`` — discovers and routes agents per task.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..brief import DesignBrief
from ..llm_io import _extract_token_usage, parse_json_response

# ── Tool ───────────────────────────────────────────────────────────────────────

@dataclass
class RetrievalTool:
    name: str
    description: str
    fn: Callable[..., list[str]]

    def invoke(self, args: dict) -> list[str]:
        return self.fn(**(args or {}))


_LOOP_PROTOCOL = """
You have access to the following tools:
{tool_descriptions}

Respond with JSON only, one action per turn:
- To use a tool: {{"tool": "<tool name>", "args": {{...}}}}
- To finish:     {{"content": ["<relevant snippet>", ...], "citations": ["<source>", ...]}}

Finish as soon as you have material relevant to the request. If nothing in your
corpus is relevant, finish with {{"content": [], "citations": []}}."""


# ── Agent ──────────────────────────────────────────────────────────────────────

class RetrievalAgent:
    """Pluggable retrieval agent: corpus tools + optional LLM loop.

    The corpus type (local files, remote API, mixed) is determined by the
    tools — not by subclassing. Two execution modes:

    - **Agentic** (system_prompt + tools + LLM available): bounded JSON loop
      where the model decides which tools to call and when to stop.
    - **Deterministic** (no LLM or no system_prompt): runs every tool once
      with the query text — network-free fallback.

    ``can_handle`` gates routing in the registry: domain match takes priority
    over keyword match, falling back to False when neither list is set.
    """

    def __init__(
        self,
        name: str,
        source_type: str,
        *,
        description: str = "",
        domains: list[str] | None = None,
        keywords: list[str] | None = None,
        system_prompt: str = "",
        tools: list[RetrievalTool] | None = None,
        max_tool_calls: int = 3,
    ) -> None:
        self.name = name
        self.source_type = source_type
        self.description = description
        self.system_prompt = system_prompt
        self.tools = list(tools or [])
        self.max_tool_calls = max_tool_calls
        self._domains = [d.lower() for d in (domains or [])]
        self._keywords = [k.lower() for k in (keywords or [])]

    def can_handle(self, design_brief: DesignBrief, task_name: str) -> bool:
        haystack = " ".join(
            p for p in (
                design_brief.title,
                design_brief.domain,
                task_name,
                " ".join(design_brief.learning_goals or []),
            ) if p
        ).lower()
        if self._domains and any(domain in haystack for domain in self._domains):
            return True
        return bool(self._keywords) and any(keyword in haystack for keyword in self._keywords)

    def retrieve(self, design_brief: DesignBrief, task_name: str, query: str = "") -> dict:
        """Deterministic fallback: run each tool once with the query text."""
        query = query or task_name
        content: list[str] = []
        citations: list[str] = []
        for tool in self.tools:
            try:
                content.extend(tool.invoke({"query": query}))
                citations.append(f"{self.source_type}:{tool.name}")
            except TypeError:
                try:
                    content.extend(tool.invoke({}))
                    citations.append(f"{self.source_type}:{tool.name}")
                except Exception:
                    continue
            except Exception:
                continue
        return {
            "source": self.source_type,
            "subagent": self.name,
            "task_name": task_name,
            "content": content,
            "citations": citations,
        }

    def describe(self) -> dict:
        return {"name": self.name, "description": self.description, "domains": self._domains}

    def run_agentic(self, llm, query: str, task_name: str, *, log_llm_call=None) -> dict:
        """Run the bounded JSON tool loop and return a standard result dict."""
        tool_index = {tool.name: tool for tool in self.tools}
        tool_descriptions = "\n".join(f"- {t.name}: {t.description}" for t in self.tools)
        messages = [
            {"role": "system", "content": self.system_prompt + _LOOP_PROTOCOL.format(tool_descriptions=tool_descriptions)},
            {"role": "user", "content": f"Retrieval request (task: {task_name}):\n{query}"},
        ]

        tool_calls = 0
        for _ in range(self.max_tool_calls + 1):
            result = llm.invoke(messages)
            content = result.content if hasattr(result, "content") else str(result)
            if log_llm_call is not None:
                log_llm_call(*_extract_token_usage(result))
            parsed = parse_json_response(content, warn=False)
            if not isinstance(parsed, dict) or not parsed:
                break
            if "tool" in parsed and tool_calls < self.max_tool_calls:
                tool = tool_index.get(parsed.get("tool", ""))
                if tool is None:
                    break
                tool_calls += 1
                try:
                    tool_result = tool.invoke(parsed.get("args") or {})
                except Exception as exc:
                    tool_result = [f"tool error: {exc}"]
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": f"TOOL RESULT ({tool.name}):\n" + "\n".join(str(x) for x in tool_result),
                })
                continue
            return {
                "source": self.source_type,
                "subagent": self.name,
                "task_name": task_name,
                "content": [str(x) for x in parsed.get("content", []) or []],
                "citations": [str(x) for x in parsed.get("citations", []) or []],
                "tool_calls": tool_calls,
            }

        fallback = self._empty_result(task_name)
        fallback["tool_calls"] = tool_calls
        return fallback

    def _empty_result(self, task_name: str) -> dict:
        return {
            "source": self.source_type,
            "subagent": self.name,
            "task_name": task_name,
            "content": [],
            "citations": [],
        }


# ── Registry ───────────────────────────────────────────────────────────────────

class RetrievalAgentRegistry:
    """Holds retrieval agents and routes them to tasks by relevance.

    The registry is the discovery/routing layer: for each task it asks every
    agent ``can_handle`` and runs only the matches. The benchmark constructs
    an empty registry, so a benchmark run never reaches an external corpus.
    """

    def __init__(self, agents: list[RetrievalAgent] | None = None) -> None:
        self._agents: list[RetrievalAgent] = list(agents or [])

    def __len__(self) -> int:
        return len(self._agents)

    def get(self, name: str) -> RetrievalAgent | None:
        for agent in self._agents:
            if getattr(agent, "name", "") == name:
                return agent
        return None

    def select(self, design_brief: DesignBrief, task_name: str) -> list[RetrievalAgent]:
        selected: list[RetrievalAgent] = []
        for agent in self._agents:
            try:
                if agent.can_handle(design_brief, task_name):
                    selected.append(agent)
            except Exception:
                continue
        return selected

    def retrieve(self, design_brief: DesignBrief, task_name: str, query: str = "") -> list[dict]:
        results: list[dict] = []
        for agent in self.select(design_brief, task_name):
            try:
                result = agent.retrieve(design_brief, task_name, query)
            except Exception:
                continue
            if result and result.get("content"):
                results.append(result)
        return results

