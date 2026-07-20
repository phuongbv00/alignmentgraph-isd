from __future__ import annotations
from collections.abc import Callable
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    ChatModelFactory = Callable[[], ChatAnthropic | ChatOpenAI]
else:
    ChatModelFactory = Callable[[], Any]


class AblationConfig(BaseModel):
    # ``use_rag`` toggles external-corpus retrieval (RAG). It is OFF for every
    # benchmark preset and no preset currently turns it on — a future case-study
    # preset built on the static ``full`` workflow will. Graph-context retrieval
    # is core harness behaviour, always on, and is NOT considered RAG.
    use_rag: bool = False
    use_verifier: bool = True
    use_repair: bool = True
    multi_agent: bool = True
    # Whether specialists condition generation on graph traversal + establish
    # the 13-relation matrix's edges, and whether the verifier's alignment
    # tier (relation coverage + the Bloom/format validity rule) runs at all.
    # This is NOT a QC on/off switch — completeness (structural field
    # presence + single-artifact content checks) always runs regardless; see
    # pedagogical_verifier.py::verify(). Independent of ``multi_agent``: a
    # single agent can decompose element nodes and establish id/type-match
    # edges from its own output without any traversal, but it never sees
    # graph coordination, so this stays False for ``wo_ma`` (the single-agent arm).
    use_graph_coordination: bool = True

    # The preset key this config was built from (``full``/``wo_graph``/``wo_ma``).
    # The unique arm identity, used to name per-arm artifacts like the graph dump
    # so one arm's output never overwrites another's. Empty when the config was
    # constructed directly from flags rather than via ``from_key``.
    arm: str = ""

    PRESETS: ClassVar[Dict[str, dict]] = {
        # ── The 3-rung RQ2 ablation ladder (QC always on; only the presence of
        # graph coordination differs — see AblationConfig.use_graph_coordination
        # and pedagogical_verifier.py::verify()). ───────────────────────────────
        # Rung 3: multi-agent decomposition + graph coordination (full mechanism).
        "full": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=True,
                     use_graph_coordination=True),
        # Rung 2: multi-agent decomposition, naive blob context, NO graph coordination —
        # isolates whether decomposition alone (without the graph) helps over rung 1.
        "wo_graph": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=True,
                          use_graph_coordination=False),
        # Rung 1: single agent, one blob call — baseline, no decomposition at all.
        # ``wo_ma`` ("without multi-agent") is the canonical arm name; the internal
        # single-agent generation node/class stays named ``SingleAgent`` (that is
        # execution-layer vocabulary, not the arm label). ``build_graph`` in
        # nodes.py branches on ``multi_agent`` — there is no workflow registry.
        "wo_ma": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=False,
                      use_graph_coordination=False),
    }

    @classmethod
    def from_key(cls, key: str) -> "AblationConfig":
        if key not in cls.PRESETS:
            raise ValueError(f"Unknown ablation key: {key!r}. Valid: {list(cls.PRESETS)}")
        return cls(arm=key, **cls.PRESETS[key])


class HarnessRunConfig(BaseModel):
    ablation: AblationConfig = AblationConfig()
    # The injected chat-model producer is the SINGLE source of truth for "which
    # model". There is no parallel declarative model config: model provenance in
    # the run metadata is introspected from the model this factory builds (see
    # runner.py::_llm_metadata), so it can never drift from what actually ran.
    llm_factory: ChatModelFactory | None = None
    retrieval_subagents: list[Any] = []

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_ablation(cls, key: str = "full") -> "HarnessRunConfig":
        return cls(ablation=AblationConfig.from_key(key))
