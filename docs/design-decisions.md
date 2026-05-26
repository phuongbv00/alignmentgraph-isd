# Design Decisions

File này ghi lại các quyết định đã chốt để giữ terminology và scope nhất quán khi viết tiếp luận văn.

## Thesis Positioning

- Contribution duy nhất của luận văn là **Adaptive Instructional Design Agent Harness**.
- Công thức định vị hệ thống:

```text
Adaptive Instructional Design Agent = LLM + Adaptive Instructional Design Agent Harness
```

- Harness là instructional-design-specific nhưng subject-domain-agnostic: chuyên cho instructional design, nhưng không bị neo vào Computer Science, Math hoặc một môn cụ thể.
- Computer Science chỉ là case study triển khai để kể câu chuyện hệ thống vận hành trong bối cảnh thật, không phải benchmark và không phải một RQ độc lập.

## Evaluation Scope

- Case study CS dùng để kể câu chuyện hệ thống hoạt động trong đời thật (KHÔNG benchmark).
- RQ1 đánh giá harness trên các benchmark instructional-design hiện có, ví dụ ISD-Agent-Bench hoặc benchmark tương đương.
- RQ2 đánh giá learner-state-aware orchestration trên các benchmark adaptive tutoring/feedback hiện có.

## Core Terminology

- Dùng **learner-state-aware memory**, không dùng learner-model-aware, vì thesis chỉ claim hệ thống nhận biết và duy trì learner state ở mức lớp/context; không claim xây learner model đầy đủ theo nghĩa ITS cổ điển.
- Dùng **AID Loop** (**Adaptive Instructional Design Loop**) cho vòng vận hành `Assessment -> Diagnosis -> Intervention -> Reassessment`; không dùng APO Loop vì "pedagogical orchestration" là cơ chế rộng hơn, không phải tên identity của thesis.
- Dùng **ClassLearningProfile** cho learner state bền vững ở cấp lớp.
- Dùng **class-level learner state**, không dùng student group làm đơn vị chính của memory.
- Dùng **domain plugin** cho phần mở rộng theo subject domain.
- Dùng **benchmark adapter** cho lớp ánh xạ input/output của benchmark. Không trộn domain plugin với benchmark adapter.

## Agent Roles

- `InstructionalDesignAgent` thiết kế lesson/intervention plan, learning activities, assessment artifacts và rubric như một phần của instructional design.
- `FeedbackAgent` đánh giá submission hoặc assessment evidence, điều phối domain-specific evaluators nếu domain plugin cung cấp, chuẩn hoá kết quả và tạo feedback/adaptive signal.
- `ProfileAgent` chuyển evaluation/feedback signal thành class diagnosis và đề xuất `ClassLearningProfilePatch`.
- `Plan-and-Execute Orchestrator` điều phối graph, transition, retry, HITL và memory commit.
- `PedagogicalVerifier` là node kiểm tra constraint tường minh trong graph.

## Domain Plugin

- Domain plugin là optional. Core harness vẫn chạy nếu không có plugin.
- Domain plugin có thể cung cấp agents, tools, sandbox, policies, corpus và metadata.
- Với case study Computer Science, domain plugin có thể cung cấp code verifier/test runner trong sandbox và taxonomy lỗi lập trình.
- Domain-specific Evaluation Agents nếu có sẽ nằm trong domain plugin; `FeedbackAgent` là role core chịu trách nhiệm spawn/điều phối/chuẩn hoá output của chúng.
