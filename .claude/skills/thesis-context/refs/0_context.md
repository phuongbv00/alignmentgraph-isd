# Context & Quyết định dự án

## Đề tài & Các quyết định đã chốt

**Tên đề tài**: "Ứng dụng mô hình Multi-Agent Agentic RAG trong đào tạo và hướng dẫn kỹ thuật"

**Định vị & scope lock**:

> Đề tài mang định hướng ứng dụng, tập trung thiết kế và hiện thực một hệ thống hỗ trợ sư phạm kỹ thuật dựa trên Multi-Agent Agentic RAG. Đóng góp kỹ thuật của đề tài nằm ở cách tổ chức workflow Agentic RAG cho bối cảnh sư phạm kỹ thuật dưới ràng buộc local small LLM, thông qua typed task graph, verifier-guided repair, các tiêu chí sư phạm và HITL. Kiến trúc được thiết kế có các điểm mở rộng cho nhiều miền kỹ thuật thông qua cơ chế domain plugin; tuy nhiên, trong phạm vi luận văn, hệ thống chỉ được triển khai và đánh giá thực nghiệm trên case study CNTT/lập trình.

**Signature của luận văn**:

> TTG-ARAG: kiến trúc Multi-Agent Agentic RAG được tuỳ chỉnh cho tác vụ hỗ trợ sư phạm kỹ thuật trên local small LLM.

**Ranh giới đóng góp kỹ thuật**:

- Không xem từng kỹ thuật riêng lẻ như graph orchestration, verifier, self-repair, Bloom/rubric constraint hay plugin architecture là đóng góp mới.
- Đóng góp nằm ở mức **thiết kế và tích hợp hệ thống**: tổ hợp có chủ đích các kỹ thuật đã biết thành một workflow hỗ trợ sư phạm có kiểm soát, phù hợp với local small LLM và dữ liệu giáo viên nội bộ.
- Kết quả đánh giá chỉ kết luận trong phạm vi case study CNTT/lập trình: TTG-ARAG có/không cải thiện so với LLM-only, Naive RAG, Generic ReAct ARAG và Fixed MA-ARAG trên benchmark đã xây dựng.

Ba cơ chế kỹ thuật là trụ cột hiện thực của hệ thống:

1. **Typed Task Graph Orchestration**: tác vụ sư phạm được phân rã thành đồ thị các bước có kiểu rõ ràng; mỗi node định nghĩa `input_schema`, `output_schema`, `allowed_tools`, `retrieval_policy`, `verifier`, `retry_policy` và `stop_condition`.
2. **Verification-Guided Retry/Repair**: lỗi từ verifier được cấu trúc hóa thành `error_type`, `failed_component`, `evidence`, `repair_action`; hệ thống sửa đúng thành phần lỗi thay vì regenerate toàn bộ output.
3. **Pedagogy-Constrained Generation**: output phải thỏa các ràng buộc sư phạm và bằng chứng, gồm Bloom alignment, citation coverage, rubric consistency, misconception taxonomy, feedback policy và HITL.

- **Đóng góp**: một kiến trúc Agentic RAG chuyên biệt cho sư phạm kỹ thuật chạy local small LLM, tích hợp typed workflow, verifier-guided repair, pedagogical constraints, HITL và domain plugin; được đánh giá bằng comparison + ablation trên domain IT. Domain plugin là cơ chế phân tách thiết kế, không phải bằng chứng rằng hệ thống đã scale sang nhiều ngành.
- **Ràng buộc cứng**: LLM chạy local / mã nguồn mở trên edge (Gemma 4 E2B/E4B).
- **Đánh giá**: benchmark tự động + LLM-as-judge (không human eval diện rộng).

## Mục tiêu đề tài

- **EQ1**: Trong miền CNTT/lập trình được chọn làm case study, TTG-ARAG (Typed Task Graph Agentic RAG — một hiện thực có kiểm soát của Multi-Agent Agentic RAG) có hiệu quả hơn Generic ReAct ARAG, Fixed MA-ARAG và RAG thuần trên các tác vụ hỗ trợ sư phạm đã giới hạn không? (đánh giá qua comparison + ablation)
- **EQ2** _(optional — chỉ đưa vào nếu đủ thời gian/kết quả)_: Với cùng benchmark case study, hệ thống TTG-ARAG chạy local small LLM có đạt chất lượng cạnh tranh với phương án dùng LLM tham số lớn / thương mại không? (trade-off an toàn dữ liệu vs chất lượng)

**Phạm vi tác vụ chính**:

- Hỏi đáp/giải thích dựa trên tài liệu học phần.
- Sinh bài tập lập trình nhỏ kèm lời giải tham chiếu/test cơ bản.
- Sinh feedback cho bài nộp lập trình dựa trên kết quả verifier.

Không mở rộng sang xây dựng LMS hoàn chỉnh, cá nhân hóa lộ trình học dài hạn, đánh giá hiệu quả học tập qua nhiều tuần, hay triển khai plugin cho nhiều ngành kỹ thuật trong phạm vi luận văn.

## Đóng góp dự kiến của đề tài

Đề tài dự kiến đóng góp ở mức thiết kế hệ thống, hiện thực prototype và đánh giá kỹ thuật, không ở mức phát minh từng cơ chế riêng lẻ:

1. **TTG-ARAG cho sư phạm kỹ thuật chạy local small LLM**: một cấu hình Agentic RAG chuyển agent loop tự do thành typed workflow có schema, tool scope, retrieval policy, verifier, retry policy và stop condition rõ ràng.
2. **Cơ chế tích hợp verifier miền với targeted repair**: dùng kết quả kiểm chứng có cấu trúc để sửa đúng component lỗi như lời giải, test case, citation, feedback hoặc Bloom alignment, thay vì regenerate toàn bộ output.
3. **Pipeline sinh nội dung bị ràng buộc bởi yêu cầu sư phạm**: đưa Bloom alignment, constructive alignment, citation coverage, rubric consistency, misconception mapping, feedback policy và HITL thành điều kiện kiểm tra trong pipeline.
4. **Đánh giá kỹ thuật trên phạm vi đã giới hạn**: xây bộ benchmark nhỏ trên miền CNTT/lập trình để so sánh toàn bộ cấu hình TTG-ARAG và từng thành phần với các baseline RAG/Agentic RAG tổng quát. Kết quả chỉ kết luận trong phạm vi benchmark/case study này.

Kiến trúc core + domain plugin là phương tiện hiện thực và tách phần chung/phần miền. Plugin CNTT/lập trình được dùng làm proof-of-concept để đánh giá thực nghiệm; các domain kỹ thuật khác là hướng mở rộng và chỉ được thảo luận ở mức phân tích thiết kế.

## Format & Template

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
