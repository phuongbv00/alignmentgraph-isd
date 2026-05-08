# Đề cương 7 chương (theo template SOICT, mở rộng)

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên mất nhiều giờ cho tác vụ sư phạm lặp; LLM thương mại có rủi ro dữ liệu; các agent framework tổng quát chưa tối ưu cho tác vụ sư phạm.
- Vấn đề: thiếu một lớp harness điều phối và ràng buộc agent theo nguyên tắc sư phạm — tương tự Claude Code/Codex cho lập trình viên nhưng dành cho giáo viên.
- Phạm vi: Pedagogy Agent Harness với hai trụ cột (Pedagogy-Constrained Orchestration, Pedagogy Domain Extension), được validate qua hai case study: CNTT/lập trình và Toán.
- Định vị đóng góp: không xem từng cơ chế riêng lẻ là mới; nhấn mạnh harness như contribution ở tầng infrastructure, với Multi-Agent và Agentic RAG là implementation bên trong.
- Mục tiêu và EQ (xem [0_context.md](refs/0_context.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case: soạn giáo án, sinh bài tập/đề, chấm bài + feedback cá nhân hoá.
- Yêu cầu phi chức năng/ràng buộc thiết kế: HITL bắt buộc, pedagogical constraint enforcement, khả năng mở rộng bằng Pedagogy Domain Extension, LLM là pluggable component.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG, coding agent harness) — xác định gap.

## Chương 3 — Nền tảng lý thuyết & công nghệ sử dụng

Xem chi tiết 16 subsection tại [2_lit-review.md](refs/2_lit-review.md).

Tóm tắt cấu trúc (16 subsection):

1. Large Language Models (LLM)
2. AI Agent vs Agentic AI — phân biệt khái niệm
3. Agentic AI trong thực tế — AI coding assistants (Claude Code, OpenAI Codex, Devin, Cursor/Windsurf) → **analogy chính cho Pedagogy Agent Harness**
4. Human-in-the-loop & Human-Agent Collaboration (teacher-in-the-loop, override, preference memory)
5. Retrieval-Augmented Generation (RAG, Self-RAG, CRAG, Agentic RAG, GraphRAG, A-RAG)
6. Multi-Agent Systems (MAS) với LLM (AutoGen, MetaGPT, CrewAI, LangGraph, communication/collaboration surveys)
7. Agent Memory Architecture (MemGPT, Sumers taxonomy, episodic/preference memory)
8. Context Management cho LLM Agent (ACON, Lost in the Middle, Chain-of-Agents, Context-Folding)
9. LLM Agent Safety & Guardrails (prompt injection, LlamaGuard, AGrail, ToolSafe, No Free Lunch)
10. LLM deployment options (cloud, local, edge) — context cho lựa chọn LLM của prototype
11. Evaluation Methodology cho hệ thống LLM/RAG/Agent (LLM-as-Judge, RAGAS, agent trajectory evaluation, ablation)
12. Desktop app tích hợp AI (Tauri + HTTP server + SSE)
13. LLM trong giáo dục (tutoring, auto-grading, content generation, AI-assisted feedback)
14. Privacy & Local-first Deployment trong giáo dục (student data, local-first, teacher-controlled data governance)
15. Nền tảng sư phạm (Bloom's Taxonomy, Constructive Alignment)
16. Khoảng trống & định vị hệ thống

## Chương 4 — Thiết kế và triển khai hệ thống

Xem chi tiết đầy đủ tại [3_system-design.md](refs/3_system-design.md).

Tóm tắt cấu trúc:

1. Mục tiêu thiết kế và phạm vi hệ thống
2. Yêu cầu thiết kế chính: HITL, pedagogy constraints, technical verification, extensibility, LLM-agnostic
3. Kiến trúc tổng quan — Pedagogy Agent Harness
4. Các luồng nghiệp vụ chính
5. Pedagogy-Constrained Orchestration
6. Pedagogy Domain Extension (CNTT/lập trình extension + Toán extension)
7. Retrieval và quản lý tri thức
8. Verification, Guardrails và HITL
9. Kiến trúc ứng dụng desktop và runtime
10. Tổng kết thiết kế

## Chương 5 — Đánh giá hệ thống

Xem chi tiết đầy đủ tại [4_evaluation.md](refs/4_evaluation.md).

Tóm tắt cấu trúc:

1. Thiết lập thực nghiệm (hardware, mô hình, corpus, hyperparameters)
2. Bộ dữ liệu đánh giá (~180 sample: CNTT/lập trình + Toán)
3. Baselines + Ablation (LLM-only → Naive RAG → Generic ReAct ARAG → Fixed MA-ARAG → hệ thống đề xuất)
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, teacher-controlled mutation metrics, LLM-as-judge, latency)
5. Kết quả, phân tích lỗi, thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: lớp điều phối agent cho tác vụ sư phạm, tổ chức quanh Pedagogy-Constrained Orchestration và Pedagogy Domain Extension. Định vị rõ ràng như harness infrastructure (tương tự Claude Code/Codex) thay vì application.
2. **Hai domain extension**: CNTT/lập trình và Toán — bằng chứng thực nghiệm rằng Pedagogy Domain Extension interface đủ tổng quát cho hai domain có đặc trưng khác biệt.
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study với corpus nội bộ, retrieval local, verifier và teacher-controlled review flow.
4. **Bộ benchmark sư phạm tự xây**: ~180 sample (CNTT: giáo án/bài tập/chấm code; Toán: bài tập/chấm lời giải) với corpus nội bộ tiếng Việt.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5), đồng thời nêu rõ giới hạn: kết quả chứng minh giá trị của cấu hình tích hợp trong phạm vi hai case study, không chứng minh các cơ chế con là mới.

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 và EQ2.
- Giới hạn: không human eval diện rộng, mới hai domain extension, LLM-as-judge bias, performance phụ thuộc LLM được chọn.
- Hướng mở rộng: extension thêm domain (Vật lý, Lịch sử...), human eval, fine-tune LLM nhỏ trên curriculum VN, tối ưu runtime local, tích hợp LMS.
