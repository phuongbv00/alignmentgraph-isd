# Chương 4 — Thiết kế thực nghiệm và protocol đánh giá

Chương này mô tả protocol đánh giá được dùng để trả lời hai câu hỏi nghiên cứu đã nêu ở Chương 1. Mục tiêu của chương không chỉ là liệt kê các chỉ số sẽ đo, mà là cố định cách tạo benchmark, cách chạy các biến thể hệ thống, cách chấm điểm và cách kiểm soát bias để kết quả ở Chương 5 có thể tái lập.

## 4.1 Mục tiêu đánh giá

Luận văn đánh giá **Pedagogy Agent Harness** như một execution environment cho LLM trong bối cảnh sư phạm. Vì vậy, đánh giá không tập trung vào việc chứng minh LLM sinh văn bản hay hơn nói chung, mà kiểm tra liệu các thành phần harness như retrieval, typed workflow graph, verifier, memory/context injection và domain plugin có tạo khác biệt đo được trong các tác vụ thiết kế dạy học và đánh giá hay không.

| Câu hỏi nghiên cứu                                                                                            | Claim cần kiểm tra                                                                                                                                             | Bằng chứng chính                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **RQ1**: Pedagogy-specific harness có hiệu quả hơn các kiến trúc harness tổng quát trên UC-ID và UC-AS không? | Hệ thống đề xuất đạt chất lượng sư phạm, tính hợp lệ schema, grounding và verifier pass rate tốt hơn các baseline, với chi phí vận hành chấp nhận được.        | Controlled comparison trên cùng model, corpus, query set và output schema.                                                                 |
| **RQ2**: IDA Loop có tạo phân hoá có chủ đích theo nhóm học sinh không?                                       | Khi có `StudentGroupProfile`, output vòng 2 thay đổi theo đúng điểm mạnh, điểm yếu, readiness và misconception của nhóm, thay vì chỉ thêm nhãn nhóm hình thức. | Paired comparison giữa output không có profile và có profile; chấm `group-fit`, `differentiation specificity` và `profile evidence usage`. |

Phạm vi đánh giá là **technical and pedagogical artifact evaluation** trên case study CNTT/lập trình. Luận văn không đo learning outcome dài hạn trên lớp học thật; giới hạn này được thảo luận ở Chương 5.

## 4.2 Run manifest và điều kiện cố định

Mỗi lần chạy thực nghiệm tạo một `run_manifest` để đóng băng cấu hình. Các kết luận trong Chương 5 chỉ được diễn giải trong phạm vi cấu hình đã ghi nhận này.

| Nhóm cấu hình    | Trường cần ghi nhận                                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Runtime          | ngày chạy, commit hash của prototype, phiên bản benchmark, phiên bản corpus, seed/randomization key                         |
| Hardware         | CPU, RAM, GPU/VRAM nếu có, hệ điều hành                                                                                     |
| Model generation | model/checkpoint, provider/local runtime, quantization nếu dùng local model, context length, temperature, top-p, max tokens |
| Retrieval        | embedding model, reranker, chunking config, top-k, metadata filter policy                                                   |
| Baseline prompts | prompt template id, output schema version, retry policy                                                                     |
| Judge setup      | judge model id, judge prompt version, rubric version, randomization order                                                   |
| Cost trace       | số LLM call, số tool call, token input/output, latency end-to-end                                                           |

Các biến thể hệ thống dùng cùng một `run_manifest`, trừ những thành phần là đối tượng so sánh trực tiếp như orchestration, memory, verifier hoặc domain plugin.

## 4.3 Corpus và kiểm soát dữ liệu

Corpus trong thực nghiệm **có thể là tài liệu mở hoặc tài liệu nội bộ**. Điểm bắt buộc không phải là corpus phải kín, mà là corpus phải được kiểm soát nguồn, đóng băng phiên bản và gán metadata đủ để đánh giá retrieval/grounding một cách công bằng.

### 4.3.1 Tiêu chí chọn corpus

Một nguồn tài liệu được đưa vào corpus nếu thỏa các điều kiện sau:

1. Có nguồn gốc rõ ràng: URL/DOI/repository nếu là tài liệu mở, hoặc mã tài liệu/phiên bản nếu là tài liệu nội bộ.
2. Có liên quan trực tiếp tới case study CNTT/lập trình: CTDL&GT, OOP Java, bài tập lập trình, rubric, test case, feedback mẫu hoặc lỗi thường gặp.
3. Có thể trích dẫn ở mức đoạn/chunk để kiểm tra grounding.
4. Không chứa nguyên văn sample input/output của benchmark ở dạng có thể làm lộ đáp án.
5. Có license/quyền sử dụng phù hợp với phạm vi luận văn.

Nếu dùng corpus mở, luận văn **không claim** rằng LLM chưa từng thấy nội dung này trong training data. Khi đó, giá trị của RAG/harness được đánh giá qua khả năng dùng đúng nguồn, trích dẫn đúng chunk, tuân thủ metadata Bloom/difficulty và kết hợp tài liệu vào workflow sư phạm. Nếu dùng corpus nội bộ, luận văn báo cáo thêm lợi thế về privacy và local-first deployment, nhưng không lấy tính "không có trong training data" làm giả định bắt buộc.

### 4.3.2 Thành phần corpus

Corpus case study được tổ chức thành bốn nhóm nguồn:

| Nhóm nguồn            | Nội dung                                                      | Vai trò trong đánh giá                                                       |
| --------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Lecture material      | slide, giáo trình, ghi chú bài giảng về CTDL&GT và OOP Java   | Grounding cho lesson plan, learning objective, ví dụ và giải thích khái niệm |
| Assessment material   | đề bài, rubric, ma trận đề, thang điểm                        | Grounding cho UC-AS và kiểm tra rubric consistency                           |
| Programming artifacts | lời giải mẫu, test case, code lỗi mô phỏng, error taxonomy    | Kiểm tra domain verifier, chấm code và gán misconception                     |
| Pedagogical templates | mẫu kế hoạch bài dạy, mẫu hoạt động phân hoá, feedback policy | Kiểm tra constructive alignment và tone feedback                             |

Quy mô mục tiêu của corpus là 2.000-4.000 chunk sau xử lý. Con số cuối cùng được báo cáo trong `run_manifest`.

### 4.3.3 Chunking và metadata

Tài liệu được tách chunk theo đơn vị ngữ nghĩa, ưu tiên heading/section trong tài liệu gốc. Chunk quá dài được chia nhỏ, chunk quá ngắn được gộp với đoạn lân cận nếu cùng chủ đề.

| Thuộc tính     | Giá trị protocol                                                  |
| -------------- | ----------------------------------------------------------------- |
| Chunk size     | 300-700 token, overlap tối đa 80 token                            |
| Embedding      | cùng một embedding model cho mọi variant dùng retrieval           |
| Reranking      | cùng một reranker và `top-k = 5` cho mọi variant dùng retrieval   |
| Deduplication  | loại chunk trùng gần nhau bằng checksum hoặc similarity threshold |
| Frozen version | corpus sau chunking được gán `corpus_version` và checksum         |

Metadata tối thiểu của mỗi chunk:

```json
{
  "chunk_id": "corpus_v1:source:section:idx",
  "source_id": "string",
  "source_type": "lecture|assessment|code|rubric|template",
  "title": "string",
  "topic": "string",
  "subtopic": "string",
  "bloom_level": "remember|understand|apply|analyze|evaluate|create|unknown",
  "difficulty": "intro|basic|intermediate|advanced|unknown",
  "artifact_type": "concept|example|exercise|rubric|solution|feedback_policy",
  "language": "vi|en",
  "license_or_access": "open|institutional|internal",
  "version": "string",
  "span": "page/slide/line range"
}
```

Một mẫu 10% chunk được kiểm tra thủ công để ước lượng lỗi metadata. Nếu metadata Bloom/difficulty sai trên 15% mẫu kiểm tra, corpus phải được chỉnh trước khi chạy benchmark chính.

## 4.4 Benchmark dataset

Benchmark v1 gồm **140 sample** trên case study CNTT/lập trình. Mỗi sample là một input độc lập kèm reference package và rubric chấm điểm. Các sample được chia theo hai use-case family: UC-ID và UC-AS.

### 4.4.1 Schema của sample

Mỗi sample trong benchmark có cấu trúc:

```json
{
  "sample_id": "A1-STACK-001",
  "family": "UC-ID|UC-AS",
  "task": "lesson_plan|exercise_generation|rubric_generation|grading_feedback",
  "topic": "string",
  "bloom_target": "remember|understand|apply|analyze|evaluate|create",
  "difficulty": "basic|intermediate|advanced",
  "profile_condition": "no_profile|with_profile",
  "input_payload": {},
  "student_group_profile": null,
  "expected_output_schema": "schema_id",
  "reference_package": "reference_id",
  "scoring_rubric": "rubric_id",
  "source_refs": ["chunk_id"]
}
```

`reference_package` không nhất thiết là một đáp án duy nhất. Với lesson plan và rubric, reference package gồm checklist sư phạm, tiêu chí bắt buộc và ví dụ đạt chuẩn. Với exercise/code grading, reference package có đáp án, test case, expected misconception labels và policy feedback.

### 4.4.2 Phân bố sample

| Task                                     |   N | Profile condition           | Input chính                                    | Reference package                                     |
| ---------------------------------------- | --: | --------------------------- | ---------------------------------------------- | ----------------------------------------------------- |
| **A1: Lesson plan round-1**              |  25 | không có profile            | `{topic, bloom_target, duration, constraints}` | kế hoạch mẫu + checklist Bloom/constructive alignment |
| **A2: Lesson plan round-2**              |  25 | có `StudentGroupProfile`    | cùng topic với A1 + profile nhóm               | checklist group-fit + differentiated activities       |
| **B1: Exercise generation**              |  20 | không có profile            | `{topic, difficulty, exercise_type}`           | đề bài, đáp án, test case, rubric                     |
| **B2: Personalized exercise generation** |  20 | có `StudentGroupProfile`    | cùng schema B1 + profile nhóm                  | đáp án/test case + difficulty calibration theo nhóm   |
| **B3: Rubric/assessment tool**           |  10 | có/không profile tùy sample | `{topic, assessment_type, bloom_target}`       | rubric mẫu, ma trận đề, tiêu chí phân mức             |
| **C1: Code grading + feedback**          |  20 | không có profile            | submission lỗi + rubric + test case            | điểm, lỗi chính, feedback chuẩn, misconception label  |
| **C2: Personalized grading + feedback**  |  20 | có `StudentGroupProfile`    | cùng schema C1 + profile nhóm                  | feedback chuẩn có nhấn vào misconception/readiness    |

A1/A2 là các cặp paired sample: cùng chủ đề, cùng Bloom target và cùng ràng buộc thời lượng; A2 chỉ bổ sung profile nhóm. B1/B2 và C1/C2 cũng được thiết kế paired theo cùng topic/difficulty để đo tác động của profile.

### 4.4.3 Bao phủ chủ đề

| Nhóm chủ đề                               | A1/A2 pairs | B1/B2 samples | B3 samples | C1/C2 samples |
| ----------------------------------------- | ----------: | ------------: | ---------: | ------------: |
| Stack, queue, linked list                 |           4 |             6 |          1 |             6 |
| Recursion và iteration                    |           4 |             6 |          1 |             6 |
| Sorting, searching, complexity            |           4 |             6 |          1 |             6 |
| Tree, graph, traversal                    |           5 |             8 |          2 |             8 |
| OOP fundamentals trong Java               |           4 |             6 |          2 |             6 |
| Inheritance, polymorphism, interface      |           2 |             4 |          1 |             4 |
| Exception, collections, file I/O, testing |           2 |             4 |          2 |             4 |
| **Tổng**                                  |      **25** |        **40** |     **10** |        **40** |

### 4.4.4 StudentGroupProfile dùng trong benchmark

Các sample có profile dùng một trong bốn archetype nhóm học sinh. Profile là synthetic nhưng được xây dựng từ error taxonomy CNTT/lập trình và được reviewer kiểm tra tính hợp lý.

| Archetype                  | Readiness      | Misconception/nhu cầu chính                                                                   | Kỳ vọng output                                                       |
| -------------------------- | -------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| G1 - Foundation gap        | thấp           | nhầm cú pháp cơ bản, yếu prerequisite, cần scaffold                                           | hoạt động từng bước, ví dụ ngắn, feedback cụ thể và ít thuật ngữ khó |
| G2 - Misconception cluster | trung bình     | hiểu sai một khái niệm cụ thể như stack LIFO, recursion base case, inheritance vs composition | can thiệp trực tiếp vào misconception, bài tập phản ví dụ            |
| G3 - Application-ready     | trung bình-khá | hiểu khái niệm nhưng yếu phân rã bài toán và kiểm thử                                         | hoạt động áp dụng, test case gợi mở, feedback về chiến lược giải     |
| G4 - Advanced extension    | cao            | cần thử thách tối ưu, trade-off, edge case                                                    | hoạt động mở rộng, phân tích complexity, yêu cầu giải thích lựa chọn |

Mỗi profile gồm `readiness_level`, `known_misconceptions`, `strengths`, `recent_evidence`, `recommended_interventions`. Trong chấm điểm, judge chỉ thấy profile của sample, không thấy tên variant sinh output.

### 4.4.5 Tạo và kiểm tra reference package

Reference package được tạo theo ba bước:

1. Tác giả soạn bản nháp dựa trên corpus đã đóng băng và rubric sư phạm của luận văn.
2. Hai reviewer có nền tảng CNTT/sư phạm kiểm tra độc lập trên tối thiểu 30% sample; các sample còn lại được kiểm tra chéo theo checklist.
3. Bất đồng được adjudicate bằng cách sửa reference package, không sửa output của bất kỳ variant nào.

Với bài tập lập trình và chấm code, reference package bắt buộc có test case chạy được. Với lesson plan/rubric, reference package không yêu cầu output trùng câu chữ, mà dùng tiêu chí rubric để chấm mức đạt.

## 4.5 Baseline và protocol so sánh

Thực nghiệm dùng controlled comparison: **cùng model, cùng corpus, cùng query set, cùng output schema và cùng giới hạn retry**; chỉ thay đổi kiến trúc harness.

### 4.5.1 Các yếu tố cố định

| Yếu tố             | Giá trị cố định                                                                                 |
| ------------------ | ----------------------------------------------------------------------------------------------- |
| Model generation   | cùng model/checkpoint và decoding config cho tất cả variant                                     |
| Query set          | cùng 140 sample, thứ tự chạy được randomize bằng cùng seed                                      |
| Output schema      | tất cả variant được yêu cầu sinh cùng schema đích để đo schema validity                         |
| Corpus/index       | cùng corpus version, embedding index và reranker cho variant có retrieval                       |
| Retrieval top-k    | `top-k = 5`, cùng metadata filter nếu variant được phép dùng metadata                           |
| Temperature        | 0.2 cho generation; 0.0 cho judge                                                               |
| Retry              | tối đa 2 retry/task nếu variant có cơ chế validation/repair                                     |
| Human intervention | không có chỉnh sửa thủ công trong lúc chạy; HITL chỉ được log hoặc mô phỏng bằng policy cố định |

Không variant nào được nhận feedback từ kết quả chấm trong cùng batch benchmark. Điều này tránh việc hệ thống đề xuất được lợi nhờ tuning sau khi thấy output của baseline.

### 4.5.2 Capability matrix của các variant

| Variant                      | Retrieval | Tool use | Typed workflow                                     | Memory/profile injection            | Pedagogical verifier | Domain plugin/verifier           | Mục đích so sánh                               |
| ---------------------------- | --------- | -------- | -------------------------------------------------- | ----------------------------------- | -------------------- | -------------------------------- | ---------------------------------------------- |
| **LLM-only**                 | không     | không    | không                                              | không                               | không                | không                            | lower bound: model sinh trực tiếp              |
| **Naive RAG**                | có        | không    | không                                              | không                               | không                | không                            | đo lợi ích retrieval đơn thuần                 |
| **Generic ReAct ARAG**       | có        | có       | không, agent tự do ReAct                           | không có memory sư phạm             | không                | tool chung, không plugin sư phạm | harness tổng quát vs harness domain-specific   |
| **Fixed MA-ARAG**            | có        | có       | pipeline planner/generator/grader/reviewer cố định | không có IDA Loop/profile synthesis | generic review       | không domain plugin              | multi-agent có cấu trúc nhưng không sư phạm    |
| **Proposed w/o Domain Plugin** | có        | có       | UC-ID/UC-AS typed graph                            | có CourseContext/Profile injection  | có                   | không                            | đo core pedagogy harness khi thiếu plugin CNTT |
| **Full Proposed System**     | có        | có       | UC-ID/UC-AS typed graph                            | có CourseContext/Profile injection  | có                   | có CNTT plugin/verifier          | hệ thống đề xuất đầy đủ                        |

Prompt template của từng variant được lưu trong phụ lục hoặc repository kèm id phiên bản. Với các baseline không có workflow/harness, prompt vẫn được cung cấp task instruction và output schema để tránh đánh giá thấp baseline chỉ vì format.

### 4.5.3 Xử lý HITL trong benchmark

HITL là một cơ chế governance của hệ thống đề xuất, nhưng benchmark không cho phép giáo viên chỉnh output trong lúc chạy vì điều đó tạo lợi thế không công bằng so với baseline. Do đó:

- output được chấm là bản artifact sau automated validation/repair, trước mọi teacher edit;
- HITL checkpoint được log như một metric governance: có yêu cầu approve/edit/reject hay không, lý do là gì;
- với IDA Loop, profile dùng trong paired sample được lấy từ benchmark reference package, không phải từ chỉnh sửa thủ công trong lúc chạy;
- một experiment phụ có thể báo cáo chất lượng `ProfileSynthesis`, nhưng không trộn điểm đó vào comparison chính nếu có can thiệp của người.

## 4.6 Protocol chạy thực nghiệm

### 4.6.1 Headless benchmark runner

Benchmark được chạy hoàn toàn độc lập so với ứng dụng Electron, nhờ standalone deployment model đã mô tả ở mục 3.2.1. Entry point là `benchmark/runner.ts`, sử dụng `BenchmarkAdapter` để giao tiếp với harness core qua `HarnessTransport` interface:

```typescript
const adapter = new BenchmarkAdapter({ outputDir, runId })
const harness = new HarnessRuntime(adapter, runConfig)

for (const sample of fixtures) {
  adapter.injectRequest(sample.input_payload)
  const trace = await harness.run()
  results.push({ sample_id: sample.sample_id, trace, output: adapter.lastOutput })
}
```

`BenchmarkAdapter` không gửi streaming token về UI; nó ghi raw output và `WorkflowTrace` ra file JSON sau mỗi sample. Mỗi variant trong bảng 4.5.2 được khởi tạo bằng cách thay `runConfig` — model, retrieval policy, orchestration mode, memory injection flag — mà không thay code trong harness core. Output được lưu theo convention `results/{run_id}/{variant}/{sample_id}.json`.

Thiết kế này đảm bảo điều kiện controlled comparison: cùng fixture, cùng code path qua schema validation và verifier, chỉ khác cấu hình kiến trúc ở `runConfig`. Kết quả có thể đối chiếu theo `pair_id` cho các task A1/A2, B1/B2 và C1/C2 mà không cần can thiệp thủ công vào quá trình chạy.

### 4.6.2 Quy trình chạy từng sample

1. Load `input_payload`, profile condition và output schema.
2. Chạy cùng sample qua sáu variant theo thứ tự randomize.
3. Ghi raw output, normalized output, trace, retrieved chunks, verifier result, retry count, latency và token usage.
4. Validate output schema bằng cùng validator.
5. Với task có code/test case, chạy verifier trong sandbox.
6. Đóng gói output cho judge: ẩn tên variant, chuẩn hoá format trình bày, randomize thứ tự.
7. Chấm bằng automatic metrics, LLM-as-judge và human subset.

Đối với các task paired A1/A2, B1/B2 và C1/C2, kết quả được lưu theo `pair_id` để dùng kiểm định paired. Nếu một variant không sinh được output hợp lệ sau tối đa 2 retry, sample đó được tính là failure cho schema validity và nhận điểm chất lượng tối thiểu cho các metric phụ thuộc output.

## 4.7 Metric và cách tính

### 4.7.1 Metric chung

| Metric                                   | Cách tính                                                                                   | Áp dụng     |
| ---------------------------------------- | ------------------------------------------------------------------------------------------- | ----------- |
| `schema_validity`                        | tỷ lệ output parse được và thỏa JSON Schema bắt buộc                                        | tất cả task |
| `quality_score`                          | trung bình có trọng số các rubric dimension, chuẩn hoá 0-100                                | tất cả task |
| `citation_coverage`                      | tỷ lệ claim cần grounding có citation hợp lệ tới chunk liên quan                            | A1, A2, B3  |
| `unsupported_citation_rate`              | tỷ lệ citation không hỗ trợ claim được trích                                                | A1, A2, B3  |
| `pedagogical_violation_rate`             | tỷ lệ output vi phạm Bloom, constructive alignment, rubric consistency hoặc feedback policy | tất cả task |
| `latency_ms`                             | thời gian end-to-end từ input tới final artifact                                            | tất cả task |
| `llm_calls`, `tool_calls`, `token_usage` | lấy từ `WorkflowTrace`/runtime log                                                          | tất cả task |

`quality_score` không thay thế các metric thành phần. Chương 5 báo cáo cả điểm tổng hợp và các dimension chính để tránh che giấu trade-off.

### 4.7.2 Metric cho UC-ID

| Dimension              | Thang điểm | Mô tả                                                                            |
| ---------------------- | ---------- | -------------------------------------------------------------------------------- |
| Bloom alignment        | 0-3        | mục tiêu, hoạt động và assessment có khớp Bloom target không                     |
| Constructive alignment | 0-3        | learning objectives, teaching activities và assessment có liên kết rõ không      |
| Pedagogical coherence  | 0-3        | trình tự dạy học có hợp lý, khả thi, tránh nhảy bước không                       |
| Completeness           | 0-3        | có đủ mục tiêu, hoạt động, thời lượng, assessment, citation nếu yêu cầu          |
| Feasibility            | 0-3        | giáo viên có thể triển khai trong thời lượng và điều kiện lớp học giả định không |

### 4.7.3 Metric cho UC-AS

| Task                      | Metric tự động                                                                 | Rubric/judge dimension                                                        |
| ------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| B1/B2 Exercise generation | `verify_solution_pass_rate`, `test_case_validity`, `schema_validity`           | clarity, difficulty calibration, coverage of edge cases, rubric consistency   |
| B3 Rubric/assessment tool | `bloom_coverage`, `criteria_count`, `schema_validity`                          | rubric clarity, level discrimination, alignment với chuẩn đầu ra, feasibility |
| C1/C2 Grading + feedback  | `misconception_label_f1`, `feedback_policy_violation_rate`, `grading_accuracy` | feedback helpfulness, explanation depth, correctness, pedagogical tone        |

`grading_accuracy` được tính bằng độ lệch tuyệt đối giữa điểm hệ thống và điểm reference, sau đó chuẩn hoá về 0-100. `misconception_label_f1` so sánh nhãn hệ thống với expected labels trong reference package.

### 4.7.4 Personalization delta cho RQ2

RQ2 không chỉ hỏi output có khác nhau hay không, mà hỏi khác biệt đó có đúng hướng sư phạm không. Vì vậy, mỗi cặp no-profile/profile được chấm bằng các dimension sau:

| Dimension                     | Thang điểm | Câu hỏi chấm                                                                 |
| ----------------------------- | ---------- | ---------------------------------------------------------------------------- |
| `group_fit`                   | 0-3        | output có phù hợp với readiness, strength và weakness của nhóm không         |
| `misconception_alignment`     | 0-3        | hoạt động/feedback có xử lý đúng misconception trong profile không           |
| `differentiation_specificity` | 0-3        | khác biệt giữa các nhóm có cụ thể và triển khai được không, hay chỉ đổi nhãn |
| `profile_evidence_usage`      | 0-3        | quyết định sư phạm có dựa trên evidence trong profile/diagnosis không        |
| `non_harmful_adaptation`      | 0-3        | cá nhân hoá có tránh hạ thấp kỳ vọng, định kiến hoặc feedback tiêu cực không |

Với mỗi pair `i`, tính:

```text
personalization_delta_i =
  group_fit_with_profile_i - group_fit_no_profile_i
```

và báo cáo thêm:

```text
specificity_delta_i =
  differentiation_specificity_with_profile_i
  - differentiation_specificity_no_profile_i
```

Một output vòng 2 chỉ được xem là cá nhân hoá có ý nghĩa nếu tăng `group_fit` hoặc `specificity` mà không làm giảm `Bloom alignment`, `correctness` hoặc `non_harmful_adaptation`.

## 4.8 LLM-as-judge và human evaluation

### 4.8.1 Blind judging

Output gửi cho judge được chuẩn hoá theo cùng format và ẩn hoàn toàn tên variant. Thứ tự output được randomize theo sample để giảm position bias. Judge chỉ nhận:

- task input;
- profile nếu sample thuộc condition có profile;
- rubric chấm điểm;
- output đã ẩn tên variant;
- retrieved citations nếu metric cần kiểm tra grounding.

Judge không nhận thông tin variant nào là hệ thống đề xuất, baseline nào dùng RAG, hay output nào đến từ vòng 1/vòng 2.

### 4.8.2 LLM-as-judge setup

Hai judge model độc lập được dùng cho mỗi output. Judge chạy ở temperature 0.0 với cùng rubric. Nếu hai judge lệch quá 1 điểm trên bất kỳ dimension 0-3 nào, sample đó được đưa vào hàng đợi adjudication.

Báo cáo độ nhất quán gồm:

- Cohen's kappa cho các nhãn rời rạc như pass/fail, violation/no violation;
- weighted kappa hoặc Krippendorff's alpha cho thang ordinal 0-3;
- tương quan Spearman giữa LLM judge và human subset.

Nếu agreement dưới 0.6 ở metric chính, Chương 5 không dùng metric đó như bằng chứng kết luận chính; metric chỉ được báo cáo như tín hiệu phụ và cần thảo luận threat to validity.

### 4.8.3 Human subset

Tối thiểu 20% output, stratified theo task và variant, được chấm bởi reviewer người. Với 140 sample và 6 variant, subset tối thiểu là 168 output. Nếu nguồn lực hạn chế, luận văn phải báo cáo rõ subset thực tế và xem đây là limitation.

Human reviewer chấm blind theo cùng rubric với LLM judge. Điểm human subset dùng để:

1. kiểm tra LLM-as-judge có tương quan đủ với đánh giá người không;
2. phát hiện bias style/verbosity của judge;
3. cung cấp ví dụ định tính cho phân tích lỗi.

## 4.9 Kiểm định thống kê

Vì các variant chạy trên cùng sample, phân tích chính dùng paired tests.

| Loại metric                                               | Kiểm định chính                               | Effect size                             |
| --------------------------------------------------------- | --------------------------------------------- | --------------------------------------- |
| Ordinal/score 0-3 hoặc quality score không giả định chuẩn | Wilcoxon signed-rank                          | rank-biserial correlation               |
| Binary pass/fail như schema valid, verifier pass          | McNemar test                                  | odds ratio hoặc paired proportion delta |
| Count metric như số retry/tool call                       | Wilcoxon signed-rank hoặc paired bootstrap CI | median delta                            |
| Latency/token usage                                       | paired bootstrap CI + Wilcoxon                | median/mean delta                       |

So sánh chính cho RQ1:

1. Full Proposed System vs Generic ReAct ARAG.
2. Full Proposed System vs Fixed MA-ARAG.
3. Full Proposed System vs Proposed - Domain Plugin, để đo plugin delta trên task CNTT.

So sánh chính cho RQ2:

1. With-profile vs no-profile trong cùng pair A1/A2.
2. With-profile vs no-profile trong cùng pair B1/B2 và C1/C2.

Các so sánh phụ dùng Holm-Bonferroni correction. Chương 5 báo cáo p-value, effect size và confidence interval; không kết luận chỉ dựa vào p-value nếu effect size nhỏ hoặc chi phí vận hành tăng quá lớn.

## 4.10 Phân tích lỗi và cơ chế

Sau khi chấm định lượng, luận văn phân tích tối thiểu 30 output thất bại, stratified theo task và variant. Mỗi lỗi được gán một hoặc nhiều nhãn:

- hallucination hoặc unsupported citation;
- retrieval miss hoặc chunk metadata sai;
- off-Bloom hoặc sai constructive alignment;
- schema invalid hoặc thiếu field bắt buộc;
- code không compile, test case sai hoặc lời giải không khớp verifier;
- feedback thiếu giải thích, sai misconception label hoặc tone không phù hợp;
- cá nhân hoá hình thức, sai nhóm, ngược profile hoặc có nguy cơ định kiến;
- tool-call sai thứ tự, sai argument hoặc retry không sửa được lỗi.

Với mỗi nhóm lỗi, Chương 5 báo cáo ví dụ rút gọn, nguyên nhân khả dĩ, thành phần harness liên quan và hướng cải thiện. Phân tích cơ chế dựa trên trace như retrieved chunks, verifier result, retry count, schema validation và profile injection. Luận văn không diễn giải trace như ablation định lượng của từng thành phần nếu không có thiết kế ablation riêng.

## 4.11 Tiêu chí diễn giải kết quả

RQ1 được xem là có bằng chứng ủng hộ nếu Full Proposed System cải thiện có ý nghĩa trên các metric chất lượng chính so với Generic ReAct ARAG và Fixed MA-ARAG, đồng thời không tạo trade-off chi phí/latency vượt mức làm hệ thống khó sử dụng trong bối cảnh giáo viên.

RQ2 được xem là có bằng chứng ủng hộ nếu condition có `StudentGroupProfile` tăng `group_fit` và `differentiation_specificity` trên paired sample, trong khi không làm giảm correctness, Bloom alignment hoặc non-harmful adaptation.

Nếu kết quả chỉ cải thiện ở schema/verifier nhưng không cải thiện rubric sư phạm, luận văn chỉ được kết luận rằng harness giúp tăng tính kiểm soát kỹ thuật, chưa đủ bằng chứng về giá trị sư phạm. Nếu kết quả cá nhân hoá chỉ thể hiện ở việc nhắc lại tên nhóm hoặc thêm nhãn nhóm, luận văn phải xem đó là failure mode của IDA Loop.
