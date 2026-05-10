# Giới thiệu & Khảo sát — Chương 1 & 2

*(Chương 2 — Khảo sát và phân tích yêu cầu — được gộp vào đây. Xem đề cương tổng thể tại [0_outlines.md](0_outlines.md).)*

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên mất nhiều giờ cho tác vụ sư phạm lặp; LLM thương mại có rủi ro dữ liệu; các agent framework tổng quát chưa tối ưu cho tác vụ sư phạm.
- Vấn đề: LLM đơn thuần chưa phải agent sư phạm — thiếu một harness kết hợp với LLM để tạo thành Pedagogy Agent có tool layer, pedagogical constraints, HITL, workspace-scoped memory và extensibility. Đặc biệt, vòng lặp thiết kế dạy học–đánh giá cá nhân hoá (IDA Loop) — giáo viên đánh giá nhóm học sinh → thiết kế dạy học phân hoá → đánh giá lại → lặp — đòi hỏi harness có khả năng duy trì hồ sơ nhóm và lịch sử chẩn đoán xuyên suốt khoá học, điều mà LLM stateless và agent framework tổng quát không cung cấp; tương tự Claude Code/Codex là harness biến LLM thành coding agent, nhưng dành cho giáo viên.
- Phạm vi: Pedagogy Agent Harness thỏa hai ràng buộc thiết kế cứng (pedagogical constraint enforcement xuyên suốt pipeline, domain extensibility qua plugin interface), được validate qua hai case study: CNTT/lập trình và Toán.
- Định vị đóng góp: không xem từng cơ chế riêng lẻ là mới; nhấn mạnh harness như contribution ở tầng infrastructure, với Multi-Agent và Agentic RAG là implementation bên trong.
- Mục tiêu và EQ (xem [0_outlines.md §3](0_outlines.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case theo hai UC family: **UC-ID** (soạn kế hoạch bài dạy theo phẩm chất/năng lực, điều chỉnh theo StudentGroupProfile) và **UC-AS** (xây dựng công cụ đánh giá/rubric/ma trận đề, sinh đề/bài tập cá nhân hoá, chấm bài + feedback theo nhóm, tổng hợp StudentGroupProfile). **IDA Loop** là vòng lặp kết nối UC-ID và UC-AS theo nhóm học sinh.
- Teacher journey: giao diện **chat hội thoại**; `student_group_profile` dual input (nhập tay qua chat + agent tự tổng hợp từ kết quả UC-AS); cá nhân hoá ở mức nhóm học sinh (group-level), không phải per-student.
- Context scope taxonomy: *global* (giáo viên/user — cá nhân hoá agent xuyên mọi khoá học), *workspace* (một khoá học/môn học cụ thể, chứa tập hợp học viên — phục vụ IDA Loop), *session* (phiên làm việc nằm trong workspace — ephemeral).
- Yêu cầu phi chức năng/ràng buộc thiết kế: HITL bắt buộc, pedagogical constraint enforcement xuyên suốt pipeline, Workspace Memory duy trì xuyên khoá học, domain extensibility qua optional plugin interface (null-plugin contract), LLM là pluggable component.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG, coding agent harness) — xác định gap.
