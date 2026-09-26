"""`isd-exp bloom train`: what goes in, how it is split, and what a
continued checkpoint answers for. The fine-tuning itself needs a model and is
not run here; everything around it is pure and is."""

import csv
import json
from pathlib import Path

import pytest

from isd_experiments import paths
from isd_experiments.alignment import bloom_train
from isd_experiments.cli import build_parser

#: The evidence the primary Bloom checkpoint ships with: its record, its
#: held-out scores and each corpus's test set.
FIXTURE = Path(__file__).parent / "fixtures" / "bloom"


def _csv(path: Path, rows: list[tuple[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["QUESTION", "BT LEVEL"])
        writer.writerows(rows)
    return path


def test_duplicates_are_collapsed_and_a_conflicting_text_is_dropped(tmp_path):
    a = _csv(tmp_path / "a.csv", [("Define X.", "Remember"), ("Compare A and B", "Understand"),
                                  ("Design a plan", "Create")])
    b = _csv(tmp_path / "b.csv", [("define x", "Remember"), ("Compare A and B.", "Analyze")])
    rows, stats = bloom_train.load_rows([a, b], "QUESTION", "BT LEVEL", None)
    assert stats["duplicate"] == 2 and stats["conflicting_label"] == 1
    assert sorted(r["text"] for r in rows) == ["Define X.", "Design a plan"]
    assert {r["source"] for r in rows} == {"a"}


def test_the_split_is_stratified_disjoint_and_deterministic():
    rows = [{"text": f"{s}-{level}-{i}", "label": level, "source": s}
            for s in ("x", "y") for level in (1, 2) for i in range(10)]
    rows.append({"text": "lonely", "label": 6, "source": "x"})
    rest, held = bloom_train.stratified_split(rows, 0.2, 666)
    assert {r["text"] for r in rest}.isdisjoint(r["text"] for r in held)
    assert len(held) == 8, "2 of 10 from each of the four strata"
    assert any(r["text"] == "lonely" for r in rest), "a one-row stratum is never held"
    assert (rest, held) == bloom_train.stratified_split(rows, 0.2, 666)


def test_a_continued_checkpoint_answers_for_its_parents_held_out_split(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    bloom_train.write_split(parent / "eval_split.csv",
                            [{"text": "Define X.", "label": 1, "source": "edm"}])
    child = tmp_path / "child"
    child.mkdir()
    bloom_train.write_split(child / "eval_split.csv",
                            [{"text": "Design a plan", "label": 6, "source": "q"}])
    (child / bloom_train.RECORD).write_text(json.dumps({"held_out_splits": [
        {"path": "eval_split.csv"}, {"path": str(parent / "eval_split.csv")}]}))
    assert bloom_train.inherited_held_out(str(parent)) == [(parent / "eval_split.csv").resolve()]
    assert set(bloom_train.inherited_held_out(str(child))) == {
        (child / "eval_split.csv").resolve(), (parent / "eval_split.csv").resolve()}
    assert bloom_train.inherited_held_out("bert-base-uncased") == []


def test_the_cli_reaches_every_training_option():
    args = build_parser().parse_args([
        "bloom", "train", "a.csv", "b.csv", "--output-dir", "out", "--init", "ckpt",
        "--text-col", "QUESTION", "--label-col", "BT LEVEL", "--seed", "1"])
    assert [str(p) for p in args.labels] == ["a.csv", "b.csv"]
    assert (args.init, args.text_col, args.label_col, args.seed) == (
        "ckpt", "QUESTION", "BT LEVEL", 1)


def test_each_corpus_is_read_in_its_own_layout(tmp_path):
    """Pooling EDM2022CLO's wide layout with a question set's long one: the
    header decides each file's columns, an explicit column still wins."""
    wide = tmp_path / "wide.csv"
    with wide.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Learning_outcome", *bloom_train.LEVEL_COLUMNS])
        writer.writerow(["Explain the water cycle", "", "1", "", "", "", ""])
        writer.writerow(["Explain and design a pump", "", "1", "", "", "", "1"])
    long = _csv(tmp_path / "long.csv", [("Design a pump", "Create")])
    assert bloom_train.detect_columns(wide)["label_cols"].startswith("Remember,")
    assert bloom_train.detect_columns(long) == {
        "text_col": "QUESTION", "label_col": "BT LEVEL", "label_cols": None}
    rows, stats = bloom_train.load_rows([wide, long])
    assert sorted((r["text"], r["label"]) for r in rows) == [
        ("Design a pump", 6), ("Explain the water cycle", 2)]
    assert stats["multi_label"] == 1
    assert bloom_train.detect_columns(long, text_col="BT LEVEL")["text_col"] == "BT LEVEL"


QUESTION_SETS = ("Gani_2023_collected-dataset-1200", "Mohammed-and-Omar_2020_126",
                 "Sangodiah_2017_415", "yahya-2012")


def _pairs(rows):
    return [(r["text"], r["label"]) for r in rows]


@pytest.mark.skipif(not (paths.edm_root() / "data" / "sample_full.csv").exists(),
                    reason="the EDM2022CLO submodule is not checked out")
def test_the_objectives_test_set_is_drawn_again_row_for_row():
    """The test set is never stored as an input: it is drawn from EDM2022CLO
    the way createBERT draws it, and this holds that drawing it again gives
    the 3,755 rows the shipped checkpoint was scored on, in order."""
    tests, recipes = bloom_train.derive_test_splits(
        [paths.edm_root() / "data" / "sample_full.csv"], 0.2, 666)
    stored = bloom_train.read_split(FIXTURE / "test_EDM2022CLO.csv")
    assert _pairs(tests["EDM2022CLO"]) == _pairs(stored)
    assert recipes["EDM2022CLO"] == bloom_train.CREATEBERT_RECIPE


@pytest.mark.skipif(not paths.bloom_questions_root().joinpath("data").exists(),
                    reason="the bloom-classification-aied2026 submodule is not checked out")
def test_the_questions_test_set_is_drawn_again_row_for_row():
    data = paths.bloom_questions_root() / "data"
    tests, recipes = bloom_train.derive_test_splits(
        [data / f"{name}_revised.csv" for name in QUESTION_SETS], 0.2, 666)
    stored = bloom_train.read_split(FIXTURE / "test_bloom-classification-aied2026.csv")
    assert _pairs(tests["bloom-classification-aied2026"]) == _pairs(stored)
    assert recipes["bloom-classification-aied2026"] == bloom_train.POOLED_RECIPE


def test_the_shipped_checkpoint_is_held_to_both_test_sets():
    """Trained from the base model on both corpora, each corpus's test set
    drawn from the corpus itself; the record names how each was drawn, the
    device it was trained on and the base weights' revision."""
    record = json.loads((FIXTURE / "training_record.json").read_text())
    by_corpus = {e.get("corpus"): e for e in record["held_out_splits"] if e.get("corpus")}
    assert set(by_corpus) == {"EDM2022CLO", "bloom-classification-aied2026"}
    assert by_corpus["EDM2022CLO"]["n_held_out"] == 3755
    assert by_corpus["bloom-classification-aied2026"]["n_held_out"] == 464
    assert record["split"]["test"]["EDM2022CLO"] == bloom_train.CREATEBERT_RECIPE
    assert record["init"] == "bert-base-uncased" and record["init_revision"]
    assert record["device"] and record["rows"]["in_parent_held_out"] == 0
