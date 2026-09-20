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
            if key not in artifact_schemas.ARTIFACT_SCHEMAS:
                missing.append(f"{step.name}.{key}")
    for name, spec in fanout.SPECS.items():
        for output in spec.outputs:
            if output.schema_key not in artifact_schemas.ARTIFACT_SCHEMAS:
                missing.append(f"{name}.{output.schema_key}")
    assert not missing, f"submit fields with no deep schema: {missing}"


def test_a_submit_field_name_is_its_own_schema_key():
    """One key, one shape, no indirection. The one field name that was reused
    across stages for three shapes (``dev_plan``) is gone: the three stages
    whose grouping it stated now derive it from the design instead."""
    keys = [key for step in specialists.STEPS for key, _t, _r in step.submit_fields]
    assert len(keys) == len(set(keys)), "a field name means one artifact, everywhere"
    assert not any("dev_plan" in key for key in keys)
