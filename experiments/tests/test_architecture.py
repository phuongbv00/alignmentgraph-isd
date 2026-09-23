"""The invariants that keep this package an entrypoint rather than a tangle.

Three rules, each enforced by reading source text rather than by convention,
because every one of them was violated by the arrangement this package
replaces and every violation looked locally reasonable at the time.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from isd_experiments import paths

SRC = paths.exp_root() / "src" / "isd_experiments"
BIN = paths.exp_root() / "bin"


def _sources(*roots):
    for root in roots:
        if root.exists():
            yield from sorted(root.rglob("*.py"))


def _grep(pattern: str, *roots) -> list[str]:
    """Matching `path:line: text` across the given roots, comments included.

    Comments are deliberately not excluded: a rule this package states in
    prose and then breaks in a comment is still a rule the next reader will
    copy.
    """
    rx = re.compile(pattern)
    hits = []
    for path in _sources(*roots):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(paths.exp_root())}:{n}: {line.strip()}")
    return hits


# ── A. one-way dependency ────────────────────────────────────────────────────

class TestDependencyDirection:
    """experiments/ imports the tools. Nothing imports experiments/.

    The benchmark is a submodule shared with an upstream project and the
    harness is the thesis contribution; either one importing the experiment
    that uses it would make both unusable on their own, and would put this
    study's choices inside a tool that other studies are supposed to reuse.
    """

    @pytest.mark.parametrize("sibling", ["isd-agent-benchmark", "alignmentgraph-isd"])
    def test_no_sibling_imports_this_package(self, sibling):
        root = paths.thesis_root() / sibling
        if not root.exists():
            pytest.skip(f"{sibling} is not checked out")
        # git grep skips venvs, caches and results without a hand-maintained
        # exclude list, and falls back cleanly outside a work tree.
        proc = subprocess.run(
            ["git", "grep", "-n", "isd_experiments", "--", "*.py", "*.sh", "*.toml"],
            cwd=root, capture_output=True, text=True,
        )
        assert proc.stdout.strip() == "", (
            f"{sibling} imports isd_experiments -- the dependency runs one way only:\n"
            f"{proc.stdout}"
        )


# ── path anchoring and dynamic imports ───────────────────────────────────────

class TestNoPathHacks:
    """One anchor, no dynamic imports, no sys.path surgery.

    The twenty scripts this replaces each counted `parents[N]` to find the
    repository and inserted the evaluator onto sys.path by hand. Both are
    symptoms of code living in the wrong place; now that it lives in the right
    one, neither has any remaining excuse.
    """

    def test_parents_index_only_in_paths(self):
        offenders = [h for h in _grep(r"parents\[", SRC) if not h.startswith("src/isd_experiments/paths.py:")]
        assert offenders == [], (
            "Resolve locations through paths.py instead of counting directories:\n"
            + "\n".join(offenders)
        )

    def test_no_sys_path_insert(self):
        offenders = _grep(r"sys\.path\.insert", SRC)
        assert offenders == [], (
            "Install packages instead of inserting them onto sys.path:\n" + "\n".join(offenders)
        )

    def test_no_loading_by_file_path(self):
        """Every benchmark component this package uses is an installed package,
        so nothing is loaded by file path. Six sibling scripts once loaded each
        other that way purely because their filenames began with digits."""
        offenders = _grep(r"spec_from_file_location", SRC)
        assert offenders == [], (
            "Import installed packages normally:\n" + "\n".join(offenders)
        )


class TestComponentsNotTheEntryPoint:
    """The benchmark supplies components -- its agents, `shared`, the scenarios,
    the evaluator -- and never the orchestration.

    Running the comparison through the benchmark's own entry point would make
    the study depend on a script it does not own, and customising that script
    is what made it drift from the one the benchmark ships. The runner is this
    package's (`runner/`); the entry point is not named, imported or launched.
    """

    def test_the_entry_point_is_never_named(self):
        offenders = _grep(r"run_benchmark", SRC, BIN)
        assert offenders == [], (
            "the benchmark's entry point is referenced again:\n" + "\n".join(offenders)
        )


# ── C. no vendor lock-in ─────────────────────────────────────────────────────

class TestNoVendorNames:
    """Hosts and model families are configuration, not code.

    experiment.toml declares the ladder, the encoder arms and the URL each is
    reached at; a rung can be any OpenAI-compatible endpoint, on any host or
    none. Nothing in src/ discovers, names or authenticates against a
    particular host any more -- so a vendor name here is always the beginning
    of a lock-in, and it always looks like a harmless literal in a diff.
    """

    @pytest.mark.parametrize("vendor", ["runpod", "qwen", "nemotron"])
    def test_vendor_absent_from_code(self, vendor):
        offenders = _grep(rf"(?i){vendor}", SRC, BIN)
        assert offenders == [], (
            f"{vendor!r} belongs in experiment.toml, not in code:\n" + "\n".join(offenders)
        )


# ── naming ───────────────────────────────────────────────────────────────────

class TestSemanticNaming:
    """Names say what a thing is, not which numbered question it served.

    `rq1`/`tn2` are indices into one draft's numbering: opaque to a reader and
    stale the moment anything is renumbered -- the same defect that made the
    old `07_`/`09_` filenames meaningless. The two measurement families are
    `llm_judge` and `alignment`; the two experiments are `comparison` and
    `ablation`.
    """

    def test_no_question_or_experiment_indices(self):
        offenders = [h for h in _grep(r"(?i)\b(rq[12]|tn[12])\b", SRC, BIN)]
        assert offenders == [], (
            "Name these semantically (llm_judge/alignment, comparison/ablation):\n"
            + "\n".join(offenders)
        )


class TestOneResultsVariable:
    """One env var names the results tree, end to end.

    One name for one fact: a second name that could only ever hold the same
    value is a relay rather than a setting, one more thing to keep in step and
    one more place for the two to disagree.

    The name is deliberately plain (`RESULTS_DIR`); `doctor` reports an
    inherited value rather than assuming it, since a plain name in a global
    namespace is one another tool can also set.
    """

    NAME = "RESULTS_DIR"

    def test_no_second_name_survives(self):
        offenders = _grep(r"ISD_BENCH_RESULTS_DIR|ISD_RESULTS_DIR", SRC, BIN)
        assert offenders == [], (
            "a second name for the results tree is back:\n" + "\n".join(offenders)
        )

    def test_paths_reads_it(self, monkeypatch, tmp_path):
        from isd_experiments import paths as p

        monkeypatch.setenv(self.NAME, str(tmp_path))
        assert p.results_root() == tmp_path

    def test_bench_hands_the_same_name_through(self, monkeypatch, tmp_path):
        """Passed through to a subprocess, not translated."""
        from isd_experiments import bench

        monkeypatch.setenv(self.NAME, str(tmp_path))
        env = bench.bench_env()
        assert env[self.NAME] == str(tmp_path)
        assert not [k for k in env if "BENCH_RESULTS" in k]

    def test_the_runner_writes_under_it(self, monkeypatch, tmp_path):
        from isd_experiments.runner.execute import run_dir_for

        monkeypatch.setenv(self.NAME, str(tmp_path))
        assert run_dir_for("split", "org/model", "t1", "20260101_000000").parent == tmp_path

    def test_the_launcher_exports_it(self):
        matrix = (BIN / "_matrix.sh").read_text(encoding="utf-8")
        assert f"export {self.NAME}=" in matrix
