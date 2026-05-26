# Chương 2 — Background and Related Work

Chương này đặt luận văn vào giao điểm của **Instructional Systems Design**, **Adaptive Learning Systems** và **Agentic AI Systems**. Thứ tự trình bày được đổi từ "kỹ thuật AI trước, giáo dục sau" sang mạch khái niệm phù hợp hơn với đóng góp chính là **Adaptive Instructional Design Agent Harness**:

```text
Learning Theory
  -> Instructional Systems
  -> Adaptive Learning / ITS
  -> Educational Agents
  -> Agentic Orchestration
  -> Research Gap
```

Mục tiêu của chương không phải chứng minh LLM hữu ích trong giáo dục nói chung. Mục tiêu là xác định vì sao một adaptive instructional system hiện đại cần một harness instructional-design-specific: learner-state-aware memory, assessment-driven diagnosis, intervention policy, reassessment, workflow execution và evaluation semantics.

## 2.1 Định vị nghiên cứu

Luận văn không được định vị như một nghiên cứu về "AI trong giáo dục", "multi-agent RAG cho học tập", hay "LLM hỗ trợ đào tạo" theo nghĩa công cụ tạo sinh. Định vị chính là:

```text
AI-mediated Instructional Systems -> Adaptive Instructional Design Agent Harness
```

Theo định vị này, pedagogy không phải contribution chính tách rời. Pedagogy là grounding giúp xác định lifecycle, semantics và constraints của hệ thống. Đóng góp chính thuộc tầng computer science: một harness điều phối agent cho instructional design thích ứng, có learner-state-aware orchestration, workflow execution, trace, schema constraint và benchmark adapters.

| Thành phần | Vai trò trong luận văn |
| --- | --- |
| Instructional Systems Design | định nghĩa instructional lifecycle, alignment và evaluation semantics |
| Adaptive Learning / ITS | biện minh cho learner modeling, remediation và adaptive sequencing |
| Agentic AI Systems | cung cấp cơ chế planning, memory, tool use, workflow execution và reflective refinement |
| Pedagogy | grounding cho workflow, constraint và rubric đánh giá |
| Computing contribution | Adaptive Instructional Design Agent Harness |

Vocabulary của luận văn cũng được điều chỉnh theo hướng system-oriented:

| Cách gọi cũ | Cách gọi mới |
| --- | --- |
| teaching strategy | orchestration policy |
| learner progress | learner state |
| feedback | adaptive signal |
| redesign | policy refinement |
| tutoring flow | instructional workflow |
| personalization | adaptive orchestration |

Vì vậy, hệ thống đề xuất không được xem như "một multi-agent framework cho giáo dục", mà là **an Adaptive Instructional Design Agent Harness**: một execution framework cho instructional workflow có trạng thái, kiểm soát được và có thể đánh giá bằng benchmark adapters.

## 2.2 Learning Theory và Instructional Systems Design

Instructional Systems Design (ISD) cung cấp ngôn ngữ nền để mô tả dạy học như một hệ thống có lifecycle, input, output, evidence và refinement. Các framework như **ADDIE**, **Dick & Carey**, **Gagné's events of instruction** và **4C/ID** đều nhấn mạnh rằng instruction không chỉ là nội dung, mà là chuỗi quyết định liên kết giữa mục tiêu, hoạt động, điều kiện triển khai, đánh giá và cải tiến.

- **ADDIE** cung cấp lifecycle phân tích, thiết kế, phát triển, triển khai và đánh giá. Trong luận văn, ADDIE được dùng để neo ý tưởng rằng instructional workflow cần trạng thái và vòng cải tiến, không phải artifact generation một lần.
- **Dick & Carey** xem instruction như một system có mục tiêu, learner analysis, performance objectives, assessment instruments, instructional strategy, formative evaluation và revision. Đây là cơ sở trực tiếp cho việc đặt assessment, diagnosis và intervention trong cùng một loop.
- **Gagné** nhấn mạnh sequencing của events of instruction, giúp đánh giá tính hợp lý của activity order, scaffold và instructional intervention.
- **4C/ID** hữu ích với các miền kỹ năng phức hợp như lập trình, nơi instruction cần whole-task practice, supportive information, procedural information và part-task practice.

Một số construct sư phạm được dùng như alignment constraints và evaluation semantics:

- **Bloom's Taxonomy** (Bloom et al., 1956; Anderson & Krathwohl, 2001) giúp gán mức nhận thức cho objective, activity và assessment.
- **Constructive Alignment** (Biggs, 1996; Biggs & Tang, 2011) yêu cầu learning objectives, teaching activities và assessment cùng đo một năng lực.
- **Backward Design / Understanding by Design** (Wiggins & McTighe, 1998; 2005) đặt assessment evidence trước khi chọn hoạt động dạy học.
- **Formative Assessment Cycle** (Black & Wiliam, 1998) và **Data-Driven Instruction** (Bambrick-Santoyo, 2010) cung cấp foundation cho closed-loop learning:

```text
Assessment -> Diagnosis -> Intervention -> Reassessment
```

- **Differentiated Instruction** (Tomlinson, 2001; 2014) biện minh cho việc điều chỉnh instruction theo readiness, interest, learning profile và misconception, nhưng trong luận văn được giới hạn ở class-level learner state.
- **Learning objectives well-formed** (Mager, 1962) hỗ trợ kiểm tra objective có observable verb, condition và criterion.
- **CS education misconceptions** (Sorva, 2012; Qian & Lehman, 2017) cung cấp taxonomy lỗi cho case study Computer Science, nhưng không định nghĩa phạm vi benchmark chính của luận văn.

Điểm quan trọng là các lý thuyết trên không phải contribution mới của luận văn. Chúng định nghĩa **instructional workflow**, **evaluation semantics**, **adaptation logic** và **alignment constraints** để hệ thống agentic có thể vận hành có kiểm soát.

## 2.3 Adaptive Learning Systems và Intelligent Tutoring Systems

Intelligent Tutoring Systems (ITS) và Adaptive Learning Systems đặt nền cho việc mô hình hoá learner state và điều chỉnh instruction dựa trên bằng chứng. Một ITS cổ điển thường gồm domain model, learner model, tutoring/pedagogical model và interface model. Adaptive learning mở rộng hướng này bằng adaptive sequencing, remediation, feedback timing, mastery tracking và personalization.

Các khái niệm liên quan trực tiếp đến luận văn:

- **Learner modeling**: biểu diễn kiến thức, misconception, readiness, strength và evidence của người học; trong luận văn, biểu diễn này được gom ở cấp lớp.
- **Adaptive sequencing**: chọn hoặc điều chỉnh hoạt động tiếp theo dựa trên learner state thay vì theo syllabus tĩnh.
- **Remediation loop**: dùng assessment evidence để chẩn đoán lỗi và đề xuất can thiệp.
- **Longitudinal adaptation**: duy trì learner state qua nhiều phiên, nhiều assessment và nhiều instructional decisions.

Luận văn kế thừa tư duy learner modeling và remediation của ITS, nhưng không xây một dialogue tutor cho từng học viên. Đơn vị chính của hệ thống là **teacher-facing instructional workflow** ở mức lớp. Vì vậy, learner state được biểu diễn bằng `ClassLearningProfile`, được cập nhật qua assessment/feedback evidence và teacher-in-the-loop, rồi dùng lại để điều phối UC-ID và UC-FB.

Khoảng trống từ góc nhìn adaptive learning là nhiều hệ thống vẫn thiếu persistent state theo lớp, thiếu cơ chế refinement kéo dài qua nhiều phiên, hoặc chỉ điều chỉnh nội dung mà không điều phối toàn bộ workflow assessment -> diagnosis -> intervention -> reassessment.

## 2.4 Educational Agents và LLM trong instructional workflows

Các nghiên cứu về LLM trong giáo dục có thể chia thành bốn dòng chính:

1. tổng quan cơ hội/rủi ro của ChatGPT và LLM trong giáo dục (Kasneci et al., 2023; Mogavi et al., 2024), bao gồm tutoring, content generation, academic integrity, bias và over-reliance;
2. teacher-facing lesson planning và content creation, gần với UC-ID;
3. submission evaluation, grading và feedback, gần với UC-FB;
4. tutor benchmarks/student-facing systems, hữu ích để mượn construct như guidance quality, adaptivity và misconception handling, nhưng khác user và task surface của luận văn.

Các paper/phương pháp gần với luận văn:

| Công trình | Đối tượng đánh giá | Điểm liên quan | Khoảng cách với luận văn |
| --- | --- | --- | --- |
| **LessonPlanner** (arXiv 2408.01102) | lesson-plan support cho novice teachers | gần UC-ID, pedagogy-driven lesson plan, usability | thiếu closed-loop assessment -> profile -> intervention |
| **Automatic Lesson Plan Generation via LLMs with Self-critique Prompting** (2024) | sinh lesson plan và chấm bằng educator rubric | cung cấp construct lesson-plan quality | chủ yếu là prompt/self-critique, chưa có learner-state-aware memory |
| **Teaching-plan enhancement through simulation** (npj Science of Learning, 2025) | reflection và refinement qua mô phỏng teacher-student | gần với plan refinement | refinement một artifact, chưa là longitudinal orchestration |
| **Small Models, Big Support** (arXiv 2506.05925) | local LLM cho teacher-centric content creation và assessment | gần local-first, privacy, verifier và teacher-in-the-loop | chưa định vị rõ như orchestration framework có typed workflow và learner-state loop |
| **AI-assisted grading framework** (Scientific Reports, 2026) | grading trong higher education | gần UC-FB, rubric consistency, explainability | không nối grading/feedback sang instructional intervention |
| **Automatic feedback generation evaluation** (Computers and Education: AI, 2024) | đánh giá feedback tự động | feedback helpfulness, specificity, alignment | không bao phủ instructional workflow nhiều phiên |
| **Pedagogy Benchmark** (arXiv 2506.18710) | pedagogical knowledge của LLM | bổ sung construct kiến thức sư phạm | đánh giá knowledge QA hơn là orchestration |

**ISD-Agent-Bench** được dùng trong luận văn như benchmark chính cho nhánh instructional design: nó cho thấy instructional agents, pedagogical evaluation và theory-grounded orchestration đã trở thành một hướng nghiên cứu hợp lệ. Thay vì xây một benchmark instructional design mới, luận văn thiết kế adapter để chạy Adaptive Instructional Design Agent Harness trên các benchmark có sẵn và so sánh với baseline dưới cùng điều kiện model/judge khi khả thi.

Gap của nhóm educational agents là các thành phần như lesson planning, feedback, retrieval, verifier và HITL đã có tiền lệ riêng lẻ, nhưng còn thiếu một harness tích hợp để duy trì closed-loop instructional refinement qua nhiều phiên và expose được workflow trace cho đánh giá.

## 2.5 Agentic AI Systems và harness engineering

LLM cung cấp năng lực ngôn ngữ, reasoning và generation, nhưng bản thân model chưa phải một instructional system. Luận văn sử dụng công thức làm việc:

```text
Agent = Model + Harness
```

Trong đó, **harness** là toàn bộ phần code, cấu hình và execution logic bao quanh model: state, tool execution, retrieval, memory, orchestration, policy, logging, sandbox, verifier, permission và feedback loop. Raw model trở thành agent khi được đặt trong một execution environment có khả năng duy trì trạng thái, gọi tool, tuân thủ ràng buộc và chạy workflow nhiều bước.

Các capability cốt lõi của harness:

1. **Durable storage**: lưu state qua nhiều phiên và nhiều task.
2. **Tool execution / sandbox**: gọi tool trong môi trường kiểm soát.
3. **Memory & context injection**: quản lý long-term/working memory và inject đúng phần cần thiết.
4. **Orchestration logic**: điều phối task graph, role assignment, transition rule và retry.
5. **Context management**: tạo bounded context pack, compaction và slot allocation.
6. **Deterministic enforcement hooks**: schema validation, guardrails, HITL, verifier và commit gate.

Các agentic tools trong thực tế minh hoạ pattern này. Claude Code và OpenAI Codex không chỉ là model mạnh hơn, mà là coding harness có file system, terminal, sandbox, test runner, HITL và workspace memory. NotebookLM và Perplexity là research/knowledge harness với retrieval, citation và source-grounded synthesis. Tương tự, **Adaptive Instructional Design Agent Harness** đặt LLM vào một instructional systems harness: tool layer là retrieval/verifier/profile synthesis, memory là program/class/session memory, constraint là Bloom/rubric/constructive alignment/feedback policy, và execution loop là assessment-driven instructional refinement.

## 2.6 Retrieval, memory, context và deployment cho instructional systems

Retrieval-Augmented Generation (RAG) là nền tảng kỹ thuật quan trọng nhưng không phải identity của luận văn. RAG gốc (Lewis et al., 2020) giải quyết hallucination và knowledge cutoff bằng external corpus; Advanced RAG bổ sung query rewriting, reranking, HyDE; Self-RAG và CRAG cho phép model tự critique hoặc sửa retrieval; GraphRAG dùng entity graph và community summary; Agentic RAG cho phép agent chủ động chọn nhiều retrieval action.

Trong luận văn, retrieval là một cơ chế phục vụ orchestration:

- đưa curriculum, rubric, lecture material và assessment material vào `ContextPack`;
- hỗ trợ grounding cho artifact;
- mở rộng query theo learner state và misconception;
- cung cấp evidence cho verifier và judge.

Memory architecture là thành phần quan trọng hơn RAG đơn thuần vì closed-loop learning cần state bền vững. Các nghiên cứu về cognitive architectures for language agents (Sumers et al., 2024), MemGPT (Packer et al., 2023), agent memory surveys (Zhang et al., 2024; Du, 2026) và episodic memory (Pink et al., 2025) cho thấy agent dài hạn cần phân biệt working, episodic, semantic và procedural memory. Luận văn ánh xạ taxonomy này thành bốn scope:

| Scope | Cognitive type | Vai trò trong thesis |
| --- | --- | --- |
| `SessionMemory` | working | trạng thái workflow tức thời |
| `ClassMemory` | episodic -> local semantic | diagnosis, artifact log và `ClassLearningProfile` của một lớp |
| `ProgramMemory` | semantic | syllabus, material library và cross-class insights |
| `GlobalMemory` | procedural | preference và teaching style của giáo viên |

Context management cũng là yêu cầu bắt buộc vì context window hữu hạn. Các hướng như Lost in the Middle (Liu et al., 2023), ACON (Kang et al., 2025), Context-Folding (Li et al., 2025) và Chain-of-Agents (Zhang et al., 2024) cho thấy long-horizon agent cần compaction, ordering và context allocation có chủ đích. Trong hệ thống đề xuất, harness chịu trách nhiệm tạo bounded context pack thay vì đẩy toàn bộ conversation history vào prompt.

Về deployment, luận văn giữ thiết kế LLM-agnostic. Prototype có thể chạy với cloud/frontier API hoặc local/edge SLM qua llama.cpp, GGUF/AWQ/GPTQ và các model families như Gemma, Phi, Qwen. Local-first deployment được xem như yêu cầu thiết kế quan trọng trong giáo dục vì dữ liệu học viên, rubric nội bộ và submission có tính nhạy cảm.

## 2.7 Multi-agent workflow coordination

Luận văn dùng multi-agent như một cơ chế tổ chức workflow, không định vị contribution là "multi-agent cho giáo dục". Nền tảng multi-agent systems (Wooldridge & Jennings, 1995; Shoham & Leyton-Brown, 2009) cung cấp khái niệm role, coordination và interaction. LLM-based MAS như AutoGen, MetaGPT, CrewAI và LangGraph/LangGraph.js cho thấy có thể triển khai role-based hoặc graph-based agent workflows.

Tuy nhiên, một ReAct agent hoặc MAS tự do không đủ cho instructional systems vì các quyết định quan trọng cần kiểm soát được:

- output phải có schema để commit vào memory;
- assessment result phải được chuyển thành diagnosis có evidence;
- profile update phải qua HITL;
- verifier failure phải kích hoạt targeted repair;
- orchestration trace phải đo được để phục vụ evaluation.

Vì vậy, luận văn chọn hướng **graph-based orchestration**: agent node có role rõ, input/output schema rõ, quyền tool rõ và transition rule rõ. Đây là cơ chế kỹ thuật để biến closed-loop learning thành workflow có thể chạy, log, kiểm tra và đánh giá.

## 2.8 Human governance, safety và alignment constraints

Teacher-in-the-loop không chỉ là một tuỳ chọn UI. Trong hệ thống này, giáo viên giữ accountability cuối cùng với learning objective, rubric, difficulty, feedback tone và profile update. HITL vừa là guardrail vận hành, vừa là nguồn memory: override của giáo viên có thể ghi preference vào `GlobalMemory` hoặc correction cụ thể vào `ClassMemory`.

Các nghiên cứu về LLM-based Human-Agent Systems (Zou et al., 2025) nhấn mạnh vai trò human feedback, control, orchestration và profiling, đặc biệt khi fully autonomous agent còn có rủi ro reliability, hallucination, safety và ethics. Với agent có tool execution, các rủi ro như prompt injection (Perez & Ribeiro, 2022), unsafe tool invocation, data leakage và false-positive guardrail càng cần được kiểm soát. Các hướng như LlamaGuard, AGrail, ToolSafe và các nghiên cứu về guardrail calibration cung cấp nền cho thiết kế nhiều lớp: input guard, output guard, schema validation, sandbox verifier và commit gate.

Trong bối cảnh giáo dục, alignment constraints gồm Bloom alignment, constructive alignment, rubric consistency, feedback policy, non-harmful adaptation và evidence faithfulness. Những constraint này không thay thế giáo viên; chúng tạo điểm kiểm tra tất định để agentic workflow không biến thành chuỗi generation không kiểm soát.

## 2.9 Evaluation methodology cho adaptive pedagogical agents

Đánh giá hệ thống agentic instructional không thể chỉ đo output cuối bằng impression chung. Cần đo cả artifact quality, schema compliance, grounding, trajectory, verifier/repair, learner-state adaptation và alignment với rubric sư phạm.

Các nền tảng phương pháp:

- **LLM-as-Judge / MT-Bench** (Zheng et al., 2023): pairwise/single-answer grading bằng model judge; cần blind judging, random order và human subset để kiểm soát bias.
- **RAGAS** (Es et al., 2023): faithfulness, answer relevance, context precision và context recall cho pipeline retrieval.
- **Agent evaluation survey** (Yehudai et al., 2025): task success, tool use, planning, self-reflection, memory, cost-efficiency, safety và robustness.
- **TRAJECT-Bench** (He et al., 2025): đánh giá tool-use trajectory thay vì chỉ output cuối.
- **Teacher-facing evaluation literature**: lesson-plan quality, actionability, teacher usability, grading explainability, feedback helpfulness và misconception handling.
- **ISD-Agent-Bench**: benchmark/reference quan trọng cho instructional agents và pedagogical evaluation, dùng làm một target chính của benchmark adapter cho RQ1.

Protocol ở Chương 4 vì vậy dùng benchmark adapters tới các benchmark instructional-design/adaptive-tutoring hiện có, chạy controlled comparison trên cùng model, output schema trung gian và judge khi khả thi; không lấy trực tiếp published score từ các paper có dataset/task/model khác làm baseline số học.

## 2.10 Khoảng trống nghiên cứu và định vị hệ thống

Từ các nhóm nghiên cứu trên, khoảng trống chính của luận văn là:

```text
Learner-state-aware Memory
  + Longitudinal Adaptation
  + Closed-loop Pedagogical Refinement
  + Theory-grounded Agent Orchestration
```

Các hệ thống hiện có thường mạnh ở một phần: sinh lesson plan, tạo rubric, chấm bài, sinh feedback, retrieval, self-critique hoặc tutor dialogue. Tuy nhiên, chúng thường chưa tích hợp thành một adaptive instructional system có learner-state-aware memory, closed-loop execution và orchestration grounded bằng ISD.

| Chiều so sánh | Teacher-facing SOTA papers | Generic agent/RAG frameworks | Adaptive Instructional Design Agent Harness đề xuất |
| --- | --- | --- | --- |
| Đối tượng chính | lesson plan, content, grading, feedback | general task completion | adaptive instructional workflow |
| Learner state | thường là input context cục bộ | user/project memory tổng quát | `ClassLearningProfile` trong `ClassMemory` |
| Vòng lặp | thường xử lý một artifact hoặc một task | task loop tổng quát | Assessment -> Diagnosis -> Intervention -> Reassessment |
| Orchestration | prompt pipeline/self-critique | ReAct/MAS task-agnostic | typed graph với policy, verifier, HITL và commit |
| Pedagogical grounding | rubric hoặc expert review theo paper | policy chung | ISD, Bloom, constructive alignment, formative assessment |
| Evaluation | paper-specific rubric | task success/tool correctness | artifact quality + workflow trace + learner-state adaptation |

Đề tài không claim từng thành phần riêng lẻ là mới. Đóng góp nằm ở **Adaptive Instructional Design Agent Harness**: cấu hình hệ thống tích hợp memory, workflow, assessment-driven diagnosis, intervention policy, HITL governance, schema/trace và benchmark adapters để hiện thực hoá bước tiến từ static instructional workflow sang adaptive instructional systems.

---

**Nguồn nền**: ISD/learning theory, adaptive learning/ITS, AIED/L@S/LAK/SIGCSE, Computers & Education, ACL/EMNLP/NAACL, NeurIPS/ICML, agent evaluation literature và official docs/product pages cho các agent harness thực tế.
