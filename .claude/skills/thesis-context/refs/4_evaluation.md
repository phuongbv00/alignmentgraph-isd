# Đánh giá hệ thống — Chương 5

## 5.1 Thực nghiệm & Đánh giá

**Thiết lập**:

- Hardware: ghi rõ CPU/RAM/GPU (chốt sau khi có máy).
- Model: Gemma 4 E2B GGUF Q4_K_M (và E4B nếu RAM đủ).
- Corpus: **tài liệu nội bộ giáo viên** — không có trong training data của LLM, đảm bảo RAG có giá trị thật sự:
  - Slide bài giảng + đề thi + rubric chấm của 1–2 giáo viên cộng tác (tiếng Việt).
  - Giáo trình tiếng Việt: CTDL&GT (bản giảng dạy nội bộ), OOP Java (tài liệu khoa soạn).
  - Tài liệu soạn sau 2024 (sau knowledge cutoff của Gemma 4).
  - Tất cả chunk được gán metadata Bloom thủ công/bán tự động (`bloom_level`, `learning_objective`, `topic`, `difficulty`).
  - Tổng ~3.000–6.000 chunk (nhỏ hơn nhưng có giá trị RAG cao hơn corpus public).
- **Lý do không dùng corpus public** (Python Crash Course, CLRS, v.v.): LLM đã được train trên các tài liệu này → LLM-only baseline trông mạnh giả tạo → ∆ giữa các variant bé → không chứng minh được giá trị của RAG.

**Dataset benchmark** (130 sample, kiểm soát độ khó đồng đều):

| Task         | N   | Input                                | Ground truth                         | Cách tạo GT                              |
| ------------ | --- | ------------------------------------ | ------------------------------------ | ---------------------------------------- |
| A: Giáo án   | 50  | `{chủ đề, bloom_target, số buổi}`    | Giáo án mẫu + checklist tiêu chí     | Tự soạn; peer review với 1 giáo viên CS  |
| B: Bài tập   | 50  | `{topic, difficulty, exercise_type}` | Bài tập + test case + đáp án         | Tự soạn; verify bằng `verify_solution()` |
| C: Chấm code | 30  | Bài nộp code lỗi (giả lập)           | Feedback chuẩn + misconception label | Tự viết dựa trên error_taxonomy          |

### Thiết kế thực nghiệm cho EQ1

Controlled comparison: **cùng LLM + cùng corpus + cùng queries**; chỉ thay đổi kiến trúc hệ thống.

**Bảng đảm bảo fairness** — mọi variant giữ nguyên các yếu tố nền tảng dưới đây, chỉ thay đổi cơ chế orchestration/verification:

| Yếu tố                | Giá trị cố định cho tất cả variant                        |
| --------------------- | --------------------------------------------------------- |
| **Model**             | Gemma 4 E2B GGUF Q4_K_M (cùng checkpoint, cùng file)     |
| **Corpus**            | Cùng Qdrant collection, cùng chunk, cùng embedding        |
| **Retriever**         | bge-m3 embedding + bge-reranker-v2-m3; top-k = 5         |
| **Tool access**       | LLM-only: không tool; Naive RAG: không tool; các variant agentic dùng cùng tool set nếu variant đó cho phép tool |
| **Context length**    | Tối đa 8 192 token (giới hạn Gemma 4 E2B)                |
| **Temperature**       | 0.2 (generation); 0.0 (judge)                            |
| **Số lần retry**      | Tối đa 2 retry per task; riêng ablation sẽ bật/tắt targeted repair |
| **Prompt budget**     | System prompt ≤ 512 token; retrieved context ≤ 2 048 token; instruction ≤ 256 token |

> Các variant agentic phải lock cùng model, corpus, retriever, tool implementation, context length và temperature. Khác biệt chính chỉ nằm ở: generic ReAct loop, fixed multi-agent pipeline, hay typed task graph có verifier/constraint.

_Tầng 1 — Comparison study_ (trả lời trực tiếp EQ1):

| Variant | Mô tả | Mục đích |
| --- | --- | --- |
| **LLM-only** | Không RAG, không agent — Gemma 4 E2B generate thẳng | Baseline thấp nhất; đo giá trị của RAG |
| **Naive RAG** | top-k vector search + LLM generate; không agent loop | Đo giá trị của retrieval |
| **Generic ReAct ARAG** | 1 ReAct agent tự do, có retrieval/tool access, không typed graph | Baseline giống agent platform tổng quát |
| **Fixed MA-ARAG** | Pipeline nhiều role cố định: planner/generator/grader/reviewer | Kiểm tra liệu chia role thủ công đã đủ chưa |
| **TTG-ARAG** | Typed Task Graph + verifier + pedagogy constraints + targeted repair | Hệ thống đề xuất |

_Tầng 2 — Ablation study_ (giải thích tại sao TTG-ARAG hoạt động):

| Variant | Thành phần bỏ/thay đổi | Câu hỏi ablation |
| --- | --- | --- |
| **TTG − Typed schemas** | Node vẫn theo graph nhưng input/output free-form | Schema có giúp giảm lỗi định dạng và hallucination không? |
| **TTG − Verifier** | Không chạy pytest/linter/citation/Bloom checks trước output | Verifier đóng góp bao nhiêu vào correctness? |
| **TTG − Targeted Repair** | Có verifier nhưng retry regenerate toàn bộ output | Sửa đúng component lỗi có tốt hơn retry toàn cục không? |
| **TTG − Pedagogical Constraints** | Bỏ Bloom/rubric/misconception/feedback checks | Constraint sư phạm cải thiện chất lượng giáo dục bao nhiêu? |
| **TTG − HITL Feedback Injection** | Teacher reject không được đưa lại thành constraint retry | Vòng teacher feedback có giảm reject rate không? |

**Metrics per task**:

| Task | Metric tự động | LLM-as-judge / human-subset rubric |
| --- | --- | --- |
| A: Giáo án | RAGAS faithfulness/context recall · Bloom violation rate · citation coverage · schema validity | Bloom alignment · constructive alignment · pedagogical coherence · completeness |
| B: Bài tập | `verify_solution()` pass rate · test coverage proxy · compile/runtime error rate · schema validity | Exercise clarity · difficulty calibration · rubric consistency · test case adequacy |
| C: Chấm code | pytest pass-rate precision · misconception hit rate · feedback policy violation rate · citation coverage | Feedback helpfulness · explanation depth · pedagogical tone · correctness of misconception label |

Tất cả: latency end-to-end (ms) + VRAM peak (MB) + số LLM calls + số retry + token budget.

**LLM-as-judge setup**: 2 judge độc lập (GPT-4o + Claude 3.5 Sonnet); rubric gửi blind. Tính Cohen's κ — nếu κ < 0.6 thì thảo luận lại rubric.

**Kiểm định thống kê**:

- Test: **Wilcoxon signed-rank** (paired, non-parametric).
- So sánh: mọi cặp variant Tầng 1, per metric per task; tập trung chính vào `TTG-ARAG` vs `Generic ReAct ARAG` và `TTG-ARAG` vs `Fixed MA-ARAG`.
- Threshold: p < 0.05; report effect size (rank-biserial correlation r).
- Multiple comparison correction: Bonferroni hoặc Holm–Bonferroni.

**Phân tích kết quả**:

- Bảng chính: mean ± std per variant × task × metric.
- Significance matrix: heatmap p-value giữa các cặp.
- Per-task insight: TTG-ARAG dự kiến win rõ nhất ở Task B/C, nơi verifier và targeted repair có tín hiệu khách quan.
- Error analysis: ≥ 30 output thất bại phân loại (hallucination, off-Bloom, unsupported citation, code không compile, test thiếu edge case, feedback thiếu giải thích).
- Ablation contribution chart: bar chart ∆ score khi bỏ typed schemas, verifier, targeted repair, pedagogical constraints.
