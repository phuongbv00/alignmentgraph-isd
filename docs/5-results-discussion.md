# Chương 5 — Results and Discussion

> File này là khung điền sau khi chạy thực nghiệm. Mục tiêu là tách rõ **protocol đánh giá** ở Chương 4 khỏi **kết quả và diễn giải** ở Chương 5.

## 5.1 Result Reporting Plan

Kết quả cần được trình bày theo thứ tự trả lời trực tiếp các research questions:

1. **RQ1 — Comparison study**: so sánh hệ thống đề xuất với LLM-only, Naive RAG, Generic ReAct Agentic RAG và Fixed MA-ARAG.
2. **RQ2 — Personalization delta**: so sánh paired round-1 và round-2 để kiểm tra IDA Loop có tạo phân hoá theo nhóm hay không.

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
- Lợi ích quan sát rõ nhất ở retrieval, workflow có cấu trúc, verifier/repair, pedagogical constraints hay memory/context injection?
- Có trade-off latency hoặc số LLM/tool calls đáng kể không?

## 5.3 Plugin and Mechanism Analysis

Không báo cáo ablation study riêng. Phần này dùng plugin delta, log vận hành và phân tích lỗi để giải thích cơ chế tạo khác biệt của harness.

Template phân tích:

| Analysis item | Evidence | Interpretation |
| --- | --- | --- |
| Domain plugin delta | `Proposed - Domain Plugin` vs `Full Proposed System` | Plugin CNTT cải thiện verifier/code-related tasks ở mức nào? |
| Schema/interface compliance | Schema validity, missing-field rate, malformed output rate | Workflow có cấu trúc có giảm lỗi giao diện không? |
| Verifier/repair behavior | Pass rate, retry count, repaired issue types | Verifier giúp bắt loại lỗi nào thường xuyên nhất? |
| Pedagogical violation pattern | Bloom violation, rubric mismatch, feedback policy violation | Constraint sư phạm giúp kiểm soát chất lượng giáo dục ở điểm nào? |
| Cost/latency trade-off | LLM calls, tool calls, token usage, latency | Chất lượng tăng có đi kèm chi phí vận hành chấp nhận được không? |

Cách viết phù hợp là diễn giải các tín hiệu này như bằng chứng hỗ trợ cho **cấu hình harness tích hợp**, không kết luận định lượng rằng từng thành phần riêng lẻ gây ra mức cải thiện cụ thể.

## 5.4 Personalization Delta Analysis

Template paired analysis:

| Pair | Round-1 output | Round-2 output with StudentGroupProfile | Personalization delta | Group-fit score |
| --- | --- | --- | --- | --- |
| IT-A1/A2 | TBD | TBD | TBD | TBD |

Các dấu hiệu cần tìm:

- Hoạt động học tập có được tag hoặc điều chỉnh đúng theo nhóm không?
- Feedback có nhấn vào misconception đã biết của nhóm không?
- Độ khó bài tập có dịch chuyển hợp lý theo readiness level không?
- Round-2 có chỉ thêm nhãn nhóm hình thức, hay thật sự thay đổi hoạt động/đánh giá?

## 5.5 Error Analysis

Phân loại tối thiểu 30 output thất bại theo taxonomy:

- Hallucination hoặc unsupported citation.
- Off-Bloom hoặc sai constructive alignment.
- Schema invalid hoặc thiếu field bắt buộc.
- Code không compile hoặc test case sai.
- Feedback thiếu giải thích, sai misconception label hoặc tone không phù hợp.
- Phân hoá nhóm sai, ngược profile hoặc quá chung chung.
- Retrieval thất bại do query không đúng domain hoặc chunk metadata kém.

Mỗi nhóm lỗi cần có: mô tả, ví dụ rút gọn, nguyên nhân khả dĩ, thành phần harness liên quan và hướng sửa.

## 5.6 Threats to Validity

**Internal validity**:

- LLM-as-judge có thể bias theo vị trí hoặc style output.
- Ground truth do nhóm tác giả tự soạn có thể thiên lệch.
- Prompt và hyperparameter có thể ưu ái một variant.

**External validity**:

- Chỉ có một case study CNTT/lập trình; chưa kiểm chứng trên domain khác.
- Corpus nội bộ tiếng Việt có thể không đại diện cho mọi trường học.
- Prototype local-first chưa phản ánh deployment LMS quy mô lớn.

**Construct validity**:

- Personalization delta có thể đo được sự khác biệt bề mặt, chưa chắc phản ánh hiệu quả học tập thật.
- Verifier pass rate không bao quát toàn bộ chất lượng sư phạm.
- Latency/token cost phụ thuộc model và hạ tầng.

## 5.7 Discussion

Các điểm cần chốt trong phần thảo luận:

- Khi nào Pedagogy Agent Harness hơn agent framework tổng quát?
- Khi nào plugin verifier tạo khác biệt rõ, và khi nào core harness đã đủ?
- Memory continuity và Context Injection có tạo giá trị thực hay chỉ tăng độ phức tạp?
- Teacher-in-the-loop nên nằm ở đâu để cân bằng autonomy, accountability và UX?
- Hệ thống có thể mở rộng sang domain ít verifier hình thức như Văn, Lịch sử, Địa lý bằng cách nào?
