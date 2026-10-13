"""Generated tables must carry the numbers the frozen pooled fixtures imply.

The golden pooled files (``fixtures/golden/pooled_{comparison,ablation}.json``)
are built from the synthetic run tree, and ``fixtures/golden/generated/`` and
``fixtures/golden/generated_ablation/`` hold the tables generated from them. A difference here is a number, a column or a caption
that moved, which a generator change must do on purpose: regenerate the
goldens from that fixture and read the diff before committing it.

Provenance lines (timestamp, producing command) differ by design and are
ignored.
"""

from __future__ import annotations

import re

import pytest

from isd_experiments import paths, schema
from isd_experiments.report import ablation_tables, tables

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"

#: Every artifact `tables.build` writes, compared one by one.
ARTIFACTS = sorted([
    "stats_macros.tex", "stats_summary.md", "tab_alignment.tex", "tab_alignment_panel.tex",
    "tab_llm_judge_addie.tex", "tab_llm_judge_total.tex", "tab_llm_judge_trajectory.tex",
])

#: Every artifact `ablation_tables.build` writes.
ABLATION_ARTIFACTS = sorted([
    "abl_macros.tex", "stats_ablation.md", "tab_ablation.tex", "tab_ablation_factorial.tex",
    "tab_ablation_factorial_full.tex", "tab_ablation_process.tex",
])

#: Provenance lines: a timestamp and the producing command, different by design.
HEADER = re.compile(r"^\s*%?\s*(AUTO-GENERATED|generated_at:|Generated:|source pooled)", re.I)


def normalise(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines()
            if not HEADER.match(ln.strip().lstrip("%").strip()) and not HEADER.match(ln.strip())]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("tables")
    pooled = schema.load(GOLDEN / "pooled_comparison.json")
    for name, content in tables.build(pooled).items():
        (out / name).write_text(content, encoding="utf-8")
    return out


def test_the_generator_writes_exactly_the_compared_set(generated):
    assert sorted(p.name for p in generated.iterdir()) == ARTIFACTS


@pytest.mark.parametrize("name", ARTIFACTS)
def test_content_matches_the_golden(generated, name):
    gold = normalise((GOLDEN / "generated" / name).read_text(encoding="utf-8"))
    new = normalise((generated / name).read_text(encoding="utf-8"))
    assert len(gold) == len(new), f"{name}: {len(gold)} lines in the golden, {len(new)} now"
    mismatches = [f"L{i}\n  golden: {a}\n  now   : {b}"
                  for i, (a, b) in enumerate(zip(gold, new)) if a != b]
    assert mismatches == [], f"{name}:\n" + "\n".join(mismatches[:5])


@pytest.fixture(scope="module")
def generated_ablation(tmp_path_factory):
    out = tmp_path_factory.mktemp("ablation_tables")
    pooled = schema.load(GOLDEN / "pooled_ablation.json")
    for name, content in ablation_tables.build(pooled).items():
        (out / name).write_text(content, encoding="utf-8")
    return out


def test_the_ablation_generator_writes_exactly_the_compared_set(generated_ablation):
    assert sorted(p.name for p in generated_ablation.iterdir()) == ABLATION_ARTIFACTS


@pytest.mark.parametrize("name", ABLATION_ARTIFACTS)
def test_ablation_content_matches_the_golden(generated_ablation, name):
    gold = normalise((GOLDEN / "generated_ablation" / name).read_text(encoding="utf-8"))
    new = normalise((generated_ablation / name).read_text(encoding="utf-8"))
    assert len(gold) == len(new), f"{name}: {len(gold)} lines in the golden, {len(new)} now"
    mismatches = [f"L{i}\n  golden: {a}\n  now   : {b}"
                  for i, (a, b) in enumerate(zip(gold, new)) if a != b]
    assert mismatches == [], f"{name}:\n" + "\n".join(mismatches[:5])


class TestArtifactNaming:
    def test_no_artifact_indexes_a_question_number(self, generated):
        names = [p.name for p in generated.iterdir()]
        assert not [n for n in names if re.search(r"(?i)rq[12]|tn[12]", n)]

    def test_no_label_indexes_a_question_number(self, generated):
        offenders = []
        for p in sorted(generated.glob("*.tex")):
            for m in re.finditer(r"\\label\{([^}]*)\}", p.read_text(encoding="utf-8")):
                if re.search(r"(?i)rq[12]|tn[12]", m.group(1)):
                    offenders.append(f"{p.name}: {m.group(1)}")
        assert offenders == []

    def test_family_prefix_is_not_doubled(self, generated):
        """The family comes from config now; a caller that also hard-codes it
        produces 'Family-Family-4B'. That happened once during the move."""
        from isd_experiments.config import current
        family = next((m.family for m in current().models if m.family), "")
        if not family:
            pytest.skip("no display family configured")
        for p in sorted(generated.glob("*.tex")):
            assert f"{family}-{family}-" not in p.read_text(encoding="utf-8"), p.name
