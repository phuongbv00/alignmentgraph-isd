# Chương 1 — Introduction

## 1.1 Motivation and Problem Statement

Giáo viên dành phần lớn thời gian ngoài giờ lên lớp cho các tác vụ lặp lại: soạn kế hoạch bài dạy, xây dựng rubric, tạo đề, chấm bài và viết feedback. LLM có năng lực ngôn ngữ đủ mạnh để hỗ trợ các tác vụ này, nhưng LLM đơn thuần là stateless — mỗi phiên làm việc bắt đầu lại từ đầu, hiệu quả phụ thuộc vào khả năng viết prompt của từng người chứ không phải năng lực sư phạm của họ.

Các ứng dụng phổ biến như ChatGPT hay Gemini bổ sung thêm lịch sử hội thoại và giao diện thân thiện hơn, nhưng về bản chất vẫn được tối ưu cho Q&A tổng quát. Chúng không có khái niệm về khoá học, nhóm học sinh hay tiến trình dạy học — mỗi câu hỏi vẫn được xử lý độc lập, không tích luỹ ngữ cảnh sư phạm qua thời gian.

Trong khi đó, một xu hướng rõ nét đang hình thành ở các lĩnh vực khác: các công cụ chuyên dụng bọc LLM bằng một execution environment phù hợp với từng domain, hay còn được gọi là **harness** — lớp phần mềm bao quanh model để quản lý prompt/context engineering, RAG, tool use, agentic loop, memory, permission và orchestration. Có thể kể đến các ví dụ điển hình như Claude Code và Codex biến LLM thành cộng sự lập trình bằng cách tích hợp file system, terminal và coding workflow; NotebookLM và Perplexity tối ưu LLM cho nghiên cứu tài liệu với grounding và citation. Mỗi công cụ đó không mạnh hơn chỉ vì dùng LLM tốt hơn, mà vì harness của chúng phù hợp với đặc thù của lĩnh vực.

Trong lĩnh vực sư phạm, cá nhân hoá đang là một trong những xu hướng trọng tâm: từ differentiated instruction đến adaptive learning, nghiên cứu giáo dục ngày càng cho thấy việc điều chỉnh nội dung, độ khó và phản hồi theo đặc điểm từng nhóm học sinh cải thiện rõ rệt kết quả học tập. Nhưng để cá nhân hoá có chủ đích, không phải một tác vụ đơn lẻ mà là một vòng lặp: đánh giá học sinh → phát hiện điểm mạnh/yếu → điều chỉnh kế hoạch dạy học → triển khai → đánh giá lại. Luận văn gọi vòng lặp này là **IDA Loop** (Instructional Design–Assessment Loop). Các harness tổng quát có thể đáp ứng một phần nhu cầu này thông qua prompt engineering, skill hay MCP — nhưng không được thiết kế cho đặc thù sư phạm và không thể đạt mức độ cần thiết. Đó là khoảng trống mà luận văn này giải quyết.

## 1.2 Contributions

Luận văn có ba đóng góp chính:

1. **Pedagogy Agent Harness**: một execution environment biến LLM thành Pedagogy Agent, vận hành IDA Loop (Instructional Design–Assessment Loop) làm lõi chính cho group-level personalization, hỗ trợ mở rộng đa lĩnh vực sư phạm qua pedagogy domain plugin, và enforce ràng buộc sư phạm xuyên suốt pipeline cùng với HITL governance. Harness tập trung vào hai use-case family: **UC-ID — Instructional Design** (soạn kế hoạch bài dạy, điều chỉnh kế hoạch theo `StudentGroupProfile`, phân hoá hoạt động theo nhóm) và **UC-AS — Assessment** (xây dựng rubric/ma trận đề, sinh bài tập hoặc đề kiểm tra, chấm bài, sinh feedback và tổng hợp kết quả đánh giá thành `StudentGroupProfile`). Cá nhân hoá được giới hạn ở mức **group-level personalization**.
2. **End-to-end prototype**: prototype Pedagogy Agent Harness chạy local trên case study CNTT/lập trình, bao gồm domain plugin implementation cho lĩnh vực này.
3. **Technical benchmark**: benchmark kỹ thuật với comparison study (LLM-only, Naive RAG, Generic ReAct Agentic RAG, Fixed MA-ARAG), interface compliance, plugin delta, personalization delta analysis và SOTA research-paper anchoring với các teacher-facing papers.

## 1.3 Research Questions

- **RQ1**: Pedagogy Agent Harness đạt hiệu quả như thế nào so với các baseline kiến trúc LLM/agent tổng quát và các SOTA teacher-facing AI support systems trên các tác vụ UC-ID và UC-AS?
- **RQ2**: Pedagogy Agent Harness có cá nhân hoá output theo hồ sơ nhóm học sinh trên các tác vụ UC-ID và UC-AS không?

## 1.4 Thesis Outlines

Chương 1 giới thiệu
Chương 2 trình bày nền tảng và công trình liên quan.
Chương 3 mô tả kiến trúc Pedagogy Agent Harness.
Chương 4 trình bày thiết lập thực nghiệm và protocol đánh giá. 
Chương 5 báo cáo kết quả comparison study, personalization delta, phân tích lỗi, thảo luận và threat to validity.
Chương 6 kết luận và nêu hướng phát triển.
