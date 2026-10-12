#!/usr/bin/env python3
"""The ladder's private Vast.ai templates, built from ladder.py.

Same image, same env, same argv as the RunPod templates (runpod_templates.py)
and run-docker.sh beside this file (docs/guides/benchmark_guides.md §3.4),
no image to build. The image's ENTRYPOINT is ``vllm serve`` and RunPod passes
the args as its CMD; Vast's ``args`` runtype would do the same but caps
``args_str`` at 256 characters, which the ladder's args exceed. So the template
runs ``ssh`` and its on-start script starts ``vllm serve <model> <args>`` — the
same process with the same argv — teeing its output to the instance log
(PID 1's stdout, what ``vastai logs`` and the console show) and to
``/var/log/vllm.log``.

The API key is NOT in any template: vLLM reads ``VLLM_API_KEY`` from the
environment, and a Vast account-level env var is injected into every instance
the account starts — the counterpart of RunPod's ``{{ RUNPOD_SECRET_... }}``:

    vastai create env-var VLLM_API_KEY <value>     # same value as experiments/.env

Run with any python3 (stdlib only); the Vast key is read from VAST_API_KEY or
the file the ``vastai`` CLI writes:

    python3 vastai_templates.py            # print what would be sent
    python3 vastai_templates.py --apply    # create missing, update changed
    python3 vastai_templates.py --endpoints  # base URL of each running instance
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ladder import CUDA, HF_HOME, IMAGE, PORT, RUNGS, SECRETS, TAG, Rung

BASE = os.getenv("VAST_URL", "https://console.vast.ai") + "/api/v0"
API = BASE + "/template/"
ENV = f"-p {PORT}:{PORT} -e HF_HOME={HF_HOME}"


def payload(rung: Rung) -> dict:
    """No volume as on RunPod: the one disk holds the image and the weights."""
    return {
        "name": rung.name,
        "image": IMAGE,
        "tag": TAG,
        "runtype": "ssh",
        "args_str": "",
        "env": ENV,
        # The instance log Vast shows is PID 1's stdout; tee puts vLLM there and
        # keeps /var/log/vllm.log for an SSH session.
        "onstart": f"nohup sh -c 'vllm serve {rung.argv} 2>&1 | tee /var/log/vllm.log"
                   f" > /proc/1/fd/1' > /dev/null 2>&1 &",
        "use_ssh": True,
        "jup_direct": False,
        "ssh_direct": True,
        "use_jupyter_lab": False,
        "recommended_disk_space": rung.disk_gb,
        "extra_filters": {
            "verified": {"eq": True},
            "external": {"eq": False},
            "rentable": {"eq": True},
            "gpu_name": {"eq": rung.gpu},
            "num_gpus": {"eq": 1},
            "cuda_max_good": {"gte": float(CUDA)},  # the driver must run the image's CUDA
        },
        "desc": f"vLLM {TAG} serving {rung.model} for isd-agent-bench (mirror of the RunPod template)",
        "readme": f"Set the account env var(s) {', '.join(rung.secrets)} first."
                  f" Endpoint: http://<public_ip>:<port mapped to {PORT}>/v1",
        "readme_visible": True,
        "private": True,
    }


# The fields a template is compared on; anything else the server adds is ignored.
COMPARED = ("image", "tag", "runtype", "onstart", "env", "recommended_disk_space", "extra_filters")


def api_key() -> str:
    key = os.getenv("VAST_API_KEY")
    if not key:
        path = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "vastai" / "vast_api_key"
        key = path.read_text().strip() if path.exists() else ""
    if not key:
        sys.exit("No Vast API key: set VAST_API_KEY or run `vastai set api-key`.")
    return key


def call(method: str, body: dict | None = None, query: dict | None = None, url: str = API) -> dict:
    if query:
        url += "?" + urllib.parse.urlencode({k: json.dumps(v) for k, v in query.items()})
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:  # Vast rate-limits a burst of lookups
                sys.exit(f"{method} {url}: HTTP {e.code} {e.read().decode(errors='replace')}")
            time.sleep(2 ** attempt)


def mine(name: str) -> list[dict]:
    found = call("GET", query={"select_cols": ["*"], "select_filters": {"name": {"eq": name}}})
    return [t for t in found.get("templates", []) if t.get("name") == name and t.get("private")]


def same(have: dict, want: dict) -> bool:
    def norm(k, v):
        if k == "recommended_disk_space" and v is not None:
            return float(v)
        if k == "extra_filters" and isinstance(v, str):  # the server returns it serialized
            return json.loads(v)
        return v
    return all(norm(k, have.get(k)) == norm(k, want[k]) for k in COMPARED)


def endpoints() -> None:
    """Each running instance's OpenAI base URL, for ``base_urls`` in experiment.toml.

    Vast maps a container port to a random port on the machine's shared public
    IP, so the URL is only known once the instance runs: it is the host port
    bound to container port ``PORT`` (inside the instance, $PUBLIC_IPADDR and
    $VAST_TCP_PORT_8000 say the same).
    """
    url = os.getenv("VAST_URL", "https://console.vast.ai") + "/api/v1/instances/"
    rows = call("GET", query={"select_filters": {}, "limit": 100}, url=url).get("instances", [])
    if not rows:
        print("No instances.")
    for i in rows:
        model = next((w for w in (i.get("onstart") or "").split() if "/" in w and not w.startswith(("/", "-"))), "?")
        bound = ((i.get("ports") or {}).get(f"{PORT}/tcp") or [{}])[0].get("HostPort")
        where = f"http://{i.get('public_ipaddr')}:{bound}/v1" if bound else f"(port {PORT} not bound yet)"
        print(f"{i['id']}  {i.get('actual_status')}  {i.get('gpu_name')}  {model}  {where}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="create or update the templates on Vast")
    ap.add_argument("--endpoints", action="store_true", help="print the base URL of each running instance")
    opts = ap.parse_args()
    if opts.endpoints:
        endpoints()
        return

    for rung in RUNGS:
        want = payload(rung)
        if not opts.apply:
            print(json.dumps(want, indent=2))
            continue
        existing = mine(want["name"])
        if existing and same(existing[0], want):
            print(f"{want['name']}: unchanged ({existing[0]['hash_id']})")
            continue
        if existing:
            rj = call("PUT", {**want, "hash_id": existing[0]["hash_id"]})
            verb = "updated"
        else:
            rj = call("POST", want)
            verb = "created"
        if not rj.get("success", True) or "template" not in rj:
            sys.exit(f"{want['name']}: {rj.get('msg', rj)}")
        t = rj["template"]
        print(f"{want['name']}: {verb} -> {t.get('hash_id')} (id {t.get('id')})")
    env_var_guide()


def env_var_guide() -> None:
    """What the account must carry for these templates, and which of it it does.

    Vast injects an account-level env var into every instance at container
    start, so a change reaches a running instance only through a reboot.
    """
    try:
        have = set(call("GET", url=BASE + "/secrets/").get("secrets", {}))
    except SystemExit as e:  # the guide is still worth printing without the lookup
        print(f"(could not read the account's env vars: {e})", file=sys.stderr)
        have = None
    sys.stdout.flush()  # after the template lines, not interleaved with them
    out = ["", "Account env vars the templates read (values never shown):"]
    for name, (required, why) in SECRETS.items():
        rungs = [r.name for r in RUNGS if name in r.secrets]
        state = "?" if have is None else ("set" if name in have else "MISSING")
        out.append(f"  [{state:^7}] {name} ({'required' if required else 'optional'}) - {why}")
        out.append(f"            read by: {', '.join(rungs)}")
        if state != "set":
            out.append(f"            vastai create env-var {name} <value>")
    out += [
        "  Every instance of the account gets every one of them, whichever rung it serves.",
        "  Set or changed after an instance started: vastai reboot instance <id>",
    ]
    print("\n".join(out), file=sys.stderr)


if __name__ == "__main__":
    main()
