"""The declared LLM judge roster, rendered into the variables it is read from.

The evaluator resolves its roster from the environment: ``JUDGE_MODEL_NAMES`` is
the master list and every other plural is index-aligned to it, with ``|``
separating the credentials of ONE judge inside a ``,``-separated list of judges.

Both the singular and the plural form are emitted, always. Two auxiliary
evaluators read only the singular names as their own fallback chain, so a
declaration that set the plurals alone would leave those two on a default the
declaration never mentions.

One renderer, because both callers -- launching a run and re-judging a finished
one -- have to name the same roster or a repaired row is rejected for having
been scored by a different one.
"""

from __future__ import annotations

from .config import Judge


def judge_env(judge: Judge) -> dict[str, str]:
    """The environment a judge declaration stands for, empty when none is made.

    Empty means the reader answers for the roster as it did before: whatever the
    environment carries, then the evaluator's own default.
    """
    if not judge.declared:
        return {}

    env = {"JUDGE_MODEL_NAMES": ",".join(m.name for m in judge.models)}
    for key, value in (("JUDGE_MODEL_PROVIDER", judge.provider),
                       ("JUDGE_MODEL_BASE_URL", judge.base_url),
                       ("JUDGE_MODEL_API_KEY_ENV", judge.key_env)):
        if value:
            env[key] = value

    # A plural is emitted only when the declaration actually says something
    # per judge. An absent plural is not a gap: the reader falls back per index
    # to the singular above, so filling one in with that same default would
    # assert nothing new -- while asserting it for a field whose fallback is
    # DERIVED rather than defaulted would change the answer.
    #
    # `provider` is that field. With no plural, the reader infers each judge's
    # provider from its `vendor/model` slug, and that inferred value is what
    # lands in the comparison report and in the roster identity a re-judge is
    # checked against. Writing the profile into every slot would relabel both,
    # so the plural is emitted only when every judge names its own.
    if all(m.provider for m in judge.models):
        env["JUDGE_MODEL_PROVIDERS"] = ",".join(m.provider for m in judge.models)

    if any(m.base_url for m in judge.models):
        env["JUDGE_MODEL_BASE_URLS"] = ",".join(m.base_url or judge.base_url
                                                for m in judge.models)

    key_env_groups = [m.key_envs or ((judge.key_env,) if judge.key_env else ())
                      for m in judge.models]
    if any(m.key_envs for m in judge.models):
        env["JUDGE_MODEL_API_KEY_ENVS"] = ",".join("|".join(g) for g in key_env_groups)

    def strategy(model, envs: tuple[str, ...]) -> str:
        if model.credential_strategy:
            return model.credential_strategy
        return "round_robin" if len(envs) > 1 else "first"

    if any(m.key_envs or m.credential_strategy for m in judge.models):
        env["JUDGE_MODEL_CREDENTIAL_STRATEGIES"] = ",".join(
            strategy(m, g) for m, g in zip(judge.models, key_env_groups)
        )
    return env


def judge_flags(judge: Judge) -> list[str]:
    """The same roster as command-line arguments.

    Flags rather than environment, because the launcher's child re-reads .env
    after it inherits anything the parent exported, and the benchmark layers the
    flags it was given over the environment it hands the evaluator. A flag is
    the only channel a stale .env cannot take back.
    """
    flag_for = {
        "JUDGE_MODEL_PROVIDER": "--judge-model-provider",
        "JUDGE_MODEL_PROVIDERS": "--judge-model-providers",
        "JUDGE_MODEL_NAMES": "--judge-model-names",
        "JUDGE_MODEL_BASE_URL": "--judge-model-base-url",
        "JUDGE_MODEL_BASE_URLS": "--judge-model-base-urls",
        "JUDGE_MODEL_API_KEY_ENV": "--judge-model-api-key-env",
        "JUDGE_MODEL_API_KEY_ENVS": "--judge-model-api-key-envs",
        "JUDGE_MODEL_CREDENTIAL_STRATEGIES": "--judge-model-credential-strategies",
    }
    env = judge_env(judge)
    return [part
            for name, flag in flag_for.items() if env.get(name)
            for part in (flag, env[name])]


def key_env_names(judge: Judge) -> tuple[str, ...]:
    """Every environment variable the roster reads a key from, in order."""
    seen: list[str] = []
    for model in judge.models:
        for name in (model.key_envs or ((judge.key_env,) if judge.key_env else ())):
            if name not in seen:
                seen.append(name)
    return tuple(seen)
