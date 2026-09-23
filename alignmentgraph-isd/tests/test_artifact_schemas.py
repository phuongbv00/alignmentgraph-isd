"""Every submit-able artifact must have a deep tool-call schema.

``tools._parameters_from`` silently falls back to the old generic shallow
shape for a ``submit_fields``/``fanout.SetOutput`` key with no entry in
``artifact_schemas.ARTIFACT_SCHEMAS`` — a fallback that exists so a missing
key degrades gracefully rather than raising, not so a new artifact can quietly
regress to shallow. This test is what actually catches that regression.
"""
from __future__ import annotations

from alignmentgraph_isd.core.agentic import artifact_schemas, fanout, specialists, tools


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


def _objects(schema, path="") -> list[tuple[str, dict]]:
    """Every object node of a schema tree, with the path that reaches it."""
    found: list[tuple[str, dict]] = []
    if not isinstance(schema, dict):
        return found
    if schema.get("type") == "object":
        found.append((path, schema))
        for name, prop in (schema.get("properties") or {}).items():
            found += _objects(prop, f"{path}.{name}" if path else name)
    elif schema.get("type") == "array":
        found += _objects(schema.get("items"), f"{path}[]")
    return found


def test_a_required_container_declares_its_floor():
    """The contract the model is SHOWN must not be weaker than the one its
    submit is judged against.

    An empty list or object is "not arrived" everywhere here
    (``specialists._arrived``, ``validation._check_fields``, the fan-out's
    primary-output validator), so a required container is judged non-empty —
    while JSON Schema's ``required`` says only PRESENT. MEASURED (run
    aef73e0a): ``{"gaps": []}``, a valid instance of the schema handed over,
    rejected as "must be a non-empty list"; that class was 11 of the 51 submit
    rejections recorded across the runs beside it.
    """
    unfloored = []
    for key, schema in artifact_schemas.ARTIFACT_SCHEMAS.items():
        for path, obj in _objects(schema, key):
            for name in obj.get("required") or ():
                prop = (obj.get("properties") or {}).get(name)
                if not isinstance(prop, dict):
                    continue
                where = f"{path}.{name}"
                if prop.get("type") == "array" and prop.get("minItems") != 1:
                    unfloored.append(where)
                elif (prop.get("type") == "object"
                      and "additionalProperties" in prop
                      and prop.get("minProperties") != 1):
                    unfloored.append(where)
    assert not unfloored, f"required containers with no non-empty floor: {unfloored}"


def test_a_required_array_submit_field_declares_its_floor():
    """The same, one level up: an ARRAY artifact (the objectives, the modules,
    the media selections, a Developer's own output) is judged non-empty on
    arrival, so its own tool schema says so."""
    for step in specialists.STEPS:
        for spec in tools.submit_specs(step):
            for name, prop in spec["function"]["parameters"]["properties"].items():
                if prop.get("type") == "array":
                    assert prop.get("minItems") == 1, f"{step.name}.{name}"


#: A required list arriving EMPTY, per stage validator — each one a shape a 2B
#: model has actually submitted. The floors above are honest only while these
#: stay rejections.
_EMPTY_REQUIRED_LISTS = [
    ("analysis", {"needs_analysis": {"gaps": [],
                                     "priority_matrix": {"high": ["a gap, as prose"]}}},
     "needs_analysis.gaps"),
    ("analysis", {"context_analysis": {"constraints": [], "environment": "online"}},
     "context_analysis.constraints"),
    ("analysis", {"task_analysis": {"topics": [], "prerequisites": ["some"]}},
     "task_analysis.topics"),
    ("analysis", {"improvement_plan": {"improvements": [], "feedback_loop": "x"}},
     "improvement_plan.improvements"),
    ("assessment", {"assessment_plan": {"sets": [], "lo_coverage_targets": {"ILO-001": ["f"]}}},
     "assessment_plan.sets"),
]


def test_a_required_list_that_arrives_empty_is_rejected():
    steps = {step.name: step for step in specialists.STEPS}
    for stage, payload, field in _EMPTY_REQUIRED_LISTS:
        errors = steps[stage].validate(payload)
        assert any(field in e for e in errors), (stage, field, errors)


def test_a_media_selection_names_the_constraints_it_respects():
    """P8 is built entirely from ``respects_constraints``, so the field the
    relation requires has to be the field the contract requires.

    It was declared OPTIONAL while P8 required it. MEASURED (run bd2531da):
    all 12 selections omitted it, P8 read 0.00 in a graph where every other
    relation read 1.00, and all 12 findings were stamped ``unseen`` -- the
    check runs after the stage's loop has closed, so no agent was ever in a
    position to fix it. The same shape as the ``lo_coverage_targets`` defect:
    two parts of one system reading two different contracts.

    Pinned on BOTH halves, because either one alone leaves the asymmetry: the
    schema is what the model is shown, the validator is what refuses a submit.
    """
    schema = artifact_schemas.ARTIFACT_SCHEMAS["media_selections"]
    assert "respects_constraints" in schema["required"]
    assert schema["properties"]["respects_constraints"]["minItems"] == 1

    steps = {step.name: step for step in specialists.STEPS}
    whole = {"id": "MS-01", "media_type": "slides",
             "for_modules": ["MOD-01"], "respects_constraints": ["c001"]}
    assert steps["content"].validate({"media_selections": [whole]}) == []
    for field in ("respects_constraints", "for_modules"):
        short = {k: v for k, v in whole.items() if k != field}
        errors = steps["content"].validate({"media_selections": [short]})
        assert any(f"media_selections[0].{field}" in e for e in errors), (field, errors)
