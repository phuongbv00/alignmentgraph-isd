---
name: thesis-context
description: This skill should be used whenever the user discusses, asks about, or works on the MSc thesis about Multi-Agent Agentic RAG. Activate when the user mentions "luận văn", "thesis", "chương", "RAG", "multi-agent", "hệ thống", "kiến trúc", or any chapter/section of the thesis. Also activate when working on LaTeX files in this project, planning milestones, or writing literature review content.
version: 1.0.0
---

# Thesis Context — Multi-Agent Agentic RAG

## Quy tắc load file

Đọc file theo nhu cầu thực tế — không load tất cả mỗi lần:

| File                 | Đường dẫn                                       | Load khi nào                                                                                          |
| -------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `0_context.md`       | `${CLAUDE_PLUGIN_ROOT}/refs/0_context.md`       | **Luôn luôn** — quyết định đã chốt, cấu trúc chương, template                                         |
| `1_outline.md`       | `${CLAUDE_PLUGIN_ROOT}/refs/1_outline.md`       | Khi thảo luận cấu trúc chương, thêm/sửa nội dung bất kỳ chương                                        |
| `2_lit-review.md`    | `${CLAUDE_PLUGIN_ROOT}/refs/2_lit-review.md`    | Chỉ khi làm việc với **Chương 3** (lý thuyết, citations, subsections)                                 |
| `3_system-design.md` | `${CLAUDE_PLUGIN_ROOT}/refs/3_system-design.md` | Chỉ khi làm việc với **Chương 4** (kiến trúc, HITL, core MAS, plugin, retrieval, llama.cpp, Electron) |
| `4_evaluation.md`    | `${CLAUDE_PLUGIN_ROOT}/refs/4_evaluation.md`    | Chỉ khi làm việc với **Chương 5** (benchmark, metrics, baselines, ablation, kết quả)                  |

## Quy tắc áp dụng sau khi đọc

- Trả lời bằng **tiếng Việt** trừ khi được yêu cầu khác.
- LaTeX: bám sát preamble và cấu trúc trong `0_context.md`; không tự ý đổi compiler, font, margin.
- Mọi thay đổi cấu trúc chương phải cập nhật đồng thời `0_context.md`, `1_outline.md`, và `main.tex`.
- Đóng góp novelty **chưa chốt** — không claim từng cơ chế như typed graph, verifier/repair, constraint generation, plugin hay HITL là mới độc lập; chỉ trình bày ở mức system/integration contribution và chờ kết quả thực nghiệm để xác nhận.
- Mọi thiết kế hệ thống phải tôn trọng nguyên tắc HITL trong `3_system-design.md`.
- Citation: BibLaTeX key dạng `AuthorYYYY` — không bịa reference.
