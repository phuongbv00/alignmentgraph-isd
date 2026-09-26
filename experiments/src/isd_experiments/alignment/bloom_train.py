"""Fine-tune the Bloom classifier's 6-way head: ``isd-exp bloom train``.

The recipe is ``createBERT`` from Li et al.'s ``EDM2022 CLO.ipynb`` with ONE
substitution, the head:

===================  ==========================  ==========================
                     createBERT (notebook)       here
===================  ==========================  ==========================
base model           bert-base-uncased           same (``--init``)
max_length           55                          same
batch size           64                          same
epochs               3                           same
warmup_steps         5                           same
weight_decay         0.05                        same
learning rate        transformers default        same (``--lr`` unset)
eval/save strategy   steps, every 10             same
best model           load_best, metric=f1        same
early stopping       patience 10                 same
metric               macro F1 (argmax)           same
split                20% test, then 20% val,     same, stratified on the
                     random_state 666            6-way label (and the source)
**head**             **num_labels=2, x6 levels** **num_labels=6, one model**
===================  ==========================  ==========================

Six binary heads answer "does level L apply"; the panel needs "which level",
so one softmax over six levels gives it directly. A single-label head cannot
use rows the annotators marked at several levels, so those are dropped.

``--init`` is either the base model or an EXISTING checkpoint, which is how
the primary arm is continued on another genre. A checkpoint carries its
held-out splits forward (``training_record.json``): a continued model is also
judged on its parent's held-out set, and no text of that set may enter its
training data, which is checked here rather than assumed.

Exact duplicates (case and spacing aside) are collapsed BEFORE the split, so
one question cannot sit in train and test at once; a text carrying two
different labels is dropped as unusable.

Writes, into ``--output-dir``: the model and tokenizer, ``train_split.csv``,
``val_split.csv``, ``eval_split.csv`` (the held-out test set, the file
``isd-exp bloom validate`` recognises as out-of-sample),
``held_out_metrics.json`` (the number a paper cites) and
``training_record.json`` (what went in, and how).
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
from collections import Counter
from pathlib import Path

from .. import paths
from .bloom import _read_labelled, _repo_relative, cohen_kappa

#: The notebook's ``createBERT`` configuration.
RECIPE = {
    "max_length": 55,
    "batch_size": 64,
    "epochs": 3,
    "warmup_steps": 5,
    "weight_decay": 0.05,
    "eval_steps": 10,
    "patience": 10,
    "test_fraction": 0.2,
    "val_fraction": 0.2,
    "seed": 666,
}

RECORD = "training_record.json"
SPLIT_COLUMNS = ("text", "label", "source")


def normalize_text(text: str) -> str:
    """The key two texts are the same question under: case and spacing aside."""
    return re.sub(r"\s+", " ", str(text or "").lower()).strip(" .?!")


LEVEL_COLUMNS = ("Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create")
_TEXT_COLUMNS = ("text", "Learning_outcome", "QUESTION", "question", "objective")
_LABEL_COLUMNS = ("label", "BT LEVEL", "level", "bloom_level")


def detect_columns(path: Path, text_col: str | None = None, label_col: str | None = None,
                   label_cols: str | None = None) -> dict:
    """The columns ONE labelled CSV carries its text and its level in.

    An explicit column wins; otherwise the header decides, which is what lets
    corpora in different layouts be pooled in one call: the wide layout
    (EDM2022CLO: one column per level, marked) when all six level columns are
    there, else one text column and one label column by the names the known
    corpora use."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f), [])
    text = text_col or next((c for c in _TEXT_COLUMNS if c in header), None)
    if label_cols:
        wide = label_cols
    elif not label_col and all(level in header for level in LEVEL_COLUMNS):
        wide = ",".join(LEVEL_COLUMNS)
    else:
        wide = None
    label = None if wide else (label_col or next((c for c in _LABEL_COLUMNS if c in header), None))
    if text is None or (wide is None and label is None):
        raise SystemExit(f"{Path(path).name}: cannot tell its text and label columns from "
                         f"{header}; pass --text-col with --label-col or --label-cols.")
    return {"text_col": text, "label_col": label, "label_cols": wide}


def load_rows(paths: list[Path], text_col: str | None = None, label_col: str | None = None,
              label_cols: str | None = None) -> tuple[list[dict], dict]:
    """Single-label ``{text, label, source}`` rows from every CSV, deduplicated.

    Returns the rows and a count of what was dropped, which the record keeps."""
    stats = Counter()
    by_key: dict[str, dict] = {}
    labels_of: dict[str, set[int]] = {}
    for path in paths:
        columns = detect_columns(path, text_col, label_col, label_cols)
        for text, gold in _read_labelled(path, columns["text_col"], columns["label_col"] or "",
                                         columns["label_cols"]):
            stats["read"] += 1
            if not str(text).strip() or not gold:
                stats["no_label"] += 1
                continue
            if len(gold) > 1:
                stats["multi_label"] += 1
                continue
            key = normalize_text(text)
            level = next(iter(gold))
            labels_of.setdefault(key, set()).add(level)
            if key in by_key:
                stats["duplicate"] += 1
                continue
            by_key[key] = {"text": str(text).strip(), "label": level, "source": path.stem}
    conflicting = {k for k, levels in labels_of.items() if len(levels) > 1}
    stats["conflicting_label"] = len(conflicting)
    rows = [row for key, row in by_key.items() if key not in conflicting]
    stats["kept"] = len(rows)
    return rows, dict(stats)


def stratified_split(rows: list[dict], fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """``(rest, held)`` with ``fraction`` of each stratum held.

    The stratum is (source, label), so every source set and every level is
    represented in the held part in proportion; a stratum too small to split
    stays whole on the ``rest`` side rather than being dropped."""
    strata: dict[tuple, list[dict]] = {}
    for row in rows:
        strata.setdefault((row["source"], row["label"]), []).append(row)
    rng = random.Random(seed)
    rest, held = [], []
    for key in sorted(strata):
        members = list(strata[key])
        rng.shuffle(members)
        n_held = round(len(members) * fraction) if len(members) >= 2 else 0
        held += members[:n_held]
        rest += members[n_held:]
    return rest, held


def corpus_of(path: Path) -> str:
    """The corpus a labelled CSV belongs to: the directory holding its
    ``data/`` folder (``EDM2022CLO``, ``bloom-classification-aied2026``), or
    its own folder when it sits elsewhere."""
    path = Path(path)
    return path.parent.parent.name if path.parent.name == "data" else path.parent.name


def createbert_split(path: Path, columns: dict, fraction: float,
                     seed: int) -> list[dict]:
    """The held-out rows of a wide-layout corpus, drawn as ``createBERT`` does.

    Li et al.'s notebook splits EDM2022CLO with scikit-learn's
    ``train_test_split`` stratified on the level, over its single-label rows
    in file order, text stripped and NOT deduplicated. Drawing it the same way
    gives, row for row and in order, the 3,755-row test set of Li et al.'s
    recipe, so a checkpoint's objective scores stay comparable with theirs."""
    from sklearn.model_selection import train_test_split  # noqa: PLC0415 - optional heavy dep

    texts, levels = [], []
    for text, gold in _read_labelled(path, columns["text_col"], columns["label_col"] or "",
                                     columns["label_cols"]):
        if len(gold) == 1 and str(text).strip():
            texts.append(str(text).strip())
            levels.append(next(iter(gold)))
    _, held, _, held_levels = train_test_split(texts, levels, test_size=fraction,
                                               random_state=seed, stratify=levels)
    return [{"text": t, "label": level, "source": Path(path).stem}
            for t, level in zip(held, held_levels)]


#: How :func:`derive_test_splits` draws each kind of corpus, as recorded.
CREATEBERT_RECIPE = ("createBERT: scikit-learn train_test_split stratified on the level, "
                     "single-label rows in file order, text stripped, not deduplicated")
POOLED_RECIPE = "stratified_split on (source, level) over the corpus's files, deduplicated"


def derive_test_splits(paths: list[Path], fraction: float, seed: int,
                       text_col: str | None = None, label_col: str | None = None,
                       label_cols: str | None = None
                       ) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """``(corpus -> its held-out rows, corpus -> how they were drawn)``, drawn
    from the corpora themselves.

    Each corpus is split on its own, so pooling corpora never moves one's test
    set: a wide-layout corpus (EDM2022CLO) by :func:`createbert_split`, the
    long-layout files of one corpus (the exam-question sets) pooled,
    deduplicated and split by :func:`stratified_split` on (source, level). The
    same corpora and seed give the same test sets, so they are never stored."""
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(corpus_of(path), []).append(Path(path))
    splits: dict[str, list[dict]] = {}
    recipes: dict[str, str] = {}
    for corpus, members in groups.items():
        layouts = [detect_columns(p, text_col, label_col, label_cols) for p in members]
        if len(members) == 1 and layouts[0]["label_cols"]:
            splits[corpus] = createbert_split(members[0], layouts[0], fraction, seed)
            recipes[corpus] = CREATEBERT_RECIPE
        else:
            rows, _ = load_rows(members, text_col, label_col, label_cols)
            splits[corpus] = stratified_split(rows, fraction, seed)[1]
            recipes[corpus] = POOLED_RECIPE
    return splits, recipes


def write_split(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in SPLIT_COLUMNS})


def read_split(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return [{"text": r["text"], "label": int(r["label"]), "source": r.get("source", "")}
                for r in csv.DictReader(f)]


def inherited_held_out(init: str) -> list[Path]:
    """Held-out splits a checkpoint passed as ``--init`` answers for: its own
    ``eval_split.csv`` and every split its record inherited."""
    root = Path(init)
    if not root.is_dir():
        return []
    splits: list[Path] = []
    record = root / RECORD
    if record.exists():
        data = json.loads(record.read_text(encoding="utf-8"))
        # The record names its own split relative to the checkpoint and an
        # inherited one relative to the monorepo (``_repo_relative``).
        for entry in data.get("held_out_splits", []):
            named = Path(entry["path"])
            for base in (root, paths.bench_root().parent):
                candidate = named if named.is_absolute() else (base / named)
                if candidate.exists():
                    splits.append(candidate.resolve())
                    break
    own = (root / "eval_split.csv").resolve()
    if own.exists() and own not in splits:
        splits.append(own)
    return splits


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(model, tokenizer, rows: list[dict], max_length: int, device: str,
             batch_size: int = 64) -> dict:
    import torch  # noqa: PLC0415 - optional heavy dep

    preds: list[int] = []
    model.eval()
    for start in range(0, len(rows), batch_size):
        batch = [r["text"] for r in rows[start:start + batch_size]]
        inputs = tokenizer(batch, return_tensors="pt", truncation=True, padding=True,
                           max_length=max_length).to(device)
        with torch.no_grad():
            preds += (model(**inputs).logits.argmax(dim=-1) + 1).tolist()
    pairs = [(r["label"], p) for r, p in zip(rows, preds)]
    from sklearn.metrics import f1_score  # noqa: PLC0415 - optional heavy dep
    return {
        "n_held_out": len(rows),
        "accuracy": sum(1 for g, p in pairs if g == p) / len(pairs),
        "cohen_kappa": cohen_kappa(pairs),
        "macro_f1": f1_score([g for g, _ in pairs], [p for _, p in pairs], average="macro"),
        "mean_signed_error": sum(p - g for g, p in pairs) / len(pairs),
    }


def train(*, labels: list[Path], output_dir: Path, init: str = "bert-base-uncased",
          text_col: str | None = None, label_col: str | None = None,
          label_cols: str | None = None,
          max_length: int = RECIPE["max_length"], batch_size: int = RECIPE["batch_size"],
          epochs: float = RECIPE["epochs"], warmup_steps: int = RECIPE["warmup_steps"],
          weight_decay: float = RECIPE["weight_decay"], eval_steps: int = RECIPE["eval_steps"],
          patience: int = RECIPE["patience"], lr: float | None = None,
          test_fraction: float = RECIPE["test_fraction"],
          val_fraction: float = RECIPE["val_fraction"], seed: int = RECIPE["seed"],
          device: str | None = None, overwrite: bool = False) -> int:
    """Split, fine-tune, evaluate on every held-out split, and write the record.

    Each corpus's test set is DRAWN from the corpus (:func:`derive_test_splits`),
    every text in any of them is kept out of train and val, and the model is
    scored on each corpus's test set as well as on their union
    (``eval_split.csv``). A continued checkpoint (``--init`` a directory) is
    also scored on, and kept away from, its parent's held-out sets."""
    import torch  # noqa: PLC0415 - optional heavy dep
    from transformers import (  # noqa: PLC0415 - optional heavy dep
        AutoModelForSequenceClassification,
        AutoTokenizer,
        EarlyStoppingCallback,
        Trainer,
        TrainingArguments,
    )

    output_dir = Path(output_dir)
    if Path(init).is_dir() and Path(init).resolve() == output_dir.resolve():
        raise SystemExit("--output-dir is the --init checkpoint; a continued model "
                         "is written beside its parent, never over it.")
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise SystemExit(f"{output_dir} is not empty; pass --overwrite to replace it.")
    for path in labels:
        if not Path(path).exists():
            raise SystemExit(f"Not found: {path}")

    labels = [Path(p) for p in labels]
    rows, load_stats = load_rows(labels, text_col, label_col, label_cols)
    parents = inherited_held_out(init)
    held_keys = {normalize_text(r["text"]) for split in parents for r in read_split(split)}
    tests, recipes = derive_test_splits(labels, test_fraction, seed,
                                        text_col, label_col, label_cols)
    # A text of a parent's held-out set is never tested on again as this
    # checkpoint's own: it is out of training, and scored under the parent's name.
    tests = {corpus: [r for r in part if normalize_text(r["text"]) not in held_keys]
             for corpus, part in tests.items()}
    test = [r for part in tests.values() for r in part]
    test_keys = {normalize_text(r["text"]) for r in test}
    load_stats["in_parent_held_out"] = sum(
        1 for r in rows if normalize_text(r["text"]) in held_keys)
    load_stats["in_test_split"] = sum(1 for r in rows if normalize_text(r["text"]) in test_keys)
    rest = [r for r in rows if normalize_text(r["text"]) not in held_keys | test_keys]
    if len(rest) < 20:
        raise SystemExit(f"Only {len(rest)} usable rows; nothing to fine-tune on.")
    load_stats["kept_by_source"] = dict(Counter(r["source"] for r in rest))
    train_rows, val_rows = stratified_split(rest, val_fraction, seed)
    random.Random(seed).shuffle(train_rows)
    print(f"rows {len(rows)} (dropped: {load_stats}) -> train {len(train_rows)} / "
          f"val {len(val_rows)} / test {len(test)}")

    # A GPU when there is one. What it costs is bit-for-bit reproducibility of
    # the WEIGHTS (the data, the splits and the recipe reproduce exactly on any
    # device): two runs of this recipe on Apple MPS diverge within ten steps,
    # even under torch's deterministic mode, and two full runs differed by 0.02
    # in kappa and on a tenth of the labels they give agent outputs. On CPU two
    # runs are identical to the last bit, so `device="cpu"` is the way to
    # retrain a checkpoint exactly; the record says which device made it.
    if device is None:
        device = ("cuda" if torch.cuda.is_available()
                  else "mps" if torch.backends.mps.is_available() else "cpu")
    deterministic = device == "cpu"
    tokenizer = AutoTokenizer.from_pretrained(init)
    model = AutoModelForSequenceClassification.from_pretrained(init, num_labels=6)
    # The hub commit the base weights came from: a model id alone does not pin them.
    init_revision = getattr(model.config, "_commit_hash", None)
    model.config.id2label = {i: name for i, name in enumerate(
        ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"])}
    model.config.label2id = {name: i for i, name in model.config.id2label.items()}

    class EncodeDataset(torch.utils.data.Dataset):
        """The notebook's dataset wrapper (same shape, same tensor keys)."""

        def __init__(self, part: list[dict]):
            self.encodings = tokenizer([r["text"] for r in part], truncation=True,
                                       padding=True, max_length=max_length)
            self.labels = [r["label"] - 1 for r in part]

        def __getitem__(self, idx):
            item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
            item["labels"] = torch.tensor(self.labels[idx])
            return item

        def __len__(self):
            return len(self.labels)

    def compute_metrics(prediction):
        from sklearn.metrics import f1_score  # noqa: PLC0415
        predicted = prediction.predictions.argmax(-1)
        return {"f1": f1_score(prediction.label_ids, predicted, average="macro")}

    scratch = output_dir / "_trainer"
    extra = {} if lr is None else {"learning_rate": lr}
    args = TrainingArguments(
        output_dir=str(scratch), num_train_epochs=epochs,
        per_device_train_batch_size=batch_size, per_device_eval_batch_size=batch_size,
        warmup_steps=warmup_steps, weight_decay=weight_decay,
        eval_strategy="steps", eval_steps=eval_steps, save_strategy="steps",
        save_steps=eval_steps, load_best_model_at_end=True, metric_for_best_model="f1",
        save_total_limit=2, seed=seed, report_to=[], logging_steps=eval_steps,
        use_cpu=deterministic,
        # Pinned host memory is a CUDA transfer path; elsewhere it is ignored
        # with a warning on every pass over the data.
        dataloader_pin_memory=device == "cuda", **extra)
    trainer = Trainer(model=model, args=args, train_dataset=EncodeDataset(train_rows),
                      eval_dataset=EncodeDataset(val_rows), compute_metrics=compute_metrics,
                      callbacks=[EarlyStoppingCallback(early_stopping_patience=patience)])
    trainer.train()

    # The best checkpoint is read back through from_pretrained, never through
    # the Trainer's own best-model restore: that one is a bare load_state_dict,
    # and a BERT checkpoint keeps its LayerNorm tensors under the legacy
    # gamma/beta names, which it skips as unexpected -- leaving the restored
    # model with the LAST step's LayerNorms under the best step's other weights.
    best = trainer.state.best_model_checkpoint
    model = (AutoModelForSequenceClassification.from_pretrained(best)
             if best else trainer.model)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    shutil.rmtree(scratch, ignore_errors=True)
    write_split(output_dir / "train_split.csv", train_rows)
    write_split(output_dir / "val_split.csv", val_rows)
    write_split(output_dir / "eval_split.csv", test)
    for corpus, part in tests.items():
        write_split(output_dir / f"test_{corpus}.csv", part)

    model = model.to(device)
    own = _metrics(model, tokenizer, test, max_length, device)
    (output_dir / "held_out_metrics.json").write_text(
        json.dumps(own, indent=2) + "\n", encoding="utf-8")
    parent_metrics = []
    for corpus, part in tests.items():
        measured = _metrics(model, tokenizer, part, max_length, device)
        parent_metrics.append({"path": f"test_{corpus}.csv", "corpus": corpus, **measured})
    for split in parents:
        measured = _metrics(model, tokenizer, read_split(split), max_length, device)
        parent_metrics.append({"path": _repo_relative(split), **measured})

    import transformers  # noqa: PLC0415
    record = {
        "init": _repo_relative(Path(init)) if Path(init).is_dir() else init,
        "init_revision": init_revision,
        "sources": [{"path": _repo_relative(Path(p)), "sha256": _sha256(Path(p))}
                    for p in labels],
        "columns": {_repo_relative(Path(p)): detect_columns(Path(p), text_col, label_col,
                                                             label_cols) for p in labels},
        "rows": load_stats,
        "split": {"test": recipes,
                  "n_test_by_corpus": {corpus: len(part) for corpus, part in tests.items()},
                  "test_fraction": test_fraction,
                  "val_fraction": val_fraction,
                  "seed": seed, "stratified_on": ["source", "label"],
                  "n_train": len(train_rows), "n_val": len(val_rows), "n_test": len(test)},
        "recipe": {"max_length": max_length, "batch_size": batch_size, "epochs": epochs,
                   "warmup_steps": warmup_steps, "weight_decay": weight_decay,
                   "eval_steps": eval_steps, "patience": patience,
                   "learning_rate": lr if lr is not None else args.learning_rate,
                   "best_checkpoint": Path(trainer.state.best_model_checkpoint or "").name,
                   "best_val_macro_f1": trainer.state.best_metric},
        "held_out_metrics": own,
        # Every held-out set this checkpoint answers for: the union, each
        # corpus's test set, and every split it inherited from --init, with
        # its score on each.
        "held_out_splits": [{"path": "eval_split.csv", **own}] + parent_metrics,
        "device": device,
        "torch_num_threads": torch.get_num_threads(),
        "versions": {"transformers": transformers.__version__, "torch": torch.__version__},
    }
    (output_dir / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    print(f"\nWrote {output_dir}")
    print(f"  own held-out  n={own['n_held_out']}: accuracy {own['accuracy']:.3f}, "
          f"kappa {own['cohen_kappa']:.3f}, macro F1 {own['macro_f1']:.3f}, "
          f"signed error {own['mean_signed_error']:+.2f}")
    for entry in parent_metrics:
        print(f"  {entry['path']}  n={entry['n_held_out']}: accuracy {entry['accuracy']:.3f}, "
              f"kappa {entry['cohen_kappa']:.3f}, macro F1 {entry['macro_f1']:.3f}, "
              f"signed error {entry['mean_signed_error']:+.2f}")
    return 0
