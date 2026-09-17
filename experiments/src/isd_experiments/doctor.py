"""Check that this checkout can actually run an experiment.

Every failure here is one that otherwise surfaces much later and much less
clearly: an uninstalled agent becomes an ImportError inside an agent registry,
a missing `.env` becomes an authentication error against a pod, a missing
symlink becomes a benchmark that silently has no configuration.
"""

from __future__ import annotations

import os

from . import bench, paths



class Check:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.failed = 0

    def ok(self, what: str, detail: str = "") -> None:
        self.rows.append(("ok", what, detail))

    def warn(self, what: str, detail: str = "") -> None:
        self.rows.append(("warn", what, detail))

    def bad(self, what: str, detail: str = "") -> None:
        self.rows.append(("FAIL", what, detail))
        self.failed += 1

    def report(self) -> None:
        width = max((len(w) for _s, w, _d in self.rows), default=0)
        for status, what, detail in self.rows:
            mark = {"ok": "  ok  ", "warn": " warn ", "FAIL": " FAIL "}[status]
            print(f"[{mark}] {what.ljust(width)}  {detail}")


def run(*, fix: bool = False) -> int:
    c = Check()

    # 1. The checkout.
    try:
        root = paths.bench_root()
        c.ok("benchmark checkout", str(root))
    except SystemExit as exc:
        c.bad("benchmark checkout", str(exc).splitlines()[0])
        c.report()
        return 1

    for name, path in (("harness package", paths.harness_root()),
                       ("Bloom corpus", paths.edm_root())):
        (c.ok if path.exists() else c.warn)(name, str(path))

    # 2. The packages run_benchmark.py imports. It is launched as a subprocess
    #    under THIS interpreter, so the seven agents, the harness and the
    #    evaluator have to be installed here; absent, the failure is an
    #    ImportError deep inside an agent registry, which reads like an agent
    #    bug rather than an install one.
    absent = bench.missing_packages()
    if absent and fix:
        bench.install_packages(absent)
        absent = bench.missing_packages()
    if absent:
        c.bad("benchmark packages",
              f"{len(absent)} not installed ("
              f"{', '.join(bench.dist_name(p) for p in absent)}) — run "
              f"`{paths.cli()} doctor --fix`")
    else:
        c.ok("benchmark packages",
             f"{len(bench.bench_packages())} editable in {bench.bench_python()}")

    # 3. Configuration, credentials, and the symlink that keeps the benchmark's
    #    own entry points configured after `.env` moved here.
    env = paths.env_file()
    if env.exists():
        c.ok(".env", str(env))
    else:
        c.warn(".env", f"absent — copy .env.example to {env}")

    link = root / ".env"
    if link.is_symlink() and link.resolve() == env.resolve():
        c.ok("benchmark .env symlink", "-> experiments/.env")
    elif link.exists():
        c.warn("benchmark .env symlink", "a real file, not a link to experiments/.env")
    elif fix and env.exists():
        link.symlink_to(os.path.relpath(env, root))
        c.ok("benchmark .env symlink", "created")
    else:
        c.warn("benchmark .env symlink",
               f"missing — run `{paths.cli()} doctor --fix` (run_benchmark.py --check "
               "and the smoke script read it from the benchmark root)")

    # 4. The declaration, and the packages the pipeline imports.
    try:
        from .config import current
        cfg = current()
        c.ok("experiment.toml", f"{len(cfg.models)} models, "
                                f"{len(cfg.profiles)} experiments")
    except SystemExit as exc:
        c.bad("experiment.toml", str(exc).splitlines()[0])

    # 5. Where results go. RESULTS_DIR is a deliberately plain name -- it is the
    #    same variable run_benchmark.py reads, so there is only one -- but a
    #    plain name in a GLOBAL namespace is one another tool can also set. A
    #    run silently writing somewhere else is the failure that would cost
    #    most, so an inherited value is reported rather than assumed.
    inherited = os.environ.get("RESULTS_DIR")
    if inherited:
        c.warn("results root", f"{paths.results_root()}  (from RESULTS_DIR in your "
                               f"environment, not the default — check this is yours)")
    else:
        c.ok("results root", str(paths.results_root()))
    from .alignment.presets import current as arms
    for key, arm in arms().bloom.items():
        if arm.checkpoint_path is None:
            c.ok(f"bloom arm '{key}'", "rule-based, no checkpoint needed")
        elif arm.available:
            c.ok(f"bloom arm '{key}'", str(arm.checkpoint_path))
        else:
            c.warn(f"bloom arm '{key}'",
                   f"no checkpoint at {arm.checkpoint_path} — the arm is SKIPPED, "
                   f"never silently swapped for another")

    c.report()
    return 1 if c.failed else 0
