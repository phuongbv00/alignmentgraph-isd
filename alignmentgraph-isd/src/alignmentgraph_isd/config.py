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

#: The ablation axes as types, named so a caller that only forwards a choice —
#: the server's request body — can spell the allowed values without writing the
#: matrix down a second time. The DEFAULTS stay on the fields below and nowhere
#: else.
AgentMode = Literal["single", "multi"]
ContextMode = Literal["prose", "graph"]
DevelopmentMode = Literal["light", "full"]


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
    # AlignmentGraph written and read (relation-scoped injection and joins, the
    # alignment-state docket), the cross-artifact checks and their repairs over
    # its edges, the residual GraphAuditor pass, the aggregator's graph-derived
    # enrichments (``design.alignment_matrix``, the coverage-aware
    # ``expert_review``), and the graph dump. Cross-artifact violations are
    # reconciled ONCE after the last stage: each goes to the family that owns
    # it (``repairs.OWNED_BY_FAMILY``, on ``Violation.target_designer``) — the
    # owning role's own context in ``multi``, in place in ``single``, same
    # rounds and same budget either way.
    # ``context_mode="prose"`` runs a GRAPH-FREE blackboard instead
    # (`core/prose_store.py::ProseStore`): each step deposits its whole parsed
    # JSON under one key, later steps read documents back verbatim by a static
    # read-list, safeguards reduce to the within-artifact checks plus the
    # shared self-repair/regen, and there is no audit and no graph artifact.
    # Two consequences that must be REPORTED, not glossed:
    #   * The graph arm's context is a relation-scoped SUBSET of what prose
    #     hands the model, which dumps whole upstream documents — so PROSE has
    #     the longer prompts. The axis is "graph filters, joins and adds a
    #     coverage docket", NOT "graph gives the model more to work with".
    #   * Two of the six families (activity, content) carry only cross-artifact
    #     checks, so in prose they get NO self-validation and NO repair — the
    #     axis bundles alignment machinery with any quality control for those
    #     two families.
    # It ablates the machinery as a BUNDLE: not a rendering of the same facts,
    # and not a single isolated variable.
    agent_mode: AgentMode = "multi"
    context_mode: ContextMode = "graph"

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
    # The experiment's adapter sources this from env (HARNESS_LLM_MAX_CONCURRENCY,
    # else the runner's rate preset, BENCHMARK_RATE_LIMIT).
    # ``llm_min_interval_seconds`` additionally spaces call STARTS apart, for an
    # endpoint that meters request rate rather than concurrency; it is off by
    # default and deliberately NOT wired to BENCHMARK_DELAY, which is a
    # between-agents delay and would add a sleep before every call.
    llm_max_concurrency: int = 0
    llm_min_interval_seconds: float = 0.0

    # How many of a family's work sets the multi arm's fan-out runs AT ONCE.
    # 1 (the default, and the ladder's) is the sequential fan-out. Above 1,
    # ``core/runner.py::_run_fanout`` runs the Developers on worker threads,
    # bounded by ``llm_max_concurrency`` where that is set, and still commits
    # every set in PLAN order so the design state — and every listing read
    # off it — is the same whatever the worker count. Wall time only: the
    # calls, the tokens and the artifacts do not change. Opt-in because the
    # single arm has no fan-out to speed up, so a parallel multi arm is a
    # timing difference to declare, and because a shared endpoint answers an
    # unbounded burst with HTTP 429 (see ``llm_max_concurrency`` above).
    fanout_workers: int = 1

    # How much of the planned scale the Developers write out. The PLAN always
    # states the course at full scale (a 40-item quiz, a module's whole run of
    # activities). ``"light"`` writes a typical, reviewable slice of it — one
    # item per (objective x timing) pair at the objective's own Bloom level,
    # one activity per objective, two outlined materials per module, the
    # quotas ``core.dev_plans.LIGHT_*`` — for a human, the LLM judge and the
    # alignment panel to judge alignment quality and typical content on;
    # ``"full"`` writes all of it for deployment, batching what one call
    # cannot hold. The table at the head of ``core/dev_plans.py``'s
    # development-mode section states the difference field by field.
    # ``"light"`` is the default because a full development multiplies
    # Developer calls by the blueprint's scale and a benchmark ladder is
    # scored per scenario. NOT an ablation axis: every arm of one experiment
    # runs under the same value (declared once in experiment.toml
    # ``[harness].development_mode``), it changes numbers and a derived
    # assignment in a work set plus one note in its assignment and never a
    # ``RULES_*`` block, and ``metadata.run_config`` records it. The aggregate
    # states the scope it was written at (``development.development_scope``),
    # so a reader of the output is never left to infer why a quiz of 40 shows
    # three items.
    development_mode: DevelopmentMode = "light"

    #: Lazily built by ``core.ratelimit.gate_for`` and shared by every agent in
    #: the run (they all receive this same config instance).
    _call_gate: Any = PrivateAttr(default=None)
    #: The ``tool_choice`` this run's backend accepts, learned once by
    #: ``core.agentic.client.AgenticLLM`` and shared by every agent after:
    #: None until known (the client then sends ``"required"``), ``"auto"``
    #: once a request under ``"required"`` was refused, ``""`` when
    #: ``bind_tools`` takes no such keyword at all.
    _tool_choice: Any = PrivateAttr(default=None)

    model_config = {"arbitrary_types_allowed": True}
