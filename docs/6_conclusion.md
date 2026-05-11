# Chương 6 — Conclusion and Future Work

## 6.1 Conclusion

Luận văn đề xuất **Pedagogy Agent Harness**, một execution environment kết hợp với LLM để tạo thành Pedagogy Agent phục vụ giáo viên trong thiết kế dạy học và đánh giá cá nhân hoá theo nhóm học sinh. Thay vì xem LLM như một chatbot độc lập, luận văn định vị hệ thống theo công thức `Agent = Model + Harness`: model cung cấp năng lực ngôn ngữ và reasoning, còn harness cung cấp memory, tool execution, constraint enforcement, workflow control, teacher-in-the-loop và cơ chế mở rộng đa lĩnh vực sư phạm.

Kiến trúc đề xuất tập trung vào **IDA Loop**: assessment tạo diagnosis, diagnosis được tổng hợp thành StudentGroupProfile, profile được inject vào các tác vụ instructional design và assessment tiếp theo, sau đó vòng lặp được lặp lại trong phạm vi một khoá học. Cách tiếp cận này hướng tới group-level personalization thay vì per-student adaptive learning.

Đóng góp của luận văn nằm ở tầng thiết kế hệ thống và bằng chứng kỹ thuật: một harness có ràng buộc sư phạm xuyên suốt pipeline, memory architecture ba scope, Profile Synthesis Pipeline, Context Injection, HITL governance và optional Domain Plugin Interface cho mở rộng đa lĩnh vực sư phạm với null-plugin contract.

## 6.2 Trả lời câu hỏi nghiên cứu

**RQ1**: Kết luận cần tóm tắt hệ thống đề xuất có vượt các baseline hay không, vượt ở task/metric nào, và có trade-off latency/cost nào đáng kể.

**RQ2**: Kết luận cần xác nhận CNTT/lập trình và Toán có cùng implement được Domain Plugin Interface không, có cần sửa core không, và null-plugin contract có pass không.

**RQ3**: Kết luận cần nêu IDA Loop có tạo ra personalization delta có ý nghĩa không, đặc biệt ở group-fit, activity differentiation, difficulty calibration và feedback alignment.

## 6.3 Limitations

- Chưa có human evaluation diện rộng trên lớp học thật.
- Chỉ đánh giá hai domain là CNTT/lập trình và Toán.
- Cá nhân hoá ở mức nhóm học sinh, chưa hỗ trợ per-student adaptive learning.
- LLM-as-judge và benchmark tự xây có rủi ro bias.
- Kết quả phụ thuộc model, corpus, verifier và chất lượng metadata.
- Prototype tập trung vào local/local-first workflow, chưa đánh giá tích hợp LMS hoặc deployment nhiều người dùng.

## 6.4 Future Work

- Mở rộng domain plugin sang Vật lý, Hoá học, Ngữ văn, Lịch sử và các domain ít có verifier hình thức.
- Tổ chức human evaluation với giáo viên và lớp học thật để đo usefulness, trust, workload reduction và learning outcome.
- Nghiên cứu fine-tune hoặc distill small LLM cho dữ liệu chương trình giáo dục Việt Nam.
- Tối ưu runtime local: quantization, caching, smaller verifier model, context compaction và batch retrieval.
- Tích hợp LMS hoặc gradebook để nhập/xuất dữ liệu học viên có kiểm soát.
- Phát triển privacy-preserving analytics và audit log cho teacher-controlled data governance.
