"""Render figures/architecture_band.svg: Hình 1, following the conventions of the
multi-agent papers reviewers know (survey 2026-10-13):

* the fixed order as a left-to-right chain of role chips (ChatDev, Instructional
  Agents), one uniform agent glyph, the active one highlighted;
* a full-width harness band and ONE agent's act/observe pair in two colours
  (SWE-agent's agent-computer interface, ReAct's actions/observations);
* the shared state as the single central object below it (blackboard papers),
  reached only through the harness;
* outputs on the right. Developers are a stacked shadow; relation ids beyond
  the triad, budgets and repair logic are left to the text.

Every label is >= 16 px, i.e. >= 7 pt once the 1150 px canvas is set at 18 cm.

Build: python3 make_architecture_band.py && rsvg-convert -f pdf -o architecture_band.pdf architecture_band.svg
"""
from pathlib import Path

SLATE, SLATE_FILL = "#3E5F7E", "#EAEFF4"
OCHRE, BAND_FILL = "#B5652B", "#FBF5EE"   # observation / state colour
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


def arrow(x0, y0, x1, y1, *, color=SLATE, sw=2.2, dash=False):
    d = ' stroke-dasharray="6 4"' if dash else ""
    out.append(f'<path d="M {x0} {y0} L {x1} {y1}" stroke="{color}" stroke-width="{sw}" '
               f'fill="none"{d} marker-end="url(#a-{color[1:]})"/>')


def chevron(x, y, color=MUTED):
    out.append(f'<path d="M {x} {y - 7} L {x + 8} {y} L {x} {y + 7}" stroke="{color}" '
               f'stroke-width="2.4" fill="none" stroke-linecap="round" '
               f'stroke-linejoin="round"/>')


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


# ── top: input and the six roles in their fixed order ───────────────────────
rect(8, 22, 122, 50, fill=GREY_FILL, stroke=GREY)
text(69, 38, "Bản mô tả", fs=16, bold=True)
text(69, 58, "thiết kế", fs=16, bold=True)
arrow(130, 47, 152, 47, color=GREY)

ROLES = ["Phân tích", "Mục tiêu", "Đánh giá", "Hoạt động", "Học liệu", "Triển khai"]
ACTIVE = 2
X0, CW, GAP, CY = 158, 136, 22, 24
centres = []
for k, name in enumerate(ROLES):
    x = X0 + k * (CW + GAP)
    on = k == ACTIVE
    if k >= 2:                                     # Developer tier: stacked shadow
        for d in (8, 4):
            rect(x + d, CY + d, CW, 46, fill="#FFFFFF",
                 stroke=SLATE if on else MUTED, sw=1.0, r=12)
    rect(x, CY, CW, 46, fill=SLATE if on else "#FFFFFF",
         stroke=SLATE if on else MUTED, sw=1.8 if on else 1.3, r=12)
    glyph(x + 22, CY + 25, on=on)
    text(x + 40, CY + 23, f"{k + 1} {name}", fs=16, bold=on,
         fc="#FFFFFF" if on else GREY, anchor="start")
    centres.append(x + CW / 2)
    if k < len(ROLES) - 1:
        chevron(x + CW + 8 + (6 if k >= 2 else 0), CY + 23)

# ── the active agent's act / observe pair, into the harness band ─────────────
AX = centres[ACTIVE]
arrow(AX - 14, 80, AX - 14, 124, color=SLATE)
arrow(AX + 14, 124, AX + 14, 80, color=OCHRE, dash=True)
text(AX - 24, 102, "gọi công cụ", fs=16, fc=SLATE, anchor="end")
text(AX + 24, 102, "quan sát", fs=16, fc=OCHRE, anchor="start")

# ── the harness band ────────────────────────────────────────────────────────
rect(158, 128, 945, 46, fill=SLATE_FILL, stroke=SLATE, sw=2.0, r=12)
text(452, 151, "Khung điều phối", fs=17, bold=True, fc=SLATE, anchor="end")
text(462, 151, "kiểm tra lượt nộp  ·  ghi nút  ·  dựng cạnh  ·  kiểm tra tất định",
     fs=16, fc=SLATE, anchor="start")

# ── harness <-> the shared state ─────────────────────────────────────────────
GX = 630
arrow(GX - 14, 176, GX - 14, 210, color=SLATE)
arrow(GX + 14, 210, GX + 14, 176, color=OCHRE, dash=True)
text(GX - 24, 193, "ghi", fs=16, fc=SLATE, anchor="end")
text(GX + 24, 193, "đọc", fs=16, fc=OCHRE, anchor="start")

# ── the alignment graph: the triad, other node types faint ──────────────────
rect(455, 214, 350, 172, fill=BAND_FILL, stroke=TRIAD, sw=2.0, r=16)
text(630, 236, "Đồ thị căn chỉnh", fs=18, bold=True, fc=TRIAD)
for fx, fy in ((488, 262), (480, 352), (778, 262), (782, 352), (630, 372)):
    out.append(f'<circle cx="{fx}" cy="{fy}" r="7" fill="#FFFFFF" stroke="{MUTED}" '
               f'stroke-width="1.3"/>')
out.append(f'<path d="M 495 262 L 572 278 M 487 348 L 558 343 M 771 262 L 688 278 '
           f'M 775 352 L 702 343" stroke="{MUTED}" stroke-width="1.1" fill="none"/>')


def node(cx, cy, label, w):
    rect(cx - w / 2, cy - 16, w, 32, fill="#FFFFFF", stroke=TRIAD, sw=1.6, r=8)
    text(cx, cy, label, fs=16, bold=True)


node(630, 276, "Mục tiêu", 100)
node(560, 344, "Hoạt động", 104)
node(700, 344, "Đánh giá", 92)
arrow(610, 293, 578, 326, color=TRIAD)
arrow(650, 293, 682, 326, color=TRIAD)
arrow(613, 344, 652, 344, color=TRIAD)
text(578, 302, "C3", fs=16, bold=True, fc=TRIAD)
text(684, 302, "C2", fs=16, bold=True, fc=TRIAD)
text(632, 326, "C4", fs=16, bold=True, fc=TRIAD)

# ── outputs ─────────────────────────────────────────────────────────────────
arrow(807, 262, 893, 262, color=GREY)
arrow(807, 340, 893, 340, color=GREY)
rect(896, 238, 207, 48, fill=GREY_FILL, stroke=GREY)
text(1000, 262, "Bản thiết kế ADDIE", fs=16, bold=True)
rect(896, 316, 207, 48, fill=GREY_FILL, stroke=GREY)
text(1000, 340, "Đồ thị + sổ vi phạm", fs=16, bold=True)

W, H = 1112, 394
defs = "".join(
    f'<marker id="a-{c[1:]}" markerWidth="7" markerHeight="7" refX="6.2" refY="3" '
    f'orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 7 3 L 0 6 z" '
    f'fill="{c}"/></marker>' for c in (SLATE, OCHRE, GREY, TRIAD))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}px" '
       f'height="{H}px" viewBox="0 0 {W} {H}"><defs>{defs}</defs>'
       + "".join(out) + "</svg>")
path = Path(__file__).with_name("architecture_band.svg")
path.write_text(svg)
print("wrote", path)
