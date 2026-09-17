"""Small shared helpers: averaging, spread, and JSON that strict parsers accept."""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
from pathlib import Path
from typing import Optional


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")



def json_safe(value):
    """Replace every non-finite float with None, recursively.

    ``json.dumps`` writes bare ``NaN`` and ``Infinity`` tokens, which are not
    valid JSON: Python reads them back, but a strict parser — jq, most JS, most
    typed loaders — rejects the file outright. NaN reaches the pooled structure
    from ``_mean`` whenever a cell has nothing to average (an agent that
    produced no scorable output at a size), which is a real and expected state,
    so the fix is to emit ``null`` rather than to forbid it.

    Applied once at the dump, not at each producer: the alternative is every
    arithmetic helper guarding its own return, and one that forgets puts an
    unparseable token in the artifact the whole paper is generated from.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value



def sd(values: list[float]) -> Optional[float]:
    """Sample SD, or None when there are fewer than two values.

    None rather than nan (changed 2026-09-10, when the ladder went to one
    deterministic run per cell and every run-to-run SD lost its second value).
    Two reasons: `json.dump` writes a bare `NaN`, which is not valid JSON and
    which strict parsers reject outright — so the pooled file would have been
    unreadable to anything but Python; and a consumer needs to tell "no
    dispersion estimate exists" apart from "dispersion is zero", which `is
    None` says and a float cannot."""
    return statistics.stdev(values) if len(values) >= 2 else None




def write_json_atomic(path: Path, payload) -> None:
    """Write JSON via a temp file in the same directory, then rename.

    A pooled file or a scores file is read by the next stage of the pipeline,
    and a run interrupted mid-write otherwise leaves a truncated artifact that
    parses as a JSON error three commands later. Non-finite floats are replaced
    on the way out so the result is valid JSON, not Python-flavoured JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(json_safe(payload), fh, indent=2, ensure_ascii=False, allow_nan=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
