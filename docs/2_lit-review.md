# Nền tảng lý thuyết & công nghệ sử dụng — Chương 3

*(Thứ tự: technical thuần → ứng dụng kỹ thuật vào giáo dục → lý thuyết sư phạm)*

## 3.1 Large Language Models (LLM)

Nền tảng kỹ thuật của toàn hệ thống. Cần trình bày đủ để người đọc không chuyên AI vẫn hiểu phần sau.

- Transformer architecture (Vaswani et al., 2017 — *Attention Is All You Need*).
- Pre-training & instruction tuning: GPT series (Brown et al., 2020), InstructGPT (Ouyang et al., 2022).
- Emergent capabilities & scaling laws (Kaplan et al., 2020; Wei et al., 2022 — *Emergent Abilities of LLMs*).
- Giới hạn nội tại: hallucination, knowledge cutoff, context window — motivate cho RAG.
- Edge SLM / small LLM: Gemma, Phi, Qwen; local inference, quantization GGUF/AWQ/GPTQ, và triển khai on-device/edge-hosted. Dùng "Edge SLM" khi nhấn vào mô hình nhỏ chạy local/edge; dùng "Edge LLM" như nhãn bao quát cho mô hình ngôn ngữ triển khai tại biên.

## 3.2 AI Agent vs Agentic AI — phân biệt khái niệm

Phần này cần định nghĩa rõ vì nhiều bài dùng lẫn lộn:

- **AI Agent** (truyền thống): thực thể percept → act trong môi trường (Russell & Norvig, *Artificial Intelligence: A Modern Approach*, 4th ed. 2020). Định nghĩa hẹp — agent như NPC, robot, rule-based system.
- **LLM-based Agent**: LLM làm "brain" — reasoning, planning, tool use (ReAct: Yao et al., 2023; Toolformer: Schick et al., 2023).
- **Agentic AI** (rộng hơn): LLM hoạt động với autonomy cao, multi-step, long-horizon task, tự quyết định khi nào dùng tool nào (Shinn et al., 2023 — *Reflexion*; Wang et al., 2024 — *A Survey on LLM-based Autonomous Agents*).
- Phân biệt: AI Agent = một instance; Agentic AI = paradigm/cách vận hành tự chủ. Hệ thống này thuộc **Agentic AI** với kiến trúc multi-agent.
- **Quan hệ Agent = Model + Harness**: LLM đơn thuần là model, chưa phải agent. Agent hình thành khi LLM được kết hợp với một harness cung cấp tool, memory, constraint enforcement và execution loop. Đây là nền tảng định vị đóng góp của luận văn: thiết kế harness, không phải thiết kế model.
- Khái niệm harness được làm rõ ở §3.3; ví dụ thực tế tiêu biểu được trình bày ở §3.4, làm cầu nối từ khái niệm sang kiến trúc hệ thống đề xuất.

## 3.3 Agent Harness Engineering

Mục này làm nền lý thuyết trực tiếp cho contribution của luận văn: Pedagogy Agent Harness là đóng góp ở tầng infrastructure — thiết kế harness, không phải model hay algorithm.

- **Định nghĩa** (LangChain, 2026 \[`LangChain2026HarnessAnatomy`\] — *"The Anatomy of an Agent Harness"*): harness là "every piece of code, configuration, and execution logic that isn't the model itself". Raw model trở thành agent khi được trang bị harness với state, tool execution, feedback loops và enforceable constraints.
- **6 capability cốt lõi của harness**:
  1. *Durable storage* — state persistence xuyên suốt task execution
  2. *Code execution / sandbox* — tool invocation trong môi trường an toàn và cô lập
  3. *Memory & context injection* — long-term và working memory do harness quản lý và inject vào từng invocation
  4. *Orchestration logic* — task graph, workflow, role assignment quyết định luồng thực thi
  5. *Context management* — bounded context pack, compaction, slot allocation (trách nhiệm của harness, không phải model)
  6. *Hooks for deterministic behavior enforcement* — HITL, guardrails, constraint checks được thực thi tại các điểm xác định trong pipeline
- **Harness vs framework**: framework là thư viện/API developer gọi từ code; harness là execution environment bao quanh model — bao gồm runtime, policy enforcement và extension mechanism. Phân biệt quan trọng để định vị contribution: harness là infrastructure-level, không phải application-level.
- **Harness engineering như infrastructure contribution**: thiết kế harness cho domain cụ thể tương tự platform engineering (OS, compiler, database engine) — contribution là môi trường biến model thành agent có năng lực domain-specific, không phải model mới hay algorithm mới.
- **Ánh xạ lên Pedagogy Agent Harness**: hai ràng buộc thiết kế cứng map trực tiếp lên 6 capability: (1) pedagogical constraint enforcement map lên capability #6 (hooks for deterministic behavior enforcement); (2) domain extensibility qua plugin interface map lên capability #4 (orchestration + extension mechanism). Ví dụ thực tế xem §3.4.

## 3.4 Agentic AI trong thực tế — AI coding assistants và analogy với Pedagogy Agent Harness

Đặt hệ thống vào bức tranh lớn của agentic AI tools. Phần này minh họa pattern Agent = Model + Harness qua các ví dụ coding agent thực tế — định nghĩa harness và 6 capability đã trình bày ở §3.3.

- GitHub Copilot (Chen et al., 2021 — *Evaluating Large Language Models Trained on Code*): autocomplete, không agentic.
- Devin (Cognition AI, 2024): fully autonomous software engineer — agentic nhưng không có HITL.
- **Claude Code** (Anthropic, 2025): Claude model + coding harness (tool: file read/write, bash, search; HITL: hỏi trước khi thực thi lệnh nguy hiểm; execution loop; MCP extensibility) = Claude Code agent. Cite official docs/product page (docs.anthropic.com/en/docs/claude-code/overview). → **Analogy chính**: harness biến Claude (model) thành Claude Code (agent); tương tự, Pedagogy Agent Harness biến LLM thành Pedagogy Agent. Tool layer thay bằng retrieval/verifier/rubric-checker; constraint thay bằng Bloom/rubric/HITL; extensibility thay bằng domain plugin interface.
- **OpenAI Codex** (OpenAI, 2025; Codex app 2026): GPT + coding harness (sandbox, worktree, file ops, test runner) = Codex agent. Cite official product/blog docs (openai.com/codex). → Minh chứng thêm cho pattern Model + Harness = Agent; khác hệ thống đề xuất ở domain (software engineering vs. pedagogy) và user (developer vs. teacher).
- Cursor, Windsurf: IDE-integrated agent — cho thấy xu hướng embedded agentic AI trong desktop app.
- **Tóm tắt analogy (Agent = Model + Harness)**:

| Chiều | Coding agent (Claude Code/Codex) | Pedagogy Agent (đề xuất) |
|---|---|---|
| Model | Claude / GPT | Pluggable LLM |
| Tool layer | file read/write, bash, search | retrieval, verifier, rubric-checker |
| Constraint | safe execution, HITL | Bloom/rubric alignment, HITL |
| Context management | context window + compaction | bounded context pack |
| Deterministic enforcement | hooks for behavior enforcement | teacher-in-the-loop, pedagogical constraints |
| Extensibility | MCP servers | domain plugin interface |
| User | Developer | Teacher |

## 3.5 Human-in-the-loop & Human-Agent Collaboration

Phần này đặt nền cho teacher-in-the-loop, override, preference memory và cơ chế phê duyệt trước khi agent tạo/chấm/sửa nội dung sư phạm.

- **LLM-based Human-Agent Systems** (Zou et al., arXiv 2505.00753 \[`Zou2025HumanAgentSurvey`\]): survey hệ thống hoá human-agent collaboration qua human feedback, human control, orchestration, interaction type và profiling; lập luận fully autonomous agent còn hạn chế về reliability, hallucination, safety và ethics.
- **Teacher-in-the-loop**: khác user-in-the-loop thông thường vì giáo viên không chỉ xác nhận output mà còn giữ quyền quyết định sư phạm: chỉnh learning objective, rubric, difficulty, tone feedback và chấp nhận/override correction.
- **Ứng dụng trong hệ thống đề xuất**: HITL override vừa là guardrail vận hành vừa là nguồn ghi episodic/preference memory; HITL giúp cân bằng autonomy của Pedagogy Agent với accountability của giáo viên.

## 3.6 Retrieval-Augmented Generation (RAG)

- RAG gốc: Lewis et al., 2020 — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (NeurIPS 2020). Giải quyết hallucination + knowledge cutoff của LLM.
- Advanced RAG: query rewriting, re-ranking, HyDE (Gao et al., 2023).
- Self-RAG: Asai et al., 2023 — LLM tự quyết định khi nào cần retrieve, tự critique.
- CRAG (Corrective RAG): Yan et al., 2024 — evaluate retrieved docs, web search fallback.
- GraphRAG: Edge et al., 2024 (Microsoft) — entity graph + community summary.
- **Agentic RAG**: RAG được điều khiển bởi agent loop — multi-step retrieval, adaptive query, tool-augmented. Khác Self-RAG ở chỗ agent có thể gọi nhiều retrieval action độc lập. Survey hệ thống: Agentic RAG Survey (arXiv 2501.09136 \[`AgenticRAGSurvey2025`\]) — taxonomy theo agent cardinality, control structure, autonomy, knowledge representation.
- **A-RAG** (arXiv 2602.03442 \[`ARAG2026`\], submitted Feb 2026): hierarchical retrieval interface — agent có 3 tool (keyword search, semantic search, chunk read), chủ động quyết định granularity và số lần retrieve.
- **GraphRAG** (Edge et al., 2024 — Microsoft \[`Edge2024GraphRAG`\]): entity graph + community summary; giúp trả lời câu hỏi cần tổng hợp nhiều document (global query).
- **Graph-based Agent Memory** (arXiv 2602.05665 \[`Yang2026GraphAgentMemory`\], submitted Feb 2026): survey taxonomy kỹ thuật memory dựa trên graph cho agent.

## 3.7 Multi-Agent Systems (MAS) với LLM

- Nền tảng lý thuyết MAS (Wooldridge & Jennings, 1995; Shoham & Leyton-Brown, *Multiagent Systems*, 2009) — briefly để đặt nền.
- LLM-based MAS: role assignment, message passing, emergent collaboration.
  - AutoGen (Wu et al., 2023 — Microsoft): conversational agent framework.
  - MetaGPT (Hong et al., 2023): role-based SOP-driven multi-agent.
  - CrewAI (2024): task delegation, hierarchical crew.
  - LangGraph (LangChain, 2024): state machine graph — **được chọn** vì tường minh, dễ visualize cho luận văn.
- **MAS Communication Survey** (arXiv 2502.14321 \[`MASCommSurvey2025`\]): "Beyond Self-Talk: A Communication-Centric Survey of LLM-Based Multi-Agent Systems" — phân loại communication patterns, coordination overhead, emergent collaboration.
- **Multi-Agent Collaboration** (arXiv 2501.06322 \[`MASCollab2025`\]): "Multi-Agent Collaboration Mechanisms: A Survey of LLMs" — taxonomy cơ chế phân công task, role assignment, message passing.
- Vấn đề của MAS: coordination overhead, context fragmentation, error propagation qua chain.

## 3.8 Agent Memory Architecture

- **Nền tảng nhận thức học**: Sumers et al. (TMLR 2024) — *Cognitive Architectures for Language Agents* \[`Sumers2024`\] hệ thống hoá taxonomy bộ nhớ agent: *working memory* (context ngắn hạn), *episodic memory* (kinh nghiệm cụ thể), *semantic memory* (kiến thức chung), *procedural memory* (kỹ năng/hành vi) — ánh xạ từ mô hình Baddeley trong tâm lý học nhận thức.
- **MemGPT** (Packer et al., NeurIPS 2023 \[`Packer2023`\]): virtual context management lấy cảm hứng từ OS paging — main context ↔ recall storage ↔ archival storage. Cho phép agent nhớ vượt context window bằng đọc/ghi có kiểm soát vào external store.
- **Survey 2024** (Zhang et al., arXiv 2404.13501 \[`Zhang2024MemSurvey`\]): phân loại cơ chế memory theo hình thức lưu trữ (in-context / external DB / model weight), thao tác (read/write/reflect), và vòng đời.
- **Survey 2026** (Du, arXiv 2603.07670 \[`Du2026MemSurvey`\], tháng 3/2026): "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers" — hệ thống hóa write–manage–read loop; taxonomy 3 chiều (temporal scope, representational substrate, control policy); 5 nhóm cơ chế: context compression, retrieval-augmented, reflective, hierarchical virtual context, policy-learned.
- **Episodic memory** (Pink et al., 2025 — arXiv 2502.06975 \[`Pink2025Episodic`\]): lập luận episodic memory là thành phần còn thiếu cho long-term agent coherence — 5 thuộc tính cần có: long-term storage, explicit reasoning, single-shot learning, instance-specific, contextual. Quan trọng khi agent cần nhớ correction và preference qua nhiều session.
- **Ứng dụng trong hệ thống đề xuất**: 4 tầng memory ánh xạ lên taxonomy Sumers; HITL override là cơ chế ghi episodic + preference vào long-term.

## 3.9 Context Management cho LLM Agent

- **Vấn đề**: context window hữu hạn là bottleneck của multi-step agent — history tích lũy tuyến tính dẫn đến truncation mất thông tin hoặc chi phí cao.
- **Lost in the Middle** (Liu et al., 2023 — arXiv 2307.03172 \[`Liu2023LostInMiddle`\]): LLM tận dụng thông tin ở đầu và cuối context tốt hơn ở giữa → cần sắp xếp context có chủ đích.
- **ACON** (Kang et al., 2025 — arXiv 2510.00615 \[`Kang2025ACON`\]): nén context cho long-horizon agent — giảm 26–54% peak token với > 95% accuracy; không fine-tune target agent, nhưng tối ưu guideline bằng LLM mạnh và có thể distill compressor sang model nhỏ → dùng như ý tưởng compaction/compressor cho local LLM.
- **Context-Folding** (Li et al., 2025 — arXiv 2510.11967 \[`Li2025ContextFolding`\]): nén lịch sử agent thành fold có cấu trúc, scale cho very long-horizon task.
- **Chain-of-Agents** (Zhang et al., NeurIPS 2024 — arXiv 2406.02818 \[`Zhang2024ChainOfAgents`\]): worker agents xử lý từng đoạn context tuần tự, manager tổng hợp — giải pháp khi task vượt xa context window một LLM; training-free và task-agnostic.
- **Context Engineering** (arXiv 2508.08322 \[`ContextEngineering2025`\], engineering practice / gray literature): kết hợp nhiều AI component để nâng accuracy code assistant trên multi-file project. Cite như ví dụ thực tiễn, không phải scholarly foundation về context budget; nếu cần nền học thuật về slot allocation thì dùng ACON + Lost in the Middle + Chain-of-Agents.
- **Ứng dụng trong hệ thống đề xuất**: context budget được quản lý trong harness — bounded context pack theo từng agent invocation, compaction lấy ý tưởng từ ACON.

## 3.10 LLM Agent Safety & Guardrails

- **Bối cảnh**: khi agent thực thi tool (chạy code, truy cập file), rủi ro cao hơn chatbot — cần guardrail ở nhiều tầng độc lập.
- **Prompt injection** (Perez & Ribeiro, 2022 \[`Perez2022`\]; cập nhật: arXiv 2504.11168 \[`BypassingGuardrails2025`\]): adversarial input trong dữ liệu bên ngoài (submission học viên) có thể override instruction của agent — vector tấn công thực tế.
- **LlamaGuard** (Meta, 2023 \[`LlamaGuard2023`\]): fine-tune LLM nhỏ classify input/output theo safety taxonomy — tiên phong paradigm *LLM-as-safety-classifier*.
- **AGrail** (Luo et al., ACL 2025 — arXiv 2502.11448 \[`Luo2025AGrail`\]): guardrail *lifelong* phân tách *task-specific risk* vs *systemic risk*; adaptive safety check không cần retrain khi thêm task mới.
- **ToolSafe** (Mou et al., 2026 — arXiv 2601.10156 \[`Mou2026ToolSafe`\]): guardrail *proactive step-level* ở cấp từng bước tool invocation — TS-Guard phát hiện unsafe invocation trước khi thực thi; TS-Flow giảm 65% harmful tool invocations trên ReAct agent.
- **No Free Lunch** (arXiv 2504.00441 \[`NoFreeLunch2025`\]): guardrail mạnh → false positive cao → UX xấu; cần calibrate threshold theo use case.
- **Ứng dụng trong hệ thống đề xuất**: 3 tầng guardrail (input / output / tool sandbox) theo phân loại AGrail; verifier sandbox theo ToolSafe principle; threshold calibrate cho sư phạm.

## 3.11 LLM Deployment Options — context cho prototype

Phần này cung cấp bối cảnh về các lựa chọn triển khai LLM; harness không coupled với provider cụ thể nhưng prototype cần chọn một LLM để chạy thực nghiệm.

- **Phổ lựa chọn**: cloud/frontier API (GPT-4o, Claude, Gemini) → self-hosted local model → edge/on-device model. Mỗi lựa chọn có trade-off khác nhau về capability, privacy, cost và offline capability.
- **Privacy motivation**: dữ liệu học viên, rubric nội bộ và học liệu giáo viên nhạy cảm — local deployment giảm rủi ro data leakage mà không cần thay đổi kiến trúc harness.
- **LLM-agnostic design của harness**: harness giao tiếp với LLM qua interface chuẩn (OpenAI-compatible API); việc chuyển đổi provider chỉ cần thay đổi config, không thay đổi orchestration logic.
- **Lựa chọn cho prototype**:
  - Local inference: llama.cpp (Gerganov, 2023) — inference engine C++ cross-platform; GGUF quantization; chạy như sidecar process.
  - Model families phù hợp cho local: Gemma 4 E2B/E4B (Google DeepMind, 2026), Phi series (Microsoft), Qwen small models — cite model cards/official docs.
  - Cloud API dùng làm baseline/reference nếu cần so sánh chất lượng.
- **Quantization**: GGUF/AWQ/GPTQ — giảm RAM/VRAM nhưng có thể ảnh hưởng quality ở reasoning dài hoặc tiếng Việt chuyên ngành; cần ghi rõ cấu hình trong thiết lập thực nghiệm.
- **Nguồn**: model card/official docs từ Google, Microsoft, Qwen; llama.cpp repo; blog industry như `DigitalApplied2026SLMBusiness` chỉ dùng để framing xu hướng, không dùng làm nguồn benchmark.

## 3.12 Evaluation Methodology cho hệ thống LLM/RAG/Agent

Phần này làm nền cho thiết kế thực nghiệm ở Chương 5: không chỉ đo output cuối, mà đo cả retrieval, trajectory agent, verifier/repair và alignment với rubric sư phạm.

- **LLM-as-Judge / MT-Bench** (Zheng et al., arXiv 2306.05685 \[`Zheng2023MTBench`\], 2023): pair-wise comparison và single-answer grading bằng GPT-4 làm judge — nền tảng methodology cho đánh giá chất lượng câu trả lời, đồng thời cần kiểm soát bias vị trí/thứ tự và dùng human review cho mẫu quan trọng.
- **RAGAS** (Es et al., arXiv 2309.15217 \[`Es2023RAGAS`\], 2023): framework đánh giá RAG pipeline (faithfulness, answer relevance, context precision, context recall) — áp dụng cho benchmark retrieval/answer grounding trong §5.
- **Agent evaluation survey** (Yehudai et al., ACL Findings 2025 — arXiv 2503.16416 \[`Yehudai2025AgentEval`\]): tổng quan benchmark/framework cho planning, tool use, self-reflection, memory, web/software/scientific agents; nhấn khoảng trống về cost-efficiency, safety, robustness và fine-grained scalable evaluation.
- **TRAJECT-Bench** (He et al., arXiv 2510.04550 \[`He2025TRAJECTBench`\]): đánh giá tool-use trajectory thay vì chỉ output cuối — tool selection, argument correctness, dependency/order satisfaction; hữu ích cho đánh giá AgenticRetriever/Tool invocations.
- **Agent evaluation**: task success rate, tool-call correctness, trajectory quality, cost/latency, số vòng repair, và failure mode taxonomy — phù hợp để đánh giá agentic workflow thay vì chỉ đánh giá câu trả lời cuối.
- **Ablation study**: so sánh baseline RAG/ReAct với Pedagogy Agent Harness; tách đóng góp của typed workflow, verifier-guided repair, pedagogical constraints và HITL.
- **Human/rubric alignment**: dùng rubric giáo viên và kiểm tra độ khớp giữa automated judge với human evaluation; liên hệ với các nghiên cứu AI-assisted grading ở §3.14.

## 3.13 Desktop app tích hợp AI (Tauri + HTTP server + SSE)

- **Tauri** (Tauri Apps, 2021–): Rust backend + OS native webview (WebView2/WebKit), cross-platform desktop; bundle size và RAM footprint nhỏ hơn Electron vì không bundle Chromium. Dùng trong các app desktop nhẹ, privacy-aware.
- Kiến trúc: webview frontend (web tech) giao tiếp với Rust backend qua Tauri commands; Rust backend quản lý process lifecycle của Python/native sidecar.
- **HTTP + SSE pattern**: orchestration backend chạy như HTTP server cục bộ (LangGraph dev server, localhost); UI gửi task qua REST, nhận stream trạng thái/output qua SSE; HITL decision gửi về qua HTTP POST để resume.
- So với Electron: Tauri đơn giản hơn về process isolation vì backend là HTTP server độc lập — UI không cần biết gì về Python runtime; Python interop qua HTTP thay vì `child_process` Node.js.
- Cite: ít bài học thuật về Tauri+AI; dùng official Tauri docs + kỹ thuật từ open-source projects (ví dụ Jan.ai, LM Studio architecture cho local AI desktop app pattern).

## 3.14 LLM trong giáo dục

- Tổng quan: Kasneci et al., 2023 — *ChatGPT for Good? On Opportunities and Challenges of LLMs for Education* (Learning and Individual Differences).
- Tutoring & Q&A: Khanmigo (Khan Academy + GPT-4), survey của Mogavi et al., 2024.
- Auto-grading code: Phung et al., 2023 (SIGCSE); Cipriano & Alves, 2023.
- Content generation (bài tập, giáo án): Malinka et al., 2023; Doughty et al., 2024 (L@S).
- AI-assisted feedback: Ba et al., 2025 — systematic review trên 129 nghiên cứu, phân loại feedback theo task/process/self-regulation/self và mức độ complexity; dùng để đặt nền cho feedback sư phạm có rubric, không chỉ sinh lời giải.
- Rủi ro & ethics: academic integrity, bias, over-reliance (Baidoo-Anu & Owusu Ansah, 2023).
- **LLM grading assessment** (Saez, Garcia, Mochon & Isasi, *Scientific Reports*, published 18 Apr 2026 \[`Saez2026LLMGrading`\]): "Evaluating large language models for AI-assisted grading: a framework and case study in higher education" — DOI 10.1038/s41598-026-48656-3; hợp đề tài nếu hệ thống có rubric/feedback.
- **Gap**: nhiều hệ thống giáo dục dùng commercial LLM hoặc chatbot/RAG tổng quát; các thành phần như retrieval, agent workflow, verifier, HITL và ràng buộc sư phạm đã có tiền lệ riêng lẻ. Khoảng trống của đề tài là thiếu một harness tích hợp được đánh giá có kiểm soát — kết hợp với LLM tạo thành Pedagogy Agent — dùng dữ liệu giáo viên nội bộ, hỗ trợ nhiều domain qua plugin interface và có ablation để tách đóng góp của typed workflow, verifier/repair và pedagogical constraints.

## 3.15 Privacy & Local-first Deployment trong giáo dục

Phần này chuyển động lực "local" từ lựa chọn triển khai thành yêu cầu thiết kế: dữ liệu học viên, rubric nội bộ và học liệu giáo viên cần được kiểm soát trong môi trường của nhà trường/giáo viên.

- **Privacy risks in LLM/LLM agents**: prompt, retrieved document, submission học viên và log tool execution đều có thể chứa dữ liệu nhạy cảm; cần phân biệt data minimization, local processing, access control và audit log.
- **Small Models, Big Support** (Reza et al., arXiv 2506.05925 \[`Reza2025SmallModels`\]): framework local small LLM 3B–7B cho educator-centric content creation và assessment, kết hợp RAG/CAG, teacher-in-the-loop và verifier LLM; rất gần với định vị local-first, private, affordable cho giáo dục.
- **Trade-off**: local deployment tăng privacy/offline control nhưng có thể giảm capability so với frontier models — harness thiết kế LLM-agnostic để giáo viên chọn deployment phù hợp; typed workflow, retrieval có kiểm soát, verifier-guided repair và HITL giúp bù đắp capability gap khi dùng model nhỏ hơn.
- **Ứng dụng trong hệ thống đề xuất**: harness không coupled với provider; dữ liệu giáo viên và submission học viên ưu tiên xử lý local; LLM provider là cấu hình triển khai, không phải dependency cứng của kiến trúc.

## 3.16 Nền tảng sư phạm

- Bloom's Taxonomy (Bloom et al., 1956; revised Anderson & Krathwohl, 2001) — 6 cấp độ nhận thức: Remember → Understand → Apply → Analyze → Evaluate → Create. Dùng để gán metadata chunk và calibrate exercise difficulty.
- Constructive Alignment (Biggs, 1996; Biggs & Tang, 2011) — learning objectives → teaching activities → assessment phải thống nhất. Cơ sở lý luận cho AlignmentRole và task graph design trong harness.
- Learning objectives well-formed (Mager, 1962) — SMART objectives dùng action verb theo Bloom. Dùng trong prompt template của role-scoped agent invocations.
- CS education misconceptions (Sorva, 2012 — *Visual Program Simulation*; Qian & Lehman, 2017) — cơ sở cho `error_taxonomy` của CNTT extension.
- Math misconceptions (literature-based) — cơ sở cho `error_taxonomy` của Toán extension (computation error, wrong method, missing step, conceptual error).

## 3.17 Khoảng trống & định vị hệ thống

Bảng so sánh tổng hợp: Pedagogy Agent Harness đề xuất vs các công trình liên quan trên các chiều: agentic workflow / verifier-guided repair / HITL / domain plugin / pedagogical awareness / desktop deployment / memory layers / guardrails / LLM-agnostic design.

Hai chiều differentiation chính:
1. **Harness framing (Agent = Model + Harness)**: hệ thống định vị là harness — kết hợp với LLM tạo thành Pedagogy Agent — thay vì application. Contribution là thiết kế harness (tool layer, constraints, HITL, extensibility), không phải LLM hay tính năng sư phạm cụ thể.
2. **Domain extensibility với 2 case study**: CNTT và Toán cùng implement domain plugin interface → bằng chứng thực nghiệm về tính tổng quát của interface, không chỉ là design claim.

Phần này phải nêu rõ: đề tài không claim từng chiều trong bảng là mới; đóng góp nằm ở cấu hình tích hợp của harness cho bối cảnh sư phạm và bằng chứng thực nghiệm qua controlled comparison + ablation trên hai domain.

---

**Nguồn**: arXiv, ACL/EMNLP/NAACL, NeurIPS/ICML (cho LLM), AIED/L@S/LAK/SIGCSE và Computers & Education/Scientific Reports (cho edu/evaluation), Anthropic/OpenAI official docs/product pages. Target ≥ 50 citation.
