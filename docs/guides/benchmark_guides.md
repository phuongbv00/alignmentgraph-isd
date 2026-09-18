# Benchmark guide — single source of truth (RQ1/RQ2)

> Toàn bộ quy trình benchmark Qwen3.5 ladder: split data → serving → tune → chạy bench → audit →
> hậu xử lý ra số cho paper, kèm định nghĩa metric (Phụ lục A). Mục tiêu: đọc mỗi file này là
> tái lập được thực nghiệm.
>
> Mọi lệnh chạy từ `isd-agent-benchmark/` trừ khi ghi khác. Bối cảnh RQ: bản thảo `docs/paper/acm/` (§Experimental Design) + [`docs/guides/alignment_protocol.md`](alignment_protocol.md).

**Ba quy tắc không được vi phạm:**

1. Mọi quyết định tuning chỉ dựa trên `train_10`. `test_90` chỉ chạy sau khi freeze code. Sửa code sau đó ⇒ chạy lại
   ladder.
2. Số trong paper **chỉ** đến từ `results/generated/` (mục 9). Không gõ tay.
3. Cấu hình LLM judge và 2 flag bảo hộ (mục 3.3) phải **đồng nhất** giữa mọi run và mọi agent — đó là điều kiện công bằng
   của so sánh.

---

## Pipeline

```
[1] setup ─► [2] split data ─► [3] serving ─► [4] TUNE (train_10) ─► CODE FREEZE ─┐
                                                 loop đến khi chốt                │
                                                                                  ▼
[8] pool ◄── [7] score alignment ◄── [6] audit ◄── [5] TN1 test_90  4 size × 1 run × 7 agent
     │            (RQ2, local)                         TN2 test_30  2 size × 1 run × 4 arm
     ▼
[9] gen tables + figures ─► [10] teardown
```

**Hai thí nghiệm chính thức, tách rời (chốt 2026-09-10 theo định hướng GVHD sau Sprint 1):**

| | TN1 — ladder | TN2 — ablation 2×2 |
|---|---|---|
| Trả lời | Objective 2 + 3 | Objective 4 |
| Agent | 7 hệ (6 baseline + hệ đề xuất) | 4 arm (A0 + 3) |
| Size | 0.8B / 2B / 4B / 9B | 0.8B / 4B |
| Dataset | `test_90` | `test_30` |
| Run/ô | 1 (deterministic) | 1 (deterministic) |
| Tag | `r1` | `a1` |
| Launcher | `isd-exp comparison run` | `isd-exp ablation run` |

**A0 chạy LẠI trong TN2**, không mượn từ TN1: LLM judge session, scenario set và dải size đều khác,
nên delta arm−A0 chỉ sạch khi hai vế đến từ cùng một run. Trước 2026-09-10 các arm chạy chung
trong ladder (10 agent một run) — mọi mô tả kiểu đó trong tài liệu cũ đã hết hiệu lực.

**1 run mỗi ô, không phải 3.** Bất định ước lượng theo SCENARIO (paired Wilcoxon + bootstrap trên
90 cặp), không theo run. Lặp chỉ dùng cho *targeted repeat* — vài ô quyết định, báo riêng với n
riêng: `RUN_TAGS="r2,r3" LADDER_SLOTS="qwen08b,qwen4b" AGENTS="..." ./isd-exp comparison run`.

### Bản đồ lệnh

Toàn bộ thí nghiệm chạy qua **một** entry point: `experiments/isd-exp`. Nó là wrapper tự
định vị — tìm `.venv` nằm cạnh nó rồi exec, nên **không cần activate và không cần thêm vào
PATH**; chạy `./isd-exp ...` từ trong `experiments/` là được. (Nếu bạn thích cài thật:
`pip install -e experiments/` sẽ đặt lệnh `isd-exp` lên PATH của môi trường đó.)
Nhóm subcommand đọc dọc theo sáu giai đoạn của lộ trình, nên thứ tự chạy chính là thứ tự
`isd-exp --help` liệt kê. Benchmark (`isd-agent-benchmark/`) chỉ còn là **công cụ đo**: nó
không biết gì về thí nghiệm, và ba script còn lại trong `scripts/` chỉ phục vụ việc chạy
benchmark độc lập.

| Lệnh | Vai trò | Mục |
|---|---|---|
| `isd-exp doctor [--fix]` | kiểm checkout, 10 gói editable của benchmark, `.env`, checkpoint Bloom | 1 |
| `isd-exp data split <tên>` | cắt `train_10` / `test_90` / `test_30` (kèm kiểm disjoint) | 2 |
| `isd-exp bloom train` / `validate` | huấn luyện head Bloom 6 lớp / chấm arm vs nhãn chuyên gia | A.3 |
| `isd-exp tune run` | hiệu chỉnh cost và budget trên `train_10` | 4 |
| `isd-exp freeze write` / `verify` | ghi / đối chiếu manifest code freeze | 5 GĐ3 |
| `isd-exp audit preflight` | trước launch: endpoint, auth, model, flag, disk | 6.1 |
| `isd-exp comparison run [--dry-run]` | **so sánh**: hệ đề xuất vs baseline theo thang model | 5 |
| `isd-exp ablation run [--dry-run]` | **ablation**: 2×2 phân rã × substrate | 5.4 |
| `isd-exp audit inflight` | khi đang chạy: red flag trong log + độ tươi của progress | 6.2 |
| `isd-exp audit postrun` | sau run: completeness / integrity / metrics | 6.3 |
| `isd-exp audit repair` | chấm lại LLM judge cho ô lỗi transient, **không** sinh lại output | 6.4 |
| `isd-exp score <run-dir>` | chấm panel alignment (không LLM), `--all-arms` cho cả sao sensitivity | 7 |
| `isd-exp trajectory rescore` | lớp diagnostic cap cao, chấm lại trajectory đã lưu *(chưa hiện thực)* | 5 GĐ1 |
| `isd-exp comparison pool` | pool run so sánh → `pooled_comparison.json` + thống kê | 8 |
| `isd-exp ablation pool` | pool 4 arm → `pooled_ablation.json` + factorial + drift | 5.4 |
| `isd-exp report tables` | bảng LLM judge + alignment, macro, `stats_summary.md` | 9 |
| `isd-exp report figures` | hình LLM judge + alignment | 9 |
| `isd-exp report cost` | hồ sơ cost/deployability đọc thẳng từ trajectory | 9 |
| `isd-exp report sensitivity` | bảng độ nhạy công cụ đo | 9 |
| `isd-exp report ablation-tables` / `ablation-figures` | artifact của ablation | 5.4 |
| `isd-exp report facts` | `facts.md`: gộp mọi số tổng hợp vào MỘT file | 9.2 |
| `isd-exp report sync` | copy artifact sang `docs/generated/` | 9 |
| `isd-exp report all` | chạy đủ theo đúng thứ tự phụ thuộc rồi sync | 9 |
| `isd-exp audit artifacts` | **cổng cuối**: artifact đủ, thật, mới, đã wire vào paper | 9.1 |
| `isd-exp expert sample` / `aggregate` | gói expert validation *(chưa hiện thực)* | 5 GĐ6 |

Còn lại bên benchmark, chỉ dùng khi chạy benchmark một mình:
`./scripts/1_setup.sh` (dựng venv riêng cho submodule — repo này **không** giữ sẵn nó),
`./scripts/2_split_data.sh` (split gốc 95/5), `./scripts/3_run_benchmark_test.sh`
(smoke 1 scenario).

**Cấu hình thí nghiệm nằm ở `experiments/experiment.toml`** — thang model, nơi host, dataset,
roster agent, các arm ablation, preset encoder/Bloom. Đổi thang model hay đổi nhà cung cấp
serving là sửa file đó, không sửa code: `tests/test_no_vendor_names.py` chặn mọi tên vendor
lọt trở lại vào `src/`.

---

## 1. Setup

**Cả repo chỉ có hai môi trường.** `experiments/.venv` chạy mọi thứ thuộc thí nghiệm — cả
`isd-exp` lẫn `run_benchmark.py`, vì `run_benchmark.py` được gọi như subprocess dưới đúng
interpreter đó. Nên benchmark, bảy agent, `alignmentgraph-isd` và `isd-evaluator` là mười
bản cài editable nằm trong nó; không danh sách dependency nào đặt tên được cho một đường
dẫn trong checkout này, nên `isd-exp doctor` báo cái nào thiếu và `--fix` cài.
`alignmentgraph-isd/.venv` là của web app demo, tách biệt hoàn toàn.

```bash
cd experiments
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
./isd-exp doctor --fix            # cài mười gói editable + symlink .env

cd ../isd-agent-benchmark
../experiments/.venv/bin/python run_benchmark.py --check   # mọi agent module import sạch
./scripts/3_run_benchmark_test.sh # smoke 1 scenario
```

`./scripts/1_setup.sh` vẫn còn và vẫn dựng được venv riêng cho submodule — nó là cái giữ
cho benchmark chạy độc lập được. Từ monorepo thì không cần: dùng `experiments/.venv`.

### `.env`

Agent model và LLM judge model cấu hình **tách biệt** (tránh self-preference bias). LLM judge giữ nguyên xuyên suốt.

```bash
# --- secrets ---
OPENROUTER_API_KEY=sk-or-...     # LLM judge
LLM_API_KEY=...                  # Bearer token của server vLLM (khớp RunPod secret)

# --- LLM judge (cố định mọi giai đoạn) ---
JUDGE_MODEL_PROVIDER=openrouter
JUDGE_MODEL_NAMES=openai/gpt-4o-mini,google/gemini-2.5-flash-lite
JUDGE_MODEL_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL_API_KEY_ENV=OPENROUTER_API_KEY

# --- agent model ---
# KHÔNG nằm ở đây. Endpoint của mỗi rung khai bằng `base_urls` trong experiment.toml
# (mục 3.4); launcher tự export QWEN{08B,2B,4B,9B}_AGENT_MODEL_BASE_URLS từ đó.

# --- tuỳ chọn ladder ---
# RATE_LIMIT=turbo                # conservative|moderate|aggressive|turbo
# QWEN08B_RATE_LIMIT=conservative # override per-slot
```

Một slot có thể có **nhiều pod**: liệt kê nhiều URL trong `base_urls` của rung đó, agent round-robin qua chúng.
Mọi URL trong một rung phải serve cùng model — `audit preflight` kiểm từng URL một và fail nếu lệch.

## 2. Split data

Đã chạy và commit sẵn (seed 42) — chỉ chạy lại nếu làm từ đầu.

```bash
./scripts/2_split_data.sh    # → scenarios/train/ (~24.6k), scenarios/test/ (~1.2k), stratified
./isd-exp data split tune-10        # train -> train_10, 10 scenario, để TUNE
./isd-exp data split test-90        # test  -> test_90,  90 scenario, để BENCH
```

Lưới stratify: 10 domain × 3 difficulty = **30 ô**. Metadata (`scenarios/*_metadata.json`) ghi seed/nguồn/số lượng —
giữ cho phần reproducibility. `train_10` lấy từ train split nên tune thoải mái không đụng test.

`per_cell` một mình không cho ra tập nhỏ hơn 30. `train_10` vì vậy dùng thêm `--max-total`: đổ đầy 1/ô rồi hạ mẫu
round-robin theo thứ tự ô đã shuffle bằng seed, nên 10 scenario nằm trên 10 ô khác nhau thay vì dồn vào ba domain đầu
danh sách. Hệ quả phải khai thẳng: **`train_10` phủ 10/30 ô nên KHÔNG phải mẫu stratified của corpus** — nó là tập hiệu
chỉnh chi phí, kết quả không bao giờ vào paper. Ở n=10, `EXACT_WILCOXON_N_MAX = 25` cộng family Holm 36 của panel làm p
điều chỉnh nhỏ nhất đạt được là 0.070, tức không kết luận suy diễn nào tồn tại được. Sidecar `train_10_metadata.json`
ghi rõ điều đó ở `source_note`, `max_total` và `cells_covered`.

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

### 3.3 Hai flag bảo hộ — bắt buộc, đảm bảo tính công bằng của so sánh

```bash
AGENT_MODEL_MAX_OUTPUT_TOKENS=8192
AGENT_MODEL_STREAMING=1
```

Cả hai khai trong `experiment.toml` (`[serving].max_output_tokens` / `.streaming`), launcher truyền xuống benchmark
dưới dạng command prefix. Pre-flight (mục 6.1) **fail** nếu `.env` cũng đặt chúng: hai nguồn cho một giới hạn phải
đồng nhất trên mọi agent và mọi size chính là cách một so sánh mất luận điểm fairness trong im lặng.

Ladder serve **để nguyên thinking**. `--reasoning-parser qwen3` (mục 3.2) tách phần suy nghĩ sang `reasoning_content`
nên `content` vẫn sạch cho đường tool-call/JSON; harness ghi lại kênh đó vào transcript nhưng không bao giờ gửi ngược cho
model, và một lượt chỉ có suy nghĩ bị tính như lượt rỗng.

### 3.4 Tạo pod + khai endpoint

Pod tạo thủ công trên console từ template public dùng chung cho cả 4 size:
**<https://console.runpod.io/deploy?template=x4cakqmn77>**

1. Deploy → chọn GPU theo bảng 3.1.
2. Đổi model: sửa **token positional đầu tiên** của container start command thành HF id của slot. RunPod truyền start
   command như Docker CMD thuần (không shell, không expand `$ENV`) nên **không đổi model bằng env var được**. Không sửa
   flag phía sau.
3. Auth đã đấu sẵn qua RunPod secret `VLLM_API_KEY` — đảm bảo secret trùng giá trị trong `.env`. Không cần `HF_TOKEN`.
4. Chờ `GET https://<pod_id>-8000.proxy.runpod.net/v1/models` trả 401 (không key) / 200 (có key).

Storage: container 20GB + mỗi pod một network volume mount `/workspace` cho HF cache — weights sống sót qua restart.

5. Dán URL vào `[[model]]` tương ứng trong `experiment.toml`:

```toml
[[model]]
slot = "qwen9b"
family = "Qwen3.5"
model = "Qwen/Qwen3.5-9B"
display = "9B"
base_urls = ["https://<pod_id>-8000.proxy.runpod.net/v1"]
key_env = "VLLM_API_KEY"
```

Nhiều pod cùng một model thì liệt kê nhiều URL — agent round-robin qua chúng. `.env` **không** chứa endpoint, chỉ chứa
key. Không có bước sync nào: `experiment.toml` là nơi duy nhất viết endpoint của một rung, và `isd-exp freeze write`
băm đúng file đó nên một run đã xong luôn trả lời được nó chạy trên endpoint nào.

**Ladder không bắt buộc nằm trên một host.** Một rung chỉ là URL + model id + tên biến key, nên ladder lai — vài rung
trên GPU của mình, vài rung trên hosted API — khai y hệt, thêm `key_env` cho rung đó:

```toml
[[model]]
slot = "qwen9b"
family = "Qwen3.5"
model = "qwen/qwen3.5-9b"                  # id mà HOST ĐÓ serve
display = "9B"
base_urls = ["https://openrouter.ai/api/v1"]
key_env = "OPENROUTER_API_KEY"             # thiếu thì dùng [serving].key_env
```

**Khai báo là danh sách phẳng, không phải ladder.** Cái làm nên một ladder là
`slots` của từng thí nghiệm — `"all"` lấy mọi model theo thứ tự khai, hoặc liệt kê
tên slot để cắt ra một ladder cụ thể. Thêm family thứ hai, hay cùng một size trên
hai host, đều khai y hệt ở đây và chỉ khác nhau ở danh sách `slots`.

**`slot` là định danh duy nhất.** Tên macro LaTeX sinh từ nó (`qwen08b` →
`QwenZeroEightB`), nhãn cột lấy từ `display` + `family`. Không có gì suy ra từ số
tham số nữa — một nhãn suy ra từ con số thì hai model cùng size là một.

`api_spec` cũng khai được theo rung nếu host nói contract khác. Chỉ giá trị key nằm trong `.env`, dưới đúng tên rung
đã đặt.

Cần nói thẳng vì khai báo sẽ không tự nói hộ: **rung hosted không cùng một nhạc cụ với rung tự host.** Provider chọn
quantisation, backend và sampling default, và có thể route một id qua nhiều backend khác nhau — nên ladder trộn hai
loại đang so **đồng thời** model scale lẫn serving stack. `freeze write` ghi lại thứ bạn khai, không ghi được thứ
provider đã làm với nó.

`./isd-exp audit preflight` (mục 6.1) kiểm đúng các URL vừa khai — 401 không key, 200 có key, model `/v1/models` trả
về khớp `model` của rung — nên sai địa chỉ bị bắt trước khi tốn một đồng GPU nào. Endpoint là OpenAI-compatible nên
thay một slot bằng hosted API chỉ là đổi URL.

## 4. Tune trên `train_10`

Chỉnh prompt/config của `alignmentgraph-isd` trên tập tách biệt với tập báo cáo.

```bash
DATASET=train_10 AGENT_MODEL_SLOTS=qwen2b AGENTS=baseline,react-isd,alignmentgraph-isd \
RUN_TAGS=tune1 ./isd-exp tune run
```

- `AGENT_MODEL_SLOTS` nhiều slot = chạy **song song** (mỗi slot một tmux session). `RUN_TAGS` nhiều tag = chạy **tuần
  tự** trong mỗi session (`tune1,tune2,tune3` để đo độ ổn định cùng code).
- Kết quả vào `results/train_10_benchmark_<model>_tune<N>_<ts>/`. Tag `tuneN` để không lẫn với run báo cáo `r1/r2/r3`.
- Thu hẹp `--agents` cho rẻ khi debug, nhưng **vòng chốt cuối chạy đủ 7 agent** để chắc thay đổi không phá agent khác.
- Kết thúc tune = **commit đóng băng code** (manifest ladder sẽ ghi commit hash).

### 4.1 Smoke rẻ trước khi tiêu tiền

Không có profile riêng cho việc này. Thu hẹp chính `tune` lại:

```bash
./isd-exp tune run --slots qwen08b --agents alignmentgraph-isd,react-isd
```

Một rung nhỏ nhất trên `train_10` = 20 generation. **Vẫn gọi LLM judge** — `run_benchmark.py` spawn
`isd-evaluator` vô điều kiện khi có từ 2 agent thành công, không có flag nào tắt, nên không tồn tại chế độ chạy
harness mà không tốn judge call. Muốn có thì phải thêm flag ở `run_benchmark.py`.

Đọc gì: `gave_up`, coverage P10/P11, violation ledger, cost, và panel alignment (chạy local). Nếu bất thường thì sửa
trước khi mở rộng ra đủ 4 rung.

## 5. Bench — TN1 (`test_90`) và TN2 (`test_30`)

### 5.1 Quy mô

TN1: 4 size × 1 run × 7 agent × 90 scenario ≈ **2 520 agent generation**. TN2: 2 size × 1 run × 4 arm
× 30 scenario = **240 generation**. Mỗi generation thêm LLM judge evaluation (1 LLM judge full + LLM judge thứ
hai trên subset corroboration). Một run đơn ở rate `turbo` mất vài giờ; TN1 chạy 4 size song song.

7 agent TN1 = 6 default + `alignmentgraph-isd` (không nằm trong defaults — launcher thêm sẵn).
Ba arm ablation KHÔNG chạy ở đây nữa; chúng là TN2 (mục 5.4).

### 5.2 Launch

```bash
source .env
./isd-exp comparison run    # gõ "yes" ở prompt
```

- Endpoint lấy từ `base_urls` trong experiment.toml; rung nào chưa khai ⇒ hard-fail kèm hướng dẫn.
- Mỗi size một tmux session (`ladder-qwen08b`...), chạy **song song**; trong mỗi session các tag chạy
  **tuần tự** — mặc định một tag `r1` → `results/test_90_benchmark_<model>_r1_<ts>/`.
- **`.env` không đổi được cái gì được chạy.** Launcher snapshot `DATASET`/`AGENTS`/`RUN_TAGS`/
  `RATE_LIMIT`/`*_SLOTS` trước khi `source .env`, rồi trả lại — override gõ inline
  (`DATASET=x ./script`) thắng, còn giá trị sót lại trong `.env` từ một phiên tune thì không. Nếu
  `DATASET` khác split chính thức của thí nghiệm, banner nói thẳng đây không phải TN chính thức.
- **Manifest reproducibility** ghi TRƯỚC khi launch vào `results/comparison_<ts>/comparison_manifest.json`: model/provider/URL
  từng slot, dataset, agents, run tag, LLM judge model, **git commit của cả benchmark lẫn monorepo cha**. Giữ file này.
- Log per-slot: `results/ladder_<ts>/<slot>.log`.

Monitor: `tmux attach -t ladder-qwen2b` (detach `Ctrl+B, D`) hoặc `tail -f results/ladder_*/qwen2b.log`.

**Resume từng phần** — mỗi (size, run) là một invocation độc lập:

```bash
LADDER_SLOTS="qwen4b" RUN_TAGS="r2,r3" ./isd-exp comparison run
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
đo theo rate thay vì theo concurrency, mặc định tắt. `HARNESS_FANOUT_WORKERS` (mặc định 1 = fan-out tuần tự, ladder
không đặt) cho các Developer của một family ở arm multi chạy đồng thời, bị cap bởi chính cap trên; commit vẫn theo thứ tự
plan nên graph không đổi, chỉ đổi wall time, và được ghi vào `metadata.run_config.fanout_workers`.
`HARNESS_DEVELOPMENT_MODE` (`sample` | `full`, ladder KHÔNG đặt = `sample`) quyết định Developer viết một mẫu đại diện
của thiết kế hay toàn bộ: plan luôn nêu quy mô thật (quiz 40 câu), `sample` viết 3 item/instrument, 2 TLA/ILO (sàn
3/module), 2 material/module, 1–2 session guide/module; `full` viết hết và chia batch. KHÔNG phải trục ablation — mọi arm
của một thí nghiệm phải chạy cùng một giá trị, ghi ở `metadata.run_config.development_mode`; output tự khai phạm vi ở
`development.development_scope`. Quota `sample` (`dev_plans.SAMPLE_*`) là tham số tạm: hiệu chỉnh trên `train_10` (cùng
scenario ở hai mode, so các mục rubric chấm theo item) TRƯỚC `isd-exp freeze`, sau đó không đổi.

Tổng request in-flight = `max_workers × scenario_max_workers × cap`. Gate là **per-run**, không process-wide: gate chung
sẽ khiến fan-out của arm này xếp hàng trước call của arm kia và thổi phồng `execution_time_seconds` của arm kia.
Cap thực tế được ghi vào `metadata.run_config.llm_max_concurrency` nên mỗi results dir tự nói được nó chạy posture nào.

**Hệ quả cần biết:** arm multi sẽ chậm hơn trước vì fan-out bị chia thành nhiều đợt. Đó là cái giá để hai phía của trục
`agent_mode` chịu cùng một điều kiện phục vụ. Mọi số multi-vs-single đo trước 2026-08-31 đều dính nhiễu này.

### 5.4 TN2 — Ablation 2×2 (thí nghiệm riêng)

```bash
# sau khi TN1 xong và code đã freeze
./isd-exp ablation run
```

**Có benchmark run riêng (đổi 2026-09-10).** TN2 = 4 arm × 2 size (0.8B, 4B) × `test_30`, 1 run
deterministic mỗi ô, tag `a1`. Bốn arm nằm trong **cùng một run** mỗi size nên chia chung LLM judge
session per scenario → delta arm-vs-A0 không dính LLM judge drift.

**A0 chạy lại trong TN2, không lấy từ TN1.** LLM judge session, scenario set và dải size đều khác, nên
so một arm TN2 với A0 của ladder là so xuyên thí nghiệm. `isd-exp ablation pool` vẫn đặt A0 của
TN2 cạnh A0 của TN1 nhưng như một **drift gauge**: nó chặn trên phần delta có thể do session gây
ra, không phải một phép so arm. Trước 2026-09-10 hai con số này đến từ cùng một run và phải bằng
nhau — mô tả đó đã hết hiệu lực.

`test_30` là subset stratified 1/ô của `test_90` (seed 42), nên hai thí nghiệm rút từ một pool
held-out duy nhất và A0 hai bên đọc được cạnh nhau; vẫn không phải paired, nên delta còn mang cả
sampling. Kiểm disjoint với tập tune:

```bash
./isd-exp data split ablation-30    # test_90 -> test_30, disjoint với train_10 và train
```

**Trần số ILO có ở CẢ BỐN arm và không có ở sáu baseline (2026-09-16).** `rulebook.MAX_OBJECTIVES = 6` được nội suy
vào rules của stage `outcomes`. Con số là của Biggs & Tang (`biggs2011teaching`, nguồn paper đã cite sẵn cho
constructive alignment): "programme and course outcomes alike should rarely exceed five or six in number, otherwise it
is practically impossible to align teaching/learning activities and assessment tasks to them all". Nó **phẳng**, không
phụ thuộc thời lượng khoá học, vì Biggs phát biểu năm-hoặc-sáu cho chính khoá dài một học kỳ. Trần **không được cưỡng
chế**: không có gì cắt bớt danh sách dài hơn, nên tỷ lệ tuân thủ là một phép đo, suy được thẳng từ danh sách objective
trong `addie_output` của mỗi run mà không cần key metadata riêng.

Nó nằm trong hệ được kiểm chứ không phải một control áp cho cả benchmark, nên khi so alignmentgraph với baseline thì
phải nói rõ: mọi tín hiệu panel lấy trung bình trên tập objective được tính trên một tập bị chặn ở phía hệ đề xuất và
không bị chặn ở phía baseline. Giữa bốn arm thì nó là hằng số, nên không ảnh hưởng delta arm-vs-A0.

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
không routing, không docket, không residual audit, và run **không có** key `graph` → không có file
`<agent_id>_graph.json` cho hai arm prose (đó chính là contrast auditability, không phải thiếu file); thay vào đó
hai arm prose ghi `<agent_id>_prose.json` — dump nguyên văn các document trên blackboard (artifact để inspect/debug,
KHÔNG phải audit: không relation, không coverage). Trục vì
vậy là một **bundle** ("bỏ máy alignment thì harness còn gì") và phải được disclose như bundle, không claim
single-variable.

Axes là **kwargs cố định theo agent_id** trong registry của `run_benchmark.py` (không phải env var) → không chạy nhầm
config được; mỗi run ghi `metadata.run_config` vào trajectory và script pool **hard-fail** nếu flag không khớp agent_id.

Post-processing chạy **sau khi ladder xong** (consistency check cần `pooled_comparison.json`):

```bash
./isd-exp ablation pool \
    --auto-glob 'results/test_30_benchmark_*_a*' \
    --ladder-pooled results/pooled_comparison.json          # → results/pooled_ablation.json
./isd-exp report ablation-tables
./isd-exp report ablation-figures
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

- Hướng delta trong bảng/hình = **arm − A0** (âm = gỡ thành phần làm giảm chất lượng); trong `pooled_ablation.json` các
  row comparison lưu chiều A0 − arm (contribution).
- `isd-exp comparison pool` chỉ xét proposed + 6 baseline nên 3 arm nằm cùng run dir **không bị nuốt** vào phía ladder.
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
./isd-exp audit preflight
```

Check: 4 pod alive + auth (401/200), model khớp slot, smoke completion (pod sinh ra chữ ở `content` **hoặc**
`reasoning_content` — thinking đang bật nên rỗng `content` chưa phải lỗi), 2 flag bảo hộ có mặt, disk trống.

### 6.2 In-flight (mỗi 30–60 phút)

```bash
./isd-exp audit inflight      # watch -n 300 để theo dõi liên tục
```

Đếm 524 / 400 / empty / stub trong log — **phải đứng yên ở 0** — cộng ✅/❌ per slot và progress freshness
(timestamp mới < 10 phút). GPU util = 0% kéo dài + progress đứng = treo.

### 6.3 Post-run

```bash
./isd-exp audit postrun                          # mọi run dir
./isd-exp audit postrun --fields-only <run_dir>  # riêng các trường RQ2 tiêu thụ
```

Script phân biệt **RED** (lỗi hạ tầng: stub / rỗng / token=0 / sai model / thiếu metric) với **info** (agent fail kiểu
capability — hợp lệ, failure policy ở mục 8 xử lý, **không** re-run). Nó phủ ba tầng:

- **Completeness** — roster và số scenario suy ra từ prefix dataset của thư mục run (`test_90_` → 7 agent
  × 90 scenario, `test_30_` → 4 arm × 30); override bằng `--agents` / `--expected-scenarios`. Mỗi scenario
  đủ output của các agent trong roster; có `comparison_report.json`; `benchmark_summary.json` tồn tại;
  đủ 4 size (TN1) / 2 size (TN2) trước khi pool.
- **Integrity** — stub/default output (stub đủ 33 sub-item nên nhìn "đầy đủ", phải quét bằng marker), output < 1KB,
  trajectory rỗng, `token_usage.total_tokens = 0`, model name trong metadata khớp thư mục run, duration hợp lý.
- **Metrics** — mỗi `comparison_report.json` có `total_score` (median multi-judge), `addie_score`, `trajectory_score`;
  đủ 5 phase ADDIE; đủ số LLM judge cấu hình; phân phối điểm sanity (không agent nào toàn 0 hoặc toàn 100).

`--fields-only` gọi thẳng extractor của evaluator để xem **đúng những trường RQ2 tiêu thụ** (objectives / assessments /
activities / evaluation) có rỗng không. Quan trọng: output parse được nhưng không trích ra objective nào sẽ bị chấm
`0.0` và trông y hệt một thiết kế lệch thật — chỉ ở đây mới phân biệt được parse fail với chất lượng kém.

> ⚠️ **Bẫy CSV Avg**: cột `Avg` trong aggregate CSV là trung bình theo LLM judge, lệch khi thiếu component. Số chuẩn cho paper luôn là
> per-scenario `total_score`.

### 6.4 Red flags

| Dấu hiệu                         | Ý nghĩa                       | Hành động                                  |
|----------------------------------|-------------------------------|--------------------------------------------|
| `Error code: 524`                | Proxy cắt call >120s          | Dừng, kiểm `AGENT_MODEL_STREAMING`         |
| `Error code: 400` max context    | Cap không ăn / prompt quá dài | Kiểm `AGENT_MODEL_MAX_OUTPUT_TOKENS`          |
| `기본 출력 반환` / stub marker         | Baseline ghi default output   | Loại scenario/run, tìm nguyên nhân rỗng    |
| `응답 길이: 0`                       | Model trả rỗng                | Kiểm pod log + cap completion (<think>)    |
| `token_usage = 0` hàng loạt      | Accounting hỏng               | Sửa trước khi chạy tiếp — số token sai hết |
| `token_usage = 0` ở **một số** agent | Agent đó dùng `LLMConfig` đã tách khỏi counter của run | Counter đi theo lineage của config: `_get_agent_runner` mở scope bằng `new_token_scope()`, `copy_with()` chia sẻ lại. Chạy `pytest shared/tests/test_token_accounting_reaches_agents.py` |
| Model name metadata ≠ run dir    | Nhầm URL pod ↔ slot           | Loại run, kiểm `base_urls` trong experiment.toml |
| `evaluation_error` trong summary | LLM judge chết giữa chừng         | `04_repair_ladder_results.py` (xem dưới)   |
| Pod EXITED giữa run              | OOM/crash server              | Xem RunPod console log, kiểm VRAM          |

LLM judge lỗi transient sửa được **không cần sinh lại output**:

```bash
./isd-exp audit repair --dry-run   # xem phạm vi, không gọi LLM judge
./isd-exp audit repair             # sửa rồi tự chạy audit post-run
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

Khai URL của pod vào arm primary trong `experiment.toml`, cùng chỗ với ladder:

```toml
[alignment.encoders.nemotron]
base_urls = ["https://<pod_id>-8000.proxy.runpod.net/v1"]
# revision = "<HF commit>"   # ghim weights; cũng vào khoá cache embedding
```

```bash
RUNS='results/test_90_benchmark_*_r* results/test_30_benchmark_*_a*'

# (1) arm primary — cần pod đang chạy
./isd-exp score $RUNS

# (2) TẮT POD, rồi chấm 3 arm sensitivity còn lại hoàn toàn local (~70 phút)
./isd-exp score $RUNS \
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
python ./isd-exp bloom train --train ../EDM2022CLO/data/sample_full.csv \
    --output-dir models/bloom-bert-edm2022
./isd-exp score --bloom-presets lexicon --embed-cache-only $RUNS
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
./isd-exp bloom validate ../EDM2022CLO/data/sample_full.csv \
    --text-col Learning_outcome --label-cols Remember,Understand,Apply,Analyze,Evaluate,Create \
    --out results/generated/bloom_validation.md
# thêm arm BERT: trỏ CSV vào held-out split cạnh checkpoint, KHÔNG dùng corpus đã train
./isd-exp bloom validate models/bloom-bert-edm2022/eval_split.csv \
    --text-col text --label-col label --bloom-checkpoint models/bloom-bert-edm2022
```

## 8. Pool → thống kê RQ1 + RQ2

```bash
./isd-exp comparison pool \
    --auto-glob 'results/test_90_benchmark_*_r*' --auto-encoders --auto-bloom
```

Output `results/pooled_comparison.json` + report stdout. Gộp run/size (mean-of-runs; TN1 mặc định 1 run), rồi per-size: Wilcoxon paired
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
./isd-exp report tables --pooled results/pooled_comparison.json
./isd-exp report sensitivity     # nếu có alignment_sensitivity
./isd-exp report figures --runs-glob 'results/test_90_benchmark_*_r*'
cd .. && ./isd-exp report sync                                 # từ repo thesis
```

Tất cả ghi vào `results/generated/` (benchmark-local, gitignored): `tab_llm_judge_addie.tex` (ADDIE-lead) kèm
`tab_llm_judge_total.tex`/`tab_llm_judge_trajectory.tex` (Total/Trajectory song song, cùng logic §A.2), `tab_alignment.tex`
(tín hiệu dẫn) kèm `tab_alignment_panel.tex` (panel đầy đủ 7 tín hiệu), `stats_macros.tex` (mọi con số trong prose là
`\newcommand`), `stats_summary.md` (bản dump người đọc để cross-check).

### 9.2 Facts sheet — gộp mọi số vào một file

```bash
./isd-exp report facts           # → results/generated/facts.md (~135 KB)
./isd-exp report facts --brief   # → facts_brief.md (~21 KB, chỉ mục 0–2)
```

Chạy **sau** `report tables`/`ablation-tables`/`cost`/`sensitivity` (nó đọc `*_macros.tex` để dựng mục 10). Nguồn: `pooled_comparison.json` +
`pooled_ablation.json` — không parse lại các `stats_*.md`, nên không có nguồn sự thật thứ hai.

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

`facts.md` là tài liệu để đọc/đưa cho LLM diễn giải, **không** phải artifact paper `\input` — nên `isd-exp audit artifacts`
không kiểm nó.

**Quy ước artifact (2026-07-30, enforce bằng `isd-exp audit artifacts` check I):** mọi text trong artifact là
**tiếng Anh**, số dùng **dấu chấm** (`87.77`). Caption chỉ nói *bảng chiếu gì* và *một ô là gì*, ~100–250 ký tự;
phần biện luận phương pháp thuộc mục Methods. Mean và SD phải cùng một signal (`sd_{addie,traj,total}_across_scenarios`
trong pooled; `run_to_run_sd` trần là Total, chỉ còn tồn tại cho `isd-exp ablation pool`). Ô nào tính trên tập
scenario thiếu thì phải in `n` + footnote — RQ2 đếm scenario có **ít nhất một** run chấm được, điều kiện yếu hơn
complete-case (đủ mọi run của ô) của RQ1, nên hai bảng ghi nhãn khác nhau.
Số format kiểu VN (`{,}`). `isd-exp report sync` là **bước copy duy nhất** sang `docs/generated/`; LaTeX trỏ tới đó bằng
đường dẫn tương đối.

Hình (cả `.pdf` vector lẫn `.png` preview; text trong hình tiếng Anh, caption tiếng Việt viết trong LaTeX):

| Hình                     | Nội dung                                                                     |
|--------------------------|------------------------------------------------------------------------------|
| `fig_llm_judge_ladder`         | ADDIE vs model size, error bar = ±SEM across scenarios (headline RQ1)        |
| `fig_llm_judge_delta`          | Δ(proposed − baseline) per size, CI95, marker đặc = p_holm < 0,05, kèm slope |
| `fig_llm_judge_components`     | ADDIE vs Trajectory theo size                                                |
| `fig_alignment_ladder`         | Objective–assessment alignment vs size (headline RQ2)                        |
| `fig_alignment_components`     | Heatmap agents × 5 alignment component per size                              |
| `fig_alignment_vs_llm_judge_scatter` | Per-scenario alignment vs Total, Spearman ρ per size — cần `--runs-glob`     |
| `fig_failure_rate`       | % scenario fail per agent × size                                             |
| `fig_cost_quality`       | Total vs total token / exec time (deployment-cost angle)                     |

`--demo` render bằng dữ liệu synthetic để test layout. Thiếu alignment/token data ⇒ hình tương ứng skip kèm cảnh báo.

Điều kiện serve phải ghi trong paper (bf16, 16k, streaming, cap 8192) — lấy nguyên văn từ mục 3.

## 9.1 Cổng cuối: audit artifact

```bash
./isd-exp audit artifacts            # sau khi đã sync
./isd-exp audit artifacts --strict   # WARN cũng fail
./isd-exp audit artifacts --no-docs  # chỉ phía benchmark
```

Chạy **sau** toàn bộ mục 9 (kể cả `isd-exp report sync`). Có mặt file là kiểm tra yếu nhất, nên script soi 8 lớp:
drift inventory (A — quét thẳng source của 5 generator, hai chiều, nên generator thêm output mới thì không thể lọt),
thiếu file (B), lệch sync docs↔results theo **byte** (C — nay cả `sync` lẫn audit đều đọc chung một bảng khai báo `report/inventory.py`, nên không còn hai danh sách để lệch nhau),
placeholder/TBD-DEMO (D — generator cố tình sinh file comment-only `\input` được khi thiếu pooled layer, LaTeX vẫn
compile và bảng biến mất im lặng), độ mới đọc từ **header** chứ không phải mtime (E — sync là `cp` nên restamp mọi
file), figure phải đủ cặp `.pdf`+`.png` (F), `\input`/`\includegraphics` có resolve và artifact nào chưa ai tham
chiếu (G), và macro nào prose dùng mà không generator nào định nghĩa (H — `Undefined control sequence`, lỗi build
mà kiểm tra file không bao giờ thấy).

Cái gì là *bắt buộc* phụ thuộc pooled layer đang có: artifact ablation chỉ bị đòi khi có `pooled_ablation.json`,
sensitivity khi pooled ladder có `alignment_sensitivity`; hai file bloom validation luôn chỉ WARN vì cần checkpoint
train tay. Exit 0 = không RED (và không WARN nếu `--strict`).

## 10. Teardown

- **Tắt/xoá pod RunPod ngay** (thao tác console, không có script) — tính tiền theo giờ kể cả idle.
- Giữ nguyên vẹn: mọi `results/test_90_benchmark_*_r*/`, mọi `comparison_manifest.json`, `pooled_comparison.json`,
  `scenarios/*_metadata.json`, và `experiment.toml` (đã được `freeze write` băm).
- Số và hình trong paper regenerate được bất kỳ lúc nào từ raw results bằng chuỗi mục 7 → 8 → 9.

---

# Phụ lục A — Metrics reference

Ba nhóm, theo nguồn tính toán thực tế trong code:

1. **LLM judge quality metrics** (A.1) — LLM judge chấm từng ADDIE output, nguồn cho RQ1.
2. **RQ1 statistics** (A.2) — thống kê suy diễn trên các LLM judge metric đã pool theo model size.
3. **RQ2 alignment protocol** (A.3) — thước đo constructive alignment tự động, **không LLM**, độc lập với LLM judge và với
   verifier nội bộ của harness.

Cộng thêm **operational metadata** (A.4) — log để debug, không vào headline stats.

## A.1 LLM judge quality metrics (per-scenario)

Nguồn: [`evaluator/src/isd_evaluator/`](../../isd-agent-benchmark/evaluator/src/isd_evaluator/).

**ADDIE Rubric Score (0–100)** — `metrics/addie_rubric.py`, rubric ở `rubrics/addie_definitions.py`. Hai bước LLM-judge
tuần tự cho mỗi sub-item: (1) *status* — phân loại vào `absent/weak/moderate/good/excellent`, mỗi trạng thái ứng một
khoảng điểm cố định; (2) *score* — chấm chi tiết, **bị ép cứng** nằm trong khoảng của status, tránh LLM judge chấm vượt
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
(3 failure policy, Holm theo từng (signal, policy)) dưới `comparisons.by_score[<signal>]`, và `total_score` vẫn báo
đầy đủ để so sánh được với chính ISD-Agent-Bench. Quyết định này là **post-hoc** (chọn sau khi đã thấy kết quả) và
phải khai đúng như vậy trong paper.

Về composite: per-scenario `total_score` trong `comparison_report.json` —
**không phải** cột `Avg` của `aggregate_table.csv`.

## A.2 RQ1 statistics

File: [`isd-exp comparison pool`](../../experiments/src/isd_experiments/pool/comparison.py).
Input: 4 size × 1 run × 90 scenario (TN1), mỗi scenario đã có `Total` cho từng agent.

- **`mean_total`** — trung bình `Total` của một agent tại một size, pool qua run rồi qua scenario (complete-case là
  policy chính).
- **`sd_{total,addie,traj}_across_scenarios`** — SD **giữa các scenario** của chính signal đó. Đây là con số in trong
  ngoặc cạnh mean ở `tab_llm_judge_addie.tex` và vẽ thành **SEM** (`sd/√n`) làm error bar của `fig_llm_judge_ladder`. Nó là **độ tản mô
  tả**, không phải ước lượng độ chính xác — khoảng tin cậy là bootstrap CI ở tầng so sánh. Cùng quy ước với bảng/hình
  panel RQ2, nên error bar hai họ instrument có cùng nghĩa.
- **`run_to_run_sd{,_addie,_traj,_total}`** — SD giữa các giá trị trung bình cấp-run. **`None` khi ô chỉ có 1 run**,
  tức mặc định của TN1; chỉ những ô nằm trong *targeted repeat* mới có số. Tính trên **đúng tập complete-case của
  `mean_total`**: nếu mỗi run trung bình trên một tập scenario khác nhau thì các run mean không so sánh được, và độ tản
  của chúng lẫn biến thiên run-to-run với khác biệt thành phần scenario. Consumer phải kiểm `isinstance(x, float)`
  trước khi in.
- **JSON hợp lệ**: `json_safe()` đổi mọi float không hữu hạn thành `null` ngay tại chỗ dump, nên `pooled_comparison.json`
  đọc được bằng parser chặt (`json.dumps(..., allow_nan=False)`), không còn token `NaN` trần.
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

File: [`alignment/protocol.py`](../../experiments/src/isd_experiments/alignment/protocol.py).
Đặc tả chốt + rationale: [`docs/guides/alignment_protocol.md`](alignment_protocol.md).

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

**Encoder.** Primary `nvidia/llama-embed-nemotron-8b` — family independence: Llama/NVIDIA ≠ agent Qwen ≠ LLM judge
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
(`isd-exp bloom train`); thiếu checkpoint thì mọi arm bị SKIP chứ không fallback ngầm.

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
  6 lớp cho thẳng quyết định đó, train bằng `isd-exp bloom train`.
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
