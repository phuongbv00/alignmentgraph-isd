# Đề cương 7 chương (theo template SOICT, mở rộng)

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên kỹ thuật mất nhiều giờ cho tác vụ lặp; LLM thương mại có rủi ro dữ liệu.
- Vấn đề: RAG tổng quát / generic ReAct Agentic RAG chưa tối ưu cho tác vụ sư phạm, đặc biệt khi ràng buộc local LLM nhỏ.
- Phạm vi: hệ thống desktop hỗ trợ giáo viên kỹ thuật, kiến trúc core + plugin, plugin đầu tiên cho CNTT.
- Mục tiêu và EQ (xem [0_context.md](refs/0_context.md)).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case: soạn giáo án, sinh bài tập/đề, chấm bài + feedback cá nhân hoá.
- Yêu cầu phi chức năng: an toàn dữ liệu (local), hiệu năng (latency edge LLM), khả năng mở rộng plugin.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG) — xác định gap.

## Chương 3 — Nền tảng lý thuyết & công nghệ sử dụng

Xem chi tiết 10 subsection tại [2_lit-review.md](refs/2_lit-review.md).

Tóm tắt cấu trúc (13 subsection):

1. Large Language Models (LLM)
2. AI Agent vs Agentic AI — phân biệt khái niệm
3. Retrieval-Augmented Generation (RAG)
4. Multi-Agent Systems (MAS) với LLM
5. Agent Memory Architecture (MemGPT, Sumers taxonomy, episodic memory)
6. Context Management cho LLM Agent (ACON, Lost in the Middle, Chain-of-Agents)
7. LLM Agent Safety & Guardrails (AGrail, ToolSafe, prompt injection)
8. Agentic AI trong thực tế — AI coding assistants (Claude Code, Devin, Cursor)
9. Edge LLM & triển khai local
10. Desktop app tích hợp AI (Electron + Python IPC)
11. LLM trong giáo dục
12. Nền tảng sư phạm (Bloom's Taxonomy, Constructive Alignment)
13. Khoảng trống & định vị hệ thống

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
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, LLM-as-judge, latency/VRAM)
5. Kết quả, phân tích lỗi, thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **Typed Task Graph Orchestration cho giáo dục kỹ thuật**: workflow sư phạm được mô hình hóa thành graph node có schema, tool scope, retrieval policy, verifier, retry policy và stop condition.
2. **Verification-Guided Retry/Repair trên local small LLM**: lỗi từ verifier được cấu trúc hóa để sửa đúng component lỗi thay vì regenerate toàn bộ output.
3. **Pedagogy-Constrained Agentic RAG**: tích hợp Bloom alignment, constructive alignment, citation coverage, rubric consistency, misconception mapping, feedback policy và HITL vào pipeline sinh nội dung.
4. **Bộ benchmark sư phạm tự xây**: 130 sample (giáo án / bài tập / chấm code) với corpus nội bộ tiếng Việt — tái sử dụng được cho các nghiên cứu tiếp theo.

So sánh EQ2 (optional): TTG-ARAG local vs generic agentic RAG dùng LLM lớn / commercial API — trình bày như trade-off giữa an toàn dữ liệu, khả năng tái lập và chất lượng, không phải claim tuyệt đối.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5).

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 (và EQ2 nếu có).
- Giới hạn: không human eval diện rộng, plugin mới 1 domain, LLM-as-judge bias.
- Hướng mở rộng: plugin Toán/Cơ khí, human eval, fine-tune LLM nhỏ trên curriculum VN, cloud mode opt-in.
