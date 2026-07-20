from __future__ import annotations
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    ChatModelFactory = Callable[[], ChatAnthropic | ChatOpenAI]
else:
    ChatModelFactory = Callable[[], Any]


class AblationArm(StrEnum):
    FULL = "full"
    WO_GRAPH = "wo_graph"
    WO_MA = "wo_ma"


class AblationConfig(BaseModel):
    enable_rag: bool = False
    enable_multi_agent: bool = True
    enable_alignment_graph: bool = True
    arm: AblationArm | None = None

    PRESETS: ClassVar[Dict[AblationArm, dict]] = {
        AblationArm.FULL: dict(enable_rag=False, enable_multi_agent=True, enable_alignment_graph=True),
        AblationArm.WO_GRAPH: dict(enable_rag=False, enable_multi_agent=True, enable_alignment_graph=False),
        AblationArm.WO_MA: dict(enable_rag=False, enable_multi_agent=False, enable_alignment_graph=False),
    }

    @classmethod
    def from_key(cls, key: "AblationArm | str") -> "AblationConfig":
        try:
            arm = AblationArm(key)
        except ValueError:
            raise ValueError(
                f"Unknown ablation key: {key!r}. Valid: {[a.value for a in AblationArm]}"
            ) from None
        return cls(arm=arm, **cls.PRESETS[arm])


class HarnessRunConfig(BaseModel):
    ablation: AblationConfig = AblationConfig()
    llm_factory: ChatModelFactory | None = None
    retrieval_subagents: list[Any] = []

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_ablation(cls, key: str = "full") -> "HarnessRunConfig":
        return cls(ablation=AblationConfig.from_key(key))
