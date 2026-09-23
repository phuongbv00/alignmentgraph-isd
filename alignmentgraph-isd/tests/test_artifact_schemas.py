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


#: Every field a MATRIX relation is built from, and the artifact that declares
#: it. A relation is only as strong as the contract behind its field: declared
#: OPTIONAL, it cannot fire for an artifact the model simply did not fill in,
#: and the resulting 0.00 says nothing about the design. That is how P8 read
#: 0.00 on run bd2531da in a graph where every other relation read 1.00.
#:
#: Exemptions carry their reason and are the interesting half of this table.
#: The test to apply is not "does a relation read it" but "would requiring it
#: make the model WRITE something true": a field the design cannot be built
#: without is asked for, and a field an honest artifact may leave empty is not,
#: because forcing that one buys an edge by fabrication.
_EDGE_FIELDS = [
    ("P7",  "course_modules",      "covers_topics",           True),
    ("P12", "course_modules",      "objectives",              True),
    ("C2",  "assessment_tools",    "aligned_objective",       True),
    ("P13", "learning_activities", "module_id",               True),
    ("C3",  "learning_activities", "aligned_objectives",      True),
    ("P5",  "learner_materials",   "linked_module",           True),
    ("P6",  "learner_materials",   "type",                    True),
    ("P6",  "media_selections",    "media_type",              True),
    ("P8",  "media_selections",    "respects_constraints",    True),
    ("P10", "session_guides",      "activity_ids",            True),
    # An activity need not prepare for a named task: a warm-up or a diagnostic
    # discussion honestly prepares for none. C4 is a CORE relation read by the
    # alignment panel, so an activity pushed to name a task it has nothing to
    # do with would buy a backbone edge by fabrication -- the worst place in
    # the system for it. C4's coverage side is the TASK anyway ("an assessment
    # task nothing prepares for"), which requiring the field on every activity
    # would not close.
    ("C4",  "learning_activities", "prepares_for_assessment", False),
    # A session with no activity is not a session; a session that hands out no
    # material is ordinary. The obligation is on the BLOCK -- every material id
    # it was handed lands in some guide -- and that is carried by the
    # deterministic division, not by each guide.
    ("P11", "session_guides",      "material_ids",            False),
]


def test_every_relation_field_is_required_or_exempt_for_a_reason():
    for relation, artifact, field, required in _EDGE_FIELDS:
        schema = artifact_schemas.ARTIFACT_SCHEMAS[artifact]
        assert field in schema["properties"], (relation, artifact, field)
        assert (field in schema["required"]) is required, (
            f"{relation}: {artifact}.{field} — a relation's field changed its "
            f"contract. Either restore it, or move the entry and say in the "
            f"comment above why the model may honestly leave it out.")


def test_the_table_covers_every_relation_that_reads_a_model_written_field():
    """The guard is only worth having while it is complete.

    The relations absent from the table are the ones built from something the
    HARNESS knows rather than something the model wrote: P1/P2/P4 record a
    section's provenance over ids the commit already holds, P3/P14 read an
    assessment task's own ``timing``/``module_id`` (both required inside
    ``assessment_plan.sets``), and P9 is established from the plan sections.
    """
    from alignmentgraph_isd.core.alignment_graph import alignment

    harness_established = {"P1", "P2", "P3", "P4", "P9", "P14"}
    covered = {relation for relation, _a, _f, _r in _EDGE_FIELDS} | harness_established
    assert covered == set(alignment.MATRIX), set(alignment.MATRIX) ^ covered
