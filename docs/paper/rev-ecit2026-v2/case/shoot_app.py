"""Screenshot the demo web app at print resolution for Hình 2.

Drives a headless Chrome over the DevTools protocol (1600x1000 CSS px at a
device scale factor of 2) against the app served on localhost:8000, opens the
deployment-case program and saves three PNGs into ../figures/:

  case_brief.png      the Brief tab: the Vietnamese design brief
  case_graph.png      the Graph tab, Alignment layer, one objective selected
  case_inspector.png  the details panel of one assessment task, items expanded
  case_trajectory.png the Trajectory tab: the stages in order, with their agents
  case_violations.png the Violations tab: the ledger, open and repaired
  case_activity.png   the details panel of one learning activity
  case_material.png   the details panel of one learning material

Needs Chrome (macOS path below) and `websockets` (in experiments/.venv). Usage:
  experiments/.venv/bin/python docs/paper/rev-ecit2026-v2/case/shoot_app.py \
      --program "Nhập môn Học máy" --objective objective:ILO-02 --task assessment:AT-02
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
APP = "http://localhost:8000/"
PORT = 9333
W, H, SCALE = 1600, 1150, 2
OUT = Path(__file__).resolve().parents[1] / "figures"


class Page:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True,
                            returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r.get("result", {}).get("value")

    async def shot(self, name):
        data = (await self.send("Page.captureScreenshot", format="png"))["data"]
        path = OUT / name
        path.write_bytes(base64.b64decode(data))
        print("wrote", path)


CLICK_TEXT = """(async (sel, text) => {
  const el = [...document.querySelectorAll(sel)].find(e => e.textContent.trim().startsWith(text));
  if (!el) throw new Error('not found: ' + sel + ' ' + text);
  el.click(); await new Promise(r => setTimeout(r, 900)); return true;
})"""

EXPAND = """(async (path) => {
  let scope = document;
  for (const key of path) {
    const btn = [...scope.querySelectorAll('button.json-toggle')].find(
      b => (b.querySelector('.json-key') || {}).textContent?.trim() === key);
    if (!btn) throw new Error('no toggle for ' + key);
    if (!btn.closest('li').querySelector(':scope > ul')) btn.click();
    await new Promise(r => setTimeout(r, 400));
    scope = btn.closest('li');
  }
  return true;
})"""

COLLAPSE = """(async (keys) => {
  for (const key of keys) {
    const btn = [...document.querySelectorAll('button.json-toggle')].find(
      b => (b.querySelector('.json-key') || {}).textContent?.trim() === key);
    if (btn && btn.closest('li').querySelector(':scope > ul')) btn.click();
  }
  return true;
})"""

TAP = """(async (id) => {
  const cy = [...document.querySelectorAll('div')].find(d => d._cyreg)._cyreg.cy;
  cy.elements().unselect();
  const n = cy.$id(id);
  if (!n.length) throw new Error('no node ' + id);
  n.select(); n.emit('tap');
  await new Promise(r => setTimeout(r, 900));
  return true;
})"""

CY = "[...document.querySelectorAll('div')].find(d => d._cyreg)._cyreg.cy"


async def run(args):
    ws_url = None
    for _ in range(40):
        try:
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            ws_url = next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.25)
    async with websockets.connect(ws_url, max_size=2 ** 26) as ws:
        p = Page(ws)
        await p.send("Emulation.setDeviceMetricsOverride", width=W, height=H,
                     deviceScaleFactor=SCALE, mobile=False)
        await p.send("Page.navigate", url=APP)
        await asyncio.sleep(3)
        await p.js(f"{CLICK_TEXT}('div.program', {json.dumps(args.program)})")
        await asyncio.sleep(1.5)

        await p.js(f"{CLICK_TEXT}('button.tab', 'Brief')")
        await p.shot("case_brief.png")

        await p.js(f"{CLICK_TEXT}('button.tab', 'Trajectory')")
        await asyncio.sleep(1)
        await p.shot("case_trajectory.png")

        await p.js(f"{CLICK_TEXT}('button.tab', 'Graph')")
        await asyncio.sleep(1.5)
        await p.js(f"{CLICK_TEXT}('button', 'Hide legend')")
        await p.js(f"{CLICK_TEXT}('button', 'Fit')")
        await p.js(f"(async () => {{ const n = {CY}.$id({json.dumps(args.objective)}); "
                   "n.select(); n.emit('tap'); await new Promise(r => setTimeout(r, 900)); "
                   "return true; })()")
        await p.shot("case_graph.png")

        await p.js(f"(async () => {{ const cy = {CY}; cy.elements().unselect(); "
                   f"const n = cy.$id({json.dumps(args.task)}); n.select(); n.emit('tap'); "
                   "await new Promise(r => setTimeout(r, 900)); return true; })()")
        # open the JSON tree along the path asked for, one key at a time, each
        # inside the subtree of the one before (a key like "0" recurs at every level)
        await p.js(EXPAND + f"({json.dumps(args.expand)})")
        await p.js(COLLAPSE + f"({json.dumps(args.collapse)})")
        await asyncio.sleep(0.8)
        await p.shot("case_inspector.png")

        await p.js(f"{CLICK_TEXT}('button.tab', 'Violations')")
        await asyncio.sleep(1)
        await p.shot("case_violations.png")

        # the output artifacts: one activity, then one material (materials sit on
        # the provenance layer, so that layer is switched on first)
        await p.js(f"{CLICK_TEXT}('button.tab', 'Graph')")
        await asyncio.sleep(1.5)
        await p.js(TAP + f"({json.dumps(args.activity)})")
        await p.shot("case_activity.png")
        await p.js("(async () => { const box = [...document.querySelectorAll('label')].find("
                   "l => l.textContent.trim().startsWith('Provenance')).querySelector('input'); "
                   "if (!box.checked) box.click(); await new Promise(r => setTimeout(r, 1500)); "
                   "return true; })()")
        await p.js(TAP + f"({json.dumps(args.material)})")
        await p.shot("case_material.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--objective", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--expand", nargs="*", default=[],
                    help="JSON-tree labels to click open, in order")
    ap.add_argument("--activity", default="activity:TLA-0102")
    ap.add_argument("--material", default="material:MAT-0101")
    ap.add_argument("--collapse", nargs="*", default=[],
                    help="JSON-tree keys to close, to make room")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    profile = tempfile.mkdtemp(prefix="shoot-chrome-")
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
                               f"--user-data-dir={profile}", f"--window-size={W},{H}",
                               "--hide-scrollbars", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        asyncio.run(run(args))
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
