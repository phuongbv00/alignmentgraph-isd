"""ProseStore — the prose arm's blackboard (core/prose_store.py)."""
from __future__ import annotations

from alignmentgraph_isd.core.prose_store import PRIMARY_STORE_FIELDS, ProseStore, primary_items


def test_put_get_has_and_overwrite():
    store = ProseStore()
    assert not store.has("objective") and store.get("objective") is None
    store.put("objective", {"learning_objectives": [{"id": "ILO-01"}]})
    assert store.has("objective")
    store.put("objective", {"learning_objectives": []})  # regen overwrites
    assert store.get("objective") == {"learning_objectives": []}
    store.put("broken", ["not", "a", "dict"])  # non-dict payload degrades to {}
    assert store.get("broken") == {}


def test_items_returns_list_field_or_empty():
    store = ProseStore()
    assert store.items("assessment", "assessment_tools") == []
    store.put("assessment", {"assessment_tools": [{"item_id": "AT-01"}], "expert_review": {}})
    assert store.items("assessment", "assessment_tools") == [{"item_id": "AT-01"}]
    assert store.items("assessment", "missing_field") == []
    store.put("assessment", {"assessment_tools": "not-a-list"})
    assert store.items("assessment", "assessment_tools") == []


def test_context_renders_verbatim_json_blocks_and_skips_absent_keys():
    store = ProseStore()
    store.put("objective", {"learning_objectives": [{"id": "ILO-01", "statement": "Apply X."}]})
    ctx = store.context(("objective", "assessment"))
    assert ctx.startswith("[OBJECTIVE]\n")
    assert '"id": "ILO-01"' in ctx and '"statement": "Apply X."' in ctx
    assert "[ASSESSMENT]" not in ctx
    assert store.context(("assessment",)) == ""


def test_context_caps_each_list_element_not_the_document():
    """Parity with the graph arm's per-node 600-char cap: a long artifact is
    truncated individually; artifacts after it still appear."""
    store = ProseStore()
    store.put("assessment", {"assessment_tools": [
        {"item_id": "AT-01", "question": "q" * 2000},
        {"item_id": "AT-02", "question": "short"},
    ]})
    ctx = store.context(("assessment",), max_chars=600)
    assert "…" in ctx
    assert "AT-02" in ctx, "an item after a truncated one was lost"
    first_item = ctx.split(", ", 1)[0]
    assert len(first_item) < 700


def test_primary_items_walks_the_declared_path():
    store = ProseStore()
    assert primary_items(store, "gap") == []
    store.put("analysis", {"needs_analysis": {"gaps": [{"id": "GAP-01"}]}})
    assert primary_items(store, "gap") == [{"id": "GAP-01"}]
    for primary_type in PRIMARY_STORE_FIELDS:
        assert primary_items(ProseStore(), primary_type) == []


def test_to_full_dict_dumps_documents_verbatim_with_metadata():
    store = ProseStore()
    store.put("objective", {"learning_objectives": [{"id": "ILO-01"}]})
    store.put("assessment_plan", {"formative": ["exit tickets"]})
    dump = store.to_full_dict(design_brief_id="brief-1")
    assert dump["documents"]["objective"] == {"learning_objectives": [{"id": "ILO-01"}]}
    assert dump["metadata"]["design_brief_id"] == "brief-1"
    assert dump["metadata"]["document_count"] == 2
    assert dump["metadata"]["document_keys"] == ["objective", "assessment_plan"]
    assert dump["metadata"]["generated_at"]
