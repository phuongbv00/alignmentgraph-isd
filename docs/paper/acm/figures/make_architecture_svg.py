"""Render figures/architecture.svg from the same coordinates as architecture.drawio.

The .drawio stays the editable master; this script exists because the export
loop in figures/README.md needs the draw.io app, which is not installed here.
Both files carry the same geometry, so re-exporting from draw.io later is a
no-op rather than a conflict.
"""
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
OCHRE, BAND_FILL, SEC = "#8A6A3B", "#F6F2EA", "#B7A88C"
BRICK, BRICK_FILL = "#8C4B47", "#F4ECEB"
GREY, GREY2, GREY_FILL = "#6B7480", "#7C848E", "#F2F3F4"
INK = "#1F2328"
FONT = 'Helvetica,Arial,sans-serif'

out = []
B = {}   # id -> (x, y, w, h)

def box(bid, x, y, w, h, lines, *, fill, stroke, sw=1.4, fs=10.5, bold=True,
        r=8, dash=None, fc=INK):
    B[bid] = (x, y, w, h)
    d = f' stroke-dasharray="4 3"' if dash else ''
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
    text(x + w / 2, y + h / 2, lines, fs=fs, bold=bold, fc=fc)

def ellipse(bid, x, y, w, h, label, *, fill, stroke, fc="#FFFFFF", fs=9.5):
    B[bid] = (x, y, w, h)
    out.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
    if label:
        text(x + w / 2, y + h / 2, [label], fs=fs, bold=True, fc=fc)

def text(cx, cy, lines, *, fs=10.5, bold=True, fc=INK, anchor="middle"):
    weight = "bold" if bold else "normal"
    n = len(lines)
    top = cy - (n - 1) * fs * 0.6
    spans = "".join(
        f'<tspan x="{cx}" dy="{0 if i == 0 else fs * 1.2}">{t}</tspan>'
        for i, t in enumerate(lines))
    out.append(f'<text x="{cx}" y="{top + fs*0.35}" font-family="{FONT}" '
               f'font-size="{fs}" font-weight="{weight}" fill="{fc}" '
               f'text-anchor="{anchor}">{spans}</text>')

def pt(bid, ax, ay):
    x, y, w, h = B[bid]
    return (x + ax * w, y + ay * h)

def edge(p0, p1, *, color=SLATE, sw=1.3, dash=False, head=True, label=None,
         lfs=9.5, lcolor=None, ldx=0, ldy=-4, lanchor="middle", italic=True):
    d = ' stroke-dasharray="5 4"' if dash else ''
    m = f' marker-end="url(#a-{color[1:]})"' if head else ''
    out.append(f'<path d="M {p0[0]:.1f} {p0[1]:.1f} L {p1[0]:.1f} {p1[1]:.1f}" '
               f'fill="none" stroke="{color}" stroke-width="{sw}"{d}{m}/>')
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        st = ' font-style="italic"' if italic else ''
        out.append(f'<text x="{mx + ldx:.1f}" y="{my + ldy:.1f}" font-family="{FONT}" '
                   f'font-size="{lfs}" fill="{lcolor or color}"{st} '
                   f'text-anchor="{lanchor}">{label}</text>')

# ── the band comes first so every node draws on top of it ────────────────────
box("band", 220, 250, 700, 210, [], fill=BAND_FILL, stroke=OCHRE, sw=1.6, r=12)
text(240, 264, ["Alignment graph"], fs=12, bold=True, fc=OCHRE, anchor="start")

# ── graph artifacts ─────────────────────────────────────────────────────────
box("g_needs", 260, 336, 104, 30, ["Needs &amp; context"], fill=BAND_FILL,
    stroke=SEC, fs=10)
box("g_act", 365, 276, 95, 30, ["Activity"], fill="#FFFFFF", stroke=OCHRE)
# The assessment ELEMENT is the TASK — the thing a learner sits. Its
# questions are a field of it, not vertices of their own, so the triad
# runs to the task and the figure names it.
box("g_asm", 365, 400, 95, 30, ["Assessment task"], fill="#FFFFFF", stroke=OCHRE, fs=9.5)
box("g_obj", 535.5, 334, 84.5, 34, ["Objective"], fill="#FFFFFF", stroke=SLATE, fs=11)
box("g_con", 711, 336, 89, 30, ["Module"], fill=BAND_FILL, stroke=SEC)
box("g_mat", 619, 410, 80, 30, ["Material"], fill=BAND_FILL, stroke=SEC, fs=10)

# core relations: the triad
edge(pt("g_obj", 0.05, 0.15), pt("g_act", 0.9, 1.0), color=OCHRE, sw=1.7,
     label="C3 practiced_by", ldy=-5)
edge(pt("g_obj", 0.05, 0.85), pt("g_asm", 0.95, 0.0), color=OCHRE, sw=1.7,
     label="C2 assessed_by", ldy=12)
edge(pt("g_act", 0.5, 1.0), pt("g_asm", 0.5, 0.0), color=OCHRE, sw=1.7,
     label="C4 prepares_for", ldx=7, ldy=28, lanchor="start")
# secondary relations
edge(pt("g_con", 0.5, 0.0), pt("g_act", 1.0, 0.5), color=SEC, sw=1.2,
     label="P13 delivered_through", ldy=-5)
edge(pt("g_needs", 1.0, 0.5), pt("g_obj", 0.0, 0.5), color=SEC, sw=1.2,
     label="P1 informs", ldy=-5)
edge(pt("g_con", 0.1, 1.0), pt("g_mat", 0.9, 0.0), color=SEC, sw=1.2,
     label="P5 covers", ldy=-4)
text(900, 448, ["Twelve further secondary relations not shown"],
     fs=9, bold=False, fc=SEC, anchor="end")

# ── brief and the six stages ────────────────────────────────────────────────
box("brief", 40, 116, 140, 60, ["Design brief", "(ISD scenario)"],
    fill=GREY_FILL, stroke=GREY2, fs=11)
STAGES = [("s_ana", 220, 100, ["Needs", "Analysis"]),
          ("s_out", 340, 100, ["Outcome", "Design"]),
          ("s_asm", 460, 100, ["Assessment", "Design"]),
          ("s_act", 580, 100, ["Activity", "Design"]),
          ("s_con", 699, 101, ["Content", "Design"]),
          ("s_imp", 820, 100, ["Implementation", "Plan"])]
for i, (sid, x, w, lines) in enumerate(STAGES, start=1):
    box(sid, x, 118, w, 56, lines, fill=SLATE_FILL, stroke=SLATE)
    ellipse(f"n{i}", x - 11, 109, 20, 20, str(i), fill=SLATE, stroke=SLATE)

edge(pt("brief", 1.0, 0.5), pt("s_ana", 0.0, 0.5), color=GREY, sw=1.6)
for (a, *_), (b, *_) in zip(STAGES, STAGES[1:]):
    edge(pt(a, 1.0, 0.5), pt(b, 0.0, 0.5), color=GREY, sw=1.6)

# ── check and repair, on every stage that owns checks ───────────────────────
for sid, x, w, _ in STAGES[1:]:
    box("v_" + sid, x, 72, w, 22, ["check · repair"], fill=BRICK_FILL,
        stroke=BRICK, sw=1.4, fs=9.5, bold=False, r=11)
    edge(pt(sid, 0.28, 0.0), pt("v_" + sid, 0.28, 1.0), color=BRICK, sw=1.2, head=False)
    edge(pt("v_" + sid, 0.72, 1.0), pt(sid, 0.72, 0.0), color=BRICK, sw=1.2)

# ── developer tier on the four dispatch stages ─────────────────────────────
for sid, x, w, _ in STAGES[2:]:
    did = "d_" + sid
    box(did, x + 42, 192, 68, 22, ["developers"], fill=SLATE_FILL, stroke=SLATE,
        sw=1.2, fs=8.5, bold=False, r=11, dash=True)
    edge(pt(sid, 0.75, 1.0), pt(did, 0.5, 0.0), color=SLATE, sw=1.2)

# ── reads and commits between the stages and the graph ─────────────────────
bx, by, bw, bh = B["band"]
for sid, x, w, _ in STAGES:
    rx = pt(sid, 0.25, 1.0)[0]
    edge((rx, by), (rx, 174), color=SLATE, sw=1.3, dash=True)          # read
    src = "d_" + sid if sid in ("s_asm", "s_act", "s_con", "s_imp") else sid
    wx = pt(src, 0.5, 1.0)[0] if src.startswith("d_") else pt(sid, 0.75, 1.0)[0]
    wy = B[src][1] + B[src][3]
    edge((wx, wy), (wx, by), color=SLATE, sw=1.3)                       # commit
text(239, 202, ["read"], fs=9, bold=False, fc=SLATE, anchor="end")
text(301, 240, ["commit"], fs=9, bold=False, fc=SLATE, anchor="start")

# ── reconciliation, aggregation, outputs ───────────────────────────────────
box("auditor", 360, 492, 130, 56, ["Reconcile", "and audit"], fill=SLATE_FILL,
    stroke=SLATE, fs=11.5)
box("aggregator", 680, 492, 129, 56, ["Aggregator"], fill=SLATE_FILL,
    stroke=SLATE, fs=11.5)
box("out_dump", 960, 319, 120, 72, ["Graph dump", "(auditable)"],
    fill=GREY_FILL, stroke=GREY2, fs=11.5)
box("out_addie", 960, 492, 120, 56, ["ADDIE output"], fill=GREY_FILL,
    stroke=GREY2, fs=11.5)
edge((bx + 0.25 * bw, by + bh), pt("auditor", 0.25, 0.0), color=SLATE)
edge(pt("auditor", 0.75, 0.0), (bx + 0.34 * bw, by + bh), color=SLATE)
edge((bx + 0.75 * bw, by + bh), pt("aggregator", 0.5, 0.0), color=SLATE)
edge(pt("band", 1.0, 0.5), pt("out_dump", 0.0, 0.5), color=GREY, sw=1.6)
edge(pt("aggregator", 1.0, 0.5), pt("out_addie", 0.0, 0.5), color=GREY, sw=1.6)

X0, Y0, X1, Y1 = 26, 60, 1094, 562
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth">'
    f'<path d="M 0 0 L 7 3 L 0 6 z" fill="{c}"/></marker>'
    for c in (SLATE, OCHRE, SEC, BRICK, GREY))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
       f'width="{X1-X0}px" height="{Y1-Y0}px" viewBox="{X0} {Y0} {X1-X0} {Y1-Y0}">'
       f'<defs>{defs}</defs>' + "".join(out) + '</svg>')
# Beside this script, not beside the caller: run from the paper root, a bare
# relative path drops a stray copy there and `generate_figures.sh` converts the
# stale one in figures/ instead.
out_path = Path(__file__).with_name("architecture.svg")
out_path.write_text(svg)
print("wrote", out_path, len(svg), "bytes")
