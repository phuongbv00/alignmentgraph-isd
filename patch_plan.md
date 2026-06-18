# Patch Plan Cho Claude Code: Sync `proposal.html` Và Thêm Slide Benchmark 18/06/2026

## Mục Tiêu

Không chỉnh trực tiếp `docs/proposal.html` bằng tay trong bước này. File này là kế hoạch patch chi tiết để Claude Code thực hiện:

1. Cập nhật phần Evaluation trong `docs/proposal.md`.
2. Thêm 1 slide kết quả benchmark ngày **18/06/2026** trên `test_30`.
3. Sync `docs/proposal.html` với nội dung mới trong Markdown.
4. Cập nhật tiến độ P2.2 trong `fix_plan.md` sau khi HTML đã được sync.

Nguồn kết quả benchmark:

```text
isd-agent-benchmark/results/test_30_benchmark_gemma-4-26b-a4b-it-nitro_20260618_193248/aggregate_table.md
```

Agent model dùng cho benchmark:

```text
Gemma 4 26B A4B
```

## Không Làm

- Không đổi code harness trong task này.
- Không regenerate hoặc sửa `docs/assets/arch.svg`.
- Không thay đổi benchmark result source.
- Không claim statistical superiority từ `test_30`; chỉ ghi là preliminary/smoke benchmark.

## Dữ Liệu Benchmark Cần Đưa Vào

### Tổng Quan Evaluator Model

| Agent | GPT | Gemini | Avg |
| --- | ---: | ---: | ---: |
| Baseline | 79.97 | 82.13 | 81.05 |
| EduPlanner | 83.68 | 86.10 | 84.89 |
| ADDIE-Agent | 82.78 | 83.57 | 83.18 |
| RPISD-Agent | 83.43 | 83.23 | 83.33 |
| Dick-Carey-Agent | 80.86 | 81.33 | 81.09 |
| React-ADDIE | 85.40 | **88.96** | **87.18** |
| AlignmentGraph-ISD (proposed) | **85.63** | 85.70 | 85.67 |

### Score Components

| Agent | Total | ADDIE | Trajectory |
| --- | ---: | ---: | ---: |
| React-ADDIE | **87.18** | **84.65** | **93.08** |
| AlignmentGraph-ISD (proposed) | 85.67 | 84.50 | 88.38 |
| EduPlanner | 84.89 | 82.18 | 91.21 |

### Difficulty

| Agent | Easy | Med. | Hard |
| --- | ---: | ---: | ---: |
| React-ADDIE | **87.67** | **86.94** | **86.93** |
| AlignmentGraph-ISD (proposed) | 86.17 | 85.24 | 85.59 |
| EduPlanner | 84.54 | 84.69 | 85.50 |

### Phase-wise Highlights

| Agent | Ana. | Des. | Dev. | Impl. | Eval. |
| --- | ---: | ---: | ---: | ---: | ---: |
| React-ADDIE | 80.4 | **86.6** | **90.3** | 81.1 | 83.7 |
| AlignmentGraph-ISD (proposed) | 82.4 | 85.2 | 85.0 | **82.3** | **85.0** |

Interpretation ngắn:

- AlignmentGraph-ISD đạt **85.67 Avg**, đứng sau React-ADDIE (**87.18**) trên `test_30`.
- AlignmentGraph-ISD đứng đầu theo evaluator GPT (**85.63**) và dẫn phase **Implementation** (**82.3**) + **Evaluation** (**85.0**) theo 2-model average.
- Khoảng cách chính hiện tại nằm ở **Trajectory**: AlignmentGraph-ISD 88.38, React-ADDIE 93.08. Đây là tín hiệu cần tiếp tục hoàn thiện structured trajectory, verifier/repair, dynamic task graph và element-level graph.
- Kết quả này là preliminary trên subset nhỏ `test_30`, chưa dùng để claim superiority.

## Patch 1: Cập Nhật `docs/proposal.md`

### Vị trí chèn

Trong `docs/proposal.md`, chèn sau đoạn metric table của mục `### 3.2 Quantitative Evaluation on ISD-Agent-Bench`, ngay sau câu:

```text
Kết quả được báo cáo theo toàn bộ test split hoặc một subset cân bằng nếu giới hạn chi phí...
```

và trước heading hiện tại:

```text
### 3.3 Ablation Study
```

### Nội dung Markdown cần chèn

```markdown
### 3.3 Preliminary Benchmark Result on `test_30` (18/06/2026)

Một benchmark sơ bộ đã được chạy ngày **18/06/2026** trên subset `test_30`, dùng agent model **Gemma 4 26B A4B**. Kết quả được lưu tại:

```text
isd-agent-benchmark/results/test_30_benchmark_gemma-4-26b-a4b-it-nitro_20260618_193248/aggregate_table.md
```

Kết quả này được dùng như checkpoint kỹ thuật để xem proposed agent đang đứng ở đâu trước khi hoàn thiện các phần còn thiếu của system design. Vì subset chỉ có 30 scenarios, kết quả chưa được dùng để claim statistical superiority.

| Agent | GPT | Gemini | Avg |
| --- | ---: | ---: | ---: |
| React-ADDIE | 85.40 | **88.96** | **87.18** |
| AlignmentGraph-ISD (proposed) | **85.63** | 85.70 | 85.67 |
| EduPlanner | 83.68 | 86.10 | 84.89 |
| RPISD-Agent | 83.43 | 83.23 | 83.33 |
| ADDIE-Agent | 82.78 | 83.57 | 83.18 |
| Dick-Carey-Agent | 80.86 | 81.33 | 81.09 |
| Baseline | 79.97 | 82.13 | 81.05 |

Các điểm đáng chú ý:

- AlignmentGraph-ISD đạt **85.67 Avg**, đứng thứ hai sau React-ADDIE (**87.18**).
- AlignmentGraph-ISD đạt điểm cao nhất theo evaluator GPT (**85.63**).
- Theo phase-wise average, AlignmentGraph-ISD đang dẫn ở **Implementation** (**82.3**) và **Evaluation** (**85.0**).
- Khoảng cách lớn nhất hiện nằm ở **Trajectory**: AlignmentGraph-ISD đạt **88.38**, thấp hơn React-ADDIE (**93.08**), cho thấy cần tiếp tục hoàn thiện logging, repair trace và dynamic orchestration.

Kế hoạch tiếp theo là tiếp tục implement các phần còn gap so với proposed system design, gồm:

- schema validation chi tiết và routing lỗi về owner agent;
- verifier mở rộng cho rubric consistency, feasibility, actionability và evaluation alignment;
- element-level AlignmentGraph cho objectives, assessments, activities, materials, constraints và evaluation nodes;
- Dynamic ISD Task Graph Builder thay cho planner chỉ dựa trên candidate list;
- retrieval subagent interface cho external corpus trong case study;
- structured trajectory cho validation, verifier, repair và cascade events.

Sau khi các gap chính được đóng, evaluation sẽ mở rộng từ `test_30` sang `test_90`, sau đó tăng dần độ robust trên các subset lớn hơn trước khi chạy full testset **1202 scenarios**.
```

### Cập nhật numbering heading

Sau khi thêm section mới, đổi numbering các heading sau đó:

- `### 3.3 Ablation Study` -> `### 3.4 Ablation Study`
- `### 3.4 Case Study Evaluation for IT/Software Engineering Prototype` -> `### 3.5 Case Study Evaluation for IT/Software Engineering Prototype`
- `### 3.5 Threats to Validity` -> `### 3.6 Threats to Validity`

## Patch 2: Sync `docs/proposal.html`

`docs/proposal.html` là slide deck thủ công dùng `const slides = [...]`, không phải HTML render trực tiếp từ Markdown. Vì vậy cần thêm slide mới vào mảng `slides`.

### Vị trí thêm slide

Trong `docs/proposal.html`, tìm slide:

```html
<div class="s-label">5 · Evaluation · ISD-Agent-Bench</div>
```

Thêm slide benchmark mới ngay sau slide này và trước slide hiện có:

```html
<div class="s-label">5 · Evaluation</div>
```

### Nội dung slide HTML đề xuất

Dùng inline style để tránh phải sửa CSS nhiều. Nếu muốn thêm CSS class thì giữ tối thiểu.

```html
  /* ── Benchmark Result — test_30 ── */
  {content: `
    <div class="s-label">5 · Evaluation · Preliminary Benchmark</div>
    <div class="s-title">Benchmark sơ bộ trên <span class="accent">test_30</span><br><span style="font-size:1.25rem;color:#64748b">18/06/2026 · Agent model: Gemma 4 26B A4B</span></div>
    <div class="s-body" style="gap:12px">
      <div class="card-row" style="gap:12px">
        <div class="card indigo">
          <div class="card-label">Overall Avg</div>
          <div class="card-text"><strong>AlignmentGraph-ISD: 85.67</strong><br>Rank #2 sau React-ADDIE 87.18 trên subset 30 scenarios.</div>
        </div>
        <div class="card teal">
          <div class="card-label">Best GPT Judge</div>
          <div class="card-text"><strong>85.63</strong><br>Cao nhất theo GPT evaluator, nhỉnh hơn React-ADDIE 85.40.</div>
        </div>
        <div class="card amber">
          <div class="card-label">Phase Strength</div>
          <div class="card-text"><strong>Implementation 82.3 · Evaluation 85.0</strong><br>Dẫn đầu ở hai pha rollout/evaluation.</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1.05fr 0.95fr;gap:14px;align-items:start">
        <div style="border:1.5px solid #e2e8f0;border-radius:12px;overflow:hidden;background:#fff">
          <div style="display:grid;grid-template-columns:1.55fr repeat(3,0.6fr);background:#f1f5f9;color:#64748b;font-size:0.68rem;font-weight:800;letter-spacing:.7px;text-transform:uppercase">
            <div style="padding:8px 10px">Agent</div><div style="padding:8px 10px;text-align:right">GPT</div><div style="padding:8px 10px;text-align:right">Gemini</div><div style="padding:8px 10px;text-align:right">Avg</div>
          </div>
          <div style="display:grid;grid-template-columns:1.55fr repeat(3,0.6fr);font-size:0.74rem;color:#334155">
            <div style="padding:7px 10px;border-top:1px solid #e2e8f0;font-weight:800;color:#4f46e5">React-ADDIE</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">85.40</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right;font-weight:800">88.96</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right;font-weight:800">87.18</div>
            <div style="padding:7px 10px;border-top:1px solid #e2e8f0;font-weight:800;color:#4f46e5">AlignmentGraph-ISD</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right;font-weight:800">85.63</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">85.70</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">85.67</div>
            <div style="padding:7px 10px;border-top:1px solid #e2e8f0">EduPlanner</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">83.68</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">86.10</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">84.89</div>
            <div style="padding:7px 10px;border-top:1px solid #e2e8f0">Baseline</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">79.97</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">82.13</div><div style="padding:7px 10px;border-top:1px solid #e2e8f0;text-align:right">81.05</div>
          </div>
        </div>

        <div class="pill-list" style="gap:8px">
          <div class="pill blue"><div class="pill-dot"></div><div><span class="kw">Trajectory gap</span>: AlignmentGraph-ISD 88.38 vs React-ADDIE 93.08 → cần structured trace, repair/cascade logging.</div></div>
          <div class="pill green"><div class="pill-dot"></div><div>Tiếp tục đóng gap: schema validation, verifier mở rộng, element-level graph, dynamic task graph, retrieval subagents.</div></div>
          <div class="pill amber"><div class="pill-dot"></div><div>Lộ trình benchmark: <code>test_30</code> → <code>test_90</code> → subset lớn hơn → full testset <strong>1202 scenarios</strong>.</div></div>
        </div>
      </div>
    </div>
  `},
```

### Lưu ý khi patch HTML

- Đảm bảo dấu phẩy giữa các object trong `slides` đúng cú pháp JS.
- Không cần sửa `counter`; deck tự đọc `slides.length`.
- Nếu label slide hiện tại có số thứ tự comment bị lệch thì có thể để nguyên comments hoặc cập nhật comments cho dễ đọc; không ảnh hưởng runtime.
- Không đưa quá nhiều bảng vào slide; slide chỉ cần summary, không cần full aggregate table.

## Patch 3: Cập Nhật `fix_plan.md`

Sau khi đã cập nhật cả `docs/proposal.md` và `docs/proposal.html`, cập nhật P2.2:

### Tìm mục

```markdown
### P2.2 Sync `proposal.html`
```

### Thêm dòng trạng thái ngay dưới heading

```markdown
**Trạng thái:** Done. Đã thêm slide benchmark `test_30` ngày 18/06/2026 vào phần Evaluation và sync `docs/proposal.html` với `docs/proposal.md`.
```

### Tick checklist cuối

Đổi:

```markdown
- [ ] `docs/proposal.html` đồng bộ với `docs/proposal.md`.
```

thành:

```markdown
- [x] `docs/proposal.html` đồng bộ với `docs/proposal.md`.
```

## Verification

Sau patch, chạy:

```bash
rg -n "no_rag|use_rag" alignmentgraph-isd/src docs/proposal.md fix_plan.md
```

Kỳ vọng:

- Không có match.

Chạy:

```bash
rg -n "test_30|Gemma 4 26B A4B|1202 scenarios|no_ext_corpus" docs/proposal.md docs/proposal.html fix_plan.md
```

Kỳ vọng:

- `test_30`, `Gemma 4 26B A4B`, `1202 scenarios` xuất hiện trong `docs/proposal.md` và `docs/proposal.html`.
- `no_ext_corpus` vẫn xuất hiện trong phần ablation.

Mở slide deck:

```bash
open docs/proposal.html
```

Kiểm tra thủ công:

- Slide benchmark mới nằm trong cụm Evaluation.
- Bảng không tràn layout ở viewport desktop.
- Counter slide vẫn hoạt động khi bấm next/prev.
- Nội dung không claim superiority; chỉ nói preliminary trên `test_30`.
