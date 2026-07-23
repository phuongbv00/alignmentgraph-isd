#!/usr/bin/env bash
# Xuất slide deck HTML trong docs/slides/ ra PDF bằng headless Chrome (macOS).
#
# Cách dùng:
#   docs/scripts/gen_slides_pdf_macos.sh                # convert mọi *.html trong docs/slides/
#   docs/scripts/gen_slides_pdf_macos.sh <file.html>... # chỉ convert các file được chỉ định
#
# PDF được ghi cạnh file HTML, cùng tên (foo.html -> foo.pdf).
# Deck phải tự khai báo @page/@media print (các deck trong repo này đã có).
set -euo pipefail

SLIDES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../slides" && pwd)"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [[ ! -x "$CHROME" ]]; then
  echo "ERROR: không tìm thấy Google Chrome tại: $CHROME" >&2
  echo "Cài Chrome hoặc sửa biến CHROME trong script." >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  targets=("$@")
else
  targets=("$SLIDES_DIR"/*.html)
fi

if [[ ${#targets[@]} -eq 0 || ! -e "${targets[0]}" ]]; then
  echo "Không có file HTML nào trong $SLIDES_DIR" >&2
  exit 1
fi

for html in "${targets[@]}"; do
  if [[ ! -f "$html" ]]; then
    echo "ERROR: không tìm thấy file: $html" >&2
    exit 1
  fi
  abs="$(cd "$(dirname "$html")" && pwd)/$(basename "$html")"
  pdf="${abs%.html}.pdf"
  "$CHROME" --headless --disable-gpu --no-pdf-header-footer \
    --virtual-time-budget=8000 \
    --print-to-pdf="$pdf" "file://$abs" 2>/dev/null
  echo "OK: $pdf ($(du -h "$pdf" | cut -f1 | tr -d ' '))"
done
