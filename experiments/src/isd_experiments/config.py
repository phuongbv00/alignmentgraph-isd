"""The experiment, read from experiment.toml.

What used to be module constants spread across five generators -- the ladder
slots, the model names, the size-to-macro-word table, the agent rosters, the
ablation arms and their expected flags -- are derived here from one declaration.
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

#: The three LLM-judge signals, reported side by side with no composite as the
#: headline. ADDIE leads the narrative because it measures design quality --
#: the construct the question is about -- while trajectory_score measures
#: process conformance and total_score's weights come from the benchmark.
JUDGE_SIGNALS = ("addie_median", "total_score", "trajectory_score")
JUDGE_LEAD = "addie_median"

#: How each judge signal is named in a report, spelled out so a reader does not
#: have to know that `total_score` is the benchmark's own composite.
JUDGE_SIGNAL_LABEL = {
    "addie_median": "ADDIE rubric (/100)",
    "total_score": "total_score = 0.7*ADDIE + 0.3*Trajectory (benchmark composite)",
    "trajectory_score": "Trajectory (BFCL tool-use, /100)",
}

#: Each judge mean paired with its OWN spread. A single shared SD is a
#: total_score statistic and overstates spread next to an ADDIE mean.
JUDGE_SD_FIELD = {
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
    judge: bool = True
    scenario_limit: int | None = None

    @property
    def slots(self) -> tuple[str, ...]:
        return tuple(r.slot for r in self.rungs)

    @property
    def n_generations(self) -> int:
        """For the cost banner. Scenario count is filled in by the launcher."""
        return len(self.rungs) * len(self.tags) * len(self.agents)


@dataclass(frozen=True)
class Serving:
    provider: str
    api_spec: str
    key_env: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Experiment:
    """The whole declaration."""

    ladder: tuple[Rung, ...]
    serving: Serving
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
        judge=bool(raw.get("judge", True)),
        scenario_limit=raw.get("scenario_limit"),
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

    serving_raw = dict(raw.get("serving", {}))
    provider = serving_raw.pop("provider", "static")
    api_spec = serving_raw.pop("api_spec", "openai_compatible")
    key_env = serving_raw.pop("key_env", "LLM_API_KEY")
    serving = Serving(provider=provider, api_spec=api_spec, key_env=key_env,
                      options=serving_raw)

    profiles = {
        name: _profile(name, body, rungs)
        for name, body in raw.get("experiment", {}).items()
    }
    if not profiles:
        raise SystemExit(f"{src} declares no [experiment.*] profiles.")

    return Experiment(ladder=rungs, serving=serving, profiles=profiles, source=src,
                      family=str(raw.get("models", {}).get("family", "")),
                      alignment_raw=raw.get("alignment", {}))


@lru_cache(maxsize=None)
def current() -> Experiment:
    """The config for this process, read once."""
    return load()
