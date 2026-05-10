# Đề cương & Context dự án

## 1. Định vị đề tài

**Tên đề tài**: "Kiến trúc và Hiện thực Pedagogy Agent Harness hỗ trợ Giáo viên trong Thiết kế Giảng dạy và Đánh giá Cá nhân hoá"

Đề tài mang định hướng thiết kế hệ thống, tập trung xây dựng một **Pedagogy Agent Harness** — môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent có khả năng hỗ trợ thiết kế dạy học và đánh giá cá nhân hoá theo nhóm học sinh trong phạm vi một môn học/khoá học ngắn hạn. Quan hệ cốt lõi: **Agent = Model + Harness**; harness không "điều phối agent" như một thực thể bên ngoài, mà là thứ biến LLM thành agent. Cách tiếp cận này tương tự Claude Code = Claude model + coding harness, hay Codex = GPT + coding harness, nhưng hướng đến giáo viên thay vì lập trình viên.

Khái niệm vận hành trung tâm của harness là **IDA Loop** (Instructional Design–Assessment Loop) — vòng lặp thiết kế dạy học và đánh giá cá nhân hoá liên tục theo nhóm học sinh: giáo viên đánh giá nhóm học sinh → harness tổng hợp hồ sơ nhóm (StudentGroupProfile) → giáo viên thiết kế dạy học phân hoá theo hồ sơ → dạy → đánh giá lại → lặp. Vòng lặp diễn ra trong phạm vi một môn học/khoá học ngắn hạn; giáo viên tương tác qua **giao diện chat hội thoại**.

Harness được thiết kế thỏa hai ràng buộc cứng: (1) **pedagogical constraint enforcement** xuyên suốt pipeline — mọi giai đoạn thực thi phải tuân theo ràng buộc sư phạm, không giới hạn ở bước orchestration; (2) **domain extensibility với null-plugin contract** — harness nhận domain sư phạm mới qua optional plugin interface mà không thay đổi core; core hoạt động đầy đủ khi plugin = null, plugin chỉ bổ sung năng lực xác minh đặc thù domain. Multi-Agent và Agentic RAG là các cơ chế kỹ thuật bên trong harness, không phải tên gọi của hệ thống.

Bốn thành phần kiến trúc cốt lõi phân biệt harness với agentic RAG thông thường: **Intent Router** (phân loại chat input của giáo viên thành UC-ID / UC-AS / UPDATE_PROFILE / QUERY / FEEDBACK); **Memory Architecture** theo 3 scope lồng nhau — *global* (hồ sơ giáo viên/user: preferences, teaching style — cá nhân hoá agent theo giáo viên xuyên suốt mọi khoá học), *workspace* (context khoá học/môn học: CourseContext, StudentGroupProfiles, DiagnosisHistory, ArtifactLog — phục vụ chính cho IDA Loop, duy trì trong phạm vi một khoá học), *session* (phiên làm việc nằm trong workspace: conversation history và active task context — ephemeral, kết thúc khi đóng session); **Profile Synthesis Pipeline** (tự động tổng hợp StudentGroupProfile từ kết quả UC-AS và merge với hồ sơ nhập tay của giáo viên vào workspace memory); **Context Injection** (tự động inject workspace + global memory vào mọi task UC-ID/UC-AS mà không cần giáo viên nhắc lại).

## 2. Phạm vi và ràng buộc

**Phạm vi triển khai/đánh giá**:

- Miền thực nghiệm: **hai case study — CNTT/lập trình và Toán**.
- Mức sản phẩm: prototype chạy local, đủ để demo và đánh giá kỹ thuật.
- LLM: pluggable component — harness không coupled với provider cụ thể; prototype sử dụng LLM theo thiết lập thực nghiệm (local hoặc API).
- Đánh giá: benchmark tự động + LLM-as-judge; không human eval diện rộng.

Phạm vi use case được tổ chức thành **hai UC family**:

**UC-ID — Instructional Design (Thiết kế dạy học)**:
- Soạn kế hoạch bài dạy theo mục tiêu phẩm chất/năng lực (Bloom alignment, constructive alignment).
- Điều chỉnh kế hoạch bài dạy theo StudentGroupProfile — phân hoá hoạt động cho từng nhóm (nâng cao / bổ trợ), ưu tiên tài liệu phù hợp trình độ nhóm, nhấn đúng misconception đã quan sát.

**UC-AS — Assessment (Kiểm tra, đánh giá)**:
- Xây dựng công cụ đánh giá: rubric, ma trận đề, tiêu chí phân mức năng lực.
- Sinh đề kiểm tra/bài tập, có thể cá nhân hoá theo StudentGroupProfile.
- Chấm bài và sinh feedback có chủ đích theo nhóm (nhấn đúng điểm yếu của nhóm nếu có profile).
- Tổng hợp kết quả đánh giá thành StudentGroupProfile (Profile Synthesis Pipeline).

**Chiều cá nhân hoá** — tất cả task trong cả hai UC family nhận input tuỳ chọn `student_group_profile` với hai nguồn:
- Giáo viên nhập tay qua chat ("Nhóm B 10 em hay nhầm push/pop").
- Agent tự tổng hợp từ kết quả UC-AS và đề xuất giáo viên xác nhận (HITL nhẹ).

**Context scope taxonomy**: harness quản lý memory theo 3 tầng — *global* (giáo viên/user, xuyên suốt mọi khoá học), *workspace* (một môn/khoá học cụ thể, chứa tập hợp học viên và phục vụ IDA Loop — duy trì đến hết khoá, reset khi bắt đầu khoá mới), *session* (một phiên làm việc nằm trong workspace — ephemeral).

**Domain plugin (tuỳ chọn — core hoạt động đầy đủ khi thiếu plugin)**:
- CNTT/lập trình: code verifier (chạy test case, báo lỗi compile/runtime), error taxonomy IT.
- Toán: symbolic checker (SymPy verify), math error taxonomy.
- Không có plugin (ví dụ Văn, Lịch sử): UC-ID và UC-AS vẫn hoạt động bình thường, chỉ thiếu auto-verify.

**Ngoài phạm vi luận văn**:

- Xây dựng LMS hoàn chỉnh.
- Cá nhân hoá lộ trình học dài hạn qua nhiều học kỳ (chỉ giải quyết IDA Loop trong phạm vi một môn/khoá học ngắn hạn).
- Cá nhân hoá đến từng học sinh — chỉ hỗ trợ phân nhóm học sinh (group-level), không phải per-student adaptive learning.
- Đánh giá hiệu quả học tập thực tế qua nhiều tuần/lớp thật (human eval diện rộng).
- Triển khai và đánh giá thực nghiệm extension cho nhiều domain hơn ngoài CNTT và Toán.

Kiến trúc được thiết kế có điểm mở rộng cho nhiều domain khác qua plugin interface. Khả năng mở rộng này được khẳng định ở mức thiết kế/interface compliance; bằng chứng thực nghiệm nằm trong hai case study CNTT/lập trình và Toán.

## 3. Mục tiêu và câu hỏi đánh giá

- **EQ1**: Trong hai case study CNTT/lập trình và Toán, kiến trúc đề xuất có hiệu quả hơn LLM-only, Naive RAG, Generic ReAct ARAG và Fixed MA-ARAG trên các tác vụ UC-ID và UC-AS không?
- **EQ2**: Pedagogy Domain Extension interface có đủ tổng quát để hai domain extension (CNTT và Toán) cùng implement mà không thay đổi core không? Core có hoạt động đầy đủ khi plugin = null không (null-plugin contract)? Câu hỏi này được trả lời bằng phân tích interface compliance và thiết kế, không bằng user study.
- **EQ3**: IDA Loop có tạo ra sự phân hoá có chủ đích theo nhóm học sinh không — output UC-ID/UC-AS ở vòng 2 (có StudentGroupProfile) có khác biệt đo được so với vòng 1 (không có profile) theo chiều phù hợp với nhóm (personalization delta) không?

## 4. Đóng góp kỹ thuật dự kiến

Đề tài đóng góp ở mức thiết kế hệ thống, hiện thực prototype và đánh giá kỹ thuật, không ở mức phát minh thuật toán mới.

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent (Agent = Model + Harness), thỏa hai ràng buộc thiết kế cứng: pedagogical constraint enforcement xuyên suốt pipeline và domain extensibility qua optional plugin interface (null-plugin contract). Harness vận hành IDA Loop qua bốn thành phần mới: Intent Router, Workspace Memory, Profile Synthesis Pipeline, Context Injection — kết hợp với LLM tạo thành agent có năng lực thiết kế dạy học và đánh giá cá nhân hoá theo nhóm học sinh — tương tự coding harness kết hợp với LLM tạo thành Claude Code hay Codex, nhưng dành cho giáo viên.
2. **Hai domain plugin implementation**: CNTT/lập trình và Toán — minh chứng tính tổng quát của domain plugin interface trên hai domain có đặc trưng khác biệt (có/không code verifier, error taxonomy khác nhau); đồng thời chứng minh null-plugin contract — core UC-ID và UC-AS hoạt động đầy đủ khi không load plugin.
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study với giao diện chat hội thoại, corpus nội bộ, retrieval local, Workspace Memory duy trì xuyên khoá học, Profile Synthesis Pipeline và teacher-controlled HITL flow.
4. **Bộ đánh giá kỹ thuật**: benchmark hai domain (~200 sample bao gồm IDA round-1 và round-2), baseline comparison với LLM-only/Naive RAG/Generic ReAct ARAG/Fixed MA-ARAG/Đề xuất-no-plugin, ablation cho các thành phần harness, và đánh giá personalization delta (EQ3).

## 5. Ràng buộc thiết kế cứng

1. **Pedagogical constraint enforcement**: mọi giai đoạn thực thi của harness (retrieval policy, generation, schema validation, verification, repair, output) phải tuân theo ràng buộc sư phạm — Bloom/rubric alignment, citation coverage, misconception mapping, feedback policy, HITL approval. Constraint không chỉ áp ở bước orchestration mà được enforce xuyên suốt pipeline qua typed schema, verifier, HITL gate và memory.
2. **Domain extensibility với null-plugin contract**: harness nhận domain sư phạm mới qua optional plugin interface mà không thay đổi core. Mỗi domain plugin khai báo metadata schema, task schema, retrieval policy, verifier/tool interface, error taxonomy, feedback template và corpus ingestion pipeline; core chỉ phụ thuộc vào interface này. Khi plugin = null, core vẫn thực thi UC-ID và UC-AS đầy đủ — null-plugin là một test case bắt buộc của interface compliance (EQ2).
3. **IDA Loop memory continuity**: Memory Architecture phải đảm bảo ba scope hoạt động đúng vai trò — *global* duy trì hồ sơ giáo viên xuyên suốt mọi khoá học; *workspace* (CourseContext, StudentGroupProfiles, DiagnosisHistory, ArtifactLog) duy trì toàn bộ context IDA Loop trong phạm vi một khoá học, reset khi bắt đầu khoá mới; *session* là ephemeral — khi kết thúc, artifact đã HITL-approve được commit vào workspace, session memory không bị lẫn giữa các phiên làm việc. StudentGroupProfile có thể được cập nhật từ hai nguồn độc lập (giáo viên nhập tay và Profile Synthesis Pipeline) và phải merge nhất quán vào workspace. Context Injection tự động inject workspace + global memory vào mọi task mà không cần giáo viên nhắc lại.

## 6. Format & Template

Dùng template **SOICT_DATN_Application_VIE_Template** tại [templates/SOICT_DATN_Application_VIE_Template/](templates/SOICT_DATN_Application_VIE_Template/).

Cấu hình preamble từ [templates/.../LuanVan.tex](templates/SOICT_DATN_Application_VIE_Template/LuanVan.tex):

- Class: `report`, `a4paper`, `13pt`, `twoside`.
- Font: `times` (Times New Roman).
- Encoding: `\usepackage[utf8]{vietnam}` — không dùng `xelatex`/`polyglossia`.
- Margin: `top=2cm, bottom=2cm, left=3.5cm, right=2.5cm`.
- Bibliography: `biblatex` + `bibtex` backend, style `ieee`.
- Spacing: `\onehalfspacing`, `parskip=6pt`, `parindent=15pt`.
- Front-matter bắt buộc: Bìa → Bìa lót → Lời cảm ơn → Tóm tắt VN → Tóm tắt EN → Mục lục → Danh mục hình vẽ → Danh mục bảng biểu → Danh mục thuật ngữ/viết tắt.
- Phụ lục: qua `\appendices`.

Cấu trúc chương (7 chương — mở rộng từ template SOICT 6 chương):

| Chương | Tiêu đề                         | File chính                         |
| ------ | ------------------------------- | ---------------------------------- |
| 1      | Giới thiệu đề tài               | `chapters/1_introduction.tex`      |
| 2      | Khảo sát và phân tích yêu cầu   | `chapters/2_survey.tex`            |
| 3      | Nền tảng lý thuyết & công nghệ  | `chapters/3_literature_review.tex` |
| 4      | Thiết kế và triển khai hệ thống | `chapters/4_system_design.tex`     |
| 5      | Đánh giá hệ thống               | `chapters/5_evaluation.tex`        |
| 6      | Giải pháp và đóng góp nổi bật   | `chapters/6_contribution.tex`      |
| 7      | Kết luận và hướng phát triển    | `chapters/7_conclusion.tex`        |

Nội dung tương ứng trong `main.tex`:

```latex
\chapter{THIẾT KẾ VÀ TRIỂN KHAI HỆ THỐNG}
\subfile{chapters/4_system_design}

\chapter{ĐÁNH GIÁ HỆ THỐNG}
\subfile{chapters/5_evaluation}

\chapter{CÁC GIẢI PHÁP VÀ ĐÓNG GÓP NỔI BẬT}
\subfile{chapters/6_contribution}

\chapter{KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN}
\subfile{chapters/7_conclusion}
```

---

# Đề cương 7 chương (theo template SOICT, mở rộng)

Xem chi tiết Chương 1 & 2 tại [1_intro.md](1_intro.md).

## Chương 1 — Giới thiệu đề tài

- Bối cảnh: giáo viên/giảng viên mất nhiều giờ cho tác vụ sư phạm lặp; LLM thương mại có rủi ro dữ liệu; các agent framework tổng quát chưa tối ưu cho tác vụ sư phạm.
- Vấn đề: LLM đơn thuần chưa phải agent sư phạm — thiếu một harness kết hợp với LLM để tạo thành Pedagogy Agent có tool layer, pedagogical constraints, HITL, workspace-scoped memory và extensibility. Đặc biệt, vòng lặp thiết kế dạy học–đánh giá cá nhân hoá (IDA Loop) — giáo viên đánh giá nhóm học sinh → thiết kế dạy học phân hoá → đánh giá lại → lặp — đòi hỏi harness có khả năng duy trì hồ sơ nhóm và lịch sử chẩn đoán xuyên suốt khoá học, điều mà LLM stateless và agent framework tổng quát không cung cấp; tương tự Claude Code/Codex là harness biến LLM thành coding agent, nhưng dành cho giáo viên.
- Phạm vi: Pedagogy Agent Harness thỏa hai ràng buộc thiết kế cứng (pedagogical constraint enforcement xuyên suốt pipeline, domain extensibility qua plugin interface), được validate qua hai case study: CNTT/lập trình và Toán.
- Định vị đóng góp: không xem từng cơ chế riêng lẻ là mới; nhấn mạnh harness như contribution ở tầng infrastructure, với Multi-Agent và Agentic RAG là implementation bên trong.
- Mục tiêu và EQ (xem §3 phía trên).
- Bố cục luận văn.

## Chương 2 — Khảo sát và phân tích yêu cầu

- Khảo sát nhu cầu giáo viên (qualitative — phỏng vấn / bảng hỏi nhanh hoặc literature-based).
- Phân tích use case theo hai UC family: **UC-ID** (soạn kế hoạch bài dạy theo phẩm chất/năng lực, điều chỉnh theo StudentGroupProfile) và **UC-AS** (xây dựng công cụ đánh giá/rubric/ma trận đề, sinh đề/bài tập cá nhân hoá, chấm bài + feedback theo nhóm, tổng hợp StudentGroupProfile). **IDA Loop** là vòng lặp kết nối UC-ID và UC-AS theo nhóm học sinh.
- Teacher journey: giao diện **chat hội thoại**; `student_group_profile` dual input (nhập tay qua chat + agent tự tổng hợp từ kết quả UC-AS); cá nhân hoá ở mức nhóm học sinh (group-level), không phải per-student.
- Context scope taxonomy: *global* (giáo viên/user — cá nhân hoá agent xuyên mọi khoá học), *workspace* (một khoá học/môn học cụ thể, chứa tập hợp học viên — phục vụ IDA Loop), *session* (phiên làm việc nằm trong workspace — ephemeral).
- Yêu cầu phi chức năng/ràng buộc thiết kế: HITL bắt buộc, pedagogical constraint enforcement xuyên suốt pipeline, Workspace Memory duy trì xuyên khoá học, domain extensibility qua optional plugin interface (null-plugin contract), LLM là pluggable component.
- Benchmarks hiện có trong lĩnh vực (AI in education, agentic RAG, coding agent harness) — xác định gap.

## Chương 3 — Nền tảng lý thuyết & công nghệ sử dụng

Xem chi tiết 17 subsection tại [2_lit-review.md](2_lit-review.md).

Tóm tắt cấu trúc (17 subsection):

1. Large Language Models (LLM)
2. AI Agent vs Agentic AI — phân biệt khái niệm
3. **Agent Harness Engineering** — định nghĩa harness, 6 capability cốt lõi, harness vs framework, infrastructure contribution framing
4. Agentic AI trong thực tế — AI coding assistants (Claude Code, OpenAI Codex, Devin, Cursor/Windsurf) → **analogy chính cho Pedagogy Agent Harness**
5. Human-in-the-loop & Human-Agent Collaboration (teacher-in-the-loop, override, preference memory)
6. Retrieval-Augmented Generation (RAG, Self-RAG, CRAG, Agentic RAG, GraphRAG, A-RAG)
7. Multi-Agent Systems (MAS) với LLM (AutoGen, MetaGPT, CrewAI, LangGraph, communication/collaboration surveys)
8. Agent Memory Architecture (MemGPT, Sumers taxonomy, episodic/preference memory)
9. Context Management cho LLM Agent (ACON, Lost in the Middle, Chain-of-Agents, Context-Folding)
10. LLM Agent Safety & Guardrails (prompt injection, LlamaGuard, AGrail, ToolSafe, No Free Lunch)
11. LLM deployment options (cloud, local, edge) — context cho lựa chọn LLM của prototype
12. Evaluation Methodology cho hệ thống LLM/RAG/Agent (LLM-as-Judge, RAGAS, agent trajectory evaluation, ablation)
13. Desktop app tích hợp AI (Electron + in-process agent)
14. LLM trong giáo dục (tutoring, auto-grading, content generation, AI-assisted feedback)
15. Privacy & Local-first Deployment trong giáo dục (student data, local-first, teacher-controlled data governance)
16. Nền tảng sư phạm (Bloom's Taxonomy, Constructive Alignment)
17. Khoảng trống & định vị hệ thống

## Chương 4 — Thiết kế và triển khai hệ thống

Xem chi tiết đầy đủ tại [3_method.md](3_method.md).

Tóm tắt cấu trúc:

1. **Kiến trúc tổng thể**: Agent = Model + Harness; IDA Loop là luồng vận hành chính; chat interface là điểm vào của giáo viên.
2. **Intent Router**: phân loại chat input thành UC-ID / UC-AS / UPDATE_PROFILE / QUERY / FEEDBACK; kích hoạt pipeline tương ứng.
3. **UC-ID Pipeline**: retrieval từ corpus (scoped theo domain + StudentGroupProfile) → generation với Bloom/constructive alignment constraints → typed schema validation → HITL → output kế hoạch bài dạy phân hoá.
4. **UC-AS Pipeline**: sinh đề/rubric hoặc chấm bài → domain verifier (optional — từ plugin) → diagnosis generation → Profile Synthesis → HITL → output feedback/diagnosis report.
5. **Memory Architecture (3 scope)**: *global* (teacher profile — preferences, teaching style); *workspace* (CourseContext, StudentGroupProfiles[], DiagnosisHistory[], ArtifactLog[] — phục vụ IDA Loop, scope = một khoá học, reset khi bắt đầu khoá mới); *session* (conversation history, active task context — ephemeral, commit artifact vào workspace khi session kết thúc).
6. **Profile Synthesis Pipeline**: parse diagnosis output → structured group update → merge với StudentGroupProfile hiện tại → đề xuất giáo viên confirm (HITL nhẹ).
7. **Context Injection**: tự động inject StudentGroupProfiles và DiagnosisHistory (N vòng gần nhất) vào retrieval policy và generation prompt cho mọi task — không cần giáo viên nhắc lại.
8. **Domain Plugin Interface (optional)**: khai báo verifier, error taxonomy, tool interface; null-plugin contract — core chạy đầy đủ khi plugin = null; hai implementation: IT plugin (code verifier + error taxonomy IT) và Toán plugin (SymPy checker + math error taxonomy).
9. **HITL Governance**: mọi output phải qua approval gate trước khi lưu vào ArtifactLog; giáo viên chỉnh sửa qua chat; rejection reason feed lại làm constraint retry.

## Chương 5 — Đánh giá hệ thống

Xem chi tiết đầy đủ tại [4_eval.md](4_eval.md).

Tóm tắt cấu trúc:

1. Thiết lập thực nghiệm (hardware, mô hình, corpus, hyperparameters)
2. Bộ dữ liệu đánh giá (~200 sample: CNTT/lập trình + Toán, bao gồm IDA round-1 và round-2)
3. Baselines + Ablation (LLM-only → Naive RAG → Generic ReAct ARAG → Fixed MA-ARAG → Đề xuất-no-plugin → hệ thống đề xuất đầy đủ)
4. Metrics (RAGAS, verifier pass rate, schema validity, pedagogical constraint violation, **personalization delta**, teacher-controlled mutation metrics, LLM-as-judge, latency)
5. Kết quả trả lời EQ1, EQ2, EQ3; phân tích lỗi; thảo luận

## Chương 6 — Giải pháp và đóng góp nổi bật

**Đóng góp dự kiến** (cập nhật thành "đóng góp được xác nhận" sau khi có kết quả thực nghiệm):

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent (Agent = Model + Harness), thỏa hai ràng buộc thiết kế cứng: pedagogical constraint enforcement xuyên suốt pipeline và domain extensibility qua plugin interface. Định vị rõ ràng như harness infrastructure (tương tự coding harness trong Claude Code/Codex) thay vì application.
2. **Hai domain plugin implementation**: CNTT/lập trình và Toán — bằng chứng thực nghiệm rằng domain plugin interface đủ tổng quát cho hai domain có đặc trưng khác biệt.
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study với corpus nội bộ, retrieval local, verifier và teacher-controlled review flow.
4. **Bộ benchmark sư phạm tự xây**: ~180 sample (CNTT: giáo án/bài tập/chấm code; Toán: bài tập/chấm lời giải) với corpus nội bộ tiếng Việt.

Phân tích điều kiện/context mà kiến trúc đề xuất vượt trội (dựa ablation Chương 5), đồng thời nêu rõ giới hạn: kết quả chứng minh giá trị của cấu hình tích hợp trong phạm vi hai case study, không chứng minh các cơ chế con là mới.

## Chương 7 — Kết luận và hướng phát triển

- Trả lời rõ EQ1 và EQ2.
- Giới hạn: không human eval diện rộng, mới hai domain extension, LLM-as-judge bias, performance phụ thuộc LLM được chọn.
- Hướng mở rộng: extension thêm domain (Vật lý, Lịch sử...), human eval, fine-tune LLM nhỏ trên curriculum VN, tối ưu runtime local, tích hợp LMS.
