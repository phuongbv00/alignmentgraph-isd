"""Get all snippets for one exact topic from this agent's corpus."""
from pathlib import Path

NAME = "get_snippets"
DESCRIPTION = "Get all snippets for one exact topic name"


def invoke(topic: str = "") -> list[str]:
    corpus_dir = Path(__file__).resolve().parent.parent / "corpus"
    if not corpus_dir.exists():
        return []
    normalized = topic.lower().replace(" ", "_")
    path = corpus_dir / f"{normalized}.md"
    if not path.exists():
        for p in corpus_dir.glob("*.md"):
            if normalized in p.stem or p.stem in normalized:
                path = p
                break
        else:
            return []
    return [s.strip() for s in path.read_text(encoding="utf-8").split("\n\n") if s.strip()]
