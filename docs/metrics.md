# Metrics

Liệt kê toàn bộ các metric được đo trong dự án và ý nghĩa của từng metric, theo nguồn tính toán thực tế trong code (
không phải mô tả lý thuyết). Bối cảnh RQ xem [`docs/summary.md`](summary.md).

Có ba nhóm, tương ứng ba tầng của pipeline đo lường:

1. **Judge quality metrics** — do LLM judge chấm trên từng ADDIE output (per scenario), nguồn cho RQ1.
2. **RQ1 statistics** — thống kê suy diễn (paired test, effect size, CI) tính trên các judge metric đã pool theo model
   size, dùng để trả lời "chất lượng có được duy trì khi thu nhỏ model không".
3. **RQ2 alignment metric** — thước đo constructive alignment định lượng, tự động, **không dùng LLM ở bước tổng hợp**,
   tính độc lập với judge và với verifier nội bộ của harness.

Ngoài ra có một số **operational metadata** được ghi log nhưng không nằm trong headline stats của hai RQ.

---

## 1. Judge quality metrics (per-scenario, LLM judge)

Nguồn: `isd-agent-benchmark/evaluator/src/isd_evaluator/`. Mỗi scenario, mỗi agent được một (hoặc nhiều, nếu
multi-judge) LLM judge chấm hai phần độc lập, gộp thành một **Total** composite.

### 1.1 ADDIE Rubric Score (0–100)

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
  Evaluation 15% — điều chỉnh động theo context của scenario (mục 1.3).
- `normalized_score` = `total_weighted / max_possible_weighted × 100` — đây là con số ADDIE 0–100 dùng downstream.

### 1.2 Trajectory Score (0–100)

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

### 1.3 Context-aware phase weighting (điều chỉnh trọng số, không phải metric riêng)

File: [`metrics/context_weights.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/context_weights.py).
Không tự nó là một con số được báo cáo, nhưng **quyết định trọng số phase** dùng ở mục 1.1 → ảnh hưởng trực tiếp
`normalized_score`. `ContextWeightAdjuster` suy ra hồ sơ ngữ cảnh scenario (loại hình tổ chức, hình thức triển khai, độ
tuổi/học lực/vai trò người học, domain, quy mô lớp, môi trường công nghệ, thời lượng — theo Context Matrix) rồi cộng/trừ
trọng số từng phase (kẹp trong [0.05, 0.50], chuẩn hoá lại tổng = 1). Mục đích: một scenario "PBL" thì Design+Evaluation
quan trọng hơn Development, một scenario "VR" thì ngược lại — rubric chấm phải phản ánh đúng trọng tâm của bối cảnh đó
thay vì áp trọng số cố định cho mọi scenario.

### 1.4 Total composite (0–100)

File: [`models/__init__.py`](../isd-agent-benchmark/evaluator/src/isd_evaluator/models/__init__.py) (
`CompositeScore.total`).

```
Total = 0.7 × ADDIE.normalized_score + 0.3 × Trajectory.total
```

Đây là con số **canonical** dùng cho mọi so sánh giữa agent (per-scenario `total_score` trong
`comparison_report.json`) — **không phải** cột "Avg" của `aggregate_table.csv`, vốn là judge-mean và lệch khi thiếu
component (xem [[aggregate-table-avg-inconsistency]] trong memory).

---

## 2. RQ1 statistics — duy trì chất lượng theo model scale

File: [`scripts/7_pool_ladder_runs.py`](../isd-agent-benchmark/scripts/7_pool_ladder_runs.py). Input: 4 kích thước
Qwen (0.8B/2B/4B/9B) × 3 run độc lập/kích thước × 90 scenario (`test_90`), mỗi scenario đã có `Total` (mục 1.4) cho từng
agent. Đây là các thống kê **suy diễn**, không phải điểm số thô.

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

## 3. RQ2 — Alignment metric (constructive alignment, LLM-free)

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

---

## 4. Operational metadata (không phải headline metric của RQ1/RQ2)

Ghi trong `metadata` của mỗi kết quả agent (`run_benchmark.py`), dùng cho debug/audit chi phí, **không** đi vào Total
hay alignment composite:

- **`token_usage`** — snapshot từ `shared/llm/token_accounting`, tổng token input/output mỗi lần chạy một scenario (đảm
  bảo mọi agent dùng `max_tokens` đồng nhất — fairness).
- **`execution_time_seconds`** — thời gian chạy hết một scenario.

