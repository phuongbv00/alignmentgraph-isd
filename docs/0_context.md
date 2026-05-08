# Context & Quyết định dự án

## 1. Định vị đề tài

**Tên đề tài**: "Thiết kế và Hiện thực Pedagogy Agent Harness cho các Tác vụ Sư phạm"

Đề tài mang định hướng thiết kế hệ thống, tập trung xây dựng một **Pedagogy Agent Harness** — lớp điều phối và ràng buộc agent dành riêng cho các tác vụ sư phạm — tương tự cách Claude Code, OpenAI Codex là harness cho coding agent nhưng hướng đến giáo viên thay vì lập trình viên. Kiến trúc đề xuất được tổ chức quanh hai trụ cột: **Pedagogy-Constrained Orchestration** và **Pedagogy Domain Extension**. Multi-Agent và Agentic RAG là các cơ chế kỹ thuật bên trong harness, không phải tên gọi của hệ thống.

## 2. Phạm vi và ràng buộc

**Phạm vi triển khai/đánh giá**:

- Miền thực nghiệm: **hai case study — CNTT/lập trình và Toán**.
- Mức sản phẩm: prototype chạy local, đủ để demo và đánh giá kỹ thuật.
- LLM: pluggable component — harness không coupled với provider cụ thể; prototype sử dụng LLM theo thiết lập thực nghiệm (local hoặc API).
- Đánh giá: benchmark tự động + LLM-as-judge; không human eval diện rộng.

**Tác vụ chính trong case study CNTT/lập trình**:

- Hỏi đáp/giải thích dựa trên tài liệu học phần.
- Sinh bài tập lập trình kèm lời giải tham chiếu/test cơ bản.
- Sinh feedback cho bài nộp lập trình dựa trên kết quả verifier.

**Tác vụ chính trong case study Toán**:

- Sinh bài tập Toán kèm lời giải tham chiếu.
- Sinh feedback cho lời giải Toán của học viên.

**Ngoài phạm vi luận văn**:

- Xây dựng LMS hoàn chỉnh.
- Cá nhân hóa lộ trình học dài hạn.
- Đánh giá hiệu quả học tập qua nhiều tuần/lớp thật.
- Triển khai và đánh giá thực nghiệm extension cho nhiều domain hơn ngoài CNTT và Toán.

Kiến trúc được thiết kế có điểm mở rộng cho nhiều domain khác thông qua Pedagogy Domain Extension. Khả năng mở rộng này được khẳng định ở mức thiết kế/interface; bằng chứng thực nghiệm nằm trong hai case study CNTT/lập trình và Toán.

## 3. Mục tiêu và câu hỏi đánh giá

- **EQ1**: Trong hai case study CNTT/lập trình và Toán, kiến trúc đề xuất có hiệu quả hơn LLM-only, Naive RAG, Generic ReAct ARAG và Fixed MA-ARAG trên các tác vụ hỗ trợ sư phạm đã giới hạn không?
- **EQ2**: Pedagogy Domain Extension interface có đủ tổng quát để hai domain extension (CNTT và Toán) cùng implement mà không thay đổi core không? Câu hỏi này được trả lời bằng phân tích interface compliance và thiết kế, không bằng user study.

## 4. Đóng góp kỹ thuật dự kiến

Đề tài đóng góp ở mức thiết kế hệ thống, hiện thực prototype và đánh giá kỹ thuật, không ở mức phát minh thuật toán mới.

1. **Pedagogy Agent Harness — kiến trúc đề xuất**: lớp điều phối agent được thiết kế riêng cho tác vụ sư phạm, tổ chức quanh Pedagogy-Constrained Orchestration và Pedagogy Domain Extension. Harness cung cấp tool layer sư phạm, enforcement pedagogical constraints, HITL governance và extensibility mechanism — tương tự coding agent harness nhưng cho giáo viên.
2. **Hai domain extension**: CNTT/lập trình và Toán — hai bản hiện thực của Pedagogy Domain Extension interface, minh chứng tính tổng quát của interface trên hai domain có đặc trưng khác biệt (có/không code verifier, error taxonomy khác nhau).
3. **Prototype end-to-end**: hệ thống chạy được trên cả hai case study, bao gồm corpus nội bộ, retrieval local, các flow tác vụ sư phạm, verifier và teacher-controlled review flow.
4. **Bộ đánh giá kỹ thuật**: benchmark hai domain (~180 sample), baseline comparison với LLM-only/Naive RAG/Generic ReAct ARAG/Fixed MA-ARAG và ablation cho các thành phần chính của harness.

## 5. Trụ cột kiến trúc

1. **Pedagogy-Constrained Orchestration**: các tác vụ sư phạm được thực thi dưới dạng typed task graph có kiểm soát. Core điều phối retrieval, generation, verification, repair và HITL theo từng bước; output phải thỏa các ràng buộc sư phạm như Bloom/rubric alignment, citation coverage, misconception mapping và feedback policy; mọi thay đổi dữ liệu/trạng thái cần được giáo viên cho phép.
2. **Pedagogy Domain Extension**: mỗi domain sư phạm được bổ sung vào harness dưới dạng một extension, khai báo metadata schema, task schema, retrieval policy, verifier/tool interface, error taxonomy, feedback template, pedagogical constraints và corpus ingestion pipeline. Core chỉ phụ thuộc vào các khai báo này thay vì hard-code logic của từng domain.

## 6. Ranh giới kết luận

- Không xem từng kỹ thuật riêng lẻ như graph orchestration, verifier, self-repair, Bloom/rubric constraint hay extension mechanism là đóng góp mới.
- Kết quả đánh giá chỉ kết luận trong phạm vi hai case study CNTT/lập trình và Toán và benchmark đã xây dựng.
- Pedagogy Domain Extension là cơ chế mở rộng ở mức kiến trúc; luận văn không khẳng định đã chứng minh hệ thống scale thực nghiệm sang nhiều domain khác.
- LLM là pluggable component; luận văn không đánh giá riêng hiệu quả của từng LLM provider.

## 7. Format & Template

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
