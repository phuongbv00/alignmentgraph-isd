from __future__ import annotations
from ..config import HarnessRunConfig


class RetrievalPlanner:
    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def retrieve(self, scenario: dict) -> dict:
        """Return a ContextPack dict. Stub returns empty; full RAG impl to be added later."""
        return {}
