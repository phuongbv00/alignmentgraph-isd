"""A report is judged only when every LLM judge of every row returned its scores.

A judge that errors leaves the row scored by the others under the same roster
names. MEASURED (run t1 20261012_090924): a router out of credit answered 402
mid-run, and rows carried a trajectory score from one or two judges of three
while their ADDIE score had all three.
"""
from __future__ import annotations

import json

from isd_experiments.judge import llm

ROSTER = ("a/one", "b/two", "c/three")


def _report(tmp_path, judges):
    row = {"agent_id": "agent-x", "total_score": 60.0, "addie_median": 55.0,
           "trajectory_score": 70.0, "phase_scores": {"analysis": 1}, "judges": judges}
    (tmp_path / llm.REPORT).write_text(json.dumps({"comparison": {"rankings": [row]}}))
    return tmp_path


def _judge(model, **over):
    return {"model": model, "addie_score": 55.0, "trajectory_score": 70.0, "error": None, **over}


def test_a_report_every_judge_scored_is_judged(tmp_path):
    d = _report(tmp_path, [_judge(m) for m in ROSTER])
    assert llm.report_gaps(d, ("agent-x",), ROSTER) is None


def test_a_judge_that_errored_makes_the_report_a_gap(tmp_path):
    d = _report(tmp_path, [_judge("a/one"), _judge("b/two"),
                           _judge("c/three", trajectory_score=None,
                                  error="Error code: 402 - would exceed your available credits")])
    gap = llm.report_gaps(d, ("agent-x",), ROSTER)
    assert gap and "c/three" in gap
