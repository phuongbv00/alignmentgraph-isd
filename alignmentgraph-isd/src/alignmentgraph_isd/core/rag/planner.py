from __future__ import annotations
from ...config import HarnessRunConfig
from ..schema import DesignBrief
from .agent import RetrievalAgentRegistry


class RetrievalPlanner:
    """On-demand retrieval façade used by specialist agents.

    Wraps the registry to provide three operations:
    - ``enabled()`` — gate check (enable_rag + non-empty registry);
    - ``build_menu()`` — compact descriptor list for a specialist's decision prompt;
    - ``execute_plan()`` — resolve agent names and run them in the sandbox.

    Does NOT handle brief-derived context (the brief itself + standing guidance,
    formatted by ``_format_design_brief``) or graph-context retrieval (core, always on).
    """

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config
        self.registry = RetrievalAgentRegistry(getattr(config, "retrieval_subagents", None) or [])

    def enabled(self) -> bool:
        return bool(self.config.ablation.enable_rag) and len(self.registry) > 0

    def build_menu(self, design_brief: DesignBrief, task_name: str) -> list[dict]:
        """Compact menu of relevant retrieval agents for a specialist's decision prompt."""
        menu: list[dict] = []
        for subagent in self.registry.select(design_brief, task_name):
            describe = getattr(subagent, "describe", None)
            if callable(describe):
                menu.append(describe())
            else:
                menu.append({
                    "name": getattr(subagent, "name", type(subagent).__name__),
                    "description": (getattr(subagent, "__doc__", "") or "").strip().split("\n")[0],
                    "domains": [],
                })
        return menu

    def execute_plan(
        self,
        design_brief: DesignBrief,
        task_name: str,
        plan: dict,
        *,
        log_llm_call=None,
    ) -> tuple[list[dict], list[dict]]:
        """Resolve the plan's agent names and run them in the retrieval sandbox."""
        from .sandbox import RetrievalSandbox

        agents = [a for a in (self.registry.get(name) for name in plan.get("agents", [])) if a is not None]
        sandbox = RetrievalSandbox(self.config.llm_factory, log_llm_call=log_llm_call)
        return sandbox.execute(design_brief, task_name, plan, agents)
