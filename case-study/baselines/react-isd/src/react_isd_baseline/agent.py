"""ReAct-ADDIE baseline clone for the RQ2 tuning experiment.

English-prompt clone of isd-agent-benchmark/agents/react-isd (v0.5.0) with two
additions the experiment needs and the original lacks:

* real token accounting (the original hardcodes ``metadata.total_tokens = 0``);
* an ``adjust`` entry point — the "targeted tuning without alignment control"
  condition: each phase sees its previous output plus the user's edit request
  and may return ``{"unchanged": true}`` to pass through verbatim.

The 5-phase pipeline shape (Analysis -> Design sequential; Development /
Implementation / Evaluation parallel) is preserved from the original.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from react_isd_baseline.llm import LLMSettings, UsageTracker, create_chat_model, settings_from_env
from react_isd_baseline.tools.phases import (
    ANALYSIS_PROMPT,
    DESIGN_PROMPT,
    DEVELOPMENT_PROMPT,
    EVALUATION_PROMPT,
    IMPLEMENTATION_PROMPT,
    adjust_phase,
    run_analysis,
    run_design,
    run_development,
    run_evaluation,
    run_implementation,
)

AGENT_ID = "react-isd-baseline"
AGENT_VERSION = "0.5.0+baseline.1"
ADJUST_MAX_TOKENS = 16384

PHASES = ("analysis", "design", "development", "implementation", "evaluation")


class ReActISDBaselineAgent:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or settings_from_env()
        self.tracker = UsageTracker()
        self.llm = create_chat_model(self.settings, self.tracker)
        # Adjust prompts carry the previous phase output (~thousands of tokens),
        # so the revision call gets a larger output budget.
        self._adjust_llm = create_chat_model(
            self.settings.with_max_tokens(max(self.settings.max_tokens, ADJUST_MAX_TOKENS)),
            self.tracker,
        )

    # ── Full generation (react_full_regen condition) ──────────────────────────

    def run(self, scenario: dict) -> dict:
        start_time = datetime.now()
        usage_before = self.tracker.snapshot()
        tool_calls: list[dict] = []
        fallbacks: list[str] = []
        info = self._scenario_info(scenario)

        analysis_result, fb = run_analysis(
            self.llm, info["title"], info["target_audience"], info["learning_environment"],
            info["duration"], info["prior_knowledge"], info["learning_goals"],
        )
        if fb:
            fallbacks.append("analysis")
        tool_calls.append({"step": 1, "tool": "run_analysis", "timestamp": datetime.now().isoformat()})

        design_result, fb = run_design(
            self.llm, info["title"], info["target_audience"], info["duration"], info["learning_goals"],
        )
        if fb:
            fallbacks.append("design")
        tool_calls.append({"step": 2, "tool": "run_design", "timestamp": datetime.now().isoformat()})

        parallel_tasks = {
            "development": lambda: run_development(
                self.llm, info["title"], info["target_audience"], info["learning_environment"], info["learning_goals"],
            ),
            "implementation": lambda: run_implementation(
                self.llm, info["title"], info["target_audience"], info["learning_environment"], info["class_size"],
            ),
            "evaluation": lambda: run_evaluation(
                self.llm, info["title"], info["target_audience"], info["learning_goals"],
            ),
        }
        parallel_results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(task): name for name, task in parallel_tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    parallel_results[name], fb = future.result()
                    if fb:
                        fallbacks.append(name)
                except Exception as e:
                    print(f"[WARN] {name} failed: {e}")
                    parallel_results[name] = {}
                    fallbacks.append(name)
        parallel_timestamp = datetime.now().isoformat()
        for i, name in enumerate(("development", "implementation", "evaluation")):
            tool_calls.append({"step": 3 + i, "tool": f"run_{name}", "timestamp": parallel_timestamp})

        addie_output = {
            "analysis": analysis_result,
            "design": design_result,
            "development": parallel_results.get("development", {}),
            "implementation": parallel_results.get("implementation", {}),
            "evaluation": parallel_results.get("evaluation", {}),
        }
        return self._assemble_result(
            scenario, addie_output, tool_calls, start_time,
            usage_before=usage_before, mode="run", fallbacks=fallbacks, unchanged_phases=[],
        )

    # ── Targeted tuning without control (react_targeted_tuning condition) ─────

    def adjust(self, scenario: dict, previous_addie_output: dict, edit_request: str) -> dict:
        """Revise a previous ADDIE output per an edit request, one call per phase.

        ``scenario`` is the brief the previous output was built from. There is no
        alignment graph and no verification: whether the revision keeps the
        design consistent is entirely up to the model — that is the condition
        under measurement.
        """
        start_time = datetime.now()
        usage_before = self.tracker.snapshot()
        tool_calls: list[dict] = []
        fallbacks: list[str] = []
        unchanged_phases: list[str] = []
        info = self._scenario_info(scenario)
        base_prompts = self._base_prompts(info)

        results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=len(PHASES)) as executor:
            futures = {
                executor.submit(
                    adjust_phase,
                    self._adjust_llm,
                    base_prompts[phase],
                    previous_addie_output.get(phase, {}),
                    edit_request,
                ): phase
                for phase in PHASES
            }
            for future in as_completed(futures):
                phase = futures[future]
                try:
                    section, unchanged, fb = future.result()
                except Exception as e:
                    print(f"[WARN] adjust {phase} failed: {e}")
                    section, unchanged, fb = previous_addie_output.get(phase, {}), False, True
                results[phase] = section
                if unchanged:
                    unchanged_phases.append(phase)
                if fb:
                    fallbacks.append(phase)
        timestamp = datetime.now().isoformat()
        for i, phase in enumerate(PHASES):
            tool_calls.append({"step": i + 1, "tool": f"adjust_{phase}", "timestamp": timestamp})

        addie_output = {phase: results[phase] for phase in PHASES}
        return self._assemble_result(
            scenario, addie_output, tool_calls, start_time,
            usage_before=usage_before, mode="adjust",
            fallbacks=fallbacks, unchanged_phases=sorted(unchanged_phases),
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _scenario_info(self, scenario: dict) -> dict:
        context = scenario.get("context", {})
        return {
            "title": scenario.get("title", "Training program"),
            "target_audience": context.get("target_audience", "general learners"),
            "learning_environment": context.get("learning_environment", "not specified"),
            "duration": context.get("duration", "not specified"),
            "prior_knowledge": context.get("prior_knowledge"),
            "learning_goals": scenario.get("learning_goals", []),
            "class_size": self._parse_class_size(context.get("class_size")),
        }

    def _base_prompts(self, info: dict) -> dict[str, str]:
        goals = json.dumps(info["learning_goals"], ensure_ascii=False)
        return {
            "analysis": ANALYSIS_PROMPT.format(
                title=info["title"], target_audience=info["target_audience"],
                learning_environment=info["learning_environment"], duration=info["duration"],
                prior_knowledge=info["prior_knowledge"] or "not specified", learning_goals=goals,
            ),
            "design": DESIGN_PROMPT.format(
                title=info["title"], target_audience=info["target_audience"],
                duration=info["duration"], learning_goals=goals,
            ),
            "development": DEVELOPMENT_PROMPT.format(
                title=info["title"], target_audience=info["target_audience"],
                learning_environment=info["learning_environment"], learning_goals=goals,
            ),
            "implementation": IMPLEMENTATION_PROMPT.format(
                title=info["title"], target_audience=info["target_audience"],
                learning_environment=info["learning_environment"],
                class_size=info["class_size"] or "not specified",
            ),
            "evaluation": EVALUATION_PROMPT.format(
                title=info["title"], target_audience=info["target_audience"], learning_goals=goals,
            ),
        }

    def _assemble_result(
        self, scenario, addie_output, tool_calls, start_time,
        *, usage_before, mode, fallbacks, unchanged_phases,
    ) -> dict:
        end_time = datetime.now()
        usage = self.tracker.delta_since(usage_before)
        return {
            "scenario_id": scenario.get("scenario_id", "unknown"),
            "agent_id": AGENT_ID,
            "timestamp": end_time.isoformat(),
            "addie_output": addie_output,
            "trajectory": {
                "tool_calls": tool_calls,
                "reasoning_steps": [f"Phase {tc['step']}: {tc['tool']}" for tc in tool_calls],
                "agent_interactions": [{
                    "iteration": 1,
                    "agent": AGENT_ID,
                    "action": mode,
                    "timestamp": start_time.isoformat(),
                }],
            },
            "metadata": {
                "model": self.settings.model_name,
                "mode": mode,
                "total_tokens": usage["total_tokens"],
                "token_usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                },
                "llm_calls": usage["llm_calls"],
                "execution_time_seconds": (end_time - start_time).total_seconds(),
                "agent_version": AGENT_VERSION,
                "iterations": 1,
                "tool_calls_count": len(tool_calls),
                "fallbacks": sorted(set(fallbacks)),
                "unchanged_phases": unchanged_phases,
            },
        }

    def _parse_class_size(self, class_size_raw):
        if class_size_raw is None:
            return None
        if isinstance(class_size_raw, int):
            return class_size_raw
        if isinstance(class_size_raw, str):
            nums = re.findall(r"\d+", class_size_raw)
            return int(nums[0]) if nums else None
        return None
