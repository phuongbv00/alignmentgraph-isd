from .core.runner import MetaAgent
from .core.alignment_graph import AlignmentGraph
from .config import HarnessRunConfig
from .core.brief import DesignBrief, DesignBriefContext, DesignBriefConstraints
from .core.rag.agent import RetrievalTool, RetrievalAgent, RetrievalAgentRegistry
from .core.llm import llm_factory_from_env
from .exceptions import HarnessCancelled


def run_design_brief(
    design_brief: DesignBrief,
    config: HarnessRunConfig | None = None,
    *,
    on_event=None,
) -> dict:
    """Run the harness on the canonical DesignBrief contract.

    Benchmark integrations are expected to map their own scenario schema to
    DesignBrief outside the core harness, then call this public entry point.

    ``on_event`` is an optional ``(kind: str, payload: dict) -> None`` consumer
    that observes the run as it happens (see ``TrajectoryLogger``). It changes
    nothing about the returned result; it exists so a UI can show progress
    during a run that takes minutes.
    """
    run_config = config or HarnessRunConfig()
    if run_config.llm_factory is None:
        raise RuntimeError(
            "run_design_brief requires HarnessRunConfig.llm_factory. "
            "Benchmark integrations should construct DesignBrief externally "
            "and pass a configured HarnessRunConfig."
        )
    return MetaAgent(run_config).run(design_brief, on_event=on_event)

__all__ = [
    "MetaAgent",
    "AlignmentGraph",
    "HarnessRunConfig",
    "DesignBrief",
    "DesignBriefContext",
    "DesignBriefConstraints",
    "RetrievalTool",
    "RetrievalAgent",
    "RetrievalAgentRegistry",
    "llm_factory_from_env",
    "run_design_brief",
    "HarnessCancelled",
]
