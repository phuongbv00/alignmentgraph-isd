"""Which sensitivity arms to pool.

Replaces a loader that pulled the scoring script in through ``importlib``
purely because its filename began with a digit. The arm registry is
configuration now (``alignment.presets``), so this is an ordinary lookup.
"""

from __future__ import annotations

from pathlib import Path

from ..alignment.presets import Arms, current
from ..runs import iter_scenario_dirs


def resolve_sensitivity_arms(
    run_dirs_by_model: dict[str, list[Path]],
    *,
    explicit: str = "",
    auto_encoders: bool = False,
    auto_bloom: bool = False,
    arms: Arms | None = None,
) -> list[tuple[str, str]]:
    """[(arm key, artifact suffix)] for the sweep arms to pool.

    Covers every sensitivity axis: encoders and the baseline correction
    (family A) and Bloom classifiers (family B). Family B is not optional decoration -- half the panel signals
    are Bloom-derived, so leaving it out would mean those are checked by no
    axis at all.

    The primary configuration is never an arm: its unsuffixed artifact IS the
    pooled alignment layer, and comparing it with itself is not a sensitivity
    check. That falls out of keying on a non-empty suffix rather than being a
    special case.

    Auto-discovery is registry-first, disk-second. The sensitivity design is
    fixed, so every non-primary arm is reported whether or not it has been
    scored -- an arm nobody ran then shows up as `skipped` rather than being
    absent, and absence is the one failure mode that makes a partial sweep look
    complete. Suffixed artifacts found on disk are added on top, so a one-off
    arm outside the registry is still picked up.
    """
    reg = arms or current()
    suffix_to_key = {**reg.suffix_to_encoder, **reg.suffix_to_bloom,
                     **reg.suffix_to_baseline}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(key: str, suffix: str) -> None:
        if suffix and key not in seen:
            seen.add(key)
            out.append((key, suffix))

    for raw in (explicit or "").split(","):
        key = raw.strip()
        if not key:
            continue
        arm = reg.encoders.get(key) or reg.bloom.get(key) or reg.baseline.get(key)
        add(key, arm.suffix if arm else key)

    if auto_bloom:
        for key, arm in reg.bloom.items():
            add(key, arm.suffix)

    if auto_encoders:
        # The fixed design first: never-scored arms must still be reported.
        for key, arm in reg.encoders.items():
            add(key, arm.suffix)
        # The baseline correction is a family-A axis: an encoder sweep that
        # left it out would report family A checked by one axis fewer.
        for key, arm in reg.baseline.items():
            add(key, arm.suffix)
        found: set[str] = set()
        for dirs in run_dirs_by_model.values():
            for run_dir in dirs:
                for _sid, scen_dir in iter_scenario_dirs(run_dir):
                    for path in scen_dir.glob("alignment_scores.*.json"):
                        found.add(path.name[len("alignment_scores."):-len(".json")])
                    break   # one scenario dir per run is enough to see the roster
        for suffix in sorted(found):
            add(suffix_to_key.get(suffix, suffix), suffix)
    return out
