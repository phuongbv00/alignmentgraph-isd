"""Search snippets by keywords across all topics in this agent's corpus."""
from pathlib import Path

NAME = "search_corpus"
DESCRIPTION = "Search snippets by keywords in the query"


def invoke(query: str = "") -> list[str]:
    corpus_dir = Path(__file__).resolve().parent.parent / "corpus"
    if not corpus_dir.exists():
        return []
    needle = query.lower()
    hits: list[str] = []
    for path in sorted(corpus_dir.glob("*.md")):
        topic = path.stem.replace("_", " ")
        topic_match = not needle or topic in needle or any(word in topic for word in needle.split())
        for snippet in path.read_text(encoding="utf-8").split("\n\n"):
            snippet = snippet.strip()
            if snippet and (topic_match or needle in snippet.lower()):
                hits.append(snippet)
    return hits
