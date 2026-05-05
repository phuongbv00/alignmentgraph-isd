# Nền tảng lý thuyết & công nghệ sử dụng — Chương 3

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
- Ví dụ thực tế tiêu biểu của agentic AI trong coding assistant được trình bày ngay ở §3.3, làm cầu nối từ khái niệm sang kiến trúc hệ thống đề xuất.

## 3.3 Agentic AI trong thực tế — AI coding assistants

Đặt hệ thống vào bức tranh lớn của agentic AI tools:

- GitHub Copilot (Chen et al., 2021 — *Evaluating Large Language Models Trained on Code*): autocomplete, không agentic.
- Devin (Cognition AI, 2024): fully autonomous software engineer — agentic nhưng không local.
- **Claude Code** (Anthropic, 2025): agentic coding assistant chạy trong terminal, dùng tool (file read/write, bash, search), HITL rõ ràng (hỏi trước khi thực thi lệnh nguy hiểm). Cite official docs/product page (docs.anthropic.com/en/docs/claude-code/overview) — chưa có technical report chính thức nên không gọi là "technical report". → Hệ thống đề xuất lấy triết lý HITL + tool-use từ đây, điều chỉnh cho domain sư phạm.
- **OpenAI Codex** (OpenAI, 2025; Codex app 2026): coding agent cho software engineering, có thể xử lý nhiều task song song trong cloud sandbox/worktree, đọc/sửa file, chạy lệnh/test và đề xuất PR; mở rộng qua CLI, IDE, web/cloud và desktop app. Cite official product/blog docs (openai.com/codex; openai.com/index/introducing-codex; openai.com/index/codex-now-generally-available; openai.com/index/introducing-the-codex-app). → Dẫn chứng xu hướng multi-agent/asynchronous coding workflow, nhưng khác hệ thống đề xuất ở chỗ tập trung software engineering tổng quát và thường dựa trên frontier/cloud models.
- Cursor, Windsurf: IDE-integrated agent — cho thấy xu hướng embedded agentic AI trong desktop app.

## 3.4 Human-in-the-loop & Human-Agent Collaboration

Phần này đặt nền cho teacher-in-the-loop, override, preference memory và cơ chế phê duyệt trước khi agent tạo/chấm/sửa nội dung sư phạm.

- **LLM-based Human-Agent Systems** (Zou et al., arXiv 2505.00753 \[`Zou2025HumanAgentSurvey`\]): survey hệ thống hoá human-agent collaboration qua human feedback, human control, orchestration, interaction type và profiling; lập luận fully autonomous agent còn hạn chế về reliability, hallucination, safety và ethics.
- **Teacher-in-the-loop**: khác user-in-the-loop thông thường vì giáo viên không chỉ xác nhận output mà còn giữ quyền quyết định sư phạm: chỉnh learning objective, rubric, difficulty, tone feedback và chấp nhận/override correction.
- **Ứng dụng trong hệ thống đề xuất**: L3 Override trong §4.8/§4.10 vừa là guardrail vận hành vừa là nguồn ghi episodic/preference memory; HITL giúp cân bằng autonomy của agent với accountability của giáo viên.

## 3.5 Retrieval-Augmented Generation (RAG)

- RAG gốc: Lewis et al., 2020 — *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (NeurIPS 2020). Giải quyết hallucination + knowledge cutoff của LLM.
- Advanced RAG: query rewriting, re-ranking, HyDE (Gao et al., 2023).
- Self-RAG: Asai et al., 2023 — LLM tự quyết định khi nào cần retrieve, tự critique.
- CRAG (Corrective RAG): Yan et al., 2024 — evaluate retrieved docs, web search fallback.
- GraphRAG: Edge et al., 2024 (Microsoft) — entity graph + community summary.
- **Agentic RAG**: RAG được điều khiển bởi agent loop — multi-step retrieval, adaptive query, tool-augmented. Khác Self-RAG ở chỗ agent có thể gọi nhiều retrieval action độc lập. Survey hệ thống: Agentic RAG Survey (arXiv 2501.09136 \[`AgenticRAGSurvey2025`\]) — taxonomy theo agent cardinality, control structure, autonomy, knowledge representation.
- **A-RAG** (arXiv 2602.03442 \[`ARAG2026`\], submitted Feb 2026): hierarchical retrieval interface — agent có 3 tool (keyword search, semantic search, chunk read), chủ động quyết định granularity và số lần retrieve; là nền tảng cho thiết kế AgenticRetriever trong §4.6.
- **GraphRAG** (Edge et al., 2024 — Microsoft \[`Edge2024GraphRAG`\]): entity graph + community summary; giúp trả lời câu hỏi cần tổng hợp nhiều document (global query). Knowledge graph trong §4.6 lấy cảm hứng từ đây nhưng giới hạn ở topic dependency graph (tĩnh) để phù hợp với edge LLM.
- **Graph-based Agent Memory** (arXiv 2602.05665 \[`Yang2026GraphAgentMemory`\], submitted Feb 2026): survey taxonomy kỹ thuật memory dựa trên graph cho agent — liên quan đến KnowledgeGraphTool trong §4.6.

## 3.6 Multi-Agent Systems (MAS) với LLM

- Nền tảng lý thuyết MAS (Wooldridge & Jennings, 1995; Shoham & Leyton-Brown, *Multiagent Systems*, 2009) — briefly để đặt nền.
- LLM-based MAS: role assignment, message passing, emergent collaboration.
  - AutoGen (Wu et al., 2023 — Microsoft): conversational agent framework.
  - MetaGPT (Hong et al., 2023): role-based SOP-driven multi-agent.
  - CrewAI (2024): task delegation, hierarchical crew.
  - LangGraph (LangChain, 2024): state machine graph — **được chọn** vì tường minh, dễ visualize cho luận văn.
- **MAS Communication Survey** (arXiv 2502.14321 \[`MASCommSurvey2025`\]): "Beyond Self-Talk: A Communication-Centric Survey of LLM-Based Multi-Agent Systems" — phân loại communication patterns, coordination overhead, emergent collaboration.
- **Multi-Agent Collaboration** (arXiv 2501.06322 \[`MASCollab2025`\]): "Multi-Agent Collaboration Mechanisms: A Survey of LLMs" — taxonomy cơ chế phân công task, role assignment, message passing.
- Vấn đề của MAS: coordination overhead, context fragmentation, error propagation qua chain.

## 3.7 Agent Memory Architecture

- **Nền tảng nhận thức học**: Sumers et al. (TMLR 2024) — *Cognitive Architectures for Language Agents* \[`Sumers2024`\] hệ thống hoá taxonomy bộ nhớ agent: *working memory* (context ngắn hạn), *episodic memory* (kinh nghiệm cụ thể), *semantic memory* (kiến thức chung), *procedural memory* (kỹ năng/hành vi) — ánh xạ từ mô hình Baddeley trong tâm lý học nhận thức.
- **MemGPT** (Packer et al., NeurIPS 2023 \[`Packer2023`\]): virtual context management lấy cảm hứng từ OS paging — main context ↔ recall storage ↔ archival storage. Cho phép agent nhớ vượt context window bằng đọc/ghi có kiểm soát vào external store.
- **Survey 2024** (Zhang et al., arXiv 2404.13501 \[`Zhang2024MemSurvey`\]): phân loại cơ chế memory theo hình thức lưu trữ (in-context / external DB / model weight), thao tác (read/write/reflect), và vòng đời.
- **Survey 2026** (Du, arXiv 2603.07670 \[`Du2026MemSurvey`\], tháng 3/2026): "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers" — hệ thống hóa write–manage–read loop; taxonomy 3 chiều (temporal scope, representational substrate, control policy); 5 nhóm cơ chế: context compression, retrieval-augmented, reflective, hierarchical virtual context, policy-learned.
- **Episodic memory** (Pink et al., 2025 — arXiv 2502.06975 \[`Pink2025Episodic`\]): lập luận episodic memory là thành phần còn thiếu cho long-term agent coherence — 5 thuộc tính cần có: long-term storage, explicit reasoning, single-shot learning, instance-specific, contextual. Quan trọng khi agent cần nhớ correction và preference qua nhiều session.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.10 — 4 tầng M1–M4 ánh xạ lên taxonomy Sumers; L3 Override của HITL là cơ chế ghi episodic + preference vào long-term.

## 3.8 Context Management cho LLM Agent

- **Vấn đề**: context window hữu hạn là bottleneck của multi-step agent — history tích lũy tuyến tính dẫn đến truncation mất thông tin hoặc chi phí cao.
- **Lost in the Middle** (Liu et al., 2023 — arXiv 2307.03172 \[`Liu2023LostInMiddle`\]): LLM tận dụng thông tin ở đầu và cuối context tốt hơn ở giữa → cần sắp xếp context có chủ đích.
- **ACON** (Kang et al., 2025 — arXiv 2510.00615 \[`Kang2025ACON`\]): nén context cho long-horizon agent — giảm 26–54% peak token với > 95% accuracy; không fine-tune target agent, nhưng tối ưu guideline bằng LLM mạnh và có thể distill compressor sang model nhỏ → dùng như ý tưởng compaction/compressor cho local LLM.
- **Context-Folding** (Li et al., 2025 — arXiv 2510.11967 \[`Li2025ContextFolding`\]): nén lịch sử agent thành fold có cấu trúc, scale cho very long-horizon task.
- **Chain-of-Agents** (Zhang et al., NeurIPS 2024 — arXiv 2406.02818 \[`Zhang2024ChainOfAgents`\]): worker agents xử lý từng đoạn context tuần tự, manager tổng hợp — giải pháp khi task vượt xa context window một LLM; training-free và task-agnostic.
- **Context Engineering** (arXiv 2508.08322 \[`ContextEngineering2025`\], engineering practice / gray literature): kết hợp nhiều AI component (Intent Translator, Elicit semantic retrieval, NotebookLM synthesis, Claude Code multi-agent executor) để nâng accuracy code assistant trên multi-file project. Cite như ví dụ thực tiễn, không phải scholarly foundation về context budget; nếu cần nền học thuật về slot allocation thì dùng ACON + Lost in the Middle + Chain-of-Agents.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.9 — context budget cố định (≤ 8 192 token), conversation compaction lấy ý tưởng từ ACON, đơn giản hoá cho single local LLM.

## 3.9 LLM Agent Safety & Guardrails

- **Bối cảnh**: khi agent thực thi tool (chạy code, truy cập file), rủi ro cao hơn chatbot — cần guardrail ở nhiều tầng độc lập.
- **Prompt injection** (Perez & Ribeiro, 2022 \[`Perez2022`\]; cập nhật: arXiv 2504.11168 \[`BypassingGuardrails2025`\]): adversarial input trong dữ liệu bên ngoài (submission học viên) có thể override instruction của agent — vector tấn công thực tế.
- **LlamaGuard** (Meta, 2023 \[`LlamaGuard2023`\]): fine-tune LLM nhỏ classify input/output theo safety taxonomy — tiên phong paradigm *LLM-as-safety-classifier*.
- **AGrail** (Luo et al., ACL 2025 — arXiv 2502.11448 \[`Luo2025AGrail`\]): guardrail *lifelong* phân tách *task-specific risk* vs *systemic risk*; adaptive safety check không cần retrain khi thêm task mới.
- **ToolSafe** (Mou et al., 2026 — arXiv 2601.10156 \[`Mou2026ToolSafe`\]): guardrail *proactive step-level* ở cấp từng bước tool invocation — TS-Guard phát hiện unsafe invocation trước khi thực thi; TS-Flow giảm 65% harmful tool invocations trên ReAct agent.
- **No Free Lunch** (arXiv 2504.00441 \[`NoFreeLunch2025`\]): guardrail mạnh → false positive cao → UX xấu; cần calibrate threshold theo use case.
- **Ứng dụng trong hệ thống đề xuất**: xem §4.8 — 3 tầng (input / output / tool sandbox) theo phân loại AGrail; PytestRunner sandbox theo ToolSafe principle; threshold calibrate cho sư phạm.

## 3.10 Edge LLM & triển khai local

- Động lực: data privacy, offline capability, cost — đặc biệt quan trọng với dữ liệu học viên.
- Quantization: GGUF (llama.cpp), AWQ, GPTQ — trade-off quality vs size.
- llama.cpp (Gerganov, 2023): inference engine C++ cross-platform, Python binding — **được chọn** để nhúng trong Electron child process.
- **Gemma 3n** (Google DeepMind, 2025): E2B / E4B edge models — multimodal, offline, dưới 2.5 GB quantized. Cite Gemma 3n model card (ai.google.dev/gemma/docs/gemma-3n/model_card).
- **Gemma 4** (Google DeepMind, tháng 4/2026): E2B (2B eff params) / E4B (4B eff params) — context 128K, multimodal (vision + audio + text), function calling. Cite model card (deepmind.google/models/gemma/gemma-4). *Nếu hệ thống được build sau tháng 4/2026, ưu tiên Gemma 4; nếu build trong 2025 thì dùng Gemma 3n.*
- So sánh capability: edge LLM vs frontier LLM trên các task — nhấn gap để motivate giả thuyết typed decomposition + verifier-guided repair giúp local small LLM xử lý tác vụ sư phạm phức tạp tốt hơn generic RAG/ReAct.

## 3.11 Evaluation Methodology cho hệ thống LLM/RAG/Agent

Phần này làm nền cho thiết kế thực nghiệm ở Chương 5: không chỉ đo output cuối, mà đo cả retrieval, trajectory agent, verifier/repair và alignment với rubric sư phạm.

- **LLM-as-Judge / MT-Bench** (Zheng et al., arXiv 2306.05685 \[`Zheng2023MTBench`\], 2023): pair-wise comparison và single-answer grading bằng GPT-4 làm judge — nền tảng methodology cho đánh giá chất lượng câu trả lời, đồng thời cần kiểm soát bias vị trí/thứ tự và dùng human review cho mẫu quan trọng.
- **RAGAS** (Es et al., arXiv 2309.15217 \[`Es2023RAGAS`\], 2023): framework đánh giá RAG pipeline (faithfulness, answer relevance, context precision, context recall) — áp dụng cho benchmark retrieval/answer grounding trong §5.
- **Agent evaluation survey** (Yehudai et al., ACL Findings 2025 — arXiv 2503.16416 \[`Yehudai2025AgentEval`\]): tổng quan benchmark/framework cho planning, tool use, self-reflection, memory, web/software/scientific agents; nhấn khoảng trống về cost-efficiency, safety, robustness và fine-grained scalable evaluation.
- **TRAJECT-Bench** (He et al., arXiv 2510.04550 \[`He2025TRAJECTBench`\]): đánh giá tool-use trajectory thay vì chỉ output cuối — tool selection, argument correctness, dependency/order satisfaction; hữu ích cho đánh giá AgenticRetriever/Tool invocations.
- **Agent evaluation**: task success rate, tool-call correctness, trajectory quality, cost/latency, số vòng repair, và failure mode taxonomy — phù hợp để đánh giá agentic workflow thay vì chỉ đánh giá câu trả lời cuối.
- **Ablation study**: so sánh baseline RAG/ReAct với TTG-ARAG; tách đóng góp của typed workflow, verifier-guided repair, pedagogical constraints, memory/context compaction và HITL.
- **Human/rubric alignment**: dùng rubric giáo viên và kiểm tra độ khớp giữa automated judge với human evaluation; liên hệ với các nghiên cứu AI-assisted grading ở §3.13.

## 3.12 Desktop app tích hợp AI (Electron + Python IPC)

- Electron (GitHub, 2013–): Chromium + Node.js, cross-platform desktop. Dùng trong VS Code, Slack, Figma.
- Kiến trúc main process / renderer / child process.
- IPC patterns: `ipcMain`/`ipcRenderer`, `child_process.spawn`, JSON-line protocol.
- Python interop trong Electron: subprocess, local HTTP (FastAPI), hay stdin/stdout — trade-off latency vs complexity.
- Cite: ít bài học thuật về Electron+AI; dùng official docs + kỹ thuật từ open-source projects (ví dụ Jan.ai, LM Studio architecture).

## 3.13 LLM trong giáo dục

- Tổng quan: Kasneci et al., 2023 — *ChatGPT for Good? On Opportunities and Challenges of LLMs for Education* (Learning and Individual Differences).
- Tutoring & Q&A: Khanmigo (Khan Academy + GPT-4), survey của Mogavi et al., 2024.
- Auto-grading code: Phung et al., 2023 (SIGCSE); Cipriano & Alves, 2023.
- Content generation (bài tập, giáo án): Malinka et al., 2023; Doughty et al., 2024 (L@S).
- AI-assisted feedback: Ba et al., 2025 — systematic review trên 129 nghiên cứu, phân loại feedback theo task/process/self-regulation/self và mức độ complexity; dùng để đặt nền cho feedback sư phạm có rubric, không chỉ sinh lời giải.
- Rủi ro & ethics: academic integrity, bias, over-reliance (Baidoo-Anu & Owusu Ansah, 2023).
- **LLM grading assessment** (Saez, Garcia, Mochon & Isasi, *Scientific Reports*, published 18 Apr 2026 \[`Saez2026LLMGrading`\]): "Evaluating large language models for AI-assisted grading: a framework and case study in higher education" — DOI 10.1038/s41598-026-48656-3; hợp đề tài nếu hệ thống có rubric/feedback.
- **Gap**: nhiều hệ thống giáo dục dùng commercial LLM hoặc chatbot/RAG tổng quát; các thành phần như retrieval, agent workflow, verifier, HITL và ràng buộc sư phạm đã có tiền lệ riêng lẻ. Khoảng trống của đề tài là thiếu một cấu hình tích hợp được đánh giá có kiểm soát cho tác vụ sư phạm kỹ thuật, chạy trên local small LLM, dùng dữ liệu giáo viên nội bộ và có ablation để tách đóng góp của typed workflow, verifier/repair và pedagogical constraints.

## 3.14 Privacy & Local-first Deployment trong giáo dục

Phần này chuyển động lực "local" từ lựa chọn triển khai thành yêu cầu thiết kế: dữ liệu học viên, rubric nội bộ và học liệu giáo viên cần được kiểm soát trong môi trường của nhà trường/giáo viên.

- **Privacy risks in LLM/LLM agents**: prompt, retrieved document, submission học viên và log tool execution đều có thể chứa dữ liệu nhạy cảm; cần phân biệt data minimization, local processing, access control và audit log.
- **Small Models, Big Support** (Reza et al., arXiv 2506.05925 \[`Reza2025SmallModels`\]): framework local small LLM 3B–7B cho educator-centric content creation và assessment, kết hợp RAG/CAG, teacher-in-the-loop và verifier LLM; rất gần với định vị local-first, private, affordable cho giáo dục.
- **Trade-off**: local small LLM tăng privacy/offline/cost control nhưng giảm capability so với frontier models; vì vậy cần typed workflow, retrieval có kiểm soát, verifier-guided repair, HITL và evaluation/ablation.
- **Ứng dụng trong hệ thống đề xuất**: dữ liệu giáo viên và submission học viên ưu tiên xử lý local; chỉ dùng external/cloud model như baseline hoặc tùy chọn đánh giá, không phải phụ thuộc mặc định.

## 3.15 Nền tảng sư phạm

- Bloom's Taxonomy (Bloom et al., 1956; revised Anderson & Krathwohl, 2001) — 6 cấp độ nhận thức: Remember → Understand → Apply → Analyze → Evaluate → Create. Dùng để gán metadata chunk và calibrate exercise difficulty.
- Constructive Alignment (Biggs, 1996; Biggs & Tang, 2011) — learning objectives → teaching activities → assessment phải thống nhất. Cơ sở lý luận cho `LessonPlannerAgent`.
- Learning objectives well-formed (Mager, 1962) — SMART objectives dùng action verb theo Bloom. Dùng trong prompt template của `LessonPlannerAgent`.
- CS education misconceptions (Sorva, 2012 — *Visual Program Simulation*; Qian & Lehman, 2017) — cơ sở cho `error_taxonomy` của Plugin CNTT.

## 3.16 Khoảng trống & định vị hệ thống

Bảng so sánh tổng hợp: hệ thống đề xuất vs các công trình liên quan trên các chiều: local LLM / agentic workflow / verifier-guided repair / HITL / domain plugin / pedagogical awareness / desktop deployment / memory layers / guardrails.

Phần này phải nêu rõ: đề tài không claim từng chiều trong bảng là mới; đóng góp nằm ở cấu hình tích hợp TTG-ARAG cho bối cảnh sư phạm kỹ thuật local small LLM và cách đánh giá controlled comparison + ablation.

---

**Nguồn**: arXiv, ACL/EMNLP/NAACL, NeurIPS/ICML (cho LLM), AIED/L@S/LAK/SIGCSE và Computers & Education/Scientific Reports (cho edu/evaluation), Anthropic/OpenAI official docs/product pages. Target ≥ 50 citation.
