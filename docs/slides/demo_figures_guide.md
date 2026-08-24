# Hướng dẫn diễn giải figure/table khi demo paper VN với thầy

Nguồn: `docs/paper/acm/vn/sections/06_results.tex` + artifact sinh tự động trong `docs/generated/`.
Mọi số dưới đây lấy đúng từ artifact, không gõ tay.

> Không rành thống kê thì đọc **Phụ lục B** ở cuối file trước: giải thích SD, CI, p, Holm,
> Wilcoxon, Fisher, DiD, bootstrap, ρ, κ bằng lời thường, kèm câu nói sẵn cho từng cái.
> **Phụ lục A** là bản đồ trang của bản VN.

**Setup nói một lần ở đầu (30 giây):** 7 agent (6 baseline + hệ đề xuất), 4 kích thước
Qwen3.5 (0.8B / 2B / 4B / 9B), 3 run độc lập mỗi kích thước, 90 scenario mỗi run.
Có 3 nhóm bằng chứng: judge chấm chất lượng (RQ1), panel 7 tín hiệu alignment đo tự động
không dùng LLM (RQ2), và ablation để chỉ ra cơ chế nào tạo ra hiệu ứng.

---

## Mạch demo 5 phút (thứ tự nên đi)

1. Fig. độ vững → 2. Bảng RQ1 → 3. Fig. 3 tín hiệu judge → 4. Bảng + heatmap RQ2 →
5. Forest plot → 6. Ablation → 7. Chi phí. Sensitivity chỉ nói một câu nếu thầy hỏi.

---

## 1. `fig:failure-rate` — Tỷ lệ scenario không có output chấm được

- **Đọc:** cột dọc = % scenario không sinh được output dùng được; nhóm theo kích thước
  model; whisker = min–max giữa 3 run.
- **Nói:** "Ở 0.8B, Baseline hỏng 61,9% và EduPlanner 58,1% số scenario. Hệ đề xuất và
  các agent có scaffold đạt 0% ở mọi kích thước. Nguyên nhân chính của Baseline là
  truncation: 100% artifact thiếu dừng đúng tại 8192 token."
- **Vì sao đặt đầu tiên:** mọi so sánh điểm đều có điều kiện trên việc agent có output.
  Nếu không nói trước, các delta khổng lồ ở 0.8B trong bảng RQ1 sẽ bị đọc sai.
- **Thầy có thể hỏi "sao không tăng token limit?"** → giới hạn 8192 áp dụng đồng đều cho
  mọi agent (fairness) và mô phỏng call budget của deployment; kết quả này là phát biểu
  về deployability, không phải về khả năng tối đa của model.

## 2. `tab:rq1-ladder` — Bảng RQ1 (ADDIE theo kích thước)

- **Một ô là gì:** điểm ADDIE trung bình mỗi scenario (thang /100), lấy mean-of-runs
  ± SD giữa 3 run; cột `n` = số scenario chấm đủ cả 3 run. **Bold = max cột, không phải
  claim ý nghĩa thống kê.**
- **Nói:** "Hệ đề xuất dẫn ở ba kích thước nhỏ (80,46 / 84,69 / 85,88) và ngang ReAct-ISD
  tại 9B (86,23 so với 86,30). SD giữa các run rất nhỏ, cỡ 0,04–0,19, nên thứ hạng ổn định."
- **Bẫy phải tự nêu trước:** các ô có dấu `*` là complete-case trên số scenario nhỏ
  (Baseline @0.8B chỉ `n=5`). Khoảng cách 80,46 so với 44,52 **không đọc được như chênh
  lệch chất lượng** — nó là hệ quả của failure rate. Layer chính của phân tích là
  `failure=0`, complete-case chỉ dùng làm sensitivity.
- **Nếu thầy hỏi "chênh lệch có ý nghĩa không?":** tại 0.8B delta so với baseline mạnh
  nhất là +0,72, CI 95% [−0,11; 1,54], p_Holm tối đa 0,125 → **không có ý nghĩa**. Tại
  2B và 4B có ý nghĩa. Tại 9B delta −0,08, CI [−0,37; 0,21] → **kết luận parity, không
  phải superiority**. Nói thẳng chỗ này sẽ ăn điểm.

## 3. `fig:rq1-components` — Ba tín hiệu judge song song

- **Đọc:** 3 panel, trục x = kích thước model, trục y = điểm; đường xanh đậm có kim
  cương là hệ đề xuất.
- **Nói:** "Ba tín hiệu có vị thế ngang nhau, không có endpoint chính. ADDIE dẫn mạch
  trình bày vì rubric của nó khớp đúng construct mà RQ1 hỏi, tức chất lượng nội dung
  thiết kế."
- **Panel trái (ADDIE):** hệ đề xuất dẫn ở đầu nhỏ, hội tụ với ReAct-ISD tại 9B.
- **Panel giữa (Trajectory):** hệ đề xuất **thấp hơn** ReAct-ISD và ADDIE-Agent ở mọi
  kích thước. Giải thích thẳng: kiến trúc đa tác tử có vòng verify–repair tạo trace dài
  và kém gọn hơn thiết kế một vòng lặp. Đây là đo tuân thủ quy trình tool-use, một
  construct khác với chất lượng artifact.
- **Panel phải (Total = 0,7·ADDIE + 0,3·Traj):** composite kế thừa phần phạt quy trình.
  Tại 0.8B hệ đề xuất được 81,48 so với 82,79 của Dick-Carey-Agent, **dù dẫn ADDIE và
  dẫn toàn bộ panel RQ2**. Nói ra chỗ thua này chủ động, đừng để thầy phát hiện.
- **Câu chốt scale:** DiD ADDIE giữa 9B và 0.8B so với ReAct-ISD là −3,06
  (CI [−3,82; −2,26], p ≈ 5,6·10⁻¹⁰) → lợi thế của harness **co lại khi model lớn lên**.
  Đây là câu trả lời cho RQ1.

## 4. `tab:rq2-panel` — Bảng panel 7 tín hiệu

- **Một ô là gì:** giá trị trung bình mỗi scenario của một tín hiệu, thang 0–1, pooled
  mean-of-runs. Hàng = tín hiệu × kích thước, cột = agent.
- **Cấu trúc phải nói:** 2 họ công cụ đo **độc lập về cơ chế**. Family A (textual
  correspondence) dùng rectified cosine `max(0, cos)` trên embedding — **không có ngưỡng
  similarity ở bất kỳ đâu**. Family B (cognitive demand) dùng Bloom: congruence, Porter,
  Webb — **không dùng similarity**. Hai họ đồng thuận thì bằng chứng mạnh hơn nhiều so
  với một chỉ số gộp.
- **Nói:** "Hệ đề xuất cao nhất ở gần như mọi ô. Rõ nhất là Obj→Asm: 0,85 so với 0,50
  của ReAct-ISD tại 0.8B, và 0,83 so với 0,57 tại 9B."
- **Quy tắc đọc panel (pre-specified, nói nguyên văn):** có lợi thế tại một kích thước
  khi ít nhất 4 trong 6 tín hiệu có hướng dương có ý nghĩa sau Holm trong-tín-hiệu, và
  không tín hiệu nào âm có ý nghĩa. Điều kiện này đạt ở **cả 4 kích thước**.
- **Tín hiệu thứ 7 (Asm→Obj, dấu †):** không định hướng, chỉ mang tính chẩn đoán, không
  tham gia phép đếm. Giá trị cao có thể nghĩa là "không có assessment item mồ côi",
  cũng có thể nghĩa là "item chỉ chép lại objective".
- **Nếu thầy hỏi "sao không gộp thành một điểm alignment?"** → gọi một tín hiệu là
  "chính" chính là một composite ngầm với trọng số không ai biện minh được. Panel phẳng
  báo cả 7, kể cả tín hiệu bất lợi.

## 5. `fig:rq2-components` — Heatmap panel

- **Đọc:** 4 lưới (một lưới/kích thước), hàng = agent, cột = 7 tín hiệu, vạch trắng dọc
  tách Family A và Family B. Càng đậm càng cao. **Chữ đỏ `n=` = ô survivor**, tính trên
  chưa tới một nửa số scenario, không so sánh được với ô có coverage đầy đủ.
- **Nói:** "Hàng cuối cùng đậm nhất và đậm đều ở cả hai họ. Đây là hình ảnh trực quan
  của bảng trên."
- **Điểm trung thực nên tự nêu:** Webb tại 0.8B, Dick-Carey-Agent đạt 0,85 còn hệ đề
  xuất 0,68 — đây là ngoại lệ bất lợi, và vì thế panel phải đọc theo từng tín hiệu.

## 6. `fig:rq2-forest` — Forest plot Δ so với ReAct-ISD

- **Đọc:** mỗi hàng một tín hiệu, điểm = delta ghép cặp theo scenario (hệ đề xuất trừ
  ReAct-ISD), thanh ngang = CI bootstrap 95%; **marker đặc = p_Holm trong-tín-hiệu < 0,05**.
  Vạch dọc 0 là mốc không khác biệt.
- **Nói:** "Toàn bộ điểm nằm bên phải mốc 0 ở cả 4 kích thước, tất cả đều đặc. So với
  đối sánh mạnh nhất, mọi tín hiệu đều dương có ý nghĩa."
- **Chi tiết đắt giá:** khoảng cách trên Obj→Asm **nới rộng về phía model nhỏ**;
  DiD = −0,086 (CI [−0,112; −0,061], p ≈ 4,8·10⁻⁸). Tức là graph context có giá trị nhất
  khi model yếu — đúng luận điểm của luận văn.

## 7. `tab:ablation` + `fig:ablation-components` — Bằng chứng cơ chế

Đây là cặp quan trọng nhất khi thầy hỏi "cái gì thực sự tạo ra kết quả".

- **Câu tóm tắt một dòng:** kết quả ablation **judge-invariant nhưng alignment-shifted**.
- **Bảng (ADDIE):** bỏ graph context hay bỏ verifier gần như không đổi điểm judge
  (|Δ| ≤ 1,24, phần lớn dưới 0,5; A2 tại 0.8B thậm chí +1,24). Mọi arm đều sinh output
  đầy đủ.
- **Heatmap (panel RQ2):** A1 (bỏ verifier) gần trùng A0. A2 và A3 (bỏ graph context)
  **tụt trên diện rộng**: Obj→Asm tại 0.8B đi 0,85 → 0,75 → 0,67.
- **Kết luận ba tầng, nói đúng phạm vi:**
  1. Tầng phân rã (mọi arm đều giữ, **chưa được ablate**): gắn với robustness và lợi thế
     ADDIE. Lợi thế ADDIE còn nguyên khi tắt graph context, nên ablation **không giải
     thích được khoảng cách RQ1**, và khi chưa có monolithic control thì chưa quy nhân
     quả được.
  2. Tầng graph context: có bằng chứng ủng hộ, nhưng **cho các tín hiệu alignment**, không
     phải cho điểm judge.
  3. Tầng verifier: không tạo cải thiện đo được trong cấu hình shipped; vai trò là repair
     backstop và nguồn bằng chứng audit.
- **Nếu thầy hỏi "vậy verifier vô dụng à?"** → trong cấu hình shipped thì không có score
  effect. Nhưng khi graph context bị tắt, simple effect của verifier trên Obj→Asm dương ở
  mọi kích thước, từ +0,051 (9B) tới +0,080 (0.8B). Đây là kết quả **phản thực**, không
  xác lập score effect trong hệ shipped.

## 8. `tab:rq2-sensitivity` — Bảng 10, trang 15

- **Cấu trúc:** 2 khối, mỗi khối một trục sweep. Khối trên = **trục encoder**, đọc trên
  tín hiệu Obj→Asm. Khối dưới = **trục Bloom classifier**, đọc trên Cognitive congruence.
  Hàng in đậm là cấu hình chính (E1 Nemotron-8B, B1 BERT-Bloom), các hàng còn lại lệch
  **đúng một trục** so với nó — đây là **star, không phải grid**.
- **Ba cột mỗi kích thước, đọc đúng thứ tự:**
  - `Mean` = giá trị trung bình của hệ đề xuất khi chấm lại bằng arm đó.
  - `ρ` = Spearman, mức giống nhau về **thứ hạng** giữa arm đó và cấu hình chính.
  - `h` = **thứ hạng của hệ đề xuất** trong arm đó.
- **Câu chốt, chỉ cần đọc cột `h`:** "Cột h toàn số 1. Hệ đứng đầu ở **12/12** ô trên trục
  encoder và **4/4** ô trên trục Bloom, kể cả với TF–IDF vốn không phải semantic embedding."
- **Điểm phải nói về cột `Mean`:** giá trị **đổi rất nhiều** giữa các arm — Granite cho
  0,975 còn TF–IDF chỉ 0,686 ở 4B. Đó là chuyện bình thường, vì mỗi encoder có thang riêng.
  Kết luận của paper là kết luận **so sánh**, nên chỉ cần thứ hạng ổn định. Nói trước ý này
  để thầy không tưởng là số bất nhất.
- **Điểm phải nói về cột `ρ`:** ρ không phải lúc nào cũng cao — thấp nhất là 0,607
  (bge-m3 @9B, TF–IDF @4B). Tức các arm **thực sự khác nhau**, không phải bản sao của nhau,
  và thứ hạng số 1 sống sót qua cả những arm bất đồng nhất. Đây mới là điều làm sensitivity
  có sức nặng.
- **Trục Bloom:** ρ chỉ 0,679–0,857, khớp với con số κ = 0,665 giữa hai arm. Hai công cụ đo
  Bloom khác hẳn nhau mà vẫn cho cùng kết luận.
- **Nếu thầy hỏi "vì sao chỉ có 2 arm ở khối Bloom mà 4 ở khối encoder?"** → mỗi trục có số
  lựa chọn khả dụng khác nhau; điều kiện của star là mỗi arm lệch đúng một trục, không phải
  mỗi trục có cùng số arm.

## 9. `fig:cost-quality` — Chất lượng so với chi phí

- **Đọc:** trục x = token trung bình mỗi scenario (thang log), trục y = ADDIE; mỗi màu
  một agent, **marker to dần theo kích thước model**; đường nối 4 kích thước của cùng
  agent. **Marker rỗng = hai toạ độ tính trên hai tập scenario khác nhau**, không phải
  thuộc tính của một tập chung.
- **Nói:** "Hệ đề xuất dùng 8 lời gọi và 24,3 nghìn token mỗi thiết kế tại 2B, tức
  1,1–1,7× median baseline và 2,7–4,0× ReAct-ISD."
- **Kết luận đánh đổi, nói thẳng:** có lợi ở hai kích thước nhỏ, xấu đi tại 4B, và
  **thua tại 9B**, nơi ReAct-ISD nằm ở góc trên-trái (parity hoặc tốt hơn với khoảng 1/3,6
  lượng token).
- **Chi phí thuộc về đâu:** telemetry quy 25,4–30,8% token overhead cho graph context và
  chỉ 0,6–2,5% cho verifier. Thành phần đắt nhất cũng chính là thành phần được ablation
  RQ2 ủng hộ.
- **Bẫy phải tự nêu:** cột token của Baseline và EduPlanner là **survivor statistics** —
  ca bị truncate không để lại artifact. Vì vậy chỉ so chi phí với các baseline có coverage
  đầy đủ. Wall-clock là throughput có xếp hàng (tối đa 150 thiết kế in-flight), **không
  phải request latency**.

---

## Các bảng ở phần Method/Methodology (nói nhanh nếu thầy lật tới)

| Bảng/Hình | Câu một dòng |
|---|---|
| `fig:architecture` | Sơ đồ harness: các specialist theo ADDIE, graph alignment ở giữa, verifier + aggregator ở cuối. |
| `tab:specialists` | Mỗi specialist phụ trách một mối quan tâm ISD; không có agent nào "làm tất cả". |
| `tab:graph-spec` | 13 quan hệ của alignment graph, dạng `RX-name`; graph dump chính là đóng góp về auditability. |
| `tab:verifier-checks` | Các kiểm tra ở mức nội dung mà verifier chạy, kèm hành vi repair. |
| `tab:judge-signals` | Ba tín hiệu RQ1 và construct từng tín hiệu đo; vai trò ngang nhau. |
| `tab:panel-signals` | Định nghĩa 7 tín hiệu panel, tách theo hai họ. |
| `tab:rq2-arms` | Cấu hình chính + 4 arm sensitivity; đây là **star, mỗi arm lệch đúng một trục**, không phải grid. |

---

## Ba câu chốt nếu chỉ còn 1 phút

1. Hệ đề xuất sinh output dùng được ở **100%** scenario tại mọi kích thước, trong khi
   agent ít scaffold nhất hỏng ~60% ở 0.8B.
2. Trên panel constructive alignment, hệ đề xuất dẫn ở **cả 4 kích thước** theo quy tắc
   đọc pre-specified, với hai họ công cụ đo độc lập cùng đồng thuận, và ablation chỉ đúng
   graph context là cơ chế.
3. Lợi thế **co lại khi model lớn lên** (DiD ADDIE −3,06): tại 9B kết quả là parity chứ
   không phải superiority, và đánh đổi chi phí lúc đó không còn có lợi.

---

# Phụ lục A — Bản đồ trang, bản VN (`docs/paper/acm/vn/main.pdf`)

| Trang | Nội dung |
|---|---|
| 3 | Bảng 1 `tab:specialists` |
| 4 | Bảng 2 `tab:graph-spec` |
| 5 | Hình 1 `fig:architecture`, Bảng 3 `tab:verifier-checks` |
| 7 | Bảng 4 `tab:panel-signals` |
| 9 | Bảng 5 `tab:judge-signals`, Bảng 6 `tab:rq2-arms` |
| **11** | **Hình 2 `fig:failure-rate`, Bảng 7 `tab:rq1-ladder`, Hình 3 `fig:rq1-components`** |
| **12** | **Bảng 8 `tab:rq2-panel`** |
| **13** | **Hình 4 `fig:rq2-components`, Hình 5 `fig:rq2-forest`** |
| **14** | **Bảng 9 `tab:ablation`, Hình 6 `fig:ablation-components`** |
| **15** | **Bảng 10 `tab:rq2-sensitivity`, Hình 7 `fig:cost-quality`** |

Cập nhật 2026-08-13: bảng sensitivity đã được thêm vào bản VN (Bảng 10). Bản VN vẫn lược so
với bản EN ở `tab_rq1_traj`, `tab_rq1_total`, `tab_rq2_alignment`, `tab_cost` — số của những
bảng đó nằm trong prose qua macro; nếu thầy đòi bảng thì mở artifact trong `docs/generated/`.

Số trang lấy từ `vn/main.aux` sau lần compile gần nhất. Thêm/bớt bảng là số trang đổi —
chạy lại `vn/compile.sh` rồi đối chiếu trước khi demo.

---

# Phụ lục B — Các chỉ số thống kê, giải thích bằng lời thường

Nguyên tắc chung khi bị hỏi: **đừng giải thích công thức**. Nói ba thứ — chỉ số đó trả lời
câu hỏi gì, số trong paper là bao nhiêu, và kết luận rút ra được là gì.

### SD giữa các run (cột `±` trong bảng RQ1)

- **Là gì:** chạy lại cùng một cấu hình 3 lần thì điểm lệch nhau bao nhiêu. Số nhỏ = kết
  quả lặp lại được, không phải ăn may một lần chạy.
- **Trong paper:** hệ đề xuất có SD 0,04–0,19 điểm; baseline hỏng nhiều thì SD tới 3,83.
- **Nói:** "Chạy lại ba lần điểm gần như không đổi, lệch dưới 0,2 điểm."
- **Quy tắc phải nhớ:** mean nào thì SD nấy. Mean ADDIE đi với SD của ADDIE, không được
  ghép với SD của Total.

### `n` — số scenario thực sự tính được

- **Là gì:** mẫu số. Không phải agent nào cũng sinh được output cho cả 90 scenario.
- **Hai cách đếm, tên khác nhau vì điều kiện khác nhau:**
  - Bảng RQ1: `n` = scenario chấm được ở **cả 3 run** (complete-case, chặt hơn).
  - Bảng RQ2: `n` = scenario chấm được ở **ít nhất 1 run** (lỏng hơn).
- **Nói khi có dấu `*`:** "Ô này chỉ tính trên số scenario mà agent đó sống sót, nên không
  so trực tiếp với ô có đủ 90 được."

### Hai layer: `failure=0` và complete-case

- **Vấn đề:** nếu chỉ chấm những scenario mà agent làm được, agent hay hỏng sẽ được điểm
  cao giả tạo, vì nó chỉ còn lại những ca dễ. Đây là **hiệu ứng chọn mẫu**.
- **Hai cách xử lý:**
  - `failure=0`: hỏng thì tính 0 điểm. Đây là **layer chính**, vì nó phạt cả việc không
    sinh được output.
  - complete-case: bỏ hẳn ca hỏng ra ngoài. Chỉ dùng làm **sensitivity**, không bao giờ
    được đọc như kết quả unconditional.
- **Nói:** "Layer chính tính hỏng là 0 điểm; bỏ ca hỏng ra chỉ là phép kiểm tra phụ."

### Delta ghép cặp (Δ, paired delta)

- **Là gì:** so trên **từng scenario một** rồi mới lấy trung bình chênh lệch, thay vì so
  hai điểm trung bình với nhau. Cách này khử được yếu tố "scenario này vốn khó".
- **Nói:** "So từng scenario với nhau nên độ khó của đề bài bị triệt tiêu."

### CI 95% (khoảng tin cậy) và bootstrap

- **Là gì:** dải giá trị mà chênh lệch thật nhiều khả năng nằm trong đó. **Bootstrap** chỉ
  là cách tính CI bằng cách lấy mẫu lại dữ liệu nhiều lần, không giả định phân phối chuẩn.
- **Cách đọc, chỉ cần nhớ một quy tắc:** CI **có chứa số 0** thì chưa kết luận được có
  khác biệt; CI **nằm trọn một phía của 0** thì khác biệt vững.
- **Ví dụ nói được ngay:**
  - 0.8B: Δ = +0,72, CI [−0,11; 1,54] → chứa 0 → "chưa đủ bằng chứng nói hơn".
  - 2B: CI [2,02; 2,99] → không chứa 0, toàn dương → "hơn thật, ít nhất khoảng 2 điểm".
  - 9B: Δ = −0,08, CI [−0,37; 0,21] → chứa 0 **và rất hẹp quanh 0** → "hai bên ngang nhau".
    Chỗ này là **parity**, và CI hẹp mới cho phép nói ngang, chứ không phải "chưa biết".

### p-value

- **Là gì:** xác suất thấy được chênh lệch lớn như quan sát nếu thực ra hai bên không khác
  nhau. p nhỏ = khó xảy ra do ngẫu nhiên.
- **Mốc dùng trong paper:** 0,05. `p = 5,6·10⁻¹⁰` nghĩa là 0,00000000056, tức rất nhỏ.
- **Nói:** "p rất nhỏ nên chênh lệch này khó là do may rủi giữa các lần chạy."
- **Không được nói:** "p nhỏ nên khác biệt lớn". p nói về độ chắc chắn, không nói về độ lớn.
  Độ lớn nằm ở Δ và CI.

### Hiệu chỉnh Holm và `p_Holm`

- **Vấn đề:** so một lúc nhiều cặp thì kiểu gì cũng có cặp trông "có ý nghĩa" do ngẫu
  nhiên. So 6 cặp ở mức 0,05 thì rủi ro báo động giả cao hơn hẳn 5%.
- **Holm làm gì:** siết ngưỡng lại theo số phép so sánh. `p_Holm` là p **đã bị siết**, nên
  luôn khắt khe hơn p thường. Vẫn dưới 0,05 thì kết luận mới được giữ.
- **Trong paper có hai tầng, phải phân biệt:**
  - `p_holm` **trong-tín-hiệu**: siết trên 6 so sánh với 6 agent, trong cùng một tín hiệu.
  - `p_holm_panel`: siết trên **toàn bộ** panel 7 tín hiệu × các baseline. Khắt khe hơn nữa.
- **Nói:** "Vì so nhiều cặp cùng lúc nên ngưỡng đã được siết theo Holm; kết luận là kết
  luận sau khi siết, không phải trước."
- **Ví dụ dùng được:** ở 0.8B, `p_Holm` tối đa 0,125 → **không** vượt được ngưỡng → paper
  nói thẳng là chênh lệch ADDIE ở 0.8B không có ý nghĩa.

### Wilcoxon signed-rank

- **Là gì:** phép kiểm cho dữ liệu ghép cặp, dựa trên thứ hạng thay vì giá trị trung bình.
- **Vì sao dùng:** điểm rubric không phân phối chuẩn và có ngoại lệ; phép này không giả
  định phân phối chuẩn nên an toàn hơn t-test.
- **Nói:** "Dùng phép kiểm phi tham số vì điểm rubric không phân phối chuẩn."

### Fisher exact test

- **Là gì:** phép kiểm cho dữ liệu **đếm/hỏng-không hỏng**, dùng cho biểu đồ failure rate.
- **Vì sao dùng:** ở đây biến là nhị phân (có output hay không), không phải điểm số.
- **Nói:** "Chênh lệch tỷ lệ hỏng được kiểm bằng Fisher, có hiệu chỉnh Holm."

### DiD — Difference-in-Differences (chênh lệch của chênh lệch)

Đây là chỉ số hay bị hỏi nhất, và là câu trả lời cho RQ1.

- **Câu hỏi nó trả lời:** khoảng cách giữa hệ đề xuất và đối thủ **giãn ra hay co lại** khi
  model to lên?
- **Cách tính bằng lời:** lấy (khoảng cách ở 9B) trừ (khoảng cách ở 0.8B).
  - Kết quả **âm** → khoảng cách co lại khi model to lên.
  - Kết quả **dương** → khoảng cách giãn ra.
- **Trong paper, RQ1:** DiD ADDIE so với ReAct-ISD = **−3,06**, CI [−3,82; −2,26],
  p ≈ 5,6·10⁻¹⁰. Đọc: ở 0.8B hệ đề xuất hơn khoảng 3 điểm, tới 9B thì gần như hết; khoảng
  cách thu hẹp khoảng 3 điểm, CI không chứa 0 nên xu hướng này chắc chắn.
- **Trong paper, RQ2:** DiD trên Obj→Asm = **−0,086**, CI [−0,112; −0,061]. Cùng ý: lợi thế
  alignment lớn nhất ở model nhỏ. Nhưng khác RQ1 ở chỗ **tại 9B vẫn còn dương có ý nghĩa**,
  chỉ là nhỏ đi.
- **Câu nói gọn:** "Lợi thế của harness lớn nhất khi model yếu và mờ dần khi model mạnh lên.
  Đây là kết luận, không phải điểm yếu — nó xác định đúng vùng mà scaffold còn giá trị."
- **Cẩn thận sign convention:** ở đây âm = co lại. Ở bảng ablation, Δ là "arm trừ A0" nên
  âm = bỏ thành phần đi làm điểm **giảm**. Hai chỗ khác nhau, đừng đọc nhầm.

### Simple effect (trong phần verifier của ablation)

- **Là gì:** hiệu ứng của một thành phần **trong một điều kiện cụ thể**, chứ không phải hiệu
  ứng trung bình.
- **Trong paper:** verifier không có tác dụng đo được khi graph context đang bật, nhưng khi
  graph context bị tắt thì bật verifier lại tăng Obj→Asm 0,051–0,080.
- **Phải nói kèm giới hạn:** "Đây là kết quả phản thực trong cấu hình không được ship, nên
  nó không xác lập hiệu ứng trong hệ thật."

### Spearman ρ (cột `ρ` của Bảng 10 sensitivity)

- **Là gì:** mức độ giống nhau về **thứ hạng**, từ −1 tới 1. Gần 1 = đổi công cụ đo thì
  thứ tự xếp hạng các agent gần như không đổi.
- **Vì sao quan trọng:** kết luận của paper là kết luận so sánh, nên chỉ cần thứ hạng ổn
  định, không cần giá trị tuyệt đối giống nhau.
- **Nói:** "Đổi encoder thì giá trị đổi, nhưng thứ hạng giữ nguyên, mà kết luận của tôi là
  kết luận về thứ hạng."

### κ (Cohen's kappa) — chỉ dùng khi hỏi về Bloom classifier

- **Là gì:** mức đồng thuận giữa hai bên gán nhãn, đã trừ đi phần trùng nhau do may rủi.
  0 = như đoán bừa, 1 = trùng khớp hoàn toàn. Trên 0,8 thường coi là rất tốt.
- **Trong paper:** checkpoint BERT đạt κ = 0,926 so với nhãn chuyên gia, còn lexicon 0,650.
  Đó là lý do BERT là cấu hình chính.
- **Cái giá phải thừa nhận:** BERT gán nhãn không truy vết được về Anderson & Krathwohl như
  lexicon, và không còn tất định ở mức bit. Vì vậy lexicon vẫn được giữ làm trục sensitivity.
- **Lưu ý:** hai arm chỉ đồng thuận với nhau ở κ = 0,665, nên chúng thực sự là hai công cụ
  khác nhau, không phải bản sao.

### Rectified cosine và mean-max (Family A) — đo, không phải thống kê

- **Cosine:** độ gần nhau về nghĩa của hai đoạn văn bản sau khi encode.
- **Rectified:** cắt phần âm về 0, tức `max(0, cos)`, để thang nằm gọn trên [0, 1]. **Đây là
  lựa chọn về thang đo, không phải ngưỡng khớp.** Nếu thầy hỏi ngưỡng: **giao thức này
  không có ngưỡng similarity ở bất kỳ đâu**.
- **Mean-max:** với mỗi objective, lấy phần tử khớp nhất ở phía bên kia, rồi lấy trung bình
  trên các objective.
- **Vì sao tên metric là "similarity" chứ không phải "alignment":** tên chỉ được phép nói
  đúng cái phép toán làm. "Alignment" là tên của giao thức, không phải tên của một con số.

### Porter index và Webb consistency (Family B)

- **Điểm chung:** cả hai so **cấp độ nhận thức Bloom** giữa objective và assessment, hoàn
  toàn không dùng similarity. Đây là lý do Family B là bằng chứng độc lập với Family A.
- **Porter (Porter 2002):** dựng ma trận phân bố **chủ đề × cấp độ Bloom** cho mỗi bên rồi
  đo phần chồng lấp của hai phân bố. Trả lời: hai bên có **trải đều giống nhau** không.
  Trong panel là trung bình của 3 cặp (objectives ↔ assessment / activities / evaluation).
- **Webb (Webb 1997/1999):** tính theo **từng item**, đo mức nhất quán về cấp độ giữa item
  và objective mà nó ứng với. Trả lời: **từng câu hỏi một** có đúng tầm nhận thức không.
- **Khác nhau chỗ nào:** Porter nhìn tổng thể phân bố, Webb nhìn từng item. Một đề có phân
  bố đúng nhưng từng câu lệch vẫn bị Webb phạt.
- **Nói:** "Hai họ đo bằng hai cơ chế không liên quan nhau. Chúng cùng chỉ một hướng thì
  bằng chứng mạnh hơn nhiều so với một chỉ số gộp."

### Ký hiệu trên hình cần đọc đúng

| Ký hiệu | Nghĩa |
|---|---|
| Marker **đặc** trên forest plot | `p_Holm` trong-tín-hiệu < 0,05 |
| Marker **rỗng** trên forest plot | chưa vượt ngưỡng sau Holm |
| Marker **rỗng** trên hình cost | hai toạ độ tính trên hai tập scenario khác nhau |
| Thanh ngang trên forest plot | CI bootstrap 95% |
| Whisker trên hình failure rate | min–max giữa 3 run, **không phải** CI |
| `†` | tín hiệu không định hướng, không tham gia phép đếm |
| `*` trong bảng | ô tính trên ít scenario hơn tổng số |
| Chữ **đỏ** `n=` trên heatmap | ô survivor, dưới một nửa số scenario |
| **Bold** trong bảng | max của cột, **không phải** claim ý nghĩa thống kê |

### Bốn câu trả lời thủ sẵn

- *"Sao không dùng t-test?"* → Điểm rubric không phân phối chuẩn và có ngoại lệ, nên dùng
  Wilcoxon ghép cặp cùng CI bootstrap; cả hai đều không giả định phân phối chuẩn.
- *"Chỉ 3 run thì đủ chưa?"* → SD giữa các run là 0,04–0,19 điểm, tức nhiễu giữa các lần
  chạy rất nhỏ so với khoảng cách giữa các agent. Sức mạnh thống kê đến từ 90 scenario ghép
  cặp, không phải từ số lần chạy.
- *"Có bị p-hacking không?"* → Quy tắc đọc panel được **pre-specified** trước khi chấm,
  không có endpoint chính nên không có chỗ chọn chỉ số có lợi, và mọi tín hiệu đều được báo
  kể cả tín hiệu bất lợi như Webb ở 0.8B.
- *"Kết quả có phụ thuộc công cụ đo không?"* → Đã kiểm bằng 4 arm sensitivity theo hình sao;
  hệ đứng đầu ở 12/12 ô trục encoder và 4/4 ô trục Bloom, kể cả với TF–IDF vốn không phải
  semantic embedding.
