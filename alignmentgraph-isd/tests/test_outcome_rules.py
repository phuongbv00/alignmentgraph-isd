"""How many objectives the outcomes stage is told to write, and why.

The number is Biggs & Tang's — "programme and course outcomes alike should
rarely exceed five or six in number, otherwise it is practically impossible to
align teaching/learning activities and assessment tasks to them all" — from the
source this work already cites for constructive alignment. It is FLAT: their
five-or-six is stated for a semester-long course, so length does not raise it.

TOLD, never enforced. Nothing trims a longer list, so these tests hold what the
agent is told, not what it produces.
"""
from __future__ import annotations

import re

from alignmentgraph_isd.core import rulebook
from alignmentgraph_isd.core.agentic.specialists import STEPS

_OUTCOMES = next(s for s in STEPS if s.name == "outcomes")


def test_the_prompt_states_the_number_the_module_declares():
    """Imported, never written twice — the rule ``RULES_ACTIVITY_DEV_PLAN``
    already follows for ``max_units("activity")``."""
    text = _OUTCOMES.task_block()
    found = re.search(r"at least 1 and no more\s+than (\d+)", text)
    assert found, "the outcomes rules no longer state a ceiling"
    assert int(found.group(1)) == rulebook.MAX_OBJECTIVES


def test_the_rules_are_fully_interpolated():
    """``RULES_OUTCOMES`` is filled at import like every other block. A stray
    ``%(...)s`` would reach the model verbatim."""
    assert "%(" not in rulebook.RULES_OUTCOMES


def test_the_ceiling_does_not_vary():
    """Flat by construction: no per-run machinery, so nothing can make one run
    — or one arm — hear a different number. `rules_vars`/`rules_text` were
    removed with the brief-derived ceiling and must not come back for this."""
    assert isinstance(rulebook.MAX_OBJECTIVES, int)
    assert not hasattr(_OUTCOMES, "rules_vars")
    assert _OUTCOMES.task_block() == _OUTCOMES.task_block()


def test_the_rules_forbid_climbing_the_levels_for_one_gap():
    """The MEASURED over-generation mechanism, and the reason a ceiling alone
    would not have fixed it.

    Runs single_20260903_224852 and single_20260901_133402 wrote 33 DISTINCT
    objectives from 3-4 gaps by sweeping Bloom levels per gap — apply, then
    analyze, then evaluate, then create about one capability. Gap count did not
    drive it (r = -0.006 over 55 runs); the level enum beside a "not a fixed
    progression" sentence did. The rules now rule the sweep out by name.
    """
    text = _OUTCOMES.task_block().lower()
    assert "climbing the levels" in text
    assert "the one objective" in text


def test_the_rules_never_claim_the_harness_discards_anything():
    """The ceiling is told and not enforced. A sentence like "only the first N
    reach the design" would be the prompt telling the model something untrue
    about the harness."""
    text = _OUTCOMES.task_block().lower()
    for claim in ("discard", "will be dropped", "only the first", "reach the design"):
        assert claim not in text, claim


def test_the_reason_travels_with_the_number():
    """A bare ceiling is the thing a reader — and a model — asks "why" about.
    Biggs's own warrant is alignment tractability, which is also this harness's
    failure mode, so the prompt carries it rather than asserting a bare cap."""
    text = _OUTCOMES.task_block().lower()
    assert "align" in text and "assessment tasks" in text
