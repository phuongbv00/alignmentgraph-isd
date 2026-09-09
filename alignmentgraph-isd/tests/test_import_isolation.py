"""The demo web app lives INSIDE this package (``alignmentgraph_isd.server``),
but the benchmark installs the package plain. So importing the package must
never drag FastAPI/uvicorn/SQLModel into the experiment environment.

These tests are the guard for that rule. They run in a subprocess because
``sys.modules`` in the pytest process is already polluted by whatever else the
suite imported.
"""
from __future__ import annotations

import subprocess
import sys


# Kept in sync with pyproject's [server] extra. If a dependency is added there,
# add it here too — that is the whole point of this test.
SERVER_ONLY_MODULES = ["fastapi", "uvicorn", "sqlmodel", "starlette", "pydantic_settings"]


def _run(code: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"subprocess failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_importing_package_does_not_pull_server_deps():
    leaked = _run(
        "import sys, json, alignmentgraph_isd\n"
        f"probe = {SERVER_ONLY_MODULES!r}\n"
        "print(json.dumps([m for m in probe if m in sys.modules]))"
    )
    assert leaked == "[]", f"importing alignmentgraph_isd leaked server-only modules: {leaked}"


def test_importing_cli_does_not_pull_server_deps():
    """``cli.py`` grows a ``serve`` subcommand; its server import must be lazy,
    inside the handler, not at module scope."""
    leaked = _run(
        "import sys, json, alignmentgraph_isd.cli\n"
        f"probe = {SERVER_ONLY_MODULES!r}\n"
        "print(json.dumps([m for m in probe if m in sys.modules]))"
    )
    assert leaked == "[]", f"importing alignmentgraph_isd.cli leaked server-only modules: {leaked}"


def test_public_api_surface_unchanged():
    """The benchmark imports from the top level. Adding the server must not
    disturb the exported names."""
    import alignmentgraph_isd

    assert set(alignmentgraph_isd.__all__) == {
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
        "HarnessCancelled",
    }
