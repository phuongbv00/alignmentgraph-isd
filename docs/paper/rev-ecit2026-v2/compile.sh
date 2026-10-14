#!/usr/bin/env bash
# Compile main.tex: xelatex -> bibtex -> xelatex -> xelatex.
# XeLaTeX because the Vietnamese text needs a font with full diacritic coverage.
# Run from anywhere; the script cd's into its own directory.
set -euo pipefail

cd "$(dirname "$0")"

TINYTEX_BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
if [ -d "$TINYTEX_BIN" ]; then
  export PATH="$TINYTEX_BIN:$PATH"
fi

# A pass may exit non-zero on an error the next pass resolves (an empty .bbl
# before bibtex has run), so only the final log decides.
xelatex -interaction=nonstopmode main.tex >/dev/null || true
bibtex main || true
xelatex -interaction=nonstopmode main.tex >/dev/null || true
xelatex -interaction=nonstopmode main.tex >/dev/null || true

if grep -n '^!' main.log; then
  echo "LaTeX errors above (see main.log)." >&2
  exit 1
fi

echo
echo "Done. Output: $(pwd)/main.pdf ($(pdfinfo main.pdf 2>/dev/null | awk '/^Pages/{print $2}') pages, limit 6)"
