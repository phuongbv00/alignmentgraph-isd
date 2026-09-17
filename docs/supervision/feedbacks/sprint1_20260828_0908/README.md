# Sprint 1 — Nhận xét của GVHD, quyết định và lộ trình thực nghiệm

> Bản tổng hợp hai file DOCX trong chính thư mục này. Hai file gốc là nguồn thẩm quyền, file
> này chỉ là bản đọc được: DOCX không diff được trong git và không grep được khi viết bài.
>
> - `Nhan_xet_ĐG_Sprint1_Q2.docx` — nhận xét, đánh giá, trả lời câu hỏi, định hướng.
> - `Lo_trinh_TN.docx` — lộ trình thực nghiệm tiết kiệm chi phí, 6 giai đoạn.
>
> Nhận ngày 2026-09-10, cho sprint kết thúc 2026-08-28/09-08. Luật viết bài rút ra từ đây nằm ở
> `docs/paper/claim-rules.md`; file này không lặp lại luật đó mà chỉ trỏ tới.

## 1. Kết luận chốt

Thầy thống nhất **phương án 2**: không mở rộng đề tài sang controlled lifecycle refinement ở
giai đoạn này. Trọng tâm là một harness đa tác tử có graph tường minh, giúp small language model
tạo thiết kế ADDIE ổn định, auditable và có measurable alignment signals tốt hơn baseline.

Mục tiêu công bố là **Q2**, không phải Q1. Lý do: bài có đóng góp framework và bằng chứng kỹ
thuật, nhưng không có human study đủ lớn cho Q1 mạnh.

Tên khuyến nghị cho manuscript, có thể chỉnh nhẹ sau thực nghiệm:

> **AlignmentGraph-ISD: A Graph-Guided Multi-Agent Harness for Auditable Instructional Systems
> Design with Small Language Models**

Không dùng chữ "controlled refinement" khi chưa có thí nghiệm refinement sau triển khai.

Sprint 1 được xếp loại là **sprint ổn định hệ thống**, không phải giai đoạn thực nghiệm báo cáo.
Mọi số hiện có đo trên một scenario thuộc `train_30`, nên chỉ có giá trị chẩn đoán.

## 2. Đánh giá Sprint 1

### 2.1. Điểm mạnh được ghi nhận

- **Hiểu đúng bản chất harness.** Hệ được tổ chức quanh stage loop, developer tier, substrate,
  relation registry, deterministic repair, audit graph và telemetry, không dừng ở prompt
  engineering. Phân biệt model sinh nội dung và harness điều phối là đúng trục đóng góp.
- **Giữ kỷ luật auditability ở điểm khó.** Việc gỡ cơ chế repair sinh cạnh C5 giả làm residual
  violation tăng, nhưng đó là quyết định đúng: hệ xây để alignment kiểm tra được, không được tự
  bịa quan hệ để đóng check. Nên đưa vào Discussion như ví dụ về ranh giới giữa repair cấu trúc
  và viết lại nội dung.
- **Nhận diện đúng LLM judge và alignment panel đo hai construct khác nhau.** Hai công cụ cho
  kết quả khác nhau không phải mâu thuẫn, đó chính là lý do RQ2 tồn tại.
- **Kỷ luật kỹ thuật tốt.** Bản vá xuất phát từ triệu chứng đo được trên run cụ thể; test tăng
  từ 367 lên 621.
- **Quan hệ lõi tiến bộ rõ.** P10/P11 từ 0.00/0.00 lên 1.00/1.00; C5 từ rất thấp về 1.00 trong
  run xác nhận.

### 2.2. Vấn đề phải sửa

| # | Vấn đề | Yêu cầu |
|---|---|---|
| 4.1 | Chưa có kết quả thực nghiệm chính thức | Không dùng số sprint làm claim. Không viết "thắng 7/7 run" hay "C3/C4 không chồng lấn" nếu chưa tái hiện trên `test_90`/`test_30` đúng protocol. |
| 4.2 | Token cost là rủi ro lớn nhất | Hệ tốn 148–347 call và 553k–1.30M token/run, cao hơn react-isd 15–55 lần. Cấm claim cost-efficient. Trước khi chấp nhận làm limitation phải làm đủ 4 việc: truy stage assessment, đo tỷ lệ prompt/completion, áp dụng adaptive batching, đo lại `STAGE_MAX_TURNS` trên một lát `train_30`. |
| 4.3 | Manuscript lệch với code sau pivot | Đây là lỗi quản trị nghiên cứu. Sửa ngay ở mức skeleton Method/Experiment/Claim, Results để trống. |
| 4.4 | Trần trajectory của judge bất công cho hệ phân rã | Evaluator chỉ đưa 20 tool call đầu. react-isd ~5 call nên được thấy trọn; hệ phân rã 150–350 call nên chỉ thấy phần đầu. Phải chốt trước ladder. |
| 4.5 | Alignment panel cần được bảo vệ chặt | Panel đo measurable signals, không thay thế expert judgment. `objective_cognitive_congruence` vẫn dùng cosine để ghép cặp trước khi so Bloom nên không độc lập hoàn toàn với họ A; chỉ Porter và Webb–Bloom là đối trọng tốt. Phải nói trước, không chờ reviewer bắt. |

## 3. Trả lời sáu câu hỏi đã xin ý kiến

**Có nên giữ trần 20 tool call của Trajectory judge không?**
Không để trần 20 làm cơ sở duy nhất. Chia hai lớp: lớp benchmark-comparable giữ trần 20 để đối
chiếu thiết lập gốc và ghi rõ limitation; lớp diagnostic/fairness chấm thêm với trần 120 hoặc
một cơ chế tóm tắt trajectory đã định nghĩa trước. Phải lưu toàn bộ trajectory và chấm offline
bằng cùng một protocol đã khóa, nhờ đó chỉ cần chấm lại trajectory chứ không chạy lại output.
Không đổi trần sau khi đã thấy kết quả `test_90`.

**Điểm Trajectory đi ngược thì xử lý thế nào?**
Không hòa giải bằng cách che hoặc giảm vai trò hậu nghiệm. Báo cáo ADDIE, Trajectory và Total
song song, nhưng narrative chính của RQ1 dẫn bằng ADDIE vì ADDIE đo chất lượng thiết kế, còn
Trajectory đo process conformance. `Total = 0.7·ADDIE + 0.3·Trajectory` là công thức của
benchmark, không phải primary metric của nghiên cứu, nên chỉ dùng để đối chiếu.

**Đồng bộ manuscript ngay hay chờ tune?**
Đồng bộ ngay ở mức cấu trúc. Cụ thể phải sửa: 13 relation thành **16 relation**; 7 tín hiệu panel
thành **6 tín hiệu**; ablation cũ thành **factorial 2×2**; bỏ các claim về verifier nếu không còn
đúng; cập nhật role decomposition, developer tier, graph/prose substrate và failure policy.

**Expert validation triển khai khi nào, quy mô bao nhiêu?**
Bắt buộc phải có, để bài không bị xem là chỉ tự chấm bằng máy. Làm **sau code freeze** và sau khi
có output chính thức của một mẫu scenario đại diện. Không dùng chuyên gia để chọn phương pháp
hoặc tinh chỉnh prompt sau khi đã nhìn kết quả.

| Mức | Quy mô | Mục tiêu |
|---|---|---|
| Tối thiểu chấp nhận được | 3 chuyên gia/giảng viên có kinh nghiệm thiết kế học phần | Xác nhận định tính, chấm một mẫu nhỏ về constructive alignment, tính khả thi, tính rõ ràng |
| Khuyến nghị | 5 chuyên gia, mỗi người chấm 8–12 sản phẩm đã ẩn tên hệ | Báo cáo agreement mô tả, nhận xét định tính, so sánh với panel deterministic |
| Tốt hơn nếu còn thời gian | 5–7 chuyên gia, rubric ổn định, có vòng pilot | Tăng độ tin cậy nếu nhắm Q2 tốt hoặc chuẩn bị mở lên Q1 |

**Có nên chuyển sang "graph lái model" trước ladder không?**
Không chuyển ngay. Hướng "graph lái, model điền" có lợi về referential integrity nhưng đổi cấu
trúc claim: C2–C5/P5/P10/P11 thành bảo đảm bằng xây dựng thay vì evidence về construct validity,
và panel RQ2 phải gánh toàn bộ phần semantic. Hoàn thành tune trên kiến trúc hiện tại trước; chỉ
triển khai nếu tune cho thấy lỗi tham chiếu vẫn phổ biến hoặc cost do read/repair sai reference
quá cao. Nếu triển khai thì viết contribution hai tầng: tầng cấu trúc là referential integrity
guaranteed by construction và kiểm bằng test, tầng ngữ nghĩa là semantic/cognitive alignment đo
bằng panel và expert validation. **Không triển khai cơ chế mới sau khi đã chạy `test_90`**, trừ
khi chấp nhận chạy lại toàn bộ.

**Experimental setup và alignment panel hiện tại có defensible không?**
Defensible cho Q2 nếu đóng gói đúng, với đủ các điều kiện: panel pre-specified; không có primary
endpoint; không claim đo đầy đủ constructive alignment; báo cả sensitivity; nêu rõ cognitive
congruence dùng cosine để ghép cặp; dùng `failure=0` làm layer chính; `test_90`/`test_30` disjoint
với `train_30`; có expert validation hoặc ít nhất qualitative expert audit. Panel được chấp nhận
như **instrument phụ trợ mạnh** cho RQ2, không được chấp nhận như bằng chứng duy nhất để tuyên bố
hệ "đạt constructive alignment".

## 4. Thiết kế thí nghiệm đã chốt

### 4.1. Cấu hình

| Hạng mục | Thiết kế cũ | Thiết kế chốt | Mục đích |
|---|---|---|---|
| Main ladder (TN1) | 4 size × 3 run × 7 agent × 90 = 7.560 | **4 size × 1 run × 7 agent × 90 = 2.520** | Giữ đủ ladder, bỏ nhân 3 toàn cục |
| Ablation (TN2) | 2 size × 3 run × 4 arm × 30 = 720 | **2 size × 1 run × 4 arm × 30 = 240** | Đủ kiểm cơ chế, giảm chi phí |
| Repeat | Lặp 3 lần ở mọi ô | Chỉ lặp có mục tiêu trên subset | Kiểm robustness thay vì lặp toàn bộ |
| LLM judge | 2 judge cho toàn bộ | **1 judge full + 1 judge corroboration subset** | Giảm cloud cost |
| Alignment panel | Full + sensitivity rộng | Full cấu hình chính; sensitivity trên subset | Giữ RQ2, giảm chấm phụ |

Tổng mức giảm khoảng **60–70% khối lượng generation** so với thiết kế cũ.

> **Mâu thuẫn giữa hai file và cách giải quyết.** `Nhan_xet` §6.4 mục 8 và §7.1 vẫn ghi 3 run
> độc lập mỗi ô và 2 judge cố định; `Lo_trinh` — viết sau, dành riêng cho lộ trình thực nghiệm —
> chốt 1 run deterministic mỗi ô, 1 judge full cộng 1 judge corroboration subset, và targeted
> repeat thay cho nhân 3. **`Lo_trinh` thắng.** Đây là con số đang dùng trong `CLAUDE.md` và
> trong pipeline `isd-exp comparison pool`. Hệ quả kéo theo: không tồn tại SD giữa các run ở ô
> chỉ chạy một lần, nên spread mô tả phải là SD **across scenarios**, còn khoảng tin cậy là
> bootstrap.

### 4.2. Nguyên tắc thống kê

Main ladder dùng deterministic decoding và fixed seed, phân tích **paired theo scenario**.
Uncertainty báo bằng bootstrap 95% CI, paired Wilcoxon, rank-biserial effect size và Holm
correction. **Không dùng SD giữa 3 lần chạy làm trụ chính.** Layer chính là `failure = 0`,
complete-case là sensitivity.

### 4.3. TN1 — Ladder comparison

Trả lời RQ1 và RQ2 ở cấp so sánh với baseline. Qwen3.5 0.8B/2B/4B/9B; 7 agent gồm A0 và 6
baseline; 90 scenario `test_90`; một lần deterministic mỗi ô. ADDIE chấm bằng một cloud judge cố
định trên toàn bộ output; Trajectory báo riêng, không dẫn narrative. Alignment panel cấu hình
chính self-host chạy trên toàn bộ output, giữ 6 tín hiệu phẳng, không composite hóa. Judge thứ
hai chỉ chấm subset stratified, ưu tiên A0 + react-isd + baseline mạnh nhất, để kiểm hướng kết
luận có phụ thuộc judge hay không. Output failure báo riêng.

```
Delta_s = score(A0, s) - score(baseline, s)
DiD     = Delta_largest - Delta_smallest
```

DiD âm nghĩa là lợi thế của A0 lớn hơn ở model nhỏ. Không dùng một khác biệt tại một size để suy
ra xu hướng theo size.

### 4.4. TN2 — Ablation factorial 2×2

Trả lời cơ chế nào đóng góp gì. Bốn arm multi-graph, multi-prose, single-graph, single-prose; hai
size 0.8B và 4B; 30 scenario `test_30`; một lần deterministic trước. Readout chính là coverage,
violation ledger, `gave_up`, context behaviour, cost và alignment panel deterministic. **Không dẫn
narrative ablation bằng LLM judge**, judge chỉ làm cross-check.

**A0 trong TN2 phải chạy lại trong chính TN2.** Không lấy A0 từ TN1 để so với các arm TN2 vì judge
session, scenario set và context thí nghiệm khác nhau.

### 4.5. Quyết định từng thành phần tốn chi phí

| Thành phần | Quyết định | Lý do |
|---|---|---|
| 4 model Qwen | **GIỮ** trong main ladder | Trục khoa học chính về model size |
| 3 run toàn ladder | **BỎ** | Thay bằng deterministic + scenario-level inference + targeted repeat |
| 2 cloud judge full | **BỎ** | 1 judge full; judge thứ hai trên subset để corroborate |
| Nemotron alignment panel | **GIỮ** cấu hình chính full | Trục chính của RQ2, self-host và deterministic |
| Sensitivity star | **RÚT GỌN** | Chạy subset, không nhân toàn bộ cost |
| Ablation 2×2 | **GIỮ** nhưng chỉ 2 size | Đủ kiểm cơ chế ở hai đầu deployment envelope |
| Expert validation | **THÊM NHỎ** | Giá trị hơn việc chi tiền cho judge thứ hai toàn bộ |

## 5. Lộ trình sáu giai đoạn

Nguyên tắc xuyên suốt: chỉ chạy chính thức sau khi đã đóng băng code, prompt, split dữ liệu,
metric và cấu hình evaluator. Không dùng kết quả tune/debug trong bài báo. Không hy sinh các trục
khoa học chính.

### Giai đoạn 1 — Khóa lỗi kỹ thuật, chặn nguyên nhân phải chạy lại

1. Chốt trajectory cap trước khi chạy lớn: tăng ngưỡng, hoặc giữ 20 nhưng tách Trajectory thành
   chỉ số phụ và khai limitation. Không đổi sau code freeze.
2. Truy stage assessment: đọc trajectory của các run tốn nhiều call để xác định vì sao 25 lượt và
   14 read mà vẫn `gave_up`. Chưa sửa tham số theo cảm tính.
3. Tối ưu cost tối thiểu: ưu tiên adaptive batching, giảm schema/read dư thừa, đo lại
   `STAGE_MAX_TURNS` trên dữ liệu tune sau khi đã sửa nguyên nhân lãng phí.
4. Hoàn thiện regression test: giữ test tái hiện lỗi C1, C5, P10/P11, fallback, repair và
   transport. Mọi lỗi đã vá phải có test chặn tái phát.

**Gate sang giai đoạn 2:** không còn lỗi parse/fallback; C1–C5 và P10/P11 ổn định; không có
failure do harness; cost không còn tăng bất thường vì bug.

### Giai đoạn 2 — Canary và tune rẻ trên `train_30`

1. Canary 3 scenario: chạy A0, react-isd và một arm đối chứng, không gọi cloud judge. Chỉ đọc
   `gave_up`, coverage, violation ledger, call/token/time và alignment panel self-host.
2. Tune 10 scenario trên `train_30` để ước lượng cost, kiểm stage position, kiểm model nhỏ còn
   failure không, và xác nhận alignment panel phân giải được khác biệt.
3. Chạy đủ 4 ablation arm trên tune: xác nhận multi/single × graph/prose đều chạy hết budget một
   cách công bằng, không arm nào bị cắt chỉ vì trần.
4. Không lấy số tune đưa vào paper. `test_90` và `test_30` phải giữ sạch.

**Gate sang giai đoạn 3:** 10 scenario chạy sạch; không phải sửa code chức năng; cost estimate
chấp nhận được hoặc đã xác định rõ limitation.

### Giai đoạn 3 — Code freeze và preflight một lần

1. Đóng băng phiên bản: ghi code hash, prompt hash, checkpoint, decoding setting, split file,
   output cap, trajectory policy, metric version và judge prompt.
2. Khóa dữ liệu: tạo `test_30` stratified seed 42, kiểm disjoint với `train_30`; `test_90` giữ
   nguyên cho ladder.
3. Preflight tự động: kiểm server/model/API, quota, đường dẫn output, schema, cache, resume,
   disk, version và estimate cost trước khi bấm chạy.
4. Bật cache và resume: mỗi scenario/agent/size có khóa hash riêng, output đã hoàn thành không
   được sinh lại, judge score cũng cache theo output hash.

**Quy tắc:** sau code freeze chỉ rerun cell lỗi kỹ thuật thật sự, không rerun vì điểm chưa đẹp.

### Giai đoạn 4 — Main ladder chính thức

Theo §4.3. Mục tiêu là trả lời RQ1/RQ2 bằng một lần chạy chính thức sạch, không dùng lại dữ liệu
tune.

### Giai đoạn 5 — Ablation và repeat có mục tiêu

Theo §4.4, cộng targeted repeat: chỉ lặp thêm trên các ô quan trọng, ví dụ A0, react-isd và
baseline mạnh nhất ở 0.8B/4B trên 30 scenario. Nếu hướng hiệu ứng ổn định qua repeat thì dừng,
không mở rộng lặp sang toàn bộ ladder.

### Giai đoạn 6 — Expert validation nhỏ và viết bài Q2

1. Mời 3–5 giảng viên/chuyên gia ISD đánh giá một subset đại diện, tập trung constructive
   alignment, tính khả thi, khả năng audit và mức cần chỉnh sửa.
2. Đồng bộ manuscript đúng kiến trúc sau pivot: 2×2 factorial, 16 relation, panel 6 tín hiệu. Bỏ
   toàn bộ mô tả thiết kế cũ.
3. Claim đúng mức bằng chứng: nhấn robustness, measurable alignment signals và auditability.
4. Đóng gói reproducibility: manifest, seed, split, config, output hash, score cache và script
   thống kê, để tái tạo được mà không sinh lại model output.

### Thứ tự ưu tiên công việc (`Nhan_xet` §6.4)

| # | Việc | Sản phẩm bàn giao |
|---|---|---|
| 1 | Chạy lại đủ 4 arm trên cùng scenario để kiểm parity kỹ thuật sau bản vá C5 | Bảng coverage, cost, `gave_up`, panel 6 tín hiệu cho 4 arm |
| 2 | Truy nguyên stage assessment gây tốn lượt và `gave_up` | Báo cáo nguyên nhân: read cost, batch size, schema reject, hoặc context compaction |
| 3 | Tối ưu cost theo thứ tự prompt/completion audit → adaptive batching → đo lại `STAGE_MAX_TURNS` | Bảng trước/sau; không đổi treatment theo cách làm lệch ablation |
| 4 | Chạy tune đầy đủ `train_30`, chưa đụng `test_90` | Quyết định code freeze dựa trên tune; khóa budget, prompt, model, judge |
| 5 | Tạo `test_30` stratified seed 42, disjoint với `train_30` | Manifest và script kiểm disjoint |
| 6 | Đồng bộ manuscript theo thiết kế sau pivot | Method/Experiment/Claim đã cập nhật; Results để trống |
| 7 | Code freeze và gắn tag | Tag repo, manifest, checksum, config snapshot |
| 8 | Chạy TN1 ladder và TN2 ablation | Theo cấu hình §4.1 |
| 9 | Expert validation mẫu nhỏ | Rubric, phiếu chấm, thống kê mô tả, nhận xét chuyên gia |
| 10 | Viết bản Q2 hoàn chỉnh | Manuscript tiếng Anh, response-ready, đủ limitations và reproducibility |

## 6. Manuscript phải sửa

Luật claim đầy đủ nằm ở `docs/paper/claim-rules.md`. Phần dưới là yêu cầu theo từng mục.

- **Abstract.** Viết lại theo phương án 2, không mở bằng controlled refinement. Bốn ý: rào cản
  dùng LLM thương mại trong ISD; SLM on-premise khả thi nhưng cần harness; AlignmentGraph-ISD tạo
  explicit alignment state và audit trail; kết quả chính là robustness, ADDIE quality, alignment
  signals và cost trade-off.
- **Introduction.** Bớt tham vọng. Gap trung tâm: chưa có đánh giá hệ thống nào cho thấy một agent
  harness duy trì được chất lượng ISD end-to-end khi model nhỏ đi, và chưa có cách đo tín hiệu
  alignment không phụ thuộc hoàn toàn vào LLM judge. Không biến MAS thành giả định đúng; MAS chỉ
  là giải pháp đề xuất.
- **Method.** Mô tả đúng hệ sau pivot: vòng act–observe, hai `agent_mode`, substrate graph/prose,
  relation registry 16 cạnh, developer tier, deterministic repair, reconciliation, aggregate.
  Phân định rõ cái gì model-dependent và cái gì deterministic harness.
- **Experimental setup.** Khóa trước khi chạy: dataset splits, seed, prompt, model checkpoint,
  serving envelope, output cap, trajectory cap, failure policy, judge models, alignment panel,
  sensitivity arms và quy tắc đọc panel. Không chỉnh sau khi xem kết quả.
- **Results.** Chỉ viết từ TN1/TN2 chính thức. Số sprint vào phụ lục kỹ thuật hoặc Engineering Log
  của luận văn. Nếu cần nhắc quá trình phát triển thì viết định tính: *"The harness was stabilized
  before the official evaluation."*
- **Discussion và Limitations.** Trung thực với mặt bất lợi: cost cao, Trajectory bị phạt, một họ
  model Qwen, benchmark tự động, panel chưa validate construct, chưa có classroom study.

### Công thức phải viết an toàn

Dùng dạng text hoặc ảnh/vector đã kiểm render, không dùng equation field phức tạp chưa kiểm bằng
PDF. Giải thích biến ngay dưới mỗi công thức.

```
Total       = 0.7 x ADDIE + 0.3 x Trajectory
sim(S,T)    = (1 / |S|) x sum_{u in S} max_{t in T} max(0, cos(e_u, e_t))
Porter(X,Y) = 1 - 0.5 x sum_i |X_i - Y_i|
coverage(R) = count(items with at least one required edge R) / count(all required items)
DiD         = [score(A0,largest) - score(B,largest)] - [score(A0,smallest) - score(B,smallest)]
```

`max(0, cos)` là rectified cosine để đưa thang về [0, 1], **không phải ngưỡng matching**.

## 7. Checklist bắt buộc trước khi chạy chính thức

Gộp phụ lục của `Nhan_xet` và §5 của `Lo_trinh`.

- [ ] Đã chạy đủ 4 arm sau bản vá C5 và có bảng parity.
- [ ] Đã truy xong stage assessment và cắt nguyên nhân cost lớn nhất.
- [ ] Đã đo tỷ lệ prompt/completion token và áp dụng adaptive batching nếu cần.
- [ ] Đã đo lại `STAGE_MAX_TURNS` trên `train_30`, không chọn bằng cảm tính.
- [ ] Đã chốt trajectory cap (20-only, 120-only, hoặc báo cả hai) **trước** `test_90`, và không
      đổi sau code freeze.
- [ ] Stage assessment không còn failure bất thường do bug.
- [ ] 4 ablation arm đều qua canary/tune.
- [ ] `train_30`, `test_30`, `test_90` đã kiểm disjoint; `test_30` stratified seed 42.
- [ ] Code hash, prompt hash, metric version, model checkpoint, seed, judge và failure policy đã
      khóa và ghi manifest.
- [ ] Cache và resume đã kiểm thử bằng cách dừng rồi chạy tiếp.
- [ ] Estimate chi phí theo tune 10 scenario đã được chấp nhận.
- [ ] Manuscript đã đồng bộ 2×2 factorial, 16 relation, 6 tín hiệu panel; không còn mô tả thiết
      kế cũ.
- [ ] Đã gắn tag code freeze, lưu manifest và checksum.
- [ ] Đã chuẩn bị rubric expert validation.

## 8. Trạng thái áp dụng trong repo

| Yêu cầu | Nơi đã ghi nhận |
|---|---|
| Luật claim, câu thay thế, mục bắt buộc khai | `docs/paper/claim-rules.md` |
| Panel 6 tín hiệu, sensitivity star, no primary endpoint | `docs/guides/alignment_protocol.md`, `experiments/.../alignment/protocol.py` |
| 1 run/ô, SD across scenarios, failure=0 là layer chính | `CLAUDE.md`, `isd-exp comparison pool`, `isd-exp report tables` |
| RQ1 báo 3 tín hiệu song song, ADDIE dẫn narrative | `RQ1_SIGNALS` trong `isd-exp comparison pool` |
| TN2 là thí nghiệm riêng trên `test_30`, A0 chạy lại trong TN2 | `CLAUDE.md`, `experiments/ (ablation stage)` |
| Lệnh tạo `test_30` disjoint seed 42 | `CLAUDE.md` mục Common commands, `isd-exp data split` |
| Quy trình chạy, audit, pooling, sinh bảng | `docs/guides/benchmark_guides.md` |

Các mục còn thiếu, kiểm tại 2026-09-16:

- **Trajectory hai lớp chưa triển khai.** `evaluator/.../metrics/trajectory.py:258` vẫn cắt cứng
  `tool_calls[:20]`, chưa có lớp diagnostic cap 120 và chưa có cơ chế chấm lại trajectory offline.
  Đây là việc phải chốt trước `test_90`.
- **Cache/resume theo hash chưa đủ.** `isd-exp score` có resume ở mức chấm và
  `02_run_ladder.sh` cho chạy tiếp ladder dở, nhưng chưa có khóa hash theo
  scenario/agent/size cho generation, và chưa có cache judge score theo output hash.
- **Manifest code freeze chưa có.** Chỉ tồn tại `results/archived/ladder_20260726_142541/comparison_manifest.json`
  của ladder cũ.
- **Expert validation chưa có gì.** Chưa có rubric, phiếu chấm, hay thư mục package.
- **Preflight** mới có `isd-exp audit preflight`; cần đối chiếu xem đã phủ đủ quota, disk, resume và
  estimate cost như giai đoạn 3 yêu cầu chưa.
