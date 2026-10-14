# docs — bản đồ tài liệu

Mỗi thư mục trả lời một câu hỏi khác nhau. Trước khi thêm file mới, đọc cột "canonical
cho" dưới đây: nếu câu hỏi đã có chủ, sửa file đang có thay vì viết file thứ hai —
tài liệu trùng nội dung luôn lệch nhau sau vài tuần.

| Đường dẫn | Canonical cho |
|:---|:---|
| `paper/rev-ecit2026-v2/` | **Bản nộp REV-ECIT 2026** (bài ứng dụng theo góp ý thầy Hải 2026-10-13): mô hình tổng quát, một bảng LLM judge, triển khai ứng dụng web trên học phần tiếng Việt; không nêu tên hệ. `make_tables.py` sinh `generated/` từ `pooled_comparison.json` và run của web app (`--case-dir`). |
| `paper/rev-ecit2026/` | **Bản v1, seed bài tạp chí** (tag `rev-ecit2026-v1`, không sửa để nộp hội thảo): bài phương pháp đủ TN1, TN2 2×2 và panel 6 tín hiệu. Source of truth cho cấu trúc và luận điểm của bài tạp chí. `generated/`, `main.pdf` và `figures/*.pdf` được commit. |
| `paper/journal-code-fixes.md` | Lỗi code (`alignmentgraph-isd`) và việc dời sang bài tạp chí, rút từ review biên tập bản v2 (2026-10-14). Mục A1 giải thích vì sao sổ vi phạm của case được đối chiếu lại bằng `rev-ecit2026-v2/case/reconcile_ledger.py`. |
| `paper/claim-rules.md` | **Luật viết.** Điều gì cấm claim và viết thay bằng gì, từ vựng điểm số, câu phải giữ nguyên văn, điều bắt buộc phải khai. Chỉ luật, không nội dung — nên không thể stale so với bản thảo. |
| `paper/structure-guide.md` | Khung cấu trúc bài báo khoa học theo đề cương của GVHD. |
| `paper/refs-deployment-survey.md` | Tư liệu citation cho phần triển khai SLM trong giáo dục (Intro + Related Work). |
| `guides/benchmark_guides.md` | **Toàn bộ quy trình thực nghiệm**: split data → serving → tune → chạy ladder → audit → chấm alignment → pooling → sinh bảng cho paper, kèm định nghĩa metric (Phụ lục A). Đọc trước khi động vào bất cứ thứ gì liên quan tới experiment. |
| `guides/ablation_parity.md` | **Parity của trục `agent_mode`**: cái gì cố ý khác giữa multi và single, cái gì phải giữ như nhau và đi qua đường code nào, cùng các bất biến kiểm offline. Bản nháp chờ duyệt. |
| `guides/alignment_protocol.md` | **Đặc tả phép đo alignment (RQ2)**: panel, thống kê, sensitivity star, validity evidence. Paper được cập nhật TỪ file này. |
| `supervision/feedbacks/` | Nhận xét gốc của GVHD theo từng sprint (DOCX) + bản đọc được. **Nguồn thẩm quyền** cho định vị, mức claim và thiết kế thí nghiệm. |
| `supervision/reports/` | Báo cáo sprint gửi GVHD. |
| `supervision/slides/` | Slide deck báo cáo (HTML là bản gốc, PDF xuất ra từ nó). |
| `supervision/backlog.md` | Việc còn phải làm trước khi nộp Q2, theo nhãn R\* và T\*. |
| `supervision/authors.md` | Thông tin tác giả / GVHD cho byline. Sửa ở đây trước rồi mới propagate. |
| `supervision/scripts/` | Xuất slide HTML và Markdown ra PDF (headless Chrome, macOS). |
| `refs/` | Tài liệu tham khảo kéo về từ repo khác — hiện có source của chính bài ISD-Agent-Bench. Chỉ để đọc, không code nào import. |

## Số liệu

`docs/generated/` **không nằm trong git và không được tạo bằng tay**: `isd-exp report sync`
copy bảng, figure và macro sinh tự động vào đó, để bản thảo tạp chí sau này `\input` từ đó bằng
đường dẫn tương đối. Bài hội thảo không đọc thư mục này: `paper/rev-ecit2026/make_tables.py`
sinh bảng và macro thẳng vào `paper/rev-ecit2026/generated/` từ hai file pooled JSON. Thư mục hiện đang trống — bản cũ bị xoá 2026-09-17 vì là số của kiến trúc
LangGraph đã bỏ, và `main.tex` đã comment hết các dòng `\input` tương ứng, mỗi chỗ cần số đánh
dấu `\TBD`. Khi TN1/TN2 chạy xong và chấm xong thì sinh lại, chạy `isd-exp report sync`, bật
lại bốn dòng `\input` và thay từng `\TBD`.

Không gõ tay bất kỳ con số thực nghiệm nào vào bản thảo.
