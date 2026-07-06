"""Interactive demo: elicit a design brief through terminal Q&A, then print the run command.

Demonstrates the motivation point "a brief is formed through brainstorming, and
AI can take part": start from a vague request, answer the agent's clarifying
questions, approve the draft, and get a brief JSON ready for an init session.

    case-study/.venv/bin/python case-study/elicit_brief.py "Can dao tao OOP cho fresher truoc khi vao du an"

Model via AGENT_MODEL_* env or flags (same contract as run_case_study.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CASE_STUDY_DIR = Path(__file__).resolve().parent

from alignmentgraph_isd import HarnessRunConfig, llm_factory_from_env
from alignmentgraph_isd.elicitation import BriefElicitationAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("request", nargs="?", default="", help="Initial vague training request.")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--api-spec", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--max-turns", type=int, default=8)
    args = parser.parse_args(argv)

    config = HarnessRunConfig.from_ablation("case_study")
    config.llm_factory = llm_factory_from_env(
        model_name=args.model_name, api_spec=args.api_spec,
        base_url=args.base_url, api_key=args.api_key,
    )
    if config.llm_factory is None:
        sys.stderr.write("A model is required: set AGENT_MODEL_NAME/AGENT_MODEL_API_KEY or pass flags.\n")
        return 2

    agent = BriefElicitationAgent(config)
    history: list[dict] = []
    user_message = args.request or input("Describe the training need (vague is fine): ").strip()

    for _ in range(args.max_turns):
        turn = agent.step(history, user_message)
        history.append({"role": "user", "content": user_message})

        if turn.kind == "question":
            history.append({"role": "assistant", "content": turn.message})
            user_message = input(f"\n[agent] {turn.message}\n> ").strip()
            continue

        brief = turn.draft_brief
        print(f"\n[agent] {turn.message}\n")
        print(json.dumps(brief.model_dump(), ensure_ascii=False, indent=2))
        answer = input("\nApprove this brief? [y = save / anything else = give feedback] ").strip()
        if answer.lower() == "y":
            out_path = CASE_STUDY_DIR / "briefs" / f"{brief.id}.json"
            out_path.write_text(json.dumps(brief.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nSaved: {out_path}")
            print("Run the init session with:")
            print(
                f"  .venv/bin/python -m alignmentgraph_isd.cli run --input {out_path} "
                f"--output /tmp/{brief.id}-result.json --ablation case_study "
                f"--training-program-id {brief.id}"
            )
            return 0
        history.append({"role": "assistant", "content": f"[proposed draft brief] {turn.message}"})
        user_message = answer or "Please revise the draft."

    print("Reached max turns without an approved brief.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
