# react-isd-baseline

English-prompt clone of `isd-agent-benchmark/agents/react-isd` (v0.5.0), used as
the cross-agent baseline in the RQ2 tuning experiment
(`case-study/`). The benchmark submodule is untouched.

Differences from the original, all documented as threats to validity in the
thesis/paper:

1. **Prompts translated Korean → English** (structure, sub-item requirements and
   JSON output schemas preserved) to remove the output-language confound with
   the harness, whose outputs are English.
2. **Token accounting** — the original hardcodes `metadata.total_tokens = 0`;
   this clone tracks `usage_metadata` per LLM call (`llm.py:UsageTracker`).
3. **`adjust(scenario, previous_addie_output, edit_request)`** — the
   "targeted tuning without alignment control" condition: each of the 5 phases
   gets its previous output + the edit request and may answer
   `{"unchanged": true}` to pass through verbatim (so untouched phases cost no
   completion tokens). No verifier, no cascade — by design; that absence is the
   condition under measurement.
4. Self-contained LLM plumbing via `AGENT_MODEL_*` env vars (no dependency on
   the benchmark's `shared/llm`).

```python
from react_isd_baseline import ReActISDBaselineAgent, settings_from_env

agent = ReActISDBaselineAgent(settings_from_env())
result = agent.run(scenario)                          # full generation
revised = agent.adjust(scenario, result["addie_output"], "Tighten all rubrics")
```
