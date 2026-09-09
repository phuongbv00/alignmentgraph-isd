"""Deterministic JSON salvage (Try 6 in ``parse_json_response``): the four
malformed-JSON classes a 0.8B model emitted in the ladder run — invalid
escapes, stray quotes after brackets, several top-level values, and mid-string
truncation at the completion cap — must parse to a usable dict instead of
returning ``{}`` (which would cost a full regeneration, or an empty section
once the regen budget is exhausted). ``salvage=False`` must keep the strict
pre-salvage behavior, which ``tools.coerce_args`` at the transport boundary
relies on."""
from __future__ import annotations

import warnings

import pytest

from alignmentgraph_isd.core.llm_io import parse_json_response


def test_invalid_escape_inside_string():
    # \' is not a legal JSON escape ("Expecting ',' delimiter" in the run log).
    raw = r'{"screen_title": "Learning with AI based on their background.\'", "frame_number": 2}'
    parsed = parse_json_response(raw)
    assert parsed.get("frame_number") == 2


def test_stray_quote_after_bracket():
    # A dict in an array closed as ``]}",`` (log: '..."Project design doc"]}",').
    raw = '{"items": [{"materials": ["lesson notes", "design doc"]}", {"event": "Gain attention"}]}'
    parsed = parse_json_response(raw)
    assert isinstance(parsed.get("items"), list)
    assert parsed["items"][0] == {"materials": ["lesson notes", "design doc"]}


def test_two_top_level_values_merge():
    # The model emitted a top-level array, then a second top-level object
    # (log: '..."linked_module": "MOD-01"}\n]\n{\n  "learner_materials": [').
    # The array element carries a bad escape too, so no clean sub-object can be
    # decoded — only whole-text salvage recovers the second value.
    raw = '[{"id": "LO-01", "note": "it\\\'s"}]\n{"learner_materials": [{"id": "M1"}]}'
    parsed = parse_json_response(raw)
    assert parsed.get("learner_materials") == [{"id": "M1"}]


def test_truncated_mid_string_keeps_prefix():
    # Response cut at the completion cap in the middle of a string value:
    # everything before the cut must survive.
    raw = '{"objectives": [{"id": "O1"}], "strategies": ["s1"], "storyboard": "Frame 2: Learni'
    parsed = parse_json_response(raw)
    assert parsed.get("objectives") == [{"id": "O1"}]
    assert parsed.get("strategies") == ["s1"]


def test_pre_salvage_paths_unchanged():
    # Literal control chars + trailing commas are fixed by the targeted tries,
    # never reaching salvage — well-formed-enough responses keep byte-identical
    # parse results.
    raw = '{"a": "line1\nline2", "b": [1, 2,],}'
    assert parse_json_response(raw, salvage=False) == {"a": "line1\nline2", "b": [1, 2]}


def test_salvage_false_keeps_strict_behavior():
    # Same class of input as test_invalid_escape_inside_string, but with the
    # strict mode the correction-turn check uses: parse must fail loudly.
    raw = r'{"screen_title": "background.\'", "frame_number": 2}'
    with pytest.warns(UserWarning, match="all attempts failed"):
        assert parse_json_response(raw, salvage=False) == {}


def test_empty_response_still_empty():
    # Salvage must not fabricate content: an empty payload stays {} so the
    # empty-section regen safety net still triggers.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert parse_json_response("") == {}
    assert parse_json_response("   \n") == {}
