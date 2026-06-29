from .orchestrator import MetaAgent
from .graph import AlignmentGraph
from .config import AblationConfig, HarnessRunConfig, MemoryConfig
from .memory import HarnessMemory
from .schema import DesignBrief, DesignBriefContext, DesignBriefConstraints
from .rag.corpus import RetrievalSubagent, LocalCorpusSubagent
from .rag.subagents import RetrievalSubagentRegistry


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
    "MemoryConfig",
    "HarnessMemory",
    "DesignBrief",
    "DesignBriefContext",
    "DesignBriefConstraints",
    "RetrievalSubagent",
    "LocalCorpusSubagent",
    "RetrievalSubagentRegistry",
    "run_design_brief",
]
