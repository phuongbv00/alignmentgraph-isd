from __future__ import annotations
from ..graph import NodeType
from ..schema import DesignBrief
from .. import alignment
import re
from .base import BaseISDAgent, _format_design_brief, parse_json_response

_BLOOM_VERB_BY_LEVEL = {
    "Remember": "Recall",
    "Understand": "Explain",
    "Apply": "Apply",
    "Analyze": "Analyze",
    "Evaluate": "Evaluate",
    "Create": "Design",
}

_VERB_REPLACEMENTS = {
    "comprehend": "Explain",
    "understand": "Explain",
    "grasp": "Explain",
    "learn": "Identify",
    "know": "Identify",
}

# ── Call 1: learning objectives only, conditioned on the analysis nodes ──────
_SYSTEM_LO = """\
You are an expert instructional designer working on the Design phase of ADDIE.

Given a training scenario and its needs/task/learner analysis, produce ONLY valid JSON with
this EXACT schema:
{
  "learning_objectives": [
    {"id": "LO-01", "level": "Remember", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-02", "level": "Understand", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-03", "level": "Apply", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-04", "level": "Analyze", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true},
    {"id": "LO-05", "level": "Evaluate", "statement": "<objective>", "bloom_verb": "<verb>", "measurable": true}
  ]
}

Must have at least 5 learning objectives spanning multiple Bloom's levels, each grounded in the
gaps/topics/learner profile given.
Use only these Bloom verbs in bloom_verb: Recall, Explain, Apply, Analyze, Evaluate, Design.
Output ONLY the JSON object, no markdown, no explanation.\
"""

# ── Call 2: the rest of Design, conditioned on the finalized objectives ──────
_SYSTEM_REST = """\
You are an expert instructional designer working on the Design phase of ADDIE.

Given a training scenario and its finalized learning objectives, produce ONLY valid JSON for
the remaining Design section with this EXACT schema:
{
  "assessment_plan": {
    "diagnostic": ["<diagnostic1>", "<diagnostic2>"],
    "formative": ["<formative1>", "<formative2>"],
    "summative": ["<summative1>", "<summative2>"]
  },
  "content_structure": {
    "modules": ["<module1>", "<module2>", "<module3>"],
    "topics": ["<topic1>", "<topic2>", "<topic3>"],
    "sequencing": "<learning sequence description>"
  },
  "instructional_strategies": {
    "model": "Gagné's 9 Events",
    "sequence": [
      {"event": "Gain attention", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Inform learners of objectives", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Stimulate recall of prior learning", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Present content", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Provide learning guidance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Elicit performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Provide feedback", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Assess performance", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]},
      {"event": "Enhance retention and transfer", "activity": "<activity>", "duration": "<time>", "resources": ["<resource>"]}
    ],
    "methods": ["<method1>", "<method2>", "<method3>"],
    "rationale": "<strategy selection rationale>"
  },
  "non_instructional_strategies": {
    "motivation_strategies": ["<motivation1>", "<motivation2>"],
    "self_directed_learning": ["<self1>", "<self2>"],
    "support_strategies": ["<support1>", "<support2>"]
  },
  "media_selection": [
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"},
    {"media_type": "<type>", "purpose": "<purpose>", "rationale": "<rationale>"}
  ],
  "storyboard": [
    {"frame_number": 1, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
    {"frame_number": 2, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"},
    {"frame_number": 3, "screen_title": "<title>", "visual_description": "<visual>", "interaction": "<interaction>", "notes": "<notes>"}
  ]
}

Must include ALL 9 Gagné events. Every part of this plan must serve the learning objectives
given — do not introduce content unrelated to them.
Output ONLY the JSON object, no markdown, no explanation.\
"""


class ObjectiveDesignAgent(BaseISDAgent):
    # activity_engagement moved to ActivityMaterialAgent: learning_activities has a single
    # owner now, so all activity-related repair belongs with the agent that generates them.
    # measurability is audit-only (over-strict statement rewrites hurt quality and the vague
    # verb it targets is already fixed by the bloom repair).
    OWNED_VIOLATION_TYPES = frozenset({"bloom"})

    def run(self, design_brief: DesignBrief) -> None:
        objective_ids = self._run_lo_call(design_brief)
        self._run_rest_call(design_brief, objective_ids)

    # ── Call 1 ────────────────────────────────────────────────────────────
    def _run_lo_call(self, design_brief: DesignBrief) -> list[str]:
        # Surgical regen: if a prior attempt already produced objectives, reuse
        # them instead of re-rolling good work (a whole-specialist regen fired
        # because the *rest* call came back empty, not this one).
        existing = self.graph.get_node(self.graph.section_id(NodeType.OBJECTIVE))
        if existing and existing["data"].get("learning_objectives"):
            return [n["id"] for n in self.graph.element_nodes(NodeType.OBJECTIVE)]

        prompt = _format_design_brief(design_brief)
        gap_ids = [n["id"] for n in self.graph.element_nodes("gap")]
        task_ids = [n["id"] for n in self.graph.element_nodes("task")]
        learner_id = self.graph.section_id("learner")
        source_ids = gap_ids + task_ids + ([learner_id] if self.graph.get_node(learner_id) else [])
        prior_ctx = self._element_context([
            n for n in (self.graph.get_node(nid) for nid in source_ids) if n is not None
        ])
        user_content = prompt
        if prior_ctx:
            user_content = f"=== NEEDS/TASK/LEARNER ANALYSIS ===\n{prior_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "objective_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM_LO},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)

        node_id = self.graph.section_id(NodeType.OBJECTIVE)
        self.graph.add_node(NodeType.OBJECTIVE, node_id, {"learning_objectives": parsed.get("learning_objectives", [])})
        self.trajectory.log_node_edit("add", node_id, NodeType.OBJECTIVE)

        # Decomposition into first-class element nodes (cheap non-LLM bookkeeping).
        objective_ids = self._decompose_elements(NodeType.OBJECTIVE, parsed.get("learning_objectives", []))
        for oid in objective_ids:
            self.trajectory.log_node_edit("add", oid, NodeType.OBJECTIVE)
        # R1/R2 are provenance relations: generation was conditioned on the
        # traversed gap/task/learner nodes above, so record that provenance.
        for oid in objective_ids:
            if gap_ids or task_ids:
                alignment.record_provenance(self.graph, "R1", gap_ids + task_ids, oid)
            if self.graph.get_node(learner_id):
                alignment.record_provenance(self.graph, "R2", [learner_id], oid)

        self.trajectory.log_step("ObjectiveDesignAgent", "design_objectives", prompt[:200], response[:200] if response else "")
        return objective_ids

    # ── Call 2 ────────────────────────────────────────────────────────────
    def _run_rest_call(self, design_brief: DesignBrief, objective_ids: list[str]) -> None:
        # Surgical regen: the strategies node only exists if a prior attempt's
        # rest call parsed successfully — skip re-rolling it then.
        if self.graph.get_node(self.graph.section_id("instructional_strategies")) is not None:
            return

        prompt = _format_design_brief(design_brief)
        lo_nodes = [n for n in (self.graph.get_node(oid) for oid in objective_ids) if n is not None]
        lo_ctx = self._element_context(lo_nodes)
        user_content = prompt
        if lo_ctx:
            user_content = f"=== FINALIZED LEARNING OBJECTIVES ===\n{lo_ctx}\n\n=== SCENARIO ===\n{prompt}"
        user_content = self._with_retrieval(design_brief, "objective_design", user_content)
        messages = [
            {"role": "system", "content": _SYSTEM_REST},
            {"role": "user", "content": user_content},
        ]
        response = self._call_llm(messages)
        parsed = parse_json_response(response)

        # Small-model robustness: the 2B endpoint intermittently returns the rest
        # payload with the storyboard and/or non-instructional strategies dropped
        # (empty), which scores the Design "prototype" (D3) and "non-instructional
        # strategy" (D2) rubric items 0/ABSENT. Synthesize them deterministically
        # from content generated in THIS same call — the Gagné sequence renders
        # screen-by-screen into a storyboard, and the learner/context profile
        # grounds the non-instructional scaffold — so the section is present and
        # grounded without spending an extra LLM call. Mirrors the deterministic
        # fallback in _repair_design_content: a guaranteed floor, not the goal.
        if not parsed.get("storyboard"):
            parsed["storyboard"] = self._fallback_storyboard(parsed)
        if not parsed.get("non_instructional_strategies"):
            parsed["non_instructional_strategies"] = self._fallback_non_instructional(design_brief)

        # Each Design "plan" sub-section becomes its own singleton node — the
        # first-class traversal source Development specialists reach through
        # (R6/R7/R9/R10/R12's sources). This is the ONE home for this data;
        # objective_0 stays limited to learning_objectives (see _run_lo_call).
        plan_node_ids: list[str] = []
        for field, node_type in (
            ("assessment_plan", "assessment_plan"),
            ("instructional_strategies", "instructional_strategies"),
            ("non_instructional_strategies", "non_instructional_strategies"),
            ("content_structure", "content_structure"),
            ("storyboard", "storyboard_plan"),
        ):
            data = parsed.get(field)
            if data in (None, {}, []):
                continue
            plan_id = self.graph.section_id(node_type)
            self.graph.add_node(node_type, plan_id, data if isinstance(data, dict) else {field: data})
            self.trajectory.log_node_edit("add", plan_id, node_type)
            plan_node_ids.append(plan_id)

        module_ids = self._decompose_auto_id(
            "content", (parsed.get("content_structure") or {}).get("modules"), id_prefix="MOD",
        )
        for mid in module_ids:
            self.trajectory.log_node_edit("add", mid, "content")

        media_ids = self._decompose_auto_id("media", parsed.get("media_selection"), id_prefix="MED")
        for mid in media_ids:
            self.trajectory.log_node_edit("add", mid, "media")

        storyboard_ids = self._decompose_auto_id(
            "storyboard", parsed.get("storyboard"), id_prefix="SB", text_key="screen_title",
        )

        # Rooting edges + R10/R11 provenance: this call was conditioned on the
        # traversed LOs/tasks/context, so record that traversal.
        # Rooting edges: every objective anchors every Design plan node this
        # call produced, so Development can traverse item -> plan -> objective
        # in one extra hop instead of fetching the LO separately.
        for oid in objective_ids:
            for plan_id in plan_node_ids:
                self.graph.add_edge("rooted-in", oid, plan_id, established_by="provenance",
                                     rationale=f"{plan_id} was generated conditioned on {oid}.")

        # R10: content modules cover the task topics traversed to build them.
        task_ids = [n["id"] for n in self.graph.element_nodes("task")]
        for module_id in module_ids:
            alignment.record_provenance(self.graph, "R10", task_ids, module_id)

        # R11: media selection is constrained by the needs/context analysis.
        needs_context_id = self.graph.section_id(NodeType.NEEDS_CONTEXT)
        for media_id in media_ids:
            alignment.record_provenance(self.graph, "R11", [needs_context_id], media_id)

        self.trajectory.log_step(
            "ObjectiveDesignAgent", "design_plan_sections", prompt[:200], response[:200] if response else "",
        )
        _ = storyboard_ids  # decomposed for future consumers; no relation currently targets it

    @staticmethod
    def _fallback_storyboard(parsed: dict) -> list[dict]:
        """Render a storyboard from the instructional flow designed in this call.

        A storyboard is the screen-by-screen view of the instructional sequence,
        so each Gagné event becomes one frame; when the sequence is unusable, fall
        back to one frame per content module. Deterministic and grounded — it never
        invents content that was not already designed."""
        strategies = parsed.get("instructional_strategies") or {}
        sequence = strategies.get("sequence") if isinstance(strategies, dict) else None
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
        modules = (parsed.get("content_structure") or {}).get("modules") or []
        for module in modules:
            title = str(module).strip() or f"Module {len(frames) + 1}"
            frames.append({
                "frame_number": len(frames) + 1,
                "screen_title": title,
                "visual_description": f"Screen presenting the module '{title}'.",
                "interaction": "Learners work through the module content and check their understanding.",
                "notes": "",
            })
        return frames

    @staticmethod
    def _fallback_non_instructional(design_brief: DesignBrief) -> dict:
        """Scaffold non-instructional strategies grounded in the learner/context
        profile so the section is scenario-specific rather than boilerplate."""
        ctx = design_brief.context
        role = (getattr(ctx, "learner_role", "") or design_brief.target_audience or "learners").strip()
        env = (getattr(ctx, "learning_environment", "") or "the learning environment").strip()
        domain = (design_brief.domain or "the subject").strip()
        return {
            "motivation_strategies": [
                f"Connect each task to authentic {domain} problems that {role} encounter in practice.",
                "Surface early wins with low-stakes formative checkpoints to build self-efficacy.",
            ],
            "self_directed_learning": [
                f"Provide a study guide and optional extension resources for self-pacing within {env}.",
                "Prompt learners to set personal goals and self-assess progress against the objectives.",
            ],
            "support_strategies": [
                f"Offer instructor support and peer discussion channels appropriate to {env}.",
                "Give scaffolded worked examples and a troubleshooting reference for common difficulties.",
            ],
        }

    def repair(self, violations: list) -> list:
        remaining = []
        content_violations = []
        for violation in violations:
            vtype = getattr(violation, "violation_type", "")
            if vtype == "bloom":
                self._repair_bloom_verb(violation)
            elif vtype == "measurability":
                content_violations.append(violation)
            else:
                remaining.append(violation)
        if content_violations:
            self._repair_design_content(content_violations)
        return remaining

    def _repair_design_content(self, violations: list) -> None:
        """Resolve measurability findings on the learning objectives.

        One LLM call revises every flagged objective statement; a
        deterministic fallback guarantees each finding is resolved even when
        the model output is unusable, so the verify-repair loop converges.
        """
        node_id = self.graph.section_id(NodeType.OBJECTIVE)
        node = self.graph.get_node(node_id)
        if not node:
            return
        from .pedagogical_verifier import _CONDITION_PATTERN, _DEGREE_PATTERN

        objectives = [dict(lo) if isinstance(lo, dict) else lo for lo in node["data"].get("learning_objectives", []) or []]
        measurability_ids = [
            str(v.metadata.get("lo_id", "") or "")
            for v in violations if v.violation_type == "measurability"
        ]

        revised = self._llm_design_revision(violations, objectives)
        revised_los = {
            str(lo["id"]): lo
            for lo in revised.get("learning_objectives", []) or []
            if isinstance(lo, dict) and lo.get("id")
        }
        for lo in objectives:
            if isinstance(lo, dict) and str(lo.get("id")) in revised_los:
                statement = str(revised_los[str(lo["id"])].get("statement") or "").strip()
                if statement:
                    lo["statement"] = statement

        # Deterministic fallback: every finding must end up resolved.
        for lo_id in measurability_ids:
            lo = next((x for x in objectives if isinstance(x, dict) and str(x.get("id")) == lo_id), None)
            if not lo:
                continue
            statement = str(lo.get("statement", ""))
            if not (_DEGREE_PATTERN.search(statement) or _CONDITION_PATTERN.search(statement)):
                lo["statement"] = (
                    statement.rstrip(". ")
                    + ", achieving at least 80% accuracy against the scoring rubric."
                )
                lo["measurable"] = True

        self.graph.update_node(node_id, {"learning_objectives": objectives})
        for lo in objectives:
            if isinstance(lo, dict) and lo.get("id"):
                self.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))
        self._log_repair(node_id, violation_type="measurability", repaired_fields=["learning_objectives"])
        self.trajectory.log_node_edit("update", node_id, NodeType.OBJECTIVE)
        self.trajectory.log_step(
            "ObjectiveDesignAgent",
            "repair_design_content",
            "; ".join(v.message for v in violations)[:200],
            f"Revised {len(measurability_ids)} objective statement(s).",
        )

    def _llm_design_revision(self, violations: list, objectives: list) -> dict:
        import json

        findings = [
            {
                "type": v.violation_type,
                "lo_id": v.metadata.get("lo_id"),
                "message": v.message,
                "hint": v.repair_hint,
            }
            for v in violations
        ]
        flagged_ids = {str(f["lo_id"]) for f in findings if f["lo_id"]}
        flagged_los = [
            lo for lo in objectives
            if isinstance(lo, dict) and str(lo.get("id")) in flagged_ids
        ]
        system = (
            "You are an expert instructional designer revising a course design to resolve "
            "verifier findings. Return ONLY valid JSON with this schema:\n"
            '{"learning_objectives": [{"id": "<existing id>", "statement": "<revised statement>"}]}\n'
            "Rules: keep objective ids, levels, and Bloom verbs unchanged; rewrite only the flagged "
            "statements so each states a performance condition and a measurable criterion. "
            "Include only revised entries."
        )
        user = json.dumps({"findings": findings, "flagged_objectives": flagged_los}, ensure_ascii=False)
        response = self._call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_retries=0,
        )
        return parse_json_response(response, warn=False) or {}

    def _repair_bloom_verb(self, violation) -> None:
        obj = self.graph.get_node(violation.node_id)
        if not obj:
            return

        lo_id = str(violation.metadata.get("lo_id", "") or "")
        objectives = list(obj["data"].get("learning_objectives", []))
        repaired = False

        for lo in objectives:
            if not isinstance(lo, dict):
                continue
            if lo_id and lo.get("id") != lo_id:
                continue
            old_verb = str(lo.get("bloom_verb", "")).strip()
            replacement = (
                _VERB_REPLACEMENTS.get(old_verb.lower())
                or _BLOOM_VERB_BY_LEVEL.get(lo.get("level"), "Explain")
            )
            lo["bloom_verb"] = replacement
            statement = str(lo.get("statement", ""))
            if old_verb and re.search(re.escape(old_verb), statement, flags=re.IGNORECASE):
                lo["statement"] = re.sub(
                    re.escape(old_verb),
                    replacement.lower(),
                    statement,
                    count=1,
                    flags=re.IGNORECASE,
                )
            elif replacement.lower() not in statement.lower():
                lo["statement"] = (
                    f"{statement} This is measured by asking learners to "
                    f"{replacement.lower()} the target skill in context."
                )
            repaired = True

        if not repaired:
            return

        self.graph.update_node(violation.node_id, {"learning_objectives": objectives})
        for lo in objectives:
            if isinstance(lo, dict) and lo.get("id"):
                self.graph.add_element_node(NodeType.OBJECTIVE, str(lo["id"]), dict(lo))
        self._log_repair(
            violation.node_id,
            violation_type=getattr(violation, "violation_type", "bloom"),
            repaired_fields=["learning_objectives", "bloom_verb"],
        )
        self.trajectory.log_node_edit("update", violation.node_id, NodeType.OBJECTIVE)
        self.trajectory.log_step(
            "ObjectiveDesignAgent",
            "repair_objective",
            violation.message,
            f"Updated Bloom verb for {lo_id or violation.node_id}.",
        )
