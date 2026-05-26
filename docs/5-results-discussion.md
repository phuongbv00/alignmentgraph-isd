# Chương 5 — Kết quả và thảo luận

> File này là khung điền sau khi chạy thực nghiệm. Chương 4 đã cố định protocol; Chương 5 chỉ báo cáo kết quả theo đúng benchmark adapters, không chọn lại metric hoặc baseline sau khi thấy kết quả.

## 5.1 Run summary

Mở đầu chương cần báo cáo `run_manifest` để người đọc biết kết quả được tạo trong điều kiện nào.

| Nhóm thông tin | Giá trị báo cáo |
| --- | --- |
| Prototype | commit hash, ngày chạy, harness version |
| Benchmark adapters | benchmark name/version, split, adapter version, số sample hợp lệ |
| Model | model/checkpoint, runtime, decoding config |
| Judge | judge model, rubric version, human subset size |
| Baselines | prompt/workflow template ids, retry policy |
| Cost trace | token usage, LLM calls, tool calls, latency |

Nếu một benchmark hoặc paper source chỉ được dùng ở mức construct-only, phần này phải ghi rõ và không đưa nó vào bảng comparison điểm số.

## 5.2 RQ1 — Instructional design benchmark results

Bảng chính báo cáo kết quả trên benchmark instructional design, ví dụ ISD-Agent-Bench hoặc benchmark tương đương được chọn ở Chương 4.

| Variant | Quality score | Lesson-plan quality | Constructive alignment | Actionability | Trajectory quality | Schema validity | Latency p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LLM-only | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Theory-grounded prompting | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ReAct/general-agent baseline | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Adaptive Instructional Design Agent Harness | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Diễn giải cần trả lời:

- Harness hơn baseline nào, theo metric nào?
- Cải thiện đến từ artifact quality, alignment, actionability, schema compliance hay workflow/trajectory?
- Chi phí latency/token/tool call có chấp nhận được trong bối cảnh giáo viên không?
- Có dimension nào harness không tốt hơn baseline không?

## 5.3 RQ2 — Learner-state adaptation results

Phần này báo cáo kết quả trên benchmark adaptive tutoring/feedback. Nếu benchmark có pair hoặc condition khác nhau theo learner context, báo cáo delta theo cặp; nếu không có pair, báo cáo comparison theo rubric adaptivity.

| Variant | Adaptivity | Scaffold quality | Feedback helpfulness | Misconception handling | Non-harmful adaptation | Schema validity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LLM-only | TBD | TBD | TBD | TBD | TBD | TBD |
| Theory-grounded prompting | TBD | TBD | TBD | TBD | TBD | TBD |
| ReAct/general-agent baseline | TBD | TBD | TBD | TBD | TBD | TBD |
| Harness without learner-state injection | TBD | TBD | TBD | TBD | TBD | TBD |
| Adaptive Instructional Design Agent Harness | TBD | TBD | TBD | TBD | TBD | TBD |

Khi diễn giải, cần chỉ ra ví dụ cụ thể:

- Output có dùng learner/student context để điều chỉnh scaffold hoặc feedback không?
- Có xử lý đúng misconception hay chỉ nhắc lại nhãn lỗi?
- Learner-state injection giúp ở loại task nào nhiều nhất?
- Có trường hợp adaptation sai hướng, hạ thấp kỳ vọng hoặc tạo feedback tiêu cực không?

## 5.4 Statistical report

Bảng này chỉ báo cáo các so sánh chính đã định nghĩa trước trong Chương 4.

| Comparison | Metric | Test | Delta | Effect size | p-value | Corrected p | Interpretation |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Harness vs LLM-only | quality_score | Wilcoxon / paired test | TBD | TBD | TBD | TBD | RQ1 |
| Harness vs ReAct/general-agent | quality_score | Wilcoxon / paired test | TBD | TBD | TBD | TBD | RQ1 |
| Harness vs theory-grounded prompting | constructive_alignment | Wilcoxon / paired test | TBD | TBD | TBD | TBD | RQ1 |
| Harness vs harness without learner-state injection | adaptivity | Wilcoxon / paired test | TBD | TBD | TBD | TBD | RQ2 |
| Harness vs harness without learner-state injection | misconception_handling | Wilcoxon / paired test | TBD | TBD | TBD | TBD | RQ2 |

Không kết luận chỉ dựa vào p-value. Nếu effect size nhỏ, confidence interval rộng, hoặc chi phí vận hành tăng lớn, phần thảo luận phải nói rõ.

## 5.5 Judge reliability

Trước khi dùng LLM-as-judge làm bằng chứng chính, báo cáo độ tin cậy của judge.

| Metric group | Agreement metric | Value | Threshold | Decision |
| --- | --- | ---: | ---: | --- |
| Pass/fail labels | Cohen's kappa | TBD | 0.6 | use / auxiliary only |
| Ordinal rubric 0-3 | weighted kappa hoặc alpha | TBD | 0.6 | use / auxiliary only |
| LLM-human alignment | Spearman correlation | TBD | report | use / auxiliary only |

Nếu judge agreement thấp, Chương 5 phải hạ mức khẳng định, ví dụ "metric này gợi ý xu hướng" thay vì "chứng minh hệ thống tốt hơn".

## 5.6 Computer Science case study

Case study Computer Science được báo cáo sau phần benchmark để minh hoạ cách harness được instantiate trong một domain cụ thể. Phần này không phải RQ và không dùng để claim statistical superiority.

| Thành phần case study | Mô tả |
| --- | --- |
| Course/context | TBD |
| Initial class learning profile | TBD |
| Assessment evidence | TBD |
| Diagnosis/profile update | TBD |
| Intervention artifact | TBD |
| HITL decision | TBD |
| Workflow trace summary | TBD |

Phân tích case study nên tập trung vào:

- workflow có nối assessment evidence -> diagnosis -> intervention -> reassessment plan không;
- artifact có đủ cụ thể để giáo viên CS dùng hoặc chỉnh ít không;
- domain material/tool/policy được cắm vào harness ở đâu;
- phần nào là logic subject-domain-agnostic và phần nào là cấu hình riêng cho CS.

## 5.7 Error analysis

Phân tích output thất bại, stratified theo benchmark, task và variant.

| Failure type | Count | Representative sample | Likely cause | Related component | Fix direction |
| --- | ---: | --- | --- | --- | --- |
| Off-Bloom / misalignment | TBD | TBD | TBD | pedagogical verifier / prompt | TBD |
| Schema invalid | TBD | TBD | TBD | schema validation / retry | TBD |
| Superficial learner-state adaptation | TBD | TBD | TBD | learner-state injection | TBD |
| Weak feedback/helpfulness | TBD | TBD | TBD | feedback policy | TBD |
| Poor trajectory/tool use | TBD | TBD | TBD | orchestration policy | TBD |
| Unsupported or over-specific domain assumption | TBD | TBD | TBD | adapter / context pack | TBD |

Mỗi ví dụ nên được rút gọn vừa đủ: input, lỗi chính, output fragment, trace liên quan và cách hệ thống nên sửa.

## 5.8 Threats to validity

**Internal validity**:

- Adapter mapping có thể làm thay đổi task surface của benchmark gốc nếu thiết kế không cẩn thận.
- Prompt và hyperparameter có thể ưu ái một variant; cần công bố prompt template, adapter mapping và retry policy.
- LLM-as-judge có thể bias theo vị trí, style hoặc độ dài output; protocol đã giảm rủi ro bằng blind judging, random order và human subset.

**External validity**:

- Benchmark reuse giúp giảm rủi ro benchmark tự xây, nhưng mỗi benchmark vẫn chỉ đại diện cho một phần của instructional design/adaptive tutoring.
- Computer Science case study minh hoạ feasibility trong một domain cụ thể, không chứng minh hiệu quả học tập hoặc khả năng tổng quát hoá sang mọi môn học.
- Prototype local-first chưa phản ánh deployment LMS quy mô lớn.

**Construct validity**:

- `adaptivity` và `feedback_helpfulness` đo chất lượng artifact/response theo rubric, chưa chứng minh learning outcome dài hạn.
- `trajectory_quality` phụ thuộc mapping giữa trace của harness và rubric của benchmark gốc.
- Learner state trong benchmark có thể là proxy từ student context, không phải learner model đầy đủ theo nghĩa ITS.

## 5.9 Discussion

Các điểm cần chốt trong phần thảo luận:

- Khi nào Adaptive Instructional Design Agent Harness hơn agent framework tổng quát?
- Learner-state injection tạo giá trị thực ở đâu, và khi nào chỉ làm output dài hơn?
- Schema, trace và HITL checkpoint giúp kiểm soát workflow ở mức nào?
- Benchmark adapters đủ để đánh giá harness-level contribution chưa, và còn thiếu loại benchmark nào?
- CS case study cho thấy gì về khả năng instantiate harness vào một subject domain cụ thể?
