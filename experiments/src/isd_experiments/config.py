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

import re
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


def macro_word(slot: str) -> str:
    """Slot -> a LaTeX-safe \\newcommand word: 'small08b' -> 'SmallZeroEightB'.

    From the SLOT, which is the identity, and not from a parameter count. A
    count is not unique: two families at 9B produced one macro name, LaTeX kept
    whichever was defined last, and the manuscript quoted one family's number
    under both labels without a warning anywhere.

    LaTeX forbids digits in a command name, so each digit becomes its word.
    """
    out = []
    for run in re.findall(r"[A-Za-z]+|\d+", slot):
        if run.isdigit():
            out.append("".join(_DIGIT_WORDS[c] for c in run))
        else:
            out.append(run.capitalize())
    return "".join(out) or "Slot"


# ── the declaration ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Model:
    """One declared model, reachable at an endpoint. Not a step of anything.

    The declaration is a FLAT list: what makes a ladder is which slots an
    experiment picks and in what order, and that lives on the experiment
    (`[experiment.*].slots`). Nothing here is a position in a sequence, so a
    second family, a repeat of one size on another host, or a model that
    belongs to three experiments at once all declare the same way.
    """

    slot: str
    model: str
    #: Column header and axis tick for this model, e.g. "0.8B". Explicit:
    #: it used to be derived from a parameter count, and deriving a LABEL from
    #: a NUMBER is what made two families at one size indistinguishable.
    display: str
    #: Which model family this belongs to. Per model rather than global:
    #: a global prefix IS the one-family assumption, and it labelled every
    #: figure with whatever family happened to be declared last.
    family: str = ""
    #: Where this model is served. Several endpoints of the SAME model is a
    #: supported setup, not a mistake: the agents round-robin across them.
    base_urls: tuple[str, ...] = ()
    #: Name of the env var holding this model's bearer token. Empty = the
    #: `[serving].key_env` default. Per model because the declaration does not
    #: have to live on one host: a model on a hosted API authenticates with
    #: that provider's key while self-hosted ones share the serving key, and a
    #: single global key would make the mixed declaration undeclarable.
    key_env: str = ""
    #: The API contract this model's endpoint speaks. Empty = `[serving]`'s.
    #: Same reason: it is a property of the host, and the hosts may differ.
    api_spec: str = ""

    @property
    def env_prefix(self) -> str:
        """<SLOT>_AGENT_MODEL_* -- the provider-neutral contract shared/llm speaks."""
        return self.slot.upper().replace("-", "_")

    @property
    def macro(self) -> str:
        return macro_word(self.slot)

    def full_display(self) -> str:
        """Axis label / column header: '<family>-4B', or just '4B' without one."""
        return f"{self.family}-{self.display}" if self.family else self.display


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
    models: tuple[Model, ...]
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
        return tuple(m.slot for m in self.models)

    @property
    def n_generations(self) -> int:
        """For the cost banner. Scenario count is filled in by the launcher."""
        return len(self.models) * len(self.tags) * len(self.agents)


@dataclass(frozen=True)
class Serving:
    """What the endpoints are: the contract they speak, the key they take, and
    the window they were launched with. One declaration for every rung."""

    api_spec: str
    key_env: str
    #: The window the endpoints were launched with, in tokens.
    context_window: int | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Generation:
    """How every model call is made, identically for every agent and every rung.

    Declared once rather than per rung or per agent: applying them uniformly is
    the fairness argument the comparison rests on, and a per-rung budget would
    turn the ladder into a comparison of budgets instead of model scale.
    """

    #: Ceiling on every agent's per-call output budget, applied centrally by the
    #: model factory as min(the agent's own, this).
    max_output_tokens: int | None = None
    #: Client-side streaming with stream_usage, for a proxy that closes a long
    #: non-streaming read before the largest rung finishes a turn.
    streaming: bool | None = None
    #: How many tokens a reply may spend reasoning before it must answer.
    #: 0 turns thinking off, a positive number caps it. A cap and not an off
    #: switch because reasoning shares the completion budget with the answer:
    #: past `max_output_tokens` the reasoning block never closes and the reply
    #: comes back empty, charged in full.
    thinking_budget: int | None = None
    #: Sampling temperature of the run config every agent is handed. An agent
    #: that pins its own in its constructor keeps it: that choice is part of
    #: the agent as the benchmark ships it.
    temperature: float | None = None
    #: Whether a submit the proposed system's validator refuses is written
    #: again by the model under the artifact's per-run schema, decoded with
    #: the schema enforced by the endpoint (``response_format`` of kind
    #: ``json_schema``). A transport recovery, declared here because it is a
    #: property of how a call is made and must be one value for every arm
    #: and every rung; the baselines make no such call. Needs an endpoint
    #: whose structured-output backend compiles the schema (a self-hosted
    #: server does; a router may not), which is one more reason the ladder
    #: is self-hosted end to end.
    structured_outputs: bool | None = None


#: The two development modes the proposed system runs under; the adapter and
#: `alignmentgraph_isd.config.DevelopmentMode` accept exactly these.
DEVELOPMENT_MODES = ("light", "full")


@dataclass(frozen=True)
class Harness:
    """The proposed system's own run posture, uniform across every rung and arm.

    Not a serving limit: nothing here changes what an endpoint is asked to do
    per call. It changes how many calls are in flight at once, so it moves wall
    time and `execution_time_seconds`, never the design a run produces."""

    #: How many of one family's Developers run at once. 1 is sequential; the
    #: adapter's call gate (from the `-r` preset) caps it further.
    fanout_workers: int | None = None
    #: How much of the planned scale the Developers write out: "light" (a
    #: typical, reviewable slice) or "full" (everything the design plans). The
    #: table in experiment.toml [harness] states the difference.
    development_mode: str | None = None


@dataclass(frozen=True)
class JudgeModel:
    """One LLM judge. Empty fields fall back to the `[judge.llm]` defaults."""

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

    models: tuple[Model, ...]
    serving: Serving
    judge: Judge
    profiles: dict[str, Profile]
    source: Path
    #: The [judge.alignment] table, verbatim. Parsed by alignment.presets rather
    #: than here, so this module stays free of measurement concepts.
    alignment_raw: dict = field(default_factory=dict)
    harness: Harness = field(default_factory=Harness)
    generation: Generation = field(default_factory=Generation)

    def by_slot(self, slot: str) -> Model:
        for m in self.models:
            if m.slot == slot:
                return m
        known = ", ".join(m.slot for m in self.models)
        raise SystemExit(f"Unknown slot {slot!r} in {self.source}. Known: {known}")

    def profile(self, name: str) -> Profile:
        try:
            return self.profiles[name]
        except KeyError:
            known = ", ".join(sorted(self.profiles))
            raise SystemExit(
                f"Unknown experiment {name!r} in {self.source}. Known: {known}"
            ) from None

    @property
    def macro_words(self) -> dict[str, str]:
        """slot -> LaTeX macro word, for every declared model.

        Keyed by slot rather than by size: the key has to tell two models
        apart, and a parameter count cannot.
        """
        return {m.slot: m.macro for m in self.models}

    def slot_of_label(self, label: str) -> str | None:
        """Run-dir model label -> the slot that produced it, or None.

        A run directory is named after the model id with the org prefix
        dropped and ':' turned into '-' (runner/llm.py::model_dir_label). Matching has
        to reproduce that spelling exactly: comparing against the raw id is why
        every hosted model, whose id carries a ':', silently failed to resolve
        and fell back to printing its own directory name as a header.
        """
        low = label.lower()
        for m in self.models:
            base = m.model.split("/")[-1]
            if low in (m.slot.lower(), base.lower(), base.replace(":", "-").lower()):
                return m.slot
        return None

    def key_env_for(self, model: Model) -> str:
        """The model's own key variable, or the serving default.

        One place decides this. Two call sites spelling `model.key_env or
        cfg.serving.key_env` differently is how a mixed-host selection ends up
        authenticating one way in the launcher and another in the audit.
        """
        return model.key_env or self.serving.key_env

    def api_spec_for(self, model: Model) -> str:
        return model.api_spec or self.serving.api_spec

    def display_for(self, label: str) -> str:
        """Run-dir model label (lowercase, as the dir name spells it) -> header text.

        Falls back to the label itself: a run from a rung this config does not
        declare must still render, since the alternative is a generator that
        crashes on data it was handed.
        """
        slot = self.slot_of_label(label)
        return self.by_slot(slot).full_display() if slot else label


def urls(raw, where: str) -> tuple[str, ...]:
    """A `base_urls` declaration: one string, or a list of them.

    Accepting the bare string is not politeness -- the single-endpoint case is
    the common one, and a declaration that must be written `["..."]` to work
    invites the list-of-characters bug the other spelling cannot express.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(u, str) for u in raw):
        raise SystemExit(f"{where}: base_urls must be a URL or a list of URLs, "
                         f"got {raw!r}.")
    return tuple(u.strip() for u in raw if u.strip())


def _required_display(raw: dict) -> str:
    """Every model states its own header text.

    There is nothing left to derive it from, and that is the point: a label
    derived from a size collides the moment two models share one.
    """
    value = raw.get("display")
    if not value or not isinstance(value, str):
        raise SystemExit(
            f"[[serving.slots]] {raw.get('slot', '?')!r}: display is required -- the column "
            f"header and axis tick for this model, e.g. \"9B\"."
        )
    return value


def _model(raw: dict) -> Model:
    return Model(
        slot=raw["slot"],
        model=raw["model"],
        display=_required_display(raw),
        family=raw.get("family", ""),
        base_urls=urls(raw.get("base_urls"), f'[[serving.slots]] {raw["slot"]!r}'),
        key_env=raw.get("key_env", ""),
        api_spec=raw.get("api_spec", ""),
    )


#: [generation] keys, refused in [serving] with the move to make.
GENERATION_KEYS = ("max_output_tokens", "streaming", "thinking_budget", "temperature",
                   "structured_outputs")


def _positive_int(rest: dict, key: str, where: str, src: Path) -> int | None:
    value = rest.pop(key, None)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SystemExit(f"{src}: {where}.{key} must be a positive integer, got {value!r}.")
    return value


def _serving(raw: dict, src: Path) -> Serving:
    """Pop the declared keys; whatever is left is the host's own table.

    ``slots`` is the model list and is read by :func:`load`, never kept here.
    """
    rest = dict(raw)
    rest.pop("slots", None)
    misplaced = [k for k in GENERATION_KEYS if k in rest]
    if misplaced:
        raise SystemExit(
            f"{src}: {', '.join(misplaced)} belong(s) in [generation], not [serving]: "
            f"they govern every agent's calls, not the endpoints.")
    api_spec = rest.pop("api_spec", "openai_compatible")
    key_env = rest.pop("key_env", "LLM_API_KEY")
    context_window = _positive_int(rest, "context_window", "[serving]", src)
    return Serving(api_spec=api_spec, key_env=key_env,
                   context_window=context_window, options=rest)


def _generation(raw: dict, serving: Serving, src: Path) -> Generation:
    rest = dict(raw)
    max_output_tokens = _positive_int(rest, "max_output_tokens", "[generation]", src)
    # Not `_positive_int`: 0 is the posture "serve with thinking off", which is
    # a declaration like any other, not an omission.
    thinking_budget = rest.pop("thinking_budget", None)
    if thinking_budget is not None and (
            not isinstance(thinking_budget, int) or isinstance(thinking_budget, bool)
            or thinking_budget < 0):
        raise SystemExit(
            f"{src}: [generation].thinking_budget must be a non-negative integer, "
            f"got {thinking_budget!r}.")
    streaming = rest.pop("streaming", None)
    if streaming is not None and not isinstance(streaming, bool):
        raise SystemExit(f"{src}: [generation].streaming must be true or false, "
                         f"got {streaming!r}.")
    structured_outputs = rest.pop("structured_outputs", None)
    if structured_outputs is not None and not isinstance(structured_outputs, bool):
        raise SystemExit(f"{src}: [generation].structured_outputs must be true or false, "
                         f"got {structured_outputs!r}.")
    temperature = rest.pop("temperature", None)
    if temperature is not None and (
            not isinstance(temperature, (int, float)) or isinstance(temperature, bool)
            or not 0 <= temperature <= 2):
        raise SystemExit(f"{src}: [generation].temperature must be a number in [0, 2], "
                         f"got {temperature!r}.")
    # Strict: every key here reaches every agent's calls, so a misspelt one
    # would be a posture that is written down and never applied.
    if rest:
        raise SystemExit(f"{src}: unknown key(s) in [generation]: {', '.join(sorted(rest))}.")
    window = serving.context_window
    if window is not None and max_output_tokens is not None and max_output_tokens >= window:
        raise SystemExit(
            f"{src}: [generation].max_output_tokens ({max_output_tokens}) leaves no room "
            f"for a prompt inside [serving].context_window ({window})."
        )
    return Generation(max_output_tokens=max_output_tokens, streaming=streaming,
                      thinking_budget=thinking_budget,
                      temperature=float(temperature) if temperature is not None else None,
                      structured_outputs=structured_outputs)


def _harness(raw: dict, src: Path) -> Harness:
    rest = dict(raw)
    workers = rest.pop("fanout_workers", None)
    if workers is not None and (
            not isinstance(workers, int) or isinstance(workers, bool) or workers < 1):
        raise SystemExit(
            f"{src}: [harness].fanout_workers must be a positive integer, got {workers!r}.")
    mode = rest.pop("development_mode", None)
    if mode is not None and mode not in DEVELOPMENT_MODES:
        raise SystemExit(
            f"{src}: [harness].development_mode must be one of "
            f"{', '.join(repr(m) for m in DEVELOPMENT_MODES)}, got {mode!r}.")
    # Strict, unlike [serving]'s pass-through options: every key here is
    # published to the proposed system, so a misspelt one would silently be a
    # posture that is written down and never applied.
    if rest:
        raise SystemExit(f"{src}: unknown key(s) in [harness]: {', '.join(sorted(rest))}.")
    return Harness(fanout_workers=workers, development_mode=mode)


#: Key-shaped names refused in [judge.llm]. The declaration carries the NAME of an
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

    _refuse_secrets(raw, "[judge.llm]")
    models_raw = raw.get("models", [])
    if not models_raw:
        raise SystemExit(
            f"{src}: [judge.llm] declares no [[judge.llm.models]]. Name at least one judge, "
            f"or drop the section and let the environment answer for the roster."
        )

    models = []
    for idx, entry in enumerate(models_raw, 1):
        where = f"[[judge.llm.models]] #{idx}"
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
        provider=_judge_scalar(raw, "provider", "[judge.llm]", src),
        base_url=_judge_scalar(raw, "base_url", "[judge.llm]", src),
        key_env=_judge_scalar(raw, "key_env", "[judge.llm]", src),
        models=tuple(models),
    )


def _profile(name: str, raw: dict, declared: tuple[Model, ...]) -> Profile:
    # THIS is what makes a ladder: the slots an experiment picks, in the order
    # it picks them. The declaration above is a flat list with no sequence in
    # it, so two experiments can carve two different ladders -- or two
    # families, or one family twice -- out of the same models without the
    # declaration knowing anything about either.
    wanted = raw.get("slots", "all")
    if wanted == "all":
        chosen = declared
    else:
        by_slot = {m.slot: m for m in declared}
        missing = [s for s in wanted if s not in by_slot]
        if missing:
            raise SystemExit(
                f"experiment.{name}.slots names undeclared slot(s): {', '.join(missing)}"
            )
        chosen = tuple(by_slot[s] for s in wanted)

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
        models=chosen,
        tags=tuple(raw.get("tags", [])),
        rate_limit=raw.get("rate_limit", "moderate"),
        session_prefix=raw.get("session_prefix", name),
        agents=agents,
        arms=arms,
        proposed=raw.get("proposed"),
        reference=raw.get("reference"),
        confirm=bool(raw.get("confirm", True)),
    )


#: Top-level tables this file does not read, and where their contents belong.
#: One is refused with the move to make: read silently, `[alignment]` would be
#: no arms and `[[model]]` no ladder, and the error would surface far from here.
_RETIRED_TABLES = {
    "model": "[[model]] -> [[serving.slots]]",
    "alignment": "[alignment...] -> [judge.alignment...]",
}


def _refuse_retired_layout(raw: dict, src: Path) -> None:
    moved = [_RETIRED_TABLES[k] for k in _RETIRED_TABLES if k in raw]
    judges = raw.get("judge", {})
    stray = sorted(k for k in judges if k not in {"llm", "alignment"})
    if stray:
        moved.append(f"[judge] {', '.join(stray)} -> [judge.llm] (and [[judge.models]] "
                     f"-> [[judge.llm.models]])")
    if moved:
        raise SystemExit(f"{src}: tables in the wrong place; move:\n  " + "\n  ".join(moved))


def load(path: Path | None = None) -> Experiment:
    """Read and validate experiment.toml."""
    src = path or paths.config_file()
    if not src.exists():
        raise SystemExit(
            f"No experiment config at {src}.\n"
            f"  Copy experiments/experiment.toml, or set ISD_EXPERIMENT_CONFIG."
        )
    raw = tomllib.loads(src.read_text(encoding="utf-8"))

    _refuse_retired_layout(raw, src)
    serving_raw = raw.get("serving", {})
    declared = tuple(_model(m) for m in serving_raw.get("slots", []))
    if not declared:
        raise SystemExit(f"{src} declares no [[serving.slots]] tables.")
    slots = [m.slot for m in declared]
    if len(set(slots)) != len(slots):
        raise SystemExit(f"{src}: duplicate [[serving.slots]] slot(s) in {slots}.")

    serving = _serving(serving_raw, src)
    generation = _generation(raw.get("generation", {}), serving, src)
    harness = _harness(raw.get("harness", {}), src)
    judges = raw.get("judge", {})
    judge = _judge(judges.get("llm", {}), src)

    profiles = {
        name: _profile(name, body, declared)
        for name, body in raw.get("experiment", {}).items()
    }
    if not profiles:
        raise SystemExit(f"{src} declares no [experiment.*] profiles.")

    return Experiment(models=declared, serving=serving, judge=judge, profiles=profiles,
                      source=src, alignment_raw=judges.get("alignment", {}),
                      harness=harness, generation=generation)


@lru_cache(maxsize=None)
def current() -> Experiment:
    """The config for this process, read once."""
    return load()
