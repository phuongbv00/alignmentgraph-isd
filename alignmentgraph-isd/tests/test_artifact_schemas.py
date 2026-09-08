"""Every submit-able artifact must have a deep tool-call schema.

``tools._parameters_from`` silently falls back to the old generic shallow
shape for a ``submit_fields``/``fanout.SetOutput`` key with no entry in
``artifact_schemas.ARTIFACT_SCHEMAS`` — a fallback that exists so a missing
key degrades gracefully rather than raising, not so a new artifact can quietly
regress to shallow. This test is what actually catches that regression.
"""
from __future__ import annotations

from alignmentgraph_isd.core.agentic import artifact_schemas, fanout, specialists


def test_every_submit_field_has_an_artifact_schema():
    missing = []
    for step in specialists.STEPS:
        for key, _json_type, _required in step.submit_fields:
            lookup = step.schema_keys.get(key, key)
            if lookup not in artifact_schemas.ARTIFACT_SCHEMAS:
                missing.append(f"{step.name}.{key} (-> {lookup!r})")
    for name, spec in fanout.SPECS.items():
        for output in spec.outputs:
            if output.schema_key not in artifact_schemas.ARTIFACT_SCHEMAS:
                missing.append(f"{name}.{output.schema_key}")
    assert not missing, f"submit fields with no deep schema: {missing}"


def test_dev_plan_collision_resolves_per_stage():
    """``dev_plan`` is the one field name reused across three stages for three
    different shapes (assessment/activity/implementation dev plans) — the
    reason ``AgenticStep.schema_keys`` exists at all. Each must resolve to its
    OWN schema, not to a shared or missing one."""
    by_name = {step.name: step for step in specialists.STEPS}
    expected = {
        "assessment": "assessment_dev_plan",
        "activities": "activity_dev_plan",
        "implementation": "implementation_dev_plan",
    }
    seen_schemas = set()
    for stage, lookup in expected.items():
        step = by_name[stage]
        assert step.schema_keys.get("dev_plan") == lookup
        schema = artifact_schemas.ARTIFACT_SCHEMAS[lookup]
        assert id(schema) not in seen_schemas
        seen_schemas.add(id(schema))
