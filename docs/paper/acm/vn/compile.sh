#!/usr/bin/env bash
# Compile the Vietnamese paper (vn/main.tex): xelatex -> bibtex -> xelatex -> xelatex.
# Needs xelatex (not pdflatex) for Vietnamese diacritics via acmart's libertine fonts + polyglossia.
# Shared assets (acmart.cls, ACM-Reference-Format.bst, references.bib, figures/) live in the
# parent acm/ directory and are found via TEXINPUTS/BIBINPUTS/BSTINPUTS pointing at "..".
# Run from anywhere; the script cd's into its own directory.
set -euo pipefail

cd "$(dirname "$0")"

# Prepend TinyTeX to PATH if it exists and isn't already there.
TINYTEX_BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
if [ -d "$TINYTEX_BIN" ]; then
  export PATH="$TINYTEX_BIN:$PATH"
fi

# Resolve shared class/style/bib from the parent acm/ directory.
export TEXINPUTS=".:..:${TEXINPUTS:-}"
export BIBINPUTS=".:..:${BIBINPUTS:-}"
export BSTINPUTS=".:..:${BSTINPUTS:-}"

xelatex -interaction=nonstopmode main.tex
bibtex main
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex

echo
echo "Done. Output: $(pwd)/main.pdf"
