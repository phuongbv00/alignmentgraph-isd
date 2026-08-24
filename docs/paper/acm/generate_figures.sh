#!/usr/bin/env bash
# Build the paper's figure PDFs from their SVG sources.
#
# The SVG is the versioned source -- exported from the matching figures/*.drawio
# (see figures/README.md) or written by hand. The PDF is a gitignored build
# artifact; main.tex \includegraphics the PDF, never the SVG.
#
# Usage:
#   ./generate_figures.sh                    # every figures/*.svg -> figures/*.pdf
#   ./generate_figures.sh architecture       # figures/architecture.svg -> .pdf
#   ./generate_figures.sh figures/foo.svg    # explicit path (absolute or relative)
#
# A draw.io export stores labels as HTML inside <foreignObject>, which no SVG
# renderer draws; drawio_labels.py rewrites them as native SVG <text> first, on a
# temporary copy, so the committed SVG stays exactly as draw.io wrote it.
# Renderer: rsvg-convert (brew install librsvg); override with RSVG_CONVERT=... .
set -euo pipefail

call_dir="$(pwd)"
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

find_cmd() {
  local candidate
  for candidate in "$@"; do
    [ -x "$candidate" ] && { printf '%s\n' "$candidate"; return 0; }
    command -v "$candidate" >/dev/null 2>&1 && { command -v "$candidate"; return 0; }
  done
  return 1
}

resolve_svg() {
  case "$1" in
    /*)    printf '%s\n' "$1" ;;
    *.svg) if [ -e "$call_dir/$1" ]; then printf '%s/%s\n' "$call_dir" "$1"
           else printf '%s/%s\n' "$script_dir" "$1"; fi ;;
    *)     printf '%s/figures/%s.svg\n' "$script_dir" "$1" ;;
  esac
}

rsvg_bin="${RSVG_CONVERT:-$(find_cmd /opt/homebrew/bin/rsvg-convert /usr/local/bin/rsvg-convert rsvg-convert 2>/dev/null || true)}"
[ -n "$rsvg_bin" ] || die "rsvg-convert not found. Install it: brew install librsvg"
xmllint_bin="$(find_cmd xmllint 2>/dev/null || true)"
pdfinfo_bin="$(find_cmd pdfinfo 2>/dev/null || true)"

svgs=()
if [ "$#" -eq 0 ]; then
  while IFS= read -r f; do svgs+=("$f"); done \
    < <(find "$script_dir/figures" -maxdepth 1 -name '*.svg' | sort)
  [ "${#svgs[@]}" -gt 0 ] || die "no SVG files in $script_dir/figures"
else
  for arg in "$@"; do svgs+=("$(resolve_svg "$arg")"); done
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
failed=0

for svg in "${svgs[@]}"; do
  [ -f "$svg" ] || die "missing input: $svg"
  name="$(basename "$svg" .svg)"
  pdf="${svg%.svg}.pdf"
  src="$svg"
  echo "==> $name"

  if [ -n "$xmllint_bin" ]; then
    "$xmllint_bin" --noout "$svg" || die "$name: malformed SVG (a truncated export?)"
  fi

  if grep -q -e '<foreignObject' -e 'svg-export-text-problems' "$svg"; then
    src="$tmp_dir/$name.svg"
    python3 "$script_dir/drawio_labels.py" "$svg" "$src" || die "$name: label conversion failed"
    ! grep -q '<foreignObject' "$src" \
      || die "$name: some labels are still HTML. Simplify them in draw.io (plain text, no tables or lists) and re-export."
  fi

  rm -f "$pdf"
  "$rsvg_bin" -f pdf -o "$pdf" "$src"

  if [ ! -s "$pdf" ]; then
    echo "  FAILED: no PDF produced" >&2; failed=1; continue
  fi
  size_bytes=$(wc -c < "$pdf" | tr -d ' ')
  if [ -n "$pdfinfo_bin" ]; then
    pages="$("$pdfinfo_bin" "$pdf" | awk -F: '/^Pages:/ {gsub(/^[ \t]+/,"",$2); print $2}')"
    dims="$("$pdfinfo_bin" "$pdf" | awk -F: '/^Page size:/ {gsub(/^[ \t]+/,"",$2); print $2}')"
    if [ "${pages:-0}" != "1" ]; then
      echo "  FAILED: expected 1 page, got ${pages:-0}" >&2; failed=1; continue
    fi
    echo "  $(basename "$pdf"): 1 page, $dims, $size_bytes bytes"
  else
    echo "  $(basename "$pdf"): $size_bytes bytes"
  fi
  [ "$size_bytes" -ge 3000 ] || echo "  warning: unusually small PDF -- check it is not blank" >&2
done

[ "$failed" -eq 0 ] || die "one or more figures failed"
echo "Done. Run ./compile.sh to rebuild main.pdf."
