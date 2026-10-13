"""Render figures/architecture_panels.svg: Hình 1 as framed panels.

Layout borrowed from the panel style common in applied-AI system papers
(Input | stacked process panels | Output, each panel framed and titled):

* Đầu vào          -- the design brief, read by every agent;
* Stage Agent      -- the six role agents in Backward Design order, the one
                      holding the turn highlighted;
* Developer        -- the groups four Stage Agents delegate to, one agent per work
                      set, acting through the same harness;
* Environment      -- what an agent acts on through tools: a read queries the
                      graph, a submit goes through validation, left to right, with the
                      alignment graph drawn as a graph in the middle of it;
* Đầu ra           -- the ADDIE design, the graph export and the ledger.

All geometry derives from the constants below, so rows stay centred and gaps
stay equal. Every label is >= 16 px, i.e. >= 7 pt with the canvas set at 18 cm.

Build: python3 make_architecture_panels.py && rsvg-convert -f pdf -o architecture_panels.pdf architecture_panels.svg
"""
from pathlib import Path

SLATE = "#3E5F7E"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"
TRIAD = "#8A6A3B"
BRICK, BRICK_FILL = "#8C4B47", "#F4ECEB"
GREY, MUTED = "#6B7480", "#A5AEB8"
AMBER, PURPLE, BLUE, BADGE = "#E3B04B", "#9C8FC7", "#7FB3D5", "#4F6F52"
STEP_FILL = "#F6E3CF"
INK = "#1F2328"
FONT = "Arial,Helvetica,sans-serif"

out: list[str] = []


# ── primitives ──────────────────────────────────────────────────────────────
def text(x, y, s, *, fs=16, bold=False, fc=INK, anchor="middle", italic=False):
    w = "bold" if bold else "normal"
    st = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="{w}" fill="{fc}" text-anchor="{anchor}"{st} '
               f'dominant-baseline="central">{s}</text>')


def rect(x, y, w, h, *, fill, stroke, sw=1.6, r=10, dash=False):
    d = ' stroke-dasharray="5 3"' if dash else ""
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def path(points, *, color=INK, sw=2.2, dash=False, head=True, tail=False):
    """`dash`: False (solid), True (dashed) or an explicit dasharray string."""
    if dash is True:
        d = ' stroke-dasharray="6 4"'
    elif dash:
        d = f' stroke-dasharray="{dash}" stroke-linecap="round"'
    else:
        d = ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    m += f' marker-start="url(#s-{color[1:]})"' if tail else ""
    pts = " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    out.append(f'<path d="M {pts}" stroke="{color}" stroke-width="{sw}" fill="none" '
               f'stroke-linejoin="round"{d}{m}/>')


def arrow(p, q, **kw):
    path([p, q], **kw)


def panel(x, y, w, h, title, color):
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=3, r=6)
    text(x + 12, y + 18, title, fs=17, bold=True, italic=True, anchor="start")


def glyph(cx, cy, *, on=False, s=1.0):
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


def doc_icon(cx, cy, s=1.0):
    w, h, f = 30 * s, 38 * s, 9 * s
    x, y = cx - w / 2, cy - h / 2
    out.append(f'<path d="M {x} {y} L {x + w - f} {y} L {x + w} {y + f} L {x + w} {y + h} '
               f'L {x} {y + h} Z" fill="#FFFFFF" stroke="{INK}" stroke-width="1.6"/>')
    out.append(f'<path d="M {x + w - f} {y} L {x + w - f} {y + f} L {x + w} {y + f}" '
               f'fill="none" stroke="{INK}" stroke-width="1.4"/>')
    for k in range(4):
        yy = y + 13 * s + k * 6 * s
        out.append(f'<path d="M {x + 6 * s} {yy} L {x + w - 6 * s} {yy}" stroke="{GREY}" '
                   f'stroke-width="1.4"/>')


def graph_icon(cx, cy, s=1.0):
    pts = [(cx, cy - 13 * s), (cx - 13 * s, cy + 10 * s), (cx + 13 * s, cy + 10 * s)]
    out.append(f'<path d="M {pts[0][0]} {pts[0][1]} L {pts[1][0]} {pts[1][1]} '
               f'L {pts[2][0]} {pts[2][1]} Z" fill="none" stroke="{TRIAD}" '
               f'stroke-width="2"/>')
    for x, y in pts:
        out.append(f'<circle cx="{x}" cy="{y}" r="{5.5 * s}" fill="{TRIAD}"/>')


def ledger_icon(cx, cy, s=1.0):
    x, y = cx - 15 * s, cy - 18 * s
    out.append(f'<rect x="{x}" y="{y}" width="{30 * s}" height="{36 * s}" rx="3" '
               f'fill="#FFFFFF" stroke="{INK}" stroke-width="1.6"/>')
    for k, ok in enumerate((True, False, True)):
        yy = y + 10 * s + k * 9 * s
        mark = (f'M {x + 5 * s} {yy} l {2 * s} {2.5 * s} l {4 * s} {-5 * s}' if ok else
                f'M {x + 5 * s} {yy - 2.5 * s} l {5 * s} {5 * s} M {x + 10 * s} '
                f'{yy - 2.5 * s} l {-5 * s} {5 * s}')
        out.append(f'<path d="{mark}" stroke="{"#3C9A5F" if ok else BRICK}" '
                   f'stroke-width="1.6" fill="none"/>')
        out.append(f'<path d="M {x + 14 * s} {yy} L {x + 25 * s} {yy}" stroke="{GREY}" '
                   f'stroke-width="1.4"/>')


# ── grid ────────────────────────────────────────────────────────────────────
PAD, GAP = 16, 22                    # inside a panel / between panels
SIDE_W = 118                         # input and output columns
TOP = 6
MID_X = 6 + SIDE_W + GAP
MID_W = 932
OUT_X = MID_X + MID_W + GAP
W = OUT_X + SIDE_W + 6
MID_L, MID_R = MID_X + PAD, MID_X + MID_W - PAD

VGAP = 12                            # between the stacked middle panels
DES_Y, DES_H = TOP, 126
DEV_Y, DEV_H = DES_Y + DES_H + VGAP, 96
HAR_Y, HAR_H = DEV_Y + DEV_H + VGAP, 170
BOTTOM = HAR_Y + HAR_H
H = BOTTOM + 6

# ── Stage Agent row, centred in its panel ──────────────────────────────────────
NAMES = [("Needs", "Analyst"), ("Outcome", "Designer"), ("Assessment", "Designer"),
         ("Activity", "Designer"), ("Content", "Designer"), ("Implementation", "Planner")]
ACTIVE = 0                           # the agent holding the turn in this snapshot
CW, CH = 132, 78
CGAP = (MID_R - MID_L - 6 * CW) / 5
CY = DES_Y + 36
cards = [MID_L + k * (CW + CGAP) for k in range(6)]
# the act/observe pair runs down the right-hand part of the active card, clear
# of the panel titles, which all sit in the top-left corner
# observe on the left, act on the right, so the read branch leaving the act line
# to the right crosses nothing; both stay on the straight part of the card edge
OBS_X = cards[ACTIVE] + CW - 24
ACT_X = cards[ACTIVE] + CW - 8

panel(6, TOP, SIDE_W, BOTTOM - TOP, "Input", AMBER)
panel(MID_X, DES_Y, MID_W, DES_H, "Stage Agent", PURPLE)
panel(MID_X, DEV_Y, MID_W, DEV_H, "Developer", PURPLE)
panel(MID_X, HAR_Y, MID_W, HAR_H, "Environment", BLUE)
panel(OUT_X, TOP, SIDE_W, BOTTOM - TOP, "Output", AMBER)

for k, ((l1, l2), x) in enumerate(zip(NAMES, cards)):
    on = k == ACTIVE
    rect(x, CY, CW, CH, fill=SLATE if on else "#FFFFFF", stroke=SLATE if on else MUTED,
         sw=1.8 if on else 1.4, r=12)
    glyph(x + CW / 2, CY + 20, on=on)
    fc = "#FFFFFF" if on else INK
    text(x + CW / 2, CY + 44, l1, fs=16, bold=on, fc=fc)
    text(x + CW / 2, CY + 63, l2, fs=16, bold=on, fc=fc)
    out.append(f'<circle cx="{x + 4}" cy="{CY + 4}" r="11" fill="{BADGE}" '
               f'stroke="#FFFFFF" stroke-width="1.5"/>')
    text(x + 4, CY + 4, str(k + 1), fs=14, bold=True, fc="#FFFFFF")
    if k < 5:                                       # turn order
        mx, my = x + CW + CGAP / 2 - 3, CY + CH / 2
        out.append(f'<path d="M {mx} {my - 7} L {mx + 7} {my} L {mx} {my + 7}" '
                   f'stroke="{MUTED}" stroke-width="2.4" fill="none" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')

# ── Developer groups, each straight under the Stage Agent that delegates to it ─
GW, GH = 108, 40
GY = DEV_Y + 32
groups = {}
for k in (2, 3, 4, 5):
    cx = cards[k] + CW / 2
    arrow((cx, CY + CH + 2), (cx, GY - 3), color=SLATE, sw=1.7, dash=True)
    rect(cx - GW / 2, GY, GW, GH, fill="#FFFFFF", stroke=SLATE, sw=1.3, r=10, dash=True)
    for j in (-1, 0, 1):
        glyph(cx + j * 31, GY + 23, s=0.9)
    groups[k] = cx
first = groups[2]
text(first + 8, DEV_Y + 14, "delegate", fs=15, fc=SLATE, anchor="start", italic=True)

# ── Environment: what an agent's tool calls act on. The tools belong to each
# agent (bound per role); what is shared is the graph and the rules the harness
# applies to it. A tool call splits at the panel's edge: a submit goes through
# validation and is written; a read queries the graph. ─────────────────────
VW, SW_, SH_ = 140, 130, 62           # validate box, other boxes, box height
GRX, GRY = 106, 60
J_Y = HAR_Y + 32                      # where a tool call enters the environment
sy = HAR_Y + 68
row_y = sy + SH_ / 2
SG = (MID_R - MID_L - (VW + 2 * SW_ + 2 * GRX)) / 3
x_val = MID_L
x_write = x_val + VW + SG
g_cx = x_write + SW_ + SG + GRX
x_rules = g_cx + GRX + SG


def step(x, w, l1, l2, *, color=TRIAD, fill=STEP_FILL):
    rect(x, sy, w, SH_, fill=fill, stroke=color, sw=1.5, r=8)
    text(x + w / 2, sy + 21, l1, fs=16, bold=True)
    text(x + w / 2, sy + 41, l2, fs=16, bold=True)


step(x_val, VW, "Validate", "submit")
step(x_write, SW_, "Write nodes,", "build edges")
step(x_rules, SW_, "Deterministic", "checks", color=BRICK, fill=BRICK_FILL)
arrow((x_val + VW + 4, row_y), (x_write - 4, row_y))
arrow((x_write + SW_ + 4, row_y), (g_cx - GRX - 4, row_y))
arrow((g_cx + GRX + 4, row_y), (x_rules - 4, row_y))

# the alignment graph, drawn as a graph
GX, GYc = g_cx, row_y
out.append(f'<ellipse cx="{GX}" cy="{GYc}" rx="{GRX}" ry="{GRY}" fill="{BAND_FILL}" '
           f'stroke="{TRIAD}" stroke-width="1.8"/>')
text(GX, GYc - 34, "Alignment graph", fs=16, bold=True, fc=TRIAD)
O, T, A = (GX, GYc - 9), (GX - 40, GYc + 26), (GX + 40, GYc + 26)
for f, to in (((GX - 84, GYc + 6), T), ((GX - 72, GYc + 34), T),
              ((GX + 84, GYc + 6), A), ((GX + 72, GYc + 34), A)):
    out.append(f'<path d="M {f[0]} {f[1]} L {to[0]} {to[1]}" stroke="{MUTED}" '
               f'stroke-width="1.1"/>')
    out.append(f'<circle cx="{f[0]}" cy="{f[1]}" r="5.5" fill="#FFFFFF" stroke="{MUTED}" '
               f'stroke-width="1.3"/>')
arrow((O[0] - 5, O[1] + 9), (T[0] + 5, T[1] - 10), color=TRIAD, sw=2.4)
arrow((O[0] + 5, O[1] + 9), (A[0] - 5, A[1] - 10), color=TRIAD, sw=2.4)
arrow((T[0] + 11, T[1]), (A[0] - 12, A[1]), color=TRIAD, sw=2.4)
for x, y in (O, T, A):
    out.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{TRIAD}" stroke="#FFFFFF" '
               f'stroke-width="2"/>')
text(GX - 34, GYc + 6, "C3", fs=14, bold=True, fc=TRIAD, anchor="end")
text(GX + 34, GYc + 6, "C2", fs=14, bold=True, fc=TRIAD, anchor="start")
text(GX, GYc + 43, "C4", fs=14, bold=True, fc=TRIAD)

# ── the agent holding the turn: a tool call down, its result back up ────────
assert x_val < OBS_X and ACT_X < x_val + VW, "validation must sit under the pair"
assert SG >= 40, f"steps too tight: {SG:.0f}px"
path([(ACT_X, CY + CH + 3), (ACT_X, sy - 3)], color=SLATE, sw=2.6)        # submit
# read: along the top of the panel, then down onto the graph
rx_ = GX - 44
top_at = row_y - GRY * (1 - (44 / GRX) ** 2) ** 0.5
assert J_Y < top_at - 10, "read lane must run above the graph"
path([(ACT_X, J_Y), (rx_, J_Y), (rx_, top_at - 3)], color=SLATE, sw=2.2)
out.append(f'<circle cx="{ACT_X}" cy="{J_Y}" r="3.6" fill="{SLATE}"/>')
text(ACT_X + 8, (J_Y + sy) / 2 + 1, "submit", fs=15, fc=SLATE, anchor="start")
text((ACT_X + rx_) / 2 + 40, J_Y - 11, "read", fs=15, fc=SLATE)
arrow((OBS_X, sy - 3), (OBS_X, CY + CH + 3), color=OCHRE, sw=2.6, dash=True)
LBL_Y = DEV_Y + DEV_H / 2 + 4
text(OBS_X - 9, LBL_Y, "observe", fs=16, bold=True, fc=OCHRE, anchor="end")
text(ACT_X + 9, LBL_Y, "act", fs=16, bold=True, fc=SLATE, anchor="start")

# Developers make the same kinds of tool call: along the bottom of their
# panel, then down onto the same entry (two-headed, dashed: call and result)
dlane = DEV_Y + DEV_H - 12
drop = ACT_X + 40
g3 = groups[2] - GW / 2 + 20
path([(g3, GY + GH + 3), (g3, dlane), (drop, dlane), (drop, J_Y - 3)],
     color=SLATE, sw=1.8, dash=True, tail=True)

# a violation that needs writing goes back to the agent that owns it: up from
# the checks, through the gap between Developer groups 5 and 6, into the
# Stage Agent tier (dashed, brick)
gap_x = (groups[4] + GW / 2 + groups[5] - GW / 2) / 2
card_gap = (cards[4] + CW + cards[5]) / 2
assert abs(gap_x - card_gap) < 30, "repair lane must pass between groups and cards"
jog_y = HAR_Y + 30
rx0 = x_rules + 14
assert rx0 > g_cx + GRX + 8, "repair lane must clear the graph"
path([(rx0, sy - 3), (rx0, jog_y), (gap_x, jog_y), (gap_x, DES_Y + DES_H + 3)],
     color=BRICK, sw=2.4, dash="0.1 5")      # dotted: unlike every dashed line
text(rx0 + 10, jog_y, "repair turn", fs=16, bold=True, fc=BRICK, anchor="start")

# ── input and outputs ───────────────────────────────────────────────────────
ic = 6 + SIDE_W / 2
mid = (TOP + BOTTOM) / 2 + 8
doc_icon(ic, mid - 62, 1.2)
text(ic, mid - 18, "Design", fs=16, bold=True)
text(ic, mid + 2, "brief", fs=16, bold=True)
for k, line in enumerate(("learners,", "goals,", "constraints")):
    text(ic, mid + 32 + k * 20, line, fs=16, fc=GREY)
arrow((6 + SIDE_W + 3, CY + CH / 2), (MID_X - 3, CY + CH / 2))
arrow((MID_X + MID_W + 3, row_y), (OUT_X - 3, row_y))

oc = OUT_X + SIDE_W / 2
OUT = [(doc_icon, ("ADDIE", "design")), (graph_icon, ("graph.json",)),
       (ledger_icon, ("Violation", "ledger"))]
slot = (BOTTOM - TOP - 34) / 3
for k, (icon, lines) in enumerate(OUT):
    cy = TOP + 34 + slot * (k + 0.5) - 12
    icon(oc, cy - 14, 1.15)
    for j, line in enumerate(lines):
        text(oc, cy + 26 + j * 20, line, fs=16, bold=True)

defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>'
    f'<marker id="s-{c[1:]}" markerWidth="7" markerHeight="7" refX="0.8" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 7 0 L 0 3 L 7 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD, MUTED, INK, BRICK))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W:.0f}px" '
       f'height="{H:.0f}px" viewBox="0 0 {W:.0f} {H:.0f}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
out_path = Path(__file__).with_name("architecture_panels.svg")
out_path.write_text(svg)
print("wrote", out_path, f"{W:.0f}x{H:.0f}")
