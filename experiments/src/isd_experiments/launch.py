"""Turn an experiment profile into a launch.

The shell keeps the tmux orchestration -- building a command string whose `$tag`
expands in the child, one session per model slot -- because that is genuinely
shell-shaped work and porting it to subprocess would be more code and more
escaping for no gain. What moves here is the DECISION of what to launch: the
profile comes from experiment.toml, so what an official run consists of is
declared once rather than re-typed at a prompt.

That also closes a hazard that needs guarding wherever `.env` can override an
experiment's own identity: a leftover `DATASET=train_10` from a tuning session
would silently run an official experiment on the wrong split. With the profile
authoritative, the override cannot happen.
"""

from __future__ import annotations

import os
import subprocess

from . import paths
from .config import Profile
from .config import current as current_config

LAUNCHER = paths.exp_root() / "bin" / "launch.sh"

#: Profiles that are not official experiments: no cost prompt, no manifest.
#: Their results never enter the paper, which is also why they have their own
#: tag namespace.
INFORMAL = {"tune"}


def profile_env(profile: Profile, *, slots: str | None = None,
                tags: str | None = None, agents: str | None = None) -> dict[str, str]:
    """The contract launch.sh reads. Overrides are per-invocation, not sticky."""
    slot_list = slots.replace(",", " ") if slots else " ".join(profile.slots)
    tag_list = tags.replace(",", " ") if tags else " ".join(profile.tags)
    roster = agents or ",".join(profile.agents)
    informal = profile.name in INFORMAL

    # Printed by the launcher when a run finishes, so it must name a command
    # the reader can actually type from where they are standing.
    pool_cmd = (f"{paths.cli()} {profile.name} pool"
                if profile.name in {"comparison", "ablation"} else "")

    env = {
        "EXPERIMENT": profile.name,
        "EXPERIMENT_TITLE": profile.title,
        "DATASET": profile.dataset,
        "CANONICAL_DATASET": profile.dataset,
        "AGENTS": roster,
        "RATE_LIMIT": profile.rate_limit,
        "_SLOTS_LIST": slot_list,
        "_RUN_TAGS_LIST": tag_list,
        "SESSION_PREFIX": profile.session_prefix,
        "POOL_HINT": pool_cmd,
        "CONFIRM": "0" if (informal or not profile.confirm) else "1",
        "MANIFEST": "0" if informal else "1",
    }

    # Per-slot defaults, from the declared ladder rather than from blocks
    # naming one model family, so a different ladder is a config edit and not
    # a shell edit. A BASE_URL declared inline serves the "static"
    # provider; the managed .env block overrides it when endpoints are synced.
    cfg = current_config()
    for rung in profile.rungs:
        prefix = rung.env_prefix
        env.setdefault(f"{prefix}_AGENT_MODEL_PROVIDER", cfg.serving.provider)
        env.setdefault(f"{prefix}_AGENT_MODEL_NAME", rung.model)
        env.setdefault(f"{prefix}_AGENT_MODEL_API_KEY_ENVS", cfg.serving.key_env)
        if rung.base_url:
            env.setdefault(f"{prefix}_AGENT_MODEL_BASE_URL", rung.base_url)
    return env


def launch(experiment: str, *, dry_run: bool = False, slots: str | None = None,
           tags: str | None = None, agents: str | None = None) -> int:
    profile = current_config().profile(experiment)
    env = dict(os.environ)
    env.update(profile_env(profile, slots=slots, tags=tags, agents=agents))
    env["DRY_RUN"] = "1" if dry_run else "0"
    if not LAUNCHER.exists():
        raise SystemExit(f"Launcher missing: {LAUNCHER}")
    return subprocess.call(["bash", str(LAUNCHER)], env=env)
