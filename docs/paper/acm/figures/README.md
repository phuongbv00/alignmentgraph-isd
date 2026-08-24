# Figures

| file | role |
|---|---|
| `architecture.drawio` | **editable master** — open at <https://app.diagrams.net> or in the draw.io desktop app |
| `architecture.svg` | versioned build source, exported from the `.drawio` |
| `architecture.pdf` | build artifact, gitignored; this is what `main.tex` includes |

## Editing loop

1. Edit `architecture.drawio` in draw.io.
2. *File → Export as → SVG…*, save over `architecture.svg`. Default settings are
   fine — leave "Include a copy of my diagram" **on** so the SVG stays editable,
   and do not worry about the "text problems" warning (see below).
3. From `docs/paper/acm/`:

   ```bash
   ./generate_figures.sh architecture && ./compile.sh
   ```

`generate_figures.sh` converts every `figures/*.svg` to a one-page PDF with
`rsvg-convert`. draw.io stores labels as HTML inside `<foreignObject>`, which no
SVG renderer draws, so the script first runs `drawio_labels.py` on a **temporary
copy** to rewrite those labels as native SVG `<text>` (keeping per-line font size
and weight) and to drop draw.io's "Text is not SVG" notice. The committed SVG is
never modified.

If the script reports labels it could not convert, simplify them in draw.io —
plain text and line breaks convert; tables, lists and nested formatting do not.

## What the figure has to stay consistent with

Every box, arrow and relation label in Figure 1 is meant to be traceable to
Algorithm 1 in `sections/04_method.tex`, to `core/nodes.py:build_graph`, and to
the relation registry in `core/alignment.py` (only R1–R13 exist; `implementation_plan`
participates in none of them). Check the caption after moving or deleting anything.

Palette (desaturated, print-safe): slate `#3E5F7E` for agents and process steps,
ochre `#8A6A3B` for the alignment graph and its relations, brick `#8C4B47` for
verify/repair, greys `#6B7480` / `#7C848E` / `#F2F3F4` for everything else.
