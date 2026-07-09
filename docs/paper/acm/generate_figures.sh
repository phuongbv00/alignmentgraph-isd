#!/usr/bin/env bash
# Generate paper figure assets.
# Default: figures/architecture.html -> figures/architecture.svg -> figures/architecture.pdf
# Usage:
#   ./generate_figures.sh
#   ./generate_figures.sh architecture
#   ./generate_figures.sh figures/architecture.html
#   ./generate_figures.sh figures/architecture.svg
set -euo pipefail

call_dir="$(pwd)"
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

find_cmd() {
  local candidate
  for candidate in "$@"; do
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

figure="${1:-architecture}"

resolve_arg_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *)
      if [ -e "$call_dir/$1" ]; then
        printf '%s/%s\n' "$call_dir" "$1"
      else
        printf '%s/%s\n' "$script_dir" "$1"
      fi
      ;;
  esac
}

case "$figure" in
  *.html)
    html="$(resolve_arg_path "$figure")"
    base="${html%.html}"
    svg="$base.svg"
    ;;
  *.svg)
    html=""
    svg="$(resolve_arg_path "$figure")"
    base="${svg%.svg}"
    ;;
  *)
    base="$script_dir/figures/$figure"
    html="$base.html"
    svg="$base.svg"
    ;;
esac

pdf="$base.pdf"

if [ -n "$html" ] && [ -f "$html" ]; then
  echo "Extracting SVG from $html"
  perl -0ne 'if (/(<svg\b[\s\S]*<\/svg>)/) { print "$1\n"; $ok=1 } END { exit($ok ? 0 : 1) }' "$html" > "$svg"
  if xmllint="$(find_cmd xmllint 2>/dev/null)"; then
    "$xmllint" --noout "$svg" >/dev/null
  fi
elif [ ! -f "$svg" ]; then
  echo "Error: missing input. Expected $html or $svg" >&2
  exit 1
fi

rsvg_convert="${RSVG_CONVERT:-}"
if [ -z "$rsvg_convert" ]; then
  rsvg_convert="$(find_cmd /opt/homebrew/bin/rsvg-convert /usr/local/bin/rsvg-convert rsvg-convert)" || {
    echo "Error: rsvg-convert not found. Install librsvg, for example: brew install librsvg" >&2
    exit 1
  }
fi

echo "Generating PDF from $svg"
"$rsvg_convert" -f pdf -o "$pdf" "$svg"

if pdfinfo="$(find_cmd pdfinfo "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pdfinfo" 2>/dev/null)"; then
  pages="$("$pdfinfo" "$pdf" | awk -F: '/^Pages:/ { gsub(/^[ \t]+/, "", $2); print $2 }')"
  size="$("$pdfinfo" "$pdf" | awk -F: '/^Page size:/ { gsub(/^[ \t]+/, "", $2); print $2 }')"
  echo "Verified PDF: ${pages:-?} page(s), ${size:-unknown size}"
fi

echo "Done."
echo "SVG: $svg"
echo "PDF: $pdf"
