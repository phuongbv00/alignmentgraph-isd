# Chương 6 — Conclusion and Future Work

## 6.1 Conclusion

Luận văn đề xuất **Adaptive Instructional Design Agent Harness**, một execution framework cho instructional design agents trong adaptive instructional systems. Thay vì xem LLM như chatbot hoặc công cụ tạo nội dung độc lập, luận văn đặt model trong một harness có memory, typed workflow, schema validation, workflow trace, verifier/checkpoint, teacher-in-the-loop governance và learner-state-aware context injection.

Kiến trúc đề xuất tập trung vào vòng lặp:

```text
Assessment -> Diagnosis -> Intervention -> Reassessment
```

`FeedbackAgent` đánh giá assessment evidence hoặc submission, tạo feedback/adaptive signal; `ProfileAgent` chuyển signal đó thành diagnosis và learner state; learner state được dùng để điều chỉnh orchestration policy cho instructional intervention và reassessment ở vòng sau. Cách tiếp cận này kế thừa tinh thần adaptive learning và ITS, nhưng đơn vị vận hành là teacher-facing instructional workflow ở mức lớp, không phải per-student dialogue tutoring.

Đóng góp của luận văn là một đóng góp thống nhất: **Adaptive Instructional Design Agent Harness**. Các thành phần như graph orchestration, learner-state-aware memory, schema-constrained artifact generation, trace logging, HITL governance, benchmark adapters và domain plugin cho case study được xem là cơ chế triển khai của contribution này.

## 6.2 Trả lời câu hỏi nghiên cứu

**RQ1**: Kết luận cần tóm tắt harness cải thiện chất lượng instructional design và workflow/trajectory như thế nào trên các benchmark instructional-design hiện có, hơn baseline nào, ở metric nào, và có trade-off latency/cost nào đáng kể. Không viết "vượt SOTA" theo nghĩa leaderboard nếu không chạy cùng benchmark split, model, prompt, output schema và judge.

**RQ2**: Kết luận cần nêu learner-state-aware orchestration có cải thiện adaptivity, scaffolding, feedback helpfulness, misconception handling và non-harmful adaptation trên benchmark adaptive tutoring/feedback không. Nếu khác biệt chỉ là nhắc lại learner context hoặc làm output dài hơn, phải xem đó là failure mode.

Case study Computer Science được trình bày như minh hoạ triển khai, không phải RQ độc lập. Nó cho thấy harness có thể được instantiate bằng domain material, policy và tool cụ thể, nhưng không dùng để claim statistical superiority hoặc learning outcome.

## 6.3 Limitations

- Chưa có human evaluation diện rộng trên lớp học thật.
- Benchmark reuse phụ thuộc vào phạm vi, rubric và judge của benchmark gốc.
- Learner-state adaptation ở mức lớp/context, chưa phải learner model đầy đủ theo nghĩa ITS cổ điển.
- LLM-as-judge có rủi ro bias; human subset chỉ giúp kiểm tra xu hướng nếu quy mô nhỏ.
- Subject-domain-agnostic là claim ở tầng kiến trúc harness; chưa chứng minh hiệu quả tương đương trên mọi môn học.
- Computer Science case study chỉ minh hoạ feasibility trong một domain cụ thể, không chứng minh hiệu quả học tập.
- Prototype local/local-first chưa đánh giá tích hợp LMS hoặc deployment nhiều người dùng.

## 6.4 Future Work

- Mở rộng case study sang nhiều subject domain khác để kiểm tra khả năng instantiate harness.
- Tổ chức human evaluation với giáo viên và lớp học thật để đo usefulness, trust, workload reduction và learning outcome.
- Nghiên cứu orchestration policy learning hoặc policy refinement từ teacher override và longitudinal class data.
- Bổ sung adapter cho các benchmark mới về instructional design, tutoring, feedback và learner modeling.
- Tối ưu runtime local: quantization, caching, smaller verifier model, context compaction và batch retrieval.
- Tích hợp LMS hoặc gradebook để nhập/xuất dữ liệu học viên có kiểm soát.
- Phát triển privacy-preserving analytics và audit log cho teacher-controlled data governance.
