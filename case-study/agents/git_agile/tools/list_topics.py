"""List available topics in this agent's corpus."""
from pathlib import Path

NAME = "list_topics"
DESCRIPTION = "List the topics available in this corpus"


def invoke() -> list[str]:
    corpus_dir = Path(__file__).resolve().parent.parent / "corpus"
    if not corpus_dir.exists():
        return []
    return sorted(p.stem.replace("_", " ") for p in corpus_dir.glob("*.md"))
