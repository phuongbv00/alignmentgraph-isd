"""Render figures/architecture_min.svg: the minimal Hình 1.

Four blocks, left to right, and nothing the text cannot carry instead:
agents (one holds the turn) <-> harness <-> alignment graph -> outputs.
Developers, repair turns and the ledger are described in Section III, not drawn.
Every label is at least 16 px, i.e. >= 7 pt once the 1150 px canvas is set at
18 cm.

Build: python3 make_architecture_min.py && rsvg-convert -f pdf -o architecture_min.pdf architecture_min.svg
"""
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
OCHRE, BAND_FILL = "#8A6A3B", "#F8F4EC"
GREY, GREY_FILL = "#6B7480", "#F2F3F4"
MUTED = "#9AA4AF"
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


def arrow(x0, y0, x1, y1, *, color=SLATE, sw=2.0, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    out.append(f'<path d="M {x0} {y0} L {x1} {y1}" stroke="{color}" stroke-width="{sw}" '
               f'fill="none"{d} marker-end="url(#a-{color[1:]})"/>')


def robot_head(cx, cy, *, active):
    """A small flat robot head: the agent icon."""
    stroke = "#FFFFFF" if active else SLATE
    out.append(f'<rect x="{cx - 11}" y="{cy - 9}" width="22" height="18" rx="6" '
               f'fill="#FFFFFF" stroke="{stroke}" stroke-width="1.4"/>')
    out.append(f'<rect x="{cx - 7.5}" y="{cy - 5.5}" width="15" height="10" rx="4" '
               f'fill="#24323F"/>')
    for dx in (-3.2, 3.2):
        out.append(f'<circle cx="{cx + dx}" cy="{cy - 0.5}" r="1.8" fill="#8FDCF5"/>')
    out.append(f'<path d="M {cx} {cy - 9} L {cx} {cy - 13}" stroke="{stroke}" '
               f'stroke-width="1.4"/>')
    out.append(f'<circle cx="{cx}" cy="{cy - 14.5}" r="2" fill="#E07A5F"/>')


# ── input ───────────────────────────────────────────────────────────────────
rect(10, 132, 118, 62, fill=GREY_FILL, stroke=GREY)
text(69, 151, "Bản mô tả", fs=16, bold=True)
text(69, 175, "thiết kế", fs=16, bold=True)
arrow(128, 163, 166, 163, color=GREY)

# ── agents: six, in turn; one holds the turn ────────────────────────────────
text(276, 24, "Tác tử, lần lượt 1 → 6", fs=16, bold=True, fc=SLATE)
AGENTS = ["Phân tích", "Mục tiêu", "Đánh giá", "Hoạt động", "Học liệu", "Triển khai"]
ACTIVE = 2
for k, name in enumerate(AGENTS):
    y = 46 + k * 40
    on = k == ACTIVE
    rect(172, y, 210, 32, fill=SLATE if on else "#FFFFFF",
         stroke=SLATE if on else MUTED, sw=1.6 if on else 1.2, r=16)
    robot_head(196, y + 17, active=on)
    text(220, y + 16, f"{k + 1}  {name}", fs=16, bold=on,
         fc="#FFFFFF" if on else GREY, anchor="start")

# ── act / observe between the active agent and the harness ──────────────────
AY = 46 + ACTIVE * 40 + 16
arrow(384, AY - 8, 486, AY - 8)
arrow(486, AY + 8, 384, AY + 8, color=OCHRE, dash=True)
text(435, AY - 24, "act", fs=16, fc=SLATE)
text(435, AY + 26, "observe", fs=16, fc=OCHRE)

# ── the harness ─────────────────────────────────────────────────────────────
rect(490, 92, 170, 150, fill=SLATE_FILL, stroke=SLATE, sw=2.0, r=14)
text(575, 140, "Khung điều phối", fs=18, bold=True, fc=SLATE)
text(575, 172, "kiểm tra, ghi,", fs=16, fc=SLATE)
text(575, 196, "báo vi phạm", fs=16, fc=SLATE)

# ── harness <-> graph ───────────────────────────────────────────────────────
arrow(662, 150, 716, 150)
arrow(716, 184, 662, 184, color=OCHRE, dash=True)
text(689, 132, "ghi", fs=16, fc=SLATE)
text(689, 204, "đọc", fs=16, fc=OCHRE)

# ── the alignment graph: the triad and nothing else ─────────────────────────
rect(720, 46, 250, 236, fill=BAND_FILL, stroke=OCHRE, sw=2.0, r=16)
text(845, 72, "Đồ thị căn chỉnh", fs=18, bold=True, fc=OCHRE)


def node(cx, cy, label, w=104):
    rect(cx - w / 2, cy - 17, w, 34, fill="#FFFFFF", stroke=OCHRE, sw=1.6, r=8)
    text(cx, cy, label, fs=16, bold=True)


node(845, 122, "Mục tiêu")
node(774, 238, "Hoạt động", w=98)
node(916, 238, "Đánh giá", w=92)
arrow(822, 139, 786, 219, color=OCHRE)          # C3
arrow(868, 139, 904, 219, color=OCHRE)          # C2
arrow(825, 238, 867, 238, color=OCHRE)          # C4
text(790, 172, "C3", fs=16, bold=True, fc=OCHRE)
text(900, 172, "C2", fs=16, bold=True, fc=OCHRE)
text(846, 220, "C4", fs=16, bold=True, fc=OCHRE)

# ── outputs ─────────────────────────────────────────────────────────────────
arrow(972, 128, 1010, 128, color=GREY)
arrow(972, 210, 1010, 210, color=GREY)
rect(1012, 100, 128, 56, fill=GREY_FILL, stroke=GREY)
text(1076, 128, "Đầu ra ADDIE", fs=16, bold=True)
rect(1012, 182, 128, 56, fill=GREY_FILL, stroke=GREY)
text(1076, 200, "Đồ thị +", fs=16, bold=True)
text(1076, 222, "sổ vi phạm", fs=16, bold=True)

W, H = 1150, 300
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}px" '
       f'height="{H}px" viewBox="0 0 {W} {H}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
path = Path(__file__).with_name("architecture_min.svg")
path.write_text(svg)
print("wrote", path)
