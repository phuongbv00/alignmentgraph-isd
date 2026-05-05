# Đề cương 7 chương (theo template SOICT, mở rộng)

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên kỹ thuật mất nhiều giờ cho tác vụ lặp; LLM thương mại có rủi ro dữ liệu.
- Vấn đề: RAG tổng quát / generic ReAct Agentic RAG chưa tối ưu cho tác vụ sư phạm, đặc biệt khi ràng buộc local LLM nhỏ.
- Phạm vi: hệ thống desktop hỗ trợ giáo viên kỹ thuật, kiến trúc core + plugin, plugin đầu tiên cho CNTT.
- Định vị đóng góp: không claim từng cơ chế là mới; nhấn mạnh cấu hình tích hợp TTG-ARAG cho sư phạm kỹ thuật local small LLM và kiểm chứng bằng ablation.
- Mục tiêu và EQ (xem [0_context.md](refs/0_context.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case: soạn giáo án, sinh bài tập/đề, chấm bài + feedback cá nhân hoá.
- Yêu cầu phi chức năng: an toàn dữ liệu (local), hiệu năng (latency edge LLM), khả năng mở rộng plugin.
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
12. Desktop app tích hợp AI (Electron + Python IPC)
13. LLM trong giáo dục (tutoring, auto-grading, content generation, AI-assisted feedback)
14. Privacy & Local-first Deployment trong giáo dục (student data, local-first, teacher-controlled data governance)
15. Nền tảng sư phạm (Bloom's Taxonomy, Constructive Alignment)
16. Khoảng trống & định vị hệ thống

## Chương 4 — Thiết kế và triển khai hệ thống

Xem chi tiết đầy đủ tại [3_system-design.md](refs/3_system-design.md) (sections 4.1–4.8).

Tóm tắt cấu trúc:

1. Nguyên tắc HITL (ràng buộc thiết kế cứng)
2. Tổng quan kiến trúc core + plugin (sơ đồ)
3. Phân tích điểm chung / điểm riêng giữa các domain
4. Typed Task Graph Orchestration + role-scoped sub-agent invocation
5. Verification-Guided Retry/Repair
6. Plugin System + Plugin CNTT (task schema, verifier, constraint, tool)
7. Agentic Retrieval Pipeline
8. llama.cpp Integration
9. Electron Desktop App

## Chương 5 — Đánh giá hệ thống

Xem chi tiết đầy đủ tại [4_evaluation.md](refs/4_evaluation.md).

Tóm tắt cấu trúc:

1. Thiết lập thực nghiệm (hardware, mô hình, corpus, hyperparameters)
2. Bộ dữ liệu đánh giá (tự xây — 3 task × 50 mẫu)
3. Baselines + Ablation (LLM-only → Naive RAG → Generic ReAct ARAG → Fixed MA-ARAG → TTG-ARAG)
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, LLM-as-judge, tool-call/trajectory quality, latency/VRAM)
5. Kết quả, phân tích lỗi, thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **TTG-ARAG như một system/integration contribution**: kiến trúc Agentic RAG có kiểm chứng sư phạm cho đào tạo kỹ thuật trên local small LLM, thay vì claim thuật toán mới cho từng cơ chế con.
2. **Tổ hợp typed workflow + verifier-guided repair + pedagogical constraints**: giải thích cách ba nhóm kỹ thuật đã biết được ràng buộc lại thành workflow có kiểm soát cho giáo án, sinh bài tập và chấm code.
3. **Core + domain plugin cho tác vụ kỹ thuật verify được bằng máy**: plugin CNTT/lập trình là proof-of-concept, cho thấy domain knowledge, verifier, error taxonomy và feedback policy có thể được đóng gói ngoài core.
4. **Bộ benchmark sư phạm tự xây**: 130 sample (giáo án / bài tập / chấm code) với corpus nội bộ tiếng Việt — dùng để đánh giá controlled comparison và ablation.

So sánh EQ2 (optional): TTG-ARAG local vs generic agentic RAG dùng LLM lớn / commercial API — trình bày như trade-off giữa an toàn dữ liệu, khả năng tái lập và chất lượng, không phải claim tuyệt đối.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5), đồng thời nêu rõ giới hạn: kết quả chứng minh giá trị của cấu hình tích hợp trong bối cảnh thử nghiệm, không chứng minh các cơ chế con là mới.

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 (và EQ2 nếu có).
- Giới hạn: không human eval diện rộng, plugin mới 1 domain, LLM-as-judge bias, local small LLM còn gap so với frontier/cloud models.
- Hướng mở rộng: plugin Toán/Cơ khí, human eval, fine-tune LLM nhỏ trên curriculum VN, cloud mode opt-in.
