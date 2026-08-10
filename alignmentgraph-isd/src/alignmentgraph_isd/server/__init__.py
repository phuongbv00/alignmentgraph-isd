"""FastAPI demo app for AlignmentGraph-ISD.

Lives inside the package so the demo ships with the thing it demos, but it is
strictly optional: everything here needs the ``[server]`` extra, and nothing in
``alignmentgraph_isd`` imports this subpackage. The benchmark installs the
package plain and must never pull FastAPI in — ``tests/test_import_isolation.py``
is the guard for that.

    pip install 'alignmentgraph-isd[server]'
    alignmentgraph-isd serve
"""
from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str):
    # Deferred so `import alignmentgraph_isd.server` stays cheap and so an
    # informative error surfaces if the extra is missing.
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
