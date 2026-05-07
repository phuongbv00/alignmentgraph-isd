# Thiết kế và triển khai hệ thống -- Chương 4

## 4.1 Mục tiêu thiết kế và phạm vi hệ thống

- Thiết kế hệ thống hỗ trợ giáo viên kỹ thuật bằng kiến trúc Multi-Agent Agentic RAG.
- Tập trung vào các tác vụ sư phạm-kỹ thuật có thể kiểm chứng:
  - hỏi đáp/giải thích dựa trên tài liệu học phần;
  - sinh bài tập lập trình;
  - sinh feedback cho bài nộp lập trình.
- Local-first deployment là ràng buộc cứng để bảo vệ dữ liệu giáo viên và học viên.
- Prototype hiện thực và đánh giá trong miền CNTT/lập trình.
- Các miền kỹ thuật khác chỉ được phân tích ở mức khả năng mở rộng của interface.
- Hệ thống không nhằm thay thế giáo viên, LMS, hay quy trình đánh giá học tập dài hạn.

## 4.2 Yêu cầu thiết kế chính

- **Local-first và privacy-aware**
  - local-first deployment là ràng buộc bắt buộc của hệ thống;
  - dữ liệu học phần, bài nộp và feedback được xử lý cục bộ;
  - hạn chế phụ thuộc API thương mại;
  - corpus và session data lưu local.

- **Human-in-the-loop**
  - giáo viên kiểm soát việc hệ thống có được thay đổi dữ liệu/trạng thái hay không;
  - giáo viên quyết định thay đổi cụ thể nào được áp dụng, chỉnh sửa, lưu, xuất hoặc hủy;
  - reject/edit reason được dùng làm tín hiệu sửa output và audit trail.

- **Pedagogy-constrained**
  - output cần bám mục tiêu học tập, Bloom level, rubric và constructive alignment;
  - feedback cần giải thích lỗi và gợi ý cải thiện;
  - citation/provenance cần rõ khi dùng tài liệu học phần.

- **Technical-verification-aware**
  - bài tập/lời giải/test cần có khả năng kiểm chứng bằng công cụ;
  - feedback chấm code cần dựa trên kết quả verifier khi có thể;
  - lỗi kỹ thuật được ánh xạ sang error taxonomy của miền.

- **Edge-LLM-constrained**
  - local/edge small LLM là ràng buộc bắt buộc của hệ thống;
  - mọi workflow phải được thiết kế theo giới hạn context, memory, latency và compute của edge LLM;
  - quản lý context, memory, tool scope, retry và số lần gọi model như constraint của orchestration;
  - không giả định frontier/cloud LLM, context rất dài hoặc agent có khả năng tool planning mạnh.

- **Extensible-by-design**
  - core không hard-code logic CNTT/lập trình;
  - domain knowledge, tool, verifier và prompt policy nằm trong Pedagogy Domain Extension;
  - extension CNTT/lập trình là bản hiện thực đầu tiên.

## 4.3 Kiến trúc tổng quan

- Kiến trúc được tổ chức quanh ba trụ cột:
  - **Pedagogy-Constrained Orchestration** — hiện thực qua Orchestrator, Role-scoped Agents, Guardrails và HITL;
  - **Edge-LLM-Constrained Orchestration** — hiện thực qua Orchestrator và Memory (context/memory budget control);
  - **Pedagogy Domain Extension** — hiện thực qua Extension và Knowledge Base.

```mermaid
flowchart TB
    T["User"]
    APP["Application"]
    EXT["Pedagogy<br/>Domain<br/>Extension"]
    MODEL["Model<br/>Inference"]

    APP ~~~ EXT

    subgraph CORE["Core System"]
        ORCHESTRATOR["Supervisor<br/>Orchestrator"]
        AGENTS["Role-Scoped Agents"]
        subgraph EXEC_CTX["Agent Execution Context"]
            direction LR
            KNOW([Knowledge Base])
            MEM([Memory])
            TOOL([Tool Sandbox])
            KNOW ~~~ MEM ~~~ TOOL
        end
        STORE["Persistence / Storage"]
    end

    CORE ~~~ MODEL

    T --> APP
    APP <--> ORCHESTRATOR

    ORCHESTRATOR <--> AGENTS

    EXT --> ORCHESTRATOR
    EXT --> EXEC_CTX
    ORCHESTRATOR <--> EXEC_CTX
    ORCHESTRATOR <--> STORE
    ORCHESTRATOR --> MODEL

    AGENTS <--> EXEC_CTX
    AGENTS --> MODEL

    EXEC_CTX <--> STORE

    style AGENTS stroke-dasharray: 5 5
    style EXEC_CTX stroke-dasharray: 5 5
```

- **Core System**
  - bao gồm Supervisor Orchestrator, Role-scoped Agents, Knowledge Base, Memory, Persistence/Storage và Tool Sandbox;
  - không bao gồm User, Application, Pedagogy Domain Extension và Model Inference;
  - giữ workflow/runtime logic có thể tái sử dụng giữa các domain extension.

- **Agent Execution Context**
  - gom Knowledge Base, Memory và Tool Sandbox;
  - là môi trường thực thi được cấp theo scope cho role-scoped agent invocations;
  - giúp agents truy cập context, memory và tools mà không mở toàn bộ hệ thống;
  - scope cụ thể vẫn do Supervisor Orchestrator kiểm soát.

- **Supervisor Orchestrator**
  - điều phối workflow sư phạm-kỹ thuật;
  - quản lý task graph, role-scoped agents, retrieval, verification, repair và HITL;
  - spawn/điều phối role-scoped agents theo từng task thay vì chạy pipeline cố định;
  - giữ vai trò routing/coordination trung tâm; agents không tự handoff trực tiếp cho nhau;
  - nạp template, retrieval policy và feedback policy từ Extension khi khởi tạo agent invocation;
  - enforce guardrails và HITL checkpoints như middleware nội bộ trong task graph;
  - áp dụng đồng thời Pedagogy-Constrained Orchestration và Edge-LLM-Constrained Orchestration;
  - độc lập với từng miền kỹ thuật cụ thể.

- **Role-scoped agents**
  - gồm các role như retrieval, draft, verification, feedback và review;
  - là các ephemeral agent invocations được orchestrator spawn khi cần;
  - giúp cô lập context của từng bước và chỉ trả kết quả có cấu trúc về orchestrator;
  - mỗi invocation có role, context scope, memory scope và tool scope riêng;
  - orchestrator quyết định role nào được gọi, thứ tự gọi và điều kiện dừng/retry;
  - agent invocation dùng chung model inference backend nhưng không nhất thiết là process/model riêng.

- **Pedagogy Domain Extension**
  - khai báo metadata schema, task schema, prompt templates;
  - cung cấp retrieval policy, verifier, error taxonomy, feedback policy;
  - đóng gói corpus ingestion pipeline và domain tools;
  - được orchestrator nạp khi khởi tạo; agents không truy cập Extension trực tiếp.

- **Knowledge Base**
  - corpus học phần đã index;
  - vector search/reranking;
  - provenance/citation metadata;
  - nhận tài liệu từ workspace/storage qua ingestion/indexing pipeline;
  - metadata và retrieval behavior được cấu hình bởi Pedagogy Domain Extension;
  - topic dependency graph ở mức prototype nếu cần.

- **Memory**
  - working memory cho state của task hiện tại;
  - short-term/session memory cho history và teacher corrections;
  - long-term memory cho teacher preferences/profile nếu được triển khai;
  - orchestrator kiểm soát lượng memory được inject vào agent context (prompt budget);
  - agents đọc/ghi memory trong phạm vi context scope được orchestrator cấp.

- **Persistence / Storage**
  - lưu workspace, configs, session metadata và audit log;
  - lưu chat history/correction history ở dạng persistable;
  - lưu checkpoint/state snapshot để hỗ trợ resume sau HITL hoặc lỗi runtime;
  - lưu corpus registry, index metadata và trạng thái ingestion;
  - là tầng lưu trữ cục bộ phục vụ Application, Knowledge Base và Memory.

- **Tool Sandbox**
  - chạy verifier, test runner, linter, syntax checker và các domain tools;
  - áp dụng timeout, resource limit và isolation cho tool execution;
  - nhận tool definitions/verifier hooks từ Pedagogy Domain Extension thông qua Orchestrator;
  - trả kết quả có cấu trúc cho Orchestrator để repair, retry hoặc chuyển HITL.

- **Model inference**
  - local/edge small LLM inference backend;
  - local embedding/reranking model services;
  - model lifecycle và resource control;
  - không phụ thuộc frontier/cloud LLM cho workflow chính.

- **Application**
  - desktop UI cho giáo viên;
  - review queue, approve/edit/reject;
  - hiển thị draft/proposed changes để giáo viên quyết định trước khi áp dụng;
  - giao tiếp hai chiều với orchestration backend qua IPC (gửi task, nhận stream trạng thái và output).

## 4.4 Các luồng nghiệp vụ chính

- **Luồng hỏi đáp/giải thích tài liệu học phần**
  - giáo viên nhập câu hỏi/chủ đề;
  - hệ thống chuẩn hóa intent và truy xuất tài liệu liên quan;
  - agent sinh câu trả lời có citation;
  - verifier kiểm tra citation coverage và ràng buộc sư phạm;
  - giáo viên quyết định câu trả lời có được lưu/xuất hay cần chỉnh sửa/hủy.

- **Luồng sinh bài tập lập trình**
  - giáo viên nhập topic, độ khó, Bloom target và exercise type;
  - hệ thống retrieve ví dụ/tài liệu/rubric liên quan;
  - agent sinh đề bài, lời giải tham chiếu và test cơ bản;
  - verifier chạy kiểm tra kỹ thuật;
  - nếu lỗi, supervisor repair đúng thành phần lỗi;
  - output được đưa vào HITL review.

- **Luồng sinh feedback cho bài nộp**
  - hệ thống nhận bài nộp và yêu cầu chấm/feedback;
  - domain verifier chạy test/lint/syntax checks;
  - lỗi được phân loại theo error taxonomy;
  - retrieval lấy giải thích liên quan từ corpus;
  - feedback agent sinh nhận xét có tính sư phạm;
  - giáo viên quyết định feedback có được lưu/xuất/gửi hay cần chỉnh sửa/hủy.

## 4.5 Pedagogy-Constrained Orchestration

- Mục tiêu:
  - đưa ràng buộc sư phạm vào workflow thay vì chỉ hậu kiểm cuối cùng;
  - giúp output phù hợp với mục tiêu học tập, rubric và ngữ cảnh lớp học.

- Supervisor Orchestrator:
  - nhận yêu cầu từ giáo viên;
  - chọn graph template theo task;
  - gọi các role-scoped agents khi cần;
  - điều phối retrieval, generation, verification, repair và HITL.

- Typed task graph:
  - mỗi node có input/output schema;
  - mỗi node có role, tool scope và verifier riêng;
  - stop condition và retry policy được khai báo rõ.

- Role-scoped agents:
  - `RetrievalRole`: truy xuất context và provenance;
  - `DraftRole`: sinh giáo án/câu trả lời/bài tập;
  - `VerificationRole`: kiểm tra schema, citation, code và constraints;
  - `FeedbackRole`: sinh feedback dựa trên verifier và error taxonomy;
  - `ReviewRole`: chuẩn bị output cho HITL.

- Pedagogical constraints:
  - Bloom alignment;
  - constructive alignment;
  - rubric consistency;
  - citation coverage;
  - misconception mapping;
  - feedback policy;
  - HITL gate.

- Verification-guided repair:
  - verifier trả lỗi có cấu trúc;
  - supervisor xác định thành phần cần sửa;
  - chỉ repair component lỗi thay vì regenerate toàn bộ;
  - nếu quá số lần retry thì chuyển sang human review.

## 4.6 Edge-LLM-Constrained Orchestration

- Mục tiêu:
  - thiết kế agentic workflow dưới ràng buộc bắt buộc của local/edge small LLM;
  - biến giới hạn context, memory, latency và compute thành constraint của orchestration;
  - giảm tải reasoning, context và tool planning cho model;
  - kiểm soát chi phí tính toán, latency và lỗi tool/schema;
  - đảm bảo hệ thống không phụ thuộc vào frontier/cloud LLM để hoàn thành workflow chính.

- Ràng buộc cứng của edge LLM:
  - context window hạn chế;
  - RAM/VRAM hạn chế;
  - reasoning và tool planning yếu hơn frontier model;
  - dễ lỗi khi prompt quá dài hoặc tool surface quá rộng;
  - nhiều LLM calls làm tăng latency;
  - retry không kiểm soát dễ tốn tài nguyên;
  - không thể đẩy toàn bộ history, corpus, tool list và multi-agent state vào một prompt.

- Context management:
  - context budget là quota bắt buộc theo từng node;
  - giới hạn retrieved chunks truyền vào mỗi node;
  - downstream agent chỉ nhận context đã lọc theo role;
  - history được tóm tắt trước khi đưa lại vào prompt;
  - provenance được giữ ngắn và có cấu trúc.

- Memory management:
  - working memory cho state của task hiện tại;
  - episodic memory cho session history và teacher corrections;
  - semantic memory cho corpus đã index;
  - long-term teacher profile là optional/future;
  - memory injection bị giới hạn bởi prompt budget;
  - memory không được dùng như nơi nhồi toàn bộ lịch sử vào LLM.

- Task decomposition:
  - tách task lớn thành các node nhỏ;
  - mỗi node giải quyết một mục tiêu hẹp;
  - tránh yêu cầu một prompt vừa retrieve, vừa generate, vừa verify, vừa format;
  - node output được chuẩn hóa để node sau dùng lại.

- Agent coordination:
  - agent là role-scoped invocation, không nhất thiết là process/model riêng;
  - supervisor quyết định role nào cần gọi theo từng task;
  - không chạy fixed multi-agent pipeline nếu task không cần;
  - trạng thái chung được quản lý ở orchestrator.

- Tool-use control:
  - tool access được cấp theo node;
  - retrieval tool chỉ mở cho retrieval node;
  - code verifier/linter chỉ mở cho verification node;
  - tool call có schema, timeout và sandbox;
  - số tool call và retry được giới hạn như tài nguyên hệ thống.

- Retrieval compression:
  - retrieval node có thể lấy nhiều candidates hơn;
  - reranker chọn context nhỏ cho downstream node;
  - context pack gồm chunk ngắn, metadata và provenance;
  - citation repair gọi lại retrieval node thay vì để draft agent tự tìm nguồn.

- Retry and repair policy:
  - retry dựa trên lỗi có cấu trúc;
  - ưu tiên targeted repair;
  - giới hạn retry depth;
  - nếu không chắc chắn thì chuyển sang HITL;
  - tránh vòng lặp agent tự sửa không dừng.

- Runtime scheduling:
  - giới hạn số LLM calls cho mỗi task;
  - cache retrieval result khi dùng lại;
  - tái sử dụng prompt/context cố định nếu runtime hỗ trợ;
  - fallback khi thiếu tài nguyên bằng cách giảm top-k, giảm context hoặc giảm retry.

## 4.7 Pedagogy Domain Extension

- Mục tiêu:
  - tách core workflow khỏi tri thức và công cụ của từng miền;
  - cho phép thêm miền kỹ thuật mới mà không thay đổi core;
  - giữ claim mở rộng ở mức thiết kế/interface.

- Core giữ:
  - orchestration logic;
  - task graph execution;
  - HITL workflow;
  - context/memory/tool scheduling;
  - generic verification/repair loop.

- Extension giữ:
  - metadata schema;
  - domain task schema;
  - retrieval policy;
  - prompt templates;
  - verifier/tool interface;
  - error taxonomy;
  - feedback policy;
  - corpus ingestion pipeline.

- Extension CNTT/lập trình:
  - exercise types: implementation, debug, trace, design;
  - metadata: topic, Bloom level, difficulty, language, content type;
  - verifier: syntax check, unit test, lint check;
  - error taxonomy: off-by-one, wrong-base-case, missing-return, type-confusion;
  - feedback template: chỉ ra lỗi, giải thích nguyên nhân, gợi ý sửa.

- Các extension khác:
  - Điện tử/Cơ khí/Xây dựng chỉ dùng làm ví dụ interface;
  - không đưa vào đánh giá thực nghiệm chính;
  - trình bày như hướng mở rộng cần kiểm chứng thêm.

## 4.8 Retrieval và quản lý tri thức

- Mục tiêu:
  - cung cấp grounding từ tài liệu học phần;
  - giảm hallucination;
  - hỗ trợ citation/provenance;
  - chọn context phù hợp với task và Bloom target.

- Corpus:
  - slide bài giảng;
  - giáo trình/tài liệu nội bộ;
  - đề bài, rubric, lời giải mẫu;
  - bài nộp/lỗi mẫu nếu được phép sử dụng.

- Metadata:
  - topic;
  - Bloom level;
  - difficulty;
  - content type;
  - language/framework;
  - source/provenance.

- Retrieval pipeline:
  - chunking theo cấu trúc tài liệu;
  - embedding và index local;
  - filter theo metadata;
  - rerank;
  - trả về context pack ngắn cho downstream agents.

- RetrievalRole:
  - lập truy vấn theo task;
  - chọn nguồn truy xuất phù hợp;
  - gom và lọc kết quả;
  - trả context có provenance;
  - hỗ trợ citation repair khi cần.

- Privacy:
  - corpus nội bộ không gửi ra ngoài mặc định;
  - nguồn external/web là optional/future;
  - mọi nguồn chưa xác minh cần được đánh dấu trong review.

## 4.9 Verification, Guardrails và HITL

- Verification:
  - kiểm tra output schema;
  - kiểm tra citation coverage;
  - kiểm tra Bloom/rubric/feedback policy;
  - kiểm tra kỹ thuật bằng domain verifier;
  - trả lỗi có cấu trúc cho repair loop.

- Guardrails:
  - input relevance check;
  - prompt injection detection;
  - PII/data leakage checks;
  - unsafe code/tool-use checks;
  - output quality and safety flags.

- Tool sandbox:
  - tool chạy trong phạm vi giới hạn;
  - timeout cứng;
  - không cho network/filesystem access nếu không cần;
  - lỗi tool được chuẩn hóa thành verification result.

- HITL levels:
  - hard gate cho các thao tác thay đổi dữ liệu/trạng thái;
  - soft review cho draft chưa ghi vào dữ liệu chính;
  - approve/edit/reject trước khi lưu, xuất hoặc cập nhật;
  - reject/edit reason cho repair;
  - audit log cho mọi thao tác được áp dụng.

- Vai trò của giáo viên:
  - cho phép hoặc từ chối data mutation;
  - xác định phần thay đổi cụ thể được áp dụng;
  - chỉnh sửa nội dung trước khi lưu/xuất/cập nhật;
  - phản hồi lý do reject;
  - xác nhận metadata/corpus label khi cần.

## 4.10 Kiến trúc ứng dụng desktop và local runtime

- Desktop application:
  - giao diện nhập yêu cầu;
  - quản lý workspace/corpus;
  - hiển thị câu trả lời, citation và verifier result;
  - review queue cho HITL.

- Runtime architecture:
  - UI process;
  - orchestration backend;
  - local LLM backend;
  - local vector database;
  - local session/profile storage.

- IPC:
  - UI gửi task tới backend;
  - backend stream trạng thái và output về UI;
  - tool/verifier chạy phía backend;
  - lỗi runtime được trả về có cấu trúc.

- Local storage:
  - indexed corpus;
  - task/session history;
  - teacher corrections;
  - audit log;
  - optional teacher profile.

- Deployment scope:
  - prototype chạy local để demo và đánh giá;
  - packaging hoàn chỉnh là mục tiêu sản phẩm/future work nếu chưa hoàn thiện.

## 4.11 Tổng kết thiết kế

- Chương này trình bày kiến trúc hệ thống ở mức system design.
- Đóng góp không nằm ở từng kỹ thuật riêng lẻ.
- Giá trị chính là cách tích hợp:
  - Multi-Agent Agentic RAG;
  - ràng buộc sư phạm;
  - điều phối dưới ràng buộc edge LLM;
  - cơ chế extension cho miền kỹ thuật;
  - verification, guardrails và HITL.

- Phạm vi hiện thực:
  - core orchestration;
  - extension CNTT/lập trình;
  - retrieval local từ corpus học phần;
  - verifier kỹ thuật cơ bản;
  - teacher-controlled data mutation/review flow.

- Chương tiếp theo đánh giá hệ thống qua:
  - baseline comparison;
  - ablation study;
  - quality metrics theo từng task;
  - latency/resource metrics cho local small LLM.
