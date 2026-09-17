"""The pooled contract, checked at the door rather than 400 lines in."""

from __future__ import annotations

import json
import math

import pytest

from isd_experiments import paths, schema

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden" / "pooled_comparison.json"


@pytest.fixture(scope="module")
def pooled():
    return schema.load(GOLDEN)


class TestGoldenIsValid:
    """The frozen reference was produced by the scripts being replaced, so if
    it does not satisfy this contract the contract is wrong, not the file."""

    def test_loads(self, pooled):
        assert pooled["models"]

    def test_labels_ordered_smallest_first(self, pooled):
        from isd_experiments.runs import parse_size_key
        sizes = [parse_size_key(lb) for lb in schema.labels(pooled)]
        assert sizes == sorted(sizes)

    def test_every_agent_row_is_complete(self, pooled):
        for label in schema.labels(pooled):
            for agent in ("alignmentgraph-isd", "react-isd", "baseline"):
                row = schema.agent_row(pooled, label, agent)
                assert row, f"{agent} missing at {label}"
                assert all(k in row for k in schema.REQUIRED_AGENT)

    def test_agent_row_is_empty_for_an_unscored_cell(self, pooled):
        assert schema.agent_row(pooled, "nonesuch", "react-isd") == {}

    def test_optional_layers_are_reported_not_required(self, pooled):
        """Alignment scoring and token accounting are separate steps; pooling
        before they run is a legitimate partial state."""
        assert "alignment" in schema.optional_layers(pooled)
        assert schema.optional_layers({"models": []}) == []


class TestStrictJson:
    def test_written_file_has_no_nan_token(self, tmp_path):
        """A bare NaN is not valid JSON. It reaches the pooled structure
        legitimately -- an agent that produced nothing has nothing to average --
        so the fix is to emit null, not to forbid the state."""
        p = tmp_path / "pooled.json"
        schema.write(p, {"models": [{"label": "x", "agents": {"a": {"mean_addie": float("nan")}}}]})
        text = p.read_text()
        assert "NaN" not in text and "Infinity" not in text
        assert json.loads(text)["models"][0]["agents"]["a"]["mean_addie"] is None

    def test_write_is_atomic_leaving_no_temp_files(self, tmp_path):
        schema.write(tmp_path / "p.json", {"a": 1})
        assert [f.name for f in tmp_path.iterdir()] == ["p.json"]


class TestValidationFailsLoudly:
    def test_missing_file_names_the_command_that_makes_one(self, tmp_path):
        with pytest.raises(SystemExit, match="pool"):
            schema.load(tmp_path / "absent.json")

    def test_malformed_json_says_re_pool(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text("{not json")
        with pytest.raises(SystemExit, match="Re-pool"):
            schema.load(p)

    def test_empty_models_is_refused(self):
        with pytest.raises(SystemExit, match="nothing was pooled"):
            schema.validate({"generated_at": "x", "config": {}, "models": []})

    def test_incomplete_agent_row_names_the_gap_and_the_agent(self):
        doc = {"generated_at": "x", "config": {},
               "models": [{"label": "m", "comparisons": {},
                           "agents": {"react-isd": {"mean_addie": 1.0}}}]}
        with pytest.raises(SystemExit) as exc:
            schema.validate(doc)
        assert "react-isd" in str(exc.value) and "mean_total" in str(exc.value)

    def test_missing_top_level_key_is_named(self):
        with pytest.raises(SystemExit, match="config"):
            schema.validate({"generated_at": "x",
                             "models": [{"label": "m", "agents": {"a": {}}, "comparisons": {}}]})

    def test_model_without_comparisons_is_refused(self):
        """Comparisons are per-model because every paired test is made within
        one model size; a model row without them was pooled incompletely."""
        with pytest.raises(SystemExit, match="comparisons"):
            schema.validate({"generated_at": "x", "config": {},
                             "models": [{"label": "m", "agents": {"a": {}}}]})
