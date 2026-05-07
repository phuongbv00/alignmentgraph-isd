# Đề cương 7 chương (theo template SOICT, mở rộng)

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên kỹ thuật mất nhiều giờ cho tác vụ lặp; LLM thương mại có rủi ro dữ liệu.
- Vấn đề: RAG tổng quát / generic ReAct Agentic RAG chưa tối ưu cho tác vụ sư phạm, đặc biệt khi local-first/privacy và local/edge small LLM là ràng buộc cứng.
- Phạm vi: hệ thống desktop hỗ trợ giáo viên kỹ thuật, kiến trúc core + Pedagogy Domain Extension, extension đầu tiên cho CNTT/lập trình.
- Định vị đóng góp: không xem từng cơ chế riêng lẻ là mới; nhấn mạnh kiến trúc Multi-Agent Agentic RAG đề xuất cho hỗ trợ sư phạm kỹ thuật, được tổ chức quanh Pedagogy-Constrained Orchestration, Edge-LLM-Constrained Orchestration và Pedagogy Domain Extension.
- Mục tiêu và EQ (xem [0_context.md](refs/0_context.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case: soạn giáo án, sinh bài tập/đề, chấm bài + feedback cá nhân hoá.
- Yêu cầu phi chức năng/ràng buộc thiết kế: local-first/privacy bắt buộc, local/edge small LLM bắt buộc, kiểm soát latency/resource, khả năng mở rộng bằng Pedagogy Domain Extension.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG) — xác định gap.

## Chương 3 — Nền tảng lý thuyết & công nghệ sử dụng

Xem chi tiết 16 subsection tại [2_lit-review.md](refs/2_lit-review.md).

Tóm tắt cấu trúc (16 subsection):

1. Large Language Models (LLM)
2. AI Agent vs Agentic AI — phân biệt khái niệm
3. Agentic AI trong thực tế — AI coding assistants (Claude Code, OpenAI Codex, Devin, Cursor/Windsurf)
4. Human-in-the-loop & Human-Agent Collaboration (teacher-in-the-loop, override, preference memory)
5. Retrieval-Augmented Generation (RAG, Self-RAG, CRAG, Agentic RAG, GraphRAG, A-RAG)
6. Multi-Agent Systems (MAS) với LLM (AutoGen, MetaGPT, CrewAI, LangGraph, communication/collaboration surveys)
7. Agent Memory Architecture (MemGPT, Sumers taxonomy, episodic/preference memory)
8. Context Management cho LLM Agent (ACON, Lost in the Middle, Chain-of-Agents, Context-Folding)
9. LLM Agent Safety & Guardrails (prompt injection, LlamaGuard, AGrail, ToolSafe, No Free Lunch)
10. Edge LLM & triển khai local (llama.cpp, quantization, Gemma 3n/Gemma 4)
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
2. Yêu cầu thiết kế chính: local-first/privacy, HITL, pedagogy, technical verification, edge LLM, extensibility
3. Kiến trúc tổng quan
4. Các luồng nghiệp vụ chính
5. Pedagogy-Constrained Orchestration
6. Edge-LLM-Constrained Orchestration
7. Pedagogy Domain Extension
8. Retrieval và quản lý tri thức
9. Verification, Guardrails và HITL
10. Kiến trúc ứng dụng desktop và local runtime
11. Tổng kết thiết kế

## Chương 5 — Đánh giá hệ thống

Xem chi tiết đầy đủ tại [4_evaluation.md](refs/4_evaluation.md).

Tóm tắt cấu trúc:

1. Thiết lập thực nghiệm (hardware, mô hình, corpus, hyperparameters)
2. Bộ dữ liệu đánh giá (tự xây — 130 mẫu: 50 giáo án, 50 bài tập, 30 chấm code)
3. Baselines + Ablation (LLM-only → Naive RAG → Generic ReAct ARAG → Fixed MA-ARAG → hệ thống đề xuất)
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, edge-LLM constraint metrics, teacher-controlled mutation metrics nếu có log, LLM-as-judge, latency/RAM/VRAM)
5. Kết quả, phân tích lỗi, thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **Kiến trúc đề xuất như một đóng góp thiết kế hệ thống**: Multi-Agent Agentic RAG cho hỗ trợ sư phạm kỹ thuật, tổ chức quanh Pedagogy-Constrained Orchestration, Edge-LLM-Constrained Orchestration và Pedagogy Domain Extension.
2. **Extension CNTT/lập trình cho miền sư phạm kỹ thuật**: bản hiện thực đầu tiên của Pedagogy Domain Extension, đóng gói domain knowledge, verifier, error taxonomy, feedback policy và corpus pipeline ngoài core.
3. **Prototype end-to-end**: hệ thống chạy được trên case study CNTT/lập trình với corpus nội bộ, retrieval local, verifier lập trình và teacher-controlled data mutation/review flow.
4. **Bộ benchmark sư phạm tự xây**: 130 sample (giáo án / bài tập / chấm code) với corpus nội bộ tiếng Việt — dùng để đánh giá controlled comparison và ablation.

So sánh EQ2 (optional): kiến trúc đề xuất chạy local/edge small LLM vs frontier/cloud LLM như reference upper bound — trình bày để định vị khoảng cách chất lượng trong khi vẫn giữ local-first/privacy là ràng buộc cứng, không xem cloud API là phương án triển khai của hệ thống.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5), đồng thời nêu rõ giới hạn: kết quả chứng minh giá trị của cấu hình tích hợp trong bối cảnh thử nghiệm, không chứng minh các cơ chế con là mới.

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 (và EQ2 nếu có).
- Giới hạn: không human eval diện rộng, extension mới 1 domain, LLM-as-judge bias, local/edge small LLM còn gap chất lượng so với frontier/cloud models.
- Hướng mở rộng: extension Điện tử/Cơ khí/Xây dựng, human eval, fine-tune hoặc distill LLM nhỏ trên curriculum VN, tối ưu runtime local/edge.
