# Context & Quyết định dự án

## Đề tài & Các quyết định đã chốt

**Tên đề tài**: "Ứng dụng mô hình Multi-Agent Agentic RAG trong đào tạo và hướng dẫn kỹ thuật"

**Phát biểu định vị** (dùng xuyên suốt quyển):
> Đề tài không định vị đóng góp ở việc xây dựng một agent platform tổng quát kiểu Claude Code/Cursor/Devin, cũng không claim rằng việc chia hệ thống thành nhiều agent, supervisor agent, plugin hay tool registry là mới. Đề tài định vị đóng góp ở việc chuyên biệt hóa Agentic RAG cho bối cảnh sư phạm kỹ thuật dưới ràng buộc local small LLM: workflow được biểu diễn bằng typed task graph, output được kiểm chứng bằng verifier miền và các lần retry/repair được dẫn dắt bởi lỗi có cấu trúc, đồng thời mọi nội dung sinh ra phải thỏa các ràng buộc sư phạm như Bloom alignment, constructive alignment, citation coverage, rubric consistency, misconception mapping và HITL gate. Hệ thống được hiện thực và đánh giá trên miền lập trình/CNTT như một proof-of-concept cho kiến trúc có khả năng mở rộng sang các ngành kỹ thuật khác thông qua domain plugin.

Ba cơ chế kỹ thuật làm trọng tâm bảo vệ:

1. **Typed Task Graph Orchestration**: tác vụ sư phạm được phân rã thành đồ thị các bước có kiểu rõ ràng; mỗi node định nghĩa `input_schema`, `output_schema`, `allowed_tools`, `retrieval_policy`, `verifier`, `retry_policy` và `stop_condition`.
2. **Verification-Guided Retry/Repair**: lỗi từ verifier được cấu trúc hóa thành `error_type`, `failed_component`, `evidence`, `repair_action`; hệ thống sửa đúng thành phần lỗi thay vì regenerate toàn bộ output.
3. **Pedagogy-Constrained Generation**: output phải thỏa các ràng buộc sư phạm và bằng chứng, gồm Bloom alignment, citation coverage, rubric consistency, misconception taxonomy, feedback policy và HITL.

- **Đóng góp**: cơ chế Agentic RAG có typed task graph, verifier-guided repair và ràng buộc sư phạm; hiện thực qua core + domain plugin và đánh giá trên domain IT.
- **Ràng buộc cứng**: LLM chạy local / mã nguồn mở trên edge (Gemma 4 E2B/E4B).
- **Đánh giá**: benchmark tự động + LLM-as-judge (không human eval diện rộng).

## Mục tiêu đề tài

- **EQ1**: TTG-ARAG (Typed Task Graph Agentic RAG — một hiện thực có kiểm soát của Multi-Agent Agentic RAG) có hiệu quả hơn Generic ReAct ARAG, Fixed MA-ARAG và RAG thuần trên bài toán hỗ trợ sư phạm không? (đánh giá qua ablation)
- **EQ2** _(optional — xác định sau khi có kết quả EQ1)_: Hệ thống TTG-ARAG chạy local small LLM có đạt chất lượng cạnh tranh với phương án dùng LLM tham số lớn / thương mại không? (trade-off an toàn dữ liệu vs chất lượng)

## Đóng góp dự kiến của đề tài

Đề tài dự kiến đóng góp ba thành phần kỹ thuật, được xác nhận bằng thực nghiệm ablation:

1. **Typed Task Graph Orchestration cho tác vụ sư phạm kỹ thuật**: thay vì agent loop tự do, workflow được mô hình hóa thành đồ thị các node có schema, tool scope, retrieval policy, verifier và retry policy rõ ràng.
2. **Verification-Guided Retry/Repair**: verifier trả lỗi có cấu trúc để hệ thống sửa đúng thành phần lỗi như lời giải, test case, citation, feedback hoặc Bloom alignment; không regenerate toàn bộ output một cách mơ hồ.
3. **Pedagogy-Constrained Agentic RAG**: output phải thỏa các ràng buộc sư phạm và bằng chứng như Bloom alignment, constructive alignment, citation coverage, rubric consistency, misconception mapping, feedback policy và HITL.

Kiến trúc core + domain plugin là phương tiện hiện thực các cơ chế trên, không phải claim novelty chính. Plugin CNTT/lập trình được dùng làm proof-of-concept để đánh giá thực nghiệm; các domain kỹ thuật khác là hướng mở rộng.

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
