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

    model_config = {"arbitrary_types_allowed": True}
