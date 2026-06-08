# Chương 1 — Introduction

## 1.1 Motivation and Problem Statement

Luận văn này không định vị như một nghiên cứu về "ứng dụng AI trong giáo dục", một hệ thống "multi-agent RAG cho học tập", hay một công cụ "LLM hỗ trợ đào tạo" theo nghĩa sinh nội dung rời rạc. Định vị trung tâm của luận văn là **Adaptive Instructional Design Agent Harness**: một harness chuyên cho thiết kế dạy học thích ứng, độc lập với subject domain cụ thể, dùng agentic AI để điều phối các quyết định dạy học trong một vòng lặp đánh giá, chẩn đoán, can thiệp và tái đánh giá có trạng thái.

Trong thực tế giảng dạy, instructional design không phải là hoạt động một lần. Kế hoạch bài dạy, hoạt động học tập, rubric, bài tập, đề kiểm tra và feedback cần được điều chỉnh liên tục theo learner state của từng lớp: nền tảng đầu vào, misconception đang nổi lên, nhịp tiếp thu, kết quả đánh giá gần nhất và bằng chứng từ các lần can thiệp trước đó. Vấn đề vì vậy không chỉ là sinh một lesson plan hay một rubric tốt tại một thời điểm, mà là duy trì một **closed-loop instructional workflow**:

```text
Assessment -> Diagnosis -> Intervention -> Reassessment
```

Các công cụ LLM hiện tại có thể hỗ trợ từng tác vụ riêng lẻ như tạo câu hỏi, gợi ý feedback hoặc soạn kế hoạch bài dạy. Tuy nhiên, chúng thường xử lý mỗi yêu cầu như một tác vụ độc lập, tách khỏi lịch sử của lớp học và khỏi lifecycle thiết kế dạy học. LLM thuần là stateless; các chatbot phổ biến bổ sung lịch sử hội thoại nhưng vẫn không có khái niệm bền vững về chương trình, lớp học, learner state, artifact đã triển khai, quyết định đánh giá trước đó và ràng buộc alignment giữa objective, activity và assessment. Các general-purpose agent tiến xa hơn nhờ tool use và memory, nhưng memory/project context của chúng không được tổ chức theo semantics của instructional systems.

Bối cảnh công việc của tác giả minh hoạ cụ thể cho khoảng trống này. Trong vai trò giảng viên nội bộ tại FPT Software, phụ trách đào tạo chuyên môn cho nhân viên mới và nhân viên trong các khoá ngắn hạn 1-3 tháng, mỗi lớp học có đặc điểm riêng: khác biệt về nền tảng kỹ thuật, nhịp tiếp thu không đồng đều giữa các nhóm, và kết quả đánh giá giữa khoá thường đòi hỏi điều chỉnh instruction. Bối cảnh Computer Science này được dùng trong luận văn như một **case study triển khai**, không phải benchmark chính.

Về mặt lý thuyết, Instructional Systems Design (ISD) đã cung cấp lifecycle và semantics cho thiết kế dạy học: phân tích nhu cầu, xác định mục tiêu, thiết kế instruction, triển khai, đánh giá và refinement. Adaptive Learning và Intelligent Tutoring Systems mở rộng hướng này bằng learner modeling, adaptive sequencing và remediation. Tuy nhiên, các hệ thống hiện có vẫn còn khoảng trống khi đặt trong bối cảnh agentic AI hiện đại: thiếu learner-state-aware memory ở cấp lớp, thiếu longitudinal adaptation qua nhiều phiên, thiếu closed-loop pedagogical refinement, và thiếu một kiến trúc agent orchestration được grounded bằng lý thuyết instructional design.

Luận văn đề xuất **Adaptive Instructional Design Agent Harness** như một bước tiếp theo của adaptive instructional systems: không phải một chatbot tutor, không phải một công cụ sinh nội dung, mà là một execution framework đặt LLM trong instructional workflow có memory, schema, trace, learner state và governance. Harness này là **instructional-design-specific** nhưng **subject-domain-agnostic**: nó không được neo vào Computer Science, Math hay một môn học cụ thể, dù có thể được instantiate bằng corpus, tool và policy riêng của từng domain.

## 1.2 Contributions

Luận văn có một đóng góp chính: **Adaptive Instructional Design Agent Harness**. Đây là một harness điều phối agent cho thiết kế dạy học thích ứng, tích hợp instructional workflow, learner-state-aware memory, schema-constrained artifact generation, workflow trace, HITL governance và benchmark adapters thành một execution framework thống nhất. Các thành phần như graph orchestration, profile-conditioned context injection, verifier/checkpoint và domain plugin được xem là cơ chế triển khai của contribution này, không phải các đóng góp tách rời.

## 1.3 Research Questions

- **RQ1**: Trên các benchmark instructional-design hiện có, **Adaptive Instructional Design Agent Harness** cải thiện chất lượng thiết kế dạy học và workflow/trajectory như thế nào so với LLM-only, ReAct/general-agent và theory-grounded prompting baselines?
- **RQ2**: Learner-state-aware orchestration trong harness có cải thiện adaptivity, scaffolding, feedback helpfulness và misconception handling trên các benchmark adaptive tutoring/feedback hiện có không?

Hai câu hỏi nghiên cứu kiểm tra contribution ở tầng harness và orchestration bằng benchmark có sẵn. Computer Science được dùng như case study định tính để minh hoạ cách harness được instantiate trong một subject domain cụ thể; case study này không được dùng như benchmark thống kê và không phải một RQ độc lập.

## 1.4 Thesis Outlines

Chương 1 giới thiệu định vị luận văn và câu hỏi nghiên cứu.
Chương 2 trình bày nền tảng và công trình liên quan theo mạch Learning Theory -> Instructional Systems -> Adaptive Learning -> Educational Agents -> Agentic Orchestration -> Research Gap.
Chương 3 mô tả kiến trúc Adaptive Instructional Design Agent Harness.
Chương 4 trình bày protocol đánh giá dựa trên benchmark adapters và case study Computer Science.
Chương 5 báo cáo kết quả benchmark comparison, learner-state adaptation analysis, case study, phân tích lỗi, thảo luận và threats to validity.
Chương 6 kết luận và nêu hướng phát triển.
