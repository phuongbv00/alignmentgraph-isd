# AlignmentGraph-ISD

## Bối cảnh

Các mô hình ngôn ngữ lớn thương mại có thể tạo ra chương trình giảng dạy chất lượng cao và ngày càng được ứng dụng trong
dạy học, sinh học liệu và thiết kế hệ thống giảng dạy (Instructional Systems Design — ISD). Tuy nhiên, chi phí suy luận,
sự phụ thuộc vào API và việc phải chuyển dữ liệu người học hoặc học liệu nội bộ qua dịch vụ bên thứ ba gây trở ngại cho
việc triển khai rộng rãi tại các cơ sở giáo dục.

Các mô hình ngôn ngữ nhỏ có trọng số mở (open-weight SLM) có thể được triển khai tại chỗ, nhờ đó đem lại sự cân bằng
thực tế hơn giữa chất lượng, chi phí và quyền kiểm soát dữ liệu. Khi mô hình nền nhỏ đi, khả năng duy trì chất lượng của
toàn hệ thống phụ thuộc nhiều hơn vào harness — bộ khung chịu trách nhiệm quản lý trạng thái, điều phối quy trình và
kiểm soát chất lượng.

## Khoảng trống nghiên cứu

Các nghiên cứu về ISD và sinh lesson plan chủ yếu tập trung vào tự động hoá quy trình, giảm khối lượng công việc, cá
nhân hoá hoặc nâng cao chất lượng đầu ra trên các mô hình mạnh. Một số công trình đã sử dụng mô hình nhỏ để hỗ trợ giáo
viên hoặc tinh chỉnh mô hình 7B cho sinh lesson plan, nhưng việc duy trì chất lượng khi thu nhỏ mô hình nền vẫn chưa
được nghiên cứu rõ như một mục tiêu thiết kế và đánh giá của hệ tác tử ISD.

Ngoài ra, các benchmark hiện có (kể cả ISD-Agent-Bench) đánh giá chất lượng đầu ra chủ yếu bằng rubric do LLM judge
chấm; **constructive alignment — điều kiện được dùng để định nghĩa thành công của một thiết kế giảng dạy — chưa được đo
trực tiếp bằng một thước đo định lượng, tự động và độc lập với hệ được đánh giá**.

Trên cơ sở khoảng trống này, nghiên cứu hướng tới hai mục tiêu:

1. Đánh giá mức độ duy trì chất lượng của harness ISD đề xuất khi thu nhỏ mô hình nền, trong tương quan với các tác tử
   ISD tiêu biểu, trên một dải kích thước mô hình cùng họ.
2. Đo trực tiếp constructive alignment của đầu ra bằng một alignment metric định lượng, và xem xét khoảng cách alignment
   giữa harness và các đối sánh thay đổi thế nào theo kích thước mô hình.

Các công trình lân cận gồm Small Models Big Support, tập trung vào hỗ trợ biên soạn nội dung bằng SLM cục bộ;
LessonPlanLM, tinh chỉnh mô hình 7B cho sinh lesson plan; và Instructional Agents, báo cáo chi phí sử dụng nhưng vẫn dựa
trên API thương mại. Phạm vi liên quan được tổng hợp trong `docs/paper/refs-deployment-survey.md`.

## Giả thuyết thiết kế

Xuất phát điểm của thiết kế là ràng buộc kỹ thuật của bài toán: để triển khai tại chỗ, mô hình nền phải là SLM, mà SLM
lại yếu đi rõ rệt khi phải xử lý một tác vụ mở, đồng thời chịu nhiều ràng buộc — điều mà việc sinh trọn một chương trình
ISD trong một lượt đòi hỏi. Một hướng đối phó là fine-tune SLM cho tác vụ, nhưng cách này gắn với từng mô hình và từng
miền dữ liệu. Nghiên cứu này chọn hướng ở cấp harness: giữ mô hình nền nguyên trạng và **thu hẹp tác vụ mà mỗi lời gọi
mô hình phải gánh**. Một tác vụ hẹp, được định phạm vi rõ, nằm trong tầm với của mô hình yếu hơn so với một tác vụ rộng,
đa mục tiêu. Đây là lý do phân rã theo mối quan tâm ISD — mỗi tác tử chuyên biệt chỉ lo một phần — thay vì một tác tử
đơn với prompt phức tạp hơn.

Phân rã lại làm nảy sinh một vấn đề mới: khi mỗi mảnh được sinh riêng, chúng phải **nhất quán với nhau**. Trong ISD,
chất lượng không nằm ở từng đầu ra riêng lẻ mà ở sự ăn khớp giữa mục tiêu học tập, hoạt động, học liệu, đánh giá và
lượng giá. Vì vậy các tác tử cần một substrate chung để phối hợp — và thứ cần được phối hợp, cụ thể trong ISD, chính là
**sự ăn khớp về sư phạm**. Constructive alignment cung cấp cơ sở lý thuyết để xác định đúng các quan hệ phải duy trì
giữa mục tiêu, hoạt động và đánh giá, qua đó định hình *lược đồ* của substrate này — các kiểu node và edge nào là hợp
lệ, và verifier phải kiểm những quan hệ nào.

Trên cơ sở đó, AlignmentGraph-ISD hiện thực hoá substrate điều phối dưới dạng alignment graph: một trạng thái thiết kế
tường minh, dùng chung, để các tác tử sinh nội dung khớp với nhau và để cơ chế kiểm chứng có thể kiểm được. Giả thuyết
là một harness tổ chức quá trình sinh xoay quanh trạng thái này sẽ giảm được sự phụ thuộc vào khả năng tự duy trì nhất
quán của bản thân mô hình — khả năng vốn suy giảm khi thu nhỏ mô hình nền.

Trạng thái tường minh này còn có giá trị thứ hai, độc lập với chất lượng sinh: **explainability/auditability cho con
người**. Vì mọi quan hệ alignment đều là node/edge cụ thể thay vì ẩn trong văn xuôi, toàn bộ đồ thị được dump ra file
riêng (JSON đầy đủ node/edge/state, kèm bản xuất Graphviz DOT để visualize) — educator có thể kiểm tra từng mục tiêu
được đo bởi đánh giá nào, được hỗ trợ bởi hoạt động nào, và can thiệp/override khi cần (educator-in-the-loop). Đây là
điều các hệ sinh một lượt bằng prompt không cung cấp được.

## AlignmentGraph-ISD

Alignment graph là cấu trúc dữ liệu trung tâm của harness — substrate mà quá trình phân rã và điều phối vận hành trên
đó. Đồ thị gồm các node có kiểu `objective`, `activity`, `material`, `assessment`, `implementation` và `evaluation`;
cùng các edge có kiểu `measures`, `supports` và `evaluates`, phản ánh các quan hệ ăn khớp mà constructive alignment đòi
hỏi.

Các tác tử chuyên biệt xây dựng đồ thị theo một quy trình ISD cố định và chỉ được cập nhật phần trạng thái thuộc phạm vi
trách nhiệm của mình. Chính cách phân rã có ràng buộc này — chứ không phải bản thân cấu trúc đồ thị — là thứ tạo ra các
liên kết bắt buộc ngay trong quá trình sinh. Sau mỗi lượt cập nhật, cơ chế kiểm chứng và sửa lỗi kiểm tra tính phù hợp
về sư phạm và nhận thức, sau đó sửa các vi phạm được phát hiện.

Cuối mỗi lần chạy, harness xuất bản dump đầy đủ của alignment graph thành artifact riêng (tách khỏi trajectory), sẵn
sàng cho việc audit và visualize — hiện thực hoá trực tiếp luận điểm "explicit and auditable" thay cho tuyên bố "aligned
by construction".

## Đóng góp

1. **AlignmentGraph-ISD** — harness đa tác tử với alignment graph là trạng thái alignment tường minh, kiểm được và audit
   được, cho bài toán sinh chương trình ADDIE.
2. **Alignment metric / benchmark extension** — mở rộng ISD-Agent-Bench với một thước đo constructive alignment định
   lượng, tự động, không dùng LLM judgment ở bước tổng hợp (Porter Alignment Index + Webb criteria + embedding
   coverage). Metric độc lập ở **cơ chế chấm** — chỉ đọc text đầu ra, không gọi LLM, không dùng nhãn/ID tự khai của hệ
   được đo — tránh vòng tròn LLM-judge và vòng tròn self-declared labels. Nó **không** độc lập về construct với harness
   đề xuất (harness được thiết kế để tối ưu chính constructive alignment mà metric đo — đây là chủ đích, và thành phần
   Webb range đạt trần by-construction đóng vai trò manipulation check); vì vậy thứ hạng theo metric được corroborate
   bằng instrument độc lập là LLM-judge rubric (RQ1).
3. **Bằng chứng thực nghiệm về model scale** — đánh giá có kiểm soát trên dải Qwen cùng họ (0.8B → 2B → 4B → 9B), mỗi mô
   hình 3 run, cho cả chất lượng (judge) lẫn alignment (metric mới).

## Câu hỏi nghiên cứu

- **RQ1 — Duy trì chất lượng theo model scale:** Chất lượng đầu ra của AlignmentGraph-ISD thay đổi thế nào khi thu nhỏ
  mô hình nền trên dải Qwen 0.8B–9B, so với các hệ tác tử đối sánh?
- **RQ2 — Alignment đo trực tiếp:** Đầu ra của AlignmentGraph-ISD có mức constructive alignment (đo bằng alignment
  metric) cao hơn các đối sánh hay không, và khoảng cách này có nới rộng khi mô hình nhỏ đi hay không?

## Thiết lập thực nghiệm

Thực nghiệm sử dụng 90 tình huống trong tập `test_90` của ISD-Agent-Bench và sáu tác tử đối sánh. Mỗi hệ thống chạy trên
bốn kích thước Qwen cùng họ (0.8B, 2B, 4B, 9B), **mỗi mô hình 3 run độc lập** để lượng hoá run-to-run variability; chất
lượng được chấm bởi hai judge và lấy trung vị/trung bình theo quy ước của benchmark.

RQ1 phân tích bằng Wilcoxon signed-rank ghép cặp theo tình huống (trên mean-of-3-runs; **exact permutation null khi
n≤25**, normal approximation chỉ ở n lớn), hiệu chỉnh Holm (family định nghĩa tường minh = 6 so sánh/size), bootstrap
95% CI. **Primary analysis** = 6 so sánh complete-case trên Total tại mỗi size; failure-rate (Fisher exact scenario-
level), sensitivity imputation (failure=0 / failure=min), interaction `method × model size` (bootstrap
difference-in-differences) và stats trên alignment composite là **secondary/exploratory**. Ô có complete-case n≤5 được
khai báo là không kiểm định được bằng score test (exact p sàn 0.25 tại n=3); bằng chứng tại các ô đó là failure-rate +
sensitivity. RQ2 chấm alignment metric offline trên đầu ra đã lưu của mọi agent — không cần chạy lại agent, không có
lời gọi LLM trong metric; báo cáo cả composite unconditional lẫn conditional-on-parseable-output.

Một **ablation study** đo mức đóng góp của từng thành phần harness: ba arm
(−Verifier tắt vòng QC verify+repair; −GraphContext tắt việc bơm graph-context vào prompt; skeleton tắt cả hai) chạy
cùng A0 (full pipeline) như bốn agent trong **một run duy nhất mỗi size** trên cả 4 kích thước Qwen — mọi arm được chấm
trong cùng judge session nên delta arm−A0 (paired per-scenario, Wilcoxon + Holm theo 3 arm/size, bootstrap CI) không
nhiễm judge drift; A0 in-session được đối chiếu với 3 run ladder làm consistency check. Ablation không đổi RQ1/RQ2 —
nó là luận cứ defense cho thiết kế harness (contribution 1).

Số liệu trong paper được sinh tự động từ artifact (script pool + generator LaTeX), không gõ tay; kết quả các run trước
pivot không được sử dụng.

## Kết quả chính

*(Số cụ thể trích từ `docs/results_20260723.md` / artifacts sinh tự động từ `pooled_ladder.json`; thứ tự dưới đây là
thứ tự dẫn dắt của narrative — mạnh nhất trước.)*

1. **Robustness theo scale:** hệ đề xuất sinh output dùng được cho 100% scenario ở cả 4 size × 3 run; baseline
   single-prompt và eduplanner hỏng phần lớn scenario ở 0.8B (87–88/90) và một phần ở 2B (Fisher exact p_holm ≤ 2e-10).
   Một phần failure có thể do truncation dưới trần token dùng chung — vẫn là failure ở cấp hệ thống.
2. **Chất lượng (judge):** thắng có ý nghĩa các structured agent cùng lớp (addie, rpisd) ở cả 4 size; dẫn đầu **ADDIE ở
   cả 4 size**. Trung thực hai chiều: hòa react-isd về Total ở 4B–9B (workflow 2-call, ~1/3 token) và thua nhẹ
   dick-carey ở 0.8B về Total (−1.59, có ý nghĩa) — tại đó harness vẫn dẫn ADDIE và vượt xa về alignment.
3. **Bù scale (dạng defensible):** lợi thế Total vs react-isd co lại có ý nghĩa khi model lớn lên (DiD −2.17,
   p=1.3e-4); failure differential tập trung ở model nhỏ; delta vs baseline/eduplanner ở 0.8B chỉ kiểm định được dưới
   sensitivity imputation (+36→+60, p_holm ≤ 1.3e-15) — không claim từ DiD n≤3.
4. **Alignment (metric mới):** dẫn đầu cả 4 size, giữ nguyên khi conditional-on-parseable; mọi so sánh p_holm ≤ 4.8e-13,
   r_rb ≥ 0.92; gap vs á quân nới rộng khi model nhỏ đi (0.079 ở 9B → 0.239 ở 0.8B) — trả lời cả hai vế RQ2, kèm giới
   hạn construct proximity đã khai báo ở Đóng góp 2.
5. **Ablation (2026-07-24, §5 results doc):** gỡ graph-context làm alignment composite rớt có ý nghĩa ở cả 4 size
   (−0.044…−0.107, p_holm ≤ 3e-7), hiệu ứng lớn nhất ở model nhỏ — graph-context là component chịu tải cho alignment và
   khớp câu chuyện bù scale. Verifier đứng riêng không đo được đóng góp (ns) nhưng skeleton rớt sâu hơn −GraphCtx ở mọi
   size (thêm −0.03…−0.06) → verifier là backstop tương tác + nguồn audit trail. Judge Total gần như bất biến giữa các
   arm (không khác biệt có ý nghĩa nào quá 0.7/100) trong khi composite dịch 6–15% → LLM-judge không đo được alignment,
   củng cố lý do tồn tại của RQ2 metric. 0 output failure ở mọi arm → robustness đến từ decomposition + schema + regen
   (giữ ở mọi arm).

## Ý nghĩa và phạm vi kết luận

Nếu giả thuyết được xác nhận, kết quả cho thấy các cơ chế ở cấp harness giúp chất lượng và alignment của hệ ISD ổn định
hơn khi mô hình nền được thu nhỏ, đồng thời cung cấp một thước đo alignment tái sử dụng được cho các benchmark ISD. Kết
luận về cơ chế được giới hạn cẩn trọng ở hai mức: claim hệ thống (so với baseline) từ ladder, và claim cơ chế từ
ablation study — ablation tách được đóng góp của graph-context (có ý nghĩa, mọi size) và vai trò backstop của verifier
trên trục alignment, nhưng không tách phân rã tác vụ đa-agent (không có arm single-agent — decomposition là nền của mọi
arm), nên claim về decomposition vẫn ở mức hệ thống.

Hệ thống được định vị là decision support cho chuyên gia ISD với educator-in-the-loop, không thay thế chuyên gia; graph
dump là cơ chế audit và override cụ thể phục vụ định vị này. Các kết quả tạo cơ sở cho hướng triển khai hệ ISD bằng
open-weight SLM với chi phí thấp hơn và quyền kiểm soát dữ liệu tốt hơn tại các cơ sở giáo dục.
