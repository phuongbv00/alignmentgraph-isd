"""Render figures/overview.svg: Hình 1, the general architecture.

The layout is the general-architecture sketch the supervisor suggested, kept as
it is: a title banner, an Input column of cards, three stacked layers of cards,
an Output column of cards, and a continuous-improvement bar under everything that
closes the loop from the output back to the input. Only the text that would be
untrue of this system is changed, and the colours are set for print (white or
near-white fills, dark strokes and text, no solid colour blocks):

* 1. Instructional design layer -- the six role agents, as in the sketch;
* 2. Small-language-model support layer -- what the harness keeps around the
     model: the alignment graph, validation, the repair loop, a schema per artifact
     and the audit trail;
* 3. Teaching & learning process layer -- the web app in which the teacher reviews the design
     exists; delivery, learners and learning outcomes are drawn dashed,
     as is the improvement loop: this study neither built nor measured them.

Build: python3 make_overview.py  (writes overview.svg, then overview.pdf through headless
Chrome, which embeds the fonts as TrueType; rsvg-convert leaves Type 3 fonts in the PDF)
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


def i_graph(cx, cy, c=BROWN):
    p = [(cx, cy - 13), (cx - 13, cy + 10), (cx + 13, cy + 10)]
    raw(f'<path d="M {p[0][0]} {p[0][1]} L {p[1][0]} {p[1][1]} L {p[2][0]} {p[2][1]} Z" '
        f'fill="none" stroke="{c}" stroke-width="2.2"/>')
    for x, y in p:
        raw(f'<circle cx="{x}" cy="{y}" r="5" fill="{c}"/>')


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


def card(x, y, w, h, icon, title, desc, *, color, n=None, dashed=False):
    """A layer card: icon on top, a bold title, a grey description."""
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=1.6, r=10, dash=dashed)
    icon(x + w / 2, y + 28)
    ty = y + 60
    for k, line in enumerate(title):
        text(x + w / 2, ty + 19 * k, line, fs=16, bold=True, fc=GREY if dashed else INK)
    dy = ty + 19 * len(title) + 5
    for k, line in enumerate(desc):
        text(x + w / 2, dy + 17 * k, line, fs=14, fc=GREY)
    if n is not None:
        badge(x + 4, y + 4, n, color)


def side_card(x, y, w, h, icon, title, bullets, color):
    """An input/output card: icon beside a bold title, bullets under it, the
    whole block centred vertically so every card carries the same margins."""
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=1.0, r=10)
    head, gap, step = 42, 10, 20
    top = y + (h - (head + gap + step * len(bullets))) / 2
    icon(x + 26, top + head / 2)
    t0 = top + head / 2 - 9.5 * (len(title) - 1)
    for k, line in enumerate(title):
        text(x + 52, t0 + 19 * k, line, fs=16, bold=True, anchor="start")
    for k, line in enumerate(bullets):
        text(x + 18, top + head + gap + step * k + step / 2, "• " + line, fs=15, fc=GREY,
             anchor="start")


def layer(x, y, w, h, title, color, bg):
    rect(x, y, w, h, fill=bg, stroke=color, sw=2.2, r=12)
    text(x + 16, y + 20, title, fs=19, bold=True, fc=color, anchor="start")


def chevrons(xs, y, color):
    for x in xs:
        path([(x - 6, y), (x + 5, y)], color=color, sw=2.4)


# ── grid ────────────────────────────────────────────────────────────────────
TOP, GAP, VGAP = 6, 26, 30
IN_X, SIDE_W = 6, 210
BAN_Y, BAN_H = TOP, 44
MID_X = IN_X + SIDE_W + GAP
MID_W = 880
OUT_X = MID_X + MID_W + GAP
W = OUT_X + SIDE_W + 6

L1_Y, L1_H = BAN_Y + BAN_H + 18, 236
L2_Y, L2_H = L1_Y + L1_H + VGAP, 196
L3_Y, L3_H = L2_Y + L2_H + VGAP, 196
SIDE_TOP, SIDE_BOTTOM = L1_Y - 18 + 0, L3_Y + L3_H
SIDE_TOP = L1_Y
BAR_Y, BAR_H = SIDE_BOTTOM + 30, 58
H = BAR_Y + BAR_H + 6
PAD, CGAP = 16, 18


def row(n):
    w = (MID_W - 2 * PAD - (n - 1) * CGAP) / n
    return [MID_X + PAD + k * (w + CGAP) for k in range(n)], w


# ── title banner ────────────────────────────────────────────────────────────
rect(MID_X, BAN_Y, MID_W, BAN_H, fill="#FFFFFF", stroke=NAVY, sw=2.4, r=12)
text(MID_X + MID_W / 2, BAN_Y + BAN_H / 2, "General Architecture of the Multi-Agent "
     "Instructional Design System", fs=21, bold=True, fc=NAVY)

# ── input ───────────────────────────────────────────────────────────────────
rect(IN_X, SIDE_TOP, SIDE_W, SIDE_BOTTOM - SIDE_TOP, fill=NAVY_BG, stroke=NAVY, sw=2.2, r=12)
text(IN_X + SIDE_W / 2, SIDE_TOP + 24, "Input", fs=22, bold=True, fc=NAVY)
INPUTS = [(i_doc, ["Course goals", "& objectives"],
           ["learning goals", "duration", "learning setting"]),
          (i_people, ["Learners' profile"], ["prior knowledge", "level, age", "class size"]),
          (i_book, ["Learning", "resources"], ["labs, LMS, tools", "technology",
                                                "language"]),
          (i_server, ["Small language", "model"], ["open-weight model", "self-hosted",
                                                    "no external API"])]
ch = (SIDE_BOTTOM - SIDE_TOP - 50 - 3 * 10) / 4
for k, (icon, title, bullets) in enumerate(INPUTS):
    side_card(IN_X + 9, SIDE_TOP + 44 + k * (ch + 10), SIDE_W - 18, ch, icon, title,
              bullets, NAVY)

# ── layer 1: the six stages ─────────────────────────────────────────────────
layer(MID_X, L1_Y, MID_W, L1_H, "1. Instructional Design & Planning Layer (multi-agent)",
      NAVY, NAVY_BG)
STAGES = [(i_search, ["Needs", "Analysis"], ["gaps, topics,", "constraints"]),
          (i_target, ["Outcome", "Designer"], ["objectives,", "modules"]),
          (i_clip, ["Assessment", "Designer"], ["blueprint, items,", "rubrics"]),
          (i_bulb, ["Activity", "Designer"], ["learning", "activities"]),
          (i_doc, ["Content", "Designer"], ["media,", "materials"]),
          (i_calendar, ["Implementation", "Planner"], ["sessions, guides,", "manuals"])]
xs, cw = row(6)
CY1, CH1 = L1_Y + 40, 150
for k, (icon, title, desc) in enumerate(STAGES):
    card(xs[k], CY1, cw, CH1, icon, title, desc, color=NAVY, n=k + 1)
chevrons([xs[k] + cw + CGAP / 2 for k in range(5)], CY1 + CH1 / 2, NAVY)
DY = CY1 + CH1 + 9
rect(xs[2], DY, xs[5] + cw - xs[2], 30, fill="#FFFFFF", stroke=NAVY, sw=1.3, r=8)
for k in range(3):
    i_robot(xs[2] + 22 + 24 * k, DY + 18, s=0.72)
text(xs[2] + 100, DY + 15, "Developer agents: items, activities, materials, sessions "
     "per module", fs=14, anchor="start")
text(xs[0], DY + 15, "Backward Design order", fs=14, fc=GREY, italic=True, anchor="start")

# ── layer 2: support around the small model ────────────────────────────────
layer(MID_X, L2_Y, MID_W, L2_H, "2. Small Language Model Support Layer (orchestration)",
      PURP, PURP_BG)
ORCH = [(i_graph, ["Alignment", "Graph"], ["links objectives,", "activities, assessments"]),
        (i_check, ["Validation"], ["checks each", "submitted artifact"]),
        (i_loop, ["Repair Loop"], ["errors back to", "the owner agent"]),
        (i_braces, ["Schema per", "Artifact"], ["constrained decoding", "(vLLM)"]),
        (i_ledger, ["Audit &", "Tracking"], ["graph and", "violation ledger"])]
xs, cw = row(5)
for k, (icon, title, desc) in enumerate(ORCH):
    card(xs[k], L2_Y + 38, cw, L2_H - 52, lambda x, y, f=icon: f(x, y, PURP) if f not in
         (i_graph,) else f(x, y), title, desc, color=PURP)

# ── layer 3: teaching and learning ──────────────────────────────────────────
layer(MID_X, L3_Y, MID_W, L3_H, "3. Teaching & Learning Process Layer", GREEN, GREEN_BG)
USE = [(i_screen, ["Web App"], ["teacher traces and", "reviews the design"], False),
       (i_teacher, ["Delivery"], ["teaches with", "session plans"], True),
       (i_people, ["Students"], ["study, practise,", "take assessments"], True),
       (i_chat, ["Interaction"], ["teacher and", "students"], True),
       (i_chart, ["Learning", "outcomes"], ["knowledge,", "skills"], True)]
xs, cw = row(5)
for k, (icon, title, desc, dashed) in enumerate(USE):
    card(xs[k], L3_Y + 38, cw, L3_H - 52, lambda x, y, f=icon: f(x, y, GREEN), title, desc,
         color=GREEN, dashed=dashed)
chevrons([xs[k] + cw + CGAP / 2 for k in range(4)], L3_Y + 38 + (L3_H - 52) / 2, GREEN)
text(MID_X + MID_W - 16, L3_Y + 20, "dashed: not built or measured in this study", fs=14,
     fc=GREY, italic=True, anchor="end")

# arrows down between the layers and into the bar
cx = MID_X + MID_W / 2
for y0, y1 in ((L1_Y + L1_H, L2_Y), (L2_Y + L2_H, L3_Y), (L3_Y + L3_H, BAR_Y)):
    path([(cx, y0 + 2), (cx, y1 - 3)], color=NAVY, sw=3, dash=y1 == BAR_Y)

# ── output ──────────────────────────────────────────────────────────────────
rect(OUT_X, SIDE_TOP, SIDE_W, SIDE_BOTTOM - SIDE_TOP, fill=GOLD_BG, stroke=GOLD, sw=2.2, r=12)
text(OUT_X + SIDE_W / 2, SIDE_TOP + 24, "Output", fs=22, bold=True, fc=GOLD)
OUTPUTS = [(i_doc, ["Course design"], ["objectives, modules", "assessment plan",
                                         "items, rubrics"]),
           (i_book, ["Teaching", "materials"], ["learning activities", "media selection",
                                                "materials per module"]),
           (i_calendar, ["Delivery plan"], ["session plans", "instructor guide",
                                            "operator manual"]),
           (None, ["Audit record"], ["alignment graph", "violation ledger",
                                     "traced in web app"])]
for k, (icon, title, bullets) in enumerate(OUTPUTS):
    draw = (lambda x, y: i_graph(x, y)) if icon is None else (lambda x, y, f=icon: f(x, y, GOLD))
    side_card(OUT_X + 9, SIDE_TOP + 44 + k * (ch + 10), SIDE_W - 18, ch, draw, title,
              bullets, GOLD)

# input -> layer 1, layer 1 -> output
path([(IN_X + SIDE_W + 2, CY1 + CH1 / 2), (MID_X - 3, CY1 + CH1 / 2)], color=NAVY, sw=3)
path([(MID_X + MID_W + 2, CY1 + CH1 / 2), (OUT_X - 3, CY1 + CH1 / 2)], color=GOLD, sw=3)

# ── continuous improvement: output -> bar -> input, all dashed ─────────────
rect(MID_X, BAR_Y, MID_W, BAR_H, fill="#FFFFFF", stroke=NAVY, sw=2.2, r=12, dash=True)
i_loop(MID_X + 40, BAR_Y + BAR_H / 2)
text(MID_X + 72, BAR_Y + 19, "Continuous Improvement (Feedback Loop) — future extension",
     fs=17, bold=True, fc=NAVY, anchor="start")
text(MID_X + 72, BAR_Y + 40, "Teacher edits  →  trace affected artifacts in the graph  →  "
     "owner agent revises  →  re-check", fs=15, fc=GREY, anchor="start")
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
