# Figures

| file | role |
|---|---|
| `architecture.drawio` | **editable master** — open at <https://app.diagrams.net> or in the draw.io desktop app |
| `make_architecture_svg.py` | writes `architecture.svg` from the same coordinates as the `.drawio`, for machines with no draw.io |
| `architecture.svg` | versioned build source |
| `architecture.pdf` | build artifact, gitignored; this is what `main.tex` includes |

## Editing loop

Two ways in, and they must not disagree — the `.drawio` and the generator carry the
same geometry, so a change made in one has to be mirrored in the other.

**Without draw.io** (how the 2026-09-10 rewrite was made): edit
`make_architecture_svg.py`, run it from this directory to rewrite
`architecture.svg`, mirror the same coordinates into `architecture.drawio`, then
build the PDF as below. The generator emits native SVG `<text>`, so the label
rewriting described further down does not apply to its output.

**With draw.io:**

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
Algorithm 1 in `sections/04_method.tex` and to the package itself:

- the six stage boxes and their order are `core/agentic/specialists.py::STEPS`;
- the `developers` chips are on exactly the stages that dispatch work sets;
- `check · repair` is on exactly the stages that own checks — `analysis` owns none,
  see `core/repairs.py::OWNED_BY_FAMILY`;
- every relation label is a key of `core/alignment_graph/alignment.py::REGISTRY`,
  drawn in the direction that registry gives it. C2 and C3 are *id-reverse*: the
  objective is the edge SOURCE even though the assessment task and the activity are
  the artifacts that declare the reference;
- the three heavy edges C2, C3, C4 are the triad of `eq:aligned`, and the note in
  the band accounts for every relation not drawn (17 total: C2–C4 and P1–P14).

Check the caption after moving or deleting anything.

Palette (desaturated, print-safe): slate `#3E5F7E` for agents and process steps,
ochre `#8A6A3B` for the alignment graph and its relations, brick `#8C4B47` for
verify/repair, greys `#6B7480` / `#7C848E` / `#F2F3F4` for everything else.
