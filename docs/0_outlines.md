# Thesis Outline (Research-Paper Style)

## Thesis Metadata

**Working title**: Architecture and Implementation of a Pedagogy Agent Harness for Teacher-Centered Instructional Design and Group-Level Personalized Assessment

**Vietnamese title**: Kiến trúc và Hiện thực Pedagogy Agent Harness hỗ trợ Giáo viên trong Thiết kế Giảng dạy và Đánh giá Cá nhân hoá theo Nhóm học sinh

**Core thesis**: Một LLM đơn thuần chưa phải là agent sư phạm. Để hỗ trợ giáo viên trong vòng lặp thiết kế dạy học và đánh giá cá nhân hoá, cần một **Pedagogy Agent Harness**: môi trường thực thi kết hợp với LLM để tạo thành Pedagogy Agent, cung cấp memory, retrieval, verifier, schema validation, teacher-in-the-loop và cơ chế mở rộng đa lĩnh vực sư phạm.

**System framing**: `Agent = Model + Harness`. Multi-Agent và Agentic RAG là cơ chế triển khai bên trong harness, không phải tên gọi chính của hệ thống.

**Primary contribution type**: system design, prototype implementation and technical evaluation; không claim phát minh thuật toán mới.

## Abstract Draft

Large language models (LLMs) have shown strong potential for educational content generation and assessment support, but a raw LLM remains stateless, weakly constrained and difficult to adapt to subject-specific pedagogical workflows. This thesis proposes a **Pedagogy Agent Harness**, an execution environment that combines a pluggable LLM with retrieval, memory, subject-specific verification, typed workflows and teacher-in-the-loop governance to support instructional design and assessment for groups of learners. The harness operationalizes an Instructional Design-Assessment Loop (IDA Loop), where assessment results are consolidated into StudentGroupProfiles and automatically injected into subsequent instructional design and assessment tasks. The architecture is designed around two hard constraints: pipeline-wide pedagogical constraint enforcement and multi-subject pedagogical extensibility through an optional plugin interface with a null-plugin contract. We implement a local prototype and evaluate it on two case studies, programming/IT and mathematics, comparing the proposed harness against LLM-only, naive RAG, generic ReAct Agentic RAG and fixed multi-agent baselines. The evaluation focuses on pedagogical alignment, verifier pass rate, schema validity, personalization delta, latency and interface compliance.

## Keywords

LLM agent, agent harness, AI in education, instructional design, assessment, teacher-in-the-loop, retrieval-augmented generation, agentic RAG, group-level personalization, multi-subject pedagogical extensibility.

## Research Questions

- **RQ1**: Trong hai case study CNTT/lập trình và Toán, Pedagogy Agent Harness có hiệu quả hơn LLM-only, Naive RAG, Generic ReAct Agentic RAG và Fixed MA-ARAG trên các tác vụ thiết kế dạy học và đánh giá không?
- **RQ2**: Domain Plugin Interface có đủ tổng quát để hai domain extension CNTT và Toán cùng implement mà không thay đổi core không? Core có hoạt động đầy đủ khi plugin = null không?
- **RQ3**: IDA Loop có tạo ra phân hoá có chủ đích theo nhóm học sinh không? Output ở vòng 2 có StudentGroupProfile có khác biệt đo được so với vòng 1 không có profile theo chiều phù hợp với nhóm không?

## Contributions

1. **Pedagogy Agent Harness architecture**: một harness biến LLM thành Pedagogy Agent bằng cách cung cấp intent routing, workspace memory, profile synthesis, context injection, typed pipelines, verifier và HITL governance.
2. **IDA Loop for group-level personalization**: vòng lặp assessment → diagnosis → StudentGroupProfile → differentiated instructional design → reassessment trong phạm vi một khoá học.
3. **Optional Domain Plugin Interface**: interface cho verifier, error taxonomy, retrieval policy và feedback templates đặc thù từng lĩnh vực sư phạm; core vẫn hoạt động khi plugin = null.
4. **Prototype and technical benchmark**: prototype end-to-end với hai case study CNTT/lập trình và Toán, benchmark có baseline comparison, ablation và personalization delta analysis.

## Thesis Chapter Structure

| Part          | File                                               | Role                                                                        |
| ------------- | -------------------------------------------------- | --------------------------------------------------------------------------- |
| Planning note | [0_outlines.md](0_outlines.md)                     | Thesis-level framing, RQs, contributions, chapter map                       |
| Chapter 1     | [1_intro.md](1_intro.md)                           | Introduction: motivation, problem, research questions, scope, contributions |
| Chapter 2     | [2_lit-review.md](2_lit-review.md)                 | Background and Related Work                                                 |
| Chapter 3     | [3_method.md](3_method.md)                         | Proposed Method: Pedagogy Agent Harness architecture                        |
| Chapter 4     | [4_eval.md](4_eval.md)                             | Experimental Setup and Evaluation Protocol                                  |
| Chapter 5     | [5_results-discussion.md](5_results-discussion.md) | Results, Ablation, Discussion and Threats to Validity                       |
| Chapter 6     | [6_conclusion.md](6_conclusion.md)                 | Conclusion and Future Work                                                  |

## Scope

**In scope**:

- Prototype chạy local hoặc local-first.
- Hai case study: CNTT/lập trình và Toán.
- Hai use-case family:
  - **UC-ID**: instructional design, lesson planning, differentiated activities.
  - **UC-AS**: assessment generation, rubric/test matrix construction, grading and feedback.
- Cá nhân hoá ở mức **nhóm học sinh** thông qua `StudentGroupProfile`, không phải per-student adaptive learning.
- Đánh giá kỹ thuật bằng benchmark tự động, verifier, LLM-as-judge, ablation và interface compliance.

**Out of scope**:

- LMS hoàn chỉnh.
- Long-term adaptive learning qua nhiều học kỳ.
- Human evaluation diện rộng trên lớp thật.
- Khẳng định novelty thuật toán cho từng cơ chế con như RAG, MAS, verifier hay memory.

## System Summary

Pedagogy Agent Harness vận hành qua bốn thành phần phân biệt chính:

1. **Intent Router**: phân loại chat input của giáo viên thành `UC_ID`, `UC_AS`, `UPDATE_PROFILE`, `QUERY`, `FEEDBACK`.
2. **Memory Architecture**: ba scope gồm `global` cho teacher preference, `workspace` cho CourseContext/StudentGroupProfiles/DiagnosisHistory/ArtifactLog, và `session` cho working memory tạm thời.
3. **Profile Synthesis Pipeline**: tổng hợp kết quả UC-AS thành StudentGroupProfile và yêu cầu giáo viên xác nhận trước khi commit.
4. **Context Injection**: tự động đưa workspace + global memory vào mọi task UC-ID/UC-AS mà không cần giáo viên nhắc lại.

## Hard Design Constraints

1. **Pipeline-wide pedagogical constraint enforcement**: ràng buộc Bloom alignment, constructive alignment, rubric consistency, misconception mapping, feedback policy, citation coverage và HITL gate được enforce xuyên suốt retrieval, generation, validation, verification, repair và output.
2. **Mở rộng đa lĩnh vực sư phạm với null-plugin contract**: harness tiếp nhận lĩnh vực sư phạm mới qua optional plugin interface mà không thay đổi core; nếu plugin = null, UC-ID và UC-AS vẫn chạy đầy đủ, chỉ thiếu verifier đặc thù từng lĩnh vực.
3. **IDA Loop memory continuity**: StudentGroupProfile và DiagnosisHistory được duy trì ở workspace scope trong phạm vi khoá học, được cập nhật từ giáo viên hoặc Profile Synthesis Pipeline, và được inject trở lại vào task tiếp theo.

## Evaluation Matrix

| RQ  | Evidence                                     | Primary metrics                                                                              |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------- |
| RQ1 | Comparison study trên CNTT/lập trình và Toán | LLM-as-judge score, verifier pass rate, schema validity, pedagogical violation rate, latency |
| RQ2 | Interface compliance + null-plugin test      | Core modification count, plugin completeness, null-plugin pass/fail                          |
| RQ3 | Paired round-1 vs round-2 analysis           | Personalization delta, group-fit score, group-tone alignment                                 |

## Baselines

1. **LLM-only**: generate trực tiếp, không RAG, không agent loop.
2. **Naive RAG**: top-k retrieval + LLM generation, không tool loop.
3. **Generic ReAct Agentic RAG**: một ReAct agent tự do, có retrieval/tool access nhưng không typed graph.
4. **Fixed MA-ARAG**: nhiều role cố định như planner/generator/grader/reviewer.
5. **Proposed minus Domain Plugin**: harness đầy đủ nhưng không load plugin, dùng để kiểm tra null-plugin contract.
6. **Full Proposed System**: Pedagogy Agent Harness đầy đủ với domain plugin tương ứng.

## Thesis Writing Notes

- Dùng thuật ngữ **Research Question (RQ)** trong bản thesis; nếu viết hoàn toàn bằng tiếng Việt có thể diễn đạt là **câu hỏi nghiên cứu/đánh giá**.
- Related Work phải đi từ nền rộng đến gap: LLM agents → harness/coding agents → RAG/MAS/memory/safety → AI in education → pedagogy → gap.
- Method phải mô tả harness như kiến trúc đề xuất, không biến thành catalog công nghệ.
- Evaluation phải tách rõ **comparison**, **ablation**, **interface compliance**, **personalization delta**.
- Results & Discussion chỉ điền sau thực nghiệm; hiện tại file [5_results-discussion.md](5_results-discussion.md) là khung báo cáo kết quả.
