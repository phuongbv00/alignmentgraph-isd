"""The package's entry point.

``MetaAgent`` is what every caller uses: the benchmark adapter, ``cli.py`` and
the demo server. It dispatches straight to the one executor. Two passthroughs
used to stand between a caller and that executor and both went 2026-09-05 —
``run_workflow`` here, and the ``run_design_brief`` wrapper in the package
root. Each took the same arguments, returned the same dict, and chose nothing.

What a run reports about itself — provenance, tokens, dump, live emit — lives
in ``core/run_report.py``. That is what lets the import below be module-level:
while those helpers sat in this file the dependency was a cycle, held open by
a deferred import inside the entry point.
"""
from __future__ import annotations

from ..config import HarnessRunConfig
from .agentic import run_agentic_brief
from .brief import DesignBrief


class MetaAgent:
    """Run one design brief through the harness."""

    def __init__(self, config: HarnessRunConfig) -> None:
        self.config = config

    def run(self, design_brief: DesignBrief, *, on_event=None) -> dict:
        """Run the brief and return the result contract (see
        ``core/agentic/run.py``, whose packaging IS that contract).

        ``on_event(kind, payload)`` is an optional consumer that observes the
        run as it happens (see ``TrajectoryLogger``). It changes nothing about
        the returned result; it exists so a UI can show progress during a run
        that takes minutes.

        The ``llm_factory`` guard lives HERE, not on a wrapper above it. It sat
        on ``run_design_brief``, which the benchmark adapter never went
        through — so the one caller that runs unattended for hours was the one
        caller without the check. What an unguarded run looks like is on record
        from the demo app: it starts, every specialist fails, and it
        "completes" in milliseconds with an empty graph under a ``succeeded``
        label. Callers map their own scenario schema to ``DesignBrief`` outside
        the harness and pass a configured ``HarnessRunConfig``.
        """
        if self.config.llm_factory is None:
            raise RuntimeError(
                "MetaAgent.run requires HarnessRunConfig.llm_factory. "
                "Benchmark integrations should construct DesignBrief externally "
                "and pass a configured HarnessRunConfig."
            )
        return run_agentic_brief(self.config, design_brief, on_event=on_event)
