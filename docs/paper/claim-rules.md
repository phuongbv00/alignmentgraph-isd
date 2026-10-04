# Claim rules cho manuscript

> Đây là file **luật viết**, không phải giàn ý. Nó không mô tả nội dung paper — nội dung nằm
> trong chính `docs/paper/acm/`, và bản thảo là source of truth duy nhất cho nội dung.
> File này chỉ giữ phần **không thể đặt trong paper**: điều gì cấm viết, viết thay bằng gì,
> câu nào phải giữ nguyên văn, và điều gì bắt buộc phải khai.

**Nguồn thẩm quyền**, theo thứ tự:

1. Nhận xét Sprint 2 của GVHD, nhận 2026-09-28, lưu ở
   `docs/supervision/feedbacks/sprint2_20260928/` (`Nx_Sprint2_định_hướng.docx`). File này
   thay thế thiết kế thí nghiệm của Sprint 1 (giao thức thống nhất, các gate) và thắng khi hai
   nhận xét lệch nhau.
2. Nhận xét sau Sprint 1 và lộ trình thực nghiệm, nhận 2026-09-10, lưu ở
   `docs/supervision/feedbacks/sprint1_20260828_0908/` (`Nhan_xet_ĐG_Sprint1_Q2.docx`,
   `Lo_trinh_TN.docx`) — định vị và mức claim.
   Khi có nhận xét sprint mới thì thêm thư mục mới cạnh chúng và cập nhật mục này.
3. Master claim rule của GVHD 2026-08-17 (đã gộp vào bảng dưới).
4. `docs/guides/alignment_protocol.md` — spec canonical của phép đo alignment (mức claim RQ2).

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
| "hệ rẻ hơn baseline", mọi biến thể của claim tiết kiệm chi phí | Cost cao hơn react-isd nhiều lần (tune Sprint 2: khoảng 12×) | Câu cost ở §4, nguyên văn. |
| "chi phí được bù đắp bởi alignment/auditability" | Chưa có đánh giá người dùng nào chứng minh | Đặt cost cạnh alignment signals, traceability và auditability, không kết luận chiều nào thắng. |
| "tương đương" / "không khác biệt" vì chênh lệch nằm trong biên nhiễu 10,8 điểm | 10,8 là số mô tả của Sprint 1, không phải ngưỡng kiểm định | Paired effect size + CI + multiplicity correction đã định trước. |
| "chất lượng chương trình ADDIE hoàn chỉnh" khi output sinh ở `light` | `light` chỉ phát triển một lát cắt đại diện | Claim giới hạn rõ, và chỉ sau khi so light–full chứng minh tính đại diện. |
| "số agent gây ra…", "graph gây ra…" từ ablation | Mỗi trục ablation là một bundle cơ chế | *"The multi-agent bundle / the graph substrate bundle"*, kèm danh sách thành phần của bundle. |
| Mức giảm token/thời gian giữa các sprint là nhờ thuật toán | Thinking bị tắt cùng lúc; cách đo token và kiến trúc cũng đổi | Không báo before–after giữa các sprint như một so sánh tương đương. |
| "kết quả giữ cho mọi SLM" | Mới thiết kế trên Qwen ladder | *"Observed on the Qwen3.5 0.8B–9B ladder."* |
| Kết luận TN2 từ một measure, một phép thử hay một chiều dự đoán khác với bản đăng ký | Chọn measure sau khi thấy kết quả là post-hoc | Theo đúng `docs/guides/benchmark_guides.md` §5.5: measure chính, họ Holm 6 phép, quy tắc ủng hộ / ngược / không phát hiện. Mọi lần đổi sau freeze ghi ngày và khai. |
| "graph cải thiện chất lượng thiết kế" từ `objectives_closed_triad` | Triad references là structural compliance, và phần lớn do repair net viết | *"The graph substrate bundle yields more structurally closed objective–activity–assessment triads"*, kèm dạng `_unrepaired`. Nối với chất lượng chỉ qua đánh giá chuyên gia. |

Cấm tuyệt đối, không có cách viết thay thế:

- **Gọi một run là "deterministic".** Generation dùng temperature 0,7; mỗi ô TN1 là một lần
  sinh, không phải một giá trị tất định. Bootstrap theo scenario không thay cho biến thiên giữa
  các lần sinh.
- **Dùng dữ liệu dở của lần chạy chính thức bị gián đoạn (Sprint 2)** làm kết quả hoặc làm căn
  cứ chọn tham số.
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
- **Không gọi constrained decoding (pass 2 dưới schema per-run, `structured_outputs`) là
  đóng góp, trục ablation hay "tối ưu cho SLM".** Nó là kỹ thuật có sẵn của serving stack
  (vLLM/XGrammar), áp đồng nhất mọi arm và mọi nấc, được khai ở Experimental Setup như một
  điều kiện serving; tỉ lệ pass 2 chỉ báo mô tả theo size, không kèm câu claim.
- **Related Work không được claim đề xuất tốt hơn** trước khi có kết quả thực nghiệm.
- **Conclusion không giới thiệu claim/kết quả mới** và không nới phạm vi model family.

## 3. Từ vựng

- Điểm benchmark (ADDIE / Trajectory / Total, do ISD-Agent-Bench chấm) = **"LLM judge
  score(s)"** — luôn viết đủ **"LLM judge"**, không bao giờ gọi cụt là "judge", kể cả trong
  các cụm ghép ("LLM judge prompts", "LLM judge drift", "the second LLM judge").
  Giá trị đo bằng code tự xây = **"alignment signal(s)"**, không gọi là "alignment score(s)".
  Tập hợp vẫn gọi là "alignment panel"; hiệu chỉnh Holm trong một tín hiệu = "within-signal".
- Hai instrument trên là **outcome measures** (chấm sản phẩm). Ablation có thêm instrument thứ ba,
  **"process measures"**: đo quá trình tạo ra thiết kế (autonomy theo stage, % stage bị trần turn
  cắt, relation coverage, triad references, violation ledger). Không gọi là score hay signal, không
  đặt ngang hàng outcome: triad references là **structural compliance**, không phải chất lượng sư
  phạm. % stage bị cắt là điều kiện để đọc kết quả `agent_mode` (treatment fidelity).
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

Cost (Results/Limitations), nhận từ GVHD 2026-09-28:

> *"AlignmentGraph-ISD incurs substantial computational overhead relative to lightweight
> workflow-based baselines. We report this cost alongside its measurable alignment signals,
> structural traceability, and auditability, without interpreting the approach as
> computationally more efficient."*

Báo kèm: số tuyệt đối, tỷ lệ so với ReAct-ISD, số call và thời gian.

Câu evaluation của abstract — phép đo alignment không được đứng thành câu phương pháp riêng:

> *"We evaluate it with ISD-Agent-Bench and a deterministic, no-LLM alignment-score
> measurement…"*

Mức tất định được phép claim: *reproducible up to floating-point noise*, **không** phải
*bit-wise deterministic* (Bloom là argmax rời rạc).

## 5. Bắt buộc phải khai

- **Measure chính của trục substrate (H-S) được chốt ở giai đoạn tune, sau khi đã thấy dữ liệu tune.**
  Lý do là LLM judge chấm từng phase ADDIE riêng rẽ nên không nhìn thấy liên kết xuyên artifact, và
  panel không đọc id liên kết. Phải khai cả lý do lẫn thời điểm chốt (2026-10-05, trước freeze), cùng
  kết quả outcome của trục này dù không ủng hộ.

- **Cơ chế failure theo từng hệ**, không gộp một câu: `baseline` hỏng vì `LengthFinishReasonError`
  đúng tại `completion_tokens = 8192`; EduPlanner hỏng vì lỗi parse schema.
- **Can thiệp duy nhất lên một baseline**: prompt scaffolding của ReAct-ISD được dịch sang tiếng
  Anh — chỉ đổi ngôn ngữ, không đổi phương pháp. Ngôn ngữ corpus đồng nhất tiếng Anh *bằng thiết
  kế*, không bằng chỉ thị.
- **Ô nào trung bình trên tập scenario không đầy đủ thì phải có footnote `n`.**
- **Trần trajectory của judge**: evaluator chỉ đưa 20 tool call đầu, react-isd ~5 call nên được
  thấy trọn, hệ phân rã vài chục call trở lên nên chỉ thấy phần đầu. Đây là bất lợi cơ học, phải
  nói trước; chính sách hai lớp (cap 20 benchmark-comparable + cap 120 diagnostic, chấm offline
  từ trajectory đã lưu) chốt trước `test_90` và không đổi sau khi thấy kết quả. Vì vậy Total
  không được là thước đo duy nhất; hai lớp trajectory báo song song.
- **Trần token suy luận trên toàn ladder**: ladder serve với thinking bật, và phần suy nghĩ
  tiêu chung ngân sách completion với câu trả lời — nên một reply nghĩ vượt 8192 token không
  bao giờ đóng khối `</think>`, bị xếp là suy nghĩ từ đầu đến cuối, và trả về `content` rỗng mà
  harness ghi là `invalid_action`. Đó là nhiễu hạ tầng chảy vào trajectory, tức là một đại
  lượng được chấm điểm. `[serving].thinking_budget` chặn nó bằng cách ép khối suy nghĩ đóng
  lại. Phải khai: **con số này là bao nhiêu, nó áp lên mọi agent và mọi size như nhau, và nó
  chốt trên tune slice trước `isd-exp freeze` rồi không đổi sau khi thấy kết quả** — cùng chính
  sách với trần trajectory. Phải khai thêm rằng đây là **trần, không phải tắt**: model vẫn
  suy luận, chỉ bị giới hạn. Không được mô tả nó như một tối ưu tốc độ.
  Và phải khai **nấc nào thật sự bị ép**: một endpoint tự host ép được trần, một router tổng
  hợp thì chỉ ép được trạng thái tắt — nó chọn provider thượng nguồn theo từng request, nên
  cùng một tham số lúc được nghe lúc không (đo 2026-09-23). Ladder trộn hai loại endpoint sẽ
  ép trần ở nấc này và không ở nấc kia, tức là nhiễu thiên lệch theo đúng biến độc lập; nếu
  không tự host được cả bốn nấc thì posture hợp lệ duy nhất là `0`.
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
- **Coverage C2–C4 = 1,00 là structural compliance**, không phải pedagogical validity. Harness
  cưỡng chế một số tiêu chí ngay lúc submit: một objective phải có item ở mức Bloom khai báo
  bằng hoặc cao hơn nó (`fanout.item_level_errors`), một item không được chép lại câu của
  objective. Các tín hiệu panel đo cùng khía cạnh đó (congruence, Webb–Bloom, C2 similarity)
  vì vậy một phần là **phép kiểm hệ tuân thủ ràng buộc của chính nó**, không phải xác nhận độc
  lập về chất lượng giáo dục. Phải khai rõ, và đặt đánh giá chuyên gia (ẩn danh, cùng mẫu cho
  mọi hệ) làm bằng chứng độc lập.
- **Thành phần của từng bundle ablation.** `agent_mode` đổi cùng lúc: ranh giới ngữ cảnh, số
  persona, fan-out, Developer tier, re-dispatch và thời điểm repair. `context_mode` đổi toàn
  bộ máy alignment (graph, state read, routing, audit). Liệt kê trong Method, và chỉ suy luận
  về bundle.
- **Thinking, temperature, decoding và backend được khóa đồng nhất** cho mọi hệ và mọi nấc,
  và metadata backend (endpoint, engine, model revision) được lưu cùng run. Nấc nào đi qua
  router phải được nêu.
- **Ba LLM judge chấm toàn bộ output TN1**: GPT-6 Luna, Gemini 3.1 Flash-Lite và DeepSeek-V4.1-Flash,
  ba hãng khác nhau, không hãng nào là của agent (Qwen). Mỗi judge lưu điểm riêng, gộp bằng median
  của ba (chốt trước). Median của ba loại được một judge lệch; với hai judge thì median chỉ bằng trung
  bình cộng.
  - Khai roster thay cặp mặc định của ISD-Agent-Bench (GPT-4o-mini + Gemini 2.5 Flash-Lite). Lý do
    được phép viết: cặp mặc định chấm hẹp (độ lệch giữa scenario nhỏ) và GPT-4o-mini yếu khi chấm
    output dài (LongJudgeBench).
  - Lý do chọn từng judge phải đúng phạm vi bằng chứng: LongJudgeBench đo DeepSeek-V4-Flash (bản
    trước của V4.1-Flash), phải nói rõ là bản trước. GPT-6 Luna và Gemini 3.1 Flash-Lite **không có**
    benchmark judge công bố; không được viết như thể có.
  - Không được biện minh roster bằng kết quả so sánh agent. Tune đã được chấm bằng cả hai roster và
    thứ hạng thay đổi theo roster; phải khai điều này, và nên báo roster mặc định của benchmark như
    một lớp sensitivity.
  - Reasoning của cả ba judge bị tắt (evaluator gửi `reasoning.enabled=false`). GPT-6 Luna không
    nhận `temperature`, nên judge này không tất định; báo độ dao động khi chấm lại.
  - Ba judge lệch nhau nhiều về mức điểm tuyệt đối (trên tune: độ lệch chuẩn giữa judge khoảng 12
    điểm); báo con số này cùng điểm median.
  - Phải khai đã xác minh cả ba judge nhận đủ output dài và không chấm nội dung dài thành "vắng mặt"
    (trên tune: 25/26 mục bị đánh ABSENT là vắng thật trong output).
  - Cần thầy duyệt việc đổi roster (Sprint 2 chốt hai judge GPT-4o-mini và Gemini 2.5 Flash-Lite).
- **Scope phát triển (`development_mode`) của output được chấm**, và bằng chứng so light–full
  trên cùng scenario (đặc biệt rubric item 12, 17, 19, 22, 30) nếu claim dựa trên light.
- **Repeat của A0/ReAct-ISD không phải thiết kế lặp cân bằng.** Bảng bảy hệ dùng bộ run chung;
  phân tích repeat làm riêng và chỉ nói về độ ổn định của hai hệ đó. Không coi ba lần sinh cùng
  một scenario là ba scenario độc lập.
- **Failure policy**: failure = 0 là layer chính (đã định trước); complete-case là sensitivity;
  fail rate và nguyên nhân báo riêng.
- **Repair không bao giờ viết nội dung giảng dạy.** Việc gỡ các repair sinh artifact/cạnh giả
  (một activity "Guided practice for ILO-01", một module gán bừa vào activity đầu tiên) làm residual
  violation tăng; đó là số trở nên trung thực, không phải regression — và là ví dụ nên đưa vào
  Discussion về ranh giới giữa repair cấu trúc và viết lại nội dung.

## 6. Giới hạn phạm vi

Kết luận chỉ phát biểu **trên dải Qwen3.5 0.8B–9B** và trên ISD-Agent-Bench mở rộng. Bốn size
cùng một họ pretraining, nên hiệu ứng scale bị lẫn với công thức nội-họ; mở rộng sang
Llama/Gemma/Phi là giả thuyết. Nêu đúng một lần ở Threats, **không nới ở abstract hay
conclusion**.
