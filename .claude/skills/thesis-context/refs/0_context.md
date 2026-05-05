# Context & Quyết định dự án

## 1. Định vị đề tài

**Tên đề tài**: "Ứng dụng mô hình Multi-Agent Agentic RAG trong đào tạo và hướng dẫn kỹ thuật"

Đề tài mang định hướng ứng dụng, tập trung thiết kế và hiện thực một hệ thống hỗ trợ giáo viên các tác vụ sư phạm kỹ thuật dựa trên Multi-Agent Agentic RAG. Kiến trúc đề xuất được tổ chức quanh ba trụ cột: Pedagogy-Constrained Orchestration, Edge-LLM-Aware Orchestration và Pedagogy Domain Extension.

## 2. Phạm vi và ràng buộc

**Phạm vi triển khai/đánh giá**:

- Miền thực nghiệm: CNTT/lập trình.
- Mức sản phẩm: prototype chạy local, đủ để demo và đánh giá kỹ thuật.
- LLM: local / mã nguồn mở trên edge (Gemma 4 E2B/E4B).
- Đánh giá: benchmark tự động + LLM-as-judge; không human eval diện rộng.

**Tác vụ chính trong case study**:

- Hỏi đáp/giải thích dựa trên tài liệu học phần.
- Sinh bài tập lập trình nhỏ kèm lời giải tham chiếu/test cơ bản.
- Sinh feedback cho bài nộp lập trình dựa trên kết quả verifier.

**Ngoài phạm vi luận văn**:

- Xây dựng LMS hoàn chỉnh.
- Cá nhân hóa lộ trình học dài hạn.
- Đánh giá hiệu quả học tập qua nhiều tuần/lớp thật.
- Triển khai và đánh giá thực nghiệm extension cho nhiều ngành kỹ thuật.

Kiến trúc vẫn được thiết kế có điểm mở rộng cho nhiều miền kỹ thuật thông qua Pedagogy Domain Extension. Tuy nhiên, khả năng mở rộng này được khẳng định ở mức thiết kế/interface; bằng chứng thực nghiệm chỉ nằm trong case study CNTT/lập trình.

## 3. Mục tiêu và câu hỏi đánh giá

- **EQ1**: Trong case study CNTT/lập trình, kiến trúc đề xuất có hiệu quả hơn LLM-only, Naive RAG, Generic ReAct ARAG và Fixed MA-ARAG trên các tác vụ hỗ trợ sư phạm đã giới hạn không?
- **EQ2** _(optional — chỉ đưa vào nếu đủ thời gian/kết quả)_: Với cùng benchmark case study, kiến trúc đề xuất chạy local small LLM có đạt chất lượng cạnh tranh với phương án dùng LLM tham số lớn / thương mại không? (trade-off an toàn dữ liệu vs chất lượng)

## 4. Đóng góp kỹ thuật dự kiến

Đề tài đóng góp ở mức thiết kế hệ thống, hiện thực prototype và đánh giá kỹ thuật, không ở mức phát minh thuật toán mới. Phần này liệt kê **artifact** của đồ án; các nguyên lý thiết kế bên trong được mô tả riêng ở mục 5.

1. **Kiến trúc đề xuất**: một kiến trúc Multi-Agent Agentic RAG được tùy chỉnh cho hỗ trợ sư phạm kỹ thuật dưới ràng buộc local small LLM, tổ chức quanh ba trụ cột: Pedagogy-Constrained Orchestration, Edge-LLM-Aware Orchestration và Pedagogy Domain Extension.
2. **Extension implementation cho miền sư phạm CNTT/lập trình**: một bản hiện thực cụ thể của Pedagogy Domain Extension cho miền CNTT/lập trình, bao gồm metadata schema, retrieval policy, verifier lập trình, error taxonomy, feedback template, pedagogical constraints và corpus ingestion pipeline.
3. **Prototype end-to-end**: hệ thống chạy được trên phạm vi case study, bao gồm corpus nội bộ, retrieval local, các flow hỏi đáp/sinh bài tập/sinh feedback, verifier lập trình và review flow cho giáo viên.
4. **Bộ đánh giá kỹ thuật**: benchmark nhỏ, baseline comparison với LLM-only/Naive RAG/Generic ReAct ARAG/Fixed MA-ARAG và ablation cho các thành phần chính của prototype.

## 5. Trụ cột kiến trúc

1. **Pedagogy-Constrained Orchestration**: các tác vụ như hỏi đáp tài liệu, sinh bài tập và sinh feedback được thực thi dưới dạng task graph có kiểm soát. Core điều phối retrieval, generation, verification, repair và HITL theo từng bước; output phải thỏa các ràng buộc sư phạm như Bloom/rubric alignment, citation coverage, misconception mapping và feedback policy.
2. **Edge-LLM-Aware Orchestration**: orchestration được thiết kế theo ràng buộc context window, năng lực suy luận và tài nguyên tính toán hạn chế của local LLM; hệ thống giới hạn tool scope, retrieval/context budget, retry depth và chia nhỏ tác vụ để giảm tải cho model.
3. **Pedagogy Domain Extension**: mỗi miền sư phạm-kỹ thuật được bổ sung vào hệ thống dưới dạng một extension, khai báo metadata schema, task schema, retrieval policy, verifier/tool interface, error taxonomy, feedback template, pedagogical constraints và corpus ingestion pipeline. Core chỉ phụ thuộc vào các khai báo này thay vì hard-code logic của từng miền.

## 6. Ranh giới kết luận

- Không xem từng kỹ thuật riêng lẻ như graph orchestration, verifier, self-repair, Bloom/rubric constraint hay extension mechanism là đóng góp mới.
- Kết quả đánh giá chỉ kết luận trong phạm vi case study CNTT/lập trình và benchmark đã xây dựng.
- Pedagogy Domain Extension là cơ chế mở rộng ở mức kiến trúc; luận văn không khẳng định đã chứng minh hệ thống scale thực nghiệm sang nhiều ngành khác trong miền sư phạm kỹ thuật.

## 7. Format & Template

Dùng template **SOICT_DATN_Application_VIE_Template** tại [templates/SOICT_DATN_Application_VIE_Template/](templates/SOICT_DATN_Application_VIE_Template/).

Cấu hình preamble từ [templates/.../DoAn.tex](templates/SOICT_DATN_Application_VIE_Template/DoAn.tex):

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
