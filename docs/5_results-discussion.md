# Chương 5 — Results and Discussion

> File này là khung điền sau khi chạy thực nghiệm. Mục tiêu là tách rõ **protocol đánh giá** ở Chương 4 khỏi **kết quả và diễn giải** ở Chương 5.

## 5.1 Result Reporting Plan

Kết quả cần được trình bày theo thứ tự trả lời trực tiếp các research questions:

1. **RQ1 — Comparison study**: so sánh hệ thống đề xuất với LLM-only, Naive RAG, Generic ReAct Agentic RAG và Fixed MA-ARAG.
2. **RQ2 — Mở rộng đa lĩnh vực sư phạm**: báo cáo interface compliance của CNTT/lập trình và Toán, cùng test null-plugin contract.
3. **RQ3 — Personalization delta**: so sánh paired round-1 và round-2 để kiểm tra IDA Loop có tạo phân hoá theo nhóm hay không.

## 5.2 Main Comparison Results

Template bảng chính:

| Task family | Variant | Quality score | Schema validity | Verifier pass rate | Pedagogical violation rate | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| UC-ID | LLM-only | TBD | TBD | N/A | TBD | TBD |
| UC-ID | Naive RAG | TBD | TBD | N/A | TBD | TBD |
| UC-ID | Generic ReAct ARAG | TBD | TBD | N/A | TBD | TBD |
| UC-ID | Fixed MA-ARAG | TBD | TBD | N/A | TBD | TBD |
| UC-ID | Proposed - Domain Plugin | TBD | TBD | N/A | TBD | TBD |
| UC-ID | Full Proposed System | TBD | TBD | TBD | TBD | TBD |
| UC-AS | LLM-only | TBD | TBD | TBD | TBD | TBD |
| UC-AS | Naive RAG | TBD | TBD | TBD | TBD | TBD |
| UC-AS | Generic ReAct ARAG | TBD | TBD | TBD | TBD | TBD |
| UC-AS | Fixed MA-ARAG | TBD | TBD | TBD | TBD | TBD |
| UC-AS | Proposed - Domain Plugin | TBD | TBD | N/A | TBD | TBD |
| UC-AS | Full Proposed System | TBD | TBD | TBD | TBD | TBD |

Diễn giải cần tập trung vào các câu hỏi:

- Harness cải thiện rõ nhất ở task nào: lesson planning, exercise generation, rubric construction hay grading/feedback?
- Lợi ích đến từ retrieval, typed workflow, verifier, pedagogical constraints hay memory/context injection?
- Có trade-off latency hoặc số LLM/tool calls đáng kể không?

## 5.3 Ablation Results

Template ablation:

| Ablation | Removed component | Expected impact | Observed delta |
| --- | --- | --- | --- |
| Proposed - Typed schemas | Typed input/output validation | Tăng lỗi định dạng và giảm consistency | TBD |
| Proposed - Verifier | Domain/citation/Bloom checks | Giảm correctness và tăng violation | TBD |
| Proposed - Targeted Repair | Node-level repair | Tăng latency hoặc lỗi lặp lại | TBD |
| Proposed - Pedagogical Constraints | Bloom/rubric/misconception checks | Giảm pedagogical alignment | TBD |
| Proposed - Teacher-controlled mutation feedback | Teacher edit/reject reason feedback | Tăng số lần reject lặp lại | TBD |

Phần này không nên diễn giải từng thành phần như một thuật toán mới. Cách viết phù hợp là: ablation cho thấy mỗi thành phần đóng góp thế nào vào chất lượng của **cấu hình harness tích hợp**.

## 5.4 Domain Extensibility and Null-Plugin Contract

Template interface compliance:

| Interface dimension | CNTT/lập trình plugin | Toán plugin | Core modification needed? |
| --- | --- | --- | --- |
| Metadata schema | TBD | TBD | TBD |
| Task schemas | TBD | TBD | TBD |
| Retrieval policy | TBD | TBD | TBD |
| Verifier | Code verifier/test runner | SymPy/structural checker | TBD |
| Error taxonomy | Programming misconceptions/errors | Math misconceptions/errors | TBD |
| Feedback templates | TBD | TBD | TBD |
| Corpus ingestion pipeline | TBD | TBD | TBD |

Null-plugin test cần báo cáo rõ:

- UC-ID có chạy đầy đủ khi không load plugin không?
- UC-AS có bỏ qua verifier mà không làm hỏng pipeline không?
- Output có còn schema-valid và HITL-governed không?
- Chất lượng giảm ở metrics nào khi thiếu verifier đặc thù domain?

## 5.5 Personalization Delta Analysis

Template paired analysis:

| Pair | Round-1 output | Round-2 output with StudentGroupProfile | Personalization delta | Group-fit score |
| --- | --- | --- | --- | --- |
| IT-A1/A2 | TBD | TBD | TBD | TBD |
| Math-A1/A2 | TBD | TBD | TBD | TBD |

Các dấu hiệu cần tìm:

- Hoạt động học tập có được tag hoặc điều chỉnh đúng theo nhóm không?
- Feedback có nhấn vào misconception đã biết của nhóm không?
- Độ khó bài tập có dịch chuyển hợp lý theo readiness level không?
- Round-2 có chỉ thêm nhãn nhóm hình thức, hay thật sự thay đổi hoạt động/đánh giá?

## 5.6 Error Analysis

Phân loại tối thiểu 30 output thất bại theo taxonomy:

- Hallucination hoặc unsupported citation.
- Off-Bloom hoặc sai constructive alignment.
- Schema invalid hoặc thiếu field bắt buộc.
- Code không compile, test case sai hoặc lời giải Toán sai bước.
- Feedback thiếu giải thích, sai misconception label hoặc tone không phù hợp.
- Phân hoá nhóm sai, ngược profile hoặc quá chung chung.
- Retrieval thất bại do query không đúng domain hoặc chunk metadata kém.

Mỗi nhóm lỗi cần có: mô tả, ví dụ rút gọn, nguyên nhân khả dĩ, thành phần harness liên quan và hướng sửa.

## 5.7 Threats to Validity

**Internal validity**:

- LLM-as-judge có thể bias theo vị trí hoặc style output.
- Ground truth do nhóm tác giả tự soạn có thể thiên lệch.
- Prompt và hyperparameter có thể ưu ái một variant.

**External validity**:

- Chỉ có hai domain CNTT/lập trình và Toán.
- Corpus nội bộ tiếng Việt có thể không đại diện cho mọi trường học.
- Prototype local-first chưa phản ánh deployment LMS quy mô lớn.

**Construct validity**:

- Personalization delta có thể đo được sự khác biệt bề mặt, chưa chắc phản ánh hiệu quả học tập thật.
- Verifier pass rate không bao quát toàn bộ chất lượng sư phạm.
- Latency/token cost phụ thuộc model và hạ tầng.

## 5.8 Discussion

Các điểm cần chốt trong phần thảo luận:

- Khi nào Pedagogy Agent Harness hơn agent framework tổng quát?
- Khi nào plugin verifier tạo khác biệt rõ, và khi nào core harness đã đủ?
- Memory continuity và Context Injection có tạo giá trị thực hay chỉ tăng độ phức tạp?
- Teacher-in-the-loop nên nằm ở đâu để cân bằng autonomy, accountability và UX?
- Hệ thống có thể mở rộng sang domain ít verifier hình thức như Văn, Lịch sử, Địa lý bằng cách nào?
