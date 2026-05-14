# Chương 1 — Introduction

## 1.1 Motivation and Problem Statement

Giáo viên dành phần lớn thời gian ngoài giờ lên lớp cho các tác vụ lặp lại: soạn kế hoạch bài dạy, xây dựng rubric, tạo đề, chấm bài và viết feedback. LLM có năng lực ngôn ngữ đủ mạnh để hỗ trợ các tác vụ này, nhưng LLM đơn thuần là stateless — mỗi phiên làm việc bắt đầu lại từ đầu, hiệu quả phụ thuộc vào khả năng viết prompt của từng người chứ không phải năng lực sư phạm của họ.

Các ứng dụng phổ biến như ChatGPT hay Gemini bổ sung thêm lịch sử hội thoại và giao diện thân thiện hơn, nhưng về bản chất vẫn được tối ưu cho Q&A tổng quát. Chúng không có khái niệm về khoá học, nhóm học sinh hay tiến trình dạy học — mỗi câu hỏi vẫn được xử lý độc lập, không tích luỹ ngữ cảnh sư phạm qua thời gian.

Trong khi đó, một xu hướng rõ nét đang hình thành ở các lĩnh vực khác: các công cụ chuyên dụng bọc LLM bằng một execution environment phù hợp với từng domain, hay còn được gọi là **harness** — thuật ngữ được hình thành vào đầu năm 2026 để bao hàm những kỹ thuật đã tích luỹ kể từ khi LLM bùng nổ: prompt/context engineering, RAG, tool use, agentic loop, memory hay multi-agent orchestration. Có thể kể đến các ví dụ điển hình như Claude Code và Codex biến LLM thành cộng sự lập trình bằng cách tích hợp file system, terminal và coding workflow. Claude Design kết hợp LLM với design canvas và design system để biến LLM thành trợ thủ đắc lực cho các nhà thiết kế. NotebookLM và Perplexity tối ưu LLM cho nghiên cứu tài liệu với grounding và citation. Mỗi công cụ đó không mạnh hơn vì dùng LLM tốt hơn, mà vì harness của chúng phù hợp với đặc thù của lĩnh vực.

Trong lĩnh vực sư phạm, cá nhân hoá đang là một trong những xu hướng trọng tâm: từ differentiated instruction đến adaptive learning, nghiên cứu giáo dục ngày càng cho thấy việc điều chỉnh nội dung, độ khó và phản hồi theo đặc điểm từng nhóm học sinh cải thiện rõ rệt kết quả học tập. Nhưng để cá nhân hoá có chủ đích, không phải một tác vụ đơn lẻ mà là một vòng lặp: đánh giá học sinh → phát hiện điểm mạnh/yếu → điều chỉnh kế hoạch dạy học → triển khai → đánh giá lại. Luận văn gọi vòng lặp này là **IDA Loop** (Instructional Design–Assessment Loop). Các harness tổng quát có thể đáp ứng một phần nhu cầu này thông qua prompt engineering, skill hay MCP — nhưng không được thiết kế cho đặc thù sư phạm và không thể đạt mức độ cần thiết. Đó là khoảng trống mà luận văn này giải quyết.

## 1.2 Proposed Approach

Luận văn đề xuất **Pedagogy Agent Harness**: một execution environment được thiết kế riêng cho bối cảnh sư phạm, kết hợp với LLM để tạo thành Pedagogy Agent theo công thức `Agent = Model + Harness`. Khác với harness tổng quát, harness này được thiết kế theo từng lớp của kiến trúc:
- **Memory layer**: ánh xạ scope sư phạm lên memory taxonomy — chuẩn chương trình, kiến thức môn học và preferences của giáo viên lên semantic memory; lịch sử chẩn đoán và hồ sơ nhóm tích luỹ theo khoá học lên episodic memory; ngữ cảnh tác vụ hiện tại lên working memory; harness tự động inject đúng tầng vào từng lần gọi, thay vì conversation history đơn thuần
- **Orchestration logic**: vận hành IDA Loop với workflow có cấu trúc — handoff rõ ràng giữa diagnosis, instructional design và assessment — thay vì để agent tự do ReAct qua prompt
- **Tools & sandbox**: trang bị tool sư phạm chuyên biệt (retriever có Bloom-aligned metadata, profile synthesizer, domain verifier) và hỗ trợ mở rộng qua pedagogy domain plugin — plugin có thể đưa tool mới vào và thực thi trong sandbox an toàn, thay vì bị giới hạn bởi built-in tool set
- **Hooks & HITL governance**: chạy pedagogical constraint checks tất định trước khi output được trình giáo viên; và đảm bảo giáo viên luôn phải tham gia tại các điểm quyết định — phê duyệt, chỉnh sửa hoặc từ chối — thuận theo nguyên tắc sư phạm rằng trách nhiệm chuyên môn không thể uỷ thác hoàn toàn cho hệ thống

Prototype được validate trên case study CNTT/lập trình.

## 1.3 Use Cases

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

## 1.4 Research Questions

- **RQ1**: Pedagogy-specific harness có hiệu quả hơn các kiến trúc harness tổng quát — từ không có harness (LLM-only), harness tối giản (Naive RAG), general-purpose agent harness (Generic ReAct ARAG) đến structured agent harness (Fixed MA-ARAG) — trên các tác vụ UC-ID và UC-AS của case study CNTT/lập trình không?
- **RQ2**: IDA Loop có tạo ra phân hoá có chủ đích theo nhóm học sinh không? Output UC-ID/UC-AS ở vòng 2 có StudentGroupProfile có khác biệt đo được so với vòng 1 không có profile theo chiều phù hợp với nhóm không?

## 1.5 Contributions

Luận văn có ba đóng góp chính:

1. **Pedagogy Agent Harness**: một execution environment biến LLM thành Pedagogy Agent, vận hành IDA Loop (Instructional Design–Assessment Loop) làm lõi chính cho group-level personalization, hỗ trợ mở rộng đa lĩnh vực sư phạm qua pedagogy domain plugin, và enforce ràng buộc sư phạm xuyên suốt pipeline cùng với HITL governance.
2. **End-to-end prototype**: prototype Pedagogy Agent Harness chạy local trên case study CNTT/lập trình, bao gồm domain plugin implementation cho lĩnh vực này.
3. **Technical benchmark**: benchmark kỹ thuật với comparison study (LLM-only, Naive RAG, Generic ReAct Agentic RAG, Fixed MA-ARAG), ablation, interface compliance và personalization delta analysis.

## 1.6 Scope and Limitations

Không xây dựng LMS hoàn chỉnh.
Không cá nhân hoá tới từng học sinh.
Không đánh giá hiệu quả học tập thực tế qua nhiều tuần/lớp thật.
Không claim novelty thuật toán cho từng thành phần như RAG hay Multi-Agent.
Đóng góp nằm ở cấu hình tích hợp của harness cho bối cảnh sư phạm, cùng bằng chứng kỹ thuật trên case study CNTT/lập trình.

## 1.7 Thesis Outlines

Chương 1 giới thiệu
Chương 2 trình bày nền tảng và công trình liên quan.
Chương 3 mô tả kiến trúc Pedagogy Agent Harness.
Chương 4 trình bày thiết lập thực nghiệm và protocol đánh giá. 
Chương 5 báo cáo kết quả, ablation, thảo luận và threat to validity.
Chương 6 kết luận và nêu hướng phát triển.
