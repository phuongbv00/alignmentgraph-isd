"""Shared fixtures.

The synthetic run tree is built on demand rather than committed. It is ~250
small JSON files that ``factory.py`` reproduces deterministically, so
committing them would add bulk to every clone and every diff for no
information. The pooled JSON and generated artifacts under ``fixtures/golden/``
are different: they are regression snapshots of what the current code makes of
that tree, committed so a change that moves a number shows up as a diff.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import factory  # noqa: E402

MINI = Path(__file__).parent / "fixtures" / "mini_run"


def _ensure_mini_run() -> Path:
    """Build the run tree if it is not there. Cheap and deterministic."""
    if not (MINI / "test_90_benchmark_qwen3.5-0.8b_r1_20260101_000000").exists():
        factory.build(MINI, tag="r1")
    if not (MINI / "test_30_benchmark_qwen3.5-0.8b_a1_20260101_000000").exists():
        factory.build_ablation(MINI, tag="a1")
    return MINI


def pytest_configure(config):
    """Built once per session, before collection touches it."""
    _ensure_mini_run()


@pytest.fixture(scope="session")
def mini_run() -> Path:
    return _ensure_mini_run()
