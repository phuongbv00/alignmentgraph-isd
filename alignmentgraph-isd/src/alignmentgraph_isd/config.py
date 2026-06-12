from __future__ import annotations
from typing import Any, ClassVar, Dict
from pydantic import BaseModel


class AblationConfig(BaseModel):
    use_rag: bool = True
    use_verifier: bool = True
    use_repair: bool = True
    multi_agent: bool = True
    dynamic_graph: bool = True

    PRESETS: ClassVar[Dict[str, dict]] = {
        "full": dict(use_rag=True, use_verifier=True, use_repair=True, multi_agent=True, dynamic_graph=True),
        "no_rag": dict(use_rag=False, use_verifier=True, use_repair=True, multi_agent=True, dynamic_graph=True),
        "no_verifier": dict(use_rag=True, use_verifier=False, use_repair=True, multi_agent=True, dynamic_graph=True),
        "no_repair": dict(use_rag=True, use_verifier=True, use_repair=False, multi_agent=True, dynamic_graph=True),
        "single_agent": dict(use_rag=True, use_verifier=True, use_repair=True, multi_agent=False, dynamic_graph=True),
        "linear_addie_only": dict(use_rag=False, use_verifier=False, use_repair=False, multi_agent=True, dynamic_graph=False),
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


class HarnessRunConfig(BaseModel):
    ablation: AblationConfig = AblationConfig()
    llm: LLMConfig = LLMConfig()
    bench_llm_config: Any = None  # holds the raw shared.llm.LLMConfig passed in from benchmark

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_ablation(cls, key: str = "full", **llm_kwargs) -> "HarnessRunConfig":
        return cls(
            ablation=AblationConfig.from_key(key),
            llm=LLMConfig(**llm_kwargs) if llm_kwargs else LLMConfig(),
        )
