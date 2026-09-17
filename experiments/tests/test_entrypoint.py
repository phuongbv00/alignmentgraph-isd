"""The documented way to invoke the CLI must actually work.

This exists because it did not. Every doc said `isd-exp ...`, which is the
console script an editable install puts on the PATH of the environment you
installed into -- so from a cold shell it is `command not found`. The whole
development of this package used `.venv/bin/python -m isd_experiments.cli`,
so nothing ever exercised the form the docs told a reader to type.

`./isd-exp` is a wrapper that finds the venv beside it and execs the CLI
there, needing no activation and no PATH change. These tests run it the way
the docs say to run it.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from isd_experiments import paths

WRAPPER = paths.exp_root() / "isd-exp"


def run(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(WRAPPER), *args], capture_output=True, text=True,
                          cwd=str(paths.exp_root()), **kw)


class TestWrapper:
    def test_it_exists_and_is_executable(self):
        assert WRAPPER.exists(), "the documented entry point is missing"
        assert WRAPPER.stat().st_mode & 0o111, f"{WRAPPER} is not executable"

    def test_it_runs_from_a_cold_shell(self):
        """No venv activated, nothing on PATH -- the state a reader is in."""
        import os
        bare = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "")}
        out = subprocess.run([str(WRAPPER), "--help"], capture_output=True,
                             text=True, env=bare, cwd=str(paths.exp_root()))
        assert out.returncode == 0, out.stderr
        assert "isd-exp" in out.stdout

    def test_a_missing_venv_explains_itself(self, tmp_path):
        """Copied somewhere without a venv, it must say what to do rather than
        fail with a bare interpreter error."""
        copy = tmp_path / "isd-exp"
        copy.write_bytes(WRAPPER.read_bytes())
        copy.chmod(0o755)
        out = subprocess.run([str(copy), "--help"], capture_output=True, text=True)
        assert out.returncode == 1
        assert "python3 -m venv" in out.stderr, out.stderr
        assert "install -e" in out.stderr, out.stderr


class TestDocumentedCommandsExist:
    """Every `./isd-exp <stage> <sub>` a doc shows is a real subcommand.

    Catches the other half of the same class of error: a command that was
    renamed in code but still written the old way in the guide.
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def known():
        from isd_experiments.cli import build_parser
        parser = build_parser()
        out = set()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        for action in actions:
            for name, sub in (action.choices or {}).items():
                out.add(name)
                for inner in getattr(sub, "_actions", []):
                    for sub_name in (getattr(inner, "choices", None) or {}):
                        out.add(f"{name} {sub_name}")
        return out

    def test_the_guide_only_names_real_commands(self, known):
        guide = paths.docs_root() / "guides" / "benchmark_guides.md"
        if not guide.exists():
            pytest.skip("guide not present")
        text = guide.read_text(encoding="utf-8")
        used = set()
        # `--help` and other flags are not stages.
        for m in re.finditer(r"isd-exp (?!-)([a-z][a-z-]*)(?: (?!-)([a-z][a-z-]*))?", text):
            stage, sub = m.group(1), m.group(2)
            used.add(f"{stage} {sub}" if sub and f"{stage} {sub}" in known else stage)
        unknown = sorted(u for u in used if u not in known)
        assert unknown == [], f"the guide names commands that do not exist: {unknown}"


class TestRunnableHints:
    """A message that says "run X" must name something the reader can type.

    Two forms of the same error, both of which shipped:

    * ``isd-exp`` is a console script on the PATH of whichever environment the
      package was installed into. On a machine using the wrapper it is
      `command not found` -- so a hint naming it causes the very failure it
      meant to prevent.
    * ``pip install ...`` runs in whatever shell the reader has open, which is
      not the environment this code runs in. The install then succeeds, changes
      nothing visible here, and the identical warning prints again. That is
      worse than the first: the reader did exactly what they were told.

    ``paths.cli()`` and ``paths.pip()`` resolve each to a form that works.

    The check walks the AST and looks only at string literals passed to a call,
    so a docstring explaining the hazard (this one, for instance) is not itself
    a violation. A regex over lines flagged those, which is how a guard teaches
    people to work around it.
    """

    HINTS = (("isd-exp ", "paths.cli()"), ("pip install ", "paths.pip()"))

    @staticmethod
    def _call_strings(tree):
        """(lineno, text) for every string literal that is part of a call."""
        import ast

        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    out.append((sub.lineno, sub.value))
                elif isinstance(sub, ast.JoinedStr):
                    # An f-string: only its literal parts can hard-code a name;
                    # the interpolations are where paths.cli() would appear.
                    literal = "".join(v.value for v in sub.values
                                      if isinstance(v, ast.Constant)
                                      and isinstance(v.value, str))
                    out.append((sub.lineno, literal))
        return out

    def _offenders(self, needle: str) -> list[str]:
        import ast

        bad = []
        for path in sorted((paths.exp_root() / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            lines = text.splitlines()
            for lineno, value in self._call_strings(tree):
                if needle not in value:
                    continue
                # The resolved form, or an interpolation right before it.
                window = "\n".join(lines[max(0, lineno - 3):lineno + 2])
                if "paths.cli()" in window or "paths.pip()" in window or "_pip()" in window:
                    continue
                if needle == "isd-exp " and re.search(r"[./\w-]isd-exp ", value):
                    continue          # already a path form
                bad.append(f"{path.name}:{lineno}: {value.strip()[:80]}")
        return bad

    def test_no_message_hard_codes_the_bare_cli(self):
        bad = self._offenders("isd-exp ")
        assert bad == [], ("these hints name a command that may not exist; "
                           "use paths.cli():\n  " + "\n  ".join(bad))

    def test_no_message_hard_codes_a_bare_pip(self):
        bad = self._offenders("pip install ")
        assert bad == [], ("these hints name a pip that may target the wrong "
                           "environment; use paths.pip():\n  " + "\n  ".join(bad))

    def test_shell_hints_use_the_wrapper(self):
        offenders = []
        for path in sorted((paths.exp_root() / "bin").glob("*.sh")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if re.search(r"echo[^\n]*(?<![./\w-])isd-exp ", line):
                    offenders.append(f"{path.name}:{n}: {line.strip()[:90]}")
        assert offenders == []

    def test_doc_command_blocks_use_the_wrapper(self):
        """Inside a fenced block, `isd-exp` is something the reader types."""
        offenders = []
        for rel in ("guides/benchmark_guides.md",):
            doc = paths.docs_root() / rel
            if not doc.exists():
                continue
            fenced = False
            for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip().startswith("```"):
                    fenced = not fenced
                    continue
                if fenced and re.search(r"(?<![./\w-])isd-exp ", line):
                    offenders.append(f"{rel}:{n}: {line.strip()[:90]}")
        assert offenders == []


class TestHelpSubcommand:
    """`help` as a word, not only as a flag.

    `--help` after a stage requires already knowing the stage name; `help` is
    what someone types when they do not. It is also the one command that has to
    work when everything else is broken, so it is dispatched before the config
    is read.
    """

    def test_bare_help_shows_the_overview(self):
        out = run("help")
        assert out.returncode == 0
        assert "<stage>" in out.stdout

    def test_help_for_a_stage(self):
        out = run("help", "score")
        assert out.returncode == 0
        assert "isd-exp score" in out.stdout
        assert "--all-arms" in out.stdout

    def test_help_for_a_nested_subcommand(self):
        out = run("help", "comparison", "pool")
        assert out.returncode == 0
        assert "isd-exp comparison pool" in out.stdout

    def test_unknown_stage_lists_the_real_ones_and_fails(self):
        out = run("help", "nope")
        assert out.returncode == 1
        assert "Unknown stage" in out.stderr
        for stage in ("comparison", "ablation", "report", "audit"):
            assert stage in out.stderr

    def test_unknown_subcommand_shows_its_stage(self):
        """More useful than listing every stage again: the reader had the
        stage right and only needs its subcommands."""
        out = run("help", "report", "nope")
        assert out.returncode == 1
        assert "No subcommand 'nope' under 'report'" in out.stderr
        assert "tables" in out.stdout

    def test_help_works_with_a_broken_config(self, tmp_path):
        """The state someone is most likely to be in when they reach for help."""
        broken = tmp_path / "experiment.toml"
        broken.write_text("this is not valid toml [[[", encoding="utf-8")
        out = run("--config", str(broken), "help")
        assert out.returncode == 0, out.stderr

    def test_every_stage_has_reachable_help(self):
        """A stage whose help crashes is worse than one with no help."""
        from isd_experiments.cli import build_parser, subparsers

        for name in sorted(subparsers(build_parser())):
            out = run("help", *name.split())
            assert out.returncode == 0, f"`help {name}` failed:\n{out.stderr}"
