"""The instrument arms of the alignment measurement, read from config.

Two mechanically independent families, each with its own sensitivity axis:

* **correspondence** -- text encoders (``EncoderArm``)
* **cognitive demand** -- Bloom classifiers (``BloomArm``)

The sweep is a STAR, not a grid: every arm deviates from the primary
configuration on exactly one axis, so a difference it shows is attributable to
that axis.

They are configuration rather than code and live in ``experiment.toml``, so
swapping an encoder or adding a classifier is a declaration edit, and the model
names are reachable from anything that reads the experiment.

**The empty suffix is load-bearing.** Exactly one encoder and one classifier
own it, and their artifact is ``alignment_scores.json`` -- the only file
pooling reads into the alignment layer. Every other arm writes
``alignment_scores.<suffix>.json`` and is a sensitivity arm by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .. import config, paths

#: Artifact written by the arm that owns the empty suffix.
PRIMARY_ARTIFACT = "alignment_scores.json"


@dataclass(frozen=True)
class EncoderArm:
    key: str
    kind: str          # "api" | "local" | "tfidf"
    model: str
    suffix: str
    display: str = ""  # table row label
    short: str = ""    # figure axis / inline label
    macro: str = ""    # digit-free token for a LaTeX \newcommand name
    #: Where a served arm is reached. Several endpoints of the SAME model
    #: load-balance one embedding space; two different models are two arms.
    base_urls: tuple[str, ...] = ()
    #: Name of the env var holding this arm's bearer token. Empty = the
    #: `[serving].key_env` default. Per arm for the same reason a rung has
    #: one: the embedding endpoint need not live on the ladder's host.
    key_env: str = ""
    #: HF commit pinning the weights. Per arm, because one revision string
    #: cannot pin the weights of several different models -- and it enters the
    #: embedding-cache key, so a bump re-embeds rather than serving stale
    #: vectors under the new name.
    revision: str | None = None

    @property
    def is_primary(self) -> bool:
        return self.suffix == ""

    @property
    def artifact(self) -> str:
        return PRIMARY_ARTIFACT if self.is_primary else f"alignment_scores.{self.suffix}.json"

    @property
    def env_slot(self) -> str:
        """Preset key -> env-var slot prefix, e.g. 'bgem3' -> 'BGEM3'."""
        return self.key.upper().replace("-", "_")

    @property
    def needs_endpoint(self) -> bool:
        """Only a served arm needs a URL; the rest run on this machine."""
        return self.kind == "api"


@dataclass(frozen=True)
class BloomArm:
    key: str
    kind: str          # "transformer" | "lexicon"
    suffix: str
    checkpoint: str | None = None
    display: str = ""
    short: str = ""
    macro: str = ""

    @property
    def is_primary(self) -> bool:
        return self.suffix == ""

    @property
    def checkpoint_path(self):
        """Absolute path to the checkpoint, or None for a rule-based arm.

        Resolved against ``paths.models_dir()``. The old literal was the
        relative string ``models/bloom-bert-edm2022``, which only worked when
        the process happened to start in the benchmark root.
        """
        return paths.models_dir() / self.checkpoint if self.checkpoint else None

    @property
    def available(self) -> bool:
        p = self.checkpoint_path
        return True if p is None else p.exists()


@dataclass(frozen=True)
class Arms:
    encoders: dict[str, EncoderArm]
    bloom: dict[str, BloomArm]
    primary_encoder: str
    primary_bloom: str

    def encoder(self, key: str) -> EncoderArm:
        try:
            return self.encoders[key]
        except KeyError:
            raise SystemExit(
                f"Unknown encoder arm {key!r}. Known: {', '.join(sorted(self.encoders))}"
            ) from None

    def bloom_arm(self, key: str) -> BloomArm:
        try:
            return self.bloom[key]
        except KeyError:
            raise SystemExit(
                f"Unknown Bloom arm {key!r}. Known: {', '.join(sorted(self.bloom))}"
            ) from None

    @property
    def suffix_to_encoder(self) -> dict[str, str]:
        """For discovering which arms a results dir already holds on disk.

        The primary's empty suffix is excluded: an unsuffixed artifact is the
        primary by definition, not a sweep arm.
        """
        return {a.suffix: k for k, a in self.encoders.items() if a.suffix}

    @property
    def suffix_to_bloom(self) -> dict[str, str]:
        return {a.suffix: k for k, a in self.bloom.items() if a.suffix}

    def star(self) -> list[tuple[str, str]]:
        """The sensitivity star as (encoder key, bloom key) pairs.

        The primary configuration, then one arm per axis deviation. Not a grid:
        a full cross would multiply cost without isolating anything, because a
        cell differing on two axes cannot attribute a difference to either.
        """
        pe, pb = self.primary_encoder, self.primary_bloom
        arms = [(pe, pb)]
        arms += [(k, pb) for k in self.encoders if k != pe]
        arms += [(pe, k) for k in self.bloom if k != pb]
        return arms


def _load(exp_config) -> Arms:
    raw = getattr(exp_config, "alignment_raw", None) or {}
    encoders = {
        key: EncoderArm(key=key, kind=body["kind"], model=body["model"],
                        suffix=body.get("suffix", key),
                        display=body.get("display", key), short=body.get("short", key),
                        macro=body.get("macro", key.title()),
                        base_urls=config.urls(body.get("base_urls"),
                                              f"[judge.alignment.encoders.{key}]"),
                        key_env=body.get("key_env", ""),
                        revision=body.get("revision"))
        for key, body in raw.get("encoders", {}).items()
    }
    bloom = {
        key: BloomArm(key=key, kind=body["kind"], suffix=body.get("suffix", key),
                      checkpoint=body.get("checkpoint"),
                      display=body.get("display", key), short=body.get("short", key),
                        macro=body.get("macro", key.title()))
        for key, body in raw.get("bloom", {}).items()
    }
    if not encoders or not bloom:
        raise SystemExit(
            f"{exp_config.source}: [judge.alignment.encoders] and [judge.alignment.bloom] "
            f"must each declare at least one arm."
        )

    for name, table in (("encoder", encoders), ("Bloom", bloom)):
        owners = [k for k, a in table.items() if a.suffix == ""]
        if len(owners) != 1:
            raise SystemExit(
                f"{exp_config.source}: exactly one {name} arm must own the empty "
                f"suffix (it writes {PRIMARY_ARTIFACT}, the artifact pooling reads); "
                f"found {owners or 'none'}."
            )

    arms = Arms(encoders=encoders, bloom=bloom,
                primary_encoder=raw.get("primary_encoder", ""),
                primary_bloom=raw.get("primary_bloom", ""))
    # The declared primary must be the arm that owns the empty suffix, or the
    # artifact pooling reads would come from an arm nobody called primary.
    for name, key, table in (("encoder", arms.primary_encoder, encoders),
                             ("Bloom", arms.primary_bloom, bloom)):
        if key not in table:
            raise SystemExit(f"{exp_config.source}: primary {name} {key!r} is not declared.")
        if not table[key].is_primary:
            raise SystemExit(
                f"{exp_config.source}: primary {name} {key!r} does not own the "
                f"empty suffix; it would not write {PRIMARY_ARTIFACT}."
            )
    return arms


@lru_cache(maxsize=None)
def current() -> Arms:
    return _load(config.current())


def display_names() -> dict[str, str]:
    """Arm key -> table label, across both axes."""
    arms = current()
    return {**{k: a.display for k, a in arms.encoders.items()},
            **{k: a.display for k, a in arms.bloom.items()}}


def short_names() -> dict[str, str]:
    """Arm key -> figure/inline label, across both axes."""
    arms = current()
    return {**{k: a.short for k, a in arms.encoders.items()},
            **{k: a.short for k, a in arms.bloom.items()}}


def macro_words() -> dict[str, str]:
    """Arm key -> digit-free token for a LaTeX \\newcommand name.

    Declared per arm rather than derived, because a derived token would change
    if the derivation changed, and a macro name that moves breaks a manuscript
    that already cites it.
    """
    arms = current()
    return {**{k: a.macro for k, a in arms.encoders.items()},
            **{k: a.macro for k, a in arms.bloom.items()}}
