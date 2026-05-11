# Chương 4 — Experimental Setup and Evaluation Protocol

## 4.1 Experimental Setup

**Thiết lập**:

- Hardware: ghi rõ CPU/RAM/GPU (chốt sau khi có máy).
- Model: pluggable — prototype dùng LLM local (ví dụ Gemma 4 E2B GGUF Q4_K_M) hoặc API; ghi rõ cấu hình cụ thể trong thiết lập thực nghiệm.
- Corpus:
  - **CNTT/lập trình**: tài liệu nội bộ giáo viên — slide bài giảng, đề thi, rubric chấm (tiếng Việt); giáo trình nội bộ CTDL&GT, OOP Java. Tài liệu soạn sau 2024. Chunk gán metadata Bloom thủ công/bán tự động.
  - **Toán**: slide, bài tập mẫu, lời giải mẫu của 1–2 giáo viên cộng tác (tiếng Việt). Chunk gán metadata topic, Bloom level, difficulty.
  - Tổng ~4.000–8.000 chunk (corpus nội bộ, không có trong training data LLM → RAG có giá trị thật sự).
- **Lý do không dùng corpus public**: LLM đã được train trên tài liệu public → LLM-only baseline trông mạnh giả tạo → ∆ giữa các variant bé → không chứng minh được giá trị của harness.

## 4.2 Benchmark Dataset

Benchmark dự kiến gồm khoảng 180 sample, chia theo hai case study và hai use-case family.

*Case study CNTT/lập trình (140 sample):*

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

*Case study Toán (60 sample):*

**UC-ID family:**

| Task | N | Input | Ground truth | Cách tạo GT |
| --- | --- | --- | --- | --- |
| A1': Kế hoạch bài dạy Toán (round-1) | 10 | `{chủ đề, bloom_target, số buổi}` | Kế hoạch mẫu + checklist | Tự soạn; peer review với 1 giáo viên Toán |
| A2': Kế hoạch bài dạy Toán (round-2) | 10 | `{chủ đề, bloom_target, số buổi, student_group_profile}` | Kế hoạch mẫu phân hoá | Tự soạn từ cặp A1' tương ứng |

**UC-AS family:**

| Task | N | Input | Ground truth | Cách tạo GT |
| --- | --- | --- | --- | --- |
| B': Bài tập Toán | 25 | `{topic, difficulty, exercise_type}` (12 có + 13 không có `student_group_profile`) | Bài tập + lời giải tham chiếu + hint | Tự soạn; verify bằng SymPy hoặc thủ công |
| C': Chấm lời giải Toán | 15 | Lời giải Toán lỗi (giả lập); 8 có kèm `student_group_profile` | Feedback chuẩn + error taxonomy label | Tự viết dựa trên math error taxonomy |

## 4.3 Baselines and Comparison Protocol

Controlled comparison: **cùng LLM + cùng corpus + cùng queries**; chỉ thay đổi kiến trúc hệ thống. Mục tiêu là đánh giá giá trị của harness trong bối cảnh sư phạm, không phải chứng minh typed graph, verifier hay pedagogical constraints là kỹ thuật mới độc lập.

**Bảng đảm bảo fairness** — mọi variant giữ nguyên các yếu tố nền tảng, chỉ thay đổi cơ chế orchestration/verification:

| Yếu tố             | Giá trị cố định cho tất cả variant                                                                               |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Model**          | Cùng LLM checkpoint và cấu hình                                                                                   |
| **Corpus**         | Cùng vector index, cùng chunk, cùng embedding                                                                    |
| **Retriever**      | bge-m3 embedding + bge-reranker-v2-m3; top-k = 5                                                                 |
| **Tool access**    | LLM-only: không tool; Naive RAG: không tool; các variant agentic dùng cùng tool set nếu variant đó cho phép tool |
| **Temperature**    | 0.2 (generation); 0.0 (judge)                                                                                    |
| **Số lần retry**   | Tối đa 2 retry per task; riêng ablation sẽ bật/tắt targeted repair                                               |

_Tầng 1 — Comparison study_ (trả lời trực tiếp RQ1):

| Variant                | Mô tả                                                                                                                        | Mục đích                                    |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **LLM-only**           | Không RAG, không agent — LLM generate thẳng                                                                                   | Baseline thấp nhất; đo giá trị của RAG      |
| **Naive RAG**          | top-k vector search + LLM generate; không agent loop                                                                         | Đo giá trị của retrieval                    |
| **Generic ReAct ARAG** | 1 ReAct agent tự do, có retrieval/tool access, không typed graph                                                             | Baseline giống agent platform tổng quát     |
| **Fixed MA-ARAG**      | Pipeline nhiều role cố định: planner/generator/grader/reviewer                                                               | Kiểm tra liệu chia role thủ công đã đủ chưa |
| **Đề xuất − Domain Plugin** | Pedagogy Agent Harness đầy đủ nhưng không load domain plugin (null-plugin) — core UC-ID + UC-AS + IDA Loop hoạt động, không có code verifier / SymPy | Trả lời RQ2 null-plugin contract; đo delta khi thêm plugin |
| **Hệ thống đề xuất**   | Pedagogy Agent Harness đầy đủ với domain plugin (CNTT hoặc Toán tùy case study) và IDA Loop (Course Memory + Profile Synthesis + Context Injection) | Kiến trúc tích hợp đề xuất — trả lời RQ1, RQ3 |

_Tầng 2 — Ablation study_ (giải thích phần nào trong harness tạo ra khác biệt):

| Variant                                            | Thành phần bỏ/thay đổi                                               | Câu hỏi ablation                                                                                 |
| -------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Đề xuất − Typed schemas**                        | Node vẫn theo graph nhưng input/output free-form                     | Schema có giúp giảm lỗi định dạng và hallucination không?                                        |
| **Đề xuất − Verifier**                             | Không chạy verifier/citation/Bloom checks trước output               | Verifier đóng góp bao nhiêu vào correctness?                                                     |
| **Đề xuất − Targeted Repair**                      | Có verifier nhưng retry regenerate toàn bộ output                    | Sửa đúng component lỗi có tốt hơn retry toàn cục không?                                          |
| **Đề xuất − Pedagogical Constraints**              | Bỏ Bloom/rubric/misconception/feedback checks                        | Constraint sư phạm cải thiện chất lượng giáo dục bao nhiêu?                                      |
| **Đề xuất − Teacher-controlled mutation feedback** | Teacher edit/reject reason không được đưa lại thành constraint retry | Phản hồi của giáo viên có giảm lỗi lặp lại và số lần reject không?                               |

## 4.4 Domain Extensibility Protocol

Phân tích interface compliance: so sánh CNTT extension và Toán extension trên các dimension:
- Interface completeness: cả hai implement đủ các khai báo bắt buộc của Pedagogy Domain Extension không?
- Core modification: có phần nào của core phải sửa để accommodate extension thứ hai không?
- Verifier adaptability: verifier optional/pluggable hoạt động đúng (code verifier cho IT, SymPy/structural cho Toán)?

## 4.5 Metrics

**Metrics per task**:

| Task | Metric tự động | LLM-as-judge / human-subset rubric |
| --- | --- | --- |
| A1/A1': Kế hoạch bài dạy round-1 | RAGAS faithfulness/context recall · Bloom violation rate · citation coverage · schema validity | Bloom alignment · constructive alignment · pedagogical coherence · completeness |
| A2/A2': Kế hoạch bài dạy round-2 | Như A1 + **personalization delta** (so với A1 cùng cặp): % hoạt động được tag đúng nhóm · độ phân hoá giữa các nhóm | Group-fit: hoạt động có sát với điểm yếu của nhóm được mô tả trong StudentGroupProfile không? |
| B/B': Bài tập/đề kiểm tra | `verify_solution()` pass rate (IT) · SymPy correctness rate (Toán) · schema validity · difficulty calibration delta (có vs không có profile) | Exercise clarity · difficulty calibration · rubric consistency · test case adequacy |
| B-rubric: Công cụ đánh giá | Schema validity · Bloom coverage · số tiêu chí phân mức | Rubric clarity · alignment với chuẩn đầu ra · tính khả thi đánh giá |
| C/C': Chấm bài + feedback | Misconception hit rate · feedback policy violation · citation coverage · **group-tone alignment** (feedback có nhấn đúng điểm yếu nhóm không, khi có profile) | Feedback helpfulness · explanation depth · pedagogical tone · correctness of misconception label |

Tất cả: latency end-to-end (ms) + số LLM calls + số tool calls + số retry + token usage.

## 4.6 LLM-as-Judge and Statistical Tests

**LLM-as-judge setup**: 2 judge độc lập (GPT-4o + Claude Sonnet); rubric gửi blind. Tính Cohen's κ — nếu κ < 0.6 thì thảo luận lại rubric.

**Kiểm định thống kê**:

- Test: **Wilcoxon signed-rank** (paired, non-parametric).
- So sánh: mọi cặp variant Tầng 1, per metric per task; tập trung chính vào `Hệ thống đề xuất` vs `Generic ReAct ARAG` và `Hệ thống đề xuất` vs `Fixed MA-ARAG`.
- Threshold: p < 0.05; report effect size (rank-biserial correlation r).
- Multiple comparison correction: Bonferroni hoặc Holm–Bonferroni.

## 4.7 Analysis Plan

**Phân tích kết quả**:

- Bảng chính: mean ± std per variant × task × metric, tách biệt theo case study.
- Significance matrix: heatmap p-value giữa các cặp.
- Per-domain insight: so sánh pattern giữa IT và Toán — harness có lợi thế khác nhau không giữa domain có plugin verifier và domain không có? (đọc từ ∆ giữa `Đề xuất − Domain Plugin` và `Hệ thống đề xuất`)
- **RQ3 — Personalization delta analysis**: so sánh trực tiếp cặp (round-1, round-2) cho A/A'; đo personalization delta tự động + LLM-as-judge group-fit; kiểm định Wilcoxon paired; diễn giải: IDA Loop có tạo phân hoá có chủ đích hay chỉ là biến động ngẫu nhiên?
- Error analysis: ≥ 30 output thất bại phân loại (hallucination, off-Bloom, unsupported citation, code không compile, lời giải Toán sai bước, feedback thiếu giải thích, phân hoá nhóm sai/ngược).
- Ablation contribution chart: bar chart ∆ score khi bỏ typed schemas, verifier, targeted repair, pedagogical constraints, Course Memory/Context Injection; diễn giải như đóng góp thực nghiệm của từng thành phần, không diễn giải như novelty thuật toán.
- RQ2 analysis: bảng interface compliance IT extension vs Toán extension; test case null-plugin (core hoạt động khi plugin = null); ghi nhận điểm core phải thích nghi (nếu có) và giải thích.
