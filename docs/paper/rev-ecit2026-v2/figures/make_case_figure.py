"""Compose Hình 2, 3 and 4 from the web-app screenshots taken by case/shoot_app.py.

  case.png         Hình 2: (a) the Trajectory tab -- the stages in order, with their
                   agents and what each submitted; (b) the Graph tab, Alignment
                   layer, objective ILO-01 selected
  case_outputs.png Hình 3: three output artifacts with their relations -- (a) a
                   learning material, (b) a learning activity, (c) an assessment item
                   of task AT-02 with its question and rubric, under the task's own node header and
                   relations (the task's other fields are elided, marked by a dotted band)
  case_audit.png   Hình 4: (a) ILO-04's details -- the constructive-alignment legs;
                   (b) the Violations tab -- the ledger, open and repaired

The crop boxes are in screenshot pixels (2x, 3200x2300) and follow the app's fixed
layout at a 1600x1150 viewport: sidebar 0-640, main panel 640-2240, details 2240-3200.
Each panel gets its label in a strip above it, so no label covers the interface.

Build: python3 make_case_figure.py  (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 48)
GAP, STRIP = 48, 70
BORDER = (150, 160, 170)


def compose(panels: list[tuple[str, Image.Image]], out: str) -> None:
    """Panels side by side, top-aligned, each under its label strip."""
    W = sum(p.width for _, p in panels) + GAP * (len(panels) - 1) + 8
    H = STRIP + max(p.height for _, p in panels) + 8
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    x = 4
    for label, img in panels:
        draw.text((x, 6), f"({label})", font=FONT, fill=(31, 35, 40))
        canvas.paste(img, (x, STRIP))
        draw.rectangle([x - 1, STRIP - 1, x + img.width, STRIP + img.height],
                       outline=BORDER, width=3)
        x += img.width + GAP
    canvas.save(HERE / out)
    print("wrote", HERE / out, canvas.size)


def elided(top: Image.Image, bottom: Image.Image) -> Image.Image:
    """Two cuts of one panel stacked, with a band marking what was left out between them."""
    band = 44
    out = Image.new("RGB", (top.width, top.height + band + bottom.height), "white")
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height + band))
    d = ImageDraw.Draw(out)
    y = top.height + band // 2
    d.line([(16, y), (top.width - 16, y)], fill=BORDER, width=2)
    d.rectangle([top.width // 2 - 40, y - 16, top.width // 2 + 40, y + 16], fill="white")
    for k in (-20, 0, 20):
        d.ellipse([top.width // 2 + k - 5, y - 5, top.width // 2 + k + 5, y + 5], fill=BORDER)
    return out


trajectory = Image.open(HERE / "case_trajectory.png").convert("RGB")
graph = Image.open(HERE / "case_graph.png").convert("RGB")
inspector = Image.open(HERE / "case_inspector.png").convert("RGB")

compose([("a", trajectory.crop((640, 220, 2240, 2160))),   # agents and the stage list
         ("b", graph.crop((640, 230, 2240, 2240)))],       # graph, from the layer filters
        "case.png")
activity = Image.open(HERE / "case_activity.png").convert("RGB")
material = Image.open(HERE / "case_material.png").convert("RGB")
violations = Image.open(HERE / "case_violations.png").convert("RGB")

compose([("a", material.crop((2240, 100, 3200, 1190))),     # MAT-0101: relations, content
         ("b", activity.crop((2240, 100, 3200, 1400))),     # TLA-0102: relations, content
         ("c", elided(inspector.crop((2240, 100, 3200, 780)),      # AT-02: node, relations
                      inspector.crop((2240, 1300, 3200, 2058))))],  # its item 1: question, rubric
        "case_outputs.png")
compose([("a", graph.crop((2240, 100, 3200, 610))),         # ILO-04: the alignment legs
         ("b", violations.crop((640, 230, 2240, 1040)))],    # the ledger: open, repaired
        "case_audit.png")
