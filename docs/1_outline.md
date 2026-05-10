# Đề cương 7 chương (theo template SOICT, mở rộng)

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên mất nhiều giờ cho tác vụ sư phạm lặp; LLM thương mại có rủi ro dữ liệu; các agent framework tổng quát chưa tối ưu cho tác vụ sư phạm.
- Vấn đề: LLM đơn thuần chưa phải agent sư phạm — thiếu một harness kết hợp với LLM để tạo thành Pedagogy Agent có tool layer, pedagogical constraints, HITL, course-scoped memory và extensibility. Đặc biệt, vòng lặp thiết kế dạy học–đánh giá cá nhân hoá (IDA Loop) — giáo viên đánh giá nhóm học sinh → thiết kế dạy học phân hoá → đánh giá lại → lặp — đòi hỏi harness có khả năng duy trì hồ sơ nhóm và lịch sử chẩn đoán xuyên suốt khoá học, điều mà LLM stateless và agent framework tổng quát không cung cấp; tương tự Claude Code/Codex là harness biến LLM thành coding agent, nhưng dành cho giáo viên.
- Phạm vi: Pedagogy Agent Harness thỏa hai ràng buộc thiết kế cứng (pedagogical constraint enforcement xuyên suốt pipeline, domain extensibility qua plugin interface), được validate qua hai case study: CNTT/lập trình và Toán.
- Định vị đóng góp: không xem từng cơ chế riêng lẻ là mới; nhấn mạnh harness như contribution ở tầng infrastructure, với Multi-Agent và Agentic RAG là implementation bên trong.
- Mục tiêu và EQ (xem [0_context.md](refs/0_context.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case theo hai UC family: **UC-ID** (soạn kế hoạch bài dạy theo phẩm chất/năng lực, điều chỉnh theo StudentGroupProfile) và **UC-AS** (xây dựng công cụ đánh giá/rubric/ma trận đề, sinh đề/bài tập cá nhân hoá, chấm bài + feedback theo nhóm, tổng hợp StudentGroupProfile). **IDA Loop** là vòng lặp kết nối UC-ID và UC-AS theo nhóm học sinh.
- Teacher journey: giao diện **chat hội thoại**; `student_group_profile` dual input (nhập tay qua chat + agent tự tổng hợp từ kết quả UC-AS); session scope = một môn/khoá học ngắn hạn; cá nhân hoá ở mức nhóm học sinh (group-level), không phải per-student.
- Yêu cầu phi chức năng/ràng buộc thiết kế: HITL bắt buộc, pedagogical constraint enforcement xuyên suốt pipeline, Course Memory duy trì xuyên khoá học, domain extensibility qua optional plugin interface (null-plugin contract), LLM là pluggable component.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG, coding agent harness) — xác định gap.

## Chương 3 — Nền tảng lý thuyết & công nghệ sử dụng

Xem chi tiết 16 subsection tại [2_lit-review.md](refs/2_lit-review.md).

Tóm tắt cấu trúc (17 subsection):

1. Large Language Models (LLM)
2. AI Agent vs Agentic AI — phân biệt khái niệm
3. **Agent Harness Engineering** — định nghĩa harness, 6 capability cốt lõi, harness vs framework, infrastructure contribution framing
4. Agentic AI trong thực tế — AI coding assistants (Claude Code, OpenAI Codex, Devin, Cursor/Windsurf) → **analogy chính cho Pedagogy Agent Harness**
5. Human-in-the-loop & Human-Agent Collaboration (teacher-in-the-loop, override, preference memory)
6. Retrieval-Augmented Generation (RAG, Self-RAG, CRAG, Agentic RAG, GraphRAG, A-RAG)
7. Multi-Agent Systems (MAS) với LLM (AutoGen, MetaGPT, CrewAI, LangGraph, communication/collaboration surveys)
8. Agent Memory Architecture (MemGPT, Sumers taxonomy, episodic/preference memory)
9. Context Management cho LLM Agent (ACON, Lost in the Middle, Chain-of-Agents, Context-Folding)
10. LLM Agent Safety & Guardrails (prompt injection, LlamaGuard, AGrail, ToolSafe, No Free Lunch)
11. LLM deployment options (cloud, local, edge) — context cho lựa chọn LLM của prototype
12. Evaluation Methodology cho hệ thống LLM/RAG/Agent (LLM-as-Judge, RAGAS, agent trajectory evaluation, ablation)
13. Desktop app tích hợp AI (Electron + in-process agent)
14. LLM trong giáo dục (tutoring, auto-grading, content generation, AI-assisted feedback)
15. Privacy & Local-first Deployment trong giáo dục (student data, local-first, teacher-controlled data governance)
16. Nền tảng sư phạm (Bloom's Taxonomy, Constructive Alignment)
17. Khoảng trống & định vị hệ thống

## Chương 4 — Thiết kế và triển khai hệ thống

Xem chi tiết đầy đủ tại [3_system-design.md](refs/3_system-design.md).

Tóm tắt cấu trúc: **(chi tiết sẽ mở rộng trong 3_system-design.md)**

Các thành phần thiết kế cốt lõi cần trình bày:

1. **Kiến trúc tổng thể**: Agent = Model + Harness; IDA Loop là luồng vận hành chính; chat interface là điểm vào của giáo viên.
2. **Intent Router**: phân loại chat input thành UC-ID / UC-AS / UPDATE_PROFILE / QUERY / FEEDBACK; kích hoạt pipeline tương ứng.
3. **UC-ID Pipeline**: retrieval từ corpus (scoped theo domain + StudentGroupProfile) → generation với Bloom/constructive alignment constraints → typed schema validation → HITL → output kế hoạch bài dạy phân hoá.
4. **UC-AS Pipeline**: sinh đề/rubric hoặc chấm bài → domain verifier (optional — từ plugin) → diagnosis generation → Profile Synthesis → HITL → output feedback/diagnosis report.
5. **Course Memory**: CourseContext, StudentGroupProfiles[], DiagnosisHistory[], ArtifactLog[]; scope = một khoá học; reset khi bắt đầu khoá mới.
6. **Profile Synthesis Pipeline**: parse diagnosis output → structured group update → merge với StudentGroupProfile hiện tại → đề xuất giáo viên confirm (HITL nhẹ).
7. **Context Injection**: tự động inject StudentGroupProfiles và DiagnosisHistory (N vòng gần nhất) vào retrieval policy và generation prompt cho mọi task — không cần giáo viên nhắc lại.
8. **Domain Plugin Interface (optional)**: khai báo verifier, error taxonomy, tool interface; null-plugin contract — core chạy đầy đủ khi plugin = null; hai implementation: IT plugin (code verifier + error taxonomy IT) và Toán plugin (SymPy checker + math error taxonomy).
9. **HITL Governance**: mọi output phải qua approval gate trước khi lưu vào ArtifactLog; giáo viên chỉnh sửa qua chat; rejection reason feed lại làm constraint retry.

## Chương 5 — Đánh giá hệ thống

Xem chi tiết đầy đủ tại [4_evaluation.md](refs/4_evaluation.md).

Tóm tắt cấu trúc:

1. Thiết lập thực nghiệm (hardware, mô hình, corpus, hyperparameters)
2. Bộ dữ liệu đánh giá (~200 sample: CNTT/lập trình + Toán, bao gồm IDA round-1 và round-2)
3. Baselines + Ablation (LLM-only → Naive RAG → Generic ReAct ARAG → Fixed MA-ARAG → Đề xuất-no-plugin → hệ thống đề xuất đầy đủ)
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, **personalization delta**, teacher-controlled mutation metrics, LLM-as-judge, latency)
5. Kết quả trả lời EQ1, EQ2, EQ3; phân tích lỗi; thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent (Agent = Model + Harness), thỏa hai ràng buộc thiết kế cứng: pedagogical constraint enforcement xuyên suốt pipeline và domain extensibility qua plugin interface. Định vị rõ ràng như harness infrastructure (tương tự coding harness trong Claude Code/Codex) thay vì application.
2. **Hai domain plugin implementation**: CNTT/lập trình và Toán — bằng chứng thực nghiệm rằng domain plugin interface đủ tổng quát cho hai domain có đặc trưng khác biệt.
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study với corpus nội bộ, retrieval local, verifier và teacher-controlled review flow.
4. **Bộ benchmark sư phạm tự xây**: ~180 sample (CNTT: giáo án/bài tập/chấm code; Toán: bài tập/chấm lời giải) với corpus nội bộ tiếng Việt.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5), đồng thời nêu rõ giới hạn: kết quả chứng minh giá trị của cấu hình tích hợp trong phạm vi hai case study, không chứng minh các cơ chế con là mới.

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 và EQ2.
- Giới hạn: không human eval diện rộng, mới hai domain extension, LLM-as-judge bias, performance phụ thuộc LLM được chọn.
- Hướng mở rộng: extension thêm domain (Vật lý, Lịch sử...), human eval, fine-tune LLM nhỏ trên curriculum VN, tối ưu runtime local, tích hợp LMS.
