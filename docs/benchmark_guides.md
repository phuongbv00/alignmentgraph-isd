# Benchmark guide — single source of truth (RQ1/RQ2)

> Toàn bộ quy trình benchmark Qwen3.5 ladder: split data → serving → tune → chạy bench → audit →
> hậu xử lý ra số cho paper, kèm định nghĩa metric (Phụ lục A). Mục tiêu: đọc mỗi file này là
> tái lập được thực nghiệm.
>
> Mọi lệnh chạy từ `isd-agent-benchmark/` trừ khi ghi khác. Bối cảnh RQ: [`docs/summary.md`](summary.md).

**Ba quy tắc không được vi phạm:**

1. Mọi quyết định tuning chỉ dựa trên `train_30`. `test_90` chỉ chạy sau khi freeze code. Sửa code sau đó ⇒ chạy lại
   ladder.
2. Số trong paper **chỉ** đến từ `results/generated/` (mục 9). Không gõ tay.
3. Cấu hình judge và 3 flag bảo hộ (mục 3.3) phải **đồng nhất** giữa mọi run và mọi agent — đó là điều kiện công bằng
   của so sánh.

---

## Pipeline

```
[1] setup ─► [2] split data ─► [3] serving ─► [4] TUNE (train_30) ─┐
                                                 loop đến khi chốt │
                                                                   ▼
[8] pool ◄── [7] score alignment ◄── [6] audit ◄── [5] BENCH test_90 (ladder)
     │            (RQ2, local)                       4 size × 3 run × 10 agent
     ▼
[9] gen tables + figures ─► [10] teardown
```

### Bản đồ script

Script chung ở `scripts/`; pipeline ladder ở `scripts/alignmentgraph-isd-bench/`; pipeline ablation ở
`.../ablation/` (numbering song song, tái dùng audit + scoring của thư mục cha).

| Script                                    | Vai trò                                                              | Mục |
|-------------------------------------------|----------------------------------------------------------------------|-----|
| `.../00_validate_bloom.py`                | **chạy trước mọi thứ, một lần**: validate cả hai Bloom arm vs nhãn chuyên gia | A.3 |
| `1_setup.sh`                              | venv + deps + agents/evaluator (editable)                            | 1   |
| `2_split_data.sh`                         | split gốc train/test 95/5 (seed 42)                                  | 2   |
| `2_split_stratified_subset.py`            | cắt `train_30` / `test_90`                                           | 2   |
| `3_sync_runpod_pods_env.py`               | list pod → verify model → ghi env-quad agent vào `.env`              | 3.4 |
| `3_run_benchmark_test.sh`                 | smoke run 1 scenario                                                 | 1   |
| `4_run_benchmark.sh`                      | launcher tmux tổng quát — dùng cho **tune**                          | 4   |
| `.../01_audit_preflight.py`               | audit trước launch: pod/auth/model/flags/smoke/disk                  | 6.1 |
| `.../02_run_ladder.sh`                    | launcher ladder 4 size × 3 run × 10 agent                            | 5   |
| `.../03_audit_inflight.py`                | audit khi đang chạy: red-flag trong log + progress freshness         | 6.2 |
| `.../04_audit_postrun.py`                 | audit sau run: completeness / integrity / metrics / trường RQ2       | 6.3 |
| `.../04_repair_ladder_results.py`         | chấm lại judge cho agent lỗi transient, **không** sinh lại output    | 6.4 |
| `.../05_sync_embed_pod_env.py`            | sync embed pod → `EMBED_SLOTS` + `<SLOT>_EMBED_*` vào `.env`         | 7   |
| `.../06_score_alignment.py`               | chấm alignment RQ2 (không LLM), sweep nhiều encoder trong một lệnh   | 7   |
| `.../07_pool_ladder_runs.py`              | pool 12 run → `pooled_ladder.bk.json` + stats + token usage             | 8   |
| `.../ablation/08_pool_ablation_runs.py`   | pool 4 arm từ chính run dir ladder → `pooled_ablation.bk.json`          | 5.4 |
| `.../09_gen_paper_tables.py`              | `.tex` + macro số liệu → `results/generated/`                        | 9   |
| `.../10_gen_paper_figures.py`             | hình RQ1/RQ2 → `results/generated/figures/`                          | 9   |
| `.../ablation/11_gen_ablation_tables.py`  | `tab_ablation.tex` + `abl_macros.tex` + `stats_ablation.md`          | 5.4 |
| `.../ablation/12_gen_ablation_figures.py` | `figures/fig_ablation*`                                              | 5.4 |
| `.../14_gen_sensitivity_table.py`         | `tab_sensitivity.tex` + `sens_macros.tex` từ `alignment_sensitivity` | 9   |
| `.../15_gen_facts_sheet.py`               | `facts.md` (+ `facts_brief.md`): GỘP mọi số tổng hợp vào MỘT file    | 9.2 |
| `.../99_audit_artifacts.py`               | cổng cuối: artifact/figure/table đủ, thật, mới, đã wire vào paper    | 9.1 |

---

## 1. Setup

```bash
cd isd-agent-benchmark
./scripts/1_setup.sh              # venv + deps + agents + evaluator (editable)
python run_benchmark.py --check   # mọi agent module import sạch
./scripts/3_run_benchmark_test.sh # smoke 1 scenario
```

### `.env`

Agent model và judge model cấu hình **tách biệt** (tránh self-preference bias). Judge giữ nguyên xuyên suốt.

```bash
# --- secrets ---
OPENROUTER_API_KEY=sk-or-...     # judge
RUNPOD_API_KEY=rpa_...           # chỉ để script list pod (read-only)
VLLM_API_KEY=...                 # Bearer token của server vLLM (khớp RunPod secret)

# --- judge (cố định mọi giai đoạn) ---
JUDGE_MODEL_PROVIDER=openrouter
JUDGE_MODEL_NAMES=openai/gpt-4o-mini,google/gemini-2.5-flash-lite
JUDGE_MODEL_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL_API_KEY_ENV=OPENROUTER_API_KEY

# --- agent model ---
# Smoke test: dùng hosted API qua AGENT_MODEL_{PROVIDER,NAME,BASE_URL,API_KEY_ENV} global.
# Tune/bench: KHÔNG viết tay. Chạy 3_sync_runpod_pods_env.py → nó append managed block
# gồm QWEN{08B,2B,4B,9B}_AGENT_MODEL_{PROVIDER,BASE_URLS,NAME,API_KEY_ENVS} + 3 flag bảo hộ.

# --- tuỳ chọn ladder ---
# RATE_LIMIT=turbo                # conservative|moderate|aggressive|turbo
# QWEN08B_RATE_LIMIT=conservative # override per-slot
```

Một slot có thể có **nhiều pod**: script gom mọi pod cùng model vào `<SLOT>_AGENT_MODEL_BASE_URLS`
(comma-separated), agent round-robin qua chúng. Pod trong cùng slot phải serve cùng model — script hard-fail nếu khác.

## 2. Split data

Đã chạy và commit sẵn (seed 42) — chỉ chạy lại nếu làm từ đầu.

```bash
./scripts/2_split_data.sh    # → scenarios/train/ (~24.6k), scenarios/test/ (~1.2k), stratified
python scripts/2_split_stratified_subset.py --source scenarios/train --target scenarios/train_30              # 30, để TUNE
python scripts/2_split_stratified_subset.py --source scenarios/test  --target scenarios/test_90 --per-cell 3  # 90, để BENCH
```

Lưới stratify: 10 domain × 3 difficulty. Metadata (`scenarios/*_metadata.json`) ghi seed/nguồn/số lượng — giữ cho phần
reproducibility. `train_30` lấy từ train split nên tune thoải mái không đụng test.

## 3. Serving (RunPod + vLLM)

> Mục này là nguồn để viết **Experimental Setup** của paper.

### 3.1 Ladder

| Slot    | Checkpoint          | GPU           |
|---------|---------------------|---------------|
| qwen08b | `Qwen/Qwen3.5-0.8B` | RTX 4090 24GB |
| qwen2b  | `Qwen/Qwen3.5-2B`   | RTX 4090 24GB |
| qwen4b  | `Qwen/Qwen3.5-4B`   | RTX 4090 24GB |
| qwen9b  | `Qwen/Qwen3.5-9B`   | RTX 5090 32GB |

### 3.2 Serving stack (viết vào Methods)

vLLM `v0.25.1`, bf16, context **16384** cho cả 4 model, mỗi model một pod, endpoint OpenAI-compatible, auth Bearer.

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
--enable-prefix-caching
```

### 3.3 Ba flag bảo hộ — bắt buộc, đảm bảo tính công bằng của so sánh

```bash
AGENT_MODEL_MAX_OUTPUT_TOKENS=8192
AGENT_MODEL_STREAMING=1
AGENT_MODEL_DISABLE_THINKING=1
```

Cả ba do `3_sync_runpod_pods_env.py` tự ghi vào managed block, áp **đồng loạt mọi agent và mọi size** nên không tạo lợi
thế riêng — đó là luận điểm fairness.

### 3.4 Tạo pod + sync env

Pod tạo thủ công trên console từ template public dùng chung cho cả 4 size:
**<https://console.runpod.io/deploy?template=x4cakqmn77>**

1. Deploy → chọn GPU theo bảng 3.1.
2. Đổi model: sửa **token positional đầu tiên** của container start command thành HF id của slot. RunPod truyền start
   command như Docker CMD thuần (không shell, không expand `$ENV`) nên **không đổi model bằng env var được**. Không sửa
   flag phía sau.
3. Auth đã đấu sẵn qua RunPod secret `VLLM_API_KEY` — đảm bảo secret trùng giá trị trong `.env`. Không cần `HF_TOKEN`.
4. Chờ `GET https://<pod_id>-8000.proxy.runpod.net/v1/models` trả 401 (không key) / 200 (có key).

Storage: container 20GB + mỗi pod một network volume mount `/workspace` cho HF cache — weights sống sót qua restart.

```bash
python scripts/3_sync_runpod_pods_env.py    # --dry-run để xem block trước
source .env
```

Script **chỉ đọc** RunPod API: list pod, match slot, **verify model thật qua `/v1/models` của chính pod**, rồi ghi đè
managed block ở cuối `.env` (giữa hai marker). Chạy lại là thay block, không duplicate, không đụng phần còn lại.
Env-quad nhận bất kỳ provider OpenAI-compatible nào nên có thể thay một slot bằng hosted API.

## 4. Tune trên `train_30`

Chỉnh prompt/config của `alignmentgraph-isd` trên tập tách biệt với tập báo cáo.

```bash
DATASET=train_30 AGENT_MODEL_SLOTS=qwen2b AGENTS=baseline,react-isd,alignmentgraph-isd \
RUN_TAGS=tune1 ./scripts/4_run_benchmark.sh
```

- `AGENT_MODEL_SLOTS` nhiều slot = chạy **song song** (mỗi slot một tmux session). `RUN_TAGS` nhiều tag = chạy **tuần
  tự** trong mỗi session (`tune1,tune2,tune3` để đo độ ổn định cùng code).
- Kết quả vào `results/train_30_benchmark_<model>_tune<N>_<ts>/`. Tag `tuneN` để không lẫn với run báo cáo `r1/r2/r3`.
- Thu hẹp `--agents` cho rẻ khi debug, nhưng **vòng chốt cuối chạy đủ 7 agent** để chắc thay đổi không phá agent khác.
- Kết thúc tune = **commit đóng băng code** (manifest ladder sẽ ghi commit hash).

## 5. Bench `test_90` — ladder

### 5.1 Quy mô

4 size × 3 run × 10 agent × 90 scenario ≈ **10 800 agent generation**, mỗi generation thêm 2 judge evaluation.
Một run đơn ở rate `turbo` mất vài giờ; cả ladder ~1 ngày wall-clock (size chạy song song, 3 run của một size tuần tự).

10 agent = 6 default + `alignmentgraph-isd` + 3 arm ablation. Không cái nào nằm trong defaults — launcher đã thêm sẵn.

### 5.2 Launch

```bash
source .env
./scripts/alignmentgraph-isd-bench/02_run_ladder.sh    # gõ "yes" ở prompt
```

- Env-quad lấy từ managed block; thiếu base URL ⇒ hard-fail kèm hướng dẫn.
- Mỗi size một tmux session (`ladder-qwen08b`...), chạy **song song**; trong mỗi session 3 run **tuần tự** với
  `--run-tag r1|r2|r3` → `results/test_90_benchmark_<model>_r<N>_<ts>/`.
- **Manifest reproducibility** ghi TRƯỚC khi launch vào `results/ladder_<ts>/ladder_manifest.json`: model/provider/URL
  từng slot, dataset, agents, run tag, judge model, **git commit của cả benchmark lẫn monorepo cha**. Giữ file này.
- Log per-slot: `results/ladder_<ts>/<slot>.log`.

Monitor: `tmux attach -t ladder-qwen2b` (detach `Ctrl+B, D`) hoặc `tail -f results/ladder_*/qwen2b.log`.

**Resume từng phần** — mỗi (size, run) là một invocation độc lập:

```bash
LADDER_SLOTS="qwen4b" RUN_TAGS="r2,r3" ./scripts/alignmentgraph-isd-bench/02_run_ladder.sh
```

Mỗi lần re-launch ghi manifest mới — giữ tất cả. **Không xoá** run dir dở dang vội: script pool báo tường minh scenario
thiếu; chỉ xoá dir cũ **sau khi** pool xác nhận dir mới đủ 90 scenario.

### 5.3 Rate limit

`RATE_LIMIT` (default `turbo`) là preset toàn cục đặt worker count + `BENCHMARK_DELAY`. Override per-slot bằng
`<SLOT>_RATE_LIMIT`. Rate được echo lúc launch và ghi vào manifest. `run_benchmark.py` publish posture của nó ra env
dưới dạng `BENCHMARK_RATE_LIMIT` + `BENCHMARK_DELAY` — không biết gì về knob nội bộ của agent nào.

**Concurrency bên trong một agent (2026-08-31).** `max_workers` × `scenario_max_workers` chỉ chặn số **agent** chạy
đồng thời. Agent nào tự fan-out bên trong thì nằm ngoài posture đó: `alignmentgraph-isd` chạy `content_designer` và
`rubric_designer` trong cùng một superstep, mỗi family lại phát một call cho mỗi work set, nên **một agent đạt đỉnh
~12 request đồng thời** (đo trên fixture test) trong khi scheduler ngoài vẫn đếm nó là 1 unit. Endpoint dùng chung trả
`429 Per-user concurrency limit exceeded` và **chỉ đánh vào hai arm multi** (9–25 lỗi/run qua ba run, so với 0–2 ở hai
arm single chạy tuần tự) — tức nhiễu throttling rơi đúng vào trục ablation `agent_mode`.

Agent nào tự fan-out thì phải tự chặn mình. Adapter `alignmentgraph-isd` đọc `BENCHMARK_RATE_LIMIT` và map sang cap
của riêng nó (`LLM_CONCURRENCY_BY_RATE_LIMIT`: conservative 2 / moderate 3 / aggressive 4 / turbo 6 — preset lạ hoặc
không có thì dùng 4), rồi truyền vào `HarnessRunConfig.llm_max_concurrency`. Ghi đè bằng
`HARNESS_LLM_MAX_CONCURRENCY` (đặt `0` để tắt hẳn); `HARNESS_LLM_MIN_INTERVAL` giãn thời điểm bắt đầu call cho endpoint
đo theo rate thay vì theo concurrency, mặc định tắt.

Tổng request in-flight = `max_workers × scenario_max_workers × cap`. Gate là **per-run**, không process-wide: gate chung
sẽ khiến fan-out của arm này xếp hàng trước call của arm kia và thổi phồng `execution_time_seconds` của arm kia.
Cap thực tế được ghi vào `metadata.run_config.llm_max_concurrency` nên mỗi results dir tự nói được nó chạy posture nào.

**Hệ quả cần biết:** arm multi sẽ chậm hơn trước vì fan-out bị chia thành nhiều đợt. Đó là cái giá để hai phía của trục
`agent_mode` chịu cùng một điều kiện phục vụ. Mọi số multi-vs-single đo trước 2026-08-31 đều dính nhiễu này.

### 5.4 Ablation (4 arm, nằm trong chính run của ladder)

**Không có benchmark run riêng.** 4 arm chạy như 4 agent bên trong run ladder nên được gộp 3 run/size như phần còn lại,
và mọi arm được chấm trong **cùng judge session** per scenario → delta arm-vs-A0 không dính judge drift. A0 **chính là**
`alignmentgraph-isd` của ladder, nên không bảng nào cần chú thích hoà giải hai con số A0.

**Trần ILO có ở CẢ BỐN arm và không có ở baseline (2026-09-10).** Harness tính
`per_goal(context.duration) × len(learning_goals)` (2/3/4 cho ngắn/vừa/dài) và đưa con số đó vào rules của stage
`outcomes`. Nó nằm trong hệ được kiểm chứ không phải một control áp cho cả benchmark, nên khi so alignmentgraph với
baseline thì phải nói rõ. Giữa bốn arm thì nó là hằng số, nên không ảnh hưởng delta arm-vs-A0. Trần **không được
cưỡng chế**; `metadata.objective_ceiling` ghi lại và tỷ lệ tuân thủ là số cần báo cáo (xem Phụ lục A.4).

Ma trận 2×2 = `agent_mode` (decomposition) × `context_mode` (alignment machinery):

| Arm            | agent_id                          | agent_mode | context_mode |
|----------------|-----------------------------------|------------|--------------|
| multi + graph  | `alignmentgraph-isd`              | multi      | graph        |
| multi + prose  | `alignmentgraph-isd-multi-prose`  | multi      | prose        |
| single + graph | `alignmentgraph-isd-single-graph` | single     | graph        |
| single + prose | `alignmentgraph-isd-single-prose` | single     | prose        |

`context_mode="prose"` là **prose blackboard graph-free** (`core/prose_store.py::ProseStore`), KHÔNG phải một cách render
khác của cùng dữ liệu graph: mỗi step lưu nguyên cục JSON đã parse vào một document key; step sau đọc lại verbatim
theo read-list tĩnh (pattern named-slice của các agent không-graph); safeguard chỉ còn 5 within-artifact check
(bloom verbs, measurability, rubric consistency, evaluation quality, actionability) + self-repair/regen dùng chung;
không routing, không docket, không residual audit, và run **không có** key `graph`/`graph_dot` → không có file
`<agent_id>_graph.json/.dot` cho hai arm prose (đó chính là contrast auditability, không phải thiếu file); thay vào đó
hai arm prose ghi `<agent_id>_prose.json` — dump nguyên văn các document trên blackboard (artifact để inspect/debug,
KHÔNG phải audit: không relation, không coverage). Trục vì
vậy là một **bundle** ("bỏ máy alignment thì harness còn gì") và phải được disclose như bundle, không claim
single-variable.

Axes là **kwargs cố định theo agent_id** trong registry của `run_benchmark.py` (không phải env var) → không chạy nhầm
config được; mỗi run ghi `metadata.run_config` vào trajectory và script pool **hard-fail** nếu flag không khớp agent_id.

Post-processing chạy **sau khi ladder xong** (consistency check cần `pooled_ladder.bk.json`):

```bash
python scripts/alignmentgraph-isd-bench/ablation/08_pool_ablation_runs.py \
    --auto-glob 'results/test_90_benchmark_*_r[123]_*' \
    --ladder-pooled results/pooled_ladder.json          # → results/pooled_ablation.json
python scripts/alignmentgraph-isd-bench/ablation/11_gen_ablation_tables.py
python scripts/alignmentgraph-isd-bench/ablation/12_gen_ablation_figures.py
```

**Đọc theo lưới 2×2, không chỉ theo "vs A0".** Bốn arm là một **thiết kế giai thừa đầy đủ** (decomposition ×
alignment machinery). So từng arm với A0 (= multi+graph) chỉ là *main effect*, và nó **giấu mất** trường hợp một cơ chế trông như vô dụng chỉ vì
cơ chế kia đã ngăn lỗi từ trước. `08` vì vậy sinh thêm hai khối:

- **`factorial`** — simple effect của từng cơ chế dưới **cả hai trạng thái** của cơ chế kia, cộng **tương tác**
  (hiệu của hai simple effect; âm = hai cơ chế **thay thế** nhau). Tính trên cả `addie_median` lẫn
  `objective_assessment_similarity`, paired per-scenario, Wilcoxon + bootstrap CI. Báo **không hiệu chỉnh**: đây là các
  contrast cấu trúc của thiết kế, không phải một family so-sánh-với-A0.
- **`verifier_activity`** — số lần verifier chạy / số lần **sửa** mỗi scenario, đọc từ `verifier_events` /
  `repair_events` trong trajectory. Đây là bằng chứng **cơ chế**: nó tách "thành phần không chạy" khỏi "chạy nhưng
  không còn việc để làm".

Artifact tương ứng: `tab_ablation_factorial.tex` (dẫn 1 tín hiệu chính) kèm `tab_ablation_factorial_full.tex`
(bản đầy đủ 2×2 read trên toàn bộ 10 tín hiệu báo cáo, phụ lục), macro `\ablVerifCtxOn/Off*` + `\ablInteraction*` +
`\ablRepairs*`, hình `fig_ablation_factorial`, và section "2x2 factorial" trong `stats_ablation.md`.

Diễn giải cần ghi trong paper:

- Hướng delta trong bảng/hình = **arm − A0** (âm = gỡ thành phần làm giảm chất lượng); trong `pooled_ablation.bk.json` các
  row comparison lưu chiều A0 − arm (contribution).
- `07_pool_ladder_runs.py` chỉ xét proposed + 6 baseline nên 3 arm nằm cùng run dir **không bị nuốt** vào phía ladder.
- Ở hai arm prose, mọi cơ chế cross-artifact (edge checks, docket, plan_coverage, routing, residual audit,
  aggregator coverage-net, `design.alignment_matrix`) **vắng theo thiết kế** — chênh lệch từ đó là **một phần của
  hiệu ứng đo được**, không phải bug. Regen loop + 5 within-artifact check + self-repair **bật ở mọi arm**.
- `a0_consistency` giờ là **invariant check**: delta phải ~0. Khác 0 = hai lần pool đọc lệch nhau trên cùng dữ liệu →
  lỗi cần sửa, không phải drift để giải thích.

## 6. Audit

Cấu trúc results: `results/test_90_benchmark_<model>_r<N>_<ts>/test_90/<scenario_id>/` chứa `{agent}_output.json`,
`{agent}_trajectory.json`, `{agent}_log.txt`, `comparison_report.json`; summary ở `benchmark_summary.json` +
`SUMMARY.md`.

### 6.1 Pre-flight

```bash
python scripts/alignmentgraph-isd-bench/01_audit_preflight.py     # --no-smoke để bỏ smoke call
```

Check: 4 pod alive + auth (401/200), model khớp slot, smoke non-thinking thật sự ăn (response **không có**
`reasoning_content`, `content` có chữ), 3 flag bảo hộ có mặt, disk trống.

### 6.2 In-flight (mỗi 30–60 phút)

```bash
python scripts/alignmentgraph-isd-bench/03_audit_inflight.py      # watch -n 300 để theo dõi liên tục
```

Đếm 524 / 400 / empty / stub trong log — **phải đứng yên ở 0** — cộng ✅/❌ per slot và progress freshness
(timestamp mới < 10 phút). GPU util = 0% kéo dài + progress đứng = treo.

### 6.3 Post-run

```bash
python scripts/alignmentgraph-isd-bench/04_audit_postrun.py                          # mọi run dir
python scripts/alignmentgraph-isd-bench/04_audit_postrun.py --fields-only <run_dir>  # riêng các trường RQ2 tiêu thụ
```

Script phân biệt **RED** (lỗi hạ tầng: stub / rỗng / token=0 / sai model / thiếu metric) với **info** (agent fail kiểu
capability — hợp lệ, failure policy ở mục 8 xử lý, **không** re-run). Nó phủ ba tầng:

- **Completeness** — 90 scenario/run; mỗi scenario đủ output của các agent; có `comparison_report.json`;
  `benchmark_summary.json` tồn tại; đủ 3 run × 4 size trước khi pool.
- **Integrity** — stub/default output (stub đủ 33 sub-item nên nhìn "đầy đủ", phải quét bằng marker), output < 1KB,
  trajectory rỗng, `token_usage.total_tokens = 0`, model name trong metadata khớp thư mục run, duration hợp lý.
- **Metrics** — mỗi `comparison_report.json` có `total_score` (median multi-judge), `addie_score`, `trajectory_score`;
  đủ 5 phase ADDIE; đủ số judge cấu hình; phân phối điểm sanity (không agent nào toàn 0 hoặc toàn 100).

`--fields-only` gọi thẳng extractor của evaluator để xem **đúng những trường RQ2 tiêu thụ** (objectives / assessments /
activities / evaluation) có rỗng không. Quan trọng: output parse được nhưng không trích ra objective nào sẽ bị chấm
`0.0` và trông y hệt một thiết kế lệch thật — chỉ ở đây mới phân biệt được parse fail với chất lượng kém.

> ⚠️ **Bẫy CSV Avg**: cột `Avg` trong aggregate CSV là judge-mean, lệch khi thiếu component. Số chuẩn cho paper luôn là
> per-scenario `total_score`.

### 6.4 Red flags

| Dấu hiệu                         | Ý nghĩa                       | Hành động                                  |
|----------------------------------|-------------------------------|--------------------------------------------|
| `Error code: 524`                | Proxy cắt call >120s          | Dừng, kiểm `AGENT_MODEL_STREAMING`         |
| `Error code: 400` max context    | Cap không ăn / prompt quá dài | Kiểm `AGENT_MODEL_MAX_OUTPUT_TOKENS`          |
| `기본 출력 반환` / stub marker         | Baseline ghi default output   | Loại scenario/run, tìm nguyên nhân rỗng    |
| `응답 길이: 0`                       | Model trả rỗng                | Kiểm non-thinking flag + pod log           |
| `token_usage = 0` hàng loạt      | Accounting hỏng               | Sửa trước khi chạy tiếp — số token sai hết |
| `token_usage = 0` ở **một số** agent | Agent đó dùng `LLMConfig` đã tách khỏi counter của run | Counter đi theo lineage của config: `_get_agent_runner` mở scope bằng `new_token_scope()`, `copy_with()` chia sẻ lại. Chạy `pytest shared/tests/test_token_accounting_reaches_agents.py` |
| Model name metadata ≠ run dir    | Nhầm URL pod ↔ slot           | Loại run, kiểm managed block               |
| `evaluation_error` trong summary | Judge chết giữa chừng         | `04_repair_ladder_results.py` (xem dưới)   |
| Pod EXITED giữa run              | OOM/crash server              | Xem RunPod console log, kiểm VRAM          |

Judge lỗi transient sửa được **không cần sinh lại output**:

```bash
python scripts/alignmentgraph-isd-bench/04_repair_ladder_results.py --dry-run   # xem phạm vi, không gọi judge
python scripts/alignmentgraph-isd-bench/04_repair_ladder_results.py             # sửa rồi tự chạy audit post-run
```

Script chấm lại từng agent bị ảnh hưởng trong thư mục tạm rồi merge **đúng row đó** vào report gốc (vì
`compare --agents X` sẽ ghi đè cả report), đồng bộ `benchmark_summary.json`/`SUMMARY.md`, tạo backup
`.pre-judge-repair`.
Output và trajectory chỉ được đọc, không bao giờ sinh lại.

## 7. Score alignment (RQ2)

Bước này **không nằm trong ladder**, phải chạy tay sau bench. Chỉ đọc `*_output.json` và ghi
`alignment_scores.json` vào từng scenario dir. Thiếu bước này thì mục 8 vẫn chạy nhưng **bỏ trống toàn bộ RQ2**
(graceful skip — dễ quên).

**Chỉ encoder primary (8B) cần pod.** Mọi arm còn lại chạy trên máy local (A.3). Pod dùng cùng convention template
ladder: **<https://console.runpod.io/deploy?template=3i3er665bh>** — GPU ≥24GB (bf16 weights ~16GB), không sửa start
command. Deploy **nhiều pod cùng lúc** thì scorer tự load-balance round-robin song song qua chúng.

Chuẩn bị trước một lần: checkpoint Bloom (arm chính) — xem A.3.

```bash
RUNS='results/test_90_benchmark_*_r[123]_*'

# (1) arm primary — cần pod đang chạy
python scripts/alignmentgraph-isd-bench/05_sync_embed_pod_env.py   # --dry-run để xem trước
source .env    # → EMBED_SLOTS + NEMOTRON_EMBED_{BASE_URLS,MODEL,API_KEY_ENV}
python scripts/alignmentgraph-isd-bench/06_score_alignment.py $RUNS

# (2) TẮT POD, rồi chấm 3 arm sensitivity còn lại hoàn toàn local (~70 phút)
python scripts/alignmentgraph-isd-bench/06_score_alignment.py $RUNS \
    --encoder-presets bgem3,granite,tfidf --bloom-presets lexicon
```

Tách hai bước như trên là cách rẻ nhất: pod chỉ sống đúng khoảng thời gian chấm arm primary. Chạy một phát
`--all-arms` cũng đúng, chỉ là pod nằm không trong lúc ba arm local chạy.

**Sweep là hình sao, không phải lưới.** Cấu hình chính = (`nemotron` + `bertbloom`); mỗi arm lệch **đúng một trục**.
Tổng 5 arm (1 chính + 3 encoder + 1 Bloom), không phải 4×2 = 8 — lưới không trả lời thêm câu hỏi nào mà nhân đôi chi
phí lẫn diện tích phải kiểm.

Trục Bloom **không tùy chọn**: 3/7 tín hiệu panel do Bloom sinh ra, bỏ trục này thì cả họ B không được kiểm bởi
trục nào. Arm chính `bertbloom` cần checkpoint (train một lần, ~15 phút trên máy local); arm sweep `lexicon` gần như
miễn phí — chạy CPU, vector lấy từ cache:

```bash
# cần checkpoint trước (một lần, vài phút GPU):
python evaluator/scripts/train_bloom_6way_classifier.py --train ../EDM2022CLO/data/sample_full.csv \
    --output-dir models/bloom-bert-edm2022
python scripts/alignmentgraph-isd-bench/06_score_alignment.py --bloom-presets lexicon --embed-cache-only $RUNS
```

Cách scorer hoạt động:

- Instrument **chỉ chọn được qua preset** (`ENCODER_PRESETS` / `BLOOM_PRESETS`); không cờ model/URL tự do. Không
  truyền cờ nào = chạy đúng cấu hình chính. Preset quyết định luôn **backend**: arm `api` lấy endpoint từ
  `<SLOT>_EMBED_BASE_URLS`, arm `local` chạy in-process (thiết bị tự chọn — `mps`/`cuda`/`cpu`, ép bằng
  `--local-device`). Arm không có pod (hoặc arm Bloom không có checkpoint) thì **SKIP kèm lý do** chứ không làm hỏng
  cả sweep — bù sau gần như miễn phí nhờ cache. `--require-all` nếu muốn "đủ mọi arm hoặc không chạy". Arm BERT **không bao giờ âm thầm fallback về
  lexicon**: fallback sẽ khiến trục sensitivity tự đồng thuận với chính nó rồi báo đó là instrument independence.
- `nemotron` ghi artifact **không suffix** — file duy nhất mà pooling đọc. Arm khác ghi
  `alignment_scores.<suffix>.json`.
- Mỗi lần gọi còn ghi một roster dạng long `results/alignment_sweep_<timestamp>.csv` (một dòng mỗi arm × run dir ×
  agent). **Có timestamp** vì sweep thường chạy làm nhiều lượt — arm primary, rồi các arm local, rồi re-score Bloom —
  và tên cố định thì lượt sau xoá roster của lượt trước. Ghim tên bằng `--sweep-csv <path>`. **Luôn được ghi** —
  không có cách tắt, vì mỗi lần chấm phải để lại dấu vết nó đã phủ những arm nào.
- Scorer hỏi `/v1/models` **từng arm** và **hard-fail** nếu pod serve model khác preset: cache key là
  `sha1(model[@revision] + text)` nên chấm nhầm pod sẽ ghi vector sai dưới key trông đúng — hỏng ngầm.
- **Pod không trả lời `/v1/models` bị loại khỏi `.env`** khi sync (tên model trong record RunPod chỉ là *nhãn pod*,
  không phải bằng chứng về thứ đang được serve). Pod đang boot thì chờ rồi re-run; `--allow-unverified` để ép.
- `tfidf` thuần CPU, luôn chạy được kể cả khi không pod nào sống. Chỉ có 1 GPU thì bật từng pod một rồi lặp lại đúng
  lệnh trên — arm đã xong được bỏ qua.
- Chết giữa chừng: chạy lại **nguyên lệnh**. Scenario hoàn chỉnh được skip, file hỏng/thiếu tự chấm lại.

Embedding cache SQLite ở `results/.embed_cache_<model>.sqlite` — mỗi text encode đúng một lần, dùng chung mọi run dir và
mọi arm cùng model. `--embed-cache-only` cho phép chấm lại hoàn toàn offline.

**Re-score hay reaggregate?**

| Đổi cái gì                                                  | Lệnh                                                                                |
|-------------------------------------------------------------|-------------------------------------------------------------------------------------|
| Định nghĩa endpoint (bỏ tiêu chí, đổi cách tổng hợp)        | `--reaggregate` — đọc `details.objectives` có sẵn, tính lại, tức thì, không cần pod |
| Tín hiệu gốc (encoder, Bloom classifier, cách extract text) | `--overwrite` — re-score thật                                                       |

Cả hai đều phải re-pool + re-gen sau đó. **Đừng trộn hai cấu hình protocol trong một pool** — pooling hard-fail nếu
phát hiện nhiều bộ `(encoder, revision, bloom_classifier)`.

Validity evidence cho Bloom — chạy một lần, báo cả hai arm + κ giữa chúng:

```bash
python scripts/alignmentgraph-isd-bench/00_validate_bloom.py ../EDM2022CLO/data/sample_full.csv \
    --text-col Learning_outcome --label-cols Remember,Understand,Apply,Analyze,Evaluate,Create \
    --out results/generated/bloom_validation.md
# thêm arm BERT: trỏ CSV vào held-out split cạnh checkpoint, KHÔNG dùng corpus đã train
python scripts/alignmentgraph-isd-bench/00_validate_bloom.py models/bloom-bert-edm2022/eval_split.csv \
    --text-col text --label-col label --bloom-checkpoint models/bloom-bert-edm2022
```

## 8. Pool → thống kê RQ1 + RQ2

```bash
python scripts/alignmentgraph-isd-bench/07_pool_ladder_runs.py \
    --auto-glob 'results/test_90_benchmark_*_r*' --auto-encoders --auto-bloom
```

Output `results/pooled_ladder.json` + report stdout. Gộp 3 run/size (mean-of-runs), rồi per-size: Wilcoxon paired
(proposed vs 6 baseline), Holm, bootstrap CI, rank-biserial, 3 failure policy, interaction DiD + trend slope — định
nghĩa ở A.2. RQ2 pool từ `alignment_scores.json` (A.3). Kèm section `token_usage` (A.4).

- `--auto-encoders` (hoặc `--encoders bgem3,granite,tfidf`) thêm khoá `alignment_sensitivity`. `pooled["alignment"]`
  **luôn** là encoder chính nên `09`/`10`/ablation không đổi gì.
- Auto-glob nhóm dir theo tên model + run tag. Nếu nó vơ nhầm dir (run tune, run bỏ dở) thì dùng mapping tường minh
  `--model <key>=dir1,dir2,dir3`.
- Kiểm trước khi kết luận: CV giữa r1/r2/r3 của cùng (model, agent) quá lớn (>~20–30%) → soi run lệch. Trend theo size
  đảo chiều ở đâu → kiểm integrity chỗ đó trước khi coi là finding.

## 9. Sinh bảng, hình + macro cho paper

```bash
python scripts/alignmentgraph-isd-bench/09_gen_paper_tables.py --pooled results/pooled_ladder.json
python scripts/alignmentgraph-isd-bench/14_gen_sensitivity_table.py     # nếu có alignment_sensitivity
python scripts/alignmentgraph-isd-bench/10_gen_paper_figures.py --runs-glob 'results/test_90_benchmark_*_r*'
cd .. && docs/scripts/sync_generated.sh                                 # từ repo thesis
```

Tất cả ghi vào `results/generated/` (benchmark-local, gitignored): `tab_rq1.tex` (ADDIE-lead) kèm
`tab_rq1_total.tex`/`tab_rq1_traj.tex` (Total/Trajectory song song, cùng logic §A.2), `tab_rq2_alignment.tex`
(tín hiệu dẫn) kèm `tab_rq2_panel.tex` (panel đầy đủ 7 tín hiệu), `stats_macros.tex` (mọi con số trong prose là
`\newcommand`), `stats_summary.md` (bản dump người đọc để cross-check).

### 9.2 Facts sheet — gộp mọi số vào một file

```bash
python scripts/alignmentgraph-isd-bench/15_gen_facts_sheet.py           # → results/generated/facts.md (~135 KB)
python scripts/alignmentgraph-isd-bench/15_gen_facts_sheet.py --brief   # → facts_brief.md (~21 KB, chỉ mục 0–2)
```

Chạy **sau** `09`/`11`/`13`/`14` (nó đọc `*_macros.tex` để dựng mục 10). Nguồn: `pooled_ladder.bk.json` +
`pooled_ablation.bk.json` — không parse lại các `stats_*.md`, nên không có nguồn sự thật thứ hai.

**Vì sao cần**: số hiện nằm ở 6 file `stats_*.md` với **quy ước dấu khác nhau**, và hai họ tín hiệu (JUDGE rubric
/100 vs PANEL RQ2 [0,1]) **cho kết luận ngược nhau trên ablation**. Đọc một file rồi dừng là đủ để trích một con số
mang nghĩa ngược. Cụ thể đã vấp: đọc bảng ADDIE rồi kết luận "graph context không giúp gì", trong khi bảng panel
ngay dưới cùng file nói 28/28 ô ngược lại.

Bố cục — mục **0 = hợp đồng đọc** (hai họ tín hiệu, quy ước dấu từng bảng, 2 tầng Holm, chính sách failure, và
**những gì KHÔNG có trong file**); mục **2 = roll-up tính sẵn** để không ai đếm ô bằng mắt:

- 2.1/2.2 — mỗi baseline × tín hiệu: thắng/thua/n.s. ở mấy size, khoảng Δ.
- 2.3 — mỗi arm × họ: số ô âm/dương/có ý nghĩa, khoảng Δ. Cột in ra là **`arm − A0`** (JSON lưu `A0 − arm`, đã lật).
- 2.4 — **kiểm gradient theo scale**: size nào giữ |Δ| lớn nhất, và verdict CONCENTRATED/SCATTERED. Đây là chốt chặn
  cho các câu kiểu "mạnh nhất ở model nhỏ" (A2 trên panel: SCATTERED đều cả 4 size → không được claim).
- 2.5 — **bảng bất đồng giữa hai họ**: mỗi dòng là một chỗ mà trích một họ thôi sẽ xuyên tạc kết quả.

Mục 3–9 là bảng đầy đủ per-cell; mục 10 là index mọi `\newcommand` — số nào trong paper mà không có ở đây tức là
**gõ tay**, vi phạm quy ước "số sinh tự động".

`facts.md` là tài liệu để đọc/đưa cho LLM diễn giải, **không** phải artifact paper `\input` — nên `99_audit_artifacts.py`
không kiểm nó.

**Quy ước artifact (2026-07-30, enforce bằng `99_audit_artifacts.py` check I):** mọi text trong artifact là
**tiếng Anh**, số dùng **dấu chấm** (`87.77`). Caption chỉ nói *bảng chiếu gì* và *một ô là gì*, ~100–250 ký tự;
phần biện luận phương pháp thuộc mục Methods. Mean và ±SD phải cùng một signal (`run_to_run_sd_{addie,traj,total}`
trong pooled; `run_to_run_sd` trần là Total, chỉ còn tồn tại cho `08_pool_ablation_runs.py`). Ô nào tính trên tập
scenario thiếu thì phải in `n` + footnote — RQ2 đếm scenario có **ít nhất một** run chấm được, điều kiện yếu hơn
complete-case đủ 3 run của RQ1, nên hai bảng ghi nhãn khác nhau.
Số format kiểu VN (`{,}`). `sync_generated.sh` là **bước copy duy nhất** sang `docs/generated/`; LaTeX trỏ tới đó bằng
đường dẫn tương đối.

Hình (cả `.pdf` vector lẫn `.png` preview; text trong hình tiếng Anh, caption tiếng Việt viết trong LaTeX):

| Hình                     | Nội dung                                                                     |
|--------------------------|------------------------------------------------------------------------------|
| `fig_rq1_ladder`         | Total vs model size, error bar = run-to-run SD (headline RQ1)                |
| `fig_rq1_delta`          | Δ(proposed − baseline) per size, CI95, marker đặc = p_holm < 0,05, kèm slope |
| `fig_rq1_components`     | ADDIE vs Trajectory theo size                                                |
| `fig_rq2_ladder`         | Objective–assessment alignment vs size (headline RQ2)                        |
| `fig_rq2_components`     | Heatmap agents × 5 alignment component per size                              |
| `fig_rq2_vs_rq1_scatter` | Per-scenario alignment vs Total, Spearman ρ per size — cần `--runs-glob`     |
| `fig_failure_rate`       | % scenario fail per agent × size                                             |
| `fig_cost_quality`       | Total vs total token / exec time (deployment-cost angle)                     |

`--demo` render bằng dữ liệu synthetic để test layout. Thiếu alignment/token data ⇒ hình tương ứng skip kèm cảnh báo.

Điều kiện serve phải ghi trong paper (bf16, 16k, non-thinking, streaming, cap 8192) — lấy nguyên văn từ mục 3.

## 9.1 Cổng cuối: audit artifact

```bash
python scripts/alignmentgraph-isd-bench/99_audit_artifacts.py            # sau khi đã sync
python scripts/alignmentgraph-isd-bench/99_audit_artifacts.py --strict   # WARN cũng fail
python scripts/alignmentgraph-isd-bench/99_audit_artifacts.py --no-docs  # chỉ phía benchmark
```

Chạy **sau** toàn bộ 9 (kể cả `sync_generated.sh`). Có mặt file là kiểm tra yếu nhất, nên script soi 8 lớp:
drift inventory (A — quét thẳng source của 5 generator, hai chiều, nên generator thêm output mới thì không thể lọt),
thiếu file (B), lệch sync docs↔results theo **byte** + `sync_generated.sh` có thực sự copy artifact đó không (C),
placeholder/TBD-DEMO (D — generator cố tình sinh file comment-only `\input` được khi thiếu pooled layer, LaTeX vẫn
compile và bảng biến mất im lặng), độ mới đọc từ **header** chứ không phải mtime (E — sync là `cp` nên restamp mọi
file), figure phải đủ cặp `.pdf`+`.png` (F), `\input`/`\includegraphics` có resolve và artifact nào chưa ai tham
chiếu (G), và macro nào prose dùng mà không generator nào định nghĩa (H — `Undefined control sequence`, lỗi build
mà kiểm tra file không bao giờ thấy).

Cái gì là *bắt buộc* phụ thuộc pooled layer đang có: artifact ablation chỉ bị đòi khi có `pooled_ablation.bk.json`,
sensitivity khi pooled ladder có `alignment_sensitivity`; hai file bloom validation luôn chỉ WARN vì cần checkpoint
train tay. Exit 0 = không RED (và không WARN nếu `--strict`).

## 10. Teardown

- **Tắt/xoá pod RunPod ngay** (thao tác console, không có script) — tính tiền theo giờ kể cả idle.
- Giữ nguyên vẹn: mọi `results/test_90_benchmark_*_r*/`, mọi `ladder_manifest.json`, `pooled_ladder.bk.json`,
  `scenarios/*_metadata.json`, và managed block trong `.env`.
- Số và hình trong paper regenerate được bất kỳ lúc nào từ raw results bằng chuỗi mục 7 → 8 → 9.

---

# Phụ lục A — Metrics reference

Ba nhóm, theo nguồn tính toán thực tế trong code:

1. **Judge quality metrics** (A.1) — LLM judge chấm từng ADDIE output, nguồn cho RQ1.
2. **RQ1 statistics** (A.2) — thống kê suy diễn trên các judge metric đã pool theo model size.
3. **RQ2 alignment protocol** (A.3) — thước đo constructive alignment tự động, **không LLM**, độc lập với judge và với
   verifier nội bộ của harness.

Cộng thêm **operational metadata** (A.4) — log để debug, không vào headline stats.

## A.1 Judge quality metrics (per-scenario)

Nguồn: [`evaluator/src/isd_evaluator/`](../isd-agent-benchmark/evaluator/src/isd_evaluator/).

**ADDIE Rubric Score (0–100)** — `metrics/addie_rubric.py`, rubric ở `rubrics/addie_definitions.py`. Hai bước LLM-judge
tuần tự cho mỗi sub-item: (1) *status* — phân loại vào `absent/weak/moderate/good/excellent`, mỗi trạng thái ứng một
khoảng điểm cố định; (2) *score* — chấm chi tiết, **bị ép cứng** nằm trong khoảng của status, tránh judge chấm vượt
khung. **33 sub-item** (Context-Matrix) → trung bình thành **13 item** → **5 phase ADDIE**. Trọng số phase mặc định
Analysis 25 / Design 25 / Development 20 / Implementation 15 / Evaluation 15, điều chỉnh động theo context scenario
(`metrics/context_weights.py`: suy ra hồ sơ ngữ cảnh — loại tổ chức, hình thức triển khai, người học, domain, quy mô
lớp, thời lượng — rồi cộng/trừ trọng số, kẹp trong [0,05; 0,50], chuẩn hoá tổng = 1; scenario "PBL" thì Design +
Evaluation nặng hơn Development, "VR" thì ngược lại). `normalized_score = total_weighted / max_possible × 100`.

**Trajectory Score (0–100)** — `metrics/trajectory.py`. Đo **chất lượng quá trình** (không phải output cuối), khung
BFCL,
4 chiều × 25 điểm: *Tool Correctness* (chọn đúng công cụ, tránh gọi thừa), *Argument Accuracy* (tham số đúng
giá trị/kiểu/không thiếu field), *Redundancy Avoidance* (tránh gọi lặp, tránh chia nhỏ vô ích), *Result Utilization*
(dùng kết quả tool vào bước sau, phục hồi hợp lý khi tool lỗi). Cùng một chuẩn cho single-agent và multi-agent.

**Total composite (0–100)** — `models/__init__.py`:

```
Total = 0,7 × ADDIE.normalized_score + 0,3 × Trajectory.total
```

**Thước dẫn của RQ1 là `addie_median`, không phải composite** — ADDIE đo chất lượng nội dung thiết kế giảng dạy, tức
đúng construct câu hỏi nghiên cứu nhắm tới; `trajectory_score` đo process conformance (construct khác); `total_score`
mang trọng số 0,7/0,3 của benchmark, không đến từ câu hỏi nghiên cứu này. Cả ba tín hiệu được thống kê **y như nhau**
(3 failure policy, Holm theo từng (signal, policy)) dưới `comparisons.by_signal[<signal>]`, và `total_score` vẫn báo
đầy đủ để so sánh được với chính ISD-Agent-Bench. Quyết định này là **post-hoc** (chọn sau khi đã thấy kết quả) và
phải khai đúng như vậy trong paper.

Về composite: per-scenario `total_score` trong `comparison_report.json` —
**không phải** cột `Avg` của `aggregate_table.csv`.

## A.2 RQ1 statistics

File: [`07_pool_ladder_runs.py`](../isd-agent-benchmark/scripts/alignmentgraph-isd-bench/07_pool_ladder_runs.py).
Input: 4 size × 3 run × 90 scenario, mỗi scenario đã có `Total` cho từng agent.

- **`mean_total`** — trung bình `Total` của một agent tại một size, pool qua 3 run rồi qua scenario (complete-case là
  policy chính).
- **`run_to_run_sd`** — SD giữa 3 giá trị trung bình cấp-run (độ ổn định run-to-run, tách khỏi phương sai giữa
  scenario).
  Tính trên **đúng tập complete-case của `mean_total`**, không phải trên mọi scenario có điểm trong từng run: nếu mỗi
  run
  trung bình trên một tập scenario khác nhau thì các run mean không so sánh được, và độ tản của chúng lẫn biến thiên
  run-to-run với khác biệt thành phần scenario. Đây là con số in kèm `mean_total` trong `tab_rq1.tex` và làm error bar
  của `fig_rq1_ladder`, nên hai số phải cùng mẫu.
- **Paired Wilcoxon signed-rank** — khớp cặp theo scenario, proposed vs từng baseline, two-sided. Với `n_effective ≤ 25`
  dùng **exact permutation null** (bắt buộc: xấp xỉ chuẩn anti-conservative ở n nhỏ — exact p sàn two-sided là 0,25 tại
  n=3). Ô có complete-case n≤5 khai báo *not testable* bằng score test; bằng chứng tại đó lấy từ failure-rate test.
- **Fisher exact 2×2 trên output-failure** (secondary) — [failed, ok] × [proposed, baseline] cấp scenario, Holm/6 mỗi
  size. Đây là mặt robustness của luận điểm bù scale, dùng thay score test ở các ô n quá nhỏ. Run-level count chỉ báo
  cáo mô tả (các run cùng scenario không độc lập).
- **Holm correction** — step-down trên family gồm đúng 6 so sánh **trong cùng một size** → `p_holm`.
- **Bootstrap 95% CI** — 10 000 resample, seed 42, trên mean paired delta.
- **Rank-biserial r** — effect size của Wilcoxon, `r = (W⁺ − W⁻)/(W⁺ + W⁻)`, range [−1, 1].
- **Failure policies** — `complete_case` (chính, loại scenario thiếu) / `zero` (impute 0) / `min_score` (impute điểm
  thấp nhất quan sát được ở size đó). Kiểm kết luận có nhạy với cách xử lý failure không.
- **Interaction / DiD** — `did_mean` = delta tại size lớn nhất trừ delta tại size nhỏ nhất, kèm bootstrap CI + Wilcoxon
  p.
- **Trend slope** — độ dốc OLS của delta theo 4 bước size, kèm CI. ⚠️ Với baseline failure nặng ở size nhỏ,
  trend/DiD complete-case trộn các subset scenario khác nhau qua size (survivorship) — **chỉ diễn giải mô tả**.

## A.3 RQ2 — Alignment evaluation protocol

File: [`metrics/alignment.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/alignment.py).
Đặc tả chốt + rationale: [`docs/rq2_protocol.md`](rq2_protocol.md).

Chấm constructive alignment bằng một hàm cố định của văn bản — **zero lời gọi LLM trong đo lường, không sampling**.
Đọc **chỉ text** (`objective_id`/`aligned_objective`/`level` tự khai **không** dùng để chấm, chỉ làm validation
evidence). Mọi giá trị trong [0, 1]. **Không có scalar tổng hợp và không có ngưỡng cắt.**

> **Panel, không thứ bậc.** 7 tín hiệu là một panel phẳng, mỗi tín hiệu một câu hỏi riêng, tất cả đều báo cho mọi so
> sánh — thắng hay thua. Không có "endpoint chính": gắn nhãn chính/phụ chỉ là composite ngầm.
>
> **Quy tắc đặt tên**: tín hiệu mang tên phép toán nó thực hiện. Tên metric bị đọc trên nhãn trục hình và bullet
> slide, nơi một cái tên hứa nhiều hơn phép toán sẽ làm đúng công việc mà chỉ tầng bằng chứng có quyền làm. Vì vậy 4
> tín hiệu họ embedding mang hậu tố `*_similarity`; từ "alignment" chỉ ở tên protocol và các vế `aligned(o)`, không
> nằm trên metric nào; và không tín hiệu nào gọi là *precision* — chữ đó gợi khung retrieval vốn phải có ngưỡng, mà
> protocol thì không có ngưỡng nào.

> **Cosine ở đây là *rectified*** — `max(0, cos)`, clip trần 1,0. Đây là lựa chọn **thang đo**, không phải ngưỡng khớp:
> cặp anti-correlated không "align" hơn cặp trực giao nên phần âm gộp về sàn 0. Không hằng số nào quyết định hai text
> "có khớp hay không". Trong paper/slide gọi đúng là *rectified cosine trên [0, 1]*.

**Panel = hai họ instrument độc lập cơ chế**, mỗi họ một trục sensitivity riêng. Đây là câu trả lời *cấu trúc* cho
chỉ trích "panel chỉ là 7 biến thể của cosine": không họ nào một mình gánh construct.

*Họ A — textual correspondence (encoder), 3 tín hiệu = đúng 3 cạnh tam giác Biggs:*

- `objective_assessment_similarity` — trung bình trên objectives của **max cosine tới bất kỳ assessment item nào**
  (liên tục, không ngưỡng): vế `measures`, quan hệ trung tâm của constructive alignment (Biggs). Lý do bỏ ngưỡng:
  ngưỡng 0,25 quá lỏng (best-match cosine p10 ≈ 0,4–0,69) → coverage bão hoà ~1,00 cho mọi hệ, không phân biệt và mở
  câu hỏi "why this threshold". Đo liên tục phân biệt rất mạnh: harness ~0,83–0,86 vs baseline 0,19–0,64.
- `objective_activity_similarity` — cùng công thức với activities (vế `supports`, C3).
- `activity_assessment_similarity` — cạnh thứ ba (mean-max cosine activity→assessment, C4 `prepares_for`). Không phụ
  thuộc objectives, nên vẫn có giá trị khi objectives của output không parse được.

**Đã xoá khỏi phép đo 2026-08-30**: `objective_evaluation_similarity`, `assessment_objective_similarity`, cặp Porter
`objectives↔evaluation` và toàn bộ đường dẫn text pha evaluation (`extract_evaluation_texts`, `counts["evaluation"]`).
Evaluation-phase text không ứng với quan hệ core nào sau khi `evaluation` bị bỏ khỏi `NodeType`. Hệ quả phải khai:
`porter_mean` **đổi định nghĩa** (nay là trung bình trên 3 cạnh tam giác, không phải 3 cặp objective-vs-X), nên số
`porter_*` trước 2026-08-30 không so sánh được.

*Họ B — cognitive demand (Bloom classifier), 3 tín hiệu, không dùng similarity:*

- `objective_cognitive_congruence` — % objective mà best assessment item (**argmax, không ngưỡng**) có Bloom level ≥
  level của objective, trên objectives classifiable hai phía (**objective-centric**).
- `porter_mean` + `porter.{assessment,activities,evaluation}` — Porter Alignment Index (Porter 2002 / Fulmer 2011): ma
  trận phân phối topic × Bloom-level chuẩn hoá mỗi phía, `P = 1 − 0,5·Σ|X_ij − Y_ij|`.
- `webb_bloom_consistency` — Webb Bloom-consistency (item-centric, khác congruence ở trên).

Không có objectives → 3 tín hiệu similarity họ A = 0,0; set trống → tín hiệu tương ứng 0,0 + note.

**Multiplicity — báo hai tầng.** `p_holm` = Holm trong từng tín hiệu (family = 6 so sánh/size), giữ nguyên power;
`p_holm_panel` = Holm trên **toàn panel × baseline** của size đó, cùng dữ liệu nên miễn phí, và nó chặn trước phản
biện "các anh chạy 168 test". Phòng thủ chống selective reporting nằm ở chỗ **mọi tín hiệu đều báo cho mọi so sánh**,
không nằm ở việc gộp family.

Hai layer validity trong `details` (**không phải tín hiệu panel** — chúng đo instrument, không đo agent):
`validation.declared_link_agreement` (% link objective↔item mà similarity matching tái tạo đúng link agent tự khai) và
`sanity.bloom_vs_declared_agreement` + `sanity.classifier` (calibration Bloom arm đang chấm vs declared level; key
mang chữ "bloom" chứ không phải "lexicon" vì trục Bloom có hai arm).

**Encoder.** Primary `nvidia/llama-embed-nemotron-8b` — family independence: Llama/NVIDIA ≠ agent Qwen ≠ judge
OpenAI/Google. Bộ sweep là **ba neural khác lineage** + một lexical floor:

| Preset     | Model                                                | Backbone    | Backend | Suffix    |
|------------|------------------------------------------------------|-------------|---------|-----------|
| `nemotron` | `nvidia/llama-embed-nemotron-8b`                     | Llama-3.1   | **pod** | (không)   |
| `bgem3`    | `BAAI/bge-m3` (568M)                                 | XLM-RoBERTa | local   | `bgem3`   |
| `granite`  | `ibm-granite/granite-embedding-311m-multilingual-r2` | ModernBERT  | local   | `granite` |
| `tfidf`    | char n-gram thuần Python                             | —           | local   | `tfidf`   |

**Chỉ arm 8B cần pod.** Ba arm còn lại chạy in-process qua sentence-transformers trên GPU máy local. Đo thật trên
M4 Pro (MPS), với **335 340 text duy nhất** của ladder: `bgem3` 126 text/s ⇒ **~44 phút**, `granite` 226 text/s ⇒
**~25 phút**, `tfidf` vài giây. Một lượt duy nhất — cache dùng chung cho mọi lần chấm lại. Model tải một lần
(bge-m3 2,6 GB, granite 627 MB).

⚠️ **Một model = một backend, không được trộn.** Cache key là `sha1(model[@revision] + text)`, **không ghi backend**,
nên nếu một model được embed vừa trên pod vừa local thì hai nguồn vector khác nhau về số học sẽ nằm chung một key mà
không ai thấy. Backend được chốt cứng trong `ENCODER_PRESETS`; đừng đổi nó giữa chừng một đợt chấm.

Chọn E2/E3 theo **backbone chứ không theo tổ chức**: `bge-m3`/`multilingual-e5`/`arctic-v2`/`jina-v3`/`nomic-v2` đều là
XLM-RoBERTa (lineage collision — chỉ lấy MỘT), và nhiều model top-2026 là Qwen/Gemma trá hình (`harrier-oss-v1-0.6b` =
`model_type: qwen3`, `jina-v4` = Qwen2.5-VL, `voyage-4-nano` = Qwen3) — **mở `config.json` kiểm backbone, đừng tin tên
**.

`tfidf` là **một trục sensitivity ngang hàng** chứ không phải phụ lục: nó trả lời câu hỏi không encoder neural nào trả
lời thay được — *thứ hạng có sống sót khi bỏ hẳn ngữ nghĩa không?* — và là encoder duy nhất **tất định bit-wise**. Nó
trực giao với ba encoder neural (vốn cùng học contrastive trên web corpus nên sai số có thể tương quan).

**Pin weights**: tên model KHÔNG pin weights. Revision set **theo từng arm** (`<SLOT>_EMBED_REVISION` trong `.env` —
placeholder do `05` sinh và giữ nguyên qua mỗi lần re-sync — hoặc `--embed-revision-for SLOT=<hash>`); không có dạng
toàn cục vì một chuỗi revision không thể pin weights của nhiều model. Revision đi vào cả `encoder_revision` của score
file lẫn **key của embedding cache**, nên đổi revision là re-embed thật. Thiếu revision thì claim tái lập chỉ đứng
được nhờ cache — `07` in cảnh báo `revision UNPINNED`.

**Bloom (arm sweep — arm chính xem mục kế)**: rule-based action-verb lexicon (`LexiconBloomClassifier`), **chỉ
tiếng Anh** — corpus được chấm đo được là
100% tiếng Anh trên mọi agent và mọi size. Text ngôn ngữ khác trả `None` (không phân loại được → bị loại khỏi các đại
lượng phụ thuộc Bloom, không đoán bừa). Coverage thực đo trên objectives: **97,1%**.

Lexicon có **hai tầng, phân biệt rõ xuất xứ**:

- **Tier 1 — `_AK_PROCESSES` (51 verb)**: 19 cognitive process của Cognitive Process Dimension + các *alternative name*
  mà Anderson & Krathwohl (2001, Table 5.1) liệt kê. **Cấp của verb ở tầng này không do mình chọn** — theo đúng A&K.
  Hệ quả khác với các bảng verb lưu truyền kiểu handout: `compare`/`contrast`/`match`/`categorize` là **Understand (2)**
  chứ không phải Analyze; `integrate`/`outline`/`structure` là **Analyze (4)** (alternative name của *organizing*) chứ
  không phải Create. Một số alternative name của A&K bị **cố ý loại** vì đa nghĩa trong văn xuôi thường
  (`focusing`, `selecting`, `mapping`, `representing`, `parsing`…) — mất recall thì được, mất xuất xứ thì không.
- **Tier 2 — `_CONVENTIONAL_VERBS` (54 verb)**: verb thông dụng trong thực hành viết objective và trong dòng literature
  rule-based Bloom (Omar et al. 2012 và các công trình sau). Xuất xứ yếu hơn tier 1 và được ghi rõ là vậy.

Một verb chỉ được nằm ở **đúng một cấp** — có test ép điều này, vì nếu không thì rule "highest wins" sẽ bị quyết định
bởi trùng lặp trong lexicon thay vì bởi văn bản.

**Guard từ loại**: match bị từ chối nếu ngay trước nó là determiner/possessive/`of` (`the design`, `a plan`,
`the proposed solution`) — đó là danh từ hoặc tính từ phân từ, không phải hành vi được thực hiện. Đo trước khi có guard:
≥4,3% số lần gán cấp là do khớp kiểu này. Guard chỉ xét **ngữ cảnh liền kề**; cho phép có khoảng cách sẽ chặn nhầm cả
động từ thật (`the learners create …`). Giới hạn đã biết: danh từ ghép không có determiner (`their lesson design`) vẫn
lọt — phân biệt được ca này cần POS tagger, tức thêm một thành phần thống kê vào một pipeline đang bán điểm tất định.

**Quy tắc gán cấp: động từ DẪN ĐẦU**, không phải động từ cao nhất. Theo Webb — level đi theo *central performance*,
còn động từ đứng sau thường chỉ nêu mục đích hoặc phương tiện (`apply X to design Y` là Apply, không phải Create).
Chọn bằng bằng chứng chứ không phải khẩu vị, trên hai corpus có nhãn độc lập:

| Corpus | highest wins | **leading verb** |
|---|---|---|
| EDM2022 learning objectives (n=18 773) | κ 0,591 | **κ 0,657** |
| Public exam-question set (n=8 767) | κ 0,386 | **κ 0,434** |

### Bằng chứng hiệu lực

Nguồn: **submodule `EDM2022CLO/`** (fork của [SteveLEEEEE/EDM2022CLO](https://github.com/SteveLEEEEE/EDM2022CLO), dataset
+ notebook đã release của Li et al. 2022, EDM) — 21 380 learning objective từ 5 558 khoá của một đại học Úc,
**gán nhãn tay**, multi-label. Đúng genre với thứ protocol chấm (không phải câu hỏi thi). Clone kèm submodule:
`git submodule update --init EDM2022CLO`.

| | |
|---|---|
| Coverage | 84,1% |
| Accuracy | 72,7% |
| Adjacent accuracy (\|Δ\|≤1) | 86,0% |
| **Cohen's κ** | **0,657** — "substantial" (Landis & Koch) |
| Majority floor / oracle ceiling | 27,1% / 77,6% → **đạt 90% khoảng khả dụng** |
| Multi-label hit rate | 79,9% |

**Mốc so sánh quan trọng:** chính paper EDM2022 báo κ = **0,63** giữa **hai human coder được đào tạo** trên bộ dữ liệu
này (lên 0,80 sau khi thảo luận thống nhất). Lexicon đạt 0,657 — **ngang hoặc hơn mức đồng thuận giữa hai chuyên gia**.
Trần oracle 77,6% là giới hạn trên của *mọi* classifier nhìn động từ (cùng một động từ mang nhiều nhãn khác nhau), nên
phần lỗi còn lại chủ yếu là mơ hồ của nhãn chứ không phải lỗi instrument.

Chạy lại: `00_validate_bloom.py <csv> --text-col Learning_outcome --label-cols Remember,Understand,Apply,Analyze,Evaluate,Create`
— **chạy một lần, trước khi tin bất kỳ số Bloom nào**; độc lập hoàn toàn với run data. Báo cáo đầy đủ (kèm phân tầng
theo độ thuần nhãn + confusion matrix): `results/generated/bloom_validation.md`.

### Trục sensitivity Bloom — `bertbloom`

3/7 tín hiệu (`objective_cognitive_congruence`, `porter_*`, `webb_bloom_consistency`) chạy trên Bloom, nên họ tín
hiệu này có **trục sensitivity riêng**, ngang hàng với trục encoder:

| Arm | Instrument | Xuất xứ | Suffix |
|---|---|---|---|
| `bertbloom` (**chính**) | `TransformerBloomClassifier` | BERT 6 lớp fine-tune trên 21 380 nhãn người của EDM2022CLO (Li et al. 2022) | (không) |
| `lexicon` (sweep) | `LexiconBloomClassifier` | A&K 2001 Table 5.1 — tất định, giải thích được từng quyết định | `lexicon` |

⚠️ Arm chính **cần checkpoint trên đĩa**, nên chấm alignment không còn zero-setup: train trước
(`evaluator/scripts/train_bloom_6way_classifier.py`); thiếu checkpoint thì mọi arm bị SKIP chứ không fallback ngầm.

Câu hỏi của trục này **không phải** "classifier nào đúng hơn" mà là *thứ hạng agent có phụ thuộc lựa chọn classifier
không*. Hai instrument dẫn xuất hoàn toàn độc lập — một từ taxonomy, một từ nhãn người — mà cho cùng thứ hạng thì đó
là bằng chứng mạnh hơn bất kỳ instrument đơn lẻ nào ở κ bất kỳ; và nó biến điểm yếu của lexicon thành **kết quả
robustness** thay vì một câu bào chữa.

Chi tiết bắt buộc khai:

- **Dùng corpus của Li et al., không dùng thiết kế classifier của họ.** Không notebook nào của họ cho ra classifier
  6 lớp: `EDM2022 CLO.ipynb` train **6 model nhị phân độc lập** (`createBERT`, `num_labels=2`), mỗi level một
  checkpoint; `Multi-Label.ipynb` train **một model multi-label** (sigmoid, ngưỡng 0,5 mỗi level) có thể ra nhiều
  level hoặc không level nào. Panel cần **đúng một mức Bloom mỗi text** (congruence so level, Porter cần một ô
  topic×level mỗi text, Webb cần một level mỗi item), nên cả hai đường đều phải thêm một tầng quyết định (argmax qua
  6 head train riêng — tỉ lệ dương của chúng chạy từ ~4% tới ~27% — hoặc tie-break trên sigmoid). Một head softmax
  6 lớp cho thẳng quyết định đó, train bằng `evaluator/scripts/train_bloom_6way_classifier.py`.
- **Cấu hình = `createBERT` của notebook, đổi đúng một thứ.** `bert-base-uncased`, `max_length` 55, batch 64,
  3 epoch, warmup 5, weight decay 0,05, learning rate mặc định transformers, eval/save theo step (10), best model
  theo macro F1, early stopping patience 10, split hai tầng 20% test → 20% val với `random_state=666`. Thứ duy nhất
  đổi là **head: `num_labels=6`** thay cho 6 head `num_labels=2`. Đổi bất kỳ tham số nào khác thì câu "cùng cấu hình
  với Li et al." hết đúng.
- Train trên **subset single-label** (18 773/21 380 dòng; 2 607 dòng multi-label bị loại vì head đơn nhãn không biểu
  diễn được). Trainer ghi `eval_split.csv` + `held_out_metrics.json` cạnh checkpoint; số của arm BERT **phải** báo
  trên split đó, báo trên tập đã train là in-sample và vô nghĩa khi so với lexicon.
- **Coverage lệch theo thiết kế**: lexicon abstain (84,1% trên EDM2022CLO), BERT argmax luôn (100%), nên mẫu số của
  congruence/Porter/Webb khác nhau giữa hai arm. Khai thẳng, không cân bằng lại — thứ hạng sống sót qua hai instrument
  có coverage lệch hẳn nhau thì kết luận càng chắc.
- Arm BERT **không bao giờ fallback ngầm về lexicon**: thiếu checkpoint thì arm bị SKIP kèm lý do — với BERT là arm
  chính, điều đó nghĩa là cả lần chấm dừng lại, đúng như mong muốn (một artifact gắn nhãn `bertbloom` mà thực chất do
  lexicon chấm là kiểu hỏng tệ nhất).

**Số đã đo (train 2026-07-29, cả hai arm trên cùng 3 755 dòng held-out — artifact:
`results/generated/bloom_arms_validation.md`):**

| Arm | Coverage | Accuracy | κ vs gold |
|---|---|---|---|
| `bertbloom` (**chính**) | 100% | 94,1% | **0,926** |
| lexicon (A&K, sweep) | 83,4% | 72,3% | 0,650 |

Đồng thuận giữa hai arm (3 133 dòng cả hai phân loại được): **73,5% raw, κ 0,665**. Con số này mới là thứ đáng đọc —
hai instrument **không phải bản sao của nhau**, nên nếu thứ hạng agent vẫn giữ khi đổi arm thì đó là robustness thật.

κ 0,650 của lexicon trên held-out khớp với 0,657 trên toàn corpus → split không lệch.

Hai câu reviewer chắc chắn hỏi, trả lời sẵn:

- *"Sao máy hơn người (κ 0,63 giữa hai coder)?"* — hai đại lượng khác nhau. κ 0,63 là hai coder **độc lập** đồng ý với
  nhau trước khi thống nhất; BERT được học chính bộ nhãn đã thống nhất, tức nó học **quy ước mã hoá** của nhóm đó chứ
  không phải "hiểu Bloom hơn con người".
- *"Sao vượt trần oracle 77,6%?"* — trần đó áp cho classifier **chỉ nhìn động từ dẫn đầu**; BERT đọc cả câu nên phân
  biệt được các ca cùng động từ khác cấp. Vượt trần là điều đúng phải xảy ra, không phải dấu hiệu rò rỉ.
- Đã kiểm rò rỉ: corpus trùng lặp 0,6% dòng, và chỉ **1,1%** text held-out từng xuất hiện trong train pool → không
  giải thích được κ 0,926.

### Pooling RQ2

`extract_alignment_metrics` + `pool_alignment` trong `07`: đọc `alignment_scores.json` từng scenario dir, gộp theo
agent × size thành `mean`/`sd_across_scenarios` cho mọi metric. Tầng inferential chạy trên **TOÀN BỘ panel**, dưới
`stats.per_model[].panel[<signal>]` — không tín hiệu nào được hoisted lên cấp trên, vì thứ bậc *cấu trúc* cũng chính
là composite ngầm mà panel loại bỏ. Mỗi tín hiệu có đủ:

- `comparisons` — paired Wilcoxon + bootstrap CI + rank-biserial (cùng machinery RQ1), kèm `p_holm` (Holm/6 trong
  tín hiệu đó) và `p_holm_panel` (Holm trên toàn panel × baseline của size đó).
- `align_descriptive` — mean + bootstrap CI95 per agent.
- `conditional_align` — chỉ scenario mà **mọi run được chấm** đều cho ≥1 objective (đọc `counts.objectives`, không đọc
  sự tồn tại của `porter_mean`). Tách quality khỏi parse failure.
- `align_failures` + `comparisons_failure_zero` — **tầng failure policy, song song RQ1**. Hai layer trên là
  **complete-case trên output CÓ SẴN**, không phải unconditional: agent crash thì không có `*_output.json`, scenario đó
  rơi khỏi tập ghép cặp và cú crash **không tốn gì** cho agent. `06` ghi roster `missing_outputs` (có log, không output
  → attempted & failed), pooling đếm vào `align_failures` rồi chạy lại paired test với các cell đó impute 0,0. Không có
  policy `min_score` như RQ1 vì các endpoint đã sàn ở 0,0. **Paper phải báo cả hai layer**, và **không được gọi layer
  chính là "unconditional"**. Roster là bắt buộc: `06` luôn ghi, `07` luôn đọc.
- `align_failures` nằm ở cấp `per_model[]` (độc lập tín hiệu); `interaction_align` — DiD (largest − smallest size) per
  baseline, bootstrap CI + Wilcoxon p — chạy trên `lead_metric` (mặc định `objective_assessment_similarity`, đổi bằng
  `--sensitivity-metric`). "Lead" ở đây chỉ chọn *chuỗi nào được vẽ* cho các tóm tắt một chiều, không phải một endpoint
  chính.

Pooling **hard-fail** nếu các run dir gộp lại mang nhiều bộ `(encoder, encoder_revision, bloom_classifier)` khác nhau —
trung bình trộn hai instrument không đo cái gì cả.

**Coverage**: `07` so số file score tìm được với kỳ vọng (`n_scenarios_union × n_runs`) và **in WARNING nếu thiếu**
(`n_scenario_files` / `n_scenario_files_expected` / `coverage_complete` cũng nằm trong JSON). Cần cảnh báo này vì con
số `n=` per-agent trong report **không phân biệt được** "agent fail ở scenario đó" (dữ liệu thật, failure policy xử lý)
với "scenario đó chưa từng được chấm" (lỗi thao tác) — một sweep chấm dở sẽ pool y như thể đã đủ. `04_audit_postrun.py`
bắt cùng lỗi này sớm hơn, ở mức từng run dir và từng encoder arm; `07` là lớp phòng thủ thứ hai ngay tại chỗ số được tạo
ra.

**Sensitivity sweep** (cả hai trục) → `alignment_sensitivity.encoders[]`, mỗi entry mang `axis: encoder|bloom`:
mỗi arm chạy **cùng** `pool_alignment` trên
`alignment_scores.<suffix>.json` nên có đủ `models` + `stats`, cộng `agreement_with_primary.per_model[]`:
Spearman ρ + p permutation chính xác (n≤8) + Kendall τ-b trên vector điểm trung bình theo agent (**trích τ-b trong
prose** vì n=7 thì Spearman nhiễu); ρ cấp scenario cho agent đề xuất (n≈90, trả lời câu hỏi khác: hai encoder có đồng ý
*scenario nào* align tốt không); và ba đối chứng phi-rank — `top1_agent_*`, `proposed_rank_*`,
`sign_agreement_vs_baselines` — vì ρ cao vẫn có thể đi kèm kết luận lật.

`--auto-encoders` / `--auto-bloom` lấy roster **từ registry trước, đĩa sau**: preset non-primary chưa chấm được ghi là
`skipped` chứ không vắng mặt — vắng mặt chính là kiểu hỏng làm một sweep dở dang trông như đã đủ.

Ablation pooling reuse `pool_alignment` → bảng `objective_assessment_similarity` arm−A0 trong `stats_ablation.md`.

## A.4 Operational metadata

Ghi trong `metadata` của mỗi `{agent}_trajectory.json`, pool bởi `pool_tokens()`. **Không** vào Total hay endpoint
alignment:

- **`token_usage`** — tổng token input/output mỗi scenario (bằng chứng mọi agent dùng `max_tokens` đồng nhất —
  fairness).
- **`execution_time_seconds`** — **chỉ lưu thô, KHÔNG dùng để báo cáo/so sánh**: nó phản ánh tải serving/latency API
  chứ không phải bản chất method.
- **`objective_ceiling`** — `{limit, written, respected}` (từ 2026-09-10). `limit` là trần số mục tiêu suy ra từ
  design brief, `written` là số mục tiêu run thực sự viết ra. Trần chỉ được thông báo trong rules của stage
  `outcomes`, không có gì cưỡng chế nó, nên **tỷ lệ `respected` chính là số cần báo cáo**: không có nó thì một
  results dir không trả lời được câu hỏi chỉ dẫn kia có tác dụng gì không. Chỉ có ở bốn arm alignmentgraph, không có
  ở sáu baseline. Muốn đưa tỷ lệ này vào paper thì phải thêm vào `15_gen_facts_sheet.py` và gate bằng
  `99_audit_artifacts.py`, theo đúng quy tắc số trong paper phải sinh tự động.
