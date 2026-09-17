"""Generated tables must carry the same numbers as before the move.

The artifact NAMES change in this migration -- `tab_rq1*` becomes
`tab_llm_judge_*` and `tab_rq2*` becomes `tab_alignment*`, because a filename
should say what is in it rather than index a draft's question numbering -- and
so do the internal LaTeX labels, and so does the score/signal vocabulary in
the generated comments, and the macro suffixes now come from a model's slot
rather than from its parameter count. Nothing else may change.

So the comparison normalises exactly those renames and nothing more. A
difference that survives normalisation is a number that moved, which is the
one thing this refactor must not do.
"""

from __future__ import annotations

import re

import pytest

from isd_experiments import paths, schema
from isd_experiments.report import tables

GOLDEN = paths.exp_root() / "tests" / "fixtures" / "golden"

#: new artifact name -> the name the replaced generator wrote
RENAMED = {
    "tab_llm_judge_addie.tex": "tab_rq1.tex",
    "tab_llm_judge_total.tex": "tab_rq1_total.tex",
    "tab_llm_judge_trajectory.tex": "tab_rq1_traj.tex",
    "tab_alignment.tex": "tab_rq2_alignment.tex",
    "tab_alignment_panel.tex": "tab_rq2_panel.tex",
    "stats_macros.tex": "stats_macros.tex",
    "stats_summary.md": "stats_summary.md",
}

#: The rename, as text substitutions, applied to the GOLDEN before comparing.
SUBSTITUTIONS = [
    (r"tab_rq1_ladder", "tab_llm_judge_ladder"),
    (r"tab_rq1", "tab_llm_judge"),
    (r"tab:rq1-ladder", "tab:llm-judge-ladder"),
    (r"tab_rq2_alignment", "tab_alignment"),
    (r"tab_rq2_panel", "tab_alignment_panel"),
    (r"tab:rq2-alignment", "tab:alignment"),
    (r"tab:rq2-panel", "tab:alignment-panel"),
    # The caption named a model family that every column header already
    # carries, and named it imprecisely. Neutral text now; the family itself
    # comes from config and appears in the headers.
    (r"on the Qwen size ladder\.", "on the model size ladder."),
    # Vocabulary: a panel value is an "alignment signal", never an "alignment
    # score" -- "score" belongs to the LLM judge alone, so the word itself says
    # which instrument produced the number.
    (r"alignment scores", "alignment signals"),
    (r"alignment score\b", "alignment signal"),
    # Macro prefixes said which draft question a number served. They now say
    # which instrument produced it, the same rule the file names follow.
    (r"\brqOne", "llmJudge"),
    (r"\brqTwo", "alignment"),
    # Macro SUFFIXES were spelled from a parameter count, so two models of the
    # same size in different families produced one macro name and LaTeX kept
    # whichever came last. They are spelled from the slot now, which is unique
    # by construction. Only the name moves -- every number either side of this
    # substitution still has to match, which is what the rest of the file
    # checks.
    (r"(ZeroEightB|TwoB|FourB|NineB)([}\)])", r"Qwen\1\2"),
]

#: Provenance lines: a timestamp and the producing command, different by design.
HEADER = re.compile(r"^\s*%?\s*(AUTO-GENERATED|generated_at:|Generated:|source pooled)", re.I)


def normalise(text: str, apply_rename: bool) -> list[str]:
    if apply_rename:
        for old, new in SUBSTITUTIONS:
            text = re.sub(old, new, text)
    return [ln.rstrip() for ln in text.splitlines()
            if not HEADER.match(ln.strip().lstrip("%").strip()) and not HEADER.match(ln.strip())]


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("tables")
    pooled = schema.load(GOLDEN / "pooled_comparison.json")
    for name, content in tables.build(pooled).items():
        (out / name).write_text(content, encoding="utf-8")
    return out


@pytest.mark.parametrize("new_name,gold_name", sorted(RENAMED.items()))
def test_content_is_unchanged_modulo_the_rename(generated, new_name, gold_name):
    gold = normalise((GOLDEN / "generated" / gold_name).read_text(encoding="utf-8"), True)
    new = normalise((generated / new_name).read_text(encoding="utf-8"), False)
    assert len(gold) == len(new), f"{new_name}: {len(gold)} lines before, {len(new)} after"
    mismatches = [f"L{i}\n  before: {a}\n  after : {b}"
                  for i, (a, b) in enumerate(zip(gold, new)) if a != b]
    assert mismatches == [], f"{new_name}:\n" + "\n".join(mismatches[:5])


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
