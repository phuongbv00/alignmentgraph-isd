"""The prose blackboard — the `prose` arm's replacement for the AlignmentGraph.

One flat, append/overwrite key→document store. Each specialist step deposits
its WHOLE parsed JSON output under one key (the same lowercase artifact-family
names the output schema already uses: ``analysis``, ``objective``,
``assessment_plan``, ``assessment``, ``activity_plan``, ``activity``,
``content``, ``material``, ``rubric``, ``implementation_plan``), and later
steps read those documents back verbatim, by a static per-step read-list.
This is the named-slice context-passing pattern the benchmark's non-graph
agents use (addie-agent, react-isd's chained tools): raw ``json.dumps`` of a
previously produced document injected into the prompt.

Deliberately absent, because their absence IS the treatment (the
``context_mode`` axis ablates the alignment machinery, not a rendering):

- no id index, no cross-references, no relation/edge vocabulary;
- no derived facts (coverage gaps, promised-pair dockets);
- no selection logic — a reader names documents, never "the nodes relation X
  calls for".

This module must not import anything from ``alignment_graph``/``alignment``:
the keys below coincide with the graph's node-type strings because both come
from the same output schema, not because one is derived from the other.
"""
from __future__ import annotations

import json

#: Per-artifact-family primary list: (store key, path of the list inside the
#: document). Used by the workflow's regen-emptiness check and the single
#: arm's idempotence guard — the prose counterpart of "does this step's
#: primary element pool have entries".
PRIMARY_STORE_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "gap": ("analysis", ("needs_analysis", "gaps")),
    "objective": ("objective", ("learning_objectives",)),
    "assessment": ("assessment", ("assessment_tools",)),
    "activity": ("activity", ("learning_activities",)),
    "material": ("material", ("learner_materials",)),
    "rubric": ("rubric", ("rubric_criteria",)),
}


def primary_items(store: "ProseStore", primary_type: str) -> list:
    """The primary artifact list for an artifact family, or ``[]``."""
    key, path = PRIMARY_STORE_FIELDS[primary_type]
    value: object = store.get(key)
    for part in path:
        if not isinstance(value, dict):
            return []
        value = value.get(part)
    return value if isinstance(value, list) else []


def _cap(text: str, max_chars: int) -> str:
    return text[:max_chars] + "…" if len(text) > max_chars else text


def _dump_capped(value: object, max_chars: int) -> str:
    """JSON-shaped text with the graph arm's per-artifact cap applied at the
    same unit: every LIST ELEMENT (≈ one artifact) is dumped whole and capped
    at ``max_chars``, exactly as ``tools.render_nodes`` caps one node's data;
    dict containers are recursed so no trailing artifact is silently dropped
    by a whole-document cut."""
    if isinstance(value, list):
        return "[" + ", ".join(
            _cap(json.dumps(item, ensure_ascii=False), max_chars) for item in value
        ) + "]"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            rendered = (
                _dump_capped(item, max_chars)
                if isinstance(item, (list, dict))
                else _cap(json.dumps(item, ensure_ascii=False), max_chars)
            )
            parts.append(f"{json.dumps(str(key), ensure_ascii=False)}: {rendered}")
        return "{" + ", ".join(parts) + "}"
    return _cap(json.dumps(value, ensure_ascii=False), max_chars)


class ProseStore:
    """Flat blackboard of raw per-step JSON documents."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def put(self, key: str, document: dict) -> None:
        """Deposit (or overwrite, on a regen re-run) one step's parsed output."""
        self._docs[key] = document if isinstance(document, dict) else {}

    def has(self, key: str) -> bool:
        return key in self._docs

    def get(self, key: str) -> dict | None:
        return self._docs.get(key)

    def items(self, key: str, field: str) -> list:
        """A list field of one document, or ``[]``."""
        value = (self._docs.get(key) or {}).get(field)
        return value if isinstance(value, list) else []

    def to_full_dict(self, design_brief_id: str = "") -> dict:
        """The run's blackboard dump — the prose arm's inspectability
        artifact (saved as ``<agent_id>_prose.json`` by the benchmark, the
        counterpart slot of the graph arm's ``<agent_id>_graph.json``). It is
        the raw per-step documents VERBATIM: what each specialist deposited
        and what later read-lists could see. Deliberately not an audit — no
        relations, no coverage, no derived facts — because the arm has none;
        it exists so a prose run stays debuggable (e.g. a truncated document
        is visible directly instead of only through downstream zeros)."""
        from datetime import datetime, timezone

        return {
            "documents": {key: self._docs[key] for key in self._docs},
            "metadata": {
                "design_brief_id": design_brief_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "document_count": len(self._docs),
                "document_keys": list(self._docs),
            },
        }

    def context(self, keys: tuple[str, ...], max_chars: int = 600) -> str:
        """Render the named documents for prompt injection: one ``[KEY]``
        block per present document, its content as verbatim JSON text
        (per-artifact cap only — see ``_dump_capped``). Absent keys are
        skipped silently; the reader's list is static, not state-dependent."""
        blocks: list[str] = []
        for key in keys:
            document = self._docs.get(key)
            if not document:
                continue
            blocks.append(f"[{key.upper()}]\n{_dump_capped(document, max_chars)}")
        return "\n\n".join(blocks)
