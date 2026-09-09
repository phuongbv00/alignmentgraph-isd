from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, PrivateAttr

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    ChatModelFactory = Callable[[], ChatAnthropic | ChatOpenAI]
else:
    ChatModelFactory = Callable[[], Any]


class HarnessRunConfig(BaseModel):
    llm_factory: ChatModelFactory | None = None

    use_rag: bool = False
    retrieval_subagents: list[Any] = []

    # Ablation matrix: decomposition x alignment machinery (2x2, no presets
    # beyond these two independent axes).
    # ``agent_mode="multi"`` starts each stage in a fresh context under that
    # stage's specialist identity; ``"single"`` carries ONE context across all
    # six under the `SingleDesignerAgent` identity. It is deliberately a BUNDLE
    # (context boundary, who walks the stages, personas, delegation), disclosed
    # exactly as ``context_mode`` is — equal model effort is NOT claimed.
    # ``context_mode="graph"`` runs the full alignment machinery: the
    # AlignmentGraph is written and read (relation-scoped context injection and
    # relation joins, the alignment-state docket), the cross-artifact checks and
    # the repairs they own run over its edges, the residual GraphAuditor pass
    # runs at the end, the aggregator's graph-derived enrichments apply
    # (``design.alignment_matrix``, the ``_ensure_assessment_coverage`` backstop,
    # the coverage-aware ``expert_review``), and the run ships the graph dump.
    # Cross-artifact violations are reconciled ONCE after the last stage, in a
    # bounded pass: each residual violation goes to the family that owns it
    # (``repairs.OWNED_BY_FAMILY``, carried on ``Violation.target_designer``).
    # In ``agent_mode="multi"`` that means the owning role's own context;
    # in ``"single"`` there is no other context, so the one agent repairs in
    # place. Same rounds, same repair budget either way -- only WHERE the
    # repair happens differs, which is the axis itself.
    # ``context_mode="prose"`` runs a GRAPH-FREE prose blackboard instead
    # (`core/prose_store.py::ProseStore`): each step deposits its whole parsed JSON
    # under one key, later steps read documents back verbatim by a static
    # read-list (the named-slice pattern non-graph agents use), safeguards are
    # limited to the within-artifact checks + the shared self-repair/regen
    # scaffolding, and there is no audit and no graph artifact.
    # Two consequences that must be reported, not glossed:
    #   * The graph arm's context is a relation-scoped SUBSET of what prose
    #     hands the model — prose dumps whole upstream documents verbatim, so
    #     ITS prompts are the longer ones. This axis is "graph filters and joins
    #     upstream content, and adds a derived coverage docket", NOT "graph
    #     gives the model more to work with".
    #   * Two of the six families (activity, content) carry only cross-artifact
    #     checks, so in prose they get NO self-validation and NO repair at all —
    #     the axis bundles "alignment machinery" with "any quality control for
    #     those two families".
    # The axis therefore ablates the alignment machinery as a bundle — not a
    # rendering of the same facts, and not a single isolated variable.
    agent_mode: Literal["single", "multi"] = "multi"
    context_mode: Literal["prose", "graph"] = "graph"

    # Robustness: re-run a specialist whose section came back with empty required
    # fields (a small model intermittently returns empty/broken JSON, or a call is
    # dropped by a 429). ``regen_budget`` is the number of extra attempts;
    # ``regen_backoff_seconds`` is the base delay applied (growing per attempt)
    # before each re-run so a rate-limit window can drain instead of being hammered.
    # The benchmark adapter sources these from env (BENCHMARK_DELAY / HARNESS_REGEN_*).
    # A dev-plan fan-out family (assessment/activity/content/implementation —
    # see core/dev_plans.py) spends this budget TWICE: once at dispatch (did the
    # plan/grouping call itself produce anything) and, independently, once
    # PER WORK SET at finalize (did that one set's Developer call produce
    # anything) — so a persistently failing model can burn up to
    # ``regen_budget`` x (1 + set_count) extra calls for one family, bounded
    # by ``core.dev_plans.MAX_SETS_HARD_CAP``.
    regen_budget: int = 2
    regen_backoff_seconds: float = 0.0

    # How much of the model's context window the transcript may occupy, derived
    # rather than fixed. ``llm_context_window`` is the SERVING window in tokens
    # (the ladder's vLLM pods run 16384); 0 keeps the historical constant.
    # ``llm_completion_reserve`` is what must be left for the answer — the
    # ladder caps completions at 8192 (AGENT_MODEL_MAX_OUTPUT_TOKENS) and a prompt
    # that eats into it makes the generation fail rather than the trim.
    #
    # Why derive it: ``HISTORY_CHAR_BUDGET`` was 24,000 characters, a number
    # with no relation to the model actually being served. On the ladder's
    # configuration the derivation lands within 2% of it — the constant was
    # well chosen — but it now TRACKS the serving setup instead of coinciding
    # with it, so a wider-window model gets the window it has.
    #
    # It is one number for BOTH arms, which is the point: the ``agent_mode``
    # axis is the context BOUNDARY, and a budget that varied by arm would make
    # the two spend different effort and mix "saw less" with "did less".
    llm_context_window: int = 0
    llm_completion_reserve: int = 8192

    # Outbound-call posture (see core/ratelimit.py). ``llm_max_concurrency``
    # caps how many LLM requests THIS run keeps in flight at once; 0 = unbounded,
    # which is the standalone default. The executor is SEQUENTIAL today, so
    # this does not currently bind on anything but RAG's parallel retrieval
    # plans. It is kept because it answers a measured failure of the LangGraph
    # pipeline, whose content/rubric fan-out issued one request per work set
    # from two families in the same superstep: one agent put 10+ requests on the
    # endpoint while the benchmark's rate posture counted it as one unit, and a
    # shared endpoint answered with HTTP 429 on the multi arms only — a
    # throttling handicap on one side of the ``agent_mode`` axis. Any concurrent
    # fan-out reintroduced here brings that back.
    # The benchmark adapter sources this from env (HARNESS_LLM_MAX_CONCURRENCY,
    # exported by run_benchmark.py from the -r preset).
    # ``llm_min_interval_seconds`` additionally spaces call STARTS apart, for an
    # endpoint that meters request rate rather than concurrency; it is off by
    # default and deliberately NOT wired to BENCHMARK_DELAY, which is a
    # between-agents delay and would add a sleep before every call.
    llm_max_concurrency: int = 0
    llm_min_interval_seconds: float = 0.0

    #: Lazily built by ``core.ratelimit.gate_for`` and shared by every agent in
    #: the run (they all receive this same config instance).
    _call_gate: Any = PrivateAttr(default=None)

    model_config = {"arbitrary_types_allowed": True}
