#!/usr/bin/env python3
"""Render a Markdown file to PDF with Google Chrome headless on macOS."""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
)

PRINT_CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
body {
  color: #202124;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 10.5pt;
  line-height: 1.48;
  max-width: 100%;
}
h1, h2, h3, h4 { color: #172b4d; line-height: 1.2; page-break-after: avoid; }
h1 { border-bottom: 2px solid #172b4d; font-size: 22pt; padding-bottom: 5mm; }
h2 { border-bottom: 1px solid #b8c2cc; font-size: 16pt; margin-top: 12mm; padding-bottom: 2mm; }
h3 { font-size: 12.5pt; margin-top: 8mm; }
p, ul, ol, blockquote { orphans: 3; widows: 3; }
table { border-collapse: collapse; font-size: 9pt; margin: 4mm 0; width: 100%; }
th, td { border: 1px solid #c8d0d8; padding: 1.5mm 2mm; vertical-align: top; }
th { background: #eaf0f6; color: #172b4d; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
blockquote { border-left: 3px solid #7b8794; color: #4b5563; margin-left: 0; padding-left: 4mm; }
pre { background: #f4f6f8; border: 1px solid #d8dee4; border-radius: 3px; font-size: 8.5pt; overflow-wrap: anywhere; padding: 3mm; white-space: pre-wrap; }
code { background: #f1f3f4; border-radius: 2px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; padding: 0.1em 0.25em; }
pre code { background: transparent; padding: 0; }
hr { border: 0; border-top: 1px solid #c8d0d8; margin: 7mm 0; }
a { color: #145dbf; }
img { max-width: 100%; }
"""

MERMAID_SCRIPT = """
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
    mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "neutral" });
    mermaid.run().then(() => {
        document.documentElement.dataset.mermaidReady = "true";
    }).catch((error) => {
        document.documentElement.dataset.mermaidError = error;
        console.error(error);
    });
</script>
"""


def find_chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return candidate
    for command in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    raise RuntimeError("Google Chrome/Chromium headless executable not found")


def render_markdown(source: Path) -> str:
    try:
        import markdown
    except ImportError as error:
        raise RuntimeError("Install Python package 'Markdown' before running this script") from error

    body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        output_format="html",
    )
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda match: f'<div class="mermaid">{html.unescape(match.group(1))}</div>',
        body,
        flags=re.DOTALL,
    )
    title = html.escape(source.stem.replace("_", " "))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{PRINT_CSS}</style></head><body>{body}</body>{MERMAID_SCRIPT}</html>"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Markdown input file")
    parser.add_argument("-o", "--output", type=Path, help="PDF output path (default: beside input)")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Markdown file not found: {source}")
    output = (args.output or source.with_suffix(".pdf")).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()

    with tempfile.TemporaryDirectory(prefix="markdown-pdf-") as temp_dir:
        html_path = Path(temp_dir) / f"{source.stem}.html"
        html_path.write_text(render_markdown(source), encoding="utf-8")
        subprocess.run(
            [
                str(chrome),
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--virtual-time-budget=8000",
                f"--print-to-pdf={output}",
                html_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

    print(f"OK: {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)