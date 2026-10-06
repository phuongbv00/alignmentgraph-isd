"""The code-freeze manifest: what an official run was produced by.

The roadmap makes this a gate -- an official experiment runs only against a
frozen version, and the manifest is what makes "frozen" checkable afterwards.
It replaces a 45-line heredoc inside the launcher, which is the wrong home for
the file the reproducibility section promises: a heredoc has no schema and no
test.

What it records, and why each is here rather than assumed:

* **Commits and dirty flags** for all three trees (the monorepo, the benchmark
  submodule, the harness package). A dirty tree means the recorded commit does
  not describe what actually ran, so the flag matters as much as the hash.
* **The experiment declaration**, hashed and embedded. The ladder, the roster
  and the arms are configuration now, so the config IS part of the version.
* **The resolved profile** -- dataset, agents, slots, tags -- so a reader does
  not have to re-resolve it from the config to know what ran.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from .. import paths
from ..config import current as current_config

#: 2: the flat `models` list (was `ladder`), with `family` per model.
SCHEMA_VERSION = 2


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def tree_state(root: Path) -> dict:
    """Commit and cleanliness of one checkout."""
    if not root.exists():
        return {"path": str(root), "present": False}
    return {
        "path": str(root),
        "present": True,
        "commit": _git(root, "rev-parse", "HEAD") or "unknown",
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        # A dirty tree makes the commit a lie about what ran, so this is not
        # decoration: an official run with dirty=true is not reproducible.
        "dirty": bool(_git(root, "status", "--porcelain")),
    }


def config_fingerprint() -> dict:
    cfg = current_config()
    raw = cfg.source.read_bytes() if cfg.source.exists() else b""
    return {
        "path": str(cfg.source),
        "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        # Flat, and keyed by slot: `family` is part of what identifies a model
        # now that it is declared per model rather than once for the file, and
        # a manifest that left it out could not tell two same-size models of
        # different families apart.
        "models": [{"slot": m.slot, "family": m.family, "model": m.model,
                    "display": m.display}
                   for m in cfg.models],
        # Spelled out beside the hash, which already covers them byte-wise: the
        # limits and the judge roster decide what every reported number means,
        # and a reader should not have to re-read a config that has moved on to
        # find out which ones a frozen run was answered under.
        "serving": {
            "context_window": cfg.serving.context_window,
        },
        "generation": {
            "max_output_tokens": cfg.generation.max_output_tokens,
            "streaming": cfg.generation.streaming,
            "thinking_budget": cfg.generation.thinking_budget,
            "temperature": cfg.generation.temperature,
            "structured_outputs": cfg.generation.structured_outputs,
        },
        "harness": {
            "fanout_workers": cfg.harness.fanout_workers,
        },
        # Recorded as DECLARED, never as resolved: a blank per-judge provider
        # means the reader derives that judge's label from its own model slug,
        # and writing the profile in here would record a label no report will
        # carry. Names of key variables only; the declaration holds no value.
        "judge": {
            "declared": cfg.judge.declared,
            "provider": cfg.judge.provider,
            "base_url": cfg.judge.base_url,
            "key_env": cfg.judge.key_env,
            "models": [{"name": m.name, "provider": m.provider,
                        "base_url": m.base_url, "key_envs": list(m.key_envs)}
                       for m in cfg.judge.models],
        },
    }


def build(*, experiment: str | None = None, tag: str | None = None) -> dict:
    cfg = current_config()
    doc = {
        "schema_version": SCHEMA_VERSION,
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "trees": {
            "thesis": tree_state(paths.thesis_root()),
            "benchmark": tree_state(paths.bench_root()),
            "harness": tree_state(paths.harness_root()),
        },
        "config": config_fingerprint(),
    }
    if experiment:
        p = cfg.profile(experiment)
        doc["profile"] = {
            "name": p.name, "dataset": p.dataset, "tags": list(p.tags),
            "slots": list(p.slots), "agents": list(p.agents),
            "arms": [{"id": a.id, **a.expected_flags} for a in p.arms],
        }
    return doc


def write(*, experiment: str | None = None, tag: str | None = None,
          out: Path | None = None, quiet: bool = False) -> Path:
    from .. import util

    target = out or (paths.results_root() / "freeze_manifest.json")
    doc = build(experiment=experiment, tag=tag)
    util.write_json_atomic(target, doc)
    if not quiet:
        dirty = [k for k, v in doc["trees"].items() if v.get("dirty")]
        print(f"wrote {target}")
        if dirty:
            print(f"! uncommitted changes in: {', '.join(dirty)} — "
                  f"the recorded commits do not describe what would run.")
    return target


def verify(*, manifest: Path | None = None, quiet: bool = False) -> int:
    """Compare the working tree against a frozen manifest.

    Exit 1 on any difference. After a freeze, a rerun is legitimate only for a
    genuine technical failure -- never because a number came out unflattering --
    so a drifted tree has to be visible before the rerun, not after.
    """
    src = manifest or (paths.results_root() / "freeze_manifest.json")
    if not src.exists():
        raise SystemExit(f"No manifest at {src}. Write one with:  {paths.cli()} freeze write")
    frozen = json.loads(src.read_text(encoding="utf-8"))
    now = build()

    problems = []
    for name, was in frozen.get("trees", {}).items():
        if not was.get("present"):
            continue
        is_ = now["trees"].get(name, {})
        if was.get("commit") != is_.get("commit"):
            problems.append(f"{name}: commit {was.get('commit', '?')[:8]} -> "
                            f"{is_.get('commit', '?')[:8]}")
        if is_.get("dirty"):
            problems.append(f"{name}: working tree is dirty")
    if frozen.get("config", {}).get("sha256") != now["config"]["sha256"]:
        problems.append("experiment.toml has changed since the freeze")

    if not quiet:
        if problems:
            print(f"DRIFT since {frozen.get('frozen_at')}:")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"clean: the tree matches the freeze of {frozen.get('frozen_at')}")
    return 1 if problems else 0
