"""Render figures/architecture_hub.svg: Hình 1, hub-and-spoke.

Same components and visual language as architecture_band (survey 2026-10-13),
arranged around the shared state: the alignment graph at the centre, the harness
as a ring around it (the only thing that touches the graph), the six role chips
on the spokes in clockwise turn order, the active agent's tool-call/observation
pair in two colours, input on the left and outputs below.

Every label is >= 16 px, i.e. >= 7 pt once the 1150 px canvas is set at 18 cm.

Build: python3 make_architecture_hub.py && rsvg-convert -f pdf -o architecture_hub.pdf architecture_hub.svg
"""
import math
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"
TRIAD = "#8A6A3B"
GREY, GREY_FILL, MUTED = "#6B7480", "#F2F3F4", "#A5AEB8"
INK = "#1F2328"
FONT = "Arial,Helvetica,sans-serif"

out: list[str] = []


def text(x, y, s, *, fs=16, bold=False, fc=INK, anchor="middle"):
    w = "bold" if bold else "normal"
    out.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="{w}" fill="{fc}" text-anchor="{anchor}" '
               f'dominant-baseline="central">{s}</text>')


def rect(x, y, w, h, *, fill, stroke, sw=1.6, r=10):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def line(x0, y0, x1, y1, *, color=MUTED, sw=1.6, head=False, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    out.append(f'<path d="M {x0:.1f} {y0:.1f} L {x1:.1f} {y1:.1f}" stroke="{color}" '
               f'stroke-width="{sw}" fill="none"{d}{m}/>')


def glyph(cx, cy, *, on):
    """A small flat agent glyph (robot head), the same for every role."""
    edge = "#FFFFFF" if on else SLATE
    out.append(f'<rect x="{cx - 11}" y="{cy - 8}" width="22" height="17" rx="6" '
               f'fill="#FFFFFF" stroke="{edge}" stroke-width="1.4"/>')
    out.append(f'<rect x="{cx - 7.5}" y="{cy - 4.5}" width="15" height="9.5" rx="4" '
               f'fill="#24323F"/>')
    for dx in (-3.2, 3.2):
        out.append(f'<circle cx="{cx + dx}" cy="{cy + 0.2}" r="1.8" fill="#8FDCF5"/>')
    out.append(f'<path d="M {cx} {cy - 8} L {cx} {cy - 12}" stroke="{edge}" '
               f'stroke-width="1.4"/>')
    out.append(f'<circle cx="{cx}" cy="{cy - 13.5}" r="2" fill="#E07A5F"/>')


def towards(box, target):
    """Point on a box's border in the direction of `target`."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = target[0] - cx, target[1] - cy
    t = min((w / 2) / abs(dx) if dx else math.inf, (h / 2) / abs(dy) if dy else math.inf)
    return cx + dx * t, cy + dy * t


# ── the hub: harness ring around the alignment graph ────────────────────────
RING = (400, 100, 390, 232)
rect(*RING, fill=SLATE_FILL, stroke=SLATE, sw=2.2, r=26)
text(595, 122, "Khung điều phối", fs=17, bold=True, fc=SLATE)

# the graph itself, drawn as a graph: a light blob of typed nodes, the
# constructive-alignment triad in the foreground, other node types faint
out.append(f'<ellipse cx="595" cy="226" rx="168" ry="82" fill="{BAND_FILL}" '
           f'stroke="{TRIAD}" stroke-width="1.4" stroke-dasharray="5 3"/>')
FAINT = [(470, 196), (452, 254), (720, 196), (738, 254), (540, 168), (650, 168)]
O, T, A = (595, 182), (538, 262), (652, 262)
for (fx, fy), to in zip(FAINT, (T, T, A, A, O, O)):
    out.append(f'<path d="M {fx} {fy} L {to[0]} {to[1]}" stroke="{MUTED}" '
               f'stroke-width="1.1"/>')
out.append(f'<path d="M 470 196 L 456 252 M 720 196 L 736 252 M 540 170 L 470 196 '
           f'M 650 170 L 720 196" stroke="{MUTED}" stroke-width="1.1"/>')
for fx, fy in FAINT:
    out.append(f'<circle cx="{fx}" cy="{fy}" r="6" fill="#FFFFFF" stroke="{MUTED}" '
               f'stroke-width="1.3"/>')
line(O[0] - 7, O[1] + 10, T[0] + 6, T[1] - 11, color=TRIAD, sw=2.6, head=True)
line(O[0] + 7, O[1] + 10, A[0] - 6, A[1] - 11, color=TRIAD, sw=2.6, head=True)
line(T[0] + 12, T[1], A[0] - 13, A[1], color=TRIAD, sw=2.6, head=True)
for (nx, ny) in (O, T, A):
    out.append(f'<circle cx="{nx}" cy="{ny}" r="10" fill="{TRIAD}" stroke="#FFFFFF" '
               f'stroke-width="2"/>')
text(595, 160, "Mục tiêu", fs=16, bold=True)
text(538, 286, "Hoạt động", fs=16, bold=True)
text(652, 286, "Đánh giá", fs=16, bold=True)
text(552, 214, "C3", fs=15, bold=True, fc=TRIAD, anchor="end")
text(638, 214, "C2", fs=15, bold=True, fc=TRIAD, anchor="start")
text(595, 249, "C4", fs=15, bold=True, fc=TRIAD)
text(595, 318, "đồ thị căn chỉnh", fs=16, bold=True, fc=TRIAD)

# ── the spokes: six roles, clockwise in turn order ──────────────────────────
ROLES = ["Needs Analyst Agent", "Outcome Designer Agent", "Assessment Designer Agent",
         "Activity Designer Agent", "Content Designer Agent",
         "Implementation Planner Agent"]
CENTRES = [(222, 146), (430, 46), (760, 46), (968, 146), (968, 290), (222, 290)]
ACTIVE = 2
CW, CH = 276, 46
hub = (RING[0] + RING[2] / 2, RING[1] + RING[3] / 2)
for k, ((cx, cy), name) in enumerate(zip(CENTRES, ROLES)):
    on = k == ACTIVE
    x, y = cx - CW / 2, cy - CH / 2
    a = towards((x, y, CW, CH), hub)
    b = towards(RING, (cx, cy))
    if not on:
        line(*a, *b, color=MUTED, sw=1.6)
    rect(x, y, CW, CH, fill=SLATE if on else "#FFFFFF",
         stroke=SLATE if on else MUTED, sw=1.8 if on else 1.3, r=12)
    glyph(x + 22, cy + 2, on=on)
    text(x + 40, cy, f"{k + 1} {name}", fs=16, bold=on,
         fc="#FFFFFF" if on else GREY, anchor="start")

# ── Developer tier: a Designer delegates its list-valued family to Developers,
# one work set each. Drawn as a separate group, never as copies of the Designer.
DW, DH = 110, 44
DEV = {2: "right", 3: "right", 4: "right", 5: "below"}
for k, side in DEV.items():
    cx, cy = CENTRES[k]
    if side == "right":
        gx, gy = cx + CW / 2 + 34, cy
        line(cx + CW / 2, cy, gx - 2, cy, color=SLATE, sw=1.8, head=True, dash=True)
    else:                                         # below the Designer
        gx, gy = cx - DW / 2, cy + CH / 2 + 32 + DH / 2
        line(cx, cy + CH / 2, cx, gy - DH / 2 - 2, color=SLATE, sw=1.8, head=True,
             dash=True)
    out.append(f'<rect x="{gx}" y="{gy - DH / 2}" width="{DW}" height="{DH}" rx="12" '
               f'fill="#FFFFFF" stroke="{SLATE}" stroke-width="1.3" '
               f'stroke-dasharray="5 3"/>')
    for j in range(3):
        glyph(gx + 22 + j * 33, gy + 3, on=False)
    if side == "right":
        text(gx + DW / 2, gy + DH / 2 + 14, "Developer", fs=16, fc=SLATE)
    else:
        text(gx + DW + 8, gy, "Developer", fs=16, fc=SLATE, anchor="start")

# the active agent's tool call and observation
AX = CENTRES[ACTIVE][0] - 30
line(AX - 10, 70, AX - 10, 98, color=SLATE, sw=2.4, head=True)
line(AX + 14, 98, AX + 14, 70, color=OCHRE, sw=2.4, head=True, dash=True)
text(AX - 26, 85, "gọi công cụ", fs=16, fc=SLATE, anchor="end")
text(AX + 28, 85, "quan sát", fs=16, fc=OCHRE, anchor="start")

# ── input and outputs ───────────────────────────────────────────────────────
rect(8, 192, 118, 52, fill=GREY_FILL, stroke=GREY)
text(67, 209, "Bản mô tả", fs=16, bold=True)
text(67, 229, "thiết kế", fs=16, bold=True)
line(126, 218, 398, 218, color=GREY, sw=2.0, head=True)

line(510, 332, 510, 354, color=GREY, sw=2.0, head=True)
line(680, 332, 680, 354, color=GREY, sw=2.0, head=True)
rect(410, 356, 180, 42, fill=GREY_FILL, stroke=GREY)
text(500, 377, "Bản thiết kế ADDIE", fs=16, bold=True)
rect(600, 356, 180, 42, fill=GREY_FILL, stroke=GREY)
text(690, 377, "Đồ thị + sổ vi phạm", fs=16, bold=True)

W, H = 1260, 404
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD, MUTED))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}px" '
       f'height="{H}px" viewBox="0 0 {W} {H}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
path = Path(__file__).with_name("architecture_hub.svg")
path.write_text(svg)
print("wrote", path)
