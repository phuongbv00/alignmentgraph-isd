"""What every serving host of the ladder runs: one image, one env, one argv.

The single declaration ``runpod_templates.py`` and ``vastai_templates.py`` are
built from, so a flag changed here changes both hosts' templates together
(run-docker.sh carries the same argv and is checked against this by eye;
docs/guides/benchmark_guides.md §3.4–§3.5).
"""

from __future__ import annotations

from dataclasses import dataclass

IMAGE, TAG = "vllm/vllm-openai", "v0.25.1"   # ENTRYPOINT ["vllm", "serve"], CUDA 13.0
CUDA = "13.0"
PORT = 8000
HF_HOME = "/workspace/huggingface"

# Everything after the model id, in the order the templates pass it.
LLM_ARGS = (
    "--dtype bfloat16 --trust-remote-code --tensor-parallel-size 1"
    " --gpu-memory-utilization 0.95 --max-model-len 16384"
    " --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder"
    " --language-model-only --enable-prefix-caching --host 0.0.0.0 --port 8000"
)
EMBED_ARGS = (
    "--dtype bfloat16 --trust-remote-code --tensor-parallel-size 1"
    " --gpu-memory-utilization 0.95 --max-model-len 8192 --host 0.0.0.0 --port 8000"
)


# Each secret a template reads from the host, whether a pod can do without it,
# and why. Both template scripts print these; no value ever appears here.
SECRETS = {
    "VLLM_API_KEY": (True, "without it vLLM serves with NO auth; use the value in experiments/.env"),
    "HF_TOKEN": (False, "no model of the ladder is gated; it only lifts Hugging Face download rate limits"),
}


@dataclass(frozen=True)
class Rung:
    name: str            # template name, the same on every host
    model: str           # HF id, the first arg
    args: str
    volume_gb: int       # RunPod: persistent /workspace (HF cache) beside a small container disk; API v2 minimum 10
    disk_gb: int         # Vast: one disk holds the image and the weights
    gpu: str             # §3.1; the Vast template filters offers on it
    secrets: tuple[str, ...] = ("VLLM_API_KEY",)

    @property
    def argv(self) -> str:
        return f"{self.model} {self.args}"


RUNGS = (
    Rung("isd-agent-bench-qwen3.5-0.8b", "Qwen/Qwen3.5-0.8B", LLM_ARGS, 10, 32, "RTX 4090"),
    Rung("isd-agent-bench-qwen3.5-2b", "Qwen/Qwen3.5-2B", LLM_ARGS, 10, 36, "RTX 4090"),
    Rung("isd-agent-bench-qwen3.5-4b", "Qwen/Qwen3.5-4B", LLM_ARGS, 10, 40, "RTX 4090"),
    Rung("isd-agent-bench-qwen3.5-9b", "Qwen/Qwen3.5-9B", LLM_ARGS, 20, 50, "RTX 5090"),
    Rung("isd-agent-bench-embed-nemotron-8b", "nvidia/llama-embed-nemotron-8b", EMBED_ARGS, 20, 50,
         "RTX 4090", secrets=("VLLM_API_KEY", "HF_TOKEN")),
)
