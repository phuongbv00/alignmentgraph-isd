"""Dev-plan normalization: turns an LLM-proposed work grouping into a
deterministic list of :class:`WorkSet` fan-out units, or derives that list
outright where no LLM decision is needed (materials).

Substrate-agnostic on purpose: this module imports nothing from
``alignment_graph`` or ``prose_store`` so both context_mode arms call the
exact same normalization code over plain data. The one invariant every
function here upholds is that **the fan-out shape never depends on
unvalidated SLM output** — every ground-truth obligation (an
(objective, category) pair, an objective, a scheduled activity or material) that survives
normalization is guaranteed to appear in exactly one returned WorkSet, LLM
proposal or not. A parse-failed or empty dev-plan call degrades to the pure
fallback (one singleton set per obligation), never to zero sets.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace

#: A backstop, NOT a plan: the fan-out width is the agent's decision — it
#: proposes the grouping and this only stops a blow-up. One set per
#: obligation-unit is the other ceiling; a set may cover several.
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

    @property
    def module_id(self) -> str:
        """The course module this set is one share of, ``""`` for a set that
        belongs to none. Read off the payload, which is what every split and
        merge below copies, so a set cut in two keeps its module for free."""
        module = self.payload.get("module") or next(
            iter(self.payload.get("modules") or []), None)
        return str((module or {}).get("id") or "") if isinstance(module, dict) else ""

    def as_dict(self) -> dict:
        return {
            "set_id": self.set_id,
            "module_id": self.module_id,
            "objectives": list(self.objectives),
            "pairs": [list(p) for p in self.pairs],
            "payload": self.payload,
            "source": self.source,
            "ordinal": self.ordinal,
        }


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
    item as ``plan_set``, it is what ``fanout.committed_set_ids`` matches,
    and it is the only thing in the graph dump that says which module a
    material came from. Numbering and naming are two jobs: a family that
    cannot take the naming must still get its ordinal, or every one of its
    sets numbers from 1 and uniqueness rests on the ``taken`` scan alone."""
    return [replace(ws, set_id=f"{prefix}-{i:02d}" if prefix else ws.set_id, ordinal=i)
            for i, ws in enumerate(sets, start=1)]


def name_sets_after(sets: list[WorkSet], prefix: str, key) -> list[WorkSet]:
    """Rename each set after the design artifact it writes for — ``AS-INS-02``,
    ``AB-MOD-01`` — keeping the ordinal ``number_sets`` assigned.

    The ordinal is positional and composes every artifact id, so it has to
    stay; the set_id is what is READ — stamped on every element as
    ``plan_set``, matched by ``fanout.committed_set_ids``, and shown as the
    assignment's own header. Derived from the artifact rather than from the
    position, it says which instrument or module a committed element came
    from, and it is the same id every time the sets are derived again from
    the same design — which is what lets a second dispatch run only the sets
    that are new. ``material_work_units`` has named its sets this way
    (``MU-MOD-03``) since the modules arrived; this is that, for the three
    families whose plan the model used to write.

    A key several sets share (one instrument batched over several calls) gets
    a ``-01`` suffix on each, so the id stays unique without depending on how
    many batches there turned out to be for any other key."""
    counts: dict[str, int] = {}
    for ws in sets:
        counts[str(key(ws) or "")] = counts.get(str(key(ws) or ""), 0) + 1
    seen: dict[str, int] = {}
    named: list[WorkSet] = []
    for ws in sets:
        bare = _bare(key(ws)) or f"{ws.ordinal:02d}"
        raw = str(key(ws) or "")
        seen[raw] = seen.get(raw, 0) + 1
        suffix = f"-{seen[raw]:02d}" if counts[raw] > 1 else ""
        named.append(replace(ws, set_id=f"{prefix}-{bare}{suffix}"))
    return named


def _cap_and_number(sets: list[WorkSet], obligation_count: int, prefix: str,
                     merge: "callable", *, family: str,
                     split: "callable") -> list[WorkSet]:
    """Bound the fan-out from BOTH ends, then assign stable ``AS-01`` ids.

    Two bounds, and the order matters. The count cap
    (``MAX_SETS_HARD_CAP``) stops a blow-up in the number of
    calls by merging the overflow into one tail set. That merge is the danger:
    on a 33-objective scenario it produced a tail carrying 22 obligations in a
    SINGLE call — the cap on calls making the calls unanswerable.

    So the size bound is applied AFTER the merge and wins over the count. A set
    the model cannot finish costs everything it was going to produce, while an
    extra call costs one call.
    """
    cap = min(obligation_count, MAX_SETS_HARD_CAP)
    if len(sets) > cap:
        head, tail = sets[:cap - 1], sets[cap - 1:]
        sets = head + [merge(tail)]
    oversized = 0
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
    return [seq[i:i + size] for i in range(0, len(seq), size)]


# ── development mode: how much of the planned scale is written out ─────────
#
# The PLAN always states the course at full scale — a 40-item quiz, a module's
# whole run of activities. ``development_mode`` decides how much of that the
# Developers write: ``"full"`` is all of it, ``"sample"`` a representative
# sample. It changes NUMBERS in a work set's payload and one sentence of its
# assignment, never a ``RULES_*`` block, so the pinned prompts do not depend
# on it. Not an ablation axis: it is recorded in ``metadata.run_config`` and
# every arm of one experiment runs under the same value.

DEVELOPMENT_MODES = ("sample", "full")

#: What ``"sample"`` writes. PROVISIONAL parameters of this harness, chosen so
#: that a sampled design is not thinner than the baselines it is scored beside
#: on the rubric items judged by artifact count (assessment plan and items,
#: activity structure, learner materials): those agents are asked for at least
#: ten quiz items plus five others and deliver ten to fifteen. To be calibrated
#: on the tune slice — the same scenarios in both modes, compared per rubric
#: item — before the configuration is frozen, and not changed after.
SAMPLE_ITEMS_PER_INSTRUMENT = 3
SAMPLE_ACTIVITIES_PER_OBJECTIVE = 2
#: One module's activities read as a sequence — introduce, practise, apply —
#: and two do not make one.
SAMPLE_ACTIVITIES_PER_MODULE_FLOOR = 3
SAMPLE_MATERIALS_PER_MODULE = 2
SAMPLE_MINUTES_PER_SESSION_GUIDE = 180
SAMPLE_SESSION_GUIDES_PER_MODULE = 2

_SAMPLE_NOTES = {
    "assessment": (
        f"SAMPLE DEVELOPMENT: each instrument states its full scale in item_counts; write a "
        f"representative sample of it — about {SAMPLE_ITEMS_PER_INSTRUMENT} items per "
        "instrument, spread over its item types, and never fewer than one per (objective x "
        "plan_category) pair. Each item is written in full, as it would be administered."),
    "activity": (
        f"SAMPLE DEVELOPMENT: write a representative sample of the module's activities — about "
        f"{SAMPLE_ACTIVITIES_PER_OBJECTIVE} per objective and at least "
        f"{SAMPLE_ACTIVITIES_PER_MODULE_FLOOR} per module, a complete introduce, practise, "
        "apply sequence rather than a catalogue. Each activity is written in full."),
    "material": (
        f"SAMPLE DEVELOPMENT: write a representative sample of the module's materials — at most "
        f"{SAMPLE_MATERIALS_PER_MODULE} per module, each one complete and ready to hand to a "
        "learner."),
    "session_guide": (
        f"SAMPLE DEVELOPMENT: write one session guide per module, or "
        f"{SAMPLE_SESSION_GUIDES_PER_MODULE} for a module longer than "
        f"{SAMPLE_MINUTES_PER_SESSION_GUIDE} minutes — and still name EVERY activity and material "
        "id the block lists, because a guide is where each one is scheduled."),
}


def development_note(mode: str, family: str) -> str:
    """The one sentence that tells a writer its development is a sample, or
    ``""`` under ``"full"``. ONE wording for both decomposition arms: a
    Developer reads it in its assignment and the single agent in its stage
    turn (it divides its own batches, so the rule is all it is given)."""
    return _SAMPLE_NOTES.get(family, "") if mode == "sample" else ""


def _instrument_total(instrument: dict) -> int:
    counts = instrument.get("item_counts")
    total = 0
    for value in (counts.values() if isinstance(counts, dict) else ()):
        try:
            total += max(0, int(value))
        except (TypeError, ValueError):
            continue
    return total


def _planned_items(work_set: WorkSet, mode: str) -> int | None:
    """How many items a set's instruments call for under ``mode``; ``None``
    when the set lists no instrument and the pair count has to decide."""
    instruments = [i for i in (work_set.payload.get("instruments") or []) if isinstance(i, dict)]
    if not instruments:
        return None
    totals = [_instrument_total(i) or SAMPLE_ITEMS_PER_INSTRUMENT for i in instruments]
    if mode == "sample":
        totals = [min(total, SAMPLE_ITEMS_PER_INSTRUMENT) for total in totals]
    return max(sum(totals), len(work_set.pairs))


def _stamp_mode(sets: list[WorkSet], mode: str, family: str) -> None:
    for ws in sets:
        ws.payload["development_note"] = development_note(mode, family)


# ── the module is the key every family divides its work by ─────────────────
#
# The GROUND TRUTH of each family stays what its checks measure — pairs,
# objectives, scheduled ids — and every obligation still lands in exactly one
# set. What the modules change is the PARTITION: a set never spans two
# modules, and the sets come out in course order. A planner's own grouping is
# kept inside a module and cut where it crosses one.

def _module_brief(module: dict) -> dict:
    """What a work set carries of its module: enough to name it, to state its
    time, and to say which objectives it serves."""
    return {"id": _bare(module.get("id")), "title": str(module.get("title") or ""),
            "minutes": module.get("minutes"),
            "objectives": [_bare(o) for o in (module.get("objectives") or []) if _bare(o)]}


def _modules_in_order(modules) -> list[dict]:
    return [_module_brief(m) for m in (modules or [])
            if isinstance(m, dict) and _bare(m.get("id"))]


def _in_course_order(sets: list[WorkSet], modules: list[dict]) -> list[WorkSet]:
    order = {m["id"]: index for index, m in enumerate(modules)}
    return sorted(sets, key=lambda ws: order.get(ws.module_id, len(order)))


def _modules_of_objective(modules: list[dict]) -> dict[str, list[dict]]:
    by_lo: dict[str, list[dict]] = {}
    for module in modules:
        for lo in module["objectives"]:
            by_lo.setdefault(lo, []).append(module)
    return by_lo


def _pair_modules(pairs, modules: list[dict], instruments) -> dict[tuple[str, str], dict]:
    """The module each (objective, category) pair is written in: the module of
    the first instrument that assesses that objective at that timing, else the
    first module that serves the objective, else the course's last module —
    an objective no module serves is a P12 finding already, and its items
    still have to be written somewhere."""
    by_id = {m["id"]: m for m in modules}
    by_lo = _modules_of_objective(modules)
    from_instrument: dict[tuple[str, str], dict] = {}
    for instrument in instruments or []:
        if not isinstance(instrument, dict):
            continue
        module = by_id.get(_bare(instrument.get("module_id")))
        timing = str(instrument.get("timing") or "").strip().lower()
        for lo in instrument.get("covers_objectives") or []:
            if module is not None:
                from_instrument.setdefault((_bare(lo), timing), module)
    return {pair: from_instrument.get(pair) or next(iter(by_lo.get(pair[0], [])), modules[-1])
            for pair in pairs}


def _instruments_for(instruments, module_id: str, pairs) -> list[dict]:
    """The module's instruments that assess any of ``pairs``."""
    wanted = set(pairs)
    return [dict(i) for i in (instruments or []) if isinstance(i, dict)
            and _bare(i.get("module_id")) == module_id
            and any((_bare(lo), str(i.get("timing") or "").strip().lower()) in wanted
                    for lo in i.get("covers_objectives") or [])]


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


def instrument_pairs(instruments) -> list[tuple[str, str]]:
    """The (objective, category) pairs the plan's INSTRUMENTS assess: every
    objective an instrument covers, at that instrument's ``timing``. Bare ids
    and valid categories only, first-seen order, no repeats.

    ONE reader, shared with ``checks.instrument_pairs``: the check reports a
    promised pair these do not cover (``unassessed_pair``) and this decides
    what the fan-out divides, so a pair the two disagreed about would be
    called assessed and still reach no Developer."""
    pairs: list[tuple[str, str]] = []
    for instrument in (instruments or []):
        if not isinstance(instrument, dict):
            continue
        timing = str(instrument.get("timing") or "").strip().lower()
        if timing not in _VALID_CATEGORIES:
            continue
        for ref in instrument.get("covers_objectives") or []:
            pair = (_bare(ref), timing)
            if pair[0] and pair not in pairs:
                pairs.append(pair)
    return pairs


def _assessment_ground_truth_pairs(lo_ids, coverage_targets,
                                   instruments=None) -> list[tuple[str, str]]:
    """What the fan-out divides: the pairs the INSTRUMENTS assess.

    ``lo_coverage_targets`` is the model's PROMISE, not the work. The two are
    held together by ``checks.blueprint_consistency``, which reports a promise
    no instrument keeps (``unassessed_pair``) while the plan is still the only
    thing written and the Designer can add the instrument.

    Reading the promise HERE instead made such a pair a work set of its own
    with no instrument in it, and ``render_assessment_set`` drops the whole
    "set each item's ``instrument_id`` to one of these ids" block for a set
    that lists none — so its Developer was shown no instrument and reached for
    the only id-shaped string left in its assignment, the set's own header.
    MEASURED (run 50932ed8): three summative instruments against nine promised
    pairs, six pairs appended into three instrument-less sets, items committed
    with ``instrument_id`` "AS-02", "AS-04" and "MOD-03", and every one of the
    run's seven residual violations was the ``instrument_alignment`` that
    followed. Now an appended set is always a slice of some instrument's own
    pairs, so it can never be instrument-less.

    The promise is still the fallback for a plan that carries no instrument at
    all — an archived design from before the blueprint, or one whose
    ``instruments`` never landed."""
    pairs = instrument_pairs(instruments)
    if not pairs:
        pairs = plan_category_pairs(coverage_targets)
    if not pairs:
        pairs = [(lo, "summative") for lo in (_bare(x) for x in (lo_ids or [])) if lo]
    return list(dict.fromkeys(pairs))  # de-dup, order-preserving


def normalize_assessment_dev_plan(parsed, lo_ids, coverage_targets, *, modules=None,
                                  instruments=None, mode: str = "full"
                                  ) -> tuple[list[WorkSet], dict]:
    modules = _modules_in_order(modules)
    pairs = _assessment_ground_truth_pairs(lo_ids, coverage_targets, instruments)
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
            # A set names the INSTRUMENTS it writes, and its pairs are theirs:
            # every objective an instrument covers, at that instrument's
            # timing. ``objectives`` x ``plan_categories`` is the older way of
            # saying the same thing and is still read, so a plan written either
            # way divides the same work.
            named = {_bare(i) for i in (raw.get("instrument_ids") or []) if _bare(i)}
            candidate = [
                (_bare(lo), str(instrument.get("timing") or "").strip().lower())
                for instrument in (instruments or [])
                if isinstance(instrument, dict) and _bare(instrument.get("id")) in named
                for lo in instrument.get("covers_objectives") or []]
            stats["dropped_lo_refs"] += len(
                named - {_bare(i.get("id")) for i in (instruments or []) if isinstance(i, dict)})
            objs = [_bare(o) for o in (raw.get("objectives") or []) if _bare(o)]
            stats["dropped_lo_refs"] += sum(1 for o in objs if o not in known_los)
            cats = [str(c or "").strip().lower() for c in (raw.get("plan_categories") or [])]
            cats = [c for c in cats if c in _VALID_CATEGORIES]
            candidate += [(lo, cat) for lo in objs for cat in cats]
            if not candidate:
                continue
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

    if modules:
        # Cut every set where it crosses a module, then put one module's
        # leftovers together: with modules, the unit a Developer writes for is
        # a module's instruments, not one objective's.
        where = _pair_modules(pairs, modules, instruments)
        pieces: list[WorkSet] = []
        loose: dict[str, list[tuple[str, str]]] = {}
        for ws in sets:
            by_module: dict[str, list[tuple[str, str]]] = {}
            for pair in ws.pairs:
                by_module.setdefault(where[pair]["id"], []).append(pair)
            for module_id, module_pairs in by_module.items():
                if ws.source != "llm":
                    loose.setdefault(module_id, []).extend(module_pairs)
                    continue
                payload = dict(ws.payload)
                if len(by_module) > 1:
                    payload.pop("expected_items", None)   # it counted the whole set
                pieces.append(WorkSet(
                    set_id="", pairs=tuple(module_pairs), source="llm", payload=payload,
                    objectives=tuple(dict.fromkeys(lo for lo, _ in module_pairs))))
        pieces += [WorkSet(set_id="", pairs=tuple(module_pairs), source=src, payload={},
                           objectives=tuple(dict.fromkeys(lo for lo, _ in module_pairs)))
                   for module_pairs in loose.values()]
        by_id = {m["id"]: m for m in modules}
        for ws in pieces:
            module = where[ws.pairs[0]]
            ws.payload["module"] = by_id[module["id"]]
            ws.payload["instruments"] = _instruments_for(instruments, module["id"], ws.pairs)
        sets = _in_course_order(pieces, modules)
        stats["appended_sets"] = len(loose)
        sets = [batch for ws in sets for batch in _item_batches(ws, mode)]

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

    numbered = _cap_and_number(sets, max(len(pairs), len(sets)), "AS", _merge,
                               family="assessment", split=_split)
    # A merged or split set carries a payload copied from one of its parts, so
    # its planned count no longer describes its pairs; re-derive it from what
    # the set actually holds. Also fills the count in for appended/fallback
    # sets, whose payload is empty.
    for ws in numbered:
        ws.payload["expected_items"] = _expected_items(
            ws.payload.get("expected_items"), len(ws.pairs))
    _stamp_mode(numbered, mode, "assessment")
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    return numbered, stats


def _item_batches(work_set: WorkSet, mode: str) -> list[WorkSet]:
    """Size a set by what its INSTRUMENTS call for under ``mode``.

    ``"sample"`` writes a few items of each instrument and fits one call.
    ``"full"`` writes every item the blueprint counts, which for a 40-item
    quiz is several calls: the set becomes batches, each with its own quota
    (the total is DIVIDED between them, never repeated) and its own share of
    the pairs, and each told which part of the whole it is. A set that lists
    no instrument keeps the planner's count."""
    planned = _planned_items(work_set, mode)
    if planned is None:
        return [work_set]
    limit = max_units("assessment")
    if planned <= limit:
        work_set.payload["expected_items"] = planned
        return [work_set]
    batches = -(-planned // limit)
    base, extra = divmod(planned, batches)
    out: list[WorkSet] = []
    for index in range(1, batches + 1):
        quota = base + (1 if index <= extra else 0)
        # Every batch covers every pair when it has room to; otherwise the
        # pairs are dealt out, so between them the batches still cover all.
        pairs = (work_set.pairs if len(work_set.pairs) <= quota
                 else work_set.pairs[index - 1::batches])
        out.append(replace(
            work_set, pairs=tuple(pairs),
            objectives=tuple(dict.fromkeys(lo for lo, _ in pairs)),
            payload={**work_set.payload, "expected_items": quota, "batch": [index, batches]}))
    return [ws for ws in out if ws.pairs]


def _expected_items(raw: object, pair_count: int) -> int:
    """How many items an instrument set writes: the planner's own count,
    clamped to ``[pairs, max_units]``, or the pair count when it gave none.

    The pair count alone left the planner no way to say an instrument needs
    three items on one objective. The floor is one item per pair (``checks.plan_coverage`` holds every pair to that) and the
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


#: The shortest stretch of learner time one activity is planned in. NOT a
#: pedagogical claim — a declared parameter of the harness, like the turn
#: ceilings — and the only number the time budget needs: the budget itself is
#: the Outcome Designer's (each module's ``minutes``), because the brief states
#: a course's length only as a band ("2-4 weeks", "1-6 months") and never its
#: hours.
MIN_ACTIVITY_MINUTES = 15


def _positive(raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def fit_time_budget(sets: list[WorkSet], modules: list[dict], stats: dict) -> None:
    """Hold the planned activities to the time their MODULE has.

    Objective count does not bound an activity plan; learner time does, and
    the time is the Outcome Designer's: each module states its ``minutes``.
    The blocks of one module share that budget — their ``block_minutes`` are
    read as PROPORTIONS of it, scaled to add up to what the module has —
    and a block may plan at most one activity per ``MIN_ACTIVITY_MINUTES`` of
    its share, never fewer than one.

    MEASURED, what an unbounded plan costs: on run 1c0a4e81 the planner wrote
    ``expected_activities`` as a counting sequence (2, 3, 4 … across 33 blocks),
    the per-block clamp let 94 activities through for 5 objectives, their
    Developers were a third of the run's calls, the content stage could not
    cover them (88 activities no content supported) and the delivery plan fell
    back to a deterministic split of 96 scheduled artifacts.

    A set that belongs to no module, or to one that states no time, is left as
    it was and the record says so (``stats["time_budget"]["unbudgeted_sets"]``)
    rather than being held to a number the harness made up."""
    planned = sum(int(ws.payload.get("expected_activities") or 1) for ws in sets)
    stats["planned_activities"] = planned
    minutes_of = {m["id"]: _positive(m.get("minutes")) for m in modules}
    unbudgeted = 0
    for module_id in dict.fromkeys(ws.module_id for ws in sets):
        mine = [ws for ws in sets if ws.module_id == module_id]
        budget = minutes_of.get(module_id, 0.0)
        if not budget:
            unbudgeted += len(mine)
            continue
        declared = [_positive(ws.payload.get("block_minutes")) for ws in mine]
        # A block that named no minutes gets an even share of what is left.
        spoken = sum(declared)
        silent = declared.count(0.0)
        even = max(0.0, budget - spoken) / silent if silent else 0.0
        shares = [d or even for d in declared]
        # The blocks of a module PARTITION its time, so their shares are
        # normalized to it in both directions: scaled down when together they
        # overrun it, and up when they leave it unspent. MEASURED (run
        # 40856c96): each module's only block declared 15 of its module's
        # 100-120 minutes, which held every module to one activity.
        scale = budget / sum(shares) if sum(shares) else 1.0
        for ws, share in zip(mine, shares):
            fits = max(1, int(share * scale) // MIN_ACTIVITY_MINUTES)
            ws.payload["block_minutes"] = int(share * scale)
            ws.payload["expected_activities"] = min(
                int(ws.payload.get("expected_activities") or 1), fits)
    fitted = sum(int(ws.payload.get("expected_activities") or 1) for ws in sets)
    stats["time_budget"] = {"module_minutes": sum(minutes_of.values()),
                            "unbudgeted_sets": unbudgeted, "trimmed": planned - fitted}


def normalize_activity_dev_plan(parsed, lo_ids, items_by_lo: dict | None = None, *,
                                modules=None, mode: str = "full"
                                ) -> tuple[list[WorkSet], dict]:
    modules = _modules_in_order(modules)
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
                payload={"planned_module": _bare(raw.get("module_id")),
                         "assessment_items": items, "block_theme": str(raw.get("block_theme", "")),
                         "rationale": str(raw.get("rationale", "")),
                         "block_minutes": raw.get("block_minutes"),
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

    if modules:
        sets = _activity_sets_by_module(sets, modules, items_by_lo, src)
        stats["appended_sets"] = sum(1 for ws in sets if ws.source != "llm")
    for ws in sets:
        ws.payload.pop("planned_module", None)
    if mode == "sample":
        _sample_activities(sets)

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_objs = tuple(dict.fromkeys(o for ws in tail for o in ws.objectives))
        merged_items = sorted({i for ws in tail for i in ws.payload.get("assessment_items", [])})
        return WorkSet(set_id="", objectives=merged_objs, pairs=(),
                        payload={"assessment_items": merged_items, "block_theme": "", "rationale": "",
                                 **({"module": tail[-1].payload["module"]}
                                    if tail[-1].payload.get("module") else {})},
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
    fit_time_budget(sets, modules, stats)
    planned_total = sum(int(ws.payload.get("expected_activities") or 1) for ws in sets)
    numbered = _cap_and_number(sets, max(planned_total, len(los)), "AB", _merge,
                               family="activity", split=_split)
    _stamp_mode(numbered, mode, "activity")
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    return numbered, stats


def _sample_activities(sets: list[WorkSet]) -> None:
    """``"sample"``: a block writes ``SAMPLE_ACTIVITIES_PER_OBJECTIVE`` per
    objective it covers, and a module never fewer than
    ``SAMPLE_ACTIVITIES_PER_MODULE_FLOOR`` between its blocks. The module's
    minutes still cap it (``fit_time_budget`` runs after this)."""
    for ws in sets:
        ws.payload["expected_activities"] = min(
            MAX_EXPECTED_PER_SET, SAMPLE_ACTIVITIES_PER_OBJECTIVE * max(1, len(ws.objectives)))
    for module_id in dict.fromkeys(ws.module_id for ws in sets):
        mine = [ws for ws in sets if ws.module_id == module_id]
        short = SAMPLE_ACTIVITIES_PER_MODULE_FLOOR - sum(
            ws.payload["expected_activities"] for ws in mine)
        if module_id and short > 0:
            mine[0].payload["expected_activities"] += short


def _activity_sets_by_module(sets: list[WorkSet], modules: list[dict],
                             items_by_lo: dict, leftover_source: str) -> list[WorkSet]:
    """Cut every block where it crosses a module, and gather one module's
    unplanned objectives into one block.

    An objective that several modules serve is practised in each of them — the
    module's share of it — so a block's objectives are intersected with each
    module's own list. Its planned count and minutes are divided between the
    pieces in proportion to the objectives each keeps, never repeated. An
    objective no module serves goes to the course's last module: that it has
    none is a P12 finding already, and its activities still have to be written
    somewhere."""
    served = _modules_of_objective(modules)

    def homes(lo: str, planned: str = "") -> list[dict]:
        """Where an objective's activities are written. A block that names its
        module is taken at its word for the objectives that module serves — the
        planner deciding WHICH module's share of a shared objective this block
        is — and is cut by membership for the rest."""
        mine = served.get(lo) or [modules[-1]]
        chosen = [m for m in mine if m["id"] == planned]
        return chosen or mine

    pieces: list[WorkSet] = []
    loose: dict[str, list[str]] = {}
    for ws in sets:
        by_module: dict[str, list[str]] = {}
        planned = str(ws.payload.pop("planned_module", "") or "")
        for lo in ws.objectives:
            for module in homes(lo, planned):
                by_module.setdefault(module["id"], []).append(lo)
        total = sum(len(objs) for objs in by_module.values()) or 1
        for module_id, objs in by_module.items():
            if ws.source != "llm":
                loose.setdefault(module_id, []).extend(o for o in objs
                                                       if o not in loose.get(module_id, []))
                continue
            payload = dict(ws.payload)
            if len(by_module) > 1:
                share = len(objs) / total
                payload["expected_activities"] = max(
                    1, round(int(payload.get("expected_activities") or 1) * share))
                if _positive(payload.get("block_minutes")):
                    payload["block_minutes"] = int(_positive(payload["block_minutes"]) * share)
                payload["assessment_items"] = sorted(
                    {i for lo in objs for i in items_by_lo.get(lo, [])})
            pieces.append(WorkSet(set_id="", objectives=tuple(objs), pairs=(),
                                  payload=payload, source="llm"))
            pieces[-1].payload["module"] = next(m for m in modules if m["id"] == module_id)
    for module_id, objs in loose.items():
        covered = {lo for ws in pieces if ws.module_id == module_id for lo in ws.objectives}
        objs = [lo for lo in objs if lo not in covered]
        if not objs:
            continue
        pieces.append(WorkSet(
            set_id="", objectives=tuple(objs), pairs=(), source=leftover_source,
            payload={"assessment_items": sorted({i for lo in objs for i in items_by_lo.get(lo, [])}),
                     "block_theme": "", "rationale": "",
                     "expected_activities": _expected(None, len(objs)),
                     "module": next(m for m in modules if m["id"] == module_id)}))
    return _in_course_order(pieces, modules)


# ── modules: how many a course carries ──────────────────────────────────────

#: Ceiling on modules by course length: three for a course within a week
#: (30 instructional hours), four up to a month (120), six beyond. A PARAMETER
#: OF THIS HARNESS, not a finding from the literature — a module is taken to
#: be about one sitting of an intensive course and about one week of a long
#: one, and the top value mirrors ``rulebook.MAX_OBJECTIVES``. The other two
#: bounds of :func:`module_ceiling` do have a warrant: a module must own at
#: least one objective (module-level objectives map onto course objectives)
#: and is one cluster of the instructional analysis (Dick & Carey), so there
#: are never more modules than objectives or than topics. TOLD to the Outcome
#: Designer — as a rule in ``rulebook.RULES_COURSE_MODULES`` and as this run's
#: number in its state read — and never enforced, for the reasons
#: ``MAX_OBJECTIVES`` is not.
MODULES_BY_COURSE_HOURS = ((30, 3), (120, 4))
MAX_MODULES = 6
#: The ceiling for a course whose length cannot be read off the brief.
MODULES_UNKNOWN_LENGTH = 4


def module_ceiling(n_objectives: int, n_topics: int, hours: float) -> int:
    """``min(objectives, topics, by course length)``, never below 1. A count
    of zero is "not known yet" (the stage has not written them) and does not
    bind."""
    by_length = MODULES_UNKNOWN_LENGTH
    if hours > 0:
        by_length = next((n for limit, n in MODULES_BY_COURSE_HOURS if hours <= limit),
                         MAX_MODULES)
    bounds = [by_length] + [n for n in (n_objectives, n_topics) if n > 0]
    return max(1, min(bounds))


# ── content: material units, one per committed module (deterministic) ──────

def _expected_materials(raw: object, media_count: int) -> int:
    """How many materials a module's unit writes: the planner's own count on
    the module (``expected_materials``), clamped to ``[media, max_units]``,
    or the media count when it gave none.

    The media count alone left no way to say a broad module needs three
    documents where its media list names one. The floor is one material per media
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
                         constraints: list[dict] | None = None, *,
                         mode: str = "full") -> list[WorkSet]:
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
        if mode == "sample":
            # The unit realises what it is handed, one material per selection,
            # so a sample is the module's first few selections.
            media_for_unit = media_for_unit[:SAMPLE_MATERIALS_PER_MODULE]
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
    _stamp_mode(sets, mode, "material")
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
                   theme: str = "", rationale: str = "", expected: object = None,
                   module: dict | None = None) -> WorkSet:
    return WorkSet(
        set_id="", objectives=(), pairs=(),
        payload={"activity_ids": activities, "material_ids": materials,
                 "block_theme": theme, "rationale": rationale,
                 "expected_sessions": _expected_sessions(
                     expected, len(activities) + len(materials)),
                 **({"module": module} if module else {})},
        source=source)


def _chunk_scheduled(activities: list[str], materials: list[str], limit: int,
                     *, source: str, theme: str = "",
                     module: dict | None = None) -> list[WorkSet]:
    """Break a stretch of delivery into blocks of at most ``limit`` scheduled
    artifacts, activities first. One combined list rather than two, so a block
    is bounded by what its Developer must actually name."""
    combined = [("a", i) for i in activities] + [("m", i) for i in materials]
    return [
        _session_block([i for kind, i in chunk if kind == "a"],
                       [i for kind, i in chunk if kind == "m"],
                       source=source, theme=theme, module=module)
        for chunk in _chunks(combined, max(1, limit))
    ]


def normalize_implementation_dev_plan(parsed, activity_ids, material_ids,
                                       first_session: int = 1, *, modules=None,
                                       module_of: dict | None = None, mode: str = "full"
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
    modules = _modules_in_order(modules)
    module_of = {_bare(k): _bare(v) for k, v in (module_of or {}).items()}
    by_id = {m["id"]: m for m in modules}

    def home(artifact: str) -> dict | None:
        """The module an activity or a material was written for (its own
        ``module_id`` / ``linked_module``); one naming none that exists is
        delivered with the course's last module."""
        if not modules:
            return None
        return by_id.get(module_of.get(artifact, "")) or modules[-1]

    def by_module(ids: list[str]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for artifact in ids:
            module = home(artifact)
            out.setdefault(module["id"] if module else "", []).append(artifact)
        return out

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
            # A block is delivered inside ONE module; one that crosses a
            # module boundary is cut there, and its session count is
            # re-derived for each piece rather than repeated.
            acts_in, mats_in = by_module(valid["activity_ids"]), by_module(valid["material_ids"])
            crossing = len(set(acts_in) | set(mats_in)) > 1
            for module_id in dict.fromkeys(list(acts_in) + list(mats_in)):
                sets.append(_session_block(
                    acts_in.get(module_id, []), mats_in.get(module_id, []), source="llm",
                    theme=str(raw.get("block_theme", "")),
                    rationale=str(raw.get("rationale", "")),
                    expected=None if crossing else raw.get("expected_sessions"),
                    module=by_id.get(module_id)))

    had_llm_sets = bool(sets)
    limit = max_units("session_guide")
    leftover_acts = [a for a in acts if a not in claimed]
    leftover_mats = [m for m in mats if m not in claimed]
    left_acts, left_mats = by_module(leftover_acts), by_module(leftover_mats)
    appended = [
        block
        for module_id in dict.fromkeys(list(left_acts) + list(left_mats))
        for block in _chunk_scheduled(
            left_acts.get(module_id, []), left_mats.get(module_id, []), limit,
            source="appended" if had_llm_sets else "fallback", module=by_id.get(module_id))]
    sets += appended
    sets = _in_course_order(sets, modules) if modules else sets
    stats["appended_sets"] = len(appended)
    stats["fallback_used"] = not had_llm_sets

    def _merge(tail: list[WorkSet]) -> WorkSet:
        merged_acts = list(dict.fromkeys(a for ws in tail for a in _scheduled(ws)[0]))
        merged_mats = list(dict.fromkeys(m for ws in tail for m in _scheduled(ws)[1]))
        return _session_block(merged_acts, merged_mats, source=tail[-1].source,
                              module=tail[-1].payload.get("module"))

    def _split(ws: WorkSet, size_limit: int) -> list[WorkSet]:
        activities, materials = _scheduled(ws)
        if len(activities) + len(materials) <= size_limit:
            return [ws]
        return _chunk_scheduled(activities, materials, size_limit,
                                source=ws.source,
                                theme=str(ws.payload.get("block_theme", "")),
                                module=ws.payload.get("module"))

    numbered = _cap_and_number(sets, max(len(acts) + len(mats), 1), "SB", _merge,
                               family="session_guide", split=_split)
    stats["set_count"] = len(numbered)
    stats["oversized_splits"] = (
        numbered[0].payload.pop("_oversized_splits", 0) if numbered else 0)
    if mode == "sample":
        _sample_sessions(numbered)
    _stamp_mode(numbered, mode, "session_guide")
    return _number_sessions(numbered, first_session), stats


def _sample_sessions(sets: list[WorkSet]) -> None:
    """``"sample"``: one guide per block, or up to
    ``SAMPLE_SESSION_GUIDES_PER_MODULE`` when the block is a whole module
    longer than ``SAMPLE_MINUTES_PER_SESSION_GUIDE``. The ids a block schedules
    are untouched — a sampled guide still names every one of them."""
    per_module: dict[str, int] = {}
    for ws in sets:
        per_module[ws.module_id] = per_module.get(ws.module_id, 0) + 1
    for ws in sets:
        minutes = _positive((ws.payload.get("module") or {}).get("minutes"))
        long_module = per_module[ws.module_id] == 1 and minutes > SAMPLE_MINUTES_PER_SESSION_GUIDE
        ws.payload["expected_sessions"] = (
            SAMPLE_SESSION_GUIDES_PER_MODULE if long_module else 1)


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


# ── a work set writes what it was commissioned for, and no more ────────────

#: The payload key that states each family's count, by the output it sizes.
_QUOTA_KEY = {"assessment_tools": "expected_items", "learning_activities": "expected_activities",
              "learner_materials": "expected_materials", "session_guides": "expected_sessions"}
#: The field a repeated artifact repeats, per output.
_SAME_AS = {"assessment_tools": "question", "learning_activities": "activity_name",
            "learner_materials": "title"}


def with_membership(work_set: WorkSet, schema_key: str, items: list) -> list:
    """``items`` with the membership id each one LEFT OUT, where the set it
    was written in settles it — new dicts, the submitted ones untouched.

    An activity written in a module's block belongs to that module; an item
    written in a set that lists one instrument, or exactly one instrument of
    the item's own objective and category, belongs to that instrument. Those
    are lookups, and refusing the submit over them costs what a lookup does
    not: MEASURED (run 53a9cd1a), five refusals and a give-up-and-regen for
    `instrument_id` on sets that each listed a single instrument. Only a
    MISSING id is filled. One the model wrote is left as written, right or
    wrong — that is what P13 and ``instrument_alignment`` measure — and an
    item with several candidates is left without one for the validator."""
    if schema_key == "learning_activities" and work_set.module_id:
        return [{**item, "module_id": work_set.module_id}
                if isinstance(item, dict) and not str(item.get("module_id") or "").strip()
                else item for item in items]
    instruments = [i for i in (work_set.payload.get("instruments") or []) if isinstance(i, dict)]
    if schema_key != "assessment_tools" or not instruments:
        return items
    out = []
    for item in items:
        if isinstance(item, dict) and not str(item.get("instrument_id") or "").strip():
            lo = _bare(item.get("aligned_objective"))
            category = str(item.get("plan_category") or "").strip().lower()
            fits = [i for i in instruments
                    if str(i.get("timing") or "").strip().lower() == category
                    and lo in {_bare(o) for o in i.get("covers_objectives") or []}]
            pick = fits if len(fits) == 1 else instruments if len(instruments) == 1 else []
            if pick:
                item = {**item, "instrument_id": _bare(pick[0].get("id"))}
        out.append(item)
    return out


def quota_of(work_set: WorkSet, schema_key: str) -> int:
    """The count a set's assignment states for ``schema_key``; 0 for none."""
    try:
        return max(0, int(work_set.payload.get(_QUOTA_KEY.get(schema_key, "")) or 0))
    except (TypeError, ValueError):
        return 0


def short_of_quota(work_set: WorkSet, schema_key: str, items: list) -> str:
    """What a work set still owes of the count its assignment stated: the
    sentence that asks for it, or ``""`` when nothing is owed.

    The other half of :func:`trim_to_quota`, and an INSTALMENT notice rather
    than a rejection (``AgenticStep.owes``): what arrived is kept and the next
    submit is joined to it. MEASURED, both ways of getting this wrong. Run
    40856c96: three sets told "write exactly 3 items" each submitted ONE, were
    answered COMMITTED, and the design shipped five items for instruments
    planned at twenty-five. Run ae81359a, with the short submit REFUSED instead:
    a 2B model that writes one item per call resent its one item — 14 refusals
    of this kind, sets giving up after four calls and being regenerated up to
    three times, because a refusal asks for the whole list again under the
    same cap that produced one item. Session guides are exempt: how many
    sessions a block takes is the writer's to say, and what it owes is every
    id, which its own validator holds it to."""
    quota = quota_of(work_set, schema_key)
    if schema_key == "session_guides" or not quota or len(items) >= quota:
        return ""
    more = quota - len(items)
    return (f"KEPT: {len(items)} of the {quota} this set asks for are written and saved — do "
            f"NOT send them again. Send ONLY {more} more DIFFERENT "
            f"one{'' if more == 1 else 's'} now, in the same tool; "
            f"{'it is' if more == 1 else 'they are'} added to what is kept.")


def same_artifact_key(schema_key: str, item: object) -> str:
    """What makes two artifacts of one list THE SAME artifact: the field a
    repeat repeats (``question`` / ``activity_name`` / ``title``), case and
    spacing aside — and for an assessment item its objective and category too,
    since the same words asked of another objective are another item. An
    artifact with no such field is the same only when it is identical. ONE
    definition, for the trim and for joining instalments: an item that would
    be dropped as a repeat at commit must not count towards the set's quota
    on the way there."""
    name = _SAME_AS.get(schema_key)
    text = " ".join(str((item or {}).get(name) or "").casefold().split()) \
        if name and isinstance(item, dict) else ""
    if not text:
        return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    if schema_key == "assessment_tools":
        text += f"|{_bare(item.get('aligned_objective'))}|{item.get('plan_category', '')}"
    return text


def without_repeats(schema_key: str, items: list, *, beside: list | None = None) -> list:
    """``items`` minus any that repeats an earlier one of the list or one of
    ``beside`` (what is already kept), first occurrence winning."""
    seen = {same_artifact_key(schema_key, item) for item in (beside or [])}
    out = []
    for item in items:
        key = same_artifact_key(schema_key, item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def trim_to_quota(work_set: WorkSet, schema_key: str, items: list) -> tuple[list, int]:
    """Hold a set to the count its assignment stated: ``(kept, dropped)``.

    "Write exactly N" is told to the Developer and was enforced by nobody.
    MEASURED (run aef73e0a, sample mode): a set told to write 3 items submitted
    17 — three of them word-for-word repeats — another told 3 activities wrote
    15, and a block told one session guide wrote eight that each scheduled the
    same eleven activities. One module then held 15 of the design's 24
    activities, and the whole point of a stated scale was gone.

    Dropping is not writing: nothing is invented and what is kept is the
    model's own, in its own order. What is NEVER dropped is what a check
    measures — the first item of every (objective, category) pair the set
    owes, and any session guide that schedules an id no kept guide does. A
    repeat (same ``question`` / ``activity_name`` / ``title``) goes first. A
    family with positional references keeps a PREFIX, so ``[2]`` still means
    the second activity. A set that states no count (the single arm's own
    batches) is left as written."""
    quota = quota_of(work_set, schema_key)
    rows = [item for item in items if isinstance(item, dict)]
    if quota <= 0 or len(rows) <= quota:
        return items, 0

    rows = without_repeats(schema_key, rows)

    if schema_key == "learning_activities":
        kept = rows[:quota]
    elif schema_key == "session_guides":
        kept, covered = [], set()
        for index, guide in enumerate(rows):
            ids = {_bare(i) for field_name in ("activity_ids", "material_ids")
                   for i in (guide.get(field_name) or []) if _bare(i)}
            if index < quota or ids - covered:
                kept.append(guide)
                covered |= ids
    else:
        owed = list(work_set.pairs)
        first_of: dict[tuple[str, str], int] = {}
        for index, item in enumerate(rows):
            pair = (_bare(item.get("aligned_objective")),
                    str(item.get("plan_category") or "").strip().lower())
            if pair in owed:
                first_of.setdefault(pair, index)
        keep = set(first_of.values())
        for index in range(len(rows)):
            if len(keep) >= max(quota, len(first_of)):
                break
            keep.add(index)
        kept = [item for index, item in enumerate(rows) if index in keep]
    return kept, len(items) - len(kept)


# ── fan-in helpers: shared by every family's finalize step ─────────────────

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
                   self_ref_fields: tuple[str, ...] = (), id_prefix: str,
                   taken: frozenset[str] = frozenset()) -> list[dict]:
    """Merge a family's Developer payloads (one per work set, each carrying
    ``{"set_id", "items": [...]}) into one flat, commit-ready item list.

    **The HARNESS names these artifacts; the model does not.** A Developer
    submits its items without an id, and each is named here by composing the
    SET's ordinal with the artifact's own — ``AT-0203`` is the third artifact
    of the second work set. Workers never coordinate, so pairing the ordinals
    is what makes the result unique BY CONSTRUCTION, decided when the plan was
    numbered rather than by which Developer committed first. Dense (each set
    counts from 1), and it says who wrote what. An id the model writes is
    overwritten every time while every malformed one (``AT-{``, a duplicate,
    one copied out of an example) is a real failure, and the field's absence
    shortens what has to fit under the completion cap.

    ``self_ref_fields`` are references to OTHER artifacts of this same set,
    which the model writes as 1-based POSITIONS in the list it submitted ([1] =
    the first it wrote) and which are resolved here into the assigned ids; one
    that does not resolve is DROPPED, because a dangling id in the graph is
    invisible while a dropped reference shows in the coverage numbers. Measured
    on the test fixture before positions: 0 of 3 ``prerequisite_activities``
    resolved, while ``_establish`` reads exactly that field to build the
    ``precedes`` edges.

    CROSS-family references get nothing done to them: they name an upstream
    family already committed, which the Developer read in its final form.

    ``taken`` are the ids the design state already holds, so a set committed on
    its own lands where it would have in a batch. Every committed item is also stamped
    ``plan_set`` with its owning set's id — invisible to schemas/judges
    (unknown keys validate), and what ``fanout.committed_set_ids`` reads.
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
        for _item in set_items:
            final_id = _composite_id(id_prefix, ws.ordinal, number, seen_ids)
            number = int(final_id.rsplit("-", 1)[1][-2:]) + 1
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


# ── work-set rendering: the "=== YOUR ASSIGNED ... ===" user-content block a
# Developer (multi arm) or a per-set state (single arm) shows the model.
# Pure text formatting, not part of the decomposition axis, so both arms
# import it from here rather than one borrowing the other's agent module.

def _note_line(work_set: WorkSet) -> list[str]:
    """The assignment's footer: what is still missing, then how much to write.

    ``still_missing`` is present only on a SECOND dispatch of a set whose
    first Developer left a gap (``agentic/replan.py``). It has to be said, and
    said in every family the same way: a commit drops a repeat
    (:func:`without_repeats`), so a set told only "write this again" produces
    nothing at all."""
    lines: list[str] = []
    missing = [str(m) for m in (work_set.payload.get("still_missing") or []) if m]
    if missing:
        lines.append(
            "THIS SET HAS ALREADY BEEN WRITTEN ONCE and what it produced is kept. "
            "Write ONLY what is still missing below — anything you repeat from the "
            "first round is dropped:")
        lines += [f"  - {m}" for m in missing[:12]]
        if len(missing) > 12:
            lines.append(f"  - (+{len(missing) - 12} more of the same kind)")
    note = str(work_set.payload.get("development_note") or "")
    return lines + ([note] if note else [])


def _ordinal(index: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(index, f"{index}th")


def _fraction(total: int) -> str:
    return {2: "half", 3: "third", 4: "quarter"}.get(total, f"of {total} equal parts")


def _module_line(work_set: WorkSet, *, time: bool = False) -> list[str]:
    """The module a set is one share of, as the first thing its Developer
    reads after the set id. Every family states it the same way."""
    module = work_set.payload.get("module")
    if not isinstance(module, dict) or not module.get("id"):
        return []
    title = f" — {module['title']}" if module.get("title") else ""
    line = f"module: {module['id']}{title}"
    block = _positive(work_set.payload.get("block_minutes"))
    if time and block:
        line += f" (this block has {int(block)} minutes of learner time)"
    return [line]


def _instrument_lines(work_set: WorkSet) -> list[str]:
    instruments = [i for i in (work_set.payload.get("instruments") or []) if isinstance(i, dict)]
    if not instruments:
        return []
    lines = ["instruments of the assessment plan YOUR items belong to (set each item's "
             "``instrument_id`` to one of these ids, and its ``plan_category`` to that "
             "instrument's timing):"]
    for instrument in instruments:
        counts = instrument.get("item_counts")
        scale = (", ".join(f"{n} {kind}" for kind, n in counts.items())
                 if isinstance(counts, dict) and counts else "")
        covers = ", ".join(_bare(o) for o in (instrument.get("covers_objectives") or []))
        lines.append(f"  - {_bare(instrument.get('id'))}: {instrument.get('timing', '')} "
                     f"{instrument.get('format', '')}".rstrip()
                     + (f" — full scale: {scale}" if scale else "")
                     + (f" — covers {covers}" if covers else ""))
    return lines


def render_assessment_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"] + _module_line(work_set)
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
    lines += _instrument_lines(work_set)
    hint = work_set.payload.get("instrument_hint")
    if hint:
        lines.append(f"instrument_hint: {hint}")
    rationale = work_set.payload.get("rationale")
    if rationale:
        lines.append(f"rationale: {rationale}")
    batch = work_set.payload.get("batch")
    if batch:
        index, total = batch
        lines.append(
            f"this is part {index} of {total} of these instruments' items: another developer "
            f"writes each other part without seeing yours, so draw yours from the "
            f"{_ordinal(index)} {_fraction(total)} of the content the instruments cover.")
    return "\n".join(lines + _note_line(work_set))


def render_activity_set(work_set: WorkSet) -> str:
    lines = [f"set_id: {work_set.set_id}"] + _module_line(work_set, time=True)
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
    return "\n".join(lines + _note_line(work_set))


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
    # one per media selection as the floor.
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
    return "\n".join(lines + _note_line(work_set))


def render_session_set(work_set: WorkSet) -> str:
    first = int(work_set.payload.get("first_session") or 1)
    count = int(work_set.payload.get("expected_sessions") or 1)
    last = first + count - 1
    sessions = ", ".join(str(n) for n in range(first, last + 1))
    lines = [f"set_id: {work_set.set_id}", *_module_line(work_set),
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
    return "\n".join(lines + _note_line(work_set))
