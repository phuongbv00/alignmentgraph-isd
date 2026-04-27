# Tổng quan tài liệu — Chương 3

*(Thứ tự: technical thuần → ứng dụng kỹ thuật vào giáo dục → lý thuyết sư phạm)*

## 3.1 Large Language Models (LLM)

Nền tảng kỹ thuật của toàn hệ thống. Cần trình bày đủ để người đọc không chuyên AI vẫn hiểu phần sau.

- Transformer architecture (Vaswani et al., 2017 — *Attention Is All You Need*).
- Pre-training & instruction tuning: GPT series (Brown et al., 2020), InstructGPT (Ouyang et al., 2022).
- Emergent capabilities & scaling laws (Kaplan et al., 2020; Wei et al., 2022 — *Emergent Abilities of LLMs*).
- Giới hạn nội tại: hallucination, knowledge cutoff, context window — motivate cho RAG.
- Edge/small LLM: Gemma (Google DeepMind, 2024), Phi series (Microsoft), quantization GGUF/AWQ (llama.cpp — Gerganov 2023).

## 3.2 AI Agent vs Agentic AI — phân biệt khái niệm

Phần này cần định nghĩa rõ vì nhiều bài dùng lẫn lộn:

- **AI Agent** (truyền thống): thực thể percept → act trong môi trường (Russell & Norvig, *Artificial Intelligence: A Modern Approach*, 4th ed. 2020). Định nghĩa hẹp — agent như NPC, robot, rule-based system.
- **LLM-based Agent**: LLM làm "brain" — reasoning, planning, tool use (ReAct: Yao et al., 2023; Toolformer: Schick et al., 2023).
- **Agentic AI** (rộng hơn): LLM hoạt động với autonomy cao, multi-step, long-horizon task, tự quyết định khi nào dùng tool nào (Shinn et al., 2023 — *Reflexion*; Wang et al., 2024 — *A Survey on LLM-based Autonomous Agents*).
- Phân biệt: AI Agent = một instance; Agentic AI = paradigm/cách vận hành tự chủ. Hệ thống này thuộc **Agentic AI** với kiến trúc multi-agent.
- **Claude Code** (Anthropic, 2025) — dẫn chứng flagship của agentic AI trong thực tế: agent thao tác file system, chạy terminal, gọi tool, tự lặp lại qua nhiều bước để hoàn thành task lập trình. Là nguồn cảm hứng thiết kế cho hệ thống đề xuất.

## 3.3 Retrieval-Augmented Generation (RAG)

- RAG gốc: Lewis et al., 2020 — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (NeurIPS 2020). Giải quyết hallucination + knowledge cutoff của LLM.
- Advanced RAG: query rewriting, re-ranking, HyDE (Gao et al., 2023).
- Self-RAG: Asai et al., 2023 — LLM tự quyết định khi nào cần retrieve, tự critique.
- CRAG (Corrective RAG): Yan et al., 2024 — evaluate retrieved docs, web search fallback.
- GraphRAG: Edge et al., 2024 (Microsoft) — entity graph + community summary.
- **Agentic RAG**: RAG được điều khiển bởi agent loop — multi-step retrieval, adaptive query, tool-augmented. Khác Self-RAG ở chỗ agent có thể gọi nhiều retrieval action độc lập. Survey hệ thống: Agentic RAG Survey (arXiv 2501.09136 \[`AgenticRAGSurvey2025`\]) — taxonomy theo agent cardinality, control structure, autonomy, knowledge representation.
- **A-RAG** (arXiv 2602.03442 \[`ARAG2025`\]): hierarchical retrieval interface — agent có 3 tool (keyword search, semantic search, chunk read), chủ động quyết định granularity và số lần retrieve; là nền tảng cho thiết kế AgenticRetriever trong §4.6.
- **GraphRAG** (Edge et al., 2024 — Microsoft \[`Edge2024GraphRAG`\]): entity graph + community summary; giúp trả lời câu hỏi cần tổng hợp nhiều document (global query). Knowledge graph trong §4.6 lấy cảm hứng từ đây nhưng giới hạn ở topic dependency graph (tĩnh) để phù hợp với edge LLM.
- **Graph-based Agent Memory** (arXiv 2602.05665 \[`GraphAgentMemory2025`\]): dùng KG làm tầng memory có cấu trúc cho agent — liên quan đến KnowledgeGraphTool trong §4.6.

## 3.4 Multi-Agent Systems (MAS) với LLM

- Nền tảng lý thuyết MAS (Wooldridge & Jennings, 1995; Shoham & Leyton-Brown, *Multiagent Systems*, 2009) — briefly để đặt nền.
- LLM-based MAS: role assignment, message passing, emergent collaboration.
  - AutoGen (Wu et al., 2023 — Microsoft): conversational agent framework.
  - MetaGPT (Hong et al., 2023): role-based SOP-driven multi-agent.
  - CrewAI (2024): task delegation, hierarchical crew.
  - LangGraph (LangChain, 2024): state machine graph — **được chọn** vì tường minh, dễ visualize cho luận văn.
- Vấn đề của MAS: coordination overhead, context fragmentation, error propagation qua chain.

## 3.5 Agent Memory Architecture

- **Nền tảng nhận thức học**: Sumers et al. (TMLR 2024) — *Cognitive Architectures for Language Agents* \[`Sumers2024`\] hệ thống hoá taxonomy bộ nhớ agent: *working memory* (context ngắn hạn), *episodic memory* (kinh nghiệm cụ thể), *semantic memory* (kiến thức chung), *procedural memory* (kỹ năng/hành vi) — ánh xạ từ mô hình Baddeley trong tâm lý học nhận thức.
- **MemGPT** (Packer et al., NeurIPS 2023 \[`Packer2023`\]): virtual context management lấy cảm hứng từ OS paging — main context ↔ recall storage ↔ archival storage. Cho phép agent nhớ vượt context window bằng đọc/ghi có kiểm soát vào external store.
- **Survey 2024** (Zhang et al., arXiv 2404.13501 \[`Zhang2024MemSurvey`\]): phân loại cơ chế memory theo hình thức lưu trữ (in-context / external DB / model weight), thao tác (read/write/reflect), và vòng đời.
- **Survey 2025** (Zhang et al., arXiv 2603.07670 \[`Zhang2025MemSurvey`\]): cập nhật mới nhất; benchmark MemBench; phân tích factual vs reflective memory và scalability.
- **Episodic memory** (Vo et al., 2025 — arXiv 2502.06975 \[`Vo2025Episodic`\]): lập luận episodic memory là thành phần còn thiếu cho long-term agent coherence — quan trọng khi agent cần nhớ correction và preference qua nhiều session.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.10 — 4 tầng M1–M4 ánh xạ lên taxonomy Sumers; L3 Override của HITL là cơ chế ghi episodic + preference vào long-term.

## 3.6 Context Management cho LLM Agent

- **Vấn đề**: context window hữu hạn là bottleneck của multi-step agent — history tích lũy tuyến tính dẫn đến truncation mất thông tin hoặc chi phí cao.
- **Lost in the Middle** (Liu et al., 2023 — arXiv 2307.03172 \[`Liu2023LostInMiddle`\]): LLM tận dụng thông tin ở đầu và cuối context tốt hơn ở giữa → cần sắp xếp context có chủ đích.
- **ACON** (Kang et al., 2025 — arXiv 2510.00615 \[`Kang2025ACON`\]): nén context gradient-free cho long-horizon agent — giảm 26–54% peak token với > 95% accuracy; không cần fine-tune → dùng được trực tiếp với local LLM.
- **Context-Folding** (Li et al., 2025 — arXiv 2510.11967 \[`Li2025ContextFolding`\]): nén lịch sử agent thành fold có cấu trúc, scale cho very long-horizon task.
- **Chain-of-Agents** (Liu et al., ICLR 2025 \[`Liu2024ChainOfAgents`\]): worker agents xử lý từng đoạn context, manager tổng hợp — giải pháp khi task vượt xa context window một LLM.
- **Context Engineering** (arXiv 2508.08322 \[`ContextEngineering2025`\]): phân bổ tường minh budget cho từng slot (system prompt / retrieved chunks / history / instruction / output reserve) trong multi-agent code assistant.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.9 — context budget cố định (≤ 8 192 token), conversation compaction lấy ý tưởng từ ACON, đơn giản hoá cho single local LLM.

## 3.7 LLM Agent Safety & Guardrails

- **Bối cảnh**: khi agent thực thi tool (chạy code, truy cập file), rủi ro cao hơn chatbot — cần guardrail ở nhiều tầng độc lập.
- **Prompt injection** (Perez & Ribeiro, 2022 \[`Perez2022`\]; cập nhật: arXiv 2504.11168 \[`BypassingGuardrails2025`\]): adversarial input trong dữ liệu bên ngoài (submission học viên) có thể override instruction của agent — vector tấn công thực tế.
- **LlamaGuard** (Meta, 2023 \[`LlamaGuard2023`\]): fine-tune LLM nhỏ classify input/output theo safety taxonomy — tiên phong paradigm *LLM-as-safety-classifier*.
- **AGrail** (Luo et al., ACL 2025 — arXiv 2502.11448 \[`Luo2025AGrail`\]): guardrail *lifelong* phân tách *task-specific risk* vs *systemic risk*; adaptive safety check không cần retrain khi thêm task mới.
- **ToolSafe** (Zhang et al., 2025 — arXiv 2601.10156 \[`Zhang2025ToolSafe`\]): guardrail *proactive step-level* ở cấp từng bước tool invocation — kiểm tra trước khi tool thực thi.
- **No Free Lunch** (arXiv 2504.00441 \[`NoFreeLunch2025`\]): guardrail mạnh → false positive cao → UX xấu; cần calibrate threshold theo use case.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.8 — 3 tầng (input / output / tool sandbox) theo phân loại AGrail; PytestRunner sandbox theo ToolSafe principle; threshold calibrate cho sư phạm.

## 3.8 Agentic AI trong thực tế — AI coding assistants

Đặt hệ thống vào bức tranh lớn của agentic AI tools:

- GitHub Copilot (Chen et al., 2021 — *Evaluating Large Language Models Trained on Code*): autocomplete, không agentic.
- Devin (Cognition AI, 2024): fully autonomous software engineer — agentic nhưng không local.
- **Claude Code** (Anthropic, 2025): agentic coding assistant chạy trong terminal, dùng tool (file read/write, bash, search), HITL rõ ràng (hỏi trước khi thực thi lệnh nguy hiểm). Cite technical report/blog post của Anthropic. → Hệ thống đề xuất lấy triết lý HITL + tool-use từ đây, nhưng điều chỉnh cho domain sư phạm thay vì coding.
- Cursor, Windsurf: IDE-integrated agent — cho thấy xu hướng embedded agentic AI trong desktop app.

## 3.9 Edge LLM & triển khai local

- Động lực: data privacy, offline capability, cost — đặc biệt quan trọng với dữ liệu học viên.
- Quantization: GGUF (llama.cpp), AWQ, GPTQ — trade-off quality vs size.
- llama.cpp (Gerganov, 2023): inference engine C++ cross-platform, Python binding — **được chọn** để nhúng trong Electron child process.
- Gemma 4 (Google DeepMind, 2025): E2B (2B params) / E4B (4B params) — edge-optimized, multimodal. Cite model card / technical report.
- So sánh capability: edge LLM vs frontier LLM trên các task — nhấn gap để motivate giả thuyết typed decomposition + verifier-guided repair giúp local small LLM xử lý tác vụ sư phạm phức tạp tốt hơn generic RAG/ReAct.

## 3.10 Desktop app tích hợp AI (Electron + Python IPC)

- Electron (GitHub, 2013–): Chromium + Node.js, cross-platform desktop. Dùng trong VS Code, Slack, Figma.
- Kiến trúc main process / renderer / child process.
- IPC patterns: `ipcMain`/`ipcRenderer`, `child_process.spawn`, JSON-line protocol.
- Python interop trong Electron: subprocess, local HTTP (FastAPI), hay stdin/stdout — trade-off latency vs complexity.
- Cite: ít bài học thuật về Electron+AI; dùng official docs + kỹ thuật từ open-source projects (ví dụ Jan.ai, LM Studio architecture).

## 3.11 LLM trong giáo dục

- Tổng quan: Kasneci et al., 2023 — *ChatGPT for Good? On Opportunities and Challenges of LLMs for Education* (Learning and Individual Differences).
- Tutoring & Q&A: Khanmigo (Khan Academy + GPT-4), survey của Mogavi et al., 2024.
- Auto-grading code: Phung et al., 2023 (SIGCSE); Cipriano & Alves, 2023.
- Content generation (bài tập, giáo án): Malinka et al., 2023; Doughty et al., 2024 (L@S).
- Rủi ro & ethics: academic integrity, bias, over-reliance (Baidoo-Anu & Owusu Ansah, 2023).
- **Gap**: hầu hết dùng commercial LLM (GPT-4), không local; không có multi-agent; không HITL rõ ràng → khoảng trống hệ thống đề xuất lấp.

## 3.12 Nền tảng sư phạm

- Bloom's Taxonomy (Bloom et al., 1956; revised Anderson & Krathwohl, 2001) — 6 cấp độ nhận thức: Remember → Understand → Apply → Analyze → Evaluate → Create. Dùng để gán metadata chunk và calibrate exercise difficulty.
- Constructive Alignment (Biggs, 1996; Biggs & Tang, 2011) — learning objectives → teaching activities → assessment phải thống nhất. Cơ sở lý luận cho `LessonPlannerAgent`.
- Learning objectives well-formed (Mager, 1962) — SMART objectives dùng action verb theo Bloom. Dùng trong prompt template của `LessonPlannerAgent`.
- CS education misconceptions (Sorva, 2012 — *Visual Program Simulation*; Qian & Lehman, 2017) — cơ sở cho `error_taxonomy` của Plugin CNTT.

## 3.13 Khoảng trống & định vị hệ thống

Bảng so sánh tổng hợp: hệ thống đề xuất vs các công trình liên quan trên các chiều: local LLM / multi-agent / HITL / domain plugin / pedagogical awareness / desktop deployment / memory layers / guardrails.

---

**Nguồn**: arXiv, ACL/EMNLP/NAACL, NeurIPS/ICML (cho LLM), AIED/L@S/LAK/SIGCSE (cho edu), Anthropic technical reports. Target ≥ 50 citation.
