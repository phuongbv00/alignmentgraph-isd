# Context & Quyết định dự án

## 1. Định vị đề tài

**Tên đề tài**: "Thiết kế và Hiện thực Pedagogy Agent Harness cho Thiết kế Dạy học và Đánh giá Cá nhân hoá"

Đề tài mang định hướng thiết kế hệ thống, tập trung xây dựng một **Pedagogy Agent Harness** — môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent có khả năng hỗ trợ thiết kế dạy học và đánh giá cá nhân hoá theo nhóm học sinh trong phạm vi một môn học/khoá học ngắn hạn. Quan hệ cốt lõi: **Agent = Model + Harness**; harness không "điều phối agent" như một thực thể bên ngoài, mà là thứ biến LLM thành agent. Cách tiếp cận này tương tự Claude Code = Claude model + coding harness, hay Codex = GPT + coding harness, nhưng hướng đến giáo viên thay vì lập trình viên.

Khái niệm vận hành trung tâm của harness là **IDA Loop** (Instructional Design–Assessment Loop) — vòng lặp thiết kế dạy học và đánh giá cá nhân hoá liên tục theo nhóm học sinh: giáo viên đánh giá nhóm học sinh → harness tổng hợp hồ sơ nhóm (StudentGroupProfile) → giáo viên thiết kế dạy học phân hoá theo hồ sơ → dạy → đánh giá lại → lặp. Vòng lặp diễn ra trong phạm vi một môn học/khoá học ngắn hạn; giáo viên tương tác qua **giao diện chat hội thoại**.

Harness được thiết kế thỏa hai ràng buộc cứng: (1) **pedagogical constraint enforcement** xuyên suốt pipeline — mọi giai đoạn thực thi phải tuân theo ràng buộc sư phạm, không giới hạn ở bước orchestration; (2) **domain extensibility với null-plugin contract** — harness nhận domain sư phạm mới qua optional plugin interface mà không thay đổi core; core hoạt động đầy đủ khi plugin = null, plugin chỉ bổ sung năng lực xác minh đặc thù domain. Multi-Agent và Agentic RAG là các cơ chế kỹ thuật bên trong harness, không phải tên gọi của hệ thống.

Bốn thành phần kiến trúc cốt lõi phân biệt harness với agentic RAG thông thường: **Intent Router** (phân loại chat input của giáo viên thành UC-ID / UC-AS / UPDATE_PROFILE / QUERY / FEEDBACK); **Course Memory** (lưu trữ CourseContext, StudentGroupProfiles, DiagnosisHistory, ArtifactLog xuyên suốt khoá học); **Profile Synthesis Pipeline** (tự động tổng hợp StudentGroupProfile từ kết quả UC-AS và merge với hồ sơ nhập tay của giáo viên); **Context Injection** (tự động inject hồ sơ nhóm và lịch sử chẩn đoán vào mọi task UC-ID/UC-AS mà không cần giáo viên nhắc lại).

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

**Session scope**: một môn học/khoá học ngắn hạn — Course Memory duy trì xuyên suốt khoá, reset khi bắt đầu khoá mới.

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

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: môi trường thực thi kết hợp với LLM tạo thành Pedagogy Agent (Agent = Model + Harness), thỏa hai ràng buộc thiết kế cứng: pedagogical constraint enforcement xuyên suốt pipeline và domain extensibility qua optional plugin interface (null-plugin contract). Harness vận hành IDA Loop qua bốn thành phần mới: Intent Router, Course Memory, Profile Synthesis Pipeline, Context Injection — kết hợp với LLM tạo thành agent có năng lực thiết kế dạy học và đánh giá cá nhân hoá theo nhóm học sinh — tương tự coding harness kết hợp với LLM tạo thành Claude Code hay Codex, nhưng dành cho giáo viên.
2. **Hai domain plugin implementation**: CNTT/lập trình và Toán — minh chứng tính tổng quát của domain plugin interface trên hai domain có đặc trưng khác biệt (có/không code verifier, error taxonomy khác nhau); đồng thời chứng minh null-plugin contract — core UC-ID và UC-AS hoạt động đầy đủ khi không load plugin.
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study với giao diện chat hội thoại, corpus nội bộ, retrieval local, Course Memory duy trì xuyên khoá học, Profile Synthesis Pipeline và teacher-controlled HITL flow.
4. **Bộ đánh giá kỹ thuật**: benchmark hai domain (~200 sample bao gồm IDA round-1 và round-2), baseline comparison với LLM-only/Naive RAG/Generic ReAct ARAG/Fixed MA-ARAG/Đề xuất-no-plugin, ablation cho các thành phần harness, và đánh giá personalization delta (EQ3).

## 5. Ràng buộc thiết kế cứng

1. **Pedagogical constraint enforcement**: mọi giai đoạn thực thi của harness (retrieval policy, generation, schema validation, verification, repair, output) phải tuân theo ràng buộc sư phạm — Bloom/rubric alignment, citation coverage, misconception mapping, feedback policy, HITL approval. Constraint không chỉ áp ở bước orchestration mà được enforce xuyên suốt pipeline qua typed schema, verifier, HITL gate và memory.
2. **Domain extensibility với null-plugin contract**: harness nhận domain sư phạm mới qua optional plugin interface mà không thay đổi core. Mỗi domain plugin khai báo metadata schema, task schema, retrieval policy, verifier/tool interface, error taxonomy, feedback template và corpus ingestion pipeline; core chỉ phụ thuộc vào interface này. Khi plugin = null, core vẫn thực thi UC-ID và UC-AS đầy đủ — null-plugin là một test case bắt buộc của interface compliance (EQ2).
3. **IDA Loop memory continuity**: Course Memory (CourseContext, StudentGroupProfiles, DiagnosisHistory, ArtifactLog) phải được duy trì xuyên suốt phạm vi một môn học/khoá học. StudentGroupProfile có thể được cập nhật từ hai nguồn độc lập (giáo viên nhập tay qua chat và Profile Synthesis Pipeline từ kết quả UC-AS) và phải merge nhất quán. Context Injection phải tự động inject hồ sơ nhóm và lịch sử chẩn đoán vào mọi task mà không cần giáo viên nhắc lại.

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
