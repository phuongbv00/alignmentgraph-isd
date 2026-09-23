"""The adapter translates the runner's rate posture into its own call cap.

The runner bounds how many AGENTS run at once and publishes which posture it
chose (``BENCHMARK_RATE_LIMIT``); it knows nothing about any agent's internal
knobs. This agent fans out inside one run — the multi arm runs
content_designer and rubric_designer in the same superstep, each issuing one
Developer call per work set, peaking at ~12 concurrent requests — so the
translation has to live here. Unbounded, a shared endpoint answered the overflow
with HTTP 429 on the two multi arms only, putting a throttling handicap on the
``agent_mode`` ablation axis itself.
"""
from __future__ import annotations

import pytest

from isd_experiments.runner.adapters.alignmentgraph_isd import (
    DEFAULT_LLM_MAX_CONCURRENCY,
    LLM_CONCURRENCY_BY_RATE_LIMIT,
    _regen_settings_from_env,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("BENCHMARK_RATE_LIMIT", "HARNESS_LLM_MAX_CONCURRENCY",
                 "HARNESS_LLM_MIN_INTERVAL", "HARNESS_REGEN_BACKOFF",
                 "HARNESS_REGEN_BUDGET", "BENCHMARK_DELAY", "HARNESS_FANOUT_WORKERS",
                 "HARNESS_DEVELOPMENT_MODE"):
        monkeypatch.delenv(name, raising=False)


def _cap() -> int:
    return _regen_settings_from_env()["llm_max_concurrency"]


@pytest.mark.parametrize("preset", sorted(LLM_CONCURRENCY_BY_RATE_LIMIT))
def test_every_preset_maps_to_its_cap(monkeypatch, preset):
    monkeypatch.setenv("BENCHMARK_RATE_LIMIT", preset)
    assert _cap() == LLM_CONCURRENCY_BY_RATE_LIMIT[preset]


def test_the_presets_are_the_runners_own_names():
    """A typo here silently drops the agent to the default on every run."""
    from isd_experiments.runner.llm import RATE_PRESETS
    assert set(LLM_CONCURRENCY_BY_RATE_LIMIT) == set(RATE_PRESETS)


def test_a_tighter_posture_never_allows_more_calls():
    order = ["conservative", "moderate", "aggressive", "turbo"]
    caps = [LLM_CONCURRENCY_BY_RATE_LIMIT[p] for p in order]
    assert caps == sorted(caps)


def test_no_posture_named_falls_back_to_the_default(monkeypatch):
    assert _cap() == DEFAULT_LLM_MAX_CONCURRENCY          # direct package use
    monkeypatch.setenv("BENCHMARK_RATE_LIMIT", "not-a-preset")
    assert _cap() == DEFAULT_LLM_MAX_CONCURRENCY          # an unknown name


def test_the_cap_is_always_bounded_by_default():
    """The bug this guards: an unbounded fan-out is what drew the 429s, so no
    path through the resolver may leave the cap at 0 unless asked to."""
    assert DEFAULT_LLM_MAX_CONCURRENCY > 0
    assert all(v > 0 for v in LLM_CONCURRENCY_BY_RATE_LIMIT.values())


def test_explicit_override_beats_the_preset(monkeypatch):
    monkeypatch.setenv("BENCHMARK_RATE_LIMIT", "turbo")
    monkeypatch.setenv("HARNESS_LLM_MAX_CONCURRENCY", "1")
    assert _cap() == 1


def test_override_of_zero_opts_out(monkeypatch):
    monkeypatch.setenv("BENCHMARK_RATE_LIMIT", "turbo")
    monkeypatch.setenv("HARNESS_LLM_MAX_CONCURRENCY", "0")
    assert _cap() == 0


def test_unparseable_override_falls_back_to_the_preset(monkeypatch):
    monkeypatch.setenv("BENCHMARK_RATE_LIMIT", "moderate")
    monkeypatch.setenv("HARNESS_LLM_MAX_CONCURRENCY", "abc")
    assert _cap() == LLM_CONCURRENCY_BY_RATE_LIMIT["moderate"]


def test_min_interval_is_off_unless_asked_for(monkeypatch):
    """Wiring it to BENCHMARK_DELAY would put a 2 s sleep before every call."""
    monkeypatch.setenv("BENCHMARK_DELAY", "2.0")
    assert "llm_min_interval_seconds" not in _regen_settings_from_env()
    monkeypatch.setenv("HARNESS_LLM_MIN_INTERVAL", "0.25")
    assert _regen_settings_from_env()["llm_min_interval_seconds"] == 0.25


def test_regen_backoff_tracks_the_runners_delay(monkeypatch):
    monkeypatch.setenv("BENCHMARK_DELAY", "2.0")
    assert _regen_settings_from_env()["regen_backoff_seconds"] == 2.0


def test_the_development_mode_is_the_package_default_unless_asked_for(monkeypatch):
    """The ladder runs sampled development; a results dir written in full has
    to have asked for it, and a typo must not silently become either."""
    assert "development_mode" not in _regen_settings_from_env()
    monkeypatch.setenv("HARNESS_DEVELOPMENT_MODE", " Full ")
    assert _regen_settings_from_env()["development_mode"] == "full"
    monkeypatch.setenv("HARNESS_DEVELOPMENT_MODE", "everything")
    assert "development_mode" not in _regen_settings_from_env()


def test_fanout_workers_are_off_unless_asked_for(monkeypatch):
    """The ladder ran the sequential fan-out; a results dir produced with
    workers has to have asked for them explicitly."""
    assert "fanout_workers" not in _regen_settings_from_env()
    monkeypatch.setenv("HARNESS_FANOUT_WORKERS", "3")
    assert _regen_settings_from_env()["fanout_workers"] == 3
    monkeypatch.setenv("HARNESS_FANOUT_WORKERS", "")
    assert "fanout_workers" not in _regen_settings_from_env()


@pytest.mark.parametrize("value", ["0", "-2", "many"])
def test_a_malformed_fanout_worker_count_raises(monkeypatch, value):
    """The runner publishes it from experiment.toml and the freeze manifest
    records it, so a value dropped here would be a posture on record that
    never ran."""
    monkeypatch.setenv("HARNESS_FANOUT_WORKERS", value)
    with pytest.raises(ValueError):
        _regen_settings_from_env()
