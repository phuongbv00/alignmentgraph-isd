#!/usr/bin/env bash
# Compile main.tex: pdflatex -> bibtex -> pdflatex -> pdflatex.
# Run from anywhere; the script cd's into its own directory.
set -euo pipefail

cd "$(dirname "$0")"

# Prepend TinyTeX to PATH if it exists and isn't already there.
TINYTEX_BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
if [ -d "$TINYTEX_BIN" ]; then
  export PATH="$TINYTEX_BIN:$PATH"
fi

pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex

echo
echo "Done. Output: $(pwd)/main.pdf"
