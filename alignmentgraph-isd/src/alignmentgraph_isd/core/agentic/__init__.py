"""The executor: the 6 artifact families, each produced by a native
tool-calling act→observe loop.

It honours both ablation axes; ``core/runner.py::run_workflow`` dispatches
here. See ``run.py`` for the design notes and ``loop.py`` for the transport.
"""
from .run import run_agentic_brief

__all__ = ["run_agentic_brief"]
