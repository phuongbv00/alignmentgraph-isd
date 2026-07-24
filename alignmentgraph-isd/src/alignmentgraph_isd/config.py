from __future__ import annotations
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    ChatModelFactory = Callable[[], ChatAnthropic | ChatOpenAI]
else:
    ChatModelFactory = Callable[[], Any]


class HarnessRunConfig(BaseModel):
    llm_factory: ChatModelFactory | None = None

    use_rag: bool = False
    retrieval_subagents: list[Any] = []

    # Ablation switches (both ON = the full pipeline; there are no presets).
    # ``enable_verifier`` wires the per-specialist QC nodes (verify + repair loop)
    # into the workflow. ``enable_graph_context`` gates the READ side of the
    # AlignmentGraph only — prompt injection of prior nodes' data; the graph is
    # still written in full either way, so dumps and the residual audit stay intact.
    enable_verifier: bool = True
    enable_graph_context: bool = True

    # Robustness: re-run a specialist whose section came back with empty required
    # fields (a small model intermittently returns empty/broken JSON, or a call is
    # dropped by a 429). ``regen_budget`` is the number of extra attempts;
    # ``regen_backoff_seconds`` is the base delay applied (growing per attempt)
    # before each re-run so a rate-limit window can drain instead of being hammered.
    # The benchmark adapter sources these from env (BENCHMARK_DELAY / HARNESS_REGEN_*).
    regen_budget: int = 2
    regen_backoff_seconds: float = 0.0

    model_config = {"arbitrary_types_allowed": True}
