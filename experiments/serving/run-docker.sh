#!/usr/bin/env bash
# Run one rung of the ladder (or the alignment encoder) on a GPU host, exactly
# as its RunPod template does: the stock vLLM image, the same env, the same
# args in the same order (docs/guides/benchmark_guides.md §3.4). Self-contained,
# so copying this one file to the host is enough.
#
#   export VLLM_API_KEY=...
#   ./run-docker.sh 2b                     # GPU 0, port 8000
#   ./run-docker.sh 9b --gpu 1 --port 8001
#   ./run-docker.sh nemotron --gpu 2 --port 8002
#   ./run-docker.sh stop 2b                # remove that container
#
# Rungs: 0.8b 2b 4b 9b nemotron. One rung per GPU: two rungs on one card would
# make one rung's latency depend on the other's load, a difference on the
# ladder axis itself.
set -euo pipefail

IMAGE="vllm/vllm-openai:v0.25.1"
CACHE_VOLUME="isd-hf-cache"

usage() {
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

model_for() {
    case "$1" in
        0.8b) echo "Qwen/Qwen3.5-0.8B" ;;
        2b) echo "Qwen/Qwen3.5-2B" ;;
        4b) echo "Qwen/Qwen3.5-4B" ;;
        9b) echo "Qwen/Qwen3.5-9B" ;;
        nemotron) echo "nvidia/llama-embed-nemotron-8b" ;;
        *) echo "run-docker.sh: unknown rung '$1' (0.8b 2b 4b 9b nemotron)" >&2; exit 1 ;;
    esac
}

[[ $# -ge 1 ]] || usage 1
[[ "$1" == -h || "$1" == --help ]] && usage 0

if [[ "$1" == stop ]]; then
    [[ $# -ge 2 ]] || usage 1
    model_for "$2" >/dev/null
    docker rm -f "isd-$2"
    exit 0
fi

rung="$1"
shift
model="$(model_for "$rung")"
gpu=0
port=8000
while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu) gpu="$2"; shift 2 ;;
        --port) port="$2"; shift 2 ;;
        -h|--help) usage 0 ;;
        *) echo "run-docker.sh: unknown option '$1'" >&2; usage 1 ;;
    esac
done

: "${VLLM_API_KEY:?export VLLM_API_KEY first (the same value as in experiments/.env)}"
command -v docker >/dev/null || { echo "run-docker.sh: docker is not installed" >&2; exit 1; }

# The template's args, verbatim.
args=(
    "$model"
    --dtype bfloat16
    --trust-remote-code
    --tensor-parallel-size 1
    --gpu-memory-utilization 0.95
)
env=(-e HF_HOME=/workspace/huggingface -e VLLM_API_KEY)
if [[ "$rung" == nemotron ]]; then
    args+=(--max-model-len 8192)
    env+=(-e HF_TOKEN)
else
    args+=(
        --max-model-len 16384
        --reasoning-parser qwen3
        --enable-auto-tool-choice
        --tool-call-parser qwen3_coder
        --language-model-only
        --enable-prefix-caching
    )
fi
args+=(--host 0.0.0.0 --port 8000)

name="isd-$rung"
docker rm -f "$name" >/dev/null 2>&1 || true
docker run -d \
    --name "$name" \
    --gpus "\"device=$gpu\"" \
    --ipc=host \
    --restart unless-stopped \
    -p "$port:8000" \
    -v "$CACHE_VOLUME:/workspace/huggingface" \
    "${env[@]}" \
    "$IMAGE" "${args[@]}" >/dev/null

echo "run-docker.sh: $name ($model) on GPU $gpu, port $port; waiting for it to load..."
until curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; do
    if [[ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" != true ]]; then
        echo "run-docker.sh: $name stopped; last log lines:" >&2
        docker logs --tail 40 "$name" >&2
        exit 1
    fi
    sleep 10
done

curl -fsS "http://127.0.0.1:$port/v1/models" -H "Authorization: Bearer $VLLM_API_KEY" \
    | grep -q "\"$model\"" || { echo "run-docker.sh: /v1/models does not list $model" >&2; exit 1; }
echo "run-docker.sh: ready. base_urls = [\"http://<this-host>:$port/v1\"]  (logs: docker logs -f $name)"
