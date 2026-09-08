"""Dev-plan normalization: turns an LLM-proposed work grouping into a
deterministic list of :class:`WorkSet` fan-out units, or derives that list
outright where no LLM decision is needed (materials).

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
from dataclasses import dataclass, field, replace

#: Backstops, NOT a plan. Since 2026-09-01 the fan-out width is the agent's
#: decision — it proposes the grouping and these only stop a blow-up. They were
#: loose enough to be the real driver: measured on one scenario, an arm that
#: wrote 33 objectives got 66 assessment obligations, and a 2x factor turned
#: that into 24 Developer calls for assessment plus 24 more for activities.
#: One set per obligation-unit is the ceiling; a set may cover several.
MAX_SET_FACTOR = 1
MAX_SETS_HARD_CAP = 12

#: Estimated output cost of ONE OBLIGATION, in characters. An obligation is
#: what the split key counts — an (objective, category) pair for assessment, an
#: objective for activities, a module for materials — and the cost is how much
#: JSON the Developer actually writes for it. Both halves are measured on run
#: single_20260901_205901, over all four arms:
#:
#:   element size    item ~1,140 (max 2,973) · criterion ~355
#:                   activity ~635 (max 931) · material ~1,240 (max 1,710)
#:   yield           2.5 items/objective · 1.5 activities/objective
#:                   (spread 1.0-4.2 and 0.8-2.5 across the arms)
#:
#: So a pair costs about one item plus the criterion that marks it (~1,500),
#: and an objective costs about 1.5 activities (~950). Rounded UP, because a
#: budget that holds only for the average fails on exactly the sets that matter.
#:
#: ``session_guide`` counts a different obligation from the other three: one
#: SCHEDULED ARTIFACT (an activity to deliver or a material to hand out), not
#: one artifact produced. A session guide is a summary — it names several
#: activities in one entry — so the cost of scheduling one activity is that
#: entry's share of the guide's JSON (~800 chars over ~5 activities plus the
#: guide's own fixed fields), rounded up the same way. The obligation has to
#: be the scheduled artifact rather than the guide, because that is what the
#: plan divides and what P10/P11 coverage is checked over.
#:
#: Estimates, from a small sample on ONE scenario. Revisit them against ladder
#: data rather than treating them as constants.
UNIT_CHARS = {"assessment": 1800, "activity": 1300, "material": 1800,
              "session_guide": 400}

#: What ONE Developer call may be asked to produce, in characters of JSON.
#:
#: The 8192-token completion cap is roughly 28k characters, so this sits about
#: 2.5x under it. Not tighter, because the split trades directly against the
#: number of calls: a 33-objective scenario with three categories each is 99
#: obligations, which is 17 calls at this budget and 33 at half of it. And the
#: cap is not in fact where these runs were failing — measured mean completion
#: was 470 tokens over 95 calls, nowhere near 8192 — so buying safety margin
#: here is paid for in calls that were never at risk.
SET_OUTPUT_BUDGET = 11000


def max_units(family: str) -> int:
    """How many elements one Developer call may be asked for.

    Quantity ALONE is the wrong split key, which is what the LO-only grouping
    was: three objectives is a small set for activities and a large one for
    assessment, because an assessment obligation produces an item AND the
    criterion that marks it. Estimated output length is what the two have in
    common.
    """
    return max(1, SET_OUTPUT_BUDGET // UNIT_CHARS.get(family, SET_OUTPUT_BUDGET))


#: Backstop for the deterministic (no-LLM) material fan-out.
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
    #: This set's position in its plan, 1-based. It is the first half of every
    #: id its Developer's artifacts commit under (``AT-0203`` = set 2, item 3),
    #: so it is fixed when the plan is numbered — before any Developer runs —
    #: and no id depends on which of them commits first.
    ordinal: int = 1

    def as_dict(self) -> dict:
        return {
            "set_id": self.set_id,
            "objectives": list(self.objectives),
            "pairs": [list(p) for p in self.pairs],
            "payload": self.payload,
            "source": self.source,
            "ordinal": self.ordinal,
        }


def work_set_from_dict(data: dict) -> WorkSet:
    return WorkSet(
        set_id=str(data.get("set_id", "")),
        objectives=tuple(data.get("objectives") or ()),
        pairs=tuple(tuple(p) for p in (data.get("pairs") or ())),
        payload=dict(data.get("payload") or {}),
        source=str(data.get("source", "llm")),
        ordinal=int(data.get("ordinal") or 1),
    )


def _empty_stats(pair_count: int) -> dict:
    return {
        "set_count": 0, "pair_count": pair_count, "dropped_lo_refs": 0,
        "dropped_pairs": 0, "appended_sets": 0, "fallback_used": False,
        # Obligations the plan named in TWO sets. The second naming is dropped:
        # two Developers each told to write "the" item for one pair produce
        # two items for one obligation (measured on run e81b8108: ILO-02 x
        # formative in both AS-02 and AS-03), and nothing downstream objected
        # because coverage asks "at least one".
        "duplicate_pairs": 0,
        # Sets the HARNESS had to cut because the planner handed over one too
        # big to answer. The planner is told the budget and asked to scope its
        # own sets; this counts how often it did not, which is the only way to
        # tell a plan that is doing its job from one the backstop is carrying.
        "oversized_splits": 0,
    }


#: What a replan round adds to a set's ordinal so its ids cannot land on the
#: round before it. Well above any plausible set count (``MAX_SETS_HARD_CAP``
#: is 12, and the size bound can push past it), and correctness does not rest
#: on the number: ``_composite_id`` scans past anything already taken.
ROUND_ORDINAL_STRIDE = 50


def number_sets(sets: list[WorkSet], *, prefix: str = "") -> list[WorkSet]:
    """Give each set its 1-based ORDINAL — the first half of every id its
    Developer's artifacts commit under (``_composite_id``), fixed before any
    Developer runs so no two sets can name the same artifact and no id depends
    on who commits first.

    ``prefix`` ALSO renames the set (``AS-01``), which is what the planned
    families want. ``material_work_units`` passes none: its set ids are
    MODULE-derived (``MU-MOD-03``) and that is read — it is stamped on every
    item as ``plan_set``, it is what ``pending_set_ids`` matches for the regen,
    and it is the only thing in the graph dump that says which module a
    material came from.

    Numbering and naming are two jobs, and they were fused inside
    ``_cap_and_number``. So the one family that could not take the naming
    silently got no ordinal either: every material set kept the dataclass
    default of 1, ids came out ``MAT-0101``…``MAT-0108`` across six different
    modules, and uniqueness rested entirely on the ``taken`` scan in
    ``_composite_id`` — the exact "whoever commits first" scheme that
    function's own docstring says is not how this works. Harmless while the
    fan-out is sequential, and not harmless the moment anything retries a set
    or runs two concurrently."""
    return [replace(ws, set_id=f"{prefix}-{i:02d}" if prefix else ws.set_id, ordinal=i)
            for i, ws in enumerate(sets, start=1)]


def _cap_and_number(sets: list[WorkSet], obligation_count: int, prefix: str,
                     merge: "callable", *, family: str = "",
                     split: "callable | None" = None) -> list[WorkSet]:
    """Bound the fan-out from BOTH ends, then assign stable ``AS-01`` ids.

    Two bounds, and the order matters. The count cap
    (``MAX_SET_FACTOR``/``MAX_SETS_HARD_CAP``) stops a blow-up in the number of
    calls by merging the overflow into one tail set. That merge is the danger:
    on a 33-objective scenario it produced a tail carrying 22 obligations in a
    SINGLE call — the cap on calls making the calls unanswerable.

    So the size bound is applied AFTER the merge and wins over the count. A set
    the model cannot finish costs everything it was going to produce, while an
    extra call costs one call.
    """
    cap = min(MAX_SET_FACTOR * obligation_count, MAX_SETS_HARD_CAP)
    if len(sets) > cap:
        head, tail = sets[:cap - 1], sets[cap - 1:]
        sets = head + [merge(tail)]
    oversized = 0
    if split is not None and family:
        limit = max_units(family)
        cut: list[WorkSet] = []
        for ws in sets:
            pieces = split(ws, limit)
            oversized += len(pieces) > 1
            cut.extend(pieces)
        sets = cut
    numbered = number_sets(sets, prefix=prefix)
    if oversized and numbered:
        # Carried on the first set so the caller can read it back without a
        # second return value threaded through every family.
        numbered[0].payload.setdefault("_oversized_splits", oversized)
    return numbered


def _chunks(seq: list, size: int) -> list[list]:
    return [seq[i:i + size] for i in range(0, len(seq), size)] or [[]]


# ── assessment: instrument sets over (objective, plan_category) pairs ──────

def plan_category_pairs(coverage_targets) -> list[tuple[str, str]]:
    """``lo_coverage_targets`` as (objective, category) pairs, whatever shape
    the model wrote it in.

    Two shapes are accepted. The schema asks for a list of category names
    (``{"ILO-01": ["diagnostic", "summative"]}``), and models also write the
    richer entry that names the instrument alongside the category
    (``[{"plan_category": "formative", "instrument": "concept mapping"}]``) —
    the same promise with more detail, so it is normalized rather than
    refused. Anything whose category is not one of the three is dropped.

    ONE reader for one field, because there were two and they disagreed
    (run single_20260901_205901). This one guarded on ``_VALID_CATEGORIES``,
    saw the dict form, dropped every pair, and silently fell back to
    summative-only work sets. ``checks.plan_coverage`` did not guard: it took
    ``str(dict).lower()`` as the category, so every promised pair read as
    unrealised, and the repair then minted item ids from
    ``category[:1].upper()`` — the literal ``AT-{-ILO-01`` that reached the
    final artifact, the alignment matrix and four activities' assessment
    references."""
    pairs: list[tuple[str, str]] = []
    if not isinstance(coverage_targets, dict):
        return pairs
    for lo_ref, cats in coverage_targets.items():
        lo = _bare(lo_ref)
        if not lo or not isinstance(cats, list):
            continue
        for cat in cats:
            if isinstance(cat, dict):
                cat = cat.get("plan_category") or cat.get("category") or ""
            cat_norm = str(cat or "").strip().lower()
            if cat_norm in _VALID_CATEGORIES:
                pairs.append((lo, cat_norm))
    return list(dict.fromkeys(pairs))


def _assessment_ground_truth_pairs(lo_ids, coverage_targets) -> list[tuple[str, str]]:
    pairs = plan_category_pairs(coverage_targets)
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
    claimed: set[tuple[str, str]] = set()
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
            on_target = list(dict.fromkeys(p for p in candidate if p in pair_set))
            stats["dropped_pairs"] += len(candidate) - len(on_target)
            # Across sets, not only within one: a pair the plan already put in
            # an earlier set stays there. "Every pair in exactly one set" is
            # the rule the planner is given (RULES_ASSESSMENT_DEV_PLAN).
            set_pairs = [p for p in on_target if p not in claimed]
            stats["duplicate_pairs"] += len(on_target) - len(set_pairs)
            if not set_pairs:
                continue
            claimed.update(set_pairs)
            sets.append(WorkSet(
                set_id="", objectives=tuple(dict.fromkeys(lo for lo, _ in set_pairs)),
                pairs=tuple(set_pairs),
                payload={"instrument_hint": str(raw.get("instrument_hint", "")),
                         "rationale": str(raw.get("rationale", "")),
                         "expected_items": _expected_items(
                             raw.get("expected_items"), len(set_pairs))},
                source="llm",
            ))

    had_llm_sets = bool(sets)
    covered = {p for ws in sets for p in ws.pairs}
    missing = [p for p in pairs if p not in covered]
    src = "appended" if had_llm_sets else "fallback"
    # Grouped by OBJECTIVE, not by (objective, category). One set per pair is
    # the harness deciding the fan-out width, and it decided badly: a 4-objective
    # scenario became 12 Developer calls because each objective carries three
    # plan categories. One call writes the diagnostic, formative and summative
    # instruments for one objective — which is also how an assessment designer
    # would actually work.
    by_objective: dict[str, list[tuple[str, str]]] = {}
    for lo, cat in missing:
        by_objective.setdefault(lo, []).append((lo, cat))
    for lo, lo_pairs in by_objective.items():
        sets.append(WorkSet(set_id="", objectives=(lo,), pairs=tuple(lo_pairs),
                            payload={}, source=src))
    stats["appended_sets"] = len(by_objective)
    stats["fallback_used"] = not had_llm_sets

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_pairs = tuple(dict.fromkeys(p for ws in tail for p in ws.pairs))
        merged_objs = tuple(dict.fromkeys(lo for lo, _ in merged_pairs))
        return WorkSet(set_id="", objectives=merged_objs, pairs=merged_pairs,
                        payload=tail[-1].payload, source=tail[-1].source)

    def _split(ws: WorkSet, limit: int) -> list[WorkSet]:
        """Keep the objective grouping; subdivide WITHIN it.

        The planned quantity for this family is bounded by its pairs: a set
        writes ``expected_items`` items (at least one per pair, at most
        ``max_units``), so a set whose PAIRS fit the limit fits in one call
        and only the pair list decides whether it has to be cut.

        Chunking the flattened pair list would cut across objectives — a piece
        carrying the tail of ILO-01 and the head of ILO-02 — which throws away
        the grouping the plan chose and the shared stem the set was built
        around. So a set that does not fit is broken up BY OBJECTIVE first, and
        an objective that does not fit on its own is then chunked within
        itself.
        """
        if len(ws.pairs) <= limit:
            return [ws]
        by_lo: dict[str, list[tuple[str, str]]] = {}
        for pair in ws.pairs:
            by_lo.setdefault(pair[0], []).append(pair)
        pieces: list[list[tuple[str, str]]] = []
        for lo_pairs in by_lo.values():
            pieces.extend(_chunks(lo_pairs, limit))
        return [
            WorkSet(set_id="", objectives=(chunk[0][0],), pairs=tuple(chunk),
                    payload=ws.payload, source=ws.source)
            for chunk in pieces if chunk
        ]

    numbered = _cap_and_number(sets, len(pairs), "AS", _merge,
                               family="assessment", split=_split)
    # A merged or split set carries a payload copied from one of its parts, so
    # its planned count no longer describes its pairs; re-derive it from what
    # the set actually holds. Also fills the count in for appended/fallback
    # sets, whose payload is empty.
    for ws in numbered:
        ws.payload["expected_items"] = _expected_items(
            ws.payload.get("expected_items"), len(ws.pairs))
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    return numbered, stats


def _expected_items(raw: object, pair_count: int) -> int:
    """How many items an instrument set writes: the planner's own count,
    clamped to ``[pairs, max_units]``, or the pair count when it gave none.

    The count used to BE the pair count — "one item per (objective,
    plan_category) pair, no filler" — which left the planner no way to say
    an instrument needs three items on one objective. The floor is still one
    item per pair (``checks.plan_coverage`` holds every pair to that) and the
    ceiling is the same per-call budget the split uses, so a planned count
    can never make a set unanswerable.
    """
    floor = max(1, pair_count)
    ceiling = max(floor, max_units("assessment"))
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return floor
    return min(max(value, floor), ceiling)


# ── activity: blocks over objectives ────────────────────────────────────────

#: Activities one objective needs when the plan does not say. Measured yield
#: on run single_20260901_205901 was 0.8-2.5 per objective across the arms; the
#: high end, because under-estimating means a set the Developer cannot finish
#: and over-estimating only costs an extra call.
ACTIVITIES_PER_OBJECTIVE = 3
#: A planned count is the PLANNER's judgement, not a free hand: a 2B model that
#: writes 40 here would turn one block into a dozen calls.
MAX_EXPECTED_PER_SET = 12


def _expected(raw: object, objective_count: int) -> int:
    """The plan's own count for a set, clamped, or the deterministic estimate.

    The planner is the only step that knows whether a block is one exercise or
    a six-step progression, so it is asked. It is not trusted: a missing,
    unreadable or absurd number falls back to the measured yield.
    """
    fallback = max(1, objective_count) * ACTIVITIES_PER_OBJECTIVE
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if value < 1:
        return fallback
    return min(value, MAX_EXPECTED_PER_SET)


def normalize_activity_dev_plan(parsed, lo_ids, items_by_lo: dict | None = None) -> tuple[list[WorkSet], dict]:
    items_by_lo = items_by_lo or {}
    los = [lo for lo in (_bare(x) for x in (lo_ids or [])) if lo]
    stats = _empty_stats(len(los))
    if not los:
        return [], stats
    lo_set = set(los)

    raw_blocks = (parsed or {}).get("activity_blocks") if isinstance(parsed, dict) else None
    sets: list[WorkSet] = []
    claimed: set[str] = set()
    if isinstance(raw_blocks, list):
        for raw in raw_blocks:
            if not isinstance(raw, dict):
                continue
            objs = [_bare(o) for o in (raw.get("objectives") or []) if _bare(o)]
            known = list(dict.fromkeys(o for o in objs if o in lo_set))
            stats["dropped_lo_refs"] += len(objs) - len(known)
            # An objective already in an earlier block stays there — unless
            # this block carries its own `block_theme`, which is the planner
            # deliberately splitting one objective across distinct scopes
            # (RULES_ACTIVITY_DEV_PLAN asks for exactly that when an
            # objective needs more than one call).
            themed = bool(str(raw.get("block_theme", "")).strip())
            valid_objs = [o for o in known if themed or o not in claimed]
            stats["duplicate_pairs"] += len(known) - len(valid_objs)
            if not valid_objs:
                continue
            claimed.update(valid_objs)
            items = sorted({i for lo in valid_objs for i in items_by_lo.get(lo, [])})
            sets.append(WorkSet(
                set_id="", objectives=tuple(valid_objs), pairs=(),
                payload={"assessment_items": items, "block_theme": str(raw.get("block_theme", "")),
                         "rationale": str(raw.get("rationale", "")),
                         "expected_activities": _expected(
                             raw.get("expected_activities"), len(valid_objs))},
                source="llm",
            ))

    had_llm_sets = bool(sets)
    covered = {lo for ws in sets for lo in ws.objectives}
    missing = [lo for lo in los if lo not in covered]
    src = "appended" if had_llm_sets else "fallback"
    for lo in missing:
        sets.append(WorkSet(
            set_id="", objectives=(lo,), pairs=(),
            payload={"assessment_items": items_by_lo.get(lo, []), "block_theme": "",
                     "rationale": "", "expected_activities": _expected(None, 1)},
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

    def _split(ws: WorkSet, limit: int) -> list[WorkSet]:
        """Split on the PLANNED count, not on the objective count.

        An objective is not a unit of work here: the plan says how many
        activities a block needs (``expected_activities``), and three
        objectives that need one activity each is a smaller job than one
        objective that needs a six-step progression. Counting objectives
        cannot tell those apart.
        """
        planned = int(ws.payload.get("expected_activities") or 0) or (
            len(ws.objectives) * ACTIVITIES_PER_OBJECTIVE)
        if planned <= limit:
            return [ws]
        if len(ws.objectives) > 1:
            # Break the block up by objective first, keeping each objective
            # whole, and let the recursion handle any that is still too big.
            per_objective = max(1, planned // len(ws.objectives))
            group = max(1, limit // per_objective)
            return [
                piece
                for chunk in _chunks(list(ws.objectives), group)
                for piece in _split(WorkSet(
                    set_id="", objectives=tuple(chunk), pairs=(),
                    payload={**ws.payload,
                             "expected_activities": per_objective * len(chunk),
                             "assessment_items": sorted(
                                 {i for lo in chunk for i in items_by_lo.get(lo, [])})},
                    source=ws.source), limit)
            ]
        # ONE objective that alone needs more than a call can write: batches of
        # it, each carrying its own quota so the Developer knows how many of
        # the whole it is responsible for.
        batches = -(-planned // limit)
        # The planned total is DIVIDED across the batches, not repeated: at
        # limit 8 a plan of 10 is two batches of 5, never two of 8. Repeating
        # the ceiling would commission 16 activities for a job of 10.
        base, extra = divmod(planned, batches)
        return [
            WorkSet(set_id="", objectives=ws.objectives, pairs=(),
                    payload={**ws.payload,
                             "expected_activities": base + (1 if index <= extra else 0),
                             "batch": [index, batches]},
                    source=ws.source)
            for index in range(1, batches + 1)
        ]

    # The count cap is relative to the PLANNED ACTIVITIES, not to the number
    # of objectives. Objectives were the wrong base the moment the planner was
    # asked to emit several scoped blocks for an objective that needs more than
    # one call: at one block per objective the cap was 1, so two correctly
    # scoped blocks for ILO-01 were merged back into one and the themes that
    # kept them apart were discarded — the harness undoing exactly the work it
    # had asked for. You never need more blocks than activities.
    planned_total = sum(int(ws.payload.get("expected_activities") or 1) for ws in sets)
    numbered = _cap_and_number(sets, max(planned_total, len(los)), "AB", _merge,
                               family="activity", split=_split)
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    return numbered, stats


# ── content: material units, one per committed module (deterministic) ──────

def _expected_materials(raw: object, media_count: int) -> int:
    """How many materials a module's unit writes: the planner's own count on
    the module (``expected_materials``), clamped to ``[media, max_units]``,
    or the media count when it gave none.

    The count used to BE the media count — one material realizing each media
    selection — which left no way to say a broad module needs three documents
    where its media list names one. The floor stays one material per media
    selection (``RULES_MATERIALS_UNIT`` holds every selection to that) and
    the ceiling is the same per-call budget the split uses.
    """
    floor = max(1, media_count)
    ceiling = max(floor, max_units("material"))
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return floor
    return min(max(value, floor), ceiling)


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
        return number_sets([WorkSet(
            set_id="MU-ALL", payload={"modules": [], "media_selections": media_selections,
                                       "constraints": _constraints_for(media_selections),
                                       "expected_materials": _expected_materials(
                                           None, len(media_selections))},
            source="deterministic",
        )])

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

    # The planned quantity for a module is at least its MEDIA SELECTIONS:
    # ``RULES_MATERIALS_UNIT`` says a material's type/format must realize one of
    # the media selections given, so a module with eight of them is eight
    # materials — and materials are the longest element the harness writes.
    # One unit per module said nothing about that. Above that floor the
    # planner's own ``expected_materials`` on the module decides (a broad
    # module may need three documents where its media list names one).
    limit = max_units("material")
    sets: list[WorkSet] = []
    for module in modules:
        mid = _bare(module["id"])
        media_for_unit = by_module[mid] + unassigned
        batches = (_chunks(media_for_unit, limit)
                   if len(media_for_unit) > limit else [media_for_unit])
        for index, media_batch in enumerate(batches, start=1):
            # A module split over several batches is already at the ceiling
            # per batch; only an unsplit one has room for a planned count.
            planned = (_expected_materials(module.get("expected_materials"), len(media_batch))
                       if len(batches) == 1 else len(media_batch))
            sets.append(WorkSet(
                set_id=f"MU-{mid}" if len(batches) == 1 else f"MU-{mid}-{index:02d}",
                payload={"modules": [module], "media_selections": media_batch,
                         "constraints": _constraints_for(media_batch),
                         "expected_materials": planned},
                source="deterministic",
            ))

    if len(sets) > MAX_MATERIAL_UNITS:
        head, tail = sets[:MAX_MATERIAL_UNITS - 1], sets[MAX_MATERIAL_UNITS - 1:]
        merged_modules = [m for ws in tail for m in ws.payload["modules"]]
        merged_media = [m for ws in tail for m in ws.payload["media_selections"]]
        # The merged tail is split back down to what one call can answer.
        # Learner materials are the LONGEST element the harness produces
        # (~1,240 chars mean, 1,710 max, measured), so a tail carrying every
        # leftover module is the worst single call in the system.
        chunks = _chunks(merged_modules, limit)
        merged_sets = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_ids = {_bare(m["id"]) for m in chunk if m.get("id")}
            chunk_media = [m for m in merged_media
                           if not chunk_ids
                           or not {_bare(r) for r in (m.get("for_modules") or [])}
                           or {_bare(r) for r in (m.get("for_modules") or [])} & chunk_ids]
            merged_sets.append(WorkSet(
                set_id=f"MU-MERGED-{index:02d}" if len(chunks) > 1 else "MU-MERGED",
                payload={"modules": chunk, "media_selections": chunk_media,
                         "constraints": _constraints_for(chunk_media),
                         # A merged unit is the backstop: one material per
                         # module at least, one per media selection at least.
                         "expected_materials": min(max(len(chunk), len(chunk_media), 1), limit)},
                source="deterministic",
            ))
        sets = head + merged_sets
    # Numbered here rather than in `_cap_and_number`: this family does its own
    # module-aware cap above (which recomputes each chunk's media and
    # constraints), and the generic one would rewrite `MU-MOD-03` to `MU-03`.
    return number_sets(sets)


# ── implementation: session blocks over scheduled activities/materials ─────

#: Activities one delivery session carries when the plan does not say. A
#: backstop only: the planner is the one step that knows whether a session is a
#: single long workshop or a short class, and it is asked
#: (``expected_sessions``).
ACTIVITIES_PER_SESSION = 4


def _expected_sessions(raw: object, scheduled_count: int) -> int:
    """How many session guides one block writes: the planner's own count,
    clamped, or the deterministic estimate from what the block schedules."""
    fallback = max(1, -(-max(1, scheduled_count) // ACTIVITIES_PER_SESSION))
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    if value < 1:
        return fallback
    return min(value, MAX_EXPECTED_PER_SET)


def _scheduled(work_set: WorkSet) -> tuple[list[str], list[str]]:
    return (list(work_set.payload.get("activity_ids") or []),
            list(work_set.payload.get("material_ids") or []))


def _session_block(activities: list[str], materials: list[str], *, source: str,
                   theme: str = "", rationale: str = "", expected: object = None) -> WorkSet:
    return WorkSet(
        set_id="", objectives=(), pairs=(),
        payload={"activity_ids": activities, "material_ids": materials,
                 "block_theme": theme, "rationale": rationale,
                 "expected_sessions": _expected_sessions(
                     expected, len(activities) + len(materials))},
        source=source)


def _chunk_scheduled(activities: list[str], materials: list[str], limit: int,
                     *, source: str, theme: str = "") -> list[WorkSet]:
    """Break a stretch of delivery into blocks of at most ``limit`` scheduled
    artifacts, activities first. One combined list rather than two, so a block
    is bounded by what its Developer must actually name."""
    combined = [("a", i) for i in activities] + [("m", i) for i in materials]
    return [
        _session_block([i for kind, i in chunk if kind == "a"],
                       [i for kind, i in chunk if kind == "m"],
                       source=source, theme=theme)
        for chunk in _chunks(combined, max(1, limit))
    ] or []


def normalize_implementation_dev_plan(parsed, activity_ids, material_ids,
                                       first_session: int = 1
                                       ) -> tuple[list[WorkSet], dict]:
    """Divide the delivery into session blocks, one per Developer call.

    The GROUND TRUTH is every activity and every material the design holds, and
    the invariant this module upholds everywhere applies here too: each of them
    lands in exactly one returned block whatever the planner proposed. That is
    what makes P10/P11 coverage a function of a deterministic division rather
    than of whether a small model remembered to name 161 ids — which it cannot
    do in one submit and cannot even SEE in one read (``tools.render_listing``
    stops at ``READ_CHAR_BUDGET``).

    Assigning the work is not the same as fabricating the record: a block says
    which artifacts a Developer is responsible for scheduling, and the P10/P11
    edge still comes from the ``activity_ids`` that Developer wrote. Appending
    an id to a finished session guide to close a coverage gap is the thing
    ``audit.AUDIT_ONLY_VIOLATION_TYPES`` rules out, and nothing here does it.

    Blocks are also given their SESSION NUMBERS here (``first_session``), for
    the reason artifact ids are assigned by the harness: Developers never
    coordinate, so two of them left to number their own sessions both start at
    one. ``first_session`` is where this round's numbering begins — a replan
    round passes one past what the committed guides already use, for the same
    reason ``replan.tag_round`` strides the ordinal.
    """
    acts = [a for a in (_bare(x) for x in (activity_ids or [])) if a]
    mats = [m for m in (_bare(x) for x in (material_ids or [])) if m]
    stats = _empty_stats(len(acts) + len(mats))
    if not acts and not mats:
        return [], stats
    known_acts, known_mats = set(acts), set(mats)

    raw_blocks = (parsed or {}).get("session_blocks") if isinstance(parsed, dict) else None
    sets: list[WorkSet] = []
    claimed: set[str] = set()
    if isinstance(raw_blocks, list):
        for raw in raw_blocks:
            if not isinstance(raw, dict):
                continue
            valid: dict[str, list[str]] = {}
            for field_name, known in (("activity_ids", known_acts),
                                       ("material_ids", known_mats)):
                named = list(dict.fromkeys(
                    _bare(r) for r in (raw.get(field_name) or []) if _bare(r)))
                in_design = [r for r in named if r in known]
                stats["dropped_lo_refs"] += len(named) - len(in_design)
                # An id already claimed by an earlier block stays there. Two
                # blocks naming one activity is two Developers each writing
                # "the" session that delivers it, which nothing downstream
                # objects to because coverage asks "at least one".
                fresh = [r for r in in_design if r not in claimed]
                stats["duplicate_pairs"] += len(in_design) - len(fresh)
                valid[field_name] = fresh
            if not (valid["activity_ids"] or valid["material_ids"]):
                continue
            claimed.update(valid["activity_ids"] + valid["material_ids"])
            sets.append(_session_block(
                valid["activity_ids"], valid["material_ids"], source="llm",
                theme=str(raw.get("block_theme", "")),
                rationale=str(raw.get("rationale", "")),
                expected=raw.get("expected_sessions")))

    had_llm_sets = bool(sets)
    limit = max_units("session_guide")
    leftover_acts = [a for a in acts if a not in claimed]
    leftover_mats = [m for m in mats if m not in claimed]
    appended = _chunk_scheduled(leftover_acts, leftover_mats, limit,
                                source="appended" if had_llm_sets else "fallback")
    sets += appended
    stats["appended_sets"] = len(appended)
    stats["fallback_used"] = not had_llm_sets

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_acts = list(dict.fromkeys(a for ws in tail for a in _scheduled(ws)[0]))
        merged_mats = list(dict.fromkeys(m for ws in tail for m in _scheduled(ws)[1]))
        return _session_block(merged_acts, merged_mats, source=tail[-1].source)

    def _split(ws: WorkSet, size_limit: int) -> list[WorkSet]:
        activities, materials = _scheduled(ws)
        if len(activities) + len(materials) <= size_limit:
            return [ws]
        return _chunk_scheduled(activities, materials, size_limit,
                                source=ws.source,
                                theme=str(ws.payload.get("block_theme", "")))

    numbered = _cap_and_number(sets, max(len(acts) + len(mats), 1), "SB", _merge,
                               family="session_guide", split=_split)
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    return _number_sessions(numbered, first_session), stats


def _number_sessions(sets: list[WorkSet], first_session: int = 1) -> list[WorkSet]:
    """Give each block the session numbers it writes, running in plan order."""
    out: list[WorkSet] = []
    next_session = max(1, first_session)
    for ws in sets:
        activities, materials = _scheduled(ws)
        count = _expected_sessions(ws.payload.get("expected_sessions"),
                                   len(activities) + len(materials))
        out.append(replace(ws, payload={**ws.payload, "expected_sessions": count,
                                         "first_session": next_session}))
        next_session += count
    return out


# ── fan-in helpers: shared by every family's finalize step ─────────────────

def pending_set_ids(work_sets: list[WorkSet], payloads: list[dict]) -> list[str]:
    """Work-set ids with no committed items in any payload — the per-set
    regen signal at finalize: deterministic (reads payload shape only, no
    matcher/graph dependence), so it works identically on both substrates."""
    have = {str(p.get("set_id", "")) for p in payloads if p.get("items")}
    return [ws.set_id for ws in work_sets if ws.set_id not in have]


def _composite_id(prefix: str, ordinal: int, number: int, taken: set[str]) -> str:
    """``AT-0203``: prefix, the SET's ordinal, then the item's within that set.

    Unique by construction — two sets never share an ordinal — and dense: each
    set numbers its own artifacts from 1, so there are no gaps to explain. A
    single reserved range per set would leave them (set 1 stops at ``AT-10``
    and set 2 starts at ``AT-21``), and the gap is the block boundary showing
    through into the deliverable.

    It also says who wrote it: ``AT-0203`` is the third artifact of the second
    work set, which is the same fact ``plan_set`` carries and one an auditor
    reading the graph dump gets for free.

    The scan is the backstop for the two cases the composition does not cover
    on its own: a Developer that used one id twice inside its own set, and a
    replan round whose stride somehow lands on ordinals already in play."""
    while f"{prefix}-{ordinal:02d}{number:02d}" in taken:
        number += 1
    return f"{prefix}-{ordinal:02d}{number:02d}"


def remap_and_tag(work_sets: list[WorkSet], payloads: list[dict], *, id_field: str,
                   self_ref_fields: tuple[str, ...] = (), id_prefix: str = "",
                   taken: frozenset[str] = frozenset()) -> list[dict]:
    """Merge a family's Developer payloads (one per work set, each carrying
    ``{"set_id", "items": [...]}) into one flat, commit-ready item list.

    **The HARNESS names these artifacts; the model does not.** A Developer
    submits its items without an id, and each is named here by composing the
    SET's ordinal with the artifact's own — ``AT-0203`` is the third artifact of
    the second work set. Workers never coordinate, so two of them would
    otherwise propose the same name; pairing the ordinals makes the result
    unique BY CONSTRUCTION, decided when the plan was numbered rather than by
    which Developer committed first. It is dense — each set counts from 1 — and
    it says who wrote what, the same fact ``plan_set`` carries.

    Asking the model for an id was pure cost (2026-09-03): it was overwritten
    every time, so it bought nothing, while every malformed one (``AT-{``, a
    duplicate, an id copied out of the schema example) was a real failure. The
    field is gone from the schemas, which also shortens the artifact the model
    has to fit under the completion cap.

    ``self_ref_fields`` are references to OTHER artifacts of this same set,
    which the model writes as 1-based POSITIONS in the list it submitted ([1] =
    the first artifact it wrote) and which are resolved here into the assigned
    ids. Positional because the model has no ids to name — and this was broken
    before that change, for the same underlying reason: an activity's
    ``prerequisite_activities`` was never declared a reference field at all, so
    every one of them reached the graph naming an id the commit had renumbered
    away. Measured on the test fixture: 0 of 3 resolved, while ``_establish``
    reads exactly this field to build the ``precedes`` edges.

    CROSS-family references need nothing done to them and get nothing done:
    they name an upstream family that is already committed, which the Developer
    read in its final form.

    ``taken`` are the ids the design state already holds, so a set committed on
    its own lands where it would have in a batch. Every committed item is also stamped
    ``plan_set`` with its owning set's id — invisible to schemas/judges
    (unknown keys validate), and what ``pending_set_ids``-driven regen reads to
    tell which sets produced nothing.
    """
    payload_by_set: dict[str, list[dict]] = {}
    for p in payloads:
        payload_by_set.setdefault(str(p.get("set_id", "")), []).extend(
            i for i in (p.get("items") or []) if isinstance(i, dict))

    seen_ids: set[str] = set(taken)
    out: list[dict] = []
    for ws in work_sets:
        set_items = payload_by_set.get(ws.set_id, [])
        assigned: list[str] = []
        number = 1
        for item in set_items:
            if id_prefix:
                final_id = _composite_id(id_prefix, ws.ordinal, number, seen_ids)
                number = int(final_id.rsplit("-", 1)[1][-2:]) + 1
            else:
                # No declared convention for this family: the model's own id
                # stands, with the historical collision bump behind it.
                raw_id = str(item.get(id_field) or "")
                final_id = raw_id
                if final_id and final_id in seen_ids:
                    final_id = f"{raw_id}-{ws.set_id}"
            if final_id:
                seen_ids.add(final_id)
            assigned.append(final_id)

        for index, item in enumerate(set_items):
            new_item = dict(item)
            if assigned[index]:
                new_item[id_field] = assigned[index]
            for ref_field in self_ref_fields:
                refs = new_item.get(ref_field)
                if isinstance(refs, list):
                    new_item[ref_field] = _resolve_positions(refs, assigned)
            new_item["plan_set"] = ws.set_id
            out.append(new_item)
    return out


def _resolve_positions(refs: list, assigned: list[str]) -> list[str]:
    """1-based positions in the submitted list -> the ids assigned to them.

    Tolerant of the two things a model does instead: a position out of range
    (dropped — it names nothing) and a string that is already one of the
    assigned ids (kept, because it resolves). Anything else is DROPPED rather
    than passed through: a reference that does not resolve becomes a dangling
    edge in the graph the auditability claim rests on, and a silent drop shows
    up in the coverage numbers while a dangling id does not."""
    out: list[str] = []
    for ref in refs:
        if isinstance(ref, bool):
            continue
        if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
            position = int(ref)
            if 1 <= position <= len(assigned) and assigned[position - 1]:
                out.append(assigned[position - 1])
            continue
        if isinstance(ref, str) and ref in assigned:
            out.append(ref)
    return list(dict.fromkeys(out))


# ── rubric: one unit per committed assessment item (deterministic) ─────────

# ── work-set rendering: the "=== YOUR ASSIGNED ... ===" user-content block a
# Developer (multi arm) or a per-set state (single arm) shows the model.
# Pure text formatting, not part of the decomposition axis, so both arms
# import it from here rather than one borrowing the other's agent module.

def render_assessment_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"]
    if work_set.pairs:
        # The count is stated as a number, not left to be inferred from the
        # list length: the planner's `expected_items` (floor: one per pair),
        # so a Developer that writes fewer is visibly short rather than
        # plausibly done — and a set whose pairs were trimmed (a plan
        # promising a category its own `lo_coverage_targets` did not name)
        # says how many survived.
        count = _expected_items(work_set.payload.get("expected_items"), len(work_set.pairs))
        lines.append(f"write exactly {count} item{'' if count == 1 else 's'} — "
                     + ("one for each (objective x plan_category) pair below:"
                        if count == len(work_set.pairs) else
                        "covering every (objective x plan_category) pair below at least once:"))
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
    expected = work_set.payload.get("expected_activities")
    if expected:
        lines.append(f"how many activities to write: {expected}")
    batch = work_set.payload.get("batch")
    if batch:
        # The BACKSTOP path only. Scoping a set is the planner's job — it is
        # told the budget and asked to emit several blocks with distinct
        # `block_theme`s when an objective needs more than one call's worth,
        # precisely so two developers cannot be handed the same ground. This
        # fires when it did not, and then the best available scope is the
        # ordinal: without it the pieces carry identical assignments and write
        # the same activities twice, which the id remap would keep as both.
        index, total = batch
        stage = f" of '{theme}'" if theme else ""
        lines.append(
            f"this is part {index} of {total}{stage} for these objectives: write "
            f"{expected} activities covering only "
            f"{'the opening stage' if index == 1 else f'stage {index}'} of that "
            "progression. The other parts cover the other stages — do not repeat "
            "or restate them.")
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
        # The types THIS module chose, named as a list. The rules state the
        # closed vocabulary and the schema's exemplar is a placeholder, but
        # only the assignment knows which of them apply here — and that is
        # where the failure was: MEASURED (run 2b9e911a), all eight materials
        # came out `"type": "video", "format": "mp4"`, copied verbatim from the
        # schema example, against six media selections that were slides and
        # simulation. P6 failed 8/8. A small model follows the example it is
        # shown before the rule it is told.
        allowed = list(dict.fromkeys(
            str(s.get("media_type", "")).strip() for s in media
            if str(s.get("media_type", "")).strip()))
        if allowed:
            lines.append('allowed "type" values for this module: ' + ", ".join(allowed))
    # The count, stated as a number: the planner's `expected_materials` with
    # one per media selection as the floor. Before 2026-09-05 no count was
    # given at all, and the harness sized the unit as if one were.
    count = _expected_materials(work_set.payload.get("expected_materials"), len(media))
    lines.append(f"write exactly {count} material{'' if count == 1 else 's'}"
                 + (" — one realizing each media selection above:" if media and count == len(media)
                    else " — every media selection above realized by at least one:" if media
                    else " for this module:")
                 + (" each material's ``type`` is the ``media_type`` of the selection it "
                    "realizes." if media else ""))
    constraints = work_set.payload.get("constraints") or []
    if constraints:
        lines.append("constraints these media respect:")
        for constraint in constraints:
            lines.append(f"  [CONSTRAINT:{constraint.get('id', '')}] {json.dumps(constraint, ensure_ascii=False)}")
    return "\n".join(lines)


def render_session_set(work_set: WorkSet) -> str:
    first = int(work_set.payload.get("first_session") or 1)
    count = int(work_set.payload.get("expected_sessions") or 1)
    last = first + count - 1
    sessions = ", ".join(str(n) for n in range(first, last + 1))
    lines = [f"set_id: {work_set.set_id}",
             f"write exactly {count} session guide{'' if count == 1 else 's'}, "
             f"numbered {sessions} — those session numbers are yours, and another "
             "developer holds the rest."]
    activities, materials = _scheduled(work_set)
    if activities:
        lines.append("activities YOUR sessions deliver (every one must appear in the "
                     "``activity_ids`` of one of your guides):")
        lines.append("  " + ", ".join(activities))
    if materials:
        lines.append("materials YOUR sessions hand out (every one must appear in the "
                     "``material_ids`` of one of your guides):")
        lines.append("  " + ", ".join(materials))
    theme = work_set.payload.get("block_theme")
    if theme:
        lines.append(f"block_theme: {theme}")
    rationale = work_set.payload.get("rationale")
    if rationale:
        lines.append(f"rationale: {rationale}")
    return "\n".join(lines)
