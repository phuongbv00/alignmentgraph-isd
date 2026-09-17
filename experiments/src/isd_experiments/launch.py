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
from .judge import judge_env

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

    # Per-slot values, from the declared ladder rather than from blocks naming
    # one model family, so a different ladder is a config edit and not a shell
    # edit. The ENDPOINT is assigned, not defaulted: the declaration is the one
    # place a rung's URL is written, so a leftover export of the same name in
    # the surrounding shell must not decide where a run's requests go.
    cfg = current_config()
    for model in profile.models:
        prefix = model.env_prefix
        # UNDERSCORED, like the serving limits below and for the same reason:
        # the launcher sources .env in its own shell after this, so anything
        # published under the name the benchmark reads is taken back by a stale
        # line in that file. That is not a cosmetic difference here. A leftover
        # <SLOT>_AGENT_MODEL_NAME sends the run out under a model the
        # declaration never named, while `freeze write` fingerprints the
        # declaration -- the manifest would attest to a model that never ran.
        # A leftover BASE_URL(S), especially an EMPTY one, sends it nowhere.
        env[f"_{prefix}_AGENT_MODEL_API_SPEC"] = cfg.api_spec_for(model)
        env[f"_{prefix}_AGENT_MODEL_NAME"] = model.model
        env[f"_{prefix}_AGENT_MODEL_API_KEY_ENVS"] = cfg.key_env_for(model)
        if model.base_urls:
            # Plural even for one endpoint: one shape to read, and a second
            # endpoint later is then a pure config change.
            env[f"_{prefix}_AGENT_MODEL_BASE_URLS"] = ",".join(model.base_urls)

    # The serving limits and the judge roster travel under UNDERSCORED names.
    # The launcher sources .env in its own shell before it reads any of this, so
    # a variable published under the name the benchmark reads would be taken
    # back by a stale line in that file; the launcher turns these into a command
    # prefix and a flag list, which nothing downstream can override.
    env.update({f"_{k}": v for k, v in judge_env(cfg.judge).items()})
    serving = cfg.serving
    if serving.context_window is not None:
        env["_AGENT_MODEL_CONTEXT_WINDOW"] = str(serving.context_window)
    if serving.max_output_tokens is not None:
        env["_AGENT_MODEL_MAX_OUTPUT_TOKENS"] = str(serving.max_output_tokens)
    if serving.streaming is not None:
        # "0" rather than nothing: the prefix has to be able to turn streaming
        # OFF against an environment that says otherwise.
        env["_AGENT_MODEL_STREAMING"] = "1" if serving.streaming else "0"
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
