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
    """One anchor, one dynamic import, no sys.path surgery.

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
        offenders = [h for h in _grep(r"sys\.path\.insert", SRC)
                     if not h.startswith("src/isd_experiments/bench.py:")]
        assert offenders == [], (
            "Install packages instead of inserting them onto sys.path:\n" + "\n".join(offenders)
        )

    def test_spec_loading_only_in_bench(self):
        """run_benchmark.py has no install route, so exactly one of these is
        legitimate. Six sibling scripts used to load each other this way purely
        because their filenames began with digits."""
        offenders = [h for h in _grep(r"spec_from_file_location", SRC)
                     if not h.startswith("src/isd_experiments/bench.py:")]
        assert offenders == [], (
            "Import siblings normally; bench.py holds the one unavoidable case:\n"
            + "\n".join(offenders)
        )


# ── C. no vendor lock-in ─────────────────────────────────────────────────────

class TestNoVendorNames:
    """Hosts and model families are configuration, not code.

    experiment.toml declares the ladder and the serving provider; a rung can be
    any OpenAI-compatible endpoint. A vendor name that creeps back into src/
    re-establishes the lock-in while looking like a harmless literal in a diff.
    """

    #: A provider module is allowed to name the host it implements -- that is
    #: what it is for. Nothing else may.
    ALLOWED = {
        "src/isd_experiments/serve/providers/runpod_agents.py",
        "src/isd_experiments/serve/providers/runpod_embed.py",
        "src/isd_experiments/serve/providers/__init__.py",
        "src/isd_experiments/serve/providers/base.py",
    }

    @pytest.mark.parametrize("vendor", ["runpod", "qwen", "nemotron"])
    def test_vendor_absent_from_code(self, vendor):
        offenders = [
            h for h in _grep(rf"(?i){vendor}", SRC, BIN)
            if not any(h.startswith(a + ":") for a in self.ALLOWED)
        ]
        assert offenders == [], (
            f"{vendor!r} belongs in experiment.toml, not in code:\n" + "\n".join(offenders)
        )


# ── naming ───────────────────────────────────────────────────────────────────

class TestSemanticNaming:
    """Names say what a thing is, not which numbered question it served.

    `rq1`/`tn2` are indices into one draft's numbering: opaque to a reader and
    stale the moment anything is renumbered -- the same defect that made the
    old `07_`/`09_` filenames meaningless. The two measurement families are
    `judge` and `alignment`; the two experiments are `comparison` and
    `ablation`.
    """

    def test_no_question_or_experiment_indices(self):
        offenders = [h for h in _grep(r"(?i)\b(rq[12]|tn[12])\b", SRC, BIN)]
        assert offenders == [], (
            "Name these semantically (judge/alignment, comparison/ablation):\n"
            + "\n".join(offenders)
        )


class TestOneResultsVariable:
    """One env var names the results tree, end to end.

    There were briefly two -- one read by this package, one exported to
    run_benchmark.py -- and the launcher set the second from the first. That is
    a relay, not a setting: they could only ever hold the same value, so the
    second name was one more thing to keep in step and one more place for them
    to disagree.

    The name is deliberately plain (`RESULTS_DIR`) because it is literally the
    variable run_benchmark.py reads; `doctor` reports an inherited value rather
    than assuming it, since a plain name in a global namespace is one another
    tool can also set.
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
        """Passed through, not translated: the benchmark reads this variable."""
        from isd_experiments import bench

        monkeypatch.setenv(self.NAME, str(tmp_path))
        env = bench.bench_env()
        assert env[self.NAME] == str(tmp_path)
        assert not [k for k in env if "BENCH_RESULTS" in k]

    def test_the_benchmark_reads_the_same_name(self):
        """The one-line change in the submodule. Read as source rather than
        imported, because importing run_benchmark.py executes 67 KB of it."""
        src = (paths.bench_root() / "run_benchmark.py").read_text(encoding="utf-8")
        assert f'os.environ.get("{self.NAME}")' in src

    def test_the_launcher_exports_it(self):
        matrix = (BIN / "_matrix.sh").read_text(encoding="utf-8")
        assert f"export {self.NAME}=" in matrix
