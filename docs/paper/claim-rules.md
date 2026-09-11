# Claim rules cho manuscript

> Đây là file **luật viết**, không phải giàn ý. Nó không mô tả nội dung paper — nội dung nằm
> trong chính `docs/paper/acm/`, và bản thảo là source of truth duy nhất cho nội dung
> (`docs/summary.md` đã xoá 2026-09-10 vì trùng nội dung với paper và luôn lệch khi paper đổi).
> File này chỉ giữ phần **không thể đặt trong paper**: điều gì cấm viết, viết thay bằng gì,
> câu nào phải giữ nguyên văn, và điều gì bắt buộc phải khai.

**Nguồn thẩm quyền**, theo thứ tự:

1. Nhận xét sau Sprint 1 của GVHD và lộ trình thực nghiệm, nhận 2026-09-10, lưu ở
   `docs/feedbacks/sprint1_20260828_0908/` (`Nhan_xet_ĐG_Sprint1_Q2.docx`,
   `Lo_trinh_TN.docx`) — hai file này quyết định định vị, mức claim và thiết kế thí nghiệm.
   Khi có nhận xét sprint mới thì thêm thư mục mới cạnh nó và cập nhật mục này.
2. Master claim rule của GVHD 2026-08-17 (đã gộp vào bảng dưới).
3. `docs/rq2_protocol.md` — spec canonical của phép đo alignment (mức claim RQ2).

## 1. Đơn vị so sánh là HỆ TÁC TỬ, không phải model

Đề tài đề xuất một kiến trúc agent. Vì vậy rào cản, công trình trước và khoảng trống đều phát
biểu về **các hệ tác tử ISD phụ thuộc API LLM thương mại**, không phát biểu về "LLM thương mại"
nói chung. Related Work cũng vậy: lớp đối sánh là các hệ tác tử được xây và kiểm chứng trên
model thương mại mạnh.

## 2. Claim bị cấm và cách viết thay thế

| Cấm viết | Lý do | Viết thay bằng (nguyên văn) |
|---|---|---|
| "vượt trội toàn diện", "tốt nhất mọi chỉ số" | Nhiều instrument, kết quả không ủng hộ | *"Competitive, robust, and more auditable under the tested SLM setting."* |
| "đo được đầy đủ constructive alignment" | Panel chỉ đo measurable signals, chưa validate construct | *"Measures explicit signals related to constructive alignment."* |
| "verifier cải thiện chất lượng" | Verifier là safety net + audit, chưa chứng minh tăng score | *"Verifier provides repair backstop and audit evidence."* |
| "hệ rẻ hơn baseline", mọi biến thể của claim tiết kiệm chi phí | Cost hiện cao hơn react-isd 15–55 lần | *"The method trades additional cost for explicit state and auditability."* |
| "kết quả giữ cho mọi SLM" | Mới thiết kế trên Qwen ladder | *"Observed on the Qwen3.5 0.8B–9B ladder."* |

Cấm tuyệt đối, không có cách viết thay thế:

- **Dùng số của sprint làm kết quả.** Số sprint đo trên một scenario thuộc `train_30`; chúng chỉ
  vào phụ lục kỹ thuật của luận văn, không bao giờ vào Results của paper. Nếu cần nhắc quá trình
  phát triển thì viết định tính, đúng câu của GVHD: *"The harness was stabilized before the
  official evaluation."*
- **Paper không bao giờ nhắc RAG.** RAG chỉ thuộc luận văn.
- **Không đặt tên tín hiệu là "precision"** — chữ đó ngụ ý khung retrieval cần threshold, thứ mà
  panel cố ý không có.
- **Không gọi complete-case là "unconditional".** Layer chính là `failure=0`; complete-case là
  sensitivity, tính trên output *có sẵn*.
- **Không claim novelty cho phép đo alignment.** Nó là measurement setup trong Experimental
  Design, văn phong "assemble/operationalize established criteria"; không có đề mục "protocol"
  trong Method, không đánh số đóng góp. Đóng góp vẫn đúng MỘT.
- **Related Work không được claim đề xuất tốt hơn** trước khi có kết quả thực nghiệm.
- **Conclusion không giới thiệu claim/kết quả mới** và không nới phạm vi model family.

## 3. Từ vựng

- Điểm benchmark = **"LLM judge score(s)"**. Giá trị panel = **"alignment score(s)"**. Tập hợp
  vẫn gọi là "alignment panel".
- Tên từng tín hiệu đặt theo **phép toán nó tính**, không theo construct nó phục vụ — nên hậu tố
  là `*_similarity`, và chữ "alignment" chỉ đứng ở tên protocol và ở các vế của `aligned(o)`.
- RQ2 dừng ở **"measurable signals of constructive alignment"**, không phải "đo được alignment".
- Cosine luôn mô tả là *rectified cosine on [0, 1], no matching threshold* — là lựa chọn thang
  đo, không phải ngưỡng ghép cặp.
- Định vị hệ: **"workflow-style / role-decomposed multi-agent"** (họ SOP-style như MetaGPT:
  điều phối tĩnh, không negotiation, không dynamic planning).
- Không dùng "tuning" cho vòng sửa của harness — thuật ngữ chuẩn repo-wide là "refinement".

## 4. Câu chuẩn, giữ nguyên văn

Trần token (Experimental Design):

> *"we cap generation at 8192 tokens per call — the budget a 4B model leaves on a single
> 12–16 GB GPU, the deployment target this work claims. The 24–32 GB pods were rental
> convenience for running the ladder in parallel, not the claimed envelope."*

Tính tất định của phép đo (§Measures):

> *"quy trình chấm không dùng LLM và không có thành phần ngẫu nhiên; kết quả tái lập được nhờ
> pin phiên bản encoder và cache embedding"*

Câu evaluation của abstract — phép đo alignment không được đứng thành câu phương pháp riêng:

> *"We evaluate it with ISD-Agent-Bench and a deterministic, no-LLM alignment-score
> measurement…"*

Mức tất định được phép claim: *reproducible up to floating-point noise*, **không** phải
*bit-wise deterministic* (Bloom là argmax rời rạc).

## 5. Bắt buộc phải khai

- **Cơ chế failure theo từng hệ**, không gộp một câu: `baseline` hỏng vì `LengthFinishReasonError`
  đúng tại `completion_tokens = 8192`; EduPlanner hỏng vì lỗi parse schema.
- **Can thiệp duy nhất lên một baseline**: prompt scaffolding của ReAct-ISD được dịch sang tiếng
  Anh — chỉ đổi ngôn ngữ, không đổi phương pháp. Ngôn ngữ corpus đồng nhất tiếng Anh *bằng thiết
  kế*, không bằng chỉ thị.
- **Ô nào trung bình trên tập scenario không đầy đủ thì phải có footnote `n`.**
- **Trần trajectory của judge**: evaluator chỉ đưa 20 tool call đầu, react-isd ~5 call nên được
  thấy trọn, hệ phân rã 150–350 call nên chỉ thấy phần đầu. Đây là bất lợi cơ học, phải nói
  trước; chính sách hai lớp (cap 20 benchmark-comparable + cap 120 diagnostic) chốt trước
  `test_90` và không đổi sau khi thấy kết quả.
- **`objective_cognitive_congruence` dùng cosine để ghép cặp** trước khi so Bloom, nên họ B
  không độc lập hoàn toàn với họ A; chỉ Porter và Webb–Bloom là đối trọng đầy đủ. Nói trước,
  không chờ reviewer bắt.
- **Panel đổi định nghĩa 2026-08-30**: `porter_mean` giờ là trung bình trên ba cạnh tam giác,
  nên mọi số `porter_*` cũ không so được.
- **Bẫy artifact chi phí**: `metadata.cost_usd` sai (giá API thương mại trên pod tự host);
  `metadata.total_tokens` top-level = 0 với phần lớn agent — chỉ đọc `token_usage.*`;
  wall-clock là **queued throughput, không phải latency**.
- **Hình dạng judge-bất-biến / alignment-dịch phải trình bày ở CẢ HAI cách đọc**: (thuận) LLM
  judge không nhạy với alignment, đúng lý do RQ2 tồn tại; (nghịch) instrument duy nhất tách được
  các arm lại chung construct với thiết kế bị ablate — đó là mô tả của thiếu discriminant
  validity. Dự đoán phân biệt phải phát biểu TRƯỚC khi kiểm.
- **Repair không bao giờ viết nội dung giảng dạy.** Việc gỡ repair sinh cạnh C5 giả làm residual
  violation tăng; đó là số trở nên trung thực, không phải regression — và là ví dụ nên đưa vào
  Discussion về ranh giới giữa repair cấu trúc và viết lại nội dung.

## 6. Giới hạn phạm vi

Kết luận chỉ phát biểu **trên dải Qwen3.5 0.8B–9B** và trên ISD-Agent-Bench mở rộng. Bốn size
cùng một họ pretraining, nên hiệu ứng scale bị lẫn với công thức nội-họ; mở rộng sang
Llama/Gemma/Phi là giả thuyết. Nêu đúng một lần ở Threats, **không nới ở abstract hay
conclusion**.
