#!/usr/bin/env python3
"""Rewrite draw.io's HTML labels in an SVG export as native SVG <text>.

draw.io stores every label with ``html=1`` inside a ``<switch>``: an
``<foreignObject>`` holding XHTML (which no standalone SVG renderer draws) and a
plain ``<text>`` fallback that draw.io fills only for single-line labels --
multi-line ones get the first line plus an ellipsis, and some get the literal
"Text is not SVG - cannot display".

This reads the real label out of the foreignObject and emits a <text> with one
positioned <tspan> per line, keeping the fallback's x / fill / font-family /
text-anchor and honouring per-line font-size and font-weight overrides (the
``<font style="font-size:...">`` spans draw.io writes for a smaller subtitle).
The result renders identically in rsvg-convert, Inkscape, LaTeX and a browser.

Usage: drawio_labels.py IN.svg OUT.svg
"""
from __future__ import annotations

import html
import re
import sys

SWITCH = re.compile(r"<switch>(?P<body>.*?)</switch>", re.S)
FOREIGN = re.compile(r"<foreignObject\b.*?</foreignObject>", re.S)
TEXT_TAG = re.compile(r"<text\b(?P<attrs>[^>]*)>", re.S)
PAD_TOP = re.compile(r"padding-top:\s*([\d.]+)px")
INNER_DIV = re.compile(r'<div[^>]*display:\s*inline-block[^>]*>(?P<inner>.*)</div>\s*</div>\s*</div>', re.S)
BR = re.compile(r"<br\s*/?>", re.I)
TAG = re.compile(r"<[^>]+>")
FONT_SIZE = re.compile(r"font-size:\s*([\d.]+)px")
FONT_WEIGHT = re.compile(r"font-weight:\s*(bold|normal|\d+)")
FONT_STYLE = re.compile(r"font-style:\s*(italic|normal)")
WATERMARK = "svg-export-text-problems"

# Baseline model matching draw.io's own single-line output: a line box is
# 1.2 * font-size tall and its baseline sits 0.95 * font-size below the top.
LINE_HEIGHT = 1.2
BASELINE = 0.95


def attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse_lines(inner: str, base_size: float, base_weight: str, base_style: str):
    """Split the label HTML into (text, font-size, font-weight, font-style) lines."""
    out = []
    for raw in BR.split(inner):
        size = float(m.group(1)) if (m := FONT_SIZE.search(raw)) else base_size
        weight = m.group(1) if (m := FONT_WEIGHT.search(raw)) else base_weight
        style = m.group(1) if (m := FONT_STYLE.search(raw)) else base_style
        text = html.unescape(TAG.sub("", raw)).replace("\xa0", " ").strip()
        if text:
            out.append((text, size, weight, style))
    return out


def rewrite(block: str) -> str:
    body = block
    if WATERMARK in body:
        # draw.io appends this notice whenever an export contains foreignObject.
        # Every label is native text once this script has run, so it is a lie.
        return ""
    foreign = FOREIGN.search(body)
    if not foreign:
        return block
    fo = foreign.group(0)

    pad = PAD_TOP.search(fo)
    inner_div = INNER_DIV.search(fo)
    fallback = TEXT_TAG.search(FOREIGN.sub("", body))
    if not (pad and inner_div and fallback):
        return block

    attrs = fallback.group("attrs")
    base_size = float(attr(attrs, "font-size").rstrip("px")) if attr(attrs, "font-size") else 12.0
    div_open = fo[: inner_div.start("inner")]
    if m := FONT_SIZE.search(div_open.rsplit("<div", 1)[-1]):
        base_size = float(m.group(1))
    base_weight = attr(attrs, "font-weight") or "normal"
    base_style = attr(attrs, "font-style") or "normal"

    lines = parse_lines(inner_div.group("inner"), base_size, base_weight, base_style)
    if not lines:
        return block

    cy = float(pad.group(1))
    total = sum(LINE_HEIGHT * size for _, size, _, _ in lines)
    top = cy - total / 2

    keep = [f'{k}="{attr(attrs, k)}"' for k in ("x", "fill", "font-family", "text-anchor")
            if attr(attrs, k) is not None]
    x = attr(attrs, "x") or "0"
    spans, cursor = [], top
    for text, size, weight, style in lines:
        baseline = cursor + BASELINE * size
        cursor += LINE_HEIGHT * size
        extra = f' font-size="{size:g}px" font-weight="{weight}"'
        if style == "italic":
            extra += ' font-style="italic"'
        spans.append(f'<tspan x="{x}" y="{baseline:.2f}"{extra}>{xml_escape(text)}</tspan>')
    return "<text " + " ".join(keep) + ">" + "".join(spans) + "</text>"


def main() -> int:
    if len(sys.argv) != 3:
        return print(__doc__.strip().splitlines()[-1], file=sys.stderr) or 2
    svg = open(sys.argv[1], encoding="utf-8").read()
    count = 0

    def sub(m):
        nonlocal count
        new = rewrite(m.group(0))
        count += new != m.group(0)
        return new

    out = SWITCH.sub(sub, svg)
    left = out.count("<foreignObject")
    open(sys.argv[2], "w", encoding="utf-8").write(out)
    print(f"  rewrote {count} draw.io label(s) as SVG text"
          + (f"; {left} foreignObject(s) left untouched" if left else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
