"""Render figures/architecture_vi.svg: Hình 1 of the REV-ECIT 2026 paper.

Drawn from the CURRENT harness (alignmentgraph_isd/core/runner.py::_run_multi,
agentic/specialists.py::STEPS, agentic/alignment_state.py), not from the ACM
figure. Three things the picture must say, in this order:

* the alignment graph is the shared state in the middle;
* no agent touches it: every act is a tool call into the HARNESS ring around
  it, which validates a submit, writes the nodes, builds the typed edges from the
  ids the agent declared, and runs the checks;
* the six agents take turns 1 -> 6 in Backward Design order, each running its
  own act-observe loop; four of them hand list-valued families to Developers.

ADDIE is the shape of the assembled output, not the order of work.

Build: python3 make_architecture_vi.py && rsvg-convert -f pdf -o architecture_vi.pdf architecture_vi.svg
"""
import math
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
HARNESS_FILL = "#E4EBF2"
OCHRE, BAND_FILL, SEC = "#8A6A3B", "#F8F4EC", "#B7A88C"
BRICK, BRICK_FILL = "#8C4B47", "#F4ECEB"
GREEN = "#4F6F52"
GREY, GREY2, GREY_FILL = "#6B7480", "#7C848E", "#F2F3F4"
CORAL = "#E07A5F"
VISOR, EYE = "#24323F", "#8FDCF5"
INK = "#1F2328"
FONT = "Arial,Helvetica,sans-serif"
MONO = "Menlo,Consolas,monospace"

out: list[str] = []
B: dict[str, tuple[float, float, float, float]] = {}


# ── primitives ──────────────────────────────────────────────────────────────
def text(cx, cy, lines, *, fs=10.5, bold=True, fc=INK, anchor="middle", italic=False,
         family=FONT):
    weight = "bold" if bold else "normal"
    style = ' font-style="italic"' if italic else ""
    n = len(lines)
    top = cy - (n - 1) * fs * 0.6
    spans = "".join(
        f'<tspan x="{cx}" dy="{0 if i == 0 else fs * 1.2}">{t}</tspan>'
        for i, t in enumerate(lines))
    out.append(f'<text x="{cx}" y="{top + fs * 0.35}" font-family="{family}" '
               f'font-size="{fs}" font-weight="{weight}" fill="{fc}"{style} '
               f'text-anchor="{anchor}">{spans}</text>')


def rect(bid, x, y, w, h, *, fill, stroke, sw=1.4, r=8, dash=False):
    B[bid] = (x, y, w, h)
    d = ' stroke-dasharray="4 3"' if dash else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')


def box(bid, x, y, w, h, lines, *, fill, stroke, sw=1.4, fs=10.5, bold=True,
        r=8, fc=INK):
    rect(bid, x, y, w, h, fill=fill, stroke=stroke, sw=sw, r=r)
    if lines:
        text(x + w / 2, y + h / 2, lines, fs=fs, bold=bold, fc=fc)


def pt(bid, ax, ay):
    x, y, w, h = B[bid]
    return (x + ax * w, y + ay * h)


def centre(bid):
    return pt(bid, 0.5, 0.5)


def boundary(bid, toward, pad=0.0):
    """Where the segment from this box's centre toward `toward` leaves the box."""
    x, y, w, h = B[bid]
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    t = min((w / 2 + pad) / abs(dx) if dx else math.inf,
            (h / 2 + pad) / abs(dy) if dy else math.inf)
    return (cx + dx * t, cy + dy * t)


def edge(p0, p1, *, color=SLATE, sw=1.3, dash=False, head=True, label=None,
         lfs=9.5, ldx=0, ldy=-4, lanchor="middle", italic=True):
    d = ' stroke-dasharray="5 4"' if dash else ""
    m = f' marker-end="url(#a-{color[1:]})"' if head else ""
    out.append(f'<path d="M {p0[0]:.1f} {p0[1]:.1f} L {p1[0]:.1f} {p1[1]:.1f}" '
               f'fill="none" stroke="{color}" stroke-width="{sw}"{d}{m}/>')
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        text(mx + ldx, my + ldy, [label], fs=lfs, bold=False, fc=color,
             anchor=lanchor, italic=italic)


def curve(p, q, *, bend, color, sw=1.4, dash=False):
    """A quadratic arc p->q bowed to its left by `bend`: p->q and q->p drawn
    with the same bend form a lens, the two halves of one act-observe loop."""
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    n = math.hypot(dx, dy)
    c = (mx - dy / n * bend, my + dx / n * bend)
    d = ' stroke-dasharray="5 3"' if dash else ""
    out.append(f'<path d="M {p[0]:.1f} {p[1]:.1f} Q {c[0]:.1f} {c[1]:.1f} '
               f'{q[0]:.1f} {q[1]:.1f}" fill="none" stroke="{color}" '
               f'stroke-width="{sw}"{d} marker-end="url(#a-{color[1:]})"/>')


def chip(x, y, w, label, *, color=SLATE, fill="#FFFFFF"):
    rect(f"chip_{label}", x, y, w, 22, fill=fill, stroke=color, sw=1.1, r=11)
    text(x + w / 2, y + 11, [label], fs=8.8, bold=False, fc=color)


# ── the robot ───────────────────────────────────────────────────────────────
def robot(cx, cy, s=1.0, *, accent=CORAL, prop=None):
    """A flat 2D robot: head with visor and eyes, antenna, ears, body, arms.
    `cy` is the centre of the head; the body hangs below it."""
    def R(x, y, w, h, r, fill, stroke=SLATE, sw=1.3):
        out.append(f'<rect x="{cx + x * s:.1f}" y="{cy + y * s:.1f}" width="{w * s:.1f}" '
                   f'height="{h * s:.1f}" rx="{r * s:.1f}" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="{sw * s:.2f}"/>')

    def C(x, y, r, fill, stroke="none", sw=1.0):
        out.append(f'<circle cx="{cx + x * s:.1f}" cy="{cy + y * s:.1f}" r="{r * s:.1f}" '
                   f'fill="{fill}" stroke="{stroke}" stroke-width="{sw * s:.2f}"/>')

    def L(x0, y0, x1, y1, color=SLATE, sw=1.3):
        out.append(f'<path d="M {cx + x0 * s:.1f} {cy + y0 * s:.1f} L {cx + x1 * s:.1f} '
                   f'{cy + y1 * s:.1f}" stroke="{color}" stroke-width="{sw * s:.2f}" '
                   f'stroke-linecap="round" fill="none"/>')

    # antenna, ears
    L(0, -14, 0, -21)
    C(0, -23, 3, accent)
    R(-22, -6, 5, 12, 2, accent, stroke="none")
    R(17, -6, 5, 12, 2, accent, stroke="none")
    # body (behind the head), arms
    R(-12, 13, 24, 18, 6, "#FFFFFF")
    C(0, 22, 3, accent)
    L(-12, 17, -19, 25)
    L(12, 17, 19, 23)
    # head, visor, eyes, smile
    R(-18, -14, 36, 28, 10, "#FFFFFF")
    R(-13, -9, 26, 17, 7, VISOR, stroke="none")
    out.append(f'<ellipse cx="{cx - 5.5 * s:.1f}" cy="{cy - 1.5 * s:.1f}" rx="{2.6 * s:.1f}" '
               f'ry="{3.4 * s:.1f}" fill="{EYE}"/>')
    out.append(f'<ellipse cx="{cx + 5.5 * s:.1f}" cy="{cy - 1.5 * s:.1f}" rx="{2.6 * s:.1f}" '
               f'ry="{3.4 * s:.1f}" fill="{EYE}"/>')
    out.append(f'<path d="M {cx - 3.5 * s:.1f} {cy + 3.5 * s:.1f} Q {cx:.1f} {cy + 6.5 * s:.1f} '
               f'{cx + 3.5 * s:.1f} {cy + 3.5 * s:.1f}" stroke="{EYE}" '
               f'stroke-width="{1.2 * s:.2f}" fill="none" stroke-linecap="round"/>')
    if prop:
        PROPS[prop](cx + 24 * s, cy + 20 * s, s)


def _magnifier(x, y, s):
    out.append(f'<circle cx="{x}" cy="{y - 4 * s}" r="{6.5 * s}" fill="#DFF3FB" '
               f'stroke="{SLATE}" stroke-width="{2 * s}"/>')
    out.append(f'<path d="M {x - 4.5 * s} {y + 1 * s} L {x - 10 * s} {y + 7 * s}" '
               f'stroke="{SLATE}" stroke-width="{2.6 * s}" stroke-linecap="round"/>')


def _target(x, y, s):
    for r, f in ((8, "#FFFFFF"), (5.5, CORAL), (3, "#FFFFFF"), (1.3, CORAL)):
        out.append(f'<circle cx="{x}" cy="{y - 3 * s}" r="{r * s}" fill="{f}" '
                   f'stroke="{CORAL}" stroke-width="{0.9 * s}"/>')


def _clipboard(x, y, s):
    out.append(f'<rect x="{x - 7 * s}" y="{y - 12 * s}" width="{14 * s}" height="{18 * s}" '
               f'rx="{2 * s}" fill="#FFFFFF" stroke="{SLATE}" stroke-width="{1.3 * s}"/>')
    out.append(f'<rect x="{x - 3.5 * s}" y="{y - 14 * s}" width="{7 * s}" height="{4 * s}" '
               f'rx="{1 * s}" fill="{SLATE}"/>')
    for k in range(3):
        yy = y - 7 * s + k * 5 * s
        out.append(f'<path d="M {x - 5 * s} {yy} l {1.5 * s} {1.5 * s} l {2.5 * s} {-3 * s}" '
                   f'stroke="#3C9A5F" stroke-width="{1.2 * s}" fill="none"/>')
        out.append(f'<path d="M {x} {yy} L {x + 5 * s} {yy}" stroke="{GREY2}" '
                   f'stroke-width="{1 * s}"/>')


def _board(x, y, s):
    out.append(f'<rect x="{x - 10 * s}" y="{y - 13 * s}" width="{20 * s}" height="{14 * s}" '
               f'rx="{1.5 * s}" fill="#3F6B57" stroke="{OCHRE}" stroke-width="{1.5 * s}"/>')
    out.append(f'<path d="M {x - 6 * s} {y - 9 * s} L {x + 4 * s} {y - 9 * s} M {x - 6 * s} '
               f'{y - 5 * s} L {x + 1 * s} {y - 5 * s}" stroke="#FFFFFF" '
               f'stroke-width="{1 * s}"/>')
    out.append(f'<path d="M {x - 6 * s} {y + 1 * s} L {x - 8 * s} {y + 6 * s} M {x + 6 * s} '
               f'{y + 1 * s} L {x + 8 * s} {y + 6 * s}" stroke="{OCHRE}" '
               f'stroke-width="{1.3 * s}"/>')


def _book(x, y, s):
    out.append(f'<path d="M {x} {y - 10 * s} Q {x - 6 * s} {y - 13 * s} {x - 11 * s} '
               f'{y - 11 * s} L {x - 11 * s} {y + 2 * s} Q {x - 6 * s} {y} {x} {y + 3 * s} '
               f'Q {x + 6 * s} {y} {x + 11 * s} {y + 2 * s} L {x + 11 * s} {y - 11 * s} '
               f'Q {x + 6 * s} {y - 13 * s} {x} {y - 10 * s} Z" fill="#FFFFFF" '
               f'stroke="{CORAL}" stroke-width="{1.3 * s}"/>')
    out.append(f'<path d="M {x} {y - 10 * s} L {x} {y + 3 * s}" stroke="{CORAL}" '
               f'stroke-width="{1 * s}"/>')


def _calendar(x, y, s):
    out.append(f'<rect x="{x - 9 * s}" y="{y - 12 * s}" width="{18 * s}" height="{16 * s}" '
               f'rx="{2 * s}" fill="#FFFFFF" stroke="{SLATE}" stroke-width="{1.3 * s}"/>')
    out.append(f'<rect x="{x - 9 * s}" y="{y - 12 * s}" width="{18 * s}" height="{4.5 * s}" '
               f'rx="{2 * s}" fill="{CORAL}"/>')
    for i in range(3):
        for j in range(2):
            out.append(f'<circle cx="{x - 5 * s + i * 5 * s}" cy="{y - 3.5 * s + j * 4.5 * s}" '
                       f'r="{1 * s}" fill="{SLATE}"/>')


def _pencil(x, y, s):
    out.append(f'<path d="M {x - 6 * s} {y + 4 * s} L {x + 6 * s} {y - 9 * s}" '
               f'stroke="#F2B544" stroke-width="{3.2 * s}" stroke-linecap="round"/>')
    out.append(f'<path d="M {x - 6 * s} {y + 4 * s} L {x - 7.5 * s} {y + 6 * s}" '
               f'stroke="{INK}" stroke-width="{1.4 * s}" stroke-linecap="round"/>')


PROPS = {"magnifier": _magnifier, "target": _target, "clipboard": _clipboard,
         "board": _board, "book": _book, "calendar": _calendar, "pencil": _pencil}


# ── the harness ring and the alignment graph inside it ──────────────────────
rect("harness", 350, 196, 540, 318, fill=HARNESS_FILL, stroke=SLATE, sw=2.0, r=28)
text(620, 214, ["KHUNG ĐIỀU PHỐI"], fs=11, fc=SLATE)
chip(372, 228, 128, "công cụ đọc trạng thái")
chip(556, 228, 128, "kiểm tra lượt nộp")
chip(740, 228, 128, "ghi nút + cạnh có kiểu")
chip(372, 482, 128, "kiểm tra tất định", color=BRICK, fill=BRICK_FILL)
chip(556, 482, 128, "sửa cấu trúc", color=BRICK, fill=BRICK_FILL)
chip(740, 482, 128, "sổ vi phạm", color=BRICK, fill=BRICK_FILL)

rect("graph", 410, 262, 420, 210, fill=BAND_FILL, stroke=OCHRE, sw=1.8, r=14)
text(620, 279, ["ĐỒ THỊ CĂN CHỈNH (trạng thái dùng chung)"], fs=10.5, fc=OCHRE)
box("g_act", 440, 298, 96, 28, ["Hoạt động"], fill="#FFFFFF", stroke=OCHRE, fs=10)
box("g_asm", 440, 412, 96, 28, ["Bài đánh giá"], fill="#FFFFFF", stroke=OCHRE, fs=10)
box("g_obj", 574, 354, 88, 32, ["Mục tiêu"], fill="#FFFFFF", stroke=SLATE, fs=10.5)
box("g_mod", 728, 298, 76, 28, ["Mô-đun"], fill=BAND_FILL, stroke=SEC, fs=10)
box("g_mat", 728, 412, 76, 28, ["Học liệu"], fill=BAND_FILL, stroke=SEC, fs=10)
edge(pt("g_obj", 0.1, 0.0), pt("g_act", 1.0, 0.75), color=OCHRE, sw=1.8,
     label="C3", ldx=-2, ldy=-4)
edge(pt("g_obj", 0.1, 1.0), pt("g_asm", 1.0, 0.25), color=OCHRE, sw=1.8,
     label="C2", ldx=-2, ldy=14)
edge(pt("g_act", 0.35, 1.0), pt("g_asm", 0.35, 0.0), color=OCHRE, sw=1.8,
     label="C4", ldx=6, ldy=4, lanchor="start")
edge(pt("g_mod", 0.0, 0.8), pt("g_obj", 1.0, 0.2), color=SEC, sw=1.1,
     label="P12", ldx=6, ldy=-2, lanchor="start")
edge(pt("g_mod", 0.5, 1.0), pt("g_mat", 0.5, 0.0), color=SEC, sw=1.1,
     label="P5", ldx=5, ldy=4, lanchor="start")
text(820, 462, ["+ 12 quan hệ phụ"], fs=8.5, bold=False, fc=SEC, anchor="end")

# ── turn order: the agents sit on an ellipse, 1 -> 6 clockwise ───────────────
CX, CY, RX, RY = 620, 355, 505, 292
ANGLES = [208, 270, 332, 28, 90, 152]


def on_ring(deg):
    a = math.radians(deg)
    return (CX + RX * math.cos(a), CY + RY * math.sin(a))


for a0, a1 in zip(ANGLES, ANGLES[1:]):
    a1 = a1 + 360 if a1 < a0 else a1
    s, e = on_ring(a0 + 14), on_ring(a1 - 14)
    out.append(f'<path d="M {s[0]:.1f} {s[1]:.1f} A {RX} {RY} 0 0 1 {e[0]:.1f} {e[1]:.1f}" '
               f'fill="none" stroke="{GREEN}" stroke-width="1.5" stroke-dasharray="6 4" '
               f'marker-end="url(#a-{GREEN[1:]})"/>')

# ── the six agents ──────────────────────────────────────────────────────────
AGENTS = [
    ("a1", "Phân tích nhu cầu", ["khoảng trống, chủ đề,", "ràng buộc, người học"],
     "magnifier", None),
    ("a2", "Thiết kế mục tiêu", ["mục tiêu học tập,", "mô-đun"], "target", None),
    ("a3", "Thiết kế đánh giá", ["blueprint, bài đánh giá"], "clipboard", "right"),
    ("a4", "Thiết kế hoạt động", ["hoạt động dạy – học"], "board", "right"),
    ("a5", "Thiết kế học liệu", ["phương tiện, học liệu"], "book", "right"),
    ("a6", "Lập kế hoạch triển khai", ["phiếu buổi học,", "hướng dẫn"], "calendar",
     "left"),
]
CW, CH = 236, 78
for i, ((aid, role, owns, prop, devs), deg) in enumerate(zip(AGENTS, ANGLES), start=1):
    cx, cy = on_ring(deg)
    x, y = cx - CW / 2, cy - CH / 2
    rect(aid, x, y, CW, CH, fill="#FFFFFF", stroke=SLATE, sw=1.5, r=14)
    robot(x + 34, y + 32, 1.1, prop=prop)
    text(x + 90, y + 26, [role], fs=10.5, anchor="start")
    for k, line in enumerate(owns):
        text(x + 90, y + 44 + k * 12, [line], fs=8.6, bold=False, fc=GREY, anchor="start")
    out.append(f'<circle cx="{x + 4}" cy="{y + 4}" r="10" fill="{GREEN}"/>')
    text(x + 4, y + 4, [str(i)], fs=10, fc="#FFFFFF")

    if devs:   # Developers: one work set each, same act-observe loop, same harness
        dx = x + CW + 26 if devs == "right" else x - 26
        for k, ddx in enumerate((-10, 12)):
            robot(dx + ddx * (1 if devs == "right" else -1), y + 20 + k * 30, 0.55,
                  accent=GREY2, prop="pencil")
        text(dx, y + CH + 14, ["Developer"], fs=8, bold=False, fc=SLATE, italic=True)

    # one spoke = one act-observe loop with the HARNESS (never with the graph)
    h = centre("harness")
    a_edge = boundary(aid, h, pad=2)
    h_edge = boundary("harness", (cx, cy), pad=2)
    curve(a_edge, h_edge, bend=20, color=SLATE, sw=1.7)                 # act
    curve(h_edge, a_edge, bend=20, color=OCHRE, sw=1.7, dash=True)      # observe

text(587, 150, ["act"], fs=9.5, fc=SLATE, anchor="end", italic=True)
text(653, 150, ["observe"], fs=9.5, fc=OCHRE, anchor="start", italic=True)

# a repair turn goes back to the agent that owns the violation
edge(pt("chip_kiểm tra tất định", 0.15, 1.0),
     boundary("a6", pt("chip_kiểm tra tất định", 0.15, 1.0), pad=4),
     color=BRICK, sw=1.3, dash=True, label="lượt sửa", ldx=-6, ldy=-4,
     lanchor="end")

# ── zoom: one loop, turn by turn (agent 3) ───────────────────────────────────
TURNS = [("act", "▸ read_alignment_state()"),
         ("obs", "◂ [MISSING] ILO-002: chưa có bài đánh giá"),
         ("act", "▸ submit_assessment_plan({…})"),
         ("obs", "◂ SUBMIT REJECTED: thiếu \"timing\""),
         ("act", "▸ submit_assessment_plan({…})"),
         ("obs", "◂ COMMITTED: ghi nút + cạnh")]
box("zoom", 1132, 22, 262, 128, [], fill="#FFFFFF", stroke=GREY2, sw=1.0, r=6)
text(1142, 36, ["Một vòng act–observe (tác tử 3)"], fs=9, fc=GREY, anchor="start")
for k, (kind, line) in enumerate(TURNS):
    color = SLATE if kind == "act" else OCHRE
    out.append(f'<text x="1142" y="{56 + k * 16}" font-family="{MONO}" font-size="8.6" '
               f'fill="{color}">{line}</text>')
edge(pt("a3", 0.9, 0.0), pt("zoom", 0.1, 1.0), color=GREY2, sw=1.0, dash=True,
     head=False)

# ── input and outputs ───────────────────────────────────────────────────────
box("brief", 10, 326, 104, 58, ["Bản mô tả", "thiết kế"], fill=GREY_FILL,
    stroke=GREY2, fs=10.5)
edge(pt("brief", 1.0, 0.5), pt("harness", 0.0, 0.5), color=GREY, sw=1.6,
     label="giao lượt 1→6", ldy=-8)
text(232, 372, ["(Backward Design)"], fs=9, bold=False, fc=GREEN, italic=True)

box("out_audit", 1250, 268, 144, 56, ["graph.json", "+ sổ vi phạm"],
    fill=GREY_FILL, stroke=GREY2, fs=10.5)
box("out_addie", 1250, 390, 144, 56, ["Đầu ra ADDIE", "(5 pha)"],
    fill=GREY_FILL, stroke=GREY2, fs=10.5)
edge(pt("harness", 1.0, 0.36), pt("out_audit", 0.0, 0.5), color=GREY, sw=1.6,
     label="đối chiếu · kiểm toán", ldy=-6)
edge(pt("harness", 1.0, 0.64), pt("out_addie", 0.0, 0.5), color=GREY, sw=1.6,
     label="tổng hợp", ldy=16)

# ── legend ──────────────────────────────────────────────────────────────────
LY = 720
curve((40, LY), (80, LY), bend=0.01, color=SLATE, sw=1.7)
text(86, LY, ["act: tác tử gọi công cụ của khung điều phối (đọc, nộp)"], fs=9,
     bold=False, anchor="start")
curve((450, LY), (490, LY), bend=0.01, color=OCHRE, sw=1.7, dash=True)
text(496, LY, ["observe: kết quả trả về (trạng thái, COMMITTED, lỗi)"], fs=9,
     bold=False, anchor="start")
edge((850, LY), (890, LY), color=GREEN, sw=1.5, dash=True)
text(896, LY, ["thứ tự lượt"], fs=9, bold=False, anchor="start")
edge((1000, LY), (1040, LY), color=BRICK, sw=1.3, dash=True)
text(1046, LY, ["lượt sửa"], fs=9, bold=False, anchor="start")

X0, Y0, X1, Y1 = 0, 14, 1404, 734
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth">'
    f'<path d="M 0 0 L 7 3 L 0 6 z" fill="{c}"/></marker>'
    for c in (SLATE, OCHRE, SEC, BRICK, GREY, GREEN, GREY2))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
       f'width="{X1 - X0}px" height="{Y1 - Y0}px" '
       f'viewBox="{X0} {Y0} {X1 - X0} {Y1 - Y0}">'
       f'<defs>{defs}</defs>' + "".join(out) + "</svg>")
out_path = Path(__file__).with_name("architecture_vi.svg")
out_path.write_text(svg)
print("wrote", out_path, len(svg), "bytes")
