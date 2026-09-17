"""Read and write marker-delimited blocks in a `.env` file.

Every writer owns one block and touches nothing outside its markers, so a
hand-edited credential above and a generated endpoint list below can live in
one file.

The markers deliberately name the BLOCK, not the script that writes it. A
marker embedding a writer's path stops matching the moment that writer is
renamed: it then fails to recognise its own block in an existing file and
appends a SECOND one, leaving duplicate keys whose winner depends on parse
order. A block is named for what it holds, which does not change when the
code moves.
"""

from __future__ import annotations

from pathlib import Path

BEGIN = ">>> {name} (managed) >>>"
END = "<<< {name} (managed) <<<"


def markers(name: str) -> tuple[str, str]:
    return f"# {BEGIN.format(name=name)}", f"# {END.format(name=name)}"


def read(path: Path, name: str) -> str | None:
    """The block's body, or None when it is not present."""
    if not path.exists():
        return None
    begin, end = markers(name)
    text = path.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        return None
    return text.split(begin, 1)[1].split(end, 1)[0].strip("\n")


def write(path: Path, name: str, body: str) -> None:
    """Replace the block, or append it if absent. Never touches the rest."""
    begin, end = markers(name)
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if begin in existing and end in existing:
        head = existing.split(begin, 1)[0]
        tail = existing.split(end, 1)[1]
        new = head + block + tail.lstrip("\n")
    else:
        new = existing.rstrip("\n") + ("\n\n" if existing.strip() else "") + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8")
