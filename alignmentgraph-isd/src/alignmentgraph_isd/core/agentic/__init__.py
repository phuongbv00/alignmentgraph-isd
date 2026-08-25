"""EXPERIMENTAL agentic arm: the same 7 artifact families, each produced by an
LLM tool loop (act→observe over the alignment graph) instead of a scripted
call sequence. Opt-in only — nothing in ``core/`` imports this subpackage; it
is reached solely via the benchmark registry (``alignmentgraph-isd-agentic``)
or a direct ``run_agentic_brief`` call. See ``run.py`` for the design notes.
"""
from .run import run_agentic_brief

__all__ = ["run_agentic_brief"]
