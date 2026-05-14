# Chương 4 — Experimental Setup and Evaluation Protocol

## 4.1 Experimental Setup

**Thiết lập**:

- Hardware: ghi rõ CPU/RAM/GPU (chốt sau khi có máy).
- Model: pluggable — prototype dùng LLM local (ví dụ Gemma 4 E2B GGUF Q4_K_M) hoặc API; ghi rõ cấu hình cụ thể trong thiết lập thực nghiệm.
- Corpus:
  - **CNTT/lập trình**: tài liệu nội bộ giáo viên — slide bài giảng, đề thi, rubric chấm (tiếng Việt); giáo trình nội bộ CTDL&GT, OOP Java. Tài liệu soạn trong năm 2026. Chunk gán metadata Bloom thủ công/bán tự động.
  - Tổng ~2.000–4.000 chunk (corpus nội bộ, không có trong training data LLM → RAG có giá trị thật sự).
- **Lý do không dùng corpus public**: LLM đã được train trên tài liệu public → LLM-only baseline trông mạnh giả tạo → ∆ giữa các variant bé → không chứng minh được giá trị của harness.

## 4.2 Benchmark Dataset

Benchmark dự kiến gồm khoảng 140 sample trên case study CNTT/lập trình, chia theo hai use-case family.

**UC-ID family:**

| Task | N | Input | Ground truth | Cách tạo GT |
| --- | --- | --- | --- | --- |
| A1: Kế hoạch bài dạy (round-1, không có profile) | 25 | `{chủ đề, bloom_target, số buổi}` | Kế hoạch mẫu + checklist Bloom/constructive alignment | Tự soạn; peer review với 1 giáo viên CS |
| A2: Kế hoạch bài dạy (round-2, có StudentGroupProfile) | 25 | `{chủ đề, bloom_target, số buổi, student_group_profile}` | Kế hoạch mẫu phân hoá + checklist group-fit | Tự soạn từ cặp A1 tương ứng; bổ sung tiêu chí phân hoá đúng nhóm |

**UC-AS family:**

| Task | N | Input | Ground truth | Cách tạo GT |
| --- | --- | --- | --- | --- |
| B: Bài tập/đề kiểm tra | 40 | `{topic, difficulty, exercise_type}` (20 có + 20 không có `student_group_profile`) | Bài tập + test case + đáp án | Tự soạn; verify bằng `verify_solution()` |
| B-rubric: Công cụ đánh giá | 10 | `{topic, assessment_type, bloom_target}` | Rubric/ma trận đề mẫu + tiêu chí phân mức | Tự soạn theo chuẩn đánh giá năng lực |
| C: Chấm code + feedback | 40 | Bài nộp code lỗi (giả lập); 20 có kèm `student_group_profile` | Feedback chuẩn + misconception label | Tự viết dựa trên error_taxonomy IT |

## 4.3 Baselines and Comparison Protocol

Controlled comparison: **cùng LLM + cùng corpus + cùng queries**; chỉ thay đổi kiến trúc harness. Các variant được tổ chức theo spectrum từ "không có harness" đến "pedagogy-specific harness" để trả lời câu hỏi: harness thiết kế riêng cho sư phạm có mang lại giá trị vượt các kiến trúc harness tổng quát không? Mục tiêu không phải chứng minh typed graph, verifier hay pedagogical constraints là kỹ thuật mới, mà là chứng minh cấu hình tích hợp của harness phù hợp với bối cảnh sư phạm.

**Bảng đảm bảo fairness** — mọi variant giữ nguyên các yếu tố nền tảng, chỉ thay đổi cơ chế orchestration/verification:

| Yếu tố             | Giá trị cố định cho tất cả variant                                                                               |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Model**          | Cùng LLM checkpoint và cấu hình                                                                                   |
| **Corpus**         | Cùng vector index, cùng chunk, cùng embedding                                                                    |
| **Retriever**      | bge-m3 embedding + bge-reranker-v2-m3; top-k = 5                                                                 |
| **Tool access**    | LLM-only: không tool; Naive RAG: không tool; các variant agentic dùng cùng tool set nếu variant đó cho phép tool |
| **Temperature**    | 0.2 (generation); 0.0 (judge)                                                                                    |
| **Số lần retry**   | Tối đa 2 retry per task; các variant dùng cùng policy retry khi chức năng đó tồn tại                            |

_Tầng 1 — Comparison study_ (trả lời trực tiếp RQ1):

| Variant | Loại harness | Mô tả | Câu hỏi trả lời |
| --- | --- | --- | --- |
| **LLM-only** | Không có harness | LLM generate thẳng, không RAG, không agent | Lower bound — harness có cần thiết không? |
| **Naive RAG** | Harness tối giản | top-k retrieval + LLM generate; không orchestration | Retrieval đơn thuần đã đủ chưa? |
| **Generic ReAct ARAG** | General-purpose agent harness | 1 ReAct agent tự do, có retrieval/tool access, không pedagogical constraints | Harness tổng quát vs harness domain-specific |
| **Fixed MA-ARAG** | Structured agent harness | Pipeline nhiều role cố định: planner/generator/grader/reviewer; không IDA Loop, không memory, không plugin | Harness có cấu trúc cố định vs harness sư phạm |
| **Đề xuất − Domain Plugin** | Pedagogy harness (core only) | Pedagogy Agent Harness đầy đủ nhưng không load domain plugin — UC-ID + UC-AS + IDA Loop, không có code verifier | Đo delta của domain plugin |
| **Hệ thống đề xuất** | Pedagogy harness (đầy đủ) | Pedagogy Agent Harness với CNTT domain plugin và IDA Loop (Course Memory + Profile Synthesis + Context Injection) | Kiến trúc đề xuất — trả lời RQ1, RQ2 |

## 4.4 Metrics

**Metrics per task**:

| Task | Metric tự động | LLM-as-judge / human-subset rubric |
| --- | --- | --- |
| A1: Kế hoạch bài dạy round-1 | RAGAS faithfulness/context recall · Bloom violation rate · citation coverage · schema validity | Bloom alignment · constructive alignment · pedagogical coherence · completeness |
| A2: Kế hoạch bài dạy round-2 | Như A1 + **personalization delta** (so với A1 cùng cặp): % hoạt động được tag đúng nhóm · độ phân hoá giữa các nhóm | Group-fit: hoạt động có sát với điểm yếu của nhóm được mô tả trong StudentGroupProfile không? |
| B: Bài tập/đề kiểm tra | `verify_solution()` pass rate · schema validity · difficulty calibration delta (có vs không có profile) | Exercise clarity · difficulty calibration · rubric consistency · test case adequacy |
| B-rubric: Công cụ đánh giá | Schema validity · Bloom coverage · số tiêu chí phân mức | Rubric clarity · alignment với chuẩn đầu ra · tính khả thi đánh giá |
| C/C': Chấm bài + feedback | Misconception hit rate · feedback policy violation · citation coverage · **group-tone alignment** (feedback có nhấn đúng điểm yếu nhóm không, khi có profile) | Feedback helpfulness · explanation depth · pedagogical tone · correctness of misconception label |

Tất cả: latency end-to-end (ms) + số LLM calls + số tool calls + số retry + token usage.

## 4.5 LLM-as-Judge and Statistical Tests

**LLM-as-judge setup**: 2 judge độc lập (GPT-4o + Claude Sonnet); rubric gửi blind. Tính Cohen's κ — nếu κ < 0.6 thì thảo luận lại rubric.

**Kiểm định thống kê**:

- Test: **Wilcoxon signed-rank** (paired, non-parametric).
- So sánh: mọi cặp variant Tầng 1, per metric per task; tập trung chính vào `Hệ thống đề xuất` vs `Generic ReAct ARAG` và `Hệ thống đề xuất` vs `Fixed MA-ARAG`.
- Threshold: p < 0.05; report effect size (rank-biserial correlation r).
- Multiple comparison correction: Bonferroni hoặc Holm–Bonferroni.

## 4.6 Analysis Plan

**Phân tích kết quả**:

- Bảng chính: mean ± std per variant × task × metric, tách biệt theo case study.
- Significance matrix: heatmap p-value giữa các cặp.
- Plugin delta: đọc ∆ giữa `Đề xuất − Domain Plugin` và `Hệ thống đề xuất` để đánh giá mức độ đóng góp của code verifier.
- **RQ2 — Personalization delta analysis**: so sánh trực tiếp cặp (round-1, round-2) cho A1/A2; đo personalization delta tự động + LLM-as-judge group-fit; kiểm định Wilcoxon paired; diễn giải: IDA Loop có tạo phân hoá có chủ đích hay chỉ là biến động ngẫu nhiên?
- Error analysis: ≥ 30 output thất bại phân loại (hallucination, off-Bloom, unsupported citation, code không compile, feedback thiếu giải thích, phân hoá nhóm sai/ngược).
- Mechanism analysis: đọc log tool-call, verifier/repair, schema validity, violation rate và failure taxonomy để giải thích vì sao hệ thống đề xuất tốt/kém hơn từng baseline; không diễn giải như ablation định lượng của từng thành phần.
