"""Turn an experiment profile into a launch.

The shell keeps the tmux orchestration -- one session per model slot, the run
tags of a slot one after another inside it -- because that is genuinely
shell-shaped work. What each session RUNS is `isd-exp run <experiment>
--foreground` for one slot and one tag, which reads the declaration itself
(models, serving limits, judge roster), so nothing the run depends on travels
through the shell at all.

What the shell still receives is what it prints and records: the cost banner,
the dry-run plan and the manifest. Those values travel under UNDERSCORED names,
because the launcher sources .env in its own shell after this, and a value
published under a name .env can also carry would be taken back by a stale line
there -- a manifest attesting to a model that never ran.

That also closes a hazard that needs guarding wherever `.env` can override an
experiment's own identity: a leftover `DATASET=train_10` from a tuning session
would silently run an official experiment on the wrong split. With the profile
authoritative, the override cannot happen.
"""

from __future__ import annotations

import os
import subprocess

from . import paths
from .alignment.presets import current as declared_arms
from .config import Profile
from .config import current as current_config
from .judge import judge_env

LAUNCHER = paths.exp_root() / "bin" / "launch.sh"

#: Profiles that are not official experiments: no cost prompt, no manifest.
#: Their results never enter the paper, which is also why they have their own
#: tag namespace.
INFORMAL = {"tune"}


def profile_env(profile: Profile, *, slots: str | None = None,
                tags: str | None = None, agents: str | None = None,
                judge: bool = False) -> dict[str, str]:
    """The contract launch.sh reads. Overrides are per-invocation, not sticky."""
    slot_list = slots.replace(",", " ") if slots else " ".join(profile.slots)
    tag_list = tags.replace(",", " ") if tags else " ".join(profile.tags)
    roster = agents or ",".join(profile.agents)
    informal = profile.name in INFORMAL

    # Printed by the launcher when a run finishes, so it must name a command
    # the reader can actually type from where they are standing.
    pool_cmd = (f"{paths.cli()} pool {profile.name}"
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
        "JUDGE_AFTER_RUN": "1" if judge else "0",
    }

    # Per-slot values, from the declared ladder rather than from blocks naming
    # one model family, so a different ladder is a config edit and not a shell
    # edit. The ENDPOINT is assigned, not defaulted: the declaration is the one
    # place a rung's URL is written, so a leftover export of the same name in
    # the surrounding shell must not decide where a run's requests go.
    cfg = current_config()
    # The child reads the declaration itself; it has to read THIS one. Baked
    # into its command rather than exported, because a tmux server that is
    # already running hands a new session its own environment, not ours.
    env["_ISD_EXPERIMENT_CONFIG"] = str(cfg.source)
    if judge:
        # Read only when asked: a declaration that never judges alignment need
        # not declare the instruments for it.
        # For the plan only: every declared arm as "<encoder>,<bloom>", arms
        # separated by "; ", so a reader sees which instruments score the run.
        env["_ALIGNMENT_JUDGE_ARM_LIST"] = "; ".join(
            f"{enc},{bloom}" for enc, bloom in declared_arms().star())
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

    # The window, the generation settings, the harness posture and the judge
    # roster travel under UNDERSCORED names, for the plan and the manifest only
    # (the run itself reads the declaration). The launcher sources .env in its
    # own shell first, so a plain name could be taken back by a stale line there.
    env.update({f"_{k}": v for k, v in judge_env(cfg.judge).items()})
    if cfg.serving.context_window is not None:
        env["_AGENT_MODEL_CONTEXT_WINDOW"] = str(cfg.serving.context_window)
    gen = cfg.generation
    if gen.max_output_tokens is not None:
        env["_AGENT_MODEL_MAX_OUTPUT_TOKENS"] = str(gen.max_output_tokens)
    if gen.streaming is not None:
        # "0" rather than nothing: the prefix has to be able to turn streaming
        # OFF against an environment that says otherwise.
        env["_AGENT_MODEL_STREAMING"] = "1" if gen.streaming else "0"
    if gen.thinking_budget is not None:
        env["_AGENT_MODEL_THINKING_BUDGET"] = str(gen.thinking_budget)
    if gen.temperature is not None:
        env["_AGENT_MODEL_TEMPERATURE"] = str(gen.temperature)
    if cfg.harness.fanout_workers is not None:
        env["_HARNESS_FANOUT_WORKERS"] = str(cfg.harness.fanout_workers)
    return env


def launch(experiment: str, *, dry_run: bool = False, slots: str | None = None,
           tags: str | None = None, agents: str | None = None,
           judge: bool = False) -> int:
    profile = current_config().profile(experiment)
    env = dict(os.environ)
    env.update(profile_env(profile, slots=slots, tags=tags, agents=agents,
                           judge=judge))
    env["DRY_RUN"] = "1" if dry_run else "0"
    if not LAUNCHER.exists():
        raise SystemExit(f"Launcher missing: {LAUNCHER}")
    return subprocess.call(["bash", str(LAUNCHER)], env=env)
