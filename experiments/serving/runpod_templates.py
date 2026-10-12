#!/usr/bin/env python3
"""The ladder's private RunPod pod templates, built from ladder.py.

One template per rung (docs/guides/benchmark_guides.md §3.4): the image as
published, its ENTRYPOINT ``vllm serve`` left alone and the template's start
command passed as CMD, so the model is the first arg. RunPod hands that string
to Docker as-is (no shell, no ``$ENV`` expansion), which is why the model is
written into each template rather than read from a variable.

Secrets are never in this file. A template's env names them as RunPod resolves
them at pod start, ``{{ RUNPOD_SECRET_<NAME> }}``, so each one must exist before
a template naming it is written: ``--check`` and ``--apply`` look the account's
secrets up first, and ``--apply`` leaves alone any template that names a secret
the account does not have. Create one in the console (Secrets) with the value
experiments/.env carries.

Stdlib only; the key is read from RUNPOD_API_KEY, else from the config
``runpodctl doctor`` writes (``~/.runpod/config.toml``):

    python3 runpod_templates.py            # print what would be sent
    python3 runpod_templates.py --check    # compare with RunPod, write nothing
    python3 runpod_templates.py --apply    # create missing, patch what differs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from ladder import CUDA, HF_HOME, IMAGE, PORT, RUNGS, SECRETS, TAG, Rung

BASE = os.getenv("RUNPOD_API_URL", "https://api.runpod.io") + "/v2"
API = BASE + "/templates"
CONTAINER_DISK_GB = 5   # the image only; the weights go to the volume


def payload(rung: Rung) -> dict:
    return {
        "name": rung.name,
        "image": f"{IMAGE}:{TAG}",
        "args": rung.argv,
        "disk": CONTAINER_DISK_GB,
        "mounts": {"persistent": {"size": rung.volume_gb, "path": "/workspace"}},
        "ports": [f"{PORT}/http"],
        "env": {"HF_HOME": HF_HOME, **{s: f"{{{{ RUNPOD_SECRET_{s} }}}}" for s in rung.secrets}},
        "allowedCudaVersions": [CUDA],   # the image's CUDA; the host driver must run it
        "category": "NVIDIA",
        "serverless": False,
        "public": False,
        "startSsh": True,        # RunPod's default, as the live templates carry it;
        "startJupyter": True,    # the vLLM image runs neither, so both are inert
    }


def api_key() -> str:
    """RUNPOD_API_KEY, else the key ``runpodctl doctor`` saved."""
    key = os.getenv("RUNPOD_API_KEY", "").strip()
    if not key:
        path = Path.home() / ".runpod" / "config.toml"
        if path.exists():
            key = str(tomllib.loads(path.read_text()).get("apikey", "")).strip()
    if not key:
        sys.exit("No RunPod API key: run `runpodctl doctor` or set RUNPOD_API_KEY.")
    return key


def call(method: str, url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "isd-agent-bench-templates/1",  # Cloudflare refuses urllib's default (1010)
        },
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                sys.exit(f"{method} {url}: HTTP {e.code} {e.read().decode(errors='replace')}")
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def mine() -> dict[str, dict]:
    """The caller's templates by name; two with one name is an error, not a guess."""
    found, url = [], API
    while url:
        page = call("GET", url)
        found += page.get("templates", [])
        cursor = (page.get("pagination") or {}).get("nextCursor")
        url = f"{API}?cursor={cursor}" if cursor else None
    by_name: dict[str, dict] = {}
    for t in found:
        if t.get("name") in by_name:
            sys.exit(f"Two RunPod templates are named {t['name']!r}: {by_name[t['name']]['id']}, {t['id']}")
        by_name[t.get("name")] = t
    return by_name


def args_of(v) -> str:
    """``args`` may come back as the JSON form ``{"entrypoint": [...], "cmd": [...]}``."""
    if isinstance(v, str) and v.lstrip().startswith("{"):
        v = json.loads(v)
    if isinstance(v, dict):
        if v.get("entrypoint"):
            return "<entrypoint overridden: %s>" % " ".join(v["entrypoint"])
        return " ".join(v.get("cmd") or [])
    return v or ""


def drift(have: dict, want: dict) -> dict:
    """Each declared field whose live value differs, as (live, declared)."""
    out = {}
    for k, w in want.items():
        h = have.get(k)
        if k == "args":
            h = args_of(h)
        elif k in ("env", "mounts"):
            h = h or {}
        elif k in ("ports", "allowedCudaVersions"):
            h, w = sorted(h or []), sorted(w)
        if h != w:
            out[k] = (h, w)
    return out


def account_secrets() -> set[str]:
    """Names only: RunPod never returns a secret's value."""
    return {s.get("name") for s in call("GET", f"{BASE}/account/secrets").get("secrets", [])}


def secret_guide(have: set[str] | None) -> None:
    """The RunPod secrets the templates name, which the account has, how to add one.

    ``have`` is None when the account was not looked up (a dry run). A template
    naming a secret is only as good as the secret: RunPod resolves it at pod
    start, and a secret created or changed later reaches a running pod only
    through a restart. An optional secret still has to exist while a template
    names it; to go without, take it out of that rung's ``secrets`` in ladder.py.
    """
    sys.stdout.flush()  # after the template lines, not interleaved with them
    out = ["", "RunPod secrets the templates read (create BEFORE the template; values never shown):"]
    for name, (required, why) in SECRETS.items():
        rungs = [r.name for r in RUNGS if name in r.secrets]
        if not rungs:
            continue
        state = "?" if have is None else ("set" if name in have else "MISSING")
        out.append(f"  [{state:^7}] {name} ({'required' if required else 'optional'}) - {why}")
        out.append(f"            read by: {', '.join(rungs)}")
        if state != "set":
            out.append(f"            console -> Secrets -> Create Secret, name exactly {name};"
                       f" templates reference it as {{{{ RUNPOD_SECRET_{name} }}}}")
    out.append("  Created or changed after a pod started: restart the pod.")
    print("\n".join(out), file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report drift from RunPod, write nothing")
    mode.add_argument("--apply", action="store_true", help="create or patch the templates on RunPod")
    opts = ap.parse_args()

    if not (opts.check or opts.apply):
        for rung in RUNGS:
            print(json.dumps(payload(rung), indent=2))
        secret_guide(None)
        return

    secrets = account_secrets()
    secret_guide(secrets)   # before any write: a template is only written once its secrets exist
    live = mine()
    dirty = False
    for rung in RUNGS:
        want = payload(rung)
        have = live.get(rung.name)
        absent = [s for s in rung.secrets if s not in secrets]
        if absent and opts.apply:
            dirty = True
            print(f"{rung.name}: skipped, the account has no secret {', '.join(absent)}")
            continue
        if have is None:
            dirty = True
            if not opts.apply:
                print(f"{rung.name}: missing")
                continue
            t = call("POST", API, want)
            print(f"{rung.name}: created -> {t.get('id')}")
            continue
        diff = drift(have, want)
        if not diff:
            print(f"{rung.name}: unchanged ({have['id']})")
            continue
        dirty = True
        for k, (h, w) in diff.items():
            print(f"{rung.name} ({have['id']}): {k}: {json.dumps(h)} -> {json.dumps(w)}")
        if opts.apply:
            call("PATCH", f"{API}/{have['id']}", {k: want[k] for k in diff})
            print(f"{rung.name}: patched ({have['id']})")
    if opts.check and dirty:
        sys.exit(1)


if __name__ == "__main__":
    main()
