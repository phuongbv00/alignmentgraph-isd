"""Assemble the ADDIE output contract from the design state.

Not an agent: no design role, no persona, no self-validation and no model
call — it reads the graph (or the blackboard) after the run and serializes it
into the shape ``core/validation.py`` defines.
"""
from __future__ import annotations

from copy import deepcopy

from .alignment_graph import NodeType, alignment


class ADDIEOutputAggregator:
    """Reads the finished design state and computes ``addie_output`` from real
    nodes and edges: every ``analysis``/``evaluation`` field and
    ``design.content_structure``/``design.storyboard`` is derived here from
    Gap/Topic/LearnerProfile/Constraint/Improvement elements, the Assessment
    pool, and Content/Media."""

    def __init__(self, graph, trajectory=None) -> None:
        self.graph = graph
        self.trajectory = trajectory

    def aggregate(self) -> dict:
        analysis = self._build_analysis()
        design = self._build_design()
        development = self._build_development()
        implementation = self._build_implementation()
        evaluation = self._build_evaluation()

        output = {
            "analysis": analysis,
            "design": design,
            "development": development,
            "implementation": implementation,
            "evaluation": evaluation,
        }
        return _add_alignment_views(output, self.graph)

    # ── analysis phase: computed from real Gap/Topic/LearnerProfile/Constraint elements ──
    def _build_analysis(self) -> dict:
        gaps = [n["data"] for n in self.graph.element_nodes(NodeType.GAP)]
        topics = [n["data"] for n in self.graph.element_nodes(NodeType.TOPIC)]
        constraints = [n["data"] for n in self.graph.element_nodes(NodeType.CONSTRAINT)]
        learner = _merge_node_data(self.graph.section_nodes(NodeType.LEARNER_PROFILE))
        # Each analysis section = its element pool + the narrative fields the
        # elements cannot express (problem_definition, priority_matrix,
        # prerequisites, review_summary, ...), which the analysis commit parks
        # on the matching section node — see
        # ``core/agentic/specialists.py::_store_narrative``.
        return {
            "needs_analysis": {
                **_merge_node_data(self.graph.section_nodes(NodeType.GAP)), "gaps": gaps,
            },
            "learner_analysis": learner,
            "context_analysis": {
                **_merge_node_data(self.graph.section_nodes(NodeType.CONSTRAINT)),
                "constraints": constraints,
            },
            "task_analysis": {
                **_merge_node_data(self.graph.section_nodes(NodeType.TOPIC)), "topics": topics,
            },
        }

    # ── design phase ──────────────────────────────────────────────────────
    def _build_design(self) -> dict:
        objectives = [n["data"] for n in self.graph.element_nodes(NodeType.OBJECTIVE)]
        activities = [n["data"] for n in self.graph.element_nodes(NodeType.ACTIVITY)]
        content_modules = [_without_harness_keys(n["data"])
                           for n in self.graph.element_nodes(NodeType.CONTENT)]
        media = [n["data"] for n in self.graph.element_nodes(NodeType.MEDIA_SELECTION)]
        plan_node = _merge_node_data(self.graph.section_nodes(NodeType.ACTIVITY_PLAN))

        design = {
            "learning_objectives": objectives,
            "learning_activities": activities,
            "assessment_plan": _merge_node_data(self.graph.section_nodes(NodeType.ASSESSMENT_PLAN)),
            "content_structure": {"modules": content_modules},
            "instructional_strategies": plan_node.get("instructional_strategies", {}),
            "non_instructional_strategies": plan_node.get("non_instructional_strategies", {}),
            "media_selection": media,
        }
        design["storyboard"] = _compute_storyboard(design["instructional_strategies"], content_modules)
        return design

    # ── development phase ─────────────────────────────────────────────────
    def _build_development(self) -> dict:
        materials = [n["data"] for n in self.graph.element_nodes(NodeType.MATERIAL)]
        # The criteria are already ON the items (see `fanout._attach_to_parent`),
        # so there is nothing left to join here.
        assessment_tools = _shape_rubrics(
            [n["data"] for n in self.graph.element_nodes(NodeType.ASSESSMENT)])
        impl_data = _with_session_guides(
            _merge_node_data(self.graph.section_nodes(NodeType.IMPLEMENTATION_PLAN)),
            [n["data"] for n in self.graph.element_nodes(NodeType.SESSION_GUIDE)])
        # development.expert_review is ALWAYS the audit record — a review
        # written by the same model before the artifacts exist is fiction, and
        # would collide with the thesis's separate REAL expert validation. It
        # REPORTS the verification that genuinely ran and says so.
        expert_review = self._expert_review_from_audit()
        return {
            "learner_materials": materials,
            "assessment_tools": assessment_tools,
            "expert_review": expert_review,
            "instructor_guide": impl_data.get("instructor_guide", {}),
            "operator_manual": impl_data.get("operator_manual", {}),
        }

    def _expert_review_from_audit(self) -> dict:
        """An internal-review record built from evidence, not invention.

        Beyond the aggregate counts it itemises WHAT the review examined and
        found: one finding row per violated criterion (issues found, repairs
        applied, one verbatim example issue) and the per-relation core
        alignment coverage — all read from the trajectory and the graph, so
        every row is traceable to a recorded event. It still never fabricates
        a human SME panel."""
        rounds = self.trajectory.check_events
        repairs = self.trajectory.repair_events
        found, by_type, findings, phases = _review_findings(rounds, repairs)
        coverage = alignment.all_relations_coverage(self.graph)
        core = {rid: c for rid, c in coverage.items() if c.get("tier") == "core"}
        core_full = sum(1 for c in core.values() if c.get("coverage") == 1.0)
        return {
            "review_type": "internal_automated",
            "reviewers": [
                "Automated pedagogical self-validation suite (deterministic checks over the alignment graph)",
            ],
            "review_criteria": sorted(
                {f"{rid}: {c['label']}" for rid, c in core.items()}
                | set(by_type),
            ),
            "review_process": (
                f"{len(rounds)} deterministic validation round(s) ran across "
                f"{len(phases)} design step(s)"
                + (f" ({', '.join(sorted(phases))})" if phases else "")
                + ", checking within-artifact quality and cross-artifact alignment "
                "coverage during generation."
            ),
            "findings": findings,
            "alignment_coverage": {
                rid: {"label": c.get("label", ""), "coverage": c.get("coverage")}
                for rid, c in sorted(core.items())
            },
            "feedback_summary": (
                f"{len(rounds)} self-validation round(s) inspected the design and found "
                f"{found} issue(s); {len(repairs)} repair(s) were applied. "
                f"Core alignment coverage after repair: {core_full}/{len(core)} relations fully covered. "
                "This record reports the automated verification that ran during generation; "
                "no external human expert review was performed."
            ),
        }

    # ── implementation phase (ImplementationPlannerAgent's own section) ──
    def _build_implementation(self) -> dict:
        # No session-guide join here: this phase carries the four operational
        # artifacts, and the guides belong to `development.instructor_guide`.
        con_data = _merge_node_data(self.graph.section_nodes(NodeType.IMPLEMENTATION_PLAN))
        return {
            "instructor_orientation": con_data.get("instructor_orientation", {}),
            "system_check": con_data.get("system_check", {}),
            "prototype_execution": con_data.get("prototype_execution", {}),
            "monitoring": con_data.get("monitoring", {}),
        }

    # ── evaluation phase: synthesized from the Assessment pool + AssessmentPlan + Improvement ──
    def _build_evaluation(self) -> dict:
        # The criteria are already ON the items (see `fanout._attach_to_parent`),
        # so there is nothing left to join here.
        assessment_tools = _shape_rubrics(
            [n["data"] for n in self.graph.element_nodes(NodeType.ASSESSMENT)])
        plan_data = _merge_node_data(self.graph.section_nodes(NodeType.ASSESSMENT_PLAN))
        improvements = [n["data"] for n in self.graph.element_nodes(NodeType.IMPROVEMENT)]

        formative_items = [t for t in assessment_tools if str(t.get("plan_category", "")).lower() == "formative"]
        summative_items = [t for t in assessment_tools if str(t.get("plan_category", "")).lower() == "summative"]

        # The formative half of ADDIE Evaluation is scored on more than a list
        # of instruments: the rubric asks which areas learners struggled with,
        # why, and what first-round revision follows — the assessment plan's
        # pilot_data_plan, surfaced here.
        pilot = plan_data.get("pilot_data_plan", {})
        pilot = pilot if isinstance(pilot, dict) else {}
        formative = {
            "data_collection": {
                "methods": plan_data.get("formative_methods", []),
                "collection_points": pilot.get("collection_points", []),
            },
            "anticipated_difficulties": pilot.get("anticipated_difficulties", []),
            "revision_plan": [
                {
                    "problem_area": entry.get("area", ""),
                    "evidence_source": entry.get("detected_by", ""),
                    "action": entry.get("first_revision", ""),
                }
                for entry in (pilot.get("anticipated_difficulties") or [])
                if isinstance(entry, dict)
            ],
            "assessment_tools": formative_items,
        }
        objective_ids = {t.get("aligned_objective") for t in summative_items if t.get("aligned_objective")}
        # Effectiveness/adoption synthesis: summative is the "summative"-tagged
        # slice of the unified Assessment pool, and nothing generates this
        # narrative, so it is synthesized deterministically from the counts.
        summative = {
            "assessment_tools": summative_items,
            "effectiveness_analysis": {
                "learning_outcomes": {
                    "details": f"{len(summative_items)} summative item(s) covering {len(objective_ids)} objective(s)."
                },
            },
            "adoption_decision": {
                "decision": "adopt" if summative_items else "pending",
                "rationale": (
                    "Summative evidence exists for the covered objectives; proceed to pilot review."
                    if summative_items else
                    "No summative evidence was generated; adoption cannot be recommended yet."
                ),
            },
        }
        # feedback_summary/next_iteration_goals come from the improvement plan
        # (the same call as the improvements, grounded in the gaps) — never
        # from the assessment plan, which does not carry them.
        improvement_plan = {
            **_merge_node_data(self.graph.section_nodes(NodeType.IMPROVEMENT)),
            "improvements": improvements,
        }
        improvement_plan.setdefault("feedback_summary", "")
        return {"formative": formative, "summative": summative, "improvement_plan": improvement_plan}


def _with_session_guides(implementation: dict, guides: list) -> dict:
    """Put the session guides back where the ADDIE output contract keeps them.

    They are element nodes since 2026-09-07 (``NodeType.SESSION_GUIDE``) — one
    per delivery session, written a block at a time by the Developer tier and
    the source of every P10/P11 edge — but the deliverable still declares them
    at ``development.instructor_guide.session_guides``
    (``validation._NESTED_FIELDS``), so the join happens here. Exactly the
    shape ``_shape_rubrics`` already has: the graph holds the artifact where
    the checks can reach it, the aggregator hands the judge the document it
    expects.

    Order is the graph's own insertion order, which is plan order, which is
    delivery order — the blocks were numbered before any Developer ran
    (``dev_plans._number_sessions``).
    """
    if not guides:
        return implementation
    guide = implementation.get("instructor_guide")
    guide = dict(guide) if isinstance(guide, dict) else {}
    guide["session_guides"] = list(guides)
    return {**implementation, "instructor_guide": guide}


def _shape_rubrics(items: list) -> list:
    """Put each item's rubric into the shape the deliverable declares.

    The criteria already sit on the item — filed there when they were written
    (``fanout._attach_to_parent``), on either substrate — so this no longer
    joins anything. What it still does is narrow each criterion to the four
    fields the output contract names, and rename ``description`` to
    ``criterion``: the generation schema and the deliverable disagree on that
    word, and the deliverable wins.

    Returns new dicts; never mutates the node/store data it reads.
    """
    out: list = []
    for item in items:
        if not isinstance(item, dict):
            out.append(item)
            continue
        criteria = [rc for rc in (item.get("rubric") or []) if isinstance(rc, dict)]
        if not criteria:
            out.append({k: v for k, v in item.items() if k != "rubric"})
            continue
        out.append({**item, "rubric": [{
            "id": rc.get("id", ""),
            "criterion": rc.get("criterion", rc.get("description", "")),
            "evidence_type": rc.get("evidence_type", ""),
            "levels": rc.get("levels", {}),
        } for rc in criteria]})
    return out


def _review_findings(rounds: list[dict], repairs: list[dict]) -> tuple[int, dict, list[dict], set]:
    """Itemised, evidence-backed review rows shared by both arms' synthesized
    expert_review: (total issues, issues by criterion, finding rows, phases
    inspected). Every number and example comes from a recorded trajectory
    event — nothing is invented.

    Counts DISTINCT findings, by key. It used to sum ``by_type`` across rounds,
    so a violation was counted once per round it survived — and since a check
    round re-finds everything the previous one could not repair, a measured run
    reported 28 issues for a set of 7. "How many things are wrong" and "how
    many times we looked at them" are different questions.
    """
    phases = {e["context"].get("phase") for e in rounds if e["context"].get("phase")}
    keys_by_type: dict[str, set[str]] = {}
    for event in rounds:
        context = event["context"]
        keys = context.get("keys")
        if keys:
            for key in keys:
                keys_by_type.setdefault(str(key).split("|", 1)[0], set()).add(str(key))
            continue
        # A run recorded before keys existed: fall back to the round sums it
        # does carry, so an archived trajectory still renders.
        for vtype, count in (context.get("by_type") or {}).items():
            for index in range(count):
                keys_by_type.setdefault(vtype, set()).add(f"{vtype}|legacy-{index}")
    by_type = {vtype: len(keys) for vtype, keys in keys_by_type.items()}
    found = sum(by_type.values())
    repairs_by_type: dict[str, int] = {}
    example_by_type: dict[str, str] = {}
    for event in repairs:
        context = event["context"]
        vtype = context.get("violation_type") or ""
        if not vtype:
            continue
        repairs_by_type[vtype] = repairs_by_type.get(vtype, 0) + 1
        example_by_type.setdefault(vtype, str(context.get("input_summary") or ""))
    findings = [
        {
            "criterion": vtype,
            "issues_found": count,
            "repairs_applied": repairs_by_type.get(vtype, 0),
            **({"example_issue": example_by_type[vtype]} if example_by_type.get(vtype) else {}),
        }
        for vtype, count in sorted(by_type.items())
        if count
    ]
    return found, by_type, findings, phases


def aggregate_prose(store, trajectory) -> dict:
    """The prose arm's aggregator: assemble ``addie_output`` from the
    blackboard documents alone. Same output schema as the graph aggregator,
    assembled by plain key-mapping — the documents already sit in schema
    shape, which is the point of the blackboard.

    Differences from the graph aggregator, all deliberate and all part of the
    ablated alignment machinery (never silent implementation drift):

    - no ``design.alignment_matrix`` — it is built from established edges and
      has no graph-free equivalent;
    - ``expert_review`` fallback reports the within-artifact validation
      rounds only, with no relation-coverage sentence.

    Kept: the storyboard computation and ``objective_assessment_map``, both
    deterministic readings of what the documents already declare.
    """
    def doc(key: str) -> dict:
        value = store.get(key)
        return value if isinstance(value, dict) else {}

    def items(key: str, field: str) -> list:
        return store.items(key, field)

    analysis_doc = doc("analysis")
    analysis = {
        "needs_analysis": analysis_doc.get("needs_analysis") or {},
        "learner_analysis": analysis_doc.get("learner_analysis") or {},
        "context_analysis": analysis_doc.get("context_analysis") or {},
        "task_analysis": analysis_doc.get("task_analysis") or {},
    }

    activity_plan = doc("activity_plan")
    content_modules = [_without_harness_keys(m) for m in items("content", "content_modules")]
    instructional_strategies = activity_plan.get("instructional_strategies") or {}
    design = {
        "learning_objectives": items("objective", "learning_objectives"),
        "learning_activities": items("activity", "learning_activities"),
        "assessment_plan": doc("assessment_plan"),
        "content_structure": {"modules": content_modules},
        "instructional_strategies": instructional_strategies,
        "non_instructional_strategies": activity_plan.get("non_instructional_strategies") or {},
        "media_selection": items("content", "media_selections"),
    }
    design["storyboard"] = _compute_storyboard(instructional_strategies, content_modules)

    assessment_tools = _shape_rubrics(items("assessment", "assessment_tools"))
    # The blackboard holds the guides as a top-level list of the implementation
    # document (that is where the fan-out's ``doc_key`` deposits them); the
    # deliverable declares them one level down, the same as in the graph arm.
    impl_doc = _with_session_guides(
        {k: v for k, v in doc("implementation_plan").items()
         if k not in ("session_guides",) + _HARNESS_ONLY_SECTION_KEYS},
        items("implementation_plan", "session_guides"))
    # ALWAYS synthesized (see the graph aggregator's matching note): the
    # prose arm's honest record covers only the within-artifact validation
    # that ran — no relation coverage exists to report.
    rounds = trajectory.check_events
    repairs = trajectory.repair_events
    found, by_type, findings, phases = _review_findings(rounds, repairs)
    expert_review = {
        "review_type": "internal_automated",
        "reviewers": [
            "Automated within-artifact self-validation suite (deterministic content checks)",
        ],
        "review_criteria": sorted(by_type),
        "review_process": (
            f"{len(rounds)} deterministic validation round(s) ran across "
            f"{len(phases)} design step(s)"
            + (f" ({', '.join(sorted(phases))})" if phases else "")
            + ", checking within-artifact quality during generation."
        ),
        "findings": findings,
        "feedback_summary": (
            f"{len(rounds)} self-validation round(s) inspected the design and found "
            f"{found} issue(s); {len(repairs)} repair(s) were applied. "
            "This record reports the automated verification that ran during generation; "
            "no external human expert review was performed."
        ),
    }
    development = {
        "learner_materials": items("material", "learner_materials"),
        "assessment_tools": assessment_tools,
        "expert_review": expert_review,
        "instructor_guide": impl_doc.get("instructor_guide") or {},
        "operator_manual": impl_doc.get("operator_manual") or {},
    }

    implementation = {
        "instructor_orientation": impl_doc.get("instructor_orientation") or {},
        "system_check": impl_doc.get("system_check") or {},
        "prototype_execution": impl_doc.get("prototype_execution") or {},
        "monitoring": impl_doc.get("monitoring") or {},
    }

    plan_data = doc("assessment_plan")
    improvement_doc = analysis_doc.get("improvement_plan") or {}
    formative_items = [t for t in assessment_tools
                       if isinstance(t, dict) and str(t.get("plan_category", "")).lower() == "formative"]
    summative_items = [t for t in assessment_tools
                       if isinstance(t, dict) and str(t.get("plan_category", "")).lower() == "summative"]
    pilot = plan_data.get("pilot_data_plan", {})
    pilot = pilot if isinstance(pilot, dict) else {}
    formative = {
        "data_collection": {
            "methods": plan_data.get("formative_methods", []),
            "collection_points": pilot.get("collection_points", []),
        },
        "anticipated_difficulties": pilot.get("anticipated_difficulties", []),
        "revision_plan": [
            {
                "problem_area": entry.get("area", ""),
                "evidence_source": entry.get("detected_by", ""),
                "action": entry.get("first_revision", ""),
            }
            for entry in (pilot.get("anticipated_difficulties") or [])
            if isinstance(entry, dict)
        ],
        "assessment_tools": formative_items,
    }
    objective_ids_covered = {t.get("aligned_objective") for t in summative_items if t.get("aligned_objective")}
    summative = {
        "assessment_tools": summative_items,
        "effectiveness_analysis": {
            "learning_outcomes": {
                "details": f"{len(summative_items)} summative item(s) covering {len(objective_ids_covered)} objective(s)."
            },
        },
        "adoption_decision": {
            "decision": "adopt" if summative_items else "pending",
            "rationale": (
                "Summative evidence exists for the covered objectives; proceed to pilot review."
                if summative_items else
                "No summative evidence was generated; adoption cannot be recommended yet."
            ),
        },
    }
    improvement_plan = {
        **{k: v for k, v in improvement_doc.items() if k != "improvements"},
        "improvements": improvement_doc.get("improvements") or [],
    }
    improvement_plan.setdefault("feedback_summary", "")
    evaluation = {"formative": formative, "summative": summative, "improvement_plan": improvement_plan}

    output = {
        "analysis": analysis,
        "design": design,
        "development": development,
        "implementation": implementation,
        "evaluation": evaluation,
    }
    objective_ids = [lo.get("id") for lo in design["learning_objectives"]
                     if isinstance(lo, dict) and lo.get("id")]
    if objective_ids:
        development["objective_assessment_map"] = {
            lo_id: [
                item.get("item_id")
                for item in assessment_tools
                if isinstance(item, dict) and item.get("aligned_objective") == lo_id
            ]
            for lo_id in objective_ids
        }
    return output


def _compute_storyboard(instructional_strategies: dict, content_modules: list[dict]) -> list[dict]:
    """Deterministic: one frame per Gagné event in the committed sequence,
    falling back to one frame per content module when the sequence is
    unusable. A view of already-designed content, never a stored node."""
    sequence = instructional_strategies.get("sequence") if isinstance(instructional_strategies, dict) else None
    frames: list[dict] = []
    if isinstance(sequence, list):
        for event in sequence:
            if not isinstance(event, dict):
                continue
            title = str(event.get("event") or "").strip() or f"Step {len(frames) + 1}"
            activity = str(event.get("activity") or "").strip()
            resources = event.get("resources") or []
            frames.append({
                "frame_number": len(frames) + 1,
                "screen_title": title,
                "visual_description": activity or f"Screen supporting the '{title}' step of the lesson.",
                "interaction": f"Learners engage with the '{title}' activity and receive guidance.",
                "notes": ", ".join(str(r) for r in resources) if isinstance(resources, list) else str(resources),
            })
    if frames:
        return frames
    for module in content_modules:
        title = str(module.get("title") or module.get("id") or f"Module {len(frames) + 1}").strip()
        frames.append({
            "frame_number": len(frames) + 1,
            "screen_title": title,
            "visual_description": f"Screen presenting the module '{title}'.",
            "interaction": "Learners work through the module content and check their understanding.",
            "notes": "",
        })
    return frames


#: Keys a plan section carries for the HARNESS, never for the ADDIE output.
#: ``dev_plan`` is the work-set plan the fan-out reads back (see
#: ``commit_assessment``): it belongs in the graph and its dump, where an
#: auditor can see how the family was divided up, and not in the deliverable,
#: which is what the judge scores.
_HARNESS_ONLY_SECTION_KEYS = ("dev_plan",)

#: Planning fields on an ELEMENT that only the fan-out reads — a content
#: module's `expected_materials` sizes its Developer's unit and says nothing
#: to a learner or a judge. Same rule as the section keys above: kept in the
#: graph so the dump shows how the family was divided, stripped from the
#: deliverable.
_HARNESS_ONLY_ELEMENT_KEYS = ("expected_materials",)


def _without_harness_keys(element: dict) -> dict:
    if not isinstance(element, dict):
        return element
    return {k: v for k, v in element.items() if k not in _HARNESS_ONLY_ELEMENT_KEYS}


def _merge_node_data(nodes: list[dict]) -> dict:
    """A section's data, minus the harness-only keys. A type never has more
    than one section node (every section write goes through
    ``graph.section_id``), so this is a copy, not a merge."""
    merged: dict = {}
    for node in nodes:
        data = node.get("data", {})
        if isinstance(data, dict):
            merged.update(deepcopy(data))
    for key in _HARNESS_ONLY_SECTION_KEYS:
        merged.pop(key, None)
    return merged


def _add_alignment_views(output: dict, graph) -> dict:
    """The two derived views the deliverable declares: the per-objective
    alignment matrix, read off ESTABLISHED edges, and the objective-to-item
    map, read off the items' own ``aligned_objective``. Both are readings of
    what the design holds.

    Nothing here writes design content. A harness that fills a gap it is also
    measuring satisfies its own check by existing, which is the objection that
    keeps P6 audit-only; the net that used to sit here appended an assessment
    item whose ``question`` carried the objective's own statement, which read
    to the RQ2 similarity signals as correspondence no design work produced,
    and it ran on the graph arm only, so the artefact sat on the
    ``context_mode`` axis itself."""
    design = output["design"]
    development = output["development"]

    objectives = design.get("learning_objectives", []) or []
    assessment_tools = development.get("assessment_tools", []) or []

    objective_ids = [lo.get("id") for lo in objectives if isinstance(lo, dict) and lo.get("id")]
    if objective_ids:
        design["alignment_matrix"] = _build_alignment_matrix(objective_ids, graph)
        development["objective_assessment_map"] = {
            lo_id: [
                item.get("item_id")
                for item in assessment_tools
                if isinstance(item, dict) and item.get("aligned_objective") == lo_id
            ]
            for lo_id in objective_ids
        }

    return output


def _build_alignment_matrix(objective_ids: list[str], graph) -> list[dict]:
    """Per-objective alignment record built from **established** edges
    (relation_id, established_by, evidence) — the real C1/C2/C3 picture."""
    objective_relations = [
        rid for rid, relation in alignment.MATRIX.items()
        if NodeType.OBJECTIVE in relation.target_node_types or (
            relation.coverage_side == "source" and NodeType.OBJECTIVE in relation.source_node_types
        )
    ]
    matrix: list[dict] = []
    for lo_id in objective_ids:
        target_id = f"{NodeType.OBJECTIVE}{graph.ELEMENT_SEP}{lo_id}"
        entry = {"objective_id": lo_id, "relations": {}}
        for relation_id in objective_relations:
            relation = alignment.MATRIX[relation_id]
            # LO is the edge's target for C1 (id "decomposes_to"
            # direction), but the edge's SOURCE for C2/C3 (the id-reverse
            # relations) — read whichever side actually names an objective.
            if relation.coverage_side == "source" and NodeType.OBJECTIVE in relation.source_node_types:
                edges = graph.get_edges(relation_id=relation_id, source=target_id)
            else:
                edges = graph.get_edges(relation_id=relation_id, target=target_id)
            entry["relations"][relation_id] = [
                {
                    "label": relation.label,
                    "counterpart": e["target"] if e["source"] == target_id else e["source"],
                    "established_by": e.get("established_by", ""),
                    "evidence": e.get("evidence", ""),
                }
                for e in edges
            ]
        matrix.append(entry)
    return matrix
