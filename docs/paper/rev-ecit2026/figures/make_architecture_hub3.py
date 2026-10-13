"""Render figures/architecture_hub3.svg: Hình 1, a radial hub-and-spoke.

Review of architecture_hub2 (2026-10-13) and what this version changes:

* Developer groups sat in three different places and two of their spokes ran
  long diagonals across the bottom row. Here every block -- six Designers and
  four Developer groups -- sits on ONE ellipse around the graph, each Developer
  group right after its Designer in clockwise order, so every spoke is radial,
  short and crosses nothing.
* Idle spokes were plain grey lines that said nothing. They are now two-headed
  (the agent reads and writes the graph through tools); only the agent holding
  the turn shows the tool call / observation pair in colour.
* Outputs shared the bottom row with Developer groups. They move to the right,
  out of the ring.

The layout is checked: no two blocks overlap, and the build fails if they do.

Build: python3 make_architecture_hub3.py && rsvg-convert -f pdf -o architecture_hub3.pdf architecture_hub3.svg
"""
import math
from pathlib import Path

SLATE = "#3E5F7E"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"
TRIAD = "#8A6A3B"
BRICK, BRICK_FILL = "#8C4B47", "#F4ECEB"
GREY, GREY_FILL, MUTED = "#6B7480", "#F2F3F4", "#A5AEB8"
INK = "#1F2328"
FONT = "Arial,Helvetica,sans-serif"

out: list[str] = []
BOXES: dict[str, tuple[float, float, float, float]] = {}


# ── primitives ──────────────────────────────────────────────────────────────
def text(x, y, s, *, fs=15, bold=False, fc=INK, anchor="middle"):
    w = "bold" if bold else "normal"
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="{w}" fill="{fc}" text-anchor="{anchor}" '
               f'dominant-baseline="central">{s}</text>')


def rect(x, y, w, h, *, fill, stroke, sw=1.6, r=10, dash=False):
    d = ' stroke-dasharray="5 3"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def line(p, q, *, color=MUTED, sw=1.6, head=False, tail=False, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    m += f' marker-start="url(#s-{color[1:]})"' if tail else ""
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


def box_edge(box, target, pad=2):
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = target[0] - cx, target[1] - cy
    t = min((w / 2 + pad) / abs(dx) if dx else math.inf,
            (h / 2 + pad) / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


# ── the hub: the alignment graph, drawn as a graph ──────────────────────────
GC, GRX, GRY = (470, 228), 154, 104


def ellipse_edge(target, pad=4):
    dx, dy = target[0] - GC[0], target[1] - GC[1]
    t = 1 / math.sqrt((dx / (GRX + pad)) ** 2 + (dy / (GRY + pad)) ** 2)
    return GC[0] + dx * t, GC[1] + dy * t


def hub():
    gx, gy = GC
    out.append(f'<ellipse cx="{gx}" cy="{gy}" rx="{GRX}" ry="{GRY}" fill="{BAND_FILL}" '
               f'stroke="{TRIAD}" stroke-width="2"/>')
    text(gx, gy - 80, "Đồ thị căn chỉnh", fs=16, bold=True, fc=TRIAD)
    O, T, A = (gx, gy - 44), (gx - 50, gy + 20), (gx + 50, gy + 20)
    faint = [(gx - 112, gy - 26), (gx - 118, gy + 22), (gx + 112, gy - 26),
             (gx + 118, gy + 22), (gx - 84, gy - 64), (gx + 84, gy - 64)]
    for f, to in zip(faint, (T, T, A, A, O, O)):
        line(f, to, color=MUTED, sw=1.1)
    line(faint[0], faint[1], color=MUTED, sw=1.1)
    line(faint[2], faint[3], color=MUTED, sw=1.1)
    for fx, fy in faint:
        out.append(f'<circle cx="{fx}" cy="{fy}" r="6" fill="#FFFFFF" stroke="{MUTED}" '
                   f'stroke-width="1.3"/>')
    line((O[0] - 6, O[1] + 10), (T[0] + 5, T[1] - 11), color=TRIAD, sw=2.6, head=True)
    line((O[0] + 6, O[1] + 10), (A[0] - 5, A[1] - 11), color=TRIAD, sw=2.6, head=True)
    line((T[0] + 12, T[1]), (A[0] - 13, A[1]), color=TRIAD, sw=2.6, head=True)
    for nx, ny in (O, T, A):
        out.append(f'<circle cx="{nx}" cy="{ny}" r="9" fill="{TRIAD}" stroke="#FFFFFF" '
                   f'stroke-width="2"/>')
    text(O[0] + 16, O[1], "Mục tiêu", fs=15, bold=True, anchor="start")
    text(T[0], T[1] + 24, "Hoạt động", fs=15, bold=True)
    text(A[0], A[1] + 24, "Đánh giá", fs=15, bold=True)
    text(gx - 34, gy - 14, "C3", fs=14, bold=True, fc=TRIAD, anchor="end")
    text(gx + 34, gy - 14, "C2", fs=14, bold=True, fc=TRIAD, anchor="start")
    text(gx, gy + 6, "C4", fs=14, bold=True, fc=TRIAD)
    # deterministic checks run on the state itself
    rect(gx - 72, gy + 58, 144, 26, fill=BRICK_FILL, stroke=BRICK, sw=1.3, r=13)
    text(gx, gy + 71, "kiểm tra tất định", fs=14, fc=BRICK)


# ── the ring: Designers and their Developer groups, clockwise ───────────────
RX, RY = 350, 178
BW, BH = 158, 76          # Designer block
DW, DH = 104, 40          # Developer group (label below adds 18)
# (id, angle in degrees clockwise from +x, kind, text or owning Designer)
RING = [
    # upper arc 200..338, lower arc 22..158; 0 and 180 stay free for output/input
    ("d1", 200, "designer", ("Needs Analyst", "Agent")),
    ("d2", 236, "designer", ("Outcome Designer", "Agent")),
    ("d3", 270, "designer", ("Assessment", "Designer Agent")),
    ("v3", 304, "developer", "d3"),
    ("d4", 338, "designer", ("Activity Designer", "Agent")),
    ("v4", 22, "developer", "d4"),
    ("d5", 56, "designer", ("Content Designer", "Agent")),
    ("v5", 90, "developer", "d5"),
    ("d6", 118, "designer", ("Implementation", "Planner Agent")),
    ("v6", 158, "developer", "d6"),
]
ACTIVE = "d3"


def on_ring(deg):
    a = math.radians(deg)
    return GC[0] + RX * math.cos(a), GC[1] + RY * math.sin(a)


for bid, deg, kind, _ in RING:
    cx, cy = on_ring(deg)
    w, h = (BW, BH) if kind == "designer" else (DW, DH + 18)
    BOXES[bid] = (cx - w / 2, cy - h / 2, w, h)

# inputs and outputs, outside the ring
BOXES["brief"] = (0, 212, 100, 44)
BOXES["out"] = (862, 352, 176, 100)


def overlaps(a, b, gap=6):
    return not (a[0] + a[2] + gap <= b[0] or b[0] + b[2] + gap <= a[0]
                or a[1] + a[3] + gap <= b[1] or b[1] + b[3] + gap <= a[1])


ids = list(BOXES)
clash = [(p, q) for i, p in enumerate(ids) for q in ids[i + 1:]
         if overlaps(BOXES[p], BOXES[q])]
assert not clash, f"blocks overlap: {clash}"

# spokes first, so blocks draw on top of them
for bid, deg, kind, _ in RING:
    if bid == ACTIVE:
        continue
    box = BOXES[bid]                       # a group's label belongs to it too
    c = (box[0] + box[2] / 2, box[1] + box[3] / 2)
    line(box_edge(box, GC), ellipse_edge(c), color=MUTED, sw=1.6, head=True, tail=True)

hub()

for bid, deg, kind, payload in RING:
    x, y, w, h = BOXES[bid]
    cx = x + w / 2
    if kind == "designer":
        on = bid == ACTIVE
        rect(x, y, w, h, fill=SLATE if on else "#FFFFFF", stroke=SLATE if on else MUTED,
             sw=1.8 if on else 1.3, r=12)
        glyph(cx, y + 20, on=on)
        fc = "#FFFFFF" if on else INK
        n = int(bid[1])
        text(cx, y + 46, f"{n}. {payload[0]}", fs=15, bold=on, fc=fc)
        text(cx, y + 64, payload[1], fs=15, bold=on, fc=fc)
    else:
        rect(x, y, DW, DH, fill="#FFFFFF", stroke=SLATE, sw=1.3, r=12, dash=True)
        for j in range(3):
            glyph(x + 22 + j * 30, y + DH / 2 + 3, s=0.9)
        text(cx, y + DH + 11, "Developer", fs=14, fc=SLATE)
        # delegated by its Designer
        owner = BOXES[payload]
        oc = (owner[0] + owner[2] / 2, owner[1] + owner[3] / 2)
        mine = BOXES[bid]
        mc = (cx, y + h / 2)
        line(box_edge(owner, mc, pad=3), box_edge(mine, oc, pad=4),
             color=SLATE, sw=1.7, head=True, dash=True)

# the agent holding the turn: tool call and observation, in colour
ax0, ay0, aw, ah = BOXES[ACTIVE]
acx = ax0 + aw / 2
call_from = (acx - 12, ay0 + ah + 2)
obs_to = (acx + 12, ay0 + ah + 2)
line(call_from, ellipse_edge(call_from), color=SLATE, sw=2.4, head=True)
line(ellipse_edge(obs_to), obs_to, color=OCHRE, sw=2.4, head=True, dash=True)
mid_y = (ay0 + ah + ellipse_edge(call_from)[1]) / 2
text(acx - 22, mid_y, "gọi công cụ", fs=15, fc=SLATE, anchor="end")
text(acx + 22, mid_y, "quan sát", fs=15, fc=OCHRE, anchor="start")

# input and outputs
bx, by, bw, bh = BOXES["brief"]
rect(bx, by, bw, bh, fill=GREY_FILL, stroke=GREY)
text(bx + bw / 2, by + 13, "Bản mô tả", fs=15, bold=True)
text(bx + bw / 2, by + 31, "thiết kế", fs=15, bold=True)
line((bx + bw, by + bh / 2), ellipse_edge((0, by + bh / 2)), color=GREY, sw=2.0,
     head=True)
ox, oy, ow, oh = BOXES["out"]
rect(ox, oy, ow, oh, fill="#FFFFFF", stroke=GREY, sw=1.4, r=12)
for k, label in enumerate(("Bản thiết kế ADDIE", "Đồ thị + sổ vi phạm")):
    rect(ox + 8, oy + 8 + k * 44, ow - 16, 40, fill=GREY_FILL, stroke=GREY, sw=1.3, r=8)
    text(ox + ow / 2, oy + 28 + k * 44, label, fs=15, bold=True)
oc = (ox + ow / 2, oy + oh / 2)
line(ellipse_edge(oc), box_edge(BOXES["out"], GC, pad=3), color=GREY, sw=2.0, head=True)

# canvas: tight around everything drawn
xs = [b[0] for b in BOXES.values()] + [b[0] + b[2] for b in BOXES.values()]
ys = [b[1] for b in BOXES.values()] + [b[1] + b[3] for b in BOXES.values()]
X0, Y0, X1, Y1 = min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>'
    f'<marker id="s-{c[1:]}" markerWidth="7" markerHeight="7" refX="0.8" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 7 0 L 0 3 L 7 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD, MUTED))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
       f'width="{X1 - X0:.0f}px" height="{Y1 - Y0:.0f}px" '
       f'viewBox="{X0:.0f} {Y0:.0f} {X1 - X0:.0f} {Y1 - Y0:.0f}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
path = Path(__file__).with_name("architecture_hub3.svg")
path.write_text(svg)
print("wrote", path, f"{X1 - X0:.0f}x{Y1 - Y0:.0f}")
