# Đánh giá hệ thống — Chương 5

## 5.1 Thực nghiệm & Đánh giá

**Thiết lập**:

- Hardware: ghi rõ CPU/RAM/GPU (chốt sau khi có máy).
- Model: pluggable — prototype dùng LLM local (ví dụ Gemma 4 E2B GGUF Q4_K_M) hoặc API; ghi rõ cấu hình cụ thể trong thiết lập thực nghiệm.
- Corpus:
  - **CNTT/lập trình**: tài liệu nội bộ giáo viên — slide bài giảng, đề thi, rubric chấm (tiếng Việt); giáo trình nội bộ CTDL&GT, OOP Java. Tài liệu soạn sau 2024. Chunk gán metadata Bloom thủ công/bán tự động.
  - **Toán**: slide, bài tập mẫu, lời giải mẫu của 1–2 giáo viên cộng tác (tiếng Việt). Chunk gán metadata topic, Bloom level, difficulty.
  - Tổng ~4.000–8.000 chunk (corpus nội bộ, không có trong training data LLM → RAG có giá trị thật sự).
- **Lý do không dùng corpus public**: LLM đã được train trên tài liệu public → LLM-only baseline trông mạnh giả tạo → ∆ giữa các variant bé → không chứng minh được giá trị của harness.

**Dataset benchmark** (~180 sample):

*Case study CNTT/lập trình (130 sample):*

| Task         | N   | Input                                | Ground truth                         | Cách tạo GT                              |
| ------------ | --- | ------------------------------------ | ------------------------------------ | ---------------------------------------- |
| A: Giáo án   | 50  | `{chủ đề, bloom_target, số buổi}`    | Giáo án mẫu + checklist tiêu chí     | Tự soạn; peer review với 1 giáo viên CS  |
| B: Bài tập   | 50  | `{topic, difficulty, exercise_type}` | Bài tập + test case + đáp án         | Tự soạn; verify bằng `verify_solution()` |
| C: Chấm code | 30  | Bài nộp code lỗi (giả lập)           | Feedback chuẩn + misconception label | Tự viết dựa trên error_taxonomy          |

*Case study Toán (50 sample):*

| Task              | N   | Input                                     | Ground truth                              | Cách tạo GT                                 |
| ----------------- | --- | ----------------------------------------- | ----------------------------------------- | ------------------------------------------- |
| B': Bài tập Toán  | 30  | `{topic, difficulty, exercise_type}`      | Bài tập + lời giải tham chiếu + hint      | Tự soạn; verify bằng SymPy hoặc thủ công    |
| C': Chấm lời giải | 20  | Lời giải Toán lỗi (giả lập)               | Feedback chuẩn + error taxonomy label     | Tự viết dựa trên math error taxonomy        |

### Thiết kế thực nghiệm cho EQ1

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

_Tầng 1 — Comparison study_ (trả lời trực tiếp EQ1):

| Variant                | Mô tả                                                                                                                        | Mục đích                                    |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| **LLM-only**           | Không RAG, không agent — LLM generate thẳng                                                                                   | Baseline thấp nhất; đo giá trị của RAG      |
| **Naive RAG**          | top-k vector search + LLM generate; không agent loop                                                                         | Đo giá trị của retrieval                    |
| **Generic ReAct ARAG** | 1 ReAct agent tự do, có retrieval/tool access, không typed graph                                                             | Baseline giống agent platform tổng quát     |
| **Fixed MA-ARAG**      | Pipeline nhiều role cố định: planner/generator/grader/reviewer                                                               | Kiểm tra liệu chia role thủ công đã đủ chưa |
| **Hệ thống đề xuất**   | Pedagogy Agent Harness với Pedagogy-Constrained Orchestration và domain extension (CNTT hoặc Toán tùy case study)            | Kiến trúc tích hợp đề xuất                  |

_Tầng 2 — Ablation study_ (giải thích phần nào trong harness tạo ra khác biệt):

| Variant                                            | Thành phần bỏ/thay đổi                                               | Câu hỏi ablation                                                                                 |
| -------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Đề xuất − Typed schemas**                        | Node vẫn theo graph nhưng input/output free-form                     | Schema có giúp giảm lỗi định dạng và hallucination không?                                        |
| **Đề xuất − Verifier**                             | Không chạy verifier/citation/Bloom checks trước output               | Verifier đóng góp bao nhiêu vào correctness?                                                     |
| **Đề xuất − Targeted Repair**                      | Có verifier nhưng retry regenerate toàn bộ output                    | Sửa đúng component lỗi có tốt hơn retry toàn cục không?                                          |
| **Đề xuất − Pedagogical Constraints**              | Bỏ Bloom/rubric/misconception/feedback checks                        | Constraint sư phạm cải thiện chất lượng giáo dục bao nhiêu?                                      |
| **Đề xuất − Teacher-controlled mutation feedback** | Teacher edit/reject reason không được đưa lại thành constraint retry | Phản hồi của giáo viên có giảm lỗi lặp lại và số lần reject không?                               |

### Thiết kế thực nghiệm cho EQ2

Phân tích interface compliance: so sánh CNTT extension và Toán extension trên các dimension:
- Interface completeness: cả hai implement đủ các khai báo bắt buộc của Pedagogy Domain Extension không?
- Core modification: có phần nào của core phải sửa để accommodate extension thứ hai không?
- Verifier adaptability: verifier optional/pluggable hoạt động đúng (code verifier cho IT, SymPy/structural cho Toán)?

**Metrics per task**:

| Task              | Metric tự động                                                                                         | LLM-as-judge / human-subset rubric                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| A: Giáo án (IT)   | RAGAS faithfulness/context recall · Bloom violation rate · citation coverage · schema validity         | Bloom alignment · constructive alignment · pedagogical coherence · completeness                  |
| B: Bài tập IT     | `verify_solution()` pass rate · test coverage proxy · compile/runtime error rate · schema validity     | Exercise clarity · difficulty calibration · rubric consistency · test case adequacy              |
| C: Chấm code      | pytest pass-rate precision · misconception hit rate · feedback policy violation · citation coverage     | Feedback helpfulness · explanation depth · pedagogical tone · correctness of misconception label |
| B': Bài tập Toán  | SymPy correctness rate (where applicable) · structural completeness · schema validity                  | Exercise clarity · mathematical correctness · difficulty calibration                             |
| C': Chấm lời giải | Math error taxonomy hit rate · feedback policy violation · structural completeness                      | Feedback helpfulness · mathematical explanation accuracy · pedagogical tone                      |

Tất cả: latency end-to-end (ms) + số LLM calls + số tool calls + số retry + token usage.

**LLM-as-judge setup**: 2 judge độc lập (GPT-4o + Claude Sonnet); rubric gửi blind. Tính Cohen's κ — nếu κ < 0.6 thì thảo luận lại rubric.

**Kiểm định thống kê**:

- Test: **Wilcoxon signed-rank** (paired, non-parametric).
- So sánh: mọi cặp variant Tầng 1, per metric per task; tập trung chính vào `Hệ thống đề xuất` vs `Generic ReAct ARAG` và `Hệ thống đề xuất` vs `Fixed MA-ARAG`.
- Threshold: p < 0.05; report effect size (rank-biserial correlation r).
- Multiple comparison correction: Bonferroni hoặc Holm–Bonferroni.

**Phân tích kết quả**:

- Bảng chính: mean ± std per variant × task × metric, tách biệt theo case study.
- Significance matrix: heatmap p-value giữa các cặp.
- Per-domain insight: so sánh pattern giữa IT và Toán — harness có lợi thế khác nhau không giữa domain có code verifier và domain không có?
- Error analysis: ≥ 30 output thất bại phân loại (hallucination, off-Bloom, unsupported citation, code không compile, lời giải Toán sai bước, feedback thiếu giải thích).
- Ablation contribution chart: bar chart ∆ score khi bỏ typed schemas, verifier, targeted repair, pedagogical constraints; diễn giải như đóng góp thực nghiệm của từng thành phần trong cấu hình, không diễn giải như novelty thuật toán.
- EQ2 analysis: bảng interface compliance IT extension vs Toán extension; ghi nhận điểm core phải thích nghi (nếu có) và giải thích.
