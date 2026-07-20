from .core.runner import MetaAgent
from .core.graph import AlignmentGraph
from .config import AblationConfig, HarnessRunConfig
from .core.schema import DesignBrief, DesignBriefContext, DesignBriefConstraints
from .core.rag.agent import RetrievalTool, RetrievalAgent, RetrievalAgentRegistry
from .core.llm import llm_factory_from_env


def run_design_brief(design_brief: DesignBrief, config: HarnessRunConfig | None = None) -> dict:
    """Run the harness on the canonical DesignBrief contract.

    Benchmark integrations are expected to map their own scenario schema to
    DesignBrief outside the core harness, then call this public entry point.
    """
    run_config = config or HarnessRunConfig()
    if run_config.llm_factory is None:
        raise RuntimeError(
            "run_design_brief requires HarnessRunConfig.llm_factory. "
            "Benchmark integrations should construct DesignBrief externally "
            "and pass a configured HarnessRunConfig."
        )
    return MetaAgent(run_config).run(design_brief)

__all__ = [
    "MetaAgent",
    "AlignmentGraph",
    "AblationConfig",
    "HarnessRunConfig",
    "DesignBrief",
    "DesignBriefContext",
    "DesignBriefConstraints",
    "RetrievalTool",
    "RetrievalAgent",
    "RetrievalAgentRegistry",
    "llm_factory_from_env",
    "run_design_brief",
]
