# Chương 1 — Introduction

## 1.1 Motivation

Giáo viên và giảng viên thường mất nhiều thời gian cho các tác vụ sư phạm lặp lại như soạn kế hoạch bài dạy, xây dựng rubric, tạo bài tập, chấm bài và viết feedback. LLM có thể hỗ trợ các tác vụ này, nhưng việc sử dụng LLM thương mại trong giáo dục đặt ra rủi ro về dữ liệu học viên, học liệu nội bộ và khả năng kiểm soát đầu ra. Các agent framework tổng quát có thể cung cấp tool use và orchestration, nhưng chưa tối ưu cho ràng buộc sư phạm, teacher-in-the-loop và vòng lặp cá nhân hoá theo nhóm học sinh.

Vấn đề cốt lõi của luận văn là: **LLM đơn thuần chưa phải agent sư phạm**. Một Pedagogy Agent cần một harness kết hợp với LLM để cung cấp tool layer, workspace-scoped memory, pedagogical constraints, verifier đặc thù từng môn/lĩnh vực, HITL governance và cơ chế mở rộng đa lĩnh vực sư phạm. Cách định vị này tương tự các hệ agentic AI hiện đại: Claude Code/Codex dùng coding harness cho lập trình; Claude Design dùng design canvas, design system và workflow chỉnh sửa để biến LLM thành cộng sự thiết kế; Claude Cowork dùng desktop workspace, file/app access và task delegation để biến LLM thành cộng sự tri thức; OpenClaw dùng local runtime, messaging channels, skills và sandbox để biến LLM thành trợ lý cá nhân có khả năng hành động. Điểm chung là model trở thành agent khi được bao quanh bởi một execution harness phù hợp với lĩnh vực vận hành.

## 1.2 Problem Statement

Trong bối cảnh giáo dục, vòng lặp thiết kế dạy học và đánh giá cá nhân hoá không phải là một tác vụ đơn lẻ. Giáo viên đánh giá nhóm học sinh, phát hiện điểm mạnh/yếu, điều chỉnh kế hoạch dạy học, triển khai bài học, đánh giá lại và tiếp tục điều chỉnh. Luận văn gọi vòng lặp này là **Instructional Design-Assessment Loop (IDA Loop)**.

IDA Loop đòi hỏi hệ thống phải duy trì hồ sơ nhóm học sinh và lịch sử chẩn đoán xuyên suốt một khoá học. LLM stateless hoặc RAG đơn giản không tự đảm bảo được các yêu cầu này. Một agent framework tổng quát cũng chưa đủ nếu thiếu ràng buộc sư phạm, memory scope theo khoá học, cơ chế tổng hợp StudentGroupProfile và teacher-controlled update flow.

## 1.3 Proposed Approach

Luận văn đề xuất **Pedagogy Agent Harness**: một execution environment biến LLM thành Pedagogy Agent theo công thức `Agent = Model + Harness`. Harness nhận input qua giao diện chat hội thoại của giáo viên, phân loại intent, inject context từ memory, gọi retrieval/verifier nếu cần, enforce typed schema và ràng buộc sư phạm, sau đó đưa output qua teacher-in-the-loop trước khi commit vào workspace memory.

Harness được thiết kế quanh hai ràng buộc cứng:

- **Pipeline-wide pedagogical constraint enforcement**: ràng buộc Bloom alignment, constructive alignment, rubric consistency, misconception mapping, feedback policy và HITL gate được áp dụng xuyên suốt pipeline.
- **Mở rộng đa lĩnh vực sư phạm với null-plugin contract**: lĩnh vực sư phạm mới được thêm qua optional plugin interface; core vẫn hoạt động đầy đủ khi không có plugin.

Prototype được validate qua hai case study: CNTT/lập trình và Toán. Hai domain này có đặc trưng khác nhau, giúp kiểm tra tính tổng quát của interface: CNTT có code verifier/test case, Toán có SymPy/structural checker, và cả hai đều cần error taxonomy cũng như feedback template đặc thù.

## 1.4 Use Cases

Luận văn tập trung vào hai use-case family:

**UC-ID — Instructional Design**:

- Soạn kế hoạch bài dạy theo mục tiêu phẩm chất/năng lực.
- Điều chỉnh kế hoạch bài dạy theo `StudentGroupProfile`.
- Phân hoá hoạt động cho từng nhóm học sinh, ví dụ nhóm nâng cao, nhóm cần bổ trợ, nhóm có misconception cụ thể.

**UC-AS — Assessment**:

- Xây dựng công cụ đánh giá như rubric, ma trận đề, tiêu chí phân mức năng lực.
- Sinh đề kiểm tra hoặc bài tập có thể cá nhân hoá theo nhóm học sinh.
- Chấm bài và sinh feedback theo nhóm.
- Tổng hợp kết quả đánh giá thành `StudentGroupProfile`.

Cá nhân hoá được giới hạn ở mức **group-level personalization**. `StudentGroupProfile` có thể đến từ hai nguồn: giáo viên nhập tay qua chat hoặc agent tổng hợp từ kết quả UC-AS và trình giáo viên xác nhận.

## 1.5 Research Questions

- **RQ1**: Trong hai case study CNTT/lập trình và Toán, Pedagogy Agent Harness có hiệu quả hơn LLM-only, Naive RAG, Generic ReAct Agentic RAG và Fixed MA-ARAG trên các tác vụ UC-ID và UC-AS không?
- **RQ2**: Domain Plugin Interface có đủ tổng quát để hai domain extension CNTT và Toán cùng implement mà không thay đổi core không? Core có hoạt động đầy đủ khi plugin = null không?
- **RQ3**: IDA Loop có tạo ra phân hoá có chủ đích theo nhóm học sinh không? Output UC-ID/UC-AS ở vòng 2 có StudentGroupProfile có khác biệt đo được so với vòng 1 không có profile theo chiều phù hợp với nhóm không?

## 1.6 Contributions

Luận văn có bốn đóng góp chính:

1. **Pedagogy Agent Harness architecture**: kiến trúc harness biến LLM thành Pedagogy Agent với Intent Router, Memory Architecture, Profile Synthesis Pipeline, Context Injection, typed workflow, verifier và HITL governance.
2. **IDA Loop for group-level personalization**: vòng lặp đánh giá → tổng hợp profile → thiết kế dạy học phân hoá → đánh giá lại trong phạm vi một khoá học.
3. **Optional Domain Plugin Interface**: interface mở rộng đa lĩnh vực sư phạm với null-plugin contract, được minh hoạ bằng hai implementation CNTT/lập trình và Toán.
4. **Prototype and technical evaluation plan**: prototype end-to-end và benchmark kỹ thuật với comparison study, ablation, interface compliance và personalization delta analysis.

## 1.7 Scope and Limitations

Luận văn không xây dựng LMS hoàn chỉnh, không cá nhân hoá tới từng học sinh, không đánh giá hiệu quả học tập thực tế qua nhiều tuần/lớp thật, và không claim novelty thuật toán cho từng thành phần như RAG, Multi-Agent hay verifier. Đóng góp nằm ở cấu hình tích hợp của harness cho bối cảnh sư phạm, cùng bằng chứng kỹ thuật qua hai case study.

## 1.8 Thesis Organization

Chương 2 trình bày nền tảng và công trình liên quan. Chương 3 mô tả kiến trúc Pedagogy Agent Harness. Chương 4 trình bày thiết lập thực nghiệm và protocol đánh giá. Chương 5 báo cáo kết quả, ablation, thảo luận và threat to validity. Chương 6 kết luận và nêu hướng phát triển.
