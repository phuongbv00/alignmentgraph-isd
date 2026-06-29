"""RAG = external-corpus retrieval subagents (case-study/app add-on).

In this harness, **RAG means external-corpus retrieval only**. Domain corpora
(e.g. Java/OOP, software testing, code-review rubrics) are exposed as
``RetrievalSubagent`` instances, selected per task by ``can_handle`` and run only
when ``use_rag`` is on and subagents are registered.

Graph-context retrieval (pulling the relevant subgraph from the current
``AlignmentGraph``) and memory retrieval (working/episodic memory) are *core*
harness behaviour, always on, and are deliberately **not** called RAG.

The benchmark defaults to no_rag and registers no subagents, so a benchmark run
never depends on an external corpus.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..schema import DesignBrief


class RetrievalSubagent(ABC):
    """Contract for a pluggable external-corpus retriever."""

    name: str = "retrieval_subagent"
    source_type: str = "corpus"

    @abstractmethod
    def can_handle(self, design_brief: DesignBrief, task_name: str) -> bool:
        """Return True if this subagent has relevant knowledge for the task."""

    @abstractmethod
    def retrieve(self, design_brief: DesignBrief, task_name: str, graph_context: str) -> dict:
        """Return a retrieval result dict with source/subagent/task_name/content."""


class LocalCorpusSubagent(RetrievalSubagent):
    """Network-free subagent backed by an in-memory keyword→snippets corpus.

    Suitable for case-study corpora bundled with the repo. ``domains`` and
    ``keywords`` gate ``can_handle``; matched snippets become the content.
    """

    def __init__(
        self,
        name: str,
        source_type: str,
        corpus: dict[str, list[str]],
        *,
        domains: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        self.name = name
        self.source_type = source_type
        self._corpus = corpus
        self._domains = [d.lower() for d in (domains or [])]
        self._keywords = [k.lower() for k in (keywords or list(corpus.keys()))]

    def _haystack(self, design_brief: DesignBrief, task_name: str) -> str:
        parts = [
            design_brief.title,
            design_brief.domain,
            task_name,
            " ".join(design_brief.learning_goals or []),
        ]
        return " ".join(p for p in parts if p).lower()

    def can_handle(self, design_brief: DesignBrief, task_name: str) -> bool:
        haystack = self._haystack(design_brief, task_name)
        if self._domains and any(domain in haystack for domain in self._domains):
            return True
        return any(keyword in haystack for keyword in self._keywords)

    def retrieve(self, design_brief: DesignBrief, task_name: str, graph_context: str) -> dict:
        haystack = self._haystack(design_brief, task_name)
        content: list[str] = []
        citations: list[str] = []
        for keyword, snippets in self._corpus.items():
            if keyword.lower() in haystack or not self._keywords:
                content.extend(snippets)
                citations.append(f"{self.source_type}:{keyword}")
        if not content:  # domain matched but no keyword hit — return everything
            for keyword, snippets in self._corpus.items():
                content.extend(snippets)
                citations.append(f"{self.source_type}:{keyword}")
        return {
            "source": self.source_type,
            "subagent": self.name,
            "task_name": task_name,
            "content": content,
            "citations": citations,
        }
