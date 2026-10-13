"""Render figures/architecture_hub2.svg: Hình 1, hub-and-spoke around the graph.

* The alignment graph is the hub, drawn as a graph (typed nodes, the triad in
  front); deterministic checks are a badge attached to it.
* Six near-square agent blocks (glyph on top, English agent name on two lines)
  sit on the spokes in clockwise turn order; the active one shows the tool call
  and its observation in two colours.
* A Designer delegates to its own Developer group (dashed arrow), and that group
  reaches the graph through a spoke of its own: Developers write the graph too.
* No harness ring: the harness is what the spoke labels name (tool calls), and
  the caption says the rest.

Build: python3 make_architecture_hub2.py && rsvg-convert -f pdf -o architecture_hub2.pdf architecture_hub2.svg
"""
import math
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"
TRIAD = "#8A6A3B"
BRICK, BRICK_FILL = "#8C4B47", "#F4ECEB"
GREY, GREY_FILL, MUTED = "#6B7480", "#F2F3F4", "#A5AEB8"
INK = "#1F2328"
FONT = "Arial,Helvetica,sans-serif"

out: list[str] = []


def text(x, y, s, *, fs=15, bold=False, fc=INK, anchor="middle"):
    w = "bold" if bold else "normal"
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="{w}" fill="{fc}" text-anchor="{anchor}" '
               f'dominant-baseline="central">{s}</text>')


def rect(x, y, w, h, *, fill, stroke, sw=1.6, r=10, dash=False):
    d = ' stroke-dasharray="5 3"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def line(p, q, *, color=MUTED, sw=1.6, head=False, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    out.append(f'<path d="M {p[0]:.1f} {p[1]:.1f} L {q[0]:.1f} {q[1]:.1f}" '
               f'stroke="{color}" stroke-width="{sw}" fill="none"{d}{m}/>')


def glyph(cx, cy, *, on=False, s=1.0):
    """A small flat agent glyph (robot head), the same for every agent."""
    edge = "#FFFFFF" if on else SLATE
    out.append(f'<rect x="{cx - 11 * s:.1f}" y="{cy - 8 * s:.1f}" width="{22 * s:.1f}" '
               f'height="{17 * s:.1f}" rx="{6 * s:.1f}" fill="#FFFFFF" stroke="{edge}" '
               f'stroke-width="1.4"/>')
    out.append(f'<rect x="{cx - 7.5 * s:.1f}" y="{cy - 4.5 * s:.1f}" width="{15 * s:.1f}" '
               f'height="{9.5 * s:.1f}" rx="{4 * s:.1f}" fill="#24323F"/>')
    for dx in (-3.2, 3.2):
        out.append(f'<circle cx="{cx + dx * s:.1f}" cy="{cy + 0.2 * s:.1f}" '
                   f'r="{1.8 * s:.1f}" fill="#8FDCF5"/>')
    out.append(f'<path d="M {cx:.1f} {cy - 8 * s:.1f} L {cx:.1f} {cy - 12 * s:.1f}" '
               f'stroke="{edge}" stroke-width="1.4"/>')
    out.append(f'<circle cx="{cx:.1f}" cy="{cy - 13.5 * s:.1f}" r="{2 * s:.1f}" '
               f'fill="#E07A5F"/>')


def box_edge(box, target):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = target[0] - cx, target[1] - cy
    t = min((w / 2) / abs(dx) if dx else math.inf, (h / 2) / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


# ── the hub: the alignment graph, drawn as a graph ──────────────────────────
GC, GRX, GRY = (440, 216), 150, 92


def ellipse_edge(target, pad=3):
    dx, dy = target[0] - GC[0], target[1] - GC[1]
    t = 1 / math.sqrt((dx / (GRX + pad)) ** 2 + (dy / (GRY + pad)) ** 2)
    return GC[0] + dx * t, GC[1] + dy * t


out.append(f'<ellipse cx="{GC[0]}" cy="{GC[1]}" rx="{GRX}" ry="{GRY}" fill="{BAND_FILL}" '
           f'stroke="{TRIAD}" stroke-width="2"/>')
text(GC[0], 146, "Đồ thị căn chỉnh", fs=16, bold=True, fc=TRIAD)
O, T, A = (440, 184), (392, 252), (488, 252)
FAINT = [(330, 206), (328, 252), (550, 206), (552, 252), (385, 172), (495, 172)]
for f, to in zip(FAINT, (T, T, A, A, O, O)):
    line(f, to, color=MUTED, sw=1.1)
line(FAINT[0], FAINT[1], color=MUTED, sw=1.1)
line(FAINT[2], FAINT[3], color=MUTED, sw=1.1)
for fx, fy in FAINT:
    out.append(f'<circle cx="{fx}" cy="{fy}" r="6" fill="#FFFFFF" stroke="{MUTED}" '
               f'stroke-width="1.3"/>')
line((O[0] - 6, O[1] + 10), (T[0] + 5, T[1] - 11), color=TRIAD, sw=2.6, head=True)
line((O[0] + 6, O[1] + 10), (A[0] - 5, A[1] - 11), color=TRIAD, sw=2.6, head=True)
line((T[0] + 12, T[1]), (A[0] - 13, A[1]), color=TRIAD, sw=2.6, head=True)
for nx, ny in (O, T, A):
    out.append(f'<circle cx="{nx}" cy="{ny}" r="9" fill="{TRIAD}" stroke="#FFFFFF" '
               f'stroke-width="2"/>')
text(470, 184, "Mục tiêu", fs=15, bold=True, anchor="start")
text(392, 276, "Hoạt động", fs=15, bold=True)
text(488, 276, "Đánh giá", fs=15, bold=True)
text(406, 214, "C3", fs=14, bold=True, fc=TRIAD, anchor="end")
text(474, 214, "C2", fs=14, bold=True, fc=TRIAD, anchor="start")
text(440, 240, "C4", fs=14, bold=True, fc=TRIAD)
# deterministic checks, attached to the state
rect(370, 296, 140, 26, fill=BRICK_FILL, stroke=BRICK, sw=1.3, r=13)
text(440, 309, "kiểm tra tất định", fs=14, fc=BRICK)

# ── six agents on the spokes, clockwise in turn order ───────────────────────
NAMES = [("Needs Analyst", "Agent"), ("Outcome Designer", "Agent"),
         ("Assessment", "Designer Agent"), ("Activity Designer", "Agent"),
         ("Content Designer", "Agent"), ("Implementation", "Planner Agent")]
CENTRES = [(150, 128), (360, 46), (520, 46), (730, 128), (730, 290), (150, 290)]
ACTIVE = 2
BW, BH = 146, 76
boxes = []
for k, ((cx, cy), (l1, l2)) in enumerate(zip(CENTRES, NAMES)):
    on = k == ACTIVE
    box = (cx - BW / 2, cy - BH / 2, BW, BH)
    boxes.append(box)
    if not on:
        line(box_edge(box, GC), ellipse_edge((cx, cy)), color=MUTED, sw=1.6)
    rect(*box, fill=SLATE if on else "#FFFFFF", stroke=SLATE if on else MUTED,
         sw=1.8 if on else 1.3, r=12)
    glyph(cx, cy - 18, on=on)
    fc = "#FFFFFF" if on else INK
    text(cx, cy + 8, f"{k + 1}. {l1}", fs=15, bold=on, fc=fc)
    text(cx, cy + 26, l2, fs=15, bold=on, fc=fc)

# the active agent: tool call and observation
ax = CENTRES[ACTIVE][0]
top = ellipse_edge((ax, 0))
line((ax - 10, 85), (ax - 10, top[1] - 2), color=SLATE, sw=2.4, head=True)
line((ax + 12, top[1] - 2), (ax + 12, 85), color=OCHRE, sw=2.4, head=True, dash=True)
text(ax - 20, 112, "gọi công cụ", fs=15, fc=SLATE, anchor="end")
text(ax + 22, 112, "quan sát", fs=15, fc=OCHRE, anchor="start")

# ── Developer groups: delegated by their Designer, writing the graph too ────
DW, DH = 104, 40
GROUPS = {2: (630, 26), 3: (678, 194), 4: (678, 356), 5: (98, 356)}  # top-left corners
for k, (gx, gy) in GROUPS.items():
    bx, by, bw, bh = boxes[k]
    g = (gx, gy, DW, DH)
    gc = (gx + DW / 2, gy + DH / 2)
    line(box_edge(boxes[k], gc), box_edge(g, (bx + bw / 2, by + bh / 2)),
         color=SLATE, sw=1.7, head=True, dash=True)            # delegate
    line(box_edge(g, GC), ellipse_edge(gc), color=MUTED, sw=1.6)  # its own spoke
    rect(gx, gy, DW, DH, fill="#FFFFFF", stroke=SLATE, sw=1.3, r=12, dash=True)
    for j in range(3):
        glyph(gx + 22 + j * 30, gy + DH / 2 + 3, s=0.9)
    text(gx + DW / 2, gy + DH + 12, "Developer", fs=14, fc=SLATE)

# ── input and outputs ───────────────────────────────────────────────────────
rect(8, 192, 96, 50, fill=GREY_FILL, stroke=GREY)
text(56, 208, "Bản mô tả", fs=15, bold=True)
text(56, 226, "thiết kế", fs=15, bold=True)
line((104, 217), ellipse_edge((0, 217)), color=GREY, sw=2.0, head=True)

line((400, 322), (366, 360), color=GREY, sw=2.0, head=True)
line((480, 322), (514, 360), color=GREY, sw=2.0, head=True)
rect(276, 362, 166, 40, fill=GREY_FILL, stroke=GREY)
text(359, 382, "Bản thiết kế ADDIE", fs=15, bold=True)
rect(452, 362, 166, 40, fill=GREY_FILL, stroke=GREY)
text(535, 382, "Đồ thị + sổ vi phạm", fs=15, bold=True)

W, H = 812, 422
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD, MUTED))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}px" '
       f'height="{H}px" viewBox="0 0 {W} {H}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
path = Path(__file__).with_name("architecture_hub2.svg")
path.write_text(svg)
print("wrote", path)
