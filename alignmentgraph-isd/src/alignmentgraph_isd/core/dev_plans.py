"""Dev-plan normalization: turns an LLM-proposed work grouping into a
deterministic list of :class:`WorkSet` fan-out units, or derives that list
outright where no LLM decision is needed (rubrics, materials).

Substrate-agnostic on purpose: this module imports nothing from
``alignment_graph`` or ``prose_store`` so both context_mode arms call the
exact same normalization code over plain data. The one invariant every
function here upholds is that **the fan-out shape never depends on
unvalidated SLM output** — every ground-truth obligation (an
(objective, category) pair, an objective, a committed item) that survives
normalization is guaranteed to appear in exactly one returned WorkSet, LLM
proposal or not. A parse-failed or empty dev-plan call degrades to the pure
fallback (one singleton set per obligation), never to zero sets.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

#: Sets requested beyond this multiple of the true obligation count are
#: merged into one overflow set rather than accepted verbatim — a runaway
#: LLM dev-plan (one set per LO, then some) must not blow the fan-out width
#: up to the same scale the whole-pool call used to.
MAX_SET_FACTOR = 2
MAX_SETS_HARD_CAP = 24
#: Backstops for the deterministic (no-LLM) families; both are generous
#: relative to a realistic scenario's item/module counts.
MAX_RUBRIC_UNITS = 32
MAX_MATERIAL_UNITS = 12

_VALID_CATEGORIES = ("diagnostic", "formative", "summative")
#: A model occasionally echoes a namespaced node id ("objective:ILO-01") into
#: a reference field. This is a local, import-free twin of
#: ``alignment.bare_ref`` — this module must not import ``alignment_graph``
#: so the prose arm can normalize without pulling in the graph substrate.
_NAMESPACE_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")


def _bare(ref: object) -> str:
    return _NAMESPACE_PREFIX_RE.sub("", str(ref or "").strip(), count=1)


@dataclass(frozen=True)
class WorkSet:
    """One fan-out unit: a slice of work one Developer call produces.

    ``objectives``/``pairs`` are the assessment/activity grouping keys;
    ``payload`` carries whatever else the family's Developer prompt needs
    (an instrument hint, a content module, a batch of items…). ``source``
    records how this set came to exist, for the ``dev_plan`` trajectory
    event: ``"llm"`` (proposed and validated), ``"appended"`` (an LLM plan
    ran but left this obligation uncovered), ``"fallback"`` (the LLM plan
    was absent/unusable), ``"deterministic"`` (no LLM call for this family).
    """

    set_id: str
    objectives: tuple[str, ...] = ()
    pairs: tuple[tuple[str, str], ...] = ()
    payload: dict = field(default_factory=dict)
    source: str = "llm"

    def as_dict(self) -> dict:
        return {
            "set_id": self.set_id,
            "objectives": list(self.objectives),
            "pairs": [list(p) for p in self.pairs],
            "payload": self.payload,
            "source": self.source,
        }


def work_set_from_dict(data: dict) -> WorkSet:
    return WorkSet(
        set_id=str(data.get("set_id", "")),
        objectives=tuple(data.get("objectives") or ()),
        pairs=tuple(tuple(p) for p in (data.get("pairs") or ())),
        payload=dict(data.get("payload") or {}),
        source=str(data.get("source", "llm")),
    )


def _empty_stats(pair_count: int) -> dict:
    return {
        "set_count": 0, "pair_count": pair_count, "dropped_lo_refs": 0,
        "dropped_pairs": 0, "appended_sets": 0, "fallback_used": False,
    }


def _cap_and_number(sets: list[WorkSet], obligation_count: int, prefix: str,
                     merge: "callable") -> list[WorkSet]:
    """Enforce MAX_SET_FACTOR/MAX_SETS_HARD_CAP by merging overflow into one
    tail set (never dropping an obligation), then assign stable ``AS-01``
    style ids in order."""
    cap = min(MAX_SET_FACTOR * obligation_count, MAX_SETS_HARD_CAP)
    if len(sets) > cap:
        head, tail = sets[:cap - 1], sets[cap - 1:]
        sets = head + [merge(tail)]
    return [
        WorkSet(set_id=f"{prefix}-{i:02d}", objectives=ws.objectives, pairs=ws.pairs,
                payload=ws.payload, source=ws.source)
        for i, ws in enumerate(sets, start=1)
    ]


# ── assessment: instrument sets over (objective, plan_category) pairs ──────

def _assessment_ground_truth_pairs(lo_ids, coverage_targets) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(coverage_targets, dict) and coverage_targets:
        for lo_ref, cats in coverage_targets.items():
            lo = _bare(lo_ref)
            if not lo or not isinstance(cats, list):
                continue
            for cat in cats:
                cat_norm = str(cat or "").strip().lower()
                if cat_norm in _VALID_CATEGORIES:
                    pairs.append((lo, cat_norm))
    if not pairs:
        pairs = [(lo, "summative") for lo in (_bare(x) for x in (lo_ids or [])) if lo]
    return list(dict.fromkeys(pairs))  # de-dup, order-preserving


def normalize_assessment_dev_plan(parsed, lo_ids, coverage_targets) -> tuple[list[WorkSet], dict]:
    pairs = _assessment_ground_truth_pairs(lo_ids, coverage_targets)
    stats = _empty_stats(len(pairs))
    if not pairs:
        return [], stats
    pair_set = set(pairs)
    known_los = {lo for lo, _ in pairs}

    raw_sets = (parsed or {}).get("instrument_sets") if isinstance(parsed, dict) else None
    sets: list[WorkSet] = []
    if isinstance(raw_sets, list):
        for raw in raw_sets:
            if not isinstance(raw, dict):
                continue
            objs = [_bare(o) for o in (raw.get("objectives") or []) if _bare(o)]
            if not objs:
                continue
            stats["dropped_lo_refs"] += sum(1 for o in objs if o not in known_los)
            cats = [str(c or "").strip().lower() for c in (raw.get("plan_categories") or [])]
            cats = [c for c in cats if c in _VALID_CATEGORIES]
            candidate = [(lo, cat) for lo in objs for cat in cats]
            set_pairs = list(dict.fromkeys(p for p in candidate if p in pair_set))
            stats["dropped_pairs"] += len(candidate) - len(set_pairs)
            if not set_pairs:
                continue
            sets.append(WorkSet(
                set_id="", objectives=tuple(dict.fromkeys(lo for lo, _ in set_pairs)),
                pairs=tuple(set_pairs),
                payload={"instrument_hint": str(raw.get("instrument_hint", "")),
                         "rationale": str(raw.get("rationale", ""))},
                source="llm",
            ))

    had_llm_sets = bool(sets)
    covered = {p for ws in sets for p in ws.pairs}
    missing = [p for p in pairs if p not in covered]
    src = "appended" if had_llm_sets else "fallback"
    for lo, cat in missing:
        sets.append(WorkSet(set_id="", objectives=(lo,), pairs=((lo, cat),), payload={}, source=src))
    stats["appended_sets"] = len(missing)
    stats["fallback_used"] = not had_llm_sets

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_pairs = tuple(dict.fromkeys(p for ws in tail for p in ws.pairs))
        merged_objs = tuple(dict.fromkeys(lo for lo, _ in merged_pairs))
        return WorkSet(set_id="", objectives=merged_objs, pairs=merged_pairs,
                        payload=tail[-1].payload, source=tail[-1].source)

    numbered = _cap_and_number(sets, len(pairs), "AS", _merge)
    stats["set_count"] = len(numbered)
    return numbered, stats


# ── activity: blocks over objectives ────────────────────────────────────────

def normalize_activity_dev_plan(parsed, lo_ids, items_by_lo: dict | None = None) -> tuple[list[WorkSet], dict]:
    items_by_lo = items_by_lo or {}
    los = [lo for lo in (_bare(x) for x in (lo_ids or [])) if lo]
    stats = _empty_stats(len(los))
    if not los:
        return [], stats
    lo_set = set(los)

    raw_blocks = (parsed or {}).get("activity_blocks") if isinstance(parsed, dict) else None
    sets: list[WorkSet] = []
    if isinstance(raw_blocks, list):
        for raw in raw_blocks:
            if not isinstance(raw, dict):
                continue
            objs = [_bare(o) for o in (raw.get("objectives") or []) if _bare(o)]
            valid_objs = list(dict.fromkeys(o for o in objs if o in lo_set))
            stats["dropped_lo_refs"] += len(objs) - len(valid_objs)
            if not valid_objs:
                continue
            items = sorted({i for lo in valid_objs for i in items_by_lo.get(lo, [])})
            sets.append(WorkSet(
                set_id="", objectives=tuple(valid_objs), pairs=(),
                payload={"assessment_items": items, "block_theme": str(raw.get("block_theme", "")),
                         "rationale": str(raw.get("rationale", ""))},
                source="llm",
            ))

    had_llm_sets = bool(sets)
    covered = {lo for ws in sets for lo in ws.objectives}
    missing = [lo for lo in los if lo not in covered]
    src = "appended" if had_llm_sets else "fallback"
    for lo in missing:
        sets.append(WorkSet(
            set_id="", objectives=(lo,), pairs=(),
            payload={"assessment_items": items_by_lo.get(lo, []), "block_theme": "", "rationale": ""},
            source=src,
        ))
    stats["appended_sets"] = len(missing)
    stats["fallback_used"] = not had_llm_sets

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_objs = tuple(dict.fromkeys(o for ws in tail for o in ws.objectives))
        merged_items = sorted({i for ws in tail for i in ws.payload.get("assessment_items", [])})
        return WorkSet(set_id="", objectives=merged_objs, pairs=(),
                        payload={"assessment_items": merged_items, "block_theme": "", "rationale": ""},
                        source=tail[-1].source)

    numbered = _cap_and_number(sets, len(los), "AB", _merge)
    stats["set_count"] = len(numbered)
    return numbered, stats


# ── content: material units, one per committed module (deterministic) ──────

def material_work_units(modules: list[dict], media_selections: list[dict],
                         constraints: list[dict] | None = None) -> list[WorkSet]:
    modules = [m for m in (modules or []) if isinstance(m, dict) and m.get("id")]
    media_selections = [m for m in (media_selections or []) if isinstance(m, dict) and m.get("id")]
    constraint_by_id = {
        _bare(c["id"]): c for c in (constraints or []) if isinstance(c, dict) and c.get("id")
    }

    def _constraints_for(media_list: list[dict]) -> list[dict]:
        ids = {_bare(r) for m in media_list for r in (m.get("respects_constraints") or [])}
        return [constraint_by_id[cid] for cid in ids if cid in constraint_by_id]

    if not modules:
        # Degenerates to today's single whole-pool materials call.
        return [WorkSet(
            set_id="MU-ALL", payload={"modules": [], "media_selections": media_selections,
                                       "constraints": _constraints_for(media_selections)},
            source="deterministic",
        )]

    module_ids = [_bare(m["id"]) for m in modules]
    by_module: dict[str, list[dict]] = {mid: [] for mid in module_ids}
    unassigned: list[dict] = []
    for media in media_selections:
        targets = [t for t in (_bare(r) for r in (media.get("for_modules") or [])) if t in by_module]
        if targets:
            for t in targets:
                by_module[t].append(media)
        else:
            unassigned.append(media)  # no/unknown for_modules -> attach to every unit

    sets: list[WorkSet] = []
    for module in modules:
        mid = _bare(module["id"])
        media_for_unit = by_module[mid] + unassigned
        sets.append(WorkSet(
            set_id=f"MU-{mid}", payload={"modules": [module], "media_selections": media_for_unit,
                                          "constraints": _constraints_for(media_for_unit)},
            source="deterministic",
        ))

    if len(sets) > MAX_MATERIAL_UNITS:
        head, tail = sets[:MAX_MATERIAL_UNITS - 1], sets[MAX_MATERIAL_UNITS - 1:]
        merged_modules = [m for ws in tail for m in ws.payload["modules"]]
        merged_media = [m for ws in tail for m in ws.payload["media_selections"]]
        merged = WorkSet(
            set_id="MU-MERGED", payload={"modules": merged_modules, "media_selections": merged_media,
                                          "constraints": _constraints_for(merged_media)},
            source="deterministic",
        )
        sets = head + [merged]
    return sets


# ── fan-in helpers: shared by every family's finalize step ─────────────────

def pending_set_ids(work_sets: list[WorkSet], payloads: list[dict]) -> list[str]:
    """Work-set ids with no committed items in any payload — the per-set
    regen signal at finalize: deterministic (reads payload shape only, no
    matcher/graph dependence), so it works identically on both substrates."""
    have = {str(p.get("set_id", "")) for p in payloads if p.get("items")}
    return [ws.set_id for ws in work_sets if ws.set_id not in have]


def remap_and_tag(work_sets: list[WorkSet], payloads: list[dict], *, id_field: str,
                   ref_fields: tuple[str, ...] = ()) -> list[dict]:
    """Merge a family's Developer payloads (one per work set, each carrying
    ``{"set_id", "items": [...]}) into one flat, commit-ready item list.

    Workers run independently and never coordinate ids, so two sets can
    legitimately propose the same id (e.g. both name their first item
    "AT-01"). Walking sets in dev-plan order and rewriting any id a LATER
    set reuses (``f"{raw_id}-{set_id}"``) keeps every item, in the order the
    plan produced them, with no silent overwrite. ``ref_fields`` names
    within-item fields that hold lists of same-family ids scoped to this
    set (e.g. an activity's ``prerequisite_activities``) — those are
    rewritten through the same set's rename map so an id bump does not
    dangle a same-set reference; cross-set/cross-family references are
    untouched (by contract they name ids from an upstream, already-committed
    family, which never collide with a same-run rename).

    Every committed item is stamped ``plan_set`` with its owning set's id —
    invisible to schemas/judges (unknown keys validate), and the only signal
    ``pending_set_ids``-driven regen needs to tell which sets produced
    nothing.
    """
    payload_by_set: dict[str, list[dict]] = {}
    for p in payloads:
        payload_by_set.setdefault(str(p.get("set_id", "")), []).extend(
            i for i in (p.get("items") or []) if isinstance(i, dict))

    seen_ids: set[str] = set()
    out: list[dict] = []
    for ws in work_sets:
        set_items = payload_by_set.get(ws.set_id, [])
        rename: dict[str, str] = {}
        resolved: list[tuple[dict, str]] = []
        for item in set_items:
            raw_id = str(item.get(id_field) or "")
            if not raw_id:
                resolved.append((item, ""))
                continue
            final_id = raw_id
            if final_id in seen_ids:
                final_id = f"{raw_id}-{ws.set_id}"
            seen_ids.add(final_id)
            if final_id != raw_id:
                rename[raw_id] = final_id
            resolved.append((item, final_id))
        for item, final_id in resolved:
            new_item = dict(item)
            if final_id:
                new_item[id_field] = final_id
            for ref_field in ref_fields:
                refs = new_item.get(ref_field)
                if isinstance(refs, list):
                    new_item[ref_field] = [rename.get(str(r), r) for r in refs]
            new_item["plan_set"] = ws.set_id
            out.append(new_item)
    return out


# ── rubric: one unit per committed assessment item (deterministic) ─────────

def rubric_work_units(items: list[dict]) -> list[WorkSet]:
    items = [i for i in (items or []) if isinstance(i, dict) and i.get("item_id")]
    sets = [
        WorkSet(set_id=f"RB-{_bare(item['item_id'])}", payload={"items": [item]}, source="deterministic")
        for item in items
    ]
    if len(sets) > MAX_RUBRIC_UNITS:
        head, tail = sets[:MAX_RUBRIC_UNITS - 1], sets[MAX_RUBRIC_UNITS - 1:]
        merged_items = [it for ws in tail for it in ws.payload["items"]]
        merged = WorkSet(set_id="RB-MERGED", payload={"items": merged_items}, source="deterministic")
        sets = head + [merged]
    return sets


# ── work-set rendering: the "=== YOUR ASSIGNED ... ===" user-content block a
# Developer (multi arm) or a per-set state (single arm) shows the model.
# Pure text formatting, not part of the decomposition axis, so both arms
# import it from here rather than one borrowing the other's agent module.

def render_assessment_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"]
    if work_set.pairs:
        lines.append("pairs (objective x plan_category) YOU must cover, one item each:")
        for lo, category in work_set.pairs:
            lines.append(f"  - {lo} x {category}")
    hint = work_set.payload.get("instrument_hint")
    if hint:
        lines.append(f"instrument_hint: {hint}")
    rationale = work_set.payload.get("rationale")
    if rationale:
        lines.append(f"rationale: {rationale}")
    return "\n".join(lines)


def render_activity_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"]
    if work_set.objectives:
        lines.append("objectives YOU must cover:")
        for lo in work_set.objectives:
            lines.append(f"  - {lo}")
    items = work_set.payload.get("assessment_items") or []
    if items:
        lines.append("existing assessment item ids these activities may prepare learners for:")
        lines.append(", ".join(items))
    theme = work_set.payload.get("block_theme")
    if theme:
        lines.append(f"block_theme: {theme}")
    rationale = work_set.payload.get("rationale")
    if rationale:
        lines.append(f"rationale: {rationale}")
    return "\n".join(lines)


def render_material_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"]
    modules = work_set.payload.get("modules") or []
    if modules:
        lines.append("YOUR module(s):")
        for module in modules:
            lines.append(f"  [MODULE:{module.get('id', '')}] {json.dumps(module, ensure_ascii=False)}")
    media = work_set.payload.get("media_selections") or []
    if media:
        lines.append("media selections for this module:")
        for selection in media:
            lines.append(f"  [MEDIA:{selection.get('id', '')}] {json.dumps(selection, ensure_ascii=False)}")
    constraints = work_set.payload.get("constraints") or []
    if constraints:
        lines.append("constraints these media respect:")
        for constraint in constraints:
            lines.append(f"  [CONSTRAINT:{constraint.get('id', '')}] {json.dumps(constraint, ensure_ascii=False)}")
    return "\n".join(lines)


def render_rubric_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"]
    for item in work_set.payload.get("items") or []:
        lines.append(f"[ASSESSMENT:{item.get('item_id', '')}] {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)
