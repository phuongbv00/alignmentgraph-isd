"""The experiment, read from experiment.toml.

The ladder slots, the model names, the size-to-macro-word table, the agent
rosters, the ablation arms and their expected flags are all derived here from
one declaration rather than restated as constants in each generator.
That is what makes a different ladder or a different serving host a config edit
rather than a patch: nothing below names a vendor or a model family.

The display tables that remain constants are the ones that are genuinely about
presentation of things the config already names (how to write an agent id in a
table column, how to write a panel signal on a figure axis).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import paths

# ── display, not configuration ───────────────────────────────────────────────

#: Agent id -> table column label. Ids come from the benchmark's registry.
AGENT_DISPLAY = {
    "alignmentgraph-isd": "AlignmentGraph-ISD",
    "alignmentgraph-isd-multi-prose": "multi+prose",
    "alignmentgraph-isd-single-graph": "single+graph",
    "alignmentgraph-isd-single-prose": "single+prose",
    "eduplanner": "EduPlanner",
    "baseline": "Baseline",
    "react-isd": "ReAct-ISD",
    "addie-agent": "ADDIE-Agent",
    "dick-carey-agent": "Dick\\&Carey",
    "rpisd-agent": "RPISD-Agent",
}

#: Row order in generated tables: baselines first, the proposed system last,
#: so a reader scanning down reaches the contribution after its comparators.
#: Display only -- which agents actually run comes from the experiment profile.
AGENT_ORDER = [
    "baseline", "eduplanner", "addie-agent", "rpisd-agent",
    "dick-carey-agent", "react-isd", "alignmentgraph-isd",
]

#: The three LLM judge scores, reported side by side with no composite as the
#: headline. ADDIE leads the narrative because it measures design quality --
#: the construct the question is about -- while trajectory_score measures
#: process conformance and total_score's weights come from the benchmark.
LLM_JUDGE_SCORES = ("addie_median", "total_score", "trajectory_score")
LLM_JUDGE_LEAD = "addie_median"

#: How each LLM judge score is named in a report, spelled out so a reader does not
#: have to know that `total_score` is the benchmark's own composite.
LLM_JUDGE_SCORE_LABEL = {
    "addie_median": "ADDIE rubric (/100)",
    "total_score": "total_score = 0.7*ADDIE + 0.3*Trajectory (benchmark composite)",
    "trajectory_score": "Trajectory (BFCL tool-use, /100)",
}

#: Each LLM judge mean paired with its OWN spread. A single shared SD is a
#: total_score statistic and overstates spread next to an ADDIE mean.
LLM_JUDGE_SD_FIELD = {
    "mean_addie": "sd_addie_across_scenarios",
    "mean_total": "sd_total_across_scenarios",
    "mean_traj": "sd_traj_across_scenarios",
}

#: Macro-name words for parameter counts. LaTeX forbids digits in a
#: \newcommand name, so 0.8 cannot be written as-is. Generated from the ladder
#: (see Ladder.macro_word); this table only spells the digits.
_DIGIT_WORDS = {
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
}


def macro_word(params_b: float) -> str:
    """0.8 -> 'ZeroEightB', 9.0 -> 'NineB'. Works for any rung, not a fixed set."""
    text = f"{params_b:g}".replace(".", "")
    return "".join(_DIGIT_WORDS[c] for c in text) + "B"


# ── the declaration ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rung:
    """One step of the model ladder."""

    slot: str
    model: str
    params_b: float
    display: str
    base_url: str | None = None
    #: Serving assumptions for the cost profile. A QUOTE, not a measurement:
    #: list prices recorded at deploy time, which move. Every number derived
    #: from them is labelled "Assumed" in its macro name and prose.
    gpu: str | None = None
    vram_gb: int | None = None
    usd_per_hour: float | None = None

    @property
    def env_prefix(self) -> str:
        """<SLOT>_AGENT_MODEL_* -- the provider-neutral contract shared/llm speaks."""
        return self.slot.upper().replace("-", "_")

    @property
    def macro(self) -> str:
        return macro_word(self.params_b)

    def full_display(self, family: str = "") -> str:
        """Axis label / column header: '<family>-4B', or just '4B' with no family."""
        return f"{family}-{self.display}" if family else self.display


@dataclass(frozen=True)
class Arm:
    """One cell of the ablation factorial."""

    id: str
    agent_mode: str
    context_mode: str

    @property
    def expected_flags(self) -> dict[str, str]:
        """What metadata.run_config must say for a run filed under this arm.

        Pooling hard-fails on a mismatch: a run filed under the wrong arm is a
        silently wrong factorial, which no amount of downstream care recovers.
        """
        return {"agent_mode": self.agent_mode, "context_mode": self.context_mode}


@dataclass(frozen=True)
class Profile:
    """One launchable experiment."""

    name: str
    title: str
    dataset: str
    rungs: tuple[Rung, ...]
    tags: tuple[str, ...]
    rate_limit: str
    session_prefix: str
    agents: tuple[str, ...]
    arms: tuple[Arm, ...] = ()
    proposed: str | None = None
    reference: str | None = None
    confirm: bool = True

    @property
    def slots(self) -> tuple[str, ...]:
        return tuple(r.slot for r in self.rungs)

    @property
    def n_generations(self) -> int:
        """For the cost banner. Scenario count is filled in by the launcher."""
        return len(self.rungs) * len(self.tags) * len(self.agents)


@dataclass(frozen=True)
class Serving:
    """How the ladder is served, and the limits every rung is served under.

    The three limits are declared once for the whole ladder rather than per
    rung: applying them uniformly to every agent and every size is the fairness
    argument the comparison rests on, and a per-rung window would turn the
    ladder into a comparison of budgets instead of a comparison of model scale.
    """

    provider: str
    api_spec: str
    key_env: str
    #: The window the endpoints were launched with, in tokens.
    context_window: int | None = None
    #: Ceiling on every agent's per-call output budget, applied centrally by the
    #: benchmark's model factory as min(the agent's own, this).
    max_output_tokens: int | None = None
    #: Client-side streaming with stream_usage, for a proxy that closes a long
    #: non-streaming read before the largest rung finishes a turn.
    streaming: bool | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JudgeModel:
    """One LLM judge. Empty fields fall back to the `[judge]` defaults."""

    name: str
    provider: str = ""
    base_url: str = ""
    key_envs: tuple[str, ...] = ()
    credential_strategy: str = ""


@dataclass(frozen=True)
class Judge:
    """The LLM judge roster.

    Declared here rather than left to the environment because the roster
    decides what every reported LLM judge score means, so it belongs in the file
    the freeze manifest fingerprints. Only the NAME of a key variable appears;
    a key value is not expressible in the declaration.
    """

    provider: str = ""
    base_url: str = ""
    key_env: str = ""
    models: tuple[JudgeModel, ...] = ()

    @property
    def declared(self) -> bool:
        return bool(self.models)


@dataclass(frozen=True)
class Experiment:
    """The whole declaration."""

    ladder: tuple[Rung, ...]
    serving: Serving
    judge: Judge
    profiles: dict[str, Profile]
    source: Path
    #: Display prefix for the ladder. Presentation only -- never used to look
    #: anything up, so an empty family is a perfectly good configuration.
    family: str = ""
    #: The [alignment] table, verbatim. Parsed by alignment.presets rather than
    #: here, so this module stays free of measurement concepts.
    alignment_raw: dict = field(default_factory=dict)

    def rung(self, slot: str) -> Rung:
        for r in self.ladder:
            if r.slot == slot:
                return r
        known = ", ".join(r.slot for r in self.ladder)
        raise SystemExit(f"Unknown ladder rung {slot!r} in {self.source}. Known: {known}")

    def profile(self, name: str) -> Profile:
        try:
            return self.profiles[name]
        except KeyError:
            known = ", ".join(sorted(self.profiles))
            raise SystemExit(
                f"Unknown experiment {name!r} in {self.source}. Known: {known}"
            ) from None

    @property
    def macro_words(self) -> dict[float, str]:
        """params_b -> LaTeX macro word, for every declared rung."""
        return {r.params_b: r.macro for r in self.ladder}

    @property
    def size_display(self) -> dict[float, str]:
        """params_b -> table column header, for every declared rung."""
        return {r.params_b: r.full_display(self.family) for r in self.ladder}

    @property
    def serving_profile(self) -> dict[float, dict]:
        """params_b -> {gpu, vram_gb, usd_per_hour}, for the cost profile."""
        return {r.params_b: {"gpu": r.gpu, "vram_gb": r.vram_gb,
                             "usd_per_hour": r.usd_per_hour}
                for r in self.ladder if r.usd_per_hour is not None}

    def display_for(self, label: str) -> str:
        """Run-dir model label (lowercase, as the dir name spells it) -> header text.

        Falls back to the label itself: a run from a rung this config does not
        declare must still render, since the alternative is a generator that
        crashes on data it was handed.
        """
        low = label.lower()
        for r in self.ladder:
            if r.slot.lower() == low or r.model.split("/")[-1].lower() == low:
                return r.full_display(self.family)
        return label


def _rung(raw: dict) -> Rung:
    return Rung(
        slot=raw["slot"],
        model=raw["model"],
        params_b=float(raw["params_b"]),
        display=raw.get("display") or f"{raw['params_b']:g}B",
        base_url=raw.get("base_url"),
        gpu=raw.get("gpu"),
        vram_gb=raw.get("vram_gb"),
        usd_per_hour=raw.get("usd_per_hour"),
    )


def _serving(raw: dict, src: Path) -> Serving:
    """Pop the declared keys; whatever is left is the provider's own table."""
    rest = dict(raw)
    provider = rest.pop("provider", "static")
    api_spec = rest.pop("api_spec", "openai_compatible")
    key_env = rest.pop("key_env", "LLM_API_KEY")

    def _positive_int(key: str) -> int | None:
        value = rest.pop(key, None)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise SystemExit(f"{src}: [serving].{key} must be a positive integer, got {value!r}.")
        return value

    context_window = _positive_int("context_window")
    max_output_tokens = _positive_int("max_output_tokens")
    streaming = rest.pop("streaming", None)
    if streaming is not None and not isinstance(streaming, bool):
        raise SystemExit(f"{src}: [serving].streaming must be true or false, got {streaming!r}.")
    if (context_window is not None and max_output_tokens is not None
            and max_output_tokens >= context_window):
        raise SystemExit(
            f"{src}: [serving].max_output_tokens ({max_output_tokens}) leaves no room for a "
            f"prompt inside context_window ({context_window})."
        )

    return Serving(provider=provider, api_spec=api_spec, key_env=key_env,
                   context_window=context_window, max_output_tokens=max_output_tokens,
                   streaming=streaming, options=rest)


#: Key-shaped names refused in [judge]. The declaration carries the NAME of an
#: environment variable; a value belongs in .env, which is not committed.
_JUDGE_SECRET_KEYS = ("api_key", "api_keys", "key", "keys")

#: A value that is joined on `,` or `|` and then quoted into the launcher's
#: command string. Rejecting the separators here means a malformed declaration
#: is named by its file rather than surfacing later as a misaligned roster.
_JUDGE_FORBIDDEN_CHARS = (",", "|", "'", '"', " ", "\t")


def _judge_scalar(raw: dict, key: str, where: str, src: Path) -> str:
    value = raw.get(key, "")
    if not value:
        return ""
    if not isinstance(value, str):
        raise SystemExit(f"{src}: {where}.{key} must be a string, got {value!r}.")
    bad = [c for c in _JUDGE_FORBIDDEN_CHARS if c in value]
    if bad:
        raise SystemExit(
            f"{src}: {where}.{key} may not contain {bad[0]!r} -- the launcher joins these "
            f"values on ',' and '|' and quotes them into one command."
        )
    return value


def _judge(raw: dict, src: Path) -> Judge:
    if not raw:
        return Judge()

    def _refuse_secrets(table: dict, where: str) -> None:
        present = [k for k in _JUDGE_SECRET_KEYS if k in table]
        if present:
            raise SystemExit(
                f"{src}: {where}.{present[0]} names a key VALUE. Declare the NAME of the "
                f"environment variable holding it (`key_env` / `key_envs`) and put the value "
                f"in .env."
            )

    _refuse_secrets(raw, "[judge]")
    models_raw = raw.get("models", [])
    if not models_raw:
        raise SystemExit(
            f"{src}: [judge] declares no [[judge.models]]. Name at least one judge, or drop "
            f"the section and let the environment answer for the roster."
        )

    models = []
    for idx, entry in enumerate(models_raw, 1):
        where = f"[[judge.models]] #{idx}"
        _refuse_secrets(entry, where)
        name = _judge_scalar(entry, "name", where, src)
        if not name:
            raise SystemExit(f"{src}: {where} has no `name`.")
        key_envs = tuple(entry.get("key_envs", ()))
        for env_name in key_envs:
            if not isinstance(env_name, str) or not env_name.replace("_", "a").isalnum() \
                    or env_name[0].isdigit():
                raise SystemExit(
                    f"{src}: {where}.key_envs entry {env_name!r} is not an environment "
                    f"variable name."
                )
        strategy = _judge_scalar(entry, "credential_strategy", where, src)
        if strategy and strategy not in {"first", "round_robin"}:
            raise SystemExit(
                f"{src}: {where}.credential_strategy must be 'first' or 'round_robin', "
                f"got {strategy!r}."
            )
        models.append(JudgeModel(
            name=name,
            provider=_judge_scalar(entry, "provider", where, src),
            base_url=_judge_scalar(entry, "base_url", where, src),
            key_envs=key_envs,
            credential_strategy=strategy,
        ))

    return Judge(
        provider=_judge_scalar(raw, "provider", "[judge]", src),
        base_url=_judge_scalar(raw, "base_url", "[judge]", src),
        key_env=_judge_scalar(raw, "key_env", "[judge]", src),
        models=tuple(models),
    )


def _profile(name: str, raw: dict, ladder: tuple[Rung, ...]) -> Profile:
    wanted = raw.get("rungs", "all")
    if wanted == "all":
        rungs = ladder
    else:
        by_slot = {r.slot: r for r in ladder}
        missing = [s for s in wanted if s not in by_slot]
        if missing:
            raise SystemExit(
                f"experiment.{name}.rungs names undeclared rung(s): {', '.join(missing)}"
            )
        rungs = tuple(by_slot[s] for s in wanted)

    arms = tuple(
        Arm(id=a["id"], agent_mode=a["agent_mode"], context_mode=a["context_mode"])
        for a in raw.get("arms", [])
    )
    # An ablation names its cells as arms; every other profile names agents
    # directly. Deriving the roster from the arms keeps the two from disagreeing.
    agents = tuple(raw["agents"]) if "agents" in raw else tuple(a.id for a in arms)
    if not agents:
        raise SystemExit(f"experiment.{name} declares neither `agents` nor `arms`.")

    return Profile(
        name=name,
        title=raw.get("title", name),
        dataset=raw["dataset"],
        rungs=rungs,
        tags=tuple(raw.get("tags", [])),
        rate_limit=raw.get("rate_limit", "moderate"),
        session_prefix=raw.get("session_prefix", name),
        agents=agents,
        arms=arms,
        proposed=raw.get("proposed"),
        reference=raw.get("reference"),
        confirm=bool(raw.get("confirm", True)),
    )


def load(path: Path | None = None) -> Experiment:
    """Read and validate experiment.toml."""
    src = path or paths.config_file()
    if not src.exists():
        raise SystemExit(
            f"No experiment config at {src}.\n"
            f"  Copy experiments/experiment.toml, or set ISD_EXPERIMENT_CONFIG."
        )
    raw = tomllib.loads(src.read_text(encoding="utf-8"))

    rungs = tuple(_rung(r) for r in raw.get("ladder", []))
    if not rungs:
        raise SystemExit(f"{src} declares no [[ladder]] rungs.")
    slots = [r.slot for r in rungs]
    if len(set(slots)) != len(slots):
        raise SystemExit(f"{src}: duplicate ladder slot(s) in {slots}.")

    serving = _serving(raw.get("serving", {}), src)
    judge = _judge(raw.get("judge", {}), src)

    profiles = {
        name: _profile(name, body, rungs)
        for name, body in raw.get("experiment", {}).items()
    }
    if not profiles:
        raise SystemExit(f"{src} declares no [experiment.*] profiles.")

    return Experiment(ladder=rungs, serving=serving, judge=judge, profiles=profiles, source=src,
                      family=str(raw.get("models", {}).get("family", "")),
                      alignment_raw=raw.get("alignment", {}))


@lru_cache(maxsize=None)
def current() -> Experiment:
    """The config for this process, read once."""
    return load()
