"""Render figures/architecture_timeline.svg: Hình 1 as the graph growing stage by stage.

Four rows over six columns, one column per stage:

* Stage Agent     -- the six role agents, in turn order 1 -> 6;
* Developer       -- the groups four Stage Agents delegate to;
* Guardrails      -- one boundary per stage that every call of the stage passes
                     through: a read comes up scoped to the agent's role and stage
                     (observe); a submit meets a decision (diamond) -- pass goes on
                     into the graph, fail goes back up to whoever submitted it, the
                     Stage Agent or its Developers (repair turn);
* Alignment graph -- a snapshot of the shared graph after each stage: what the
                     stage added is drawn in colour, what was already there in grey.
                     The constructive-alignment triangle closes at stage 4.

Build: python3 make_architecture_timeline.py && rsvg-convert -f pdf -o architecture_timeline.pdf architecture_timeline.svg
"""
from pathlib import Path

SLATE = "#3E5F7E"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"
TRIAD = "#8A6A3B"
BRICK = "#8C4B47"
GREY, MUTED, FAINT = "#6B7480", "#A5AEB8", "#C9CFD6"
AMBER, PURPLE, BLUE, BADGE = "#E3B04B", "#9C8FC7", "#7FB3D5", "#4F6F52"
HARNESS, HARNESS_FILL = "#C08A85", "#F7EFEE"
NEW = "#3C7DA6"                      # a node or edge added by this stage
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


def path(points, *, color=INK, sw=2.0, dash=False, head=True):
    if dash is True:
        d = ' stroke-dasharray="6 4"'
    elif dash:
        d = f' stroke-dasharray="{dash}" stroke-linecap="round"'
    else:
        d = ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    pts = " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    out.append(f'<path d="M {pts}" stroke="{color}" stroke-width="{sw}" fill="none" '
               f'stroke-linejoin="round"{d}{m}/>')


def arrow(p, q, **kw):
    path([p, q], **kw)


def panel(x, y, w, h, title, color):
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=3, r=6)
    text(x + 12, y + 18, title, fs=17, bold=True, italic=True, anchor="start")


def lane(x, y, w, h, title, color, fs=14):
    """A middle row: framed, with its title set vertically in a strip on the left
    (swimlane style), so no arrow ever has to cross a title."""
    rect(x, y, w, h, fill="#FFFFFF", stroke=color, sw=3, r=6)
    tx, ty = x + LANE / 2 + 2, y + h / 2
    out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-family="{FONT}" font-size="{fs}" '
               f'font-weight="bold" font-style="italic" fill="{INK}" '
               f'text-anchor="middle" dominant-baseline="central" '
               f'transform="rotate(-90 {tx:.1f} {ty:.1f})">{title}</text>')
    out.append(f'<path d="M {x + LANE} {y + 8} L {x + LANE} {y + h - 8}" '
               f'stroke="{color}" stroke-width="1.2" stroke-dasharray="3 3"/>')


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


def gate(cx, cy):
    """The harness's gate on a write: validate on submit, deterministic checks."""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="#FFFFFF" '
               f'stroke="{BRICK}" stroke-width="1.8"/>')
    out.append(f'<path d="M {cx - 4.5:.1f} {cy + 0.5:.1f} l 3 3 l 6 -6.5" '
               f'stroke="{BRICK}" stroke-width="2" fill="none" stroke-linecap="round" '
               f'stroke-linejoin="round"/>')


def flag(cx, cy):
    """A violation the checks found: the repair turn starts here."""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="{BRICK}" '
               f'stroke="#FFFFFF" stroke-width="1.5"/>')
    out.append(f'<path d="M {cx - 3.8:.1f} {cy - 3.8:.1f} l 7.6 7.6 M {cx + 3.8:.1f} '
               f'{cy - 3.8:.1f} l -7.6 7.6" stroke="#FFFFFF" stroke-width="2" '
               f'stroke-linecap="round"/>')


DH = 7.5                              # half-size of a decision diamond


def decision(cx, cy):
    """A guardrail check on a submit: pass goes on into the graph, fail goes back."""
    out.append(f'<path d="M {cx:.1f} {cy - DH:.1f} L {cx + DH:.1f} {cy:.1f} '
               f'L {cx:.1f} {cy + DH:.1f} L {cx - DH:.1f} {cy:.1f} Z" fill="#FFFFFF" '
               f'stroke="{BRICK}" stroke-width="1.8" stroke-linejoin="round"/>')


def scope_filter(cx, cy):
    """A guardrail on a read: only the agent's own scope comes up (a funnel)."""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9.5" fill="#FFFFFF" '
               f'stroke="{OCHRE}" stroke-width="1.8"/>')
    out.append(f'<path d="M {cx - 5:.1f} {cy - 4:.1f} L {cx + 5:.1f} {cy - 4:.1f} '
               f'L {cx + 1.2:.1f} {cy + 0.8:.1f} L {cx + 1.2:.1f} {cy + 4.5:.1f} '
               f'L {cx - 1.2:.1f} {cy + 3.3:.1f} L {cx - 1.2:.1f} {cy + 0.8:.1f} Z" '
               f'fill="{OCHRE}" stroke="{OCHRE}" stroke-width="0.8" '
               f'stroke-linejoin="round"/>')


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
PAD, GAP, VGAP = 16, 22, 12
SIDE_W = 118
TOP = 6
MID_X = 6 + SIDE_W + GAP
MID_W = 932
OUT_X = MID_X + MID_W + GAP
W = OUT_X + SIDE_W + 6
LANE = 30                           # left strip holding a row's vertical title
MID_L, MID_R = MID_X + LANE + 12, MID_X + MID_W - PAD

CW = 128
CGAP = (MID_R - MID_L - 6 * CW) / 5
cols = [MID_L + k * (CW + CGAP) for k in range(6)]

STA_Y, STA_H = TOP, 114
DEV_Y, DEV_H = STA_Y + STA_H + VGAP, 86
HAR_Y, HAR_H = DEV_Y + DEV_H + VGAP, 82
GRA_Y, GRA_H = HAR_Y + HAR_H + VGAP, 156
BOTTOM = GRA_Y + GRA_H
LEG_Y = BOTTOM + 20                  # one legend line under everything
H = LEG_Y + 16

panel(6, TOP, SIDE_W, BOTTOM - TOP, "Input", AMBER)
lane(MID_X, STA_Y, MID_W, STA_H, "Stage Agent", PURPLE)
lane(MID_X, DEV_Y, MID_W, DEV_H, "Developer", PURPLE)
lane(MID_X, HAR_Y, MID_W, HAR_H, "Guardrails", HARNESS)
lane(MID_X, GRA_Y, MID_W, GRA_H, "Alignment graph", BLUE)
panel(OUT_X, TOP, SIDE_W, BOTTOM - TOP, "Output", AMBER)

# ── Stage Agents ────────────────────────────────────────────────────────────
NAMES = [("Needs", "Analyst"), ("Outcome", "Designer"), ("Assessment", "Designer"),
         ("Activity", "Designer"), ("Content", "Designer"), ("Implementation", "Planner")]
CY, CH = STA_Y + 20, 76
for k, ((l1, l2), x) in enumerate(zip(NAMES, cols)):
    rect(x, CY, CW, CH, fill="#FFFFFF", stroke=SLATE, sw=1.5, r=12)
    glyph(x + CW / 2, CY + 20)
    text(x + CW / 2, CY + 43, l1, fs=16)
    text(x + CW / 2, CY + 62, l2, fs=16)
    out.append(f'<circle cx="{x + 4}" cy="{CY + 4}" r="11" fill="{BADGE}" '
               f'stroke="#FFFFFF" stroke-width="1.5"/>')
    text(x + 4, CY + 4, str(k + 1), fs=14, bold=True, fc="#FFFFFF")
    if k < 5:
        mx, my = x + CW + CGAP / 2 - 3, CY + CH / 2
        out.append(f'<path d="M {mx} {my - 7} L {mx + 7} {my} L {mx} {my + 7}" '
                   f'stroke="{MUTED}" stroke-width="2.4" fill="none" '
                   f'stroke-linecap="round" stroke-linejoin="round"/>')

# ── Developer groups under the four Stage Agents that delegate ──────────────
GW, GH = 62, 58
GY = DEV_Y + (DEV_H - GH) / 2
DEV = (2, 3, 4, 5)
OBS, OWN, FAIL = 12, CW - 12, 14     # observe, the Stage Agent's own submit, fail offset
# the group sits midway between the observe line and the Stage Agent's fail branch
GX = (OBS + OWN - FAIL) / 2
for k in DEV:
    cx = cols[k] + GX
    arrow((cx, CY + CH + 2), (cx, GY - 3), color=SLATE, sw=1.7, dash=True)
    rect(cx - GW / 2, GY, GW, GH, fill="#FFFFFF", stroke=SLATE, sw=1.3, r=10, dash=True)
    # three Developers in a triangle: one above, two below
    for dx, dy in ((0, 20), (-15, 44), (15, 44)):
        glyph(cx + dx, GY + dy, s=0.9)

# ── snapshots of the graph after each stage ─────────────────────────────────
SNAP_Y, SNAP_H = GRA_Y + 14, 86
# node positions inside a snapshot (fractions of its box)
POS = {"g1": (0.13, 0.25), "g2": (0.13, 0.62), "o": (0.47, 0.18), "m": (0.86, 0.18),
       "t": (0.27, 0.86), "a": (0.67, 0.86), "mat": (0.9, 0.58), "s": (0.47, 0.56)}
EDGES = [("g1", "o", "P"), ("g2", "o", "P"), ("m", "o", "P"),
         ("o", "a", "C"), ("o", "t", "C"), ("t", "a", "C"),
         ("m", "mat", "P"), ("s", "t", "P"), ("s", "mat", "P")]
ADDED = [{"g1", "g2"}, {"o", "m"}, {"a"}, {"t"}, {"mat"}, {"s"}]
WHAT = [("+ gaps, topics,", "constraints"), ("+ objectives,", "modules"),
        ("+ assessment", "tasks · C2"), ("+ activities", "C3 · C4"),
        ("+ materials", ""), ("+ session", "guides")]


def snapshot(k):
    x0 = cols[k]
    rect(x0, SNAP_Y, CW, SNAP_H, fill=BAND_FILL, stroke=TRIAD, sw=1.3, r=10)
    have = set().union(*ADDED[: k + 1])
    new = ADDED[k]
    pt = {n: (x0 + 10 + fx * (CW - 20), SNAP_Y + 10 + fy * (SNAP_H - 20))
          for n, (fx, fy) in POS.items()}
    for u, v, kind in EDGES:
        if u in have and v in have:
            fresh = u in new or v in new
            if kind == "C":
                color, sw = (TRIAD if fresh or k >= 3 else MUTED), 2.4
            else:
                color, sw = (NEW if fresh else FAINT), 1.3
            (x1, y1), (x2, y2) = pt[u], pt[v]
            out.append(f'<path d="M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}" '
                       f'stroke="{color}" stroke-width="{sw}"/>')
    for n in have:
        x, y = pt[n]
        triad = n in ("o", "t", "a")
        r = 6.5 if triad else 5
        if n in new:
            fill, stroke = (TRIAD if triad else NEW), "#FFFFFF"
        else:
            fill, stroke = ("#D8C9B4" if triad else "#FFFFFF"), (TRIAD if triad else MUTED)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="1.5"/>')
    l1, l2 = WHAT[k]
    text(x0 + CW / 2, SNAP_Y + SNAP_H + 16, l1, fs=15, fc=GREY)
    if l2:
        text(x0 + CW / 2, SNAP_Y + SNAP_H + 34, l2, fs=15, fc=GREY)
    if k < 5:
        arrow((x0 + CW + 3, SNAP_Y + SNAP_H / 2), (cols[k + 1] - 3, SNAP_Y + SNAP_H / 2),
              color=GREY, sw=2.0)


for k in range(6):
    snapshot(k)

# ── guardrails: one boundary per stage, every read and submit passes it ────
BAR_Y, BAR_H = HAR_Y + 24, HAR_H - 48
for x0 in cols:
    rect(x0 - 9, BAR_Y, CW + 13, BAR_H, fill=HARNESS_FILL, stroke=BRICK, sw=1.4,
         r=BAR_H / 2)
BAR_C = BAR_Y + BAR_H / 2
for k in range(6):
    x0, cx = cols[k], cols[k] + CW / 2
    ox = x0 + OBS                         # observe: up the left edge
    # observe: the graph state and the errors, scoped by the guardrails
    path([(ox, SNAP_Y - 2), (ox, BAR_C + 10)], color=OCHRE, sw=1.8, dash=True, head=False)
    path([(ox, BAR_C - 10), (ox, CY + CH + 3)], color=OCHRE, sw=1.8, dash=True)
    scope_filter(ox, BAR_C)
    # each submit: (x of the line, y it starts from, y its fail branch returns to)
    if k in DEV:
        gx = x0 + GX
        subs = [(x0 + OWN, CY + CH + 2, CY + CH + 3),          # the Stage Agent's own
                (gx, GY + GH + 2, GY + GH + 3)]              # its Developers'
        assert x0 + OWN - FAIL > gx + GW / 2 + 5, "fail branch must clear the group"
    else:
        subs = [(cx, CY + CH + 2, CY + CH + 3)]
    for sx, top, back in subs:
        path([(sx, top), (sx, BAR_C - DH)], color=SLATE, sw=1.8, head=False)
        path([(sx, BAR_C + DH), (sx, SNAP_Y - 2)], color=SLATE, sw=1.8)       # pass
        path([(sx - DH, BAR_C), (sx - FAIL, BAR_C), (sx - FAIL, back)],       # fail
             color=BRICK, sw=2.2, dash="0.1 4.5")
        decision(sx, BAR_C)

# ── input, outputs ──────────────────────────────────────────────────────────
ic = 6 + SIDE_W / 2
mid = (TOP + BOTTOM) / 2 + 8
doc_icon(ic, mid - 62, 1.2)
text(ic, mid - 18, "Design", fs=16, bold=True)
text(ic, mid + 2, "brief", fs=16, bold=True)
for k, line in enumerate(("learners,", "goals,", "constraints")):
    text(ic, mid + 32 + k * 20, line, fs=16, fc=GREY)
arrow((6 + SIDE_W + 3, CY + CH / 2), (MID_X - 3, CY + CH / 2))
arrow((MID_X + MID_W + 3, SNAP_Y + SNAP_H / 2), (OUT_X - 3, SNAP_Y + SNAP_H / 2))

oc = OUT_X + SIDE_W / 2
OUT = [(doc_icon, ("ADDIE", "design")), (graph_icon, ("graph.json",)),
       (ledger_icon, ("Violation", "ledger"))]
slot = (BOTTOM - TOP - 34) / 3
for k, (icon, lines) in enumerate(OUT):
    cy = TOP + 34 + slot * (k + 0.5) - 12
    icon(oc, cy - 14, 1.15)
    for j, line in enumerate(lines):
        text(oc, cy + 26 + j * 20, line, fs=16, bold=True)

# ── legend: the arrow kinds, so no arrow needs a label of its own ───────────
# (item widths are measured from the rendered text; gaps are spread evenly)
ITEMS = [("line", SLATE, True, 1.7, "delegate", 116),
         ("line", SLATE, False, 2.0, "submit", 104),
         ("line", OCHRE, True, 2.0, "observe (state, errors)", 222),
         ("filter", None, None, None, "scoped read", 132),
         ("line", BRICK, "0.1 4.5", 2.2, "repair turn", 140),
         ("diamond", None, None, None, "verify", 96)]
lgap = (MID_W - 16 - sum(w for *_, w in ITEMS)) / (len(ITEMS) - 1)
lx = MID_X + 8
for kind, color, dash, sw, label, w in ITEMS:
    if kind == "line":
        path([(lx, LEG_Y), (lx + 40, LEG_Y)], color=color, sw=sw, dash=dash)
        text(lx + 48, LEG_Y, label, fs=15, anchor="start")
    elif kind == "diamond":
        decision(lx + DH, LEG_Y)
        text(lx + 2 * DH + 8, LEG_Y, label, fs=15, anchor="start")
    elif kind == "filter":
        scope_filter(lx + 10, LEG_Y)
        text(lx + 28, LEG_Y, label, fs=15, anchor="start")
    elif kind == "flag":
        flag(lx + 9, LEG_Y)
        text(lx + 26, LEG_Y, label, fs=15, anchor="start")
    else:
        gate(lx + 9, LEG_Y)
        text(lx + 26, LEG_Y, label, fs=15, anchor="start")
    lx += w + lgap

# arrowheads of one fixed size in user units, whatever the stroke width: a head
# that grows with the line crowds the gaps between blocks
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="8" markerHeight="7" refX="7.5" refY="3.5" '
    f'orient="auto" markerUnits="userSpaceOnUse"><path d="M 0 0 L 8 3.5 L 0 7 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD, MUTED, INK, BRICK))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W:.0f}px" '
       f'height="{H:.0f}px" viewBox="0 0 {W:.0f} {H:.0f}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
out_path = Path(__file__).with_name("architecture_timeline.svg")
out_path.write_text(svg)
print("wrote", out_path, f"{W:.0f}x{H:.0f}")
