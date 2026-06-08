# Chương 4 — Thiết kế thực nghiệm và protocol đánh giá

Chương này mô tả cách đánh giá **Adaptive Instructional Design Agent Harness**. Luận văn không xây một benchmark Computer Science mới. Thay vào đó, đánh giá định lượng được thực hiện bằng **benchmark adapters** tới các benchmark instructional design và adaptive tutoring/feedback hiện có; Computer Science được dùng riêng như một case study triển khai để minh hoạ hệ thống hoạt động trong một subject domain cụ thể.

## 4.1 Mục tiêu đánh giá

Luận văn đánh giá harness như một execution framework cho instructional design agents. Vì vậy, đánh giá không tập trung vào việc chứng minh LLM sinh văn bản hay hơn nói chung, mà kiểm tra liệu các thành phần harness như learner-state-aware memory, typed workflow graph, schema validation, verifier/checkpoint, retrieval/context injection, workflow trace và HITL governance có tạo khác biệt đo được khi chạy trên benchmark công khai hay không.

| Câu hỏi nghiên cứu | Claim cần kiểm tra | Bằng chứng chính |
| --- | --- | --- |
| **RQ1**: Trên các benchmark instructional-design hiện có, Adaptive Instructional Design Agent Harness cải thiện chất lượng thiết kế dạy học và workflow/trajectory như thế nào so với baseline? | Harness tạo artifact instructional design có chất lượng, alignment, actionability và trajectory tốt hơn LLM-only, ReAct/general-agent và theory-grounded prompting baselines trong cùng protocol adapter. | Controlled comparison qua ISD-Agent-Bench hoặc benchmark instructional-design tương đương, cùng model, cùng adapter schema, cùng judge/rubric khi khả thi. |
| **RQ2**: Learner-state-aware orchestration trong harness có cải thiện adaptivity, scaffolding, feedback helpfulness và misconception handling trên các benchmark adaptive tutoring/feedback hiện có không? | Khi có learner state hoặc student context, harness điều chỉnh feedback/intervention cụ thể hơn, đúng misconception hơn và ít tạo adaptation hình thức hơn baseline. | Paired/conditioned comparison trên benchmark adaptive tutoring/feedback, dùng metric adaptivity, scaffold quality, feedback helpfulness, misconception handling và non-harmful adaptation. |

Phạm vi kết luận là **harness-level evaluation**. Luận văn có thể kết luận harness cải thiện orchestration và artifact quality trong các benchmark đã chạy, nhưng không claim hệ thống tổng quát hoá chắc chắn sang mọi subject domain. Mỗi triển khai thực tế vẫn cần corpus, policy, tool và review phù hợp với domain đó.

## 4.2 Benchmark reuse strategy

Thay vì tạo benchmark riêng, luận văn dùng ba lớp đánh giá:

1. **Instructional-design benchmark adapter**: ánh xạ các scenario từ ISD-Agent-Bench hoặc benchmark instructional-design tương đương vào request schema của harness. Lớp này trả lời RQ1.
2. **Adaptive tutoring/feedback benchmark adapter**: ánh xạ student context, error state, misconception hoặc tutoring prompt từ benchmark adaptive tutoring/feedback vào learner-state/context schema của harness. Lớp này trả lời RQ2.
3. **Computer Science case study**: triển khai end-to-end một workflow trong domain CS để minh hoạ feasibility, artifact flow và trace. Lớp này không dùng cho statistical comparison.

Benchmark adapter không được thay đổi mục tiêu gốc của benchmark. Adapter chỉ chuẩn hoá input/output để harness và baseline có thể chạy cùng điều kiện:

```typescript
interface BenchmarkAdapter<TInput, TOutput> {
  benchmarkName: string
  mapInput(sample: TInput): HarnessRequest
  mapOutput(output: HarnessArtifact): TOutput
  scoringRubric: RubricSpec
  supportedMetrics: string[]
}
```

Nếu một benchmark không có trường learner state trực tiếp, adapter chỉ được dùng cho RQ1 hoặc dùng student context có sẵn như proxy cho learner state. Luận văn không bịa thêm state làm thay đổi bản chất sample gốc, trừ khi phần đó được tách thành analysis phụ và ghi rõ là synthetic.

## 4.3 Run manifest và điều kiện cố định

Mỗi lần chạy thực nghiệm tạo một `run_manifest` để đóng băng cấu hình. Các kết luận ở Chương 5 chỉ được diễn giải trong phạm vi cấu hình đã ghi nhận này.

| Nhóm cấu hình | Trường cần ghi nhận |
| --- | --- |
| Runtime | ngày chạy, commit hash của prototype, adapter version, seed/randomization key |
| Benchmark | benchmark name/version, split, license, số sample chạy, tiêu chí loại sample nếu có |
| Adapter | mapping version, output schema version, unsupported field log, normalization rules |
| Model generation | model/checkpoint, provider/local runtime, context length, temperature, top-p, max tokens |
| Baseline prompts | prompt template id, workflow template id, retry policy |
| Judge setup | judge model id, judge prompt version, rubric version, randomization order, human subset |
| Cost trace | số LLM call, tool call, token input/output, latency end-to-end |

Các biến thể hệ thống dùng cùng một manifest, trừ những thành phần là đối tượng so sánh trực tiếp như orchestration mode, learner-state injection, validation/repair hoặc retrieval policy.

## 4.4 Variants và baseline

Thực nghiệm dùng controlled comparison: cùng benchmark sample, cùng model, cùng decoding config, cùng adapter schema và cùng judge. Các variant chính:

| Variant | Nhóm | Cách chạy | Mục đích so sánh |
| --- | --- | --- | --- |
| **LLM-only** | baseline thấp | direct prompting theo benchmark input và output schema | đo lower bound khi không có harness |
| **Theory-grounded prompting** | baseline sư phạm đơn giản | prompt bổ sung ADDIE/Bloom/constructive alignment hoặc feedback rubric | kiểm tra liệu grounding bằng prompt đã đủ chưa |
| **ReAct/general-agent baseline** | baseline agentic | agent có planning/tool/retrieval cơ bản nhưng không có instructional workflow typed graph | so sánh với agent framework tổng quát |
| **Adaptive Instructional Design Agent Harness** | proposed | typed instructional workflow, learner-state-aware memory, schema validation, trace, HITL/checkpoint và adapter-specific tools | đo contribution chính |
| **Harness without learner-state injection** | ablation | cùng harness nhưng bỏ profile/context conditioning | cô lập tác động của learner-state-aware orchestration cho RQ2 |

Với các benchmark chỉ đo artifact cuối, `WorkflowTrace` được dùng như metric phụ. Với benchmark có multi-step/trajectory, trace của harness được map sang trajectory rubric của benchmark nếu mapping không làm thay đổi protocol gốc.

## 4.5 Metric và cách tính

### 4.5.1 Metric chung

| Metric | Cách tính | Áp dụng |
| --- | --- | --- |
| `schema_validity` | tỷ lệ output parse được và thỏa adapter output schema | tất cả |
| `quality_score` | điểm rubric chuẩn hoá 0-100 theo benchmark/judge | tất cả |
| `trajectory_quality` | điểm workflow/tool-use/step quality nếu benchmark hỗ trợ | RQ1 |
| `pedagogical_violation_rate` | tỷ lệ output vi phạm Bloom, constructive alignment, feedback policy hoặc safety constraint | RQ1/RQ2 |
| `latency_ms`, `llm_calls`, `tool_calls`, `token_usage` | lấy từ `WorkflowTrace` | tất cả |

### 4.5.2 Metric cho RQ1

RQ1 dùng các dimension tương thích với instructional-design literature và benchmark gốc:

| Dimension | Ý nghĩa |
| --- | --- |
| `lesson_plan_quality` | artifact có objective, activity, assessment, timing và sequencing hợp lý không |
| `constructive_alignment` | objective, activity và assessment có liên kết rõ không |
| `actionability` | giáo viên có thể dùng trực tiếp hoặc chỉnh ít không |
| `teacher_usability` | output có giảm effort chỉnh sửa và phù hợp workflow giáo viên không |
| `workflow_trace_quality` | harness có thực hiện các bước phân tích, thiết kế, kiểm tra và repair hợp lý không |

### 4.5.3 Metric cho RQ2

RQ2 không chỉ hỏi output có khác đi không, mà hỏi khác biệt đó có đúng hướng sư phạm không:

| Dimension | Ý nghĩa |
| --- | --- |
| `adaptivity` | output có dùng student/learner context để điều chỉnh hoạt động, feedback hoặc scaffold không |
| `scaffold_quality` | hỗ trợ vừa đủ, không bỏ mặc và không làm thay effort của người học |
| `feedback_helpfulness` | feedback cụ thể, đúng trọng tâm task/process và có bước sửa lỗi rõ ràng |
| `misconception_handling` | nhận diện và xử lý đúng misconception thay vì nhắc lại nhãn lỗi |
| `non_harmful_adaptation` | tránh hạ thấp kỳ vọng, định kiến hoặc feedback tiêu cực |

Với benchmark có pair no-state/with-state hoặc các prompt cùng lỗi nhưng khác learner context, báo cáo thêm:

```text
adaptation_delta_i =
  adaptivity_with_state_i - adaptivity_without_state_i
```

Một output chỉ được xem là learner-state adaptation có ý nghĩa nếu tăng `adaptivity` hoặc `scaffold_quality` mà không làm giảm correctness, alignment hoặc `non_harmful_adaptation`.

## 4.6 LLM-as-judge và human evaluation

Output gửi cho judge được chuẩn hoá theo cùng format và ẩn tên variant. Thứ tự output được randomize theo sample để giảm position bias. Judge chỉ nhận benchmark input, learner/student context nếu benchmark có, rubric chấm điểm và output đã chuẩn hoá.

Một human subset được chấm độc lập để kiểm tra độ tin cậy của judge. Nếu agreement thấp, Chương 5 chỉ dùng metric đó như bằng chứng phụ.

| Kiểm tra | Cách báo cáo |
| --- | --- |
| Ordinal rubric agreement | weighted kappa hoặc Krippendorff's alpha |
| Binary/pass-fail agreement | Cohen's kappa |
| LLM-human alignment | Spearman correlation hoặc mean absolute difference |
| Bias check | so sánh điểm theo vị trí output, độ dài output và tên variant đã ẩn |

## 4.7 Computer Science case study

Case study Computer Science không phải benchmark và không dùng để kết luận thống kê. Vai trò của nó là minh hoạ cách một harness subject-domain-agnostic được instantiate trong một domain cụ thể.

Một case study tối thiểu gồm:

1. Bối cảnh lớp/khoá học, ví dụ OOP Java hoặc CTDL&GT cho lớp fresher.
2. Một class learning profile ban đầu, gồm readiness, strength, weakness, misconception và evidence.
3. Một assessment hoặc submission/feedback event.
4. Diagnosis và learner-state update được đề xuất bởi harness.
5. Intervention plan hoặc lesson adjustment được tạo từ learner state.
6. Workflow trace thể hiện các node, validation/checkpoint và HITL decision.

Case study được phân tích định tính theo ba câu hỏi:

- Harness có nối được assessment evidence -> diagnosis -> intervention -> reassessment plan không?
- Artifact có đủ cụ thể để giáo viên triển khai trong bối cảnh CS không?
- Domain material/tool/policy được cắm vào harness ở đâu, và phần nào vẫn là logic subject-domain-agnostic?

## 4.8 Threats to validity

**Internal validity**: prompt và adapter có thể ưu ái một variant; cần công bố prompt template, adapter mapping và deviation log. LLM-as-judge có thể bias theo style hoặc độ dài output; protocol dùng blind judging, random order và human subset để giảm rủi ro.

**Construct validity**: benchmark instructional design/adaptive tutoring không đo trực tiếp learning outcome dài hạn. Các metric như adaptivity và feedback helpfulness đo chất lượng artifact hoặc response theo rubric, không chứng minh học viên học tốt hơn.

**External validity**: subject-domain-agnostic ở đây là claim về kiến trúc harness, không phải bằng chứng rằng hệ thống đã được kiểm chứng trên mọi môn học. Computer Science case study chỉ minh hoạ feasibility trong một domain cụ thể.

**Reproducibility**: nếu benchmark gốc không công bố đầy đủ prompt/rubric/judge, luận văn phải ghi rõ phần nào là reproduced, faithful reimplementation hoặc construct-only. Published leaderboard scores không được dùng trực tiếp làm baseline số học nếu khác model, split, prompt hoặc judge.
