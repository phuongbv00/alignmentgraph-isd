"""Render figures/overview.svg and overview.pdf: Hình 1, the general architecture.

The layout is the general-architecture sketch the supervisor suggested: an Input column
of cards, three stacked layers of cards, an Output column of cards, and a dashed
local-editing bar under everything that closes the loop from the output back to the
input. Colours are set for print (white or near-white fills, dark strokes and text):

* 1. Course design & planning layer -- the six role agents and the Developer tier;
* 2. Small-language-model support layer -- what the orchestration layer keeps around
     the model: the alignment graph, validation, the repair loop, a schema per artifact
     and the audit trail;
* 3. Teaching & learning process layer -- the web app in which the teacher reviews the
     design exists; delivery, learners and outcomes are drawn dashed, as is the editing
     loop: this study neither built nor measured them.

Every card carries an icon and a title only; what each part does is in the text.

Build: python3 make_overview.py  (writes overview.svg, then overview.pdf through
headless Chrome, which embeds the fonts as TrueType; rsvg-convert leaves Type 3 fonts
in the PDF)
"""
import subprocess
import tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

INK, GREY, MUTED = "#1F2328", "#4F5864", "#9AA3AD"
NAVY, NAVY_BG = "#1F4E79", "#F4F8FC"
PURP, PURP_BG = "#4E3F8F", "#F7F5FC"
GREEN, GREEN_BG = "#2E6B45", "#F3F8F4"
GOLD, GOLD_BG = "#8F6110", "#FFFBF2"
BROWN, RED, OK = "#7A5A2E", "#9E3B34", "#2E7D4F"
FONT = "Arial,Helvetica,sans-serif"

out: list[str] = []


# ── primitives ──────────────────────────────────────────────────────────────
def text(x, y, s, *, fs=15, bold=False, fc=INK, anchor="middle", italic=False):
    s = s.replace("&", "&amp;")
    w = "bold" if bold else "normal"
    st = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="{w}" fill="{fc}" text-anchor="{anchor}"{st} '
               f'dominant-baseline="central">{s}</text>')


def rect(x, y, w, h, *, fill, stroke, sw=1.6, r=10, dash=False):
    d = ' stroke-dasharray="7 4"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def path(points, *, color=INK, sw=2.0, dash=False, head=True):
    d = ' stroke-dasharray="7 4"' if dash else ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    pts = " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    out.append(f'<path d="M {pts}" stroke="{color}" stroke-width="{sw}" fill="none" '
               f'stroke-linejoin="round"{d}{m}/>')


def raw(s):
    out.append(s)


# ── icons (centred on cx, cy; about 34 px across), line art for print ──────
def i_doc(cx, cy, c=NAVY):
    x, y = cx - 12, cy - 16
    raw(f'<path d="M {x} {y} h 17 l 7 7 v 25 h -24 z" fill="#FFFFFF" stroke="{c}" '
        f'stroke-width="2"/>')
    for k in range(4):
        raw(f'<path d="M {x + 5} {y + 11 + 5 * k} h 14" stroke="{c}" stroke-width="1.6"/>')


def i_people(cx, cy, c=NAVY):
    for dx, s in ((-11, 0.8), (11, 0.8), (0, 1.0)):
        raw(f'<circle cx="{cx + dx}" cy="{cy - 6 * s}" r="{5 * s}" fill="#FFFFFF" '
            f'stroke="{c}" stroke-width="2"/>')
        raw(f'<path d="M {cx + dx - 9 * s} {cy + 12} q {9 * s} {-17 * s} {18 * s} 0 z" '
            f'fill="#FFFFFF" stroke="{c}" stroke-width="2"/>')


def i_book(cx, cy, c=NAVY):
    raw(f'<path d="M {cx} {cy - 10} q -9 -5 -17 -2 v 22 q 8 -3 17 2 q 9 -5 17 -2 v -22 '
        f'q -8 -3 -17 2 z M {cx} {cy - 10} v 22" fill="#FFFFFF" stroke="{c}" '
        f'stroke-width="2" stroke-linejoin="round"/>')


def i_server(cx, cy, c=NAVY):
    for k in range(3):
        y = cy - 15 + 10.5 * k
        raw(f'<rect x="{cx - 15}" y="{y}" width="30" height="8.5" rx="2" fill="#FFFFFF" '
            f'stroke="{c}" stroke-width="1.8"/>')
        raw(f'<circle cx="{cx + 10}" cy="{y + 4.2}" r="1.7" fill="{c}"/>')


def i_search(cx, cy, c=NAVY):
    raw(f'<circle cx="{cx - 3}" cy="{cy - 3}" r="10" fill="none" stroke="{c}" '
        f'stroke-width="2.6"/>')
    raw(f'<path d="M {cx + 4} {cy + 4} l 9 9" stroke="{c}" stroke-width="3.4" '
        f'stroke-linecap="round"/>')


def i_target(cx, cy, c=NAVY):
    for r in (14, 9, 4):
        raw(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" '
            f'stroke-width="2.2"/>')
    raw(f'<path d="M {cx} {cy} l 13 -13" stroke="{c}" stroke-width="2.2"/>')


def i_clip(cx, cy, c=NAVY):
    raw(f'<rect x="{cx - 12}" y="{cy - 14}" width="24" height="30" rx="3" fill="#FFFFFF" '
        f'stroke="{c}" stroke-width="2"/>')
    raw(f'<rect x="{cx - 6}" y="{cy - 17}" width="12" height="6" rx="2" fill="{c}"/>')
    for k in range(3):
        y = cy - 5 + 8 * k
        raw(f'<path d="M {cx - 8} {y} l 2 2 l 3.5 -4" stroke="{c}" stroke-width="1.6" '
            f'fill="none"/>')
        raw(f'<path d="M {cx - 1} {y} h 9" stroke="{c}" stroke-width="1.6"/>')


def i_bulb(cx, cy, c=NAVY):
    raw(f'<path d="M {cx - 6} {cy + 6} q -9 -8 -6 -17 q 6 -11 18 0 q 3 9 -6 17 z" '
        f'fill="#FFFFFF" stroke="{c}" stroke-width="2"/>')
    raw(f'<path d="M {cx - 5} {cy + 10} h 10 M {cx - 4} {cy + 14} h 8" stroke="{c}" '
        f'stroke-width="2"/>')
    for a, b in ((-17, -8), (17, -8), (0, -21)):
        raw(f'<circle cx="{cx + a}" cy="{cy + b}" r="1.6" fill="{c}"/>')


def i_calendar(cx, cy, c=NAVY):
    raw(f'<rect x="{cx - 14}" y="{cy - 12}" width="28" height="26" rx="3" fill="#FFFFFF" '
        f'stroke="{c}" stroke-width="2"/>')
    raw(f'<path d="M {cx - 14} {cy - 5} h 28" stroke="{c}" stroke-width="2"/>')
    for i in range(3):
        for j in range(2):
            raw(f'<rect x="{cx - 9 + 7 * i}" y="{cy - 1 + 7 * j}" width="4" height="4" '
                f'fill="{c}"/>')


def i_graph(cx, cy, c=PURP):
    """A small network: a hub joined to four nodes, two of which are also linked."""
    hub = (cx, cy + 1)
    nodes = [(cx - 14, cy - 11), (cx + 14, cy - 11), (cx - 14, cy + 13), (cx + 14, cy + 13)]
    for x, y in nodes:
        raw(f'<path d="M {hub[0]} {hub[1]} L {x} {y}" stroke="{c}" stroke-width="2"/>')
    raw(f'<path d="M {nodes[0][0]} {nodes[0][1]} L {nodes[1][0]} {nodes[1][1]}" '
        f'stroke="{c}" stroke-width="2"/>')
    for (x, y), r in [(hub, 6)] + [(n, 4.5) for n in nodes]:
        raw(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FFFFFF" stroke="{c}" '
            f'stroke-width="2"/>')


def i_check(cx, cy, c=PURP):
    raw(f'<circle cx="{cx}" cy="{cy}" r="14" fill="#FFFFFF" stroke="{c}" stroke-width="2.2"/>')
    raw(f'<path d="M {cx - 7} {cy} l 5 5 l 9 -10" stroke="{c}" stroke-width="2.6" '
        f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')


def i_loop(cx, cy, c=NAVY):
    raw(f'<path d="M {cx + 12} {cy - 4} A 13 13 0 1 0 {cx + 9} {cy + 9}" fill="none" '
        f'stroke="{c}" stroke-width="2.4"/>')
    raw(f'<path d="M {cx + 6} {cy - 7} l 7 3 l 1 -8" fill="none" stroke="{c}" '
        f'stroke-width="2.4" stroke-linejoin="round"/>')


def i_braces(cx, cy, c=PURP):
    text(cx, cy + 1, "{ }", fs=24, bold=True, fc=c)


def i_ledger(cx, cy, c=PURP):
    x, y = cx - 12, cy - 15
    raw(f'<rect x="{x}" y="{y}" width="24" height="30" rx="3" fill="#FFFFFF" stroke="{c}" '
        f'stroke-width="2"/>')
    for k, good in enumerate((True, False, True)):
        yy = y + 8 + 7.5 * k
        mark = (f'M {x + 4} {yy} l 2 2.5 l 4 -5' if good else
                f'M {x + 4} {yy - 2.5} l 5 5 M {x + 9} {yy - 2.5} l -5 5')
        raw(f'<path d="{mark}" stroke="{OK if good else RED}" stroke-width="1.6" '
            f'fill="none"/>')
        raw(f'<path d="M {x + 13} {yy} h 7" stroke="{c}" stroke-width="1.4"/>')


def i_graph_ledger(cx, cy, c=GOLD):
    """The two audit outputs side by side: a small graph and a ledger page."""
    hub = (cx - 12, cy + 1)
    nodes = [(cx - 23, cy - 9), (cx - 1, cy - 9), (cx - 23, cy + 11), (cx - 1, cy + 11)]
    for x, y in nodes:
        raw(f'<path d="M {hub[0]} {hub[1]} L {x} {y}" stroke="{c}" stroke-width="1.8"/>')
    for (x, y), r in [(hub, 5)] + [(n, 3.6) for n in nodes]:
        raw(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#FFFFFF" stroke="{c}" '
            f'stroke-width="1.8"/>')
    x, y = cx + 6, cy - 14
    raw(f'<rect x="{x}" y="{y}" width="20" height="28" rx="3" fill="#FFFFFF" stroke="{c}" '
        f'stroke-width="2"/>')
    for k, good in enumerate((True, False, True)):
        yy = y + 7.5 + 7 * k
        mark = (f'M {x + 3.5} {yy} l 2 2.5 l 3.5 -4.5' if good else
                f'M {x + 3.5} {yy - 2.2} l 4.4 4.4 M {x + 7.9} {yy - 2.2} l -4.4 4.4')
        raw(f'<path d="{mark}" stroke="{OK if good else RED}" stroke-width="1.5" '
            f'fill="none"/>')
        raw(f'<path d="M {x + 11} {yy} h 6" stroke="{c}" stroke-width="1.3"/>')


def i_teacher(cx, cy, c=GREEN):
    raw(f'<rect x="{cx - 2}" y="{cy - 15}" width="20" height="14" fill="#FFFFFF" '
        f'stroke="{c}" stroke-width="2"/>')
    raw(f'<circle cx="{cx - 9}" cy="{cy - 8}" r="5" fill="#FFFFFF" stroke="{c}" '
        f'stroke-width="2"/>')
    raw(f'<path d="M {cx - 18} {cy + 14} v -10 q 9 -8 18 0 v 10 z" fill="#FFFFFF" '
        f'stroke="{c}" stroke-width="2"/>')


def i_screen(cx, cy, c=GREEN):
    raw(f'<rect x="{cx - 16}" y="{cy - 13}" width="32" height="21" rx="2" fill="#FFFFFF" '
        f'stroke="{c}" stroke-width="2"/>')
    raw(f'<path d="M {cx - 6} {cy + 14} h 12 M {cx} {cy + 8} v 6" stroke="{c}" '
        f'stroke-width="2"/>')
    for x, y in ((cx - 8, cy - 1), (cx, cy - 7), (cx + 8, cy - 1)):
        raw(f'<circle cx="{x}" cy="{y}" r="2.4" fill="{c}"/>')
    raw(f'<path d="M {cx - 8} {cy - 1} L {cx} {cy - 7} L {cx + 8} {cy - 1} Z" fill="none" '
        f'stroke="{c}" stroke-width="1.2"/>')


def i_chat(cx, cy, c=GREEN):
    raw(f'<path d="M {cx - 17} {cy - 13} h 22 v 14 h -14 l -5 5 v -5 h -3 z" '
        f'fill="#FFFFFF" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>')
    raw(f'<path d="M {cx - 1} {cy + 4} v 8 h 3 v 5 l 5 -5 h 10 v -14 h -9" fill="none" '
        f'stroke="{c}" stroke-width="2" stroke-linejoin="round"/>')


def i_chart(cx, cy, c=GREEN):
    for k, h in enumerate((10, 17, 24)):
        raw(f'<rect x="{cx - 13 + 9 * k}" y="{cy + 12 - h}" width="7" height="{h}" '
            f'fill="#FFFFFF" stroke="{c}" stroke-width="1.8"/>')
    raw(f'<path d="M {cx - 15} {cy + 13} h 30" stroke="{c}" stroke-width="2"/>')


def i_robot(cx, cy, s=1.0, c=NAVY):
    raw(f'<rect x="{cx - 11 * s}" y="{cy - 8 * s}" width="{22 * s}" height="{17 * s}" '
        f'rx="{6 * s}" fill="#FFFFFF" stroke="{c}" stroke-width="1.5"/>')
    for dx in (-4, 4):
        raw(f'<circle cx="{cx + dx * s}" cy="{cy + 0.2 * s}" r="{2.2 * s}" fill="{c}"/>')
    raw(f'<path d="M {cx} {cy - 8 * s} v {-4 * s}" stroke="{c}" stroke-width="1.5"/>')
    raw(f'<circle cx="{cx}" cy="{cy - 13.5 * s}" r="{2 * s}" fill="{c}"/>')


# ── composite pieces ────────────────────────────────────────────────────────
def badge(x, y, n, color):
    raw(f'<circle cx="{x}" cy="{y}" r="12" fill="#FFFFFF" stroke="{color}" '
        f'stroke-width="2.2"/>')
    text(x, y + 1, str(n), fs=14, bold=True, fc=color)


def card(x, y, w, h, icon, title, *, color, n=None, dashed=False):
    """A layer card: icon on top, a bold title under it."""
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=1.6, r=10, dash=dashed)
    icon(x + w / 2, y + 26)
    ty = y + 56
    for k, line in enumerate(title):
        text(x + w / 2, ty + 19 * k, line, fs=16, bold=True, fc=GREY if dashed else INK)
    if n is not None:
        badge(x + 4, y + 4, n, color)


def side_card(x, y, w, h, icon, title, color):
    """An input/output card: the icon on top and the bold title centred under it, the
    whole block centred vertically so every card carries the same margins."""
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=1.0, r=10)
    icon_h, gap, line = 34, 10, 19
    top = y + (h - (icon_h + gap + line * len(title))) / 2
    icon(x + w / 2, top + icon_h / 2)
    for k, t in enumerate(title):
        text(x + w / 2, top + icon_h + gap + line * k + line / 2, t, fs=16, bold=True)


def layer(x, y, w, h, title, color, bg):
    rect(x, y, w, h, fill=bg, stroke=color, sw=2.2, r=12)
    text(x + PAD, y + 20, title, fs=19, bold=True, fc=color, anchor="start")


def chevrons(xs, y, color):
    for x in xs:
        path([(x - 6, y), (x + 5, y)], color=color, sw=2.4)


# ── grid ────────────────────────────────────────────────────────────────────
# One set of spacings for every container: SP between containers (across and down),
# HEAD for a container's title band, PAD from a container's edge to its cards, CGAP
# between sibling cards. BADGE is the extra room the stage numbers need above layer 1.
TOP, SP, HEAD, PAD, CGAP, BADGE = 6, 22, 36, 12, 14, 8
IN_X, SIDE_W = 6, 170
MID_X = IN_X + SIDE_W + SP
MID_W = 880
OUT_X = MID_X + MID_W + SP
W = OUT_X + SIDE_W + 6

CH1, CH2, CH3, DEV_H = 96, 78, 78, 30
L1_Y, L1_H = TOP, HEAD + BADGE + CH1 + CGAP + DEV_H + PAD
L2_Y, L2_H = L1_Y + L1_H + SP, HEAD + CH2 + PAD
L3_Y, L3_H = L2_Y + L2_H + SP, HEAD + CH3 + PAD
SIDE_TOP, SIDE_BOTTOM = L1_Y, L3_Y + L3_H
BAR_Y, BAR_H = SIDE_BOTTOM + SP, 46
H = BAR_Y + BAR_H + 6


def row(n):
    w = (MID_W - 2 * PAD - (n - 1) * CGAP) / n
    return [MID_X + PAD + k * (w + CGAP) for k in range(n)], w


# ── title banner ────────────────────────────────────────────────────────────


# ── input ───────────────────────────────────────────────────────────────────
rect(IN_X, SIDE_TOP, SIDE_W, SIDE_BOTTOM - SIDE_TOP, fill=NAVY_BG, stroke=NAVY, sw=2.2, r=12)
text(IN_X + SIDE_W / 2, SIDE_TOP + 20, "Input", fs=22, bold=True, fc=NAVY)
INPUTS = [(i_doc, ["Course goals", "& objectives"]),
          (i_people, ["Learners' profile"]),
          (i_book, ["Learning", "resources"]),
          (i_server, ["Small language", "model"])]
ch = (SIDE_BOTTOM - SIDE_TOP - HEAD - PAD - 3 * CGAP) / 4
for k, (icon, title) in enumerate(INPUTS):
    side_card(IN_X + PAD, SIDE_TOP + HEAD + k * (ch + CGAP), SIDE_W - 2 * PAD, ch, icon,
              title, NAVY)

# ── layer 1: the six stages ─────────────────────────────────────────────────
layer(MID_X, L1_Y, MID_W, L1_H, "1. Course Design & Planning Layer (multi-agent)",
      NAVY, NAVY_BG)
STAGES = [(i_search, ["Needs", "Analysis"]),
          (i_target, ["Outcome", "Designer"]),
          (i_clip, ["Assessment", "Designer"]),
          (i_bulb, ["Activity", "Designer"]),
          (i_doc, ["Content", "Designer"]),
          (i_calendar, ["Implementation", "Planner"])]
xs, cw = row(6)
CY1 = L1_Y + HEAD + BADGE
for k, (icon, title) in enumerate(STAGES):
    card(xs[k], CY1, cw, CH1, icon, title, color=NAVY, n=k + 1)
chevrons([xs[k] + cw + CGAP / 2 for k in range(5)], CY1 + CH1 / 2, NAVY)
DY = CY1 + CH1 + CGAP
rect(xs[2], DY, xs[5] + cw - xs[2], DEV_H, fill="#FFFFFF", stroke=NAVY, sw=1.3, r=8)
for k in range(3):
    i_robot(xs[2] + 22 + 24 * k, DY + 18, s=0.72)
text(xs[2] + 100, DY + 15, "Developer agents: items, activities, materials, sessions "
     "per topic", fs=14, anchor="start")
text(xs[0], DY + 15, "Backward Design order", fs=14, fc=GREY, italic=True, anchor="start")

# ── layer 2: support around the small model ────────────────────────────────
layer(MID_X, L2_Y, MID_W, L2_H, "2. Small Language Model Support Layer (orchestration)",
      PURP, PURP_BG)
ORCH = [(i_graph, ["Alignment Graph"]),
        (i_check, ["Validation"]),
        (i_loop, ["Repair Loop"]),
        (i_braces, ["Artifact Schema"]),
        (i_ledger, ["Audit Trail"])]
xs, cw = row(5)
for k, (icon, title) in enumerate(ORCH):
    card(xs[k], L2_Y + HEAD, cw, CH2, lambda x, y, f=icon: f(x, y, PURP), title, color=PURP)

# ── layer 3: teaching and learning ──────────────────────────────────────────
layer(MID_X, L3_Y, MID_W, L3_H, "3. Teaching & Learning Process Layer", GREEN, GREEN_BG)
USE = [(i_screen, ["Web App"], False),
       (i_teacher, ["Delivery"], True),
       (i_people, ["Students"], True),
       (i_chat, ["Interaction"], True),
       (i_chart, ["Outcomes"], True)]
xs, cw = row(5)
for k, (icon, title, dashed) in enumerate(USE):
    card(xs[k], L3_Y + HEAD, cw, CH3, lambda x, y, f=icon: f(x, y, GREEN), title,
         color=GREEN, dashed=dashed)
chevrons([xs[k] + cw + CGAP / 2 for k in range(4)], L3_Y + HEAD + CH3 / 2, GREEN)
text(MID_X + MID_W - PAD, L3_Y + 20, "dashed: not built or measured in this study", fs=14,
     fc=GREY, italic=True, anchor="end")

# arrows down between the layers and into the bar
cx = MID_X + MID_W / 2
for y0, y1 in ((L1_Y + L1_H, L2_Y), (L2_Y + L2_H, L3_Y), (L3_Y + L3_H, BAR_Y)):
    path([(cx, y0 + 2), (cx, y1 - 3)], color=NAVY, sw=3, dash=y1 == BAR_Y)

# ── output ──────────────────────────────────────────────────────────────────
rect(OUT_X, SIDE_TOP, SIDE_W, SIDE_BOTTOM - SIDE_TOP, fill=GOLD_BG, stroke=GOLD, sw=2.2, r=12)
text(OUT_X + SIDE_W / 2, SIDE_TOP + 20, "Output", fs=22, bold=True, fc=GOLD)
OUTPUTS = [(i_doc, ["Course design"]),
           (i_book, ["Learning", "materials"]),
           (i_calendar, ["Delivery plan"]),
           (i_graph_ledger, ["Alignment graph", "& violation ledger"])]
for k, (icon, title) in enumerate(OUTPUTS):
    side_card(OUT_X + PAD, SIDE_TOP + HEAD + k * (ch + CGAP), SIDE_W - 2 * PAD, ch,
              lambda x, y, f=icon: f(x, y, GOLD), title, GOLD)

# input -> layer 1, layer 1 -> output
path([(IN_X + SIDE_W + 2, CY1 + CH1 / 2), (MID_X - 3, CY1 + CH1 / 2)], color=NAVY, sw=3)
path([(MID_X + MID_W + 2, CY1 + CH1 / 2), (OUT_X - 3, CY1 + CH1 / 2)], color=GOLD, sw=3)

# ── continuous improvement: output -> bar -> input, all dashed ─────────────
rect(MID_X, BAR_Y, MID_W, BAR_H, fill="#FFFFFF", stroke=NAVY, sw=2.2, r=12, dash=True)
i_loop(MID_X + 40, BAR_Y + BAR_H / 2)
text(MID_X + 72, BAR_Y + 15, "Local Editing Loop — future extension", fs=17, bold=True,
     fc=NAVY, anchor="start")
text(MID_X + 72, BAR_Y + 33, "Teacher edits  →  trace affected artifacts in the graph  →  "
     "owner agent revises  →  re-check", fs=14, fc=GREY, anchor="start")
oc, ic = OUT_X + SIDE_W / 2, IN_X + SIDE_W / 2
by = BAR_Y + BAR_H / 2
path([(oc, SIDE_BOTTOM + 2), (oc, by), (MID_X + MID_W + 3, by)], color=NAVY, sw=2.6,
     dash=True)
path([(MID_X - 2, by), (ic, by), (ic, SIDE_BOTTOM + 4)], color=NAVY, sw=2.6, dash=True)

defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="10" markerHeight="9" refX="9" refY="4.5" '
    f'orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 4.5 L 0 9 z" '
    f'fill="{c}"/></marker>' for c in (NAVY, PURP, GREEN, GOLD, GREY, MUTED, INK))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W:.0f}px" '
       f'height="{H:.0f}px" viewBox="0 0 {W:.0f} {H:.0f}"><defs>{defs}</defs>'
       f'<rect width="100%" height="100%" fill="#FFFFFF"/>' + "".join(out) + "</svg>")
out_path = Path(__file__).with_name("overview.svg")
out_path.write_text(svg)
print("wrote", out_path, f"{W:.0f}x{H:.0f}")

with tempfile.TemporaryDirectory() as tmp:
    page = Path(tmp) / "overview.html"
    page.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>'
                    f'@page{{size:{W:.0f}px {H:.0f}px;margin:0}}html,body{{margin:0;padding:0}}'
                    f'svg{{display:block}}</style></head><body>{svg}</body></html>',
                    encoding="utf-8")
    pdf = out_path.with_suffix(".pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", page.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("wrote", pdf)
