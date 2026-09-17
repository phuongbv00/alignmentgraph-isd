#!/usr/bin/env python3
"""Pre-flight audit before launching the ladder (guide section 7.1).

Checks, per ladder slot found in .env (managed block or manual quads):
  1. BASE_URL is set and every pod answers /v1/models: 401 without key,
     200 with VLLM_API_KEY, and the served model id matches *_AGENT_MODEL_NAME.
     A slot may be served by several pods: *_AGENT_MODEL_BASE_URLS (plural,
     comma-separated, what `isd-exp serve sync-agents` writes) is read first,
     falling back to the singular *_AGENT_MODEL_BASE_URL; every URL is checked.
  2. The two protective flags are set to the required values
     (AGENT_MODEL_MAX_OUTPUT_TOKENS=8192, AGENT_MODEL_STREAMING=1).
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

    The ladder is configuration, so pre-flight checks whatever rungs the
    experiment actually declares rather than a fixed set of slots naming one
    model family.
    """
    return [r.slot for r in current_config().ladder]

REQUIRED_FLAGS = {
    "AGENT_MODEL_MAX_OUTPUT_TOKENS": "8192",
    "AGENT_MODEL_STREAMING": "1",
}

_fail = 0


def report(ok: bool, label: str, detail: str = "") -> None:
    global _fail
    mark = "PASS" if ok else "FAIL"
    if not ok:
        _fail += 1
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))


def load_env_file(path: Path) -> None:
    """Best-effort .env loader: KEY=V / export KEY=V; os.environ wins."""
    if not path.exists():
        print(f"WARNING: {path} not found; relying on the current environment",
              file=sys.stderr)
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def slot_base_urls(upper: str) -> list[str]:
    """Base URLs for a slot, plural first (what the sync script writes).

    A slot may be served by several pods of the same model; the launchers fold
    <SLOT>_AGENT_MODEL_BASE_URLS into the singular and the agents round-robin
    across them (shared/llm/config.py::resolve_base_url). Accept both spellings
    here and audit every pod, not just the first.
    """
    raw = (os.environ.get(f"{upper}_AGENT_MODEL_BASE_URLS")
           or os.environ.get(f"{upper}_AGENT_MODEL_BASE_URL")
           or "")
    return [u.strip() for u in raw.split(",") if u.strip()]


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

    load_env_file(paths.env_file())
    vllm_key = os.environ.get("VLLM_API_KEY")

    print("== Pre-flight audit (guide 7.1) ==")

    # 1) pods alive + auth + model match
    any_slot = False
    for slot in slots():
        upper = slot.upper()
        base_urls = slot_base_urls(upper)
        name = os.environ.get(f"{upper}_AGENT_MODEL_NAME", "")
        print(f"\n-- {slot} ({name or 'no NAME'})")
        if not base_urls:
            report(False, "BASE_URL(S) set",
                   f"missing — run `{paths.cli()} serve sync-agents`")
            continue
        any_slot = True
        for idx, base_url in enumerate(base_urls, 1):
            # Only tag the pod index when a slot is served by several pods, so
            # the single-pod output stays exactly as it was.
            tag = f"pod {idx}/{len(base_urls)}: " if len(base_urls) > 1 else ""
            if tag:
                print(f"   {base_url}")
            status_nokey, _ = http_get(f"{base_url}/models", None)
            hint = " (404 = pod stopped/not running?)" if status_nokey == 404 else ""
            report(status_nokey == 401, f"{tag}auth required (401 without key)",
                   f"got {status_nokey}{hint}")
            if not vllm_key:
                report(False, "VLLM_API_KEY present", "not set in .env")
                break
            status, body = http_get(f"{base_url}/models", vllm_key)
            report(status == 200, f"{tag}reachable with key (200)", f"got {status}")
            if status == 200:
                try:
                    served = [m["id"] for m in json.loads(body).get("data", [])]
                except (json.JSONDecodeError, KeyError):
                    served = []
                report(name in served, f"{tag}served model matches NAME",
                       f"server: {served}")
                if not skip_smoke:
                    # Liveness only: the pod answers and generates something.
                    # Thinking is on, so the budget has to cover a <think> block
                    # AND the reply, and either channel counts as generating --
                    # asking for non-empty `content` under a tiny cap would fail
                    # a healthy pod that simply spent the cap reasoning.
                    st, doc = http_post_json(
                        f"{base_url}/chat/completions", vllm_key,
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

    # 2) protective flags
    print("\n-- protective flags")
    for key, want in REQUIRED_FLAGS.items():
        got = os.environ.get(key)
        report(got == want, f"{key}={want}", f"got {got!r}")

    # 3) disk
    print("\n-- disk")
    free_gb = shutil.disk_usage(paths.bench_root()).free / 1e9
    report(free_gb >= min_disk_gb,
           f"free disk >= {min_disk_gb:.0f}GB", f"{free_gb:.1f}GB free")

    print(f"\n== {'ALL PASS' if _fail == 0 else f'{_fail} FAIL(s)'} ==")
    return 0 if _fail == 0 else 1
