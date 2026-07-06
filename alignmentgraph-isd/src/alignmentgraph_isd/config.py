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
    # ``use_rag`` toggles external-corpus retrieval (RAG). It is OFF by default:
    # the benchmark runs no_rag. Graph-context and memory retrieval are core
    # harness behaviour, are always on, and are NOT considered RAG.
    use_rag: bool = False
    use_verifier: bool = True
    use_repair: bool = True
    multi_agent: bool = True
    dynamic_graph: bool = True

    PRESETS: ClassVar[Dict[str, dict]] = {
        # Benchmark presets: RAG is always off (no external corpus is registered
        # for the benchmark; graph/memory retrieval stays on regardless).
        "full": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=True, dynamic_graph=True),
        # Explicit benchmark default; identical to ``full`` since the benchmark runs no_rag.
        "no_rag": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=True, dynamic_graph=True),
        "no_verifier": dict(use_rag=False, use_verifier=False, use_repair=True, multi_agent=True, dynamic_graph=True),
        "no_repair": dict(use_rag=False, use_verifier=True, use_repair=False, multi_agent=True, dynamic_graph=True),
        "single_agent": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=False, dynamic_graph=True),
        "linear_addie_only": dict(use_rag=False, use_verifier=False, use_repair=False, multi_agent=True, dynamic_graph=False),
        # Case-study/app preset: enables RAG (requires registered RetrievalAgent instances).
        "case_study": dict(use_rag=True, use_verifier=True, use_repair=True, multi_agent=True, dynamic_graph=True),
    }

    @classmethod
    def from_key(cls, key: str) -> "AblationConfig":
        if key not in cls.PRESETS:
            raise ValueError(f"Unknown ablation key: {key!r}. Valid: {list(cls.PRESETS)}")
        return cls(**cls.PRESETS[key])


class LLMConfig(BaseModel):
    model_name: str = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 4096


class MemoryConfig(BaseModel):
    enabled: bool = True
    persist: bool | None = None
    root_dir: str = "alignmentgraph-isd/memory"
    training_program_id: str = ""
    session_id: str = ""
    max_episodic_events: int = 5


class HarnessRunConfig(BaseModel):
    ablation: AblationConfig = AblationConfig()
    llm: LLMConfig = LLMConfig()
    memory: MemoryConfig = MemoryConfig()
    llm_factory: ChatModelFactory | None = None
    # RetrievalAgent instances over external corpora. Empty for the benchmark;
    # case studies/app register domain agents here. Graph-context and memory
    # retrieval are core (always on) and do not use this list.
    retrieval_subagents: list[Any] = []

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_ablation(
        cls,
        key: str = "full",
        memory: MemoryConfig | dict | None = None,
        **llm_kwargs,
    ) -> "HarnessRunConfig":
        memory_config = memory if isinstance(memory, MemoryConfig) else MemoryConfig(**(memory or {}))
        return cls(
            ablation=AblationConfig.from_key(key),
            llm=LLMConfig(**llm_kwargs) if llm_kwargs else LLMConfig(),
            memory=memory_config,
        )
