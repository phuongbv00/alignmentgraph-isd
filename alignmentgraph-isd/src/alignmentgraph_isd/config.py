from __future__ import annotations
from collections.abc import Callable
from typing import Any, Literal, TYPE_CHECKING

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
    # ``agent_mode="multi"`` is the full pipeline of specialist Designers;
    # ``"single"`` runs `SingleDesignerAgent`, one persona over the same steps.
    # ``context_mode="graph"`` runs the full alignment machinery: the
    # AlignmentGraph is written and read (relation-scoped context injection and
    # relation joins, the alignment-state docket), the cross-artifact checks and
    # the repairs they own run over its edges, the residual GraphAuditor pass
    # runs at the end, the aggregator's graph-derived enrichments apply
    # (``design.alignment_matrix``, the ``_ensure_assessment_coverage`` backstop,
    # the coverage-aware ``expert_review``), and the run ships the graph dump.
    # There is NO cross-agent feedback routing: the router and the validate
    # checkpoints were removed 2026-08-28 (see core/workflow.py's module
    # docstring); ``Violation.target_designer`` is a dead field.
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
    # A dev-plan fan-out family (assessment/activity/content/rubric — see
    # core/dev_plans.py) spends this budget TWICE: once at dispatch (did the
    # plan/grouping call itself produce anything) and, independently, once
    # PER WORK SET at finalize (did that one set's Developer call produce
    # anything) — so a persistently failing model can burn up to
    # ``regen_budget`` x (1 + set_count) extra calls for one family, bounded
    # by ``core.dev_plans.MAX_SETS_HARD_CAP``.
    regen_budget: int = 2
    regen_backoff_seconds: float = 0.0

    # Outbound-call posture (see core/ratelimit.py). ``llm_max_concurrency``
    # caps how many LLM requests THIS run keeps in flight at once; 0 = unbounded,
    # which is the standalone default. It exists because the multi arm's
    # content/rubric fan-out issues one request per work set from two families
    # in the same superstep, so a single agent could put 10+ requests on the
    # endpoint while the benchmark's rate posture still counted it as one unit —
    # and a shared endpoint answered with HTTP 429 on the multi arms only,
    # putting a throttling handicap on one side of the ``agent_mode`` axis.
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
