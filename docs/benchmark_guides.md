# Benchmark guide — single source of truth (RQ1/RQ2)

> Tài liệu **duy nhất** cho toàn bộ quy trình benchmark Qwen3.5 ladder: từ split data →
> dựng serving → tune → chạy bench → audit → hậu xử lý ra bảng số liệu paper, kèm định nghĩa
> đầy đủ mọi metric (Phụ lục A). Mục tiêu: một người mới pull repo về, có API key, đọc mỗi
> file này là **tái lập được toàn bộ thực nghiệm**.
>
> Mọi lệnh chạy từ `isd-agent-benchmark/` trừ khi ghi khác. Bối cảnh RQ xem
> [`docs/summary.md`](summary.md).
>
> (File này gộp và thay thế các tài liệu cũ: `scripts/README_ladder.md`,
> `docs/notes-serving-setup.md`, `docs/results-audit-checklist.md`, `docs/metrics.md`.)

## Mục lục

1. [Tổng quan pipeline](#1-tổng-quan-pipeline)
2. [Setup một lần](#2-setup-một-lần)
3. [Split data](#3-split-data--train--test--train_30--test_90)
4. [Serving (RunPod Pods + vLLM)](#4-serving-runpod-pods--vllm)
5. [Tune trên train_30](#5-tune-harness-trên-train_30)
6. [Bench trên test_90 — ladder](#6-bench-trên-test_90--chạy-ladder)
7. [Audit kết quả](#7-audit-kết-quả)
8. [Score alignment (RQ2)](#8-score-alignment-rq2--chạy-cho-từng-run-dir)
9. [Pool runs → thống kê](#9-pool-12-runs--thống-kê-rq1--rq2)
10. [Sinh bảng + hình paper](#10-sinh-bảng-hình--macro-số-liệu-cho-paper)
11. [Teardown + lưu trữ](#11-teardown--lưu-trữ)
12. [TL;DR](#12-tldr--ladder-chạy-xong-rồi-giờ-làm-gì)
    — Phụ lục A. [Metrics reference](#phụ-lục-a--metrics-reference)

### Bản đồ script (`isd-agent-benchmark/scripts/`)

| Script                         | Vai trò                                                                                         | Mục     |
|--------------------------------|-------------------------------------------------------------------------------------------------|---------|
| `1_setup.sh`                   | venv + cài deps gốc (`pyproject.toml`) + agents/evaluator (editable)                            | 2       |
| `2_split_data.sh`              | split gốc train/test 95/5 (seed 42)                                                             | 3       |
| `2_split_stratified_subset.py` | split `train_30` / `test_90`                                                                    | 3       |
| `3_sync_runpod_pods_env.py`    | list pods → verify model → sync env-quads vào `.env`                                            | 4.6     |
| `3_run_benchmark_test.sh`      | smoke run 1 scenario (sanity sau setup, ngoài e2e)                                              | 2       |
| `4_run_benchmark.sh`           | launcher tmux tổng quát — dùng cho **tune** trên `train_30` (chọn slot qua `AGENT_MODEL_SLOTS`) | 5       |
| `5_audit_preflight.py`         | audit trước khi launch: pod/auth/model/flags/smoke/disk                                         | 7.1     |
| `5_run_ladder.sh`              | launcher ladder 4 size × 3 run                                                                  | 6       |
| `6_audit_inflight.py`          | audit trong khi chạy: đếm red-flag trong logs + progress freshness                              | 7.2     |
| `6_audit_postrun.py`           | audit sau run: completeness/integrity/metrics per run dir                                       | 7.3–7.5 |
| `7_score_alignment.py`         | chấm alignment RQ2 per run dir (LLM-free)                                                       | 8       |
| `7_pool_ladder_runs.py`        | pool 12 runs → `pooled_ladder.json` + stats + token usage                                       | 9       |
| `8_gen_paper_tables.py`        | sinh `.tex` + macros vào `docs/paper/acm/vn/generated/`                                         | 10      |
| `8_gen_paper_figures.py`       | sinh 8 hình RQ1/RQ2 (`.pdf`+`.png`) vào `docs/paper/acm/vn/generated/figures/`                  | 10      |

---

## 1. Tổng quan pipeline

```
[2] setup env ──► [3] split data ──► [4] dựng serving ──► [5] TUNE trên train_30
                                                            │  (loop đến khi chốt config)
                                                            ▼
[9] pool runs ◄── [8] score alignment ◄── [7] audit ◄── [6] BENCH test_90 (ladder)
      │                (RQ2, local)                          4 size × 3 run
      ▼
[10] gen paper tables + figures ──► [11] teardown + lưu trữ
```

Nguyên tắc xuyên suốt (ML hygiene): **mọi quyết định tuning (prompt, config, flag) chỉ dựa
trên `train_30`; `test_90` chỉ được chạy sau khi đã freeze harness**, và mọi thay đổi code
sau đó ⇒ phải chạy lại ladder.

## 2. Setup một lần

```bash
cd isd-agent-benchmark
./scripts/1_setup.sh              # venv + deps gốc từ pyproject.toml + agents + evaluator (editable)
python run_benchmark.py --check   # mọi agent module import sạch
```

### `.env` — 3 bản example theo giai đoạn

Agent model và judge model cấu hình **tách biệt** (tránh self-preference bias). Copy bản
khớp giai đoạn đang làm vào `isd-agent-benchmark/.env` rồi điền key thật. Ma trận flag/env
đầy đủ: README của benchmark.

**Bản 1 — smoke test** (`./scripts/3_run_benchmark_test.sh`, 1 scenario, chưa cần pod —
agent model dùng luôn hosted API để verify pipeline end-to-end):

```bash
# --- secrets ---
OPENROUTER_API_KEY=sk-or-...

# --- agent model (global fallback khi không truyền --agent-model-*) ---
AGENT_MODEL_PROVIDER=openrouter
AGENT_MODEL_API_SPEC=openai_compatible
AGENT_MODEL_NAME=openai/gpt-4o-mini
AGENT_MODEL_BASE_URL=https://openrouter.ai/api/v1
AGENT_MODEL_API_KEY_ENV=OPENROUTER_API_KEY

# --- judge (multi-judge, median) ---
JUDGE_MODEL_PROVIDER=openrouter
JUDGE_MODEL_NAMES=openai/gpt-4o-mini,google/gemini-2.5-flash-lite
JUDGE_MODEL_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL_API_KEY_ENV=OPENROUTER_API_KEY
```

**Bản 2 — tune trên `train_30`** (mục 5; agent model = 1 pod tự host, thường 2B):

```bash
# --- secrets ---
OPENROUTER_API_KEY=sk-or-...     # judge
RUNPOD_API_KEY=rpa_...           # account key — chỉ để 3_sync_runpod_pods_env.py list pods
VLLM_API_KEY=...                 # Bearer token server vLLM (khớp RunPod secret, mục 4.5)

# --- judge (giữ nguyên như bản 1) ---
JUDGE_MODEL_PROVIDER=openrouter
JUDGE_MODEL_NAMES=openai/gpt-4o-mini,google/gemini-2.5-flash-lite
JUDGE_MODEL_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL_API_KEY_ENV=OPENROUTER_API_KEY

# --- agent model: KHÔNG cần viết tay ---
# Sau khi pod RUNNING, chạy:  python scripts/3_sync_runpod_pods_env.py
# → script tự append managed block vào cuối file này, gồm:
#   QWEN{08B,2B,4B,9B}_AGENT_MODEL_{PROVIDER,BASE_URL,NAME,API_KEY_ENVS}
#   + 3 flag bảo hộ: AGENT_MODEL_MAX_TOKENS_CAP=8096, AGENT_MODEL_STREAMING=1,
#     AGENT_MODEL_DISABLE_THINKING=1
# Lệnh tune ở mục 5 tham chiếu $QWEN2B_AGENT_MODEL_* từ block đó.
```

**Bản 3 — bench ladder trên `test_90`** (mục 6; giống bản 2, thêm tuỳ chọn rate):

```bash
# --- secrets + judge: y hệt bản 2 ---
OPENROUTER_API_KEY=sk-or-...
RUNPOD_API_KEY=rpa_...
VLLM_API_KEY=...
JUDGE_MODEL_PROVIDER=openrouter
JUDGE_MODEL_NAMES=openai/gpt-4o-mini,google/gemini-2.5-flash-lite
JUDGE_MODEL_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL_API_KEY_ENV=OPENROUTER_API_KEY

# --- tuỳ chọn ladder (mục 6.3) ---
# RATE_LIMIT=turbo                # conservative|moderate|aggressive|turbo
# QWEN08B_RATE_LIMIT=aggressive   # override per-slot nếu cần

# --- agent model: managed block do 3_sync_runpod_pods_env.py tự ghi (như bản 2) ---
# Ladder cần đủ cả 4 slot trong block — script sẽ cảnh báo slot nào chưa có pod.
```

Ba bản chỉ khác phần agent model: smoke dùng `AGENT_MODEL_*` global trỏ hosted API; tune/bench
dùng env-quad per-slot do script sync tự quản lý. Judge giữ nguyên xuyên suốt — **cấu hình
judge phải giống hệt nhau giữa các run/giai đoạn để điểm số so sánh được**.

## 3. Split data — train / test / train_30 / test_90

Hai tầng, đều đã chạy và commit kết quả (seed 42 — chỉ chạy lại nếu làm lại từ đầu):

```bash
# Tầng 1: split gốc 95/5, stratified theo domain|difficulty|learning_environment
./scripts/2_split_data.sh                     # → scenarios/train/ (~24.6k), scenarios/test/ (~1.2k)

# Tầng 2: cắt subset cố định theo lưới domain × difficulty (10 domain × 3 level)
python scripts/2_split_stratified_subset.py --source scenarios/train --target scenarios/train_30              # 1/cell = 30, để TUNE
python scripts/2_split_stratified_subset.py --source scenarios/test  --target scenarios/test_90 --per-cell 3  # 3/cell = 90, để BENCH
```

Metadata sinh kèm (`scenarios/train_30_metadata.json`, `scenarios/test_90_metadata.json`) ghi
seed, nguồn, số lượng — giữ lại cho phần reproducibility của paper. `train_30` lấy từ **train
split** nên tune thoải mái không đụng test.

## 4. Serving (RunPod Pods + vLLM)

> Mục này đồng thời là **nguồn để viết mục Experimental Setup** của thesis/paper.

### 4.1 Model ladder

Cấu hình pod chạy ladder:

| Slot    | Checkpoint (HF id)  | Params | GPU serve         |
|---------|---------------------|--------|-------------------|
| qwen08b | `Qwen/Qwen3.5-0.8B` | 0.8B   | RTX 4090 24GB     |
| qwen2b  | `Qwen/Qwen3.5-2B`   | 2B     | RTX 4090 24GB     |
| qwen4b  | `Qwen/Qwen3.5-4B`   | 4B     | RTX 4090 24GB     |
| qwen9b  | `Qwen/Qwen3.5-9B`   | 9B     | RTX PRO 4500 32GB |

### 4.2 Serving stack (viết vào Methods)

- **Inference engine**: vLLM `v0.25.1`.
- **Precision**: bf16.
- **Context window**: 16384 cho cả 4 model.
- **Serving flags**:
  ```
  --dtype bfloat16 \
  --trust-remote-code \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 16384 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --language-model-only \
  --enable-prefix-caching \
  --host 0.0.0.0 \
  --port 8000
  ```
- Hosting: RunPod secure cloud, mỗi model một pod độc lập, endpoint OpenAI-compatible,
  auth Bearer token (vLLM `VLLM_API_KEY`).

### 4.3 Completion-budget cap (quan trọng — phải ghi trong paper)

- **Vấn đề**: nhiều agent trong benchmark hardcode `max_tokens` theo giả định model
  context lớn (baseline: 32768; alignmentgraph-isd adapter: 16384; eduplanner: tới 16384).
  Với server 16k-context, request `prompt + max_tokens > 16384` bị từ chối (HTTP 400).
- **Giải pháp**: clamp trung tâm trong `shared/llm/factory.py::_chat_kwargs`, bật bằng env
  `AGENT_MODEL_MAX_TOKENS_CAP`. Ladder runs đặt **cap = 8096** (xấp xỉ nửa context; prompt
  scenario thực đo ~5–6k tokens nên còn dư headroom). ⚠️ Ghi chú cũ viết 8192 — **giá trị
  thật trong `.env` và trong error traces của mọi run là 8096** (vd.
  `completion_tokens=8096` đúng tại trần khi baseline vỡ structured output); paper phải
  ghi 8,096.
- **Câu chữ gợi ý cho paper**: "For the 16k-context self-hosted models, every agent's
  completion budget was uniformly capped at 8,096 tokens; agents' own configured budgets
  apply whenever they are below the cap." — nhấn mạnh cap áp dụng **đồng loạt mọi agent**
  nên không tạo lợi thế riêng cho agent nào (fairness).
- Không set cap ⇒ hành vi gốc giữ nguyên (backward compatible với run dùng model context lớn).

### 4.4 Streaming + non-thinking mode

Rút từ sự cố run `test_90` đầu tiên (2026-07-22):

- **Streaming**: RunPod HTTP proxy (Cloudflare) có read-timeout 120s → call sinh ADDIE
  không-streaming của 4B/9B (>120s) bị cắt hàng loạt (HTTP 524; 17 lần với 4B, 26 lần với 9B
  trong run đầu). Fix: client bật streaming (`AGENT_MODEL_STREAMING=1` →
  `ChatOpenAI(streaming=True, stream_usage=True)` trong `shared/llm/factory.py`).
  Token accounting không đổi (đọc `usage_metadata` từ stream).
- **Non-thinking mode**: Qwen3.5 mặc định thinking; model nhỏ (2B) lan man trong `<think>`
  đến cạn completion budget → `content` rỗng → baseline âm thầm ghi stub output
  (14/14 scenario của 2B trong run đầu — dữ liệu đó bị loại). Fix: chạy ladder ở
  **non-thinking mode** (`AGENT_MODEL_DISABLE_THINKING=1` → server-side
  `chat_template_kwargs: {enable_thinking: false}`).
- **Câu chữ gợi ý**: "All ladder models were served in non-thinking mode with streaming
  enabled; completion budgets were uniformly capped at 8,096 tokens." — cả 3 điều kiện
  áp dụng đồng nhất cho mọi agent và mọi model size (fairness).
- **Run bị loại**: `test_90_benchmark_*_r1_20260722_184403` (2B stub outputs, 4B/9B 524).

Tổng hợp: **3 flag bảo hộ bắt buộc** cho mọi ladder run (script sync ở 4.6 tự ghi vào
managed block cuối `.env`):

```bash
export AGENT_MODEL_MAX_TOKENS_CAP=8096
export AGENT_MODEL_STREAMING=1
export AGENT_MODEL_DISABLE_THINKING=1
```

### 4.5 Tạo pod trên RunPod console (thủ công, từ template public)

Pod tạo **thủ công trên console** từ một template public dùng chung cho cả 4 size
(`isd-agent-bench-qwen3.5-slm-ladder`):

**Template: <https://console.runpod.io/deploy?template=x4cakqmn77>**

Các bước, lặp cho từng pod (×4):

1. Mở link template → **Deploy**. Chọn GPU: RTX 4090 24GB cho 0.8B/2B/4B, A40 48GB cho 9B.
2. Chọn model: sửa **container start command**, thay **token đầu tiên (positional)** bằng
   HF id của slot (`Qwen/Qwen3.5-0.8B` / `-2B` / `-4B` / `-9B`). RunPod truyền start command
   như Docker CMD thuần — **không có shell, không expand `$ENV`** — nên KHÔNG đổi model được
   bằng env var; không sửa các flag phía sau.
3. Auth đã đấu sẵn: template set `VLLM_API_KEY={{ RUNPOD_SECRET_VLLM_API_KEY }}` (RunPod
   secret) — đảm bảo secret đó trong account trùng giá trị `VLLM_API_KEY` trong `.env`.
   Không cần `HF_TOKEN` (checkpoint public) — đừng thêm.
4. Deploy, chờ pod RUNNING và vLLM trả lời
   `GET https://<pod_id>-8000.proxy.runpod.net/v1/models` (**401** khi không key, **200** khi có key).

Storage (theo cấu hình pod thật): container disk 20GB + **mỗi pod một network volume riêng**
(EU-RO-1) mount tại `/workspace` để cache HF weights (`HF_HOME=/workspace/huggingface`) —
weights sống sót qua stop/restart pod, không phải tải lại. Env khác của template: cổng expose
`8000/http` (vLLM) + `22/tcp`.

### 4.6 Sync env vars từ pod đang sống vào `.env`

```bash
python scripts/3_sync_runpod_pods_env.py        # --dry-run để xem block trước
source .env
```

Script **chỉ đọc** RunPod API (không tạo/xoá gì): list pods, match slot theo start command /
tên pod, **verify model thật qua chính `/v1/models` của pod**, rồi **ghi đè managed block ở
cuối `.env`** (giữa hai marker `# >>> qwen-ladder pods ... >>>` / `# <<< ... <<<`) — chạy lại
là thay block, không bao giờ duplicate, không đụng phần còn lại của `.env`. Block chứa đủ
env-quad `QWEN{08B,2B,4B,9B}_AGENT_MODEL_{PROVIDER,BASE_URL,NAME,API_KEY_ENVS}` + 3 flag bảo
hộ (4.4). Base URL dạng `https://<pod_id>-8000.proxy.runpod.net/v1`; key env là `VLLM_API_KEY`.
`5_run_ladder.sh` tự `source .env` nên sau khi sync là chạy được ngay.

Env-quad nhận **bất kỳ** provider OpenAI-compatible, nên có thể thay một slot bằng hosted API
(vd. OpenRouter) bằng cách override quad của slot đó — verify đúng model ID trên provider trước.

### 4.7 Chi tiết vận hành + chi phí (footnote/appendix nếu cần)

- 9B bf16 (~18GB weights) **không vừa GPU 24GB** ở 16k context (OOM khi load/profile với
  util 0.95) → cần GPU ≥32GB (thực tế: RTX PRO 4500 Blackwell 32GB). Đáng ghi như hardware
  requirement thực nghiệm.
- Chi phí thuê tại thời điểm chạy (secure cloud, 2026-07): RTX 4090 $0.69/h ×3 +
  RTX PRO 4500 Blackwell $0.74/h ×1 ≈ **$2.81/h cho cả ladder**.
- **Pod tính tiền theo giờ kể cả idle** — dừng/xoá pod trên console ngay khi xong (mục 11).

## 5. Tune harness trên `train_30`

Mục đích: chỉnh prompt/config của `alignmentgraph-isd` (và phát hiện lỗi hạ tầng) trên tập
tách biệt với tập báo cáo. Chạy **single run, một model** (thường chọn size nhỏ/rẻ trước):

```bash
# Launcher thực dùng: 4_run_benchmark.sh (tmux, đọc env-quads từ managed block trong .env)
DATASET=train_30 \
AGENT_MODEL_SLOTS=qwen2b \
AGENTS=baseline,react-isd,alignmentgraph-isd \
RUN_TAGS=tune1 \
./scripts/4_run_benchmark.sh
```

(`AGENT_MODEL_SLOTS` nhận nhiều slot phẩy-cách nếu muốn tune trên vài size **song song** —
mỗi slot một tmux session `bench-<slot>`. `RUN_TAGS` cũng nhận nhiều tag phẩy-cách, chạy
**tuần tự** trong mỗi session — `RUN_TAGS=tune1,tune2,tune3` = 3 run lặp cùng code, dùng để
đo độ ổn định trên `train_30`; còn giữa các vòng tune có sửa code thì mỗi vòng launch riêng
một tag. Chạy thẳng `python run_benchmark.py` với các flag `--agent-model-*` vẫn được khi
cần một lệnh foreground đơn lẻ.)

- Kết quả vào `results/train_30_benchmark_<model>_tune<N>_<ts>/`. Dùng run-tag `tuneN` để
  không lẫn với run báo cáo (`r1/r2/r3`).
- Mỗi vòng: sửa harness → chạy lại `train_30` → so `total_score`/log lỗi → lặp.
- Có thể thu hẹp `--agents` cho rẻ khi chỉ debug harness; nhưng vòng chốt cuối nên chạy đủ 7
  agent để chắc thay đổi không phá agent khác.
- **Kết thúc giai đoạn tune = đóng băng code** (commit; manifest ladder ở mục 6 sẽ tự ghi
  commit hash của cả benchmark lẫn monorepo).

## 6. Bench trên `test_90` — chạy ladder

### 6.1 Quy mô & chi phí — đọc trước khi bấm

- 4 size × 3 run độc lập/size × 7 agent (6 default + `alignmentgraph-isd` — **không** nằm
  trong defaults, launcher đã thêm sẵn) × 90 scenario ≈ **7 560 agent generations**, cộng
  2 judge evaluation/generation (multi-judge mặc định).
- Một run `test_90` đơn (7 agent, 1 model) ở rate `turbo` mất **vài giờ**; cả ladder cỡ
  **~1 ngày** wall-clock (các size chạy song song, 3 run của một size chạy tuần tự).
  Cộng thêm tiền GPU RunPod theo giờ trong suốt thời gian đó.

### 6.2 Launch

```bash
source .env            # judge config + RUNPOD_API_KEY/VLLM_API_KEY
./scripts/5_run_ladder.sh        # gõ "yes" ở prompt xác nhận
```

Cơ chế (cùng mechanism với `4_run_benchmark.sh`):

- Env-quads lấy từ managed block trong `.env` (launcher tự `source .env`); thiếu `*_BASE_URL`
  ⇒ hard-fail kèm hướng dẫn chạy `scripts/3_sync_runpod_pods_env.py`.
- Mỗi size một tmux session (`ladder-qwen08b`, `ladder-qwen2b`, `ladder-qwen4b`,
  `ladder-qwen9b`) — các size chạy **song song**; trong mỗi session 3 run chạy **tuần tự**
  với `--run-tag r1|r2|r3`, mỗi run một results dir riêng:
  `results/test_90_benchmark_<model>_r<N>_<timestamp>/`.
- **Manifest reproducibility** ghi TRƯỚC khi launch vào
  `results/ladder_<ts>/ladder_manifest.json`: model ID/provider/base URL từng slot, dataset,
  agents, run tags, judge models, và **git commit của cả benchmark checkout lẫn monorepo cha**
  (chứa package `alignmentgraph-isd`). **Giữ file này cùng kết quả.**
- Log per-slot: `results/ladder_<ts>/<slot>.log`.

### 6.3 Rate limit per-slot

`RATE_LIMIT` (default `turbo`) là preset toàn cục (`conservative|moderate|aggressive|turbo`
— đặt worker counts + `BENCHMARK_DELAY`). Vì mỗi provider/model giới hạn khác nhau, từng slot
có thể override bằng `<SLOT>_RATE_LIMIT`; slot không set thì dùng giá trị toàn cục. Rate được
echo per-slot lúc launch và ghi vào manifest.

```bash
# Toàn cục moderate, nhưng throttle model nhỏ trên endpoint giới hạn chặt hơn:
RATE_LIMIT=moderate \
QWEN08B_RATE_LIMIT=conservative \
QWEN2B_RATE_LIMIT=conservative \
./scripts/5_run_ladder.sh
```

(`<SLOT>_RATE_LIMIT` cũng hoạt động y hệt trong `4_run_benchmark.sh`.)

### 6.4 Monitor

```bash
tmux ls
tmux attach -t ladder-qwen2b     # detach: Ctrl+B, D
tail -f results/ladder_*/qwen2b.log
```

Kết hợp checklist in-flight ở mục 7.2.

### 6.5 Resume / chạy lại từng phần

Mỗi (size, run) là một invocation `run_benchmark.py` độc lập với results dir riêng, nên
resume = launch lại đúng phần còn thiếu:

```bash
# Chỉ 4B, run 2 và 3 (run 1 đã xong):
LADDER_SLOTS="qwen4b" RUN_TAGS="r2,r3" ./scripts/5_run_ladder.sh

# Chỉ 0.8B, đủ 3 run:
LADDER_SLOTS="qwen08b" ./scripts/5_run_ladder.sh
```

- Mỗi lần re-launch ghi manifest `ladder_<ts>/` mới; **giữ tất cả manifest**.
- **Không xoá** run dir dở dang vội — script pool (mục 9) báo tường minh scenario
  thiếu/fail per-run; re-run cùng tag phân biệt được bằng timestamp (dùng dir mới hơn, chỉ
  xoá dir bỏ dở **sau khi** pool xác nhận dir mới đủ).

## 7. Audit kết quả

> Đúc kết từ các sự cố thật ngày 2026-07-22 (524 proxy timeout, stub output, empty content).
> Cấu trúc results: `results/test_90_benchmark_<model>_r<N>_<ts>/test_90/<scenario_id>/` chứa
> `{agent}_output.json`, `{agent}_trajectory.json`, `{agent}_log.txt`, `comparison_report.json`;
> log tổng mỗi slot ở `results/ladder_<ts>/qwen*.log`; summary ở `benchmark_summary.json` + `SUMMARY.md`.

### 7.1 Pre-flight (trước khi bấm chạy)

```bash
python scripts/5_audit_preflight.py       # PASS/FAIL từng mục dưới; --no-smoke để bỏ smoke call
```

Script tự đọc `.env`, check pod alive/auth (401/200), model khớp slot, smoke non-thinking
(gửi đúng `chat_template_kwargs` như client ladder), 3 flag bảo hộ, disk. Checklist gốc
(để hiểu script check gì / khi cần làm tay):

- [ ] 4 pod sống + auth: cả 4 trả **401** khi curl không key, **200** khi có key
  (pod id xem managed block trong `.env` hoặc bảng 4.1):
  ```bash
  for p in <pod_id_08b> <pod_id_2b> <pod_id_4b> <pod_id_9b>; do
    curl -s -o /dev/null -w "$p: %{http_code}\n" --max-time 10 https://${p}-8000.proxy.runpod.net/v1/models
  done
  ```
- [ ] Đúng model trên đúng pod: `curl -H "Authorization: Bearer $VLLM_API_KEY" .../v1/models`
  → so id với slot (`3_sync_runpod_pods_env.py` đã tự verify bước này khi sync — cột `(live)`)
- [ ] Env đủ 3 flag bảo hộ (nằm trong managed block cuối `.env`):
  `AGENT_MODEL_MAX_TOKENS_CAP=8096`, `AGENT_MODEL_STREAMING=1`, `AGENT_MODEL_DISABLE_THINKING=1`
- [ ] Smoke test non-thinking thật sự ăn: response **không có `reasoning_content`**, `content` có chữ
- [ ] Disk trống đủ cho results (mỗi run ~vài trăm MB) — `df -h .`

### 7.2 In-flight (mỗi 30–60 phút trong khi chạy)

```bash
python scripts/6_audit_inflight.py        # ladder dir mới nhất; watch -n 300 để theo dõi liên tục
```

Đếm 524/400/empty/stub (phải đứng yên ở 0) + ✅/❌ per slot log + progress freshness.
Checklist gốc:

- [ ] **Đếm lỗi trong ladder logs** — con số phải đứng yên ở 0:
  ```bash
  for f in results/ladder_*/qwen*.log; do
    echo "$f: 524=$(grep -c 'Error code: 524' $f) 400=$(grep -c 'Error code: 400' $f) \
  empty=$(grep -c '응답 길이: 0' $f) stub=$(grep -c '기본 출력 반환' $f) \
  ok=$(grep -c '✅' $f) fail=$(grep -c '❌' $f)"
  done
  ```
    - `524 > 0` → proxy timeout quay lại (streaming chưa ăn?) — dừng, điều tra
    - `stub > 0` → baseline đang ghi default output → data scenario đó hỏng
    - `empty > 0` → thinking vẫn tràn budget hoặc model trả rỗng
- [ ] **Progress tiến đều**: `tail results/test_90_benchmark_*/benchmark_progress.log` — timestamp mới < 10 phút
- [ ] **GPU đang làm việc**: RunPod console → util > 0% ở pod đang được đánh; util = 0% kéo dài + progress đứng = treo
- [ ] Tỷ lệ ✅/❌ hợp lý (❌ lác đác do transient được retry thì chấp nhận; ❌ cùng 1 agent lặp lại → soi `{agent}_log.txt`)

### 7.3 Post-run: Completeness (đủ số lượng)

```bash
python scripts/6_audit_postrun.py         # audit mọi run dir (7.3 + 7.4 + 7.5 trong một report)
```

Script phân biệt **RED** (lỗi hạ tầng — stub/rỗng/token=0/sai model/thiếu metric) với
**info** (agent fail kiểu capability — hợp lệ, failure policy mục 9 xử lý). Checklist gốc
cho 7.3–7.5:

- [ ] **Đủ scenario**: 90 thư mục scenario mỗi run (test_90)
  ```bash
  for d in results/test_90_benchmark_*_r*/test_90; do echo "$d: $(ls $d | wc -l)"; done
  ```
- [ ] **Đủ agent × scenario**: mỗi scenario đủ 7 `_output.json` (6 default + alignmentgraph-isd)
  ```bash
  python3 - <<'EOF'
  import glob, os
  AGENTS = ["eduplanner","baseline","react-isd","addie-agent","dick-carey-agent","rpisd-agent","alignmentgraph-isd"]
  for run in sorted(glob.glob("results/test_90_benchmark_*_r*/test_90")):
      missing = []
      for sc in sorted(os.listdir(run)):
          for a in AGENTS:
              if not os.path.exists(f"{run}/{sc}/{a}_output.json"):
                  missing.append(f"{sc}/{a}")
      print(run, "MISSING:", len(missing), missing[:5])
  EOF
  ```
- [ ] Mỗi scenario có `comparison_report.json` (evaluation đã chạy); không có `evaluation_error` trong summary
- [ ] `benchmark_summary.json` tồn tại ở gốc mỗi run
- [ ] Đủ **3 runs** (r1/r2/r3) × 4 model size cho RQ1 trước khi pool

Agent thiếu output **được phép** nếu là capability failure (vd. baseline vỡ structured-output
vì trần token trên model nhỏ — chính là dữ liệu RQ1; failure policy ở mục 9 xử lý, không
re-run). **Không được phép** nếu là lỗi hạ tầng hàng loạt (7.6).

### 7.4 Post-run: Integrity (dữ liệu thật, không rác)

- [ ] **Quét stub/default output** (bài học 2B ngày 07-22 — stub đủ 33 sub-items nên nhìn "đầy đủ"):
  ```bash
  python3 - <<'EOF'
  import glob, json
  STUB_MARKS = ['"미지정"', '"problem_definition": null']
  for f in glob.glob("results/test_90_benchmark_*_r*/test_90/*/*_output.json"):
      s = open(f, encoding="utf-8").read()
      if all(m in s for m in STUB_MARKS):
          print("STUB?", f)
  EOF
  ```
- [ ] **Output rỗng / cụt**: file < 1KB hoặc thiếu phase
  ```bash
  find results/test_90_benchmark_*_r*/test_90 -name "*_output.json" -size -1k
  ```
- [ ] **Trajectory không rỗng** + agent "agentic" (react-isd, alignmentgraph-isd, ...) có tool calls thật
  ```bash
  find results/test_90_benchmark_*_r*/test_90 -name "*_trajectory.json" -size -200c
  ```
- [ ] **Token accounting > 0**: metadata mỗi trajectory có `token_usage.total_tokens > 0`
  (= 0 nghĩa là stream_usage không hoạt động hoặc call không xảy ra)
- [ ] **Đúng model sinh đúng run**: metadata ghi model name khớp thư mục run (0.8B run không lẫn URL pod 9B)
- [ ] Duration mỗi agent-run hợp lý (vài chục giây – vài phút; 0s hoặc hàng giờ đều đáng ngờ)

### 7.5 Post-run: Metrics (đủ các số cần đo)

Mỗi `comparison_report.json` (per-scenario, per-agent) phải có:

- [ ] **`total_score`** (median multi-judge, /100) — **số chuẩn cho paper là per-scenario total_score**
- [ ] **`addie_score`** (/100, từ 33 Context-Matrix sub-steps → 13 items → 5 ADDIE phases)
- [ ] **`trajectory_score`** (BFCL-based) — kiểm agent nào thiếu (agent không trajectory → biết trước, ghi chú)
- [ ] Điểm **đủ 5 phase** ADDIE, không phase nào 0/null hàng loạt
- [ ] **Multi-judge đủ số judge** cấu hình; độ lệch giữa judges không bất thường (1 judge chấm lệch hẳn → soi)
- [ ] ⚠️ **Bẫy CSV Avg**: cột Avg trong aggregate CSV là judge-mean, sẽ lệch per-scenario khi
  thiếu component — **luôn tính lại từ per-scenario `total_score`**, không lấy CSV Avg
- [ ] Phân phối điểm sanity: không có agent toàn 0 (lỗi pipeline) hoặc toàn 100 (parse lỗi);
  điểm stub (nếu lọt) thường thấp bất thường + đồng loạt giống nhau → đối chiếu 7.4

### 7.6 Red flags — dừng ngay / loại run

| Dấu hiệu                         | Ý nghĩa                                     | Hành động                                       |
|----------------------------------|---------------------------------------------|-------------------------------------------------|
| `Error code: 524` trong log      | Proxy cắt call >120s (streaming hỏng?)      | Dừng, kiểm `AGENT_MODEL_STREAMING`              |
| `Error code: 400` max context    | Cap không ăn / prompt quá dài               | Kiểm `AGENT_MODEL_MAX_TOKENS_CAP`               |
| `기본 출력 반환` / STUB? ở 7.4         | Baseline ghi default output                 | Loại scenario/run, tìm nguyên nhân content rỗng |
| `응답 길이: 0`                       | Model trả rỗng (thinking tràn? server lỗi?) | Kiểm non-thinking flag + pod logs               |
| `token_usage = 0` hàng loạt      | Accounting hỏng (stream_usage)              | Sửa trước khi chạy tiếp, số cost/token sai hết  |
| Model name metadata ≠ run dir    | Nhầm URL pod ↔ slot                         | Loại run, kiểm managed block trong `.env`       |
| `evaluation_error` trong summary | Judge/evaluator chết giữa chừng             | Chạy lại evaluation cho scenario đó             |
| Pod EXITED giữa run              | OOM/crash server                            | Xem RunPod console logs, kiểm VRAM              |

## 8. Score alignment (RQ2) — chạy cho TỪNG run dir

Bước này **không nằm trong ladder**, phải chạy tay sau bench. Tất định, LLM-free, chạy local,
không tốn API — chỉ đọc `*_output.json` và ghi `alignment_scores.json` vào từng scenario dir:

```bash
for RUN in results/test_90_benchmark_*_r*; do
  python scripts/7_score_alignment.py "$RUN"
done
```

Dùng `--overwrite` nếu cần chấm lại dir đã có `alignment_scores.json` (encoder mặc định
`tfidf`; script cũng đọc scenario gốc từ `scenarios/` để lấy topic — chạy từ trong
`isd-agent-benchmark/` là đủ). Thiếu bước này thì mục 9
vẫn chạy nhưng **bỏ trống toàn bộ phần RQ2** (graceful skip — dễ quên!).

## 9. Pool 12 runs → thống kê RQ1 + RQ2

```bash
python scripts/7_pool_ladder_runs.py --auto-glob 'results/test_90_benchmark_*_r*'
```

- Output: `results/pooled_ladder.json` + report stdout. Gộp 3 run/size (mean-of-runs), rồi
  per-size: Wilcoxon paired (proposed vs 6 baseline), Holm correction, bootstrap 95% CI,
  rank-biserial r, 3 failure policies (`complete_case` chính / `zero` / `min_score`),
  interaction DiD + trend slope — định nghĩa đầy đủ ở Phụ lục A.2. Alignment metrics (RQ2)
  pool từ `alignment_scores.json` (Phụ lục A.3). Kèm section `token_usage` (operational
  metadata, Phụ lục A.4): mean tokens / llm_calls / exec-time per agent × size.
- Auto-glob nhóm dir theo tên model + run tag; nếu nó vơ nhầm dir (vd. run tune, run bỏ dở),
  dùng mapping tường minh `--model <key>=dir1,dir2,dir3` (xem `--help`).
- Variance giữa r1/r2/r3 của cùng (model, agent): CV quá lớn (>~20–30%) → soi run lệch trước
  khi kết luận.
- Trend theo model size có giải thích được không (0.8B < 2B < 4B < 9B là kỳ vọng thô;
  đảo chiều ở đâu → kiểm integrity (7.4) chỗ đó trước khi coi là finding).
- Có dir trùng tag (re-run sau abort): dùng dir timestamp mới, xoá dir cũ **chỉ sau khi** pool
  xác nhận dir mới đủ 90 scenario.

## 10. Sinh bảng, hình + macro số liệu cho paper

```bash
python scripts/8_gen_paper_tables.py --pooled results/pooled_ladder.json
```

Ghi vào `docs/paper/acm/vn/generated/`: `tab_rq1.tex`, `tab_rq2_alignment.tex`,
`stats_macros.tex` (mọi con số trong prose là `\newcommand`, **số trong paper phải sinh tự
động, không gõ tay**), `stats_summary.md` (bản dump người đọc để cross-check). Số format
kiểu VN (`{,}`).


### 10.1 Hình (figures)

```bash
# Deps: matplotlib nằm trong pyproject.toml gốc (1_setup.sh đã cài; nếu venv cũ: pip install -e .)
python scripts/8_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
```

Ghi vào `docs/paper/acm/vn/generated/figures/` (mỗi hình cả `.pdf` vector cho
`\includegraphics` lẫn `.png` preview; text trong hình tiếng Anh, caption tiếng Việt viết
trong LaTeX):

| Hình                      | Nội dung                                                                                              |
|---------------------------|-------------------------------------------------------------------------------------------------------|
| `fig_rq1_ladder`          | Total vs model size, 7 agents, error bar = run-to-run SD (headline RQ1)                               |
| `fig_rq1_delta`           | Δ(proposed − baseline) per size, CI95 bootstrap, marker đặc = p_holm < 0,05, kèm trend slope          |
| `fig_rq1_components`      | ADDIE vs Trajectory theo size                                                                         |
| `fig_rq2_ladder`          | Alignment composite vs size (headline RQ2 — gap có nới rộng khi model nhỏ đi?)                        |
| `fig_rq2_components`      | Heatmap agents × 5 alignment components per size                                                      |
| `fig_rq2_vs_rq1_scatter`  | Per-scenario: composite vs Total (judge), Spearman ρ per size — cần `--runs-glob`                     |
| `fig_failure_rate`        | % scenario fail per agent × size (mean of runs, whisker min–max)                                      |
| `fig_cost_quality`        | Total vs total tokens / exec time (deployment-cost angle)                                             |

`--demo` render toàn bộ bằng dữ liệu synthetic (test layout, không cần pooled JSON). Thiếu
alignment/token data trong pooled JSON ⇒ hình tương ứng bị skip kèm cảnh báo.

Điều kiện serve phải ghi trong paper (bf16, 16k, non-thinking, streaming, cap 8096) — lấy
nguyên văn từ mục 4.

## 11. Teardown + lưu trữ

- **Dừng/xoá pod RunPod ngay khi ladder xong** (thao tác trên console — không có script
  teardown) — pod tính tiền theo giờ kể cả idle.
- Giữ nguyên vẹn: mọi `results/test_90_benchmark_*_r*/`, mọi `results/ladder_*/ladder_manifest.json`,
  `results/pooled_ladder.json`, `scenarios/*_metadata.json`, và managed block trong `.env`
  (ghi lại pod id/URL đợt serve gần nhất).
- Số VÀ hình trong paper chỉ được đến từ `generated/` (mục 10) — regenerate được từ raw
  results bất kỳ lúc nào bằng chuỗi [8] → [9] → [10].

## 12. TL;DR — "ladder chạy xong rồi, giờ làm gì?"

```bash
cd isd-agent-benchmark
# 1. Audit từng run dir:
python scripts/6_audit_postrun.py
# 2. RQ2 scoring (local, free):
for RUN in results/test_90_benchmark_*_r*; do python scripts/7_score_alignment.py "$RUN"; done
# 3. Pool:
python scripts/7_pool_ladder_runs.py --auto-glob 'results/test_90_benchmark_*_r*'
# 4. Bảng paper:
python scripts/8_gen_paper_tables.py --pooled results/pooled_ladder.json
# 5. Hình paper:
python scripts/8_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
# 6. Tắt pod RunPod (console), giữ manifests.
```

---

# Phụ lục A — Metrics reference

Liệt kê toàn bộ các metric được đo trong dự án và ý nghĩa của từng metric, theo nguồn tính
toán thực tế trong code (không phải mô tả lý thuyết).

Có ba nhóm, tương ứng ba tầng của pipeline đo lường:

1. **Judge quality metrics** — do LLM judge chấm trên từng ADDIE output (per scenario), nguồn cho RQ1.
2. **RQ1 statistics** — thống kê suy diễn (paired test, effect size, CI) tính trên các judge metric đã pool theo model
   size, dùng để trả lời "chất lượng có được duy trì khi thu nhỏ model không".
3. **RQ2 alignment metric** — thước đo constructive alignment định lượng, tự động, **không dùng LLM ở bước tổng hợp**,
   tính độc lập với judge và với verifier nội bộ của harness.

Ngoài ra có một số **operational metadata** được ghi log nhưng không nằm trong headline stats của hai RQ.

## A.1 Judge quality metrics (per-scenario, LLM judge)

Nguồn: `isd-agent-benchmark/evaluator/src/isd_evaluator/`. Mỗi scenario, mỗi agent được một (hoặc nhiều, nếu
multi-judge) LLM judge chấm hai phần độc lập, gộp thành một **Total** composite.

### A.1.1 ADDIE Rubric Score (0–100)

File: [`metrics/addie_rubric.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/addie_rubric.py), định
nghĩa rubric ở [
`rubrics/addie_definitions.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/rubrics/addie_definitions.py).

Đo mức độ đầy đủ/chất lượng của ADDIE output so với rubric chuyên gia ISD, theo hai bước LLM-judge tuần tự cho mỗi
sub-item:

- **Bước 1 — status**: judge phân loại từng sub-item vào 1 trong 5 trạng thái
  `absent / weak / moderate / good / excellent`, mỗi trạng thái ứng với một khoảng điểm cố định (0.0 / 1.0–3.9 /
  4.0–6.9 / 7.0–8.9 / 9.0–10.0).
- **Bước 2 — score**: judge cho điểm chi tiết, **bị ép cứng** (`enforced_score`) nằm trong khoảng của status đã xác định
  ở bước 1 — tránh judge tự do chấm vượt khung.
- **33 sub-item** (Context-Matrix — xem `docs/refs/`) → gộp trung bình thành **13 item** (`ITEM_MAPPING`) → gộp thành *
  *5 ADDIE phase** (`analysis`, `design`, `development`, `implementation`, `evaluation`).
- Mỗi phase có `raw_score` (tổng điểm item, thang 0–10/item), `weighted_score` (nhân trọng số phase), `percentage`.
- **Trọng số phase mặc định** (`DEFAULT_PHASE_WEIGHTS`): Analysis 25%, Design 25%, Development 20%, Implementation 15%,
  Evaluation 15% — điều chỉnh động theo context của scenario (mục A.1.3).
- `normalized_score` = `total_weighted / max_possible_weighted × 100` — đây là con số ADDIE 0–100 dùng downstream.

### A.1.2 Trajectory Score (0–100)

File: [`metrics/trajectory.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/trajectory.py). Đo **chất
lượng quá trình suy luận/dùng công cụ** của agent (không phải chất lượng output cuối), dựa trên khung BFCL (Berkeley
Function-Calling Leaderboard), LLM-judge trên trajectory log. 4 chiều, mỗi chiều 0–25 điểm, tổng 0–100 (
`TrajectoryScore.total`):

- **Tool Correctness** — có chọn đúng công cụ cho từng bước ADDIE không, có tránh gọi công cụ thừa không.
- **Argument Accuracy** — tham số truyền cho tool có đúng giá trị/kiểu/không thiếu field bắt buộc không.
- **Redundancy Avoidance** — có tránh gọi lặp cùng một tool với cùng tham số, tránh chia nhỏ một việc thành nhiều lời
  gọi không cần thiết.
- **Result Utilization** — có dùng kết quả tool vào bước suy luận tiếp theo, có phục hồi hợp lý khi tool lỗi không.

Đánh giá cùng một chuẩn cho cả single-agent và multi-agent (không ưu ái kiến trúc nhiều tác tử).

### A.1.3 Context-aware phase weighting (điều chỉnh trọng số, không phải metric riêng)

File: [`metrics/context_weights.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/context_weights.py).
Không tự nó là một con số được báo cáo, nhưng **quyết định trọng số phase** dùng ở mục A.1.1 → ảnh hưởng trực tiếp
`normalized_score`. `ContextWeightAdjuster` suy ra hồ sơ ngữ cảnh scenario (loại hình tổ chức, hình thức triển khai, độ
tuổi/học lực/vai trò người học, domain, quy mô lớp, môi trường công nghệ, thời lượng — theo Context Matrix) rồi cộng/trừ
trọng số từng phase (kẹp trong [0.05, 0.50], chuẩn hoá lại tổng = 1). Mục đích: một scenario "PBL" thì Design+Evaluation
quan trọng hơn Development, một scenario "VR" thì ngược lại — rubric chấm phải phản ánh đúng trọng tâm của bối cảnh đó
thay vì áp trọng số cố định cho mọi scenario.

### A.1.4 Total composite (0–100)

File: [`models/__init__.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/models/__init__.py) (
`CompositeScore.total`).

```
Total = 0.7 × ADDIE.normalized_score + 0.3 × Trajectory.total
```

Đây là con số **canonical** dùng cho mọi so sánh giữa agent (per-scenario `total_score` trong
`comparison_report.json`) — **không phải** cột "Avg" của `aggregate_table.csv`, vốn là judge-mean và lệch khi thiếu
component (xem mục 7.5).

## A.2 RQ1 statistics — duy trì chất lượng theo model scale

File: [`scripts/7_pool_ladder_runs.py`](../isd-agent-benchmark/scripts/7_pool_ladder_runs.py). Input: 4 kích thước
Qwen (0.8B/2B/4B/9B) × 3 run độc lập/kích thước × 90 scenario (`test_90`), mỗi scenario đã có `Total` (mục A.1.4) cho
từng agent. Đây là các thống kê **suy diễn**, không phải điểm số thô.

- **`mean_total`** — trung bình `Total` của một agent tại một model size, pool qua 3 run rồi qua các scenario (
  mean-of-3-runs, complete-case là policy chính).
- **`run_to_run_sd`** — SD giữa 3 giá trị trung bình cấp-run (đo độ ổn định run-to-run, tách biệt với phương sai giữa
  scenario).
- **Paired Wilcoxon signed-rank test** (`wilcoxon_signed_rank`) — so khớp cặp theo scenario giữa harness đề xuất và từng
  baseline (6 baseline), two-sided, hiệu chỉnh tie theo xấp xỉ chuẩn. Trả về `W_plus` (thống kê), `p_raw`,
  `n_effective` (số cặp có delta ≠ 0).
- **Holm correction** (`holm_correct`) — hiệu chỉnh đa kiểm định step-down trên family gồm đúng 6 so sánh (proposed vs
  mỗi baseline) **trong cùng một model size** → `p_holm`.
- **Bootstrap 95% CI** (`bootstrap_ci`, 10 000 resample, seed 42) — CI của mean paired delta (
  `Total_proposed − Total_baseline`), không giả định phân phối.
- **Matched-pairs rank-biserial correlation r** (`rank_biserial`) — effect size của Wilcoxon test,
  `r = (W+ − W−)/(W+ + W−)`, range [−1, 1].
- **Sensitivity analysis / failure policies** (`scenario_mean_map`) — 3 chính sách khi một agent fail/thiếu scenario:
  `complete_case` (chính, loại scenario thiếu), `zero` (impute 0), `min_score` (impute điểm thấp nhất quan sát được ở
  model size đó) — kiểm tra kết luận có nhạy với cách xử lý failure hay không.
- **Interaction / Difference-in-Differences** (`interaction_tests`) — trả lời "method × model size" (reviewer Q11):
  `did_mean` = delta(proposed − baseline) tại size lớn nhất trừ tại size nhỏ nhất, kèm bootstrap 95% CI và Wilcoxon p
  trên các giá trị DiD per-scenario.
- **Trend slope** (`trend_ols_slope_per_size_step`) — độ dốc OLS của delta(proposed − baseline) theo 4 bước kích thước
  model, kèm CI — đo khoảng cách chất lượng "nới rộng" hay "thu hẹp" đơn điệu theo scale.

## A.3 RQ2 — Alignment metric (constructive alignment, LLM-free)

File: [
`evaluator/src/isd_evaluator/metrics/alignment.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/alignment.py).
Đo **constructive alignment** của một ADDIE output — mức khớp giữa learning objectives, assessment, activities,
evaluation — bằng công thức tất định (zero lời gọi LLM ở bước tổng hợp), đọc **chỉ text** (không dùng `objective_id`/
`aligned_objective` hay field `level` tự khai báo để chấm điểm, chỉ dùng cho audit). Mọi thành phần nằm trong [0, 1].

- **Porter Alignment Index** (`porter_mean`, Porter 2002 / Fulmer 2011) — với mỗi cặp (objectives ↔ assessment, ↔
  activities, ↔ evaluation): dựng ma trận phân phối topic × Bloom-level chuẩn hoá (tổng = 1) cho mỗi phía, rồi
  `P = 1 − 0.5·Σ|X_ij − Y_ij|`. Đo khớp **kép** cả về nội dung (topic, suy ra bằng cosine similarity tới topic của
  scenario) lẫn tầng nhận thức (Bloom level, suy ra bằng lexicon classifier tiếng Việt/Anh — không dùng LLM).
- **Webb Range-of-Knowledge** (`webb_range`, Webb 1997/1999) — tỉ lệ objective có ít nhất một assessment item khớp (
  cosine similarity ≥ ngưỡng 0.25).
- **Webb Bloom-Consistency** (`webb_bloom_consistency`) — trong số assessment item khớp với một objective (bằng argmax
  similarity), tỉ lệ item có Bloom level ≥ level của objective tương ứng — đo assessment có "đo đúng tầng nhận thức đã
  đặt ra" hay đo thấp hơn mục tiêu.
- **Embedding coverage** (`embedding_coverage`, SE traceability framing — Cleland-Huang) — trung bình, với mỗi
  objective, độ tương đồng cosine lớn nhất tới bất kỳ assessment item nào (mọi objective có được "phủ" không).
- **Embedding precision** (`embedding_precision`) — chiều ngược lại: trung bình, với mỗi assessment item, độ tương đồng
  lớn nhất tới bất kỳ objective nào (mọi item có "bám" vào một objective thật hay là nội dung lạc đề).
- **Composite** — trung bình các thành phần *đã xác định* trong
  `[porter_mean, webb_range, webb_bloom_consistency, embedding_coverage, embedding_precision]`; = 0.0 nếu output không
  có objective nào.
- **Sanity report** (`lexicon_vs_declared_agreement`, report-only) — tỉ lệ đồng thuận giữa Bloom level do lexicon
  classifier suy ra và level agent tự khai báo trong output; **không** vào composite, chỉ để phát hiện agent "nói một
  đằng làm một nẻo" (khai declared level cao nhưng text không thể hiện).

Text encoder mặc định là character n-gram TF-IDF thuần Python (`TfidfCharNgramEncoder`, hợp tiếng Việt/Hàn không cách từ
rõ); có thể thay bằng sentence-embedding đa ngôn ngữ (`SentenceTransformerEncoder`, LaBSE/BGE-M3) nếu cần độ chính xác
semantic cao hơn — cả hai cùng interface `TextEncoder` nên không đổi công thức phía trên khi đổi encoder.

### Pooling cấp scenario/model-size (RQ2)

File: `7_pool_ladder_runs.py`, hàm `extract_alignment_metrics` + `pool_alignment` — đọc `alignment_scores.json` (nếu có)
trong từng scenario dir, gộp theo agent × model size thành `mean` và `sd_across_scenarios` cho mỗi metric ở trên (tên
field tự động flatten dạng `porter_alignment.mean`, `webb_consistency.mean`, `coverage.mean`, …), dùng để dựng bảng
`tab_rq2_alignment.tex`.

## A.4 Operational metadata (không phải headline metric của RQ1/RQ2)

Ghi trong `metadata` của mỗi `{agent}_trajectory.json` (`run_benchmark.py`), dùng cho debug/audit chi phí, **không**
đi vào Total hay alignment composite:

- **`token_usage`** — snapshot từ `shared/llm/token_accounting`, tổng token input/output mỗi lần chạy một scenario (đảm
  bảo mọi agent dùng `max_tokens` đồng nhất — fairness).
- **`execution_time_seconds`** — thời gian chạy hết một scenario.

Được pool theo agent × model size bởi `pool_tokens()` trong `7_pool_ladder_runs.py`
(section `token_usage` của `pooled_ladder.json`) — phục vụ bảng chi phí/hiệu năng, không vào RQ stats.
