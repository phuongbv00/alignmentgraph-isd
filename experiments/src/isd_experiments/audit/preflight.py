#!/usr/bin/env python3
"""Pre-flight audit before launching the ladder (guide section 7.1).

Checks, per ladder rung declared in experiment.toml:
  1. base_urls is set and every endpoint answers /v1/models: 200 with the key
     that rung names (`key_env` on the rung, else [serving].key_env), the
     served model id matches the rung's `model`, and the served window matches
     [serving].context_window where the server reports one. Without a key, 401
     is the expected answer from an endpoint of your own; 200 is a WARN, since
     a hosted catalogue is public but a self-hosted endpoint should not be.
     A slot may be served by several endpoints: `base_urls` on the rung takes
     a list, and every one of them is checked.
  2. The serving limits are declared in experiment.toml, and .env does not also
     set them. Two sources for a limit that has to be uniform across every agent
     and every rung is how a comparison loses its fairness argument quietly, so
     a duplicate is a FAIL rather than a warning. The per-slot agent-model and
     embedding variables get the same treatment: .env carries keys, nothing
     else.
  3. Smoke completion: one tiny chat call per pod; PASS = 200 and a reply that
     carries something, in either channel. Thinking is on, so a model may
     answer entirely inside reasoning_content and leave content empty -- that
     is still the pod generating, which is all this check is for.
  4. Free disk space for results (warn below --min-disk-gb, default 10).

Reads .env itself (no `source` needed). Exit code 0 = all PASS, 1 = any FAIL.

Usage:
  ./isd-exp audit preflight
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .. import paths
from ..config import current as current_config


def slots() -> list[str]:
    """Env-quad prefixes for the declared ladder, lower-cased.

    The models are configuration, so pre-flight checks whatever slots the
    experiment actually declares rather than a fixed set of slots naming one
    model family.
    """
    return [m.slot for m in current_config().models]

#: Serving limit -> the variable the benchmark reads it under. The launcher
#: writes these onto the child command; .env must not carry them at all.
SERVING_LIMIT_ENV = {
    "context_window": "AGENT_MODEL_CONTEXT_WINDOW",
    "max_output_tokens": "AGENT_MODEL_MAX_OUTPUT_TOKENS",
    "streaming": "AGENT_MODEL_STREAMING",
    "thinking_budget": "AGENT_MODEL_THINKING_BUDGET",
}

#: The proposed system's run posture -> the variable its adapter reads. Not a
#: serving limit, but the same two questions apply: declared, and not also in
#: .env, where a stale line would be a posture nobody fingerprinted.
HARNESS_POSTURE_ENV = {
    "fanout_workers": "HARNESS_FANOUT_WORKERS",
}

_fail = 0


def report(ok: bool, label: str, detail: str = "") -> None:
    global _fail
    mark = "PASS" if ok else "FAIL"
    if not ok:
        _fail += 1
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))


def env_file_assignments(path: Path) -> dict[str, str]:
    """What the file assigns: KEY=V / export KEY=V, comments and blanks skipped.

    Kept separate from loading it, because one check asks what .env says on its
    own account rather than what the process ended up with.
    """
    found: dict[str, str] = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, val = line.partition("=")
        key = key.strip()
        if key:
            found[key] = val.strip().strip('"').strip("'")
    return found


def load_env_file(path: Path) -> None:
    """Best-effort .env loader; os.environ wins."""
    if not path.exists():
        print(f"WARNING: {path} not found; relying on the current environment",
              file=sys.stderr)
        return
    for key, val in env_file_assignments(path).items():
        if key not in os.environ:
            os.environ[key] = val


#: Per-slot variables .env must not carry. Every one of them is declared in
#: experiment.toml, and none of them is a secret, so a line here is always a
#: leftover. Two are actively dangerous. An EMPTY *_BASE_URLS reads as "this
#: rung has no endpoint" and sends the run nowhere. A stale *_NAME runs the
#: ladder under a model the declaration never named -- and `freeze write`
#: hashes the declaration, so the manifest would attest to a model that never
#: ran. Both are silent: the printed command looks entirely well-formed.
_STRAY_SUFFIXES = ("_AGENT_MODEL_BASE_URL", "_AGENT_MODEL_BASE_URLS",
                   "_AGENT_MODEL_NAME", "_AGENT_MODEL_API_KEY_ENVS",
                   "_AGENT_MODEL_API_SPEC",
                   "_EMBED_BASE_URLS", "_EMBED_MODEL", "_EMBED_REVISION")


def check_protection(cfg, env_path: Path) -> list[tuple[bool, str, str]]:
    """(ok, label, detail) per serving limit and harness posture. Pure: no network, no environment.

    Two findings per limit, and they are different questions. Declared? -- an
    undeclared limit means the launcher passes nothing and the benchmark falls
    back to its own default, which is not the run anyone wrote down. Also in
    .env? -- then the file and the declaration are two answers to one question,
    and only one of them is fingerprinted.

    The same question is then asked of the endpoints, which .env must not carry
    at all.
    """
    assigned = env_file_assignments(env_path)
    findings: list[tuple[bool, str, str]] = []
    declared = [("serving", cfg.serving, attr, env_name)
                for attr, env_name in SERVING_LIMIT_ENV.items()]
    declared += [("harness", cfg.harness, attr, env_name)
                 for attr, env_name in HARNESS_POSTURE_ENV.items()]
    for table, section, attr, env_name in declared:
        value = getattr(section, attr)
        findings.append((
            value is not None,
            f"[{table}].{attr} declared",
            f"{value}" if value is not None else f"absent from {cfg.source}",
        ))
        findings.append((
            env_name not in assigned,
            f"{env_name} absent from .env",
            f"{env_path} also sets it -- experiment.toml owns this setting"
            if env_name in assigned else "",
        ))

    stray = sorted(k for k in assigned
                   if any(k.endswith(s) for s in _STRAY_SUFFIXES))
    findings.append((
        not stray,
        "no per-slot override in .env",
        f"{env_path} sets {', '.join(stray)} -- every one of these is declared "
        f"in {cfg.source}; delete these lines. A stale value here wins "
        f"silently, and the freeze manifest hashes the declaration, not .env"
        if stray else "",
    ))
    return findings


def slot_base_urls(upper: str) -> list[str]:
    """Base URLs declared for a slot, in experiment.toml.

    A slot may be served by several endpoints of the same model; the agents
    round-robin across them (shared/llm/config.py::resolve_base_url), so audit
    every one of them rather than just the first. Read from the declaration and
    not from the environment on purpose: the audit has to check what the run
    will actually use, and what the run uses is what the launcher exports out
    of this same declaration.
    """
    for model in current_config().models:
        if model.env_prefix == upper:
            return list(model.base_urls)
    return []


# Some hosting proxies 403 the default Python-urllib User-Agent;
# any curl-like UA passes through to vLLM (which then answers 401/200).
UA = {"User-Agent": "curl/8.4.0 (isd-agent-benchmark audit)"}


def http_get(url: str, key: str | None, timeout: int = 15):
    headers = dict(UA)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)


def http_post_json(url: str, key: str, payload: dict, timeout: int = 120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={**UA, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return None, {"error": str(e)}


def run(*, skip_smoke: bool = False, min_disk_gb: int = 20) -> int:

    cfg = current_config()
    env_path = paths.env_file()
    load_env_file(env_path)
    print("== Pre-flight audit (guide 7.1) ==")

    # 1) pods alive + auth + model match
    any_slot = False
    for slot in slots():
        upper = slot.upper()
        base_urls = slot_base_urls(upper)
        model = next((m for m in cfg.models if m.env_prefix == upper), None)
        name = model.model if model else ""
        # Per rung: a hybrid ladder authenticates against each host with that
        # host's own key, so checking every rung against one global key would
        # audit a run that is not the one the launcher will start.
        key_env = cfg.key_env_for(model) if model else cfg.serving.key_env
        serving_key = os.environ.get(key_env)
        print(f"\n-- {slot} ({name or 'no model'}, key {key_env})")
        if not base_urls:
            report(False, "base_urls declared",
                   f"missing — declare base_urls on the {slot!r} rung in "
                   f"{cfg.source}")
            continue
        any_slot = True
        for idx, base_url in enumerate(base_urls, 1):
            # Only tag the pod index when a slot is served by several pods, so
            # the single-pod output stays exactly as it was.
            tag = f"pod {idx}/{len(base_urls)}: " if len(base_urls) > 1 else ""
            if tag:
                print(f"   {base_url}")
            status_nokey, _ = http_get(f"{base_url}/models", None)
            if status_nokey == 401:
                report(True, f"{tag}auth required (401 without key)", "")
            elif status_nokey == 200:
                # Not a failure and not a pass. A hosted provider's catalogue
                # is normally public, so 200 is expected there; a self-hosted
                # endpoint that answers 200 without a key is reachable by
                # anyone who guesses the URL, and is billed as such.
                print(f"  [WARN] {tag}{base_url}/models answers without a key "
                      f"— expected for a hosted catalogue, but it means an "
                      f"endpoint of your own is open")
            else:
                hint = " (404 = endpoint stopped/not running?)" if status_nokey == 404 else ""
                report(False, f"{tag}reachable", f"got {status_nokey}{hint}")
            if not serving_key:
                report(False, f"{key_env} present",
                       f"not set -- the {slot!r} rung authenticates with it")
                break
            status, body = http_get(f"{base_url}/models", serving_key)
            report(status == 200, f"{tag}reachable with key (200)", f"got {status}")
            if status == 200:
                try:
                    cards = json.loads(body).get("data", [])
                except (json.JSONDecodeError, KeyError):
                    cards = []
                served = [m["id"] for m in cards]
                report(name in served, f"{tag}served model matches NAME",
                       f"server: {served}")
                # The window is the one limit whose truth lives on the server.
                # Declared and served must agree or the transcript budget the
                # agents size themselves against is a number about another run.
                want_window = cfg.serving.context_window
                lengths = [m.get("max_model_len") for m in cards
                           if m.get("id") == name and m.get("max_model_len")]
                if want_window is not None and lengths:
                    report(lengths[0] == want_window,
                           f"{tag}served window matches [serving].context_window",
                           f"server: {lengths[0]}, declared: {want_window}")
                elif want_window is not None:
                    print(f"  [WARN] {tag}the server reports no max_model_len; "
                          f"cannot confirm context_window={want_window}")
                if not skip_smoke:
                    # Liveness only: the pod answers and generates something.
                    # Thinking is on, so the budget has to cover a <think> block
                    # AND the reply, and either channel counts as generating --
                    # asking for non-empty `content` under a tiny cap would fail
                    # a healthy pod that simply spent the cap reasoning.
                    st, doc = http_post_json(
                        f"{base_url}/chat/completions", serving_key,
                        {"model": name, "max_tokens": 256,
                         "messages": [{"role": "user", "content": "Say OK"}]},
                    )
                    msg = (doc.get("choices") or [{}])[0].get("message", {})
                    said = bool((msg.get("content") or "").strip()
                                or (msg.get("reasoning_content") or "").strip())
                    report(st == 200 and said, f"{tag}smoke: the pod generated a reply",
                           f"status={st}")

    if not any_slot:
        print("\nNo slot has a BASE_URL — nothing to check against.")

    # 2) the serving limits: declared once, and only once
    print("\n-- serving limits")
    for ok, label, detail in check_protection(cfg, env_path):
        report(ok, label, detail)

    # 3) disk
    print("\n-- disk")
    free_gb = shutil.disk_usage(paths.bench_root()).free / 1e9
    report(free_gb >= min_disk_gb,
           f"free disk >= {min_disk_gb:.0f}GB", f"{free_gb:.1f}GB free")

    print(f"\n== {'ALL PASS' if _fail == 0 else f'{_fail} FAIL(s)'} ==")
    return 0 if _fail == 0 else 1
