"""The executor's PARTS: the act→observe loops, their tools, the stage table
and the Developer fan-out.

The run that drives them is ``core/runner.py::MetaAgent.run`` — it sits there,
not here, because it orchestrates a dozen private helpers of its own and
splitting it from them would make every one of them public API for one caller.
This package deliberately exports nothing: each module is imported by name.
"""
