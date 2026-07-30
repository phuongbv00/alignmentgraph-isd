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
2. Kiểm tra constructive alignment của đầu ra theo các tiêu chí đã được thiết lập, bằng một quy trình đánh giá định
   lượng tự động, và xem xét khoảng cách alignment giữa harness và các đối sánh thay đổi thế nào theo kích thước mô
   hình.

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
2. **Automated constructive-alignment evaluation protocol / benchmark extension** — mở rộng ISD-Agent-Bench với một quy
   trình đánh giá constructive alignment tự động, **không có lời gọi LLM ở bất kỳ khâu đo lường nào; điểm là hàm cố
   định của văn bản, không có thành phần ngẫu nhiên** (mức claim chính xác: xem mục 3 của section protocol).
   **Không claim metric mới**: quy trình operationalize các tiêu chí đã được thiết lập (khung Biggs–Tang, tiêu chí kiểu
   Quality Matters, chỉ số Porter/Webb, semantic correspondence). **Đo liên tục, không đặt ngưỡng cắt**, và báo cáo
   dưới dạng **panel 7 tín hiệu không thứ bậc** (§4 của section protocol) thuộc **hai họ instrument độc lập cơ chế**:
   họ textual correspondence (`objective_{assessment,activity,evaluation}_similarity` = mean-max rectified cosine cho
   3 vế của `aligned(o)`, cộng `assessment_objective_similarity` chiều ngược) và họ cognitive demand
   (`objective_cognitive_congruence`, Porter, Webb). Mỗi tín hiệu báo riêng với ý nghĩa riêng — không gộp thành scalar
   nào, và **không tín hiệu nào được gọi là "chính"**. Quy trình độc lập ở **cơ chế chấm** — chỉ đọc text đầu ra, không dùng nhãn/ID tự khai
   của hệ được đo để chấm (chỉ dùng làm validation evidence) — tránh vòng tròn LLM-judge và self-declared labels. Nó *
   *không** độc lập về
   construct với harness đề xuất (chủ đích thiết kế); thứ hạng được corroborate bằng instrument độc lập là LLM-judge
   rubric (RQ1). Mọi claim RQ2 ở mức **tương đối** (so với đối sánh, theo scale). Đặc tả đầy đủ: xem section
   **"Alignment evaluation protocol (RQ2) — đặc tả chốt"** bên dưới.
3. **Bằng chứng thực nghiệm về model scale** — đánh giá có kiểm soát trên dải Qwen cùng họ (0.8B → 2B → 4B → 9B), mỗi mô
   hình 3 run, cho cả chất lượng (judge) lẫn tín hiệu alignment (audit protocol).

## Câu hỏi nghiên cứu

- **RQ1 — Duy trì chất lượng theo model scale:** Chất lượng đầu ra của AlignmentGraph-ISD thay đổi thế nào khi thu nhỏ
  mô hình nền trên dải Qwen 0.8B–9B, so với các hệ tác tử đối sánh?
- **RQ2 — Tín hiệu alignment theo model scale:** Các *tín hiệu đo được* của constructive alignment — operationalize các
  tiêu chí đã được thiết lập thành chỉ số tự động, không dùng LLM — ở đầu ra của AlignmentGraph-ISD diễn biến thế nào so
  với
  các hệ đối sánh trên dải Qwen 0.8B–9B, và khoảng cách này có nới rộng khi mô hình nhỏ đi hay không?

  *Ghi chú mức claim:* phát biểu cố ý dừng ở "tín hiệu đo được", không phải "đo được alignment". Protocol chấm các dấu
  hiệu văn bản của alignment (tương đồng ngữ nghĩa mục tiêu↔bài kiểm tra/hoạt động/đánh giá chương trình, tầng nhận
  thức Bloom), không đo alignment như một construct đã được validate — việc đó cần expert study (xem mục 7 của section
  protocol).

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
sensitivity. RQ2 chấm alignment protocol offline trên đầu ra đã lưu của mọi agent — không cần chạy lại agent, không có
lời gọi LLM trong đo lường, **không ngưỡng**. Comparative = paired Wilcoxon **cho từng tín hiệu panel**, Holm riêng
mỗi tín hiệu (family = 6 so sánh/size) + Holm chung toàn panel báo ở footnote; vế scale = **DiD** (bootstrap,
largest−smallest); layer descriptive = mean + bootstrap CI per agent/size. **Failure policy song song RQ1**: layer chính là **complete-case trên output có sẵn** (agent crash
không ghi `*_output.json` nên rơi khỏi tập ghép cặp), kèm sensitivity **failure=0** dựng lại từ roster
`missing_outputs` — không có policy `failure=min` vì endpoint alignment đã sàn ở 0.0. Báo cả ba lát cắt:
complete-case, failure=0, và conditional-on-parseable-output (scenario có ≥1 objective). Sensitivity **3 trục** (§6 của
section protocol: encoder-independence, sàn từ vựng TF-IDF, Bloom classifier BERT↔lexicon) — mỗi họ instrument của
panel có ít nhất một trục.

Một **ablation study** đo mức đóng góp của từng thành phần harness: ba arm
(−Verifier tắt vòng QC verify+repair; −GraphContext tắt việc bơm graph-context vào prompt; skeleton tắt cả hai) chạy
cùng A0 (full pipeline) như bốn agent **bên trong chính các run của ladder** trên cả 4 kích thước Qwen — mọi arm được
chấm
trong cùng judge session nên delta arm−A0 (paired per-scenario, Wilcoxon + Holm theo 3 arm/size, bootstrap CI) không
nhiễm judge drift; A0 in-session được đối chiếu với 3 run ladder làm consistency check. Ablation không đổi RQ1/RQ2 —
nó là luận cứ defense cho thiết kế harness (contribution 1).

Số liệu trong paper được sinh tự động từ artifact (script pool + generator LaTeX), không gõ tay; kết quả các run trước
pivot không được sử dụng.

## Alignment evaluation protocol (RQ2) — đặc tả chốt

*(Section này là single source of truth cho protocol — paper VN/EN và thesis sẽ được update từ đây trong một task
riêng. Paper hiện tại CHƯA đồng bộ với đặc tả này.)*

### 1. Định vị & claim

Tên gọi: **automated constructive-alignment evaluation protocol operationalizing established criteria** (VN: quy trình
đánh giá constructive alignment tự động, operationalize các tiêu chí đã được thiết lập). **Không phải metric mới**;
không claim kế thừa validity của Porter/Webb/QM sang implementation — validity được bắc cầu bằng validation evidence
(mục 7). Chữ "proxy" chỉ dùng trong limitations như đặc tính phải khai, không dùng làm tên gọi. Mọi claim RQ2 ở mức
**tương đối** (comparative primary); mức tuyệt đối chỉ báo descriptive (mean + CI).

### 2. Nền lý thuyết

Khung Biggs–Tang (constructive alignment: ILO — hoạt động dạy học — đánh giá) làm nền; các tiêu chí review kiểu Quality
Matters rubric làm nguồn operationalize: (i) objective measurable; (ii) assessment đo đúng objective; (iii) activity
phục vụ objective; (iv) cognitive demand tương thích. Map thẳng vào predicate `aligned(o)` 3 vế
(measures/supports/evaluates) của problem formulation trong paper.

### 3. Pipeline (đúng runtime, không hứa quá)

1. **Extract text-only** từ ADDIE output (objectives, assessment items, activities, evaluation texts) — không đọc
   nhãn/ID tự khai để chấm (chỉ dùng làm validation evidence).
2. **Encoder — bộ ba độc lập lineage.** Primary là `nvidia/llama-embed-nemotron-8b` (NVIDIA, 11/2025;
   #1 MMTEB 69.46; **Bitext Mining 81.72** — proxy công bố tốt nhất cho căn chỉnh liên ngôn ngữ;
   `babakhin2025nemotron`).
   Hai encoder replication chọn theo **backbone lineage khác nhau**, không chỉ khác tổ chức:

   | | Model | Backbone | Org | License |
   |---|---|---|---|---|
   | E1 | `nvidia/llama-embed-nemotron-8b` | Llama-3.1 (decoder→bidirectional) | NVIDIA | NSCL v1 (research) |
   | E2 | `BAAI/bge-m3` | XLM-RoBERTa (encoder-only) | BAAI | MIT (`chen2024m3embedding`) |
   | E3 | `ibm-granite/granite-embedding-311m-multilingual-r2` | ModernBERT (IBM tự pretrain) | IBM | Apache-2.0 (`awasthy2026granite`) |

   Ngoài bộ ba neural còn một **encoder từ vựng (TF-IDF char n-gram)** dùng làm sàn không-ngữ-nghĩa; nó không thuộc
   nhóm kiểm encoder-independence mà là một trục sensitivity riêng (§6).

   **Family independence** giữ ở mọi tầng: không encoder nào thuộc họ Qwen/Alibaba (= agents được đo) hay
   OpenAI/Google (= judges). Đây không phải cẩn thận thừa: leaderboard 2026 đầy model **Qwen/Gemma trá hình dưới tên
   khác** — `microsoft/harrier-oss-v1-0.6b` là `model_type: qwen3`, bản 27b là `gemma3_text`, `jina-embeddings-v4` là
   Qwen2.5-VL, `voyage-4-nano` là Qwen3, `KaLM-Embedding-Gemma3-12B` (#1 MMTEB) là gemma-3-12b. **Phải mở
   `config.json` kiểm backbone**, không tin tên model.

   Cạm bẫy thứ hai — **lineage collision**: `bge-m3`, `multilingual-e5`, `arctic-embed-v2`, `jina-v3`,
   `nomic-v2` *đều* dựa XLM-RoBERTa. Lấy hai trong số đó chỉ được độc lập về tổ chức, không độc lập về biểu diễn
   (chung tokenizer + corpus pretrain). Vì vậy **chỉ lấy một** (E2), và E3 phải là ModernBERT.

   Đã loại có lý do: `Linq-Embed-Mistral` (thêm họ Mistral nhưng eval công bố chỉ tiếng Anh).

   **Chỉ E1 cần pod**; E2/E3 và sàn TF-IDF chạy local in-process (đo trên M4 Pro: bge-m3 ~44 phút, granite ~25 phút
   cho 335 340 text của ladder). Cache key không ghi backend nên **một model chỉ được dùng đúng một backend** —
   backend chốt cứng trong preset.

   Serve E1 trên RunPod RTX 5090 qua vLLM OpenAI-compatible (`vllm serve <model> --task embed`), scorer gọi API
   (preset `nemotron`, endpoint từ `NEMOTRON_EMBED_BASE_URLS`) với **embedding cache SQLite** riêng theo model (mỗi
   text encode đúng một lần; resumable; re-analysis miễn phí qua `--embed-cache-only`). **Một model mỗi slot** — các
   endpoint trong cùng slot được load-balance vào CÙNG một không gian vector nên trộn model sẽ hỏng ngầm; scorer chặn
   sẵn bằng cách đối chiếu `/v1/models` từng arm.

3. **Topic assignment**: argmax cosine tới learning goals của scenario (giữ như cũ).
4. **Bloom classifier.** Arm chính là `TransformerBloomClassifier` (mục dưới); arm sensitivity là **rule-based
   action-verb lexicon** (`LexiconBloomClassifier`) — tất định, không LLM, và là thứ giữ cho họ B có một instrument
   giải thích được.
   Thuộc dòng phương pháp citable (rule-based Bloom classification: Omar 2012; Haris & Omar; Jayakodi — accuracy báo
   cáo 70–97%). **Ba trụ phòng thủ, đều có số:**
   - **Xuất xứ**: cấp của động từ dẫn thẳng từ 19 cognitive process + alternative names của **Anderson & Krathwohl
     (2001), Table 5.1** (tier 1); các động từ ngoài A&K tách riêng thành tier 2, ghi rõ xuất xứ yếu hơn; các
     alternative name bị loại đều nêu lý do (đa nghĩa trong văn xuôi thường). Hệ quả khác bảng verb kiểu handout:
     `compare/contrast/match/categorize` là Understand, `integrate/outline/structure` là Analyze.
   - **Quy tắc gán cấp theo động từ dẫn đầu** (Webb: *central performance*), chọn bằng bằng chứng trên hai corpus có
     nhãn độc lập: κ 0,591→**0,657** (EDM2022 objectives) và 0,386→**0,434** (exam questions).
   - **Hiệu lực đo được**: trên [EDM2022CLO](https://github.com/SteveLEEEEE/EDM2022CLO) (21 380 learning objective gán
     nhãn tay, **đúng genre**) — coverage 84,1%, accuracy 72,7%, **κ = 0,657** ("substantial"), đạt **90%** khoảng giữa
     majority floor 27,1% và oracle ceiling 77,6%. Chính paper đó báo **κ = 0,63 giữa hai human coder** trên cùng bộ
     dữ liệu ⇒ lexicon **ngang mức đồng thuận chuyên gia**. Artifact: `docs/generated/bloom_validation.md`.

   **Vai trò của Bloom trong panel.** Bloom nuôi **3/7 tín hiệu** — `objective_cognitive_congruence`, `porter_*`,
   `webb_bloom_consistency` — cộng `sanity.*` ở tầng validity. Vì panel không có endpoint chính (§4), họ tín hiệu này
   phải có **trục sensitivity riêng**, y hệt encoder:

   - **Arm chính = `TransformerBloomClassifier`** — κ **0,926** với nhãn chuyên gia trên held-out (lexicon: 0,650),
     coverage 100%. Chọn theo **độ chính xác đo được**, và điều đó có giá: quyết định của nó không truy được về A&K
     cho từng ca (xem mục 3, phần "cái mất").
   - **Arm sensitivity = `LexiconBloomClassifier`** — tất định, dẫn thẳng từ A&K, giải thích được từng quyết định.
     Đây là arm kiểm mạnh nhất có thể có cho một model học từ nhãn: nó dẫn từ **taxonomy**, không dẫn từ dữ liệu, nên
     đồng thuận giữa hai arm (κ **0,665**, 73,5% raw) không phải đồng thuận rẻ tiền — hai instrument thật sự khác
     nhau, không phải hai bản sao.

   Chi tiết cách train arm chính — `bert-base-uncased` fine-tune trên **corpus** EDM2022CLO
   của Li et al. (2022). Bám sát **`createBERT`** trong `EDM2022 CLO.ipynb` — cùng base model, `max_length` 55,
   batch 64, 3 epoch, warmup 5, weight decay 0,05, learning rate mặc định của transformers, early stopping
   patience 10, chọn best model theo macro F1, split hai tầng 20% test rồi 20% val với `random_state=666` — và
   **thay đúng một thứ: head**. Notebook của họ ra 6 model nhị phân độc lập (hoặc một model multi-label ngưỡng
   0,5), đều cần thêm một tầng quyết định chưa từng được validate mới ra được một mức; panel cần **đúng một mức
   Bloom mỗi text**, nên arm này là **một head softmax 6 lớp** trên subset single-label (bỏ 2 607/21 380 dòng
   multi-label vì head đơn nhãn không biểu diễn được).

   Câu hỏi của trục này KHÔNG phải *"classifier nào đúng hơn"* mà là *thứ hạng agent có phụ thuộc lựa chọn classifier
   không*. Hai instrument dẫn xuất độc lập hoàn toàn — một từ taxonomy (A&K Table 5.1), một từ 21 380 nhãn người — mà
   cho cùng thứ hạng thì đó là bằng chứng mạnh hơn bất kỳ instrument đơn lẻ nào ở κ bất kỳ.

   Khác biệt giữa hai arm phải khai, không được giấu: BERT **argmax luôn** (coverage 100%), lexicon **abstain**
   (coverage 83,4% trên held-out), nên mẫu số của congruence/Porter/Webb khác nhau giữa hai arm. Thứ hạng sống sót qua
   hai instrument có coverage lệch hẳn nhau thì kết luận càng chắc. BloomBERT (English-only) chỉ là related work.
5. **Ngôn ngữ corpus: đồng nhất tiếng Anh, đảm bảo bằng thiết kế.** Scenario đầu vào thuần Anh, và
   prompt của **cả 7 agent** đã được thống nhất về tiếng Anh, nên ngôn ngữ đầu ra được cố định bởi cấu trúc chứ không
   bởi một chỉ thị "hãy trả lời bằng tiếng Anh" — chỉ thị kiểu đó không đáng tin ở model 0.8B. Bản cài đặt gốc của
   ReAct-ISD dùng prompt không phải tiếng Anh, nên phần prompt scaffolding của nó được dịch sang tiếng Anh (chỉ đổi
   ngôn ngữ, không đổi phương pháp) — đây là can thiệp duy nhất lên một baseline và cần nêu trong phần methodology
   của paper.

**Mức claim về tính tất định — phát biểu chính xác:**

- ĐÚNG: **không có lời gọi LLM sinh văn bản nào trong khâu đo lường**; điểm là **hàm cố định của văn bản đầu ra** —
  không sampling, không temperature, không prompt, nên không có prompt-sensitivity, self-preference bias, hay judge
  drift giữa các đợt chấm (drift của rubric judge đã đo được: +1.4…+2.0/100 giữa hai đợt).
- ĐÚNG: các thành phần **tất định theo đúng nghĩa chặt**: TF-IDF encoder, Bloom lexicon (arm sensitivity), toàn bộ
  phép tổng hợp (mean-max cosine, Porter/Webb), và **embedding cache** (sha1(model[@revision]+text) → vector) — cache
  làm mọi số báo cáo dựng lại **chính xác** từ artifact.
- **KHÔNG được claim**: tất định bit-wise của **bất kỳ thành phần neural nào** — cả encoder lẫn Bloom classifier
  chính. Forward pass trên GPU không đảm bảo tái lập từng bit khi đổi batch composition / phiên bản runtime / loại
  GPU (thứ tự reduction của matmul khác nhau). Với encoder, sai số cỡ **1e-6** trên cosine — nhỏ hơn khoảng cách đo
  được (0.19–0.30 giữa harness và á quân) khoảng **5 bậc** nên không đảo được thứ hạng. Với Bloom, hệ quả khác về
  chất: đầu ra là **argmax rời rạc**, nên nhiễu dấu phẩy động ở ranh giới hai lớp có thể **lật hẳn một nhãn** thay vì
  dịch một số. Mitigation: checkpoint được pin bằng file trên đĩa (không tải về), và tín hiệu họ B là **tỉ lệ trên
  ~90 scenario** nên một nhãn lật không dịch được con số báo cáo. Vẫn phải khai đúng là *reproducible up to
  floating-point noise*, KHÔNG phải *bit-wise deterministic*.
- **Cái mất khi lấy BERT làm arm chính, phải khai trong limitations**: quyết định gán cấp của arm chính **không còn
  truy được về A&K** cho từng trường hợp — nó là một checkpoint. Vế "không có lời gọi LLM sinh văn bản, không
  sampling, không prompt" **vẫn đúng** (BERT là classifier cố định, không sinh văn bản), nhưng vế "giải thích được
  từng quyết định" thì chỉ còn đúng với arm lexicon.
- **Cơ chế pin weights (đã có, cần bật)**: tên model không pin weights. Revision set **theo từng encoder arm**
  (`<SLOT>_EMBED_REVISION` / `--embed-revision-for`), được ghi vào score file thành `encoder_revision` **và đưa vào
  key của embedding cache** — nên bump revision là re-embed thật, không phải dán nhãn mới lên vector cũ. Pooling
  hard-fail nếu các run dir trộn nhiều cặp `(encoder, revision)`, và in `revision UNPINNED` khi chưa set. Phiên bản trọng số dùng cho đợt chấm hiện
  hành được ghi lại ở `docs/results.md` §6 (nemotron `aa3b43a4…`, bge-m3 `5617a9f6…`, granite `44399559…`) như thông
  tin tái hiện; muốn ràng buộc cứng thì set `<SLOT>_EMBED_REVISION` **trước** khi chấm.

Câu chuẩn dùng cho paper/slide: *"quy trình chấm không dùng LLM và không có thành phần ngẫu nhiên; kết quả tái lập
được nhờ pin phiên bản encoder và cache embedding"* — thay cho *"deterministic protocol"*.

### 4. Panel tín hiệu alignment — liên tục, không ngưỡng, không thứ bậc

Protocol báo cáo một **panel tín hiệu pre-specified, phẳng**: mỗi tín hiệu trả lời một câu hỏi riêng, mọi tín hiệu đều
được báo cho mọi so sánh — thắng hay thua — nên không tồn tại selective reporting. Paper đọc **profile**, không đọc một
số. **Không có "endpoint chính"**: alignment là construct nhiều mặt, gộp lại thành một số là đúng cái sai mà việc bỏ
composite đã sửa, còn gắn nhãn "chính / phụ" lên các mặt chỉ là composite ngầm.

**Quy tắc đặt tên**: tín hiệu mang tên của **phép toán nó thực hiện**, không phải của construct nó phục vụ. Tên metric
không bao giờ được đọc trong ngữ cảnh định nghĩa nó — nó nằm trên nhãn trục hình, header bảng, macro LaTeX, bullet
slide — nên một cái tên hứa nhiều hơn phép toán sẽ làm đúng công việc mà chỉ tầng bằng chứng (§7) có quyền làm. Hệ quả:
bốn tín hiệu họ embedding mang hậu tố `*_similarity`; chữ **"alignment"** chỉ sống ở tên **protocol** và ở tên **vế
predicate** `aligned(o)`, không nằm trên metric nào; và không tín hiệu nào được gọi là *precision* — chữ đó gợi khung
retrieval vốn phải có ngưỡng mới định nghĩa được, mà protocol thì không có ngưỡng nào.

Mọi tín hiệu liên tục đo bằng mean-max cosine, **không có ngưỡng matching/coverage nào**. Lý do thiết kế: một ngưỡng đủ
lỏng thì mọi hệ bão hoà ở ~1.00 (thước mất khả năng phân biệt), đủ chặt thì con số phụ thuộc vào một tham số không có
cơ sở lý thuyết để chọn — và reviewer sẽ hỏi tại sao chọn giá trị đó. Thang liên tục không có tham số nào để chọn.

**Một điểm phải khai đúng chữ**: cosine dùng ở đây là **rectified** — `max(0, cos)`, clip trần 1.0. Đây là lựa chọn
*thang đo* chứ không phải ngưỡng: cặp anti-correlated không "align" hơn cặp trực giao nên phần âm gộp về sàn 0, giữ
mọi endpoint chung [0, 1]; clip trần chỉ chặn tràn dấu phẩy động. Không có hằng số nào quyết định "hai text có khớp
hay không". Trong paper/slide gọi đúng là *rectified cosine trên [0, 1]*, *không có ngưỡng matching*.

**Panel gồm hai họ instrument độc lập cơ chế**, mỗi họ có trục sensitivity riêng (§6). Đây là tính chất thiết kế quan
trọng nhất của panel, và là câu trả lời cấu trúc — không phải biện hộ — cho chỉ trích *"panel của các anh chỉ là 7
biến thể của cosine"*: **không họ nào một mình gánh construct**.

**Họ A — textual correspondence** (đo bằng encoder; 4 tín hiệu):

| Tín hiệu | Trả lời câu gì | Hướng |
|---|---|---|
| `objective_assessment_similarity` | vế `measures` của `aligned(o)` — mean-max rectified cosine objective→assessment | cao = tốt |
| `objective_activity_similarity` | vế `supports` — cùng công thức, với activities | cao = tốt |
| `objective_evaluation_similarity` | vế `evaluates` — cùng công thức, với evaluation texts | cao = tốt |
| `assessment_objective_similarity` | chiều ngược: có assessment item mồ côi không | **không đơn nghĩa** |

**Họ B — cognitive demand** (đo bằng Bloom classifier; 3 tín hiệu, không dùng similarity):

| Tín hiệu | Trả lời câu gì | Hướng |
|---|---|---|
| `objective_cognitive_congruence` | % objective mà best assessment item (argmax, không ngưỡng) có Bloom level ≥ level của objective, trên objectives classifiable hai phía | cao = tốt |
| `porter_mean` (+ 3 cặp) | phân bố topic×level của objectives vs counterpart có cân không (Porter/Fulmer) | cao = tốt |
| `webb_bloom_consistency` | nhất quán mức nhận thức nhìn từ phía item (Webb) | cao = tốt |

`assessment_objective_similarity` là chỗ duy nhất **hướng không đơn nghĩa**: rất cao có thể là "không có item thừa",
mà cũng có thể là "assessment chỉ chép lại objective". Nó vẫn nằm trong panel và vẫn có test, nhưng khai là
**diagnostic không định hướng** — đọc kèm, KHÔNG cộng vào đếm "thắng bao nhiêu vế".

Ngoài panel: `details.validation.declared_link_agreement` và `details.sanity.*` **không phải tín hiệu panel** — chúng
đo instrument chứ không đo agent, nằm ở tầng validity evidence (§7).

- Degenerate: no objectives → 3 tín hiệu similarity họ A = 0.0; congruence undefined; set trống → tín hiệu tương ứng
  0.0 + note.
- Per-objective audit trail trong `details.objectives`: best_item/activity/evaluation + similarity liên tục + Bloom
  level. Toàn số thực, không có cờ boolean matched/covered nào.

### 5. Statistical analysis

**Multiplicity — hai tầng, báo cả hai.** Panel không có thứ bậc *báo cáo* (§4) nhưng vẫn cần neo *hiệu chỉnh*: 7 tín
hiệu × 6 so sánh × 4 size = 168 test, không hiệu chỉnh thì reviewer gọi đúng tên là fishing — và mỉa mai là nó hạ giá
chính cái panel.

- **Chính = Holm riêng cho từng tín hiệu**: mỗi tín hiệu một family = 6 so sánh/size. Phòng thủ chống selective
  reporting nằm ở chỗ **mọi tín hiệu đều báo cho mọi so sánh**, thắng hay thua, chứ không nằm ở việc gộp family.
  Giữ nguyên power.
- **Footnote = Holm chung toàn panel** (family = 7 tín hiệu × 6 so sánh mỗi size). Cùng dữ liệu, chỉ khác cách hiệu
  chỉnh, nên miễn phí về tính toán — và có nó thì câu *"kể cả hiệu chỉnh chung toàn panel, kết luận không đổi"* là
  miễn phí về lập luận. Key pooled: `comparisons[].p_holm_panel`.

- **Comparative (mỗi tín hiệu panel)**: paired Wilcoxon signed-rank per-scenario (mean-of-runs), proposed vs từng đối
  sánh, bootstrap 95% CI (10k, seed 42), rank-biserial. Key pooled:
  `alignment.stats.per_model[].panel[<signal>].comparisons`.
- **Scale**: **DiD** (largest − smallest size) trên paired delta per-scenario, bootstrap CI + Wilcoxon p — key
  `alignment.stats.interaction_align`. Chạy cho `objective_assessment_similarity` (vế `measures`, tín hiệu dẫn dắt
  narrative scale) và báo bảng phụ cho các tín hiệu còn lại.
- **Descriptive**: mean + bootstrap CI per agent/size (`align_descriptive`) + phân bố per-scenario, **cho mọi tín hiệu
  panel**; `conditional_align` (chỉ scenario mà mọi run được chấm đều cho ≥1 objective, đọc `counts.objectives`) tách
  chất lượng khỏi parse failure.
- **Failure policy** (song song RQ1, key `alignment.stats.per_model[].align_failures` +
  `comparisons_failure_zero`): hai layer trên là **complete-case trên output có sẵn**, không phải unconditional —
  agent crash thì benchmark không ghi `*_output.json` nên scenario rơi khỏi tập ghép cặp và cú crash không tốn gì cho
  agent. Scorer ghi roster `missing_outputs`, pooling chạy lại paired test với các cell đó impute 0.0. Không có
  `failure=min` vì endpoint đã sàn ở 0.0. **Artifact chấm trước 2026-07-27 chưa có roster** → pooling báo
  `UNKNOWN` (không phải "không có failure"); phải re-score `--overwrite` mới có layer này.
- Macros LaTeX: `rqTwoHarnessSim*`, `rqTwoHarnessSimCILo/Hi*`, `rqTwoSimPHolmMax*`, `rqTwoSimDiDVsBaseline*` — tên
  macro luôn bám tên metric; để hai thứ lệch nhau là cách chắc chắn nhất để prose nói sai về số.

### 6. Sensitivity — ba trục, mỗi trục một câu hỏi khác nhau

Instrument là **chiều được sweep** như kích thước mô hình: cùng một tập run được chấm lại bằng từng arm, rồi
`07_pool_ladder_runs.py --auto-encoders --auto-bloom` gộp thành `alignment_sensitivity` và tính mức đồng thuận với
cấu hình chính.

**Thiết kế star, KHÔNG phải grid.** Cấu hình chính = (encoder `nemotron` + Bloom `bertbloom`); mỗi arm lệch **đúng một
chiều** khỏi nó. Tổng cộng 5 arm (1 chính + 3 encoder + 1 Bloom), không phải 4×2 = 8. Grid không mua thêm câu trả lời
nào cho câu hỏi đang hỏi ("thứ hạng có phụ thuộc lựa chọn instrument không") mà nhân đôi chi phí và diện tích cần
kiểm.

Panel có hai họ instrument (§4) thì **mỗi họ phải có trục riêng** — đó là lý do trục 3 tồn tại: nếu chỉ sweep encoder,
3/7 tín hiệu (họ B) không được kiểm bởi trục nào cả.

**Trục 1 — Encoder independence (chính).** Chấm lại toàn bộ bằng E2 `bge-m3` và E3 `granite-r2`
(ghi ra `alignment_scores.{bgem3,granite}.json`). Câu hỏi: *thứ
hạng có phải là thuộc tính của output, hay là đặc tính riêng của một encoder?* Cần **ba** backbone lineage: hai
encoder mà bất đồng thì không phân xử được cái nào là ngoại lệ; hai encoder chung XLM-RoBERTa thì không độc lập về
biểu diễn (mục 3).

**Trục 2 — Sàn từ vựng (TF-IDF).** → `alignment_scores.tfidf.json`. Câu hỏi khác hẳn trục 1 và
không
encoder neural nào trả lời thay được: *thứ hạng có sống sót khi bỏ hẳn ngữ nghĩa không?* Giá trị tăng thêm: ba encoder
neural đều học contrastive trên web corpus lớn nên **sai số của chúng có thể tương quan** — đồng thuận giữa các mô
hình chia sẻ cùng thiên lệch là đồng thuận rẻ tiền; TF-IDF trực giao thật sự. Nó cũng là encoder duy nhất **tất định
bit-wise**, nên bổ trợ trực tiếp cho phần claim tái lập (mục 3): thứ hạng dựng lại được mà không phụ thuộc số học GPU.

**Trục 3 — Bloom classifier (họ B).** Chấm lại bằng `LexiconBloomClassifier` (mục 3.4) →
`alignment_scores.lexicon.json`, encoder giữ nguyên `nemotron`. Câu hỏi: *ba tín hiệu họ B có phải là thuộc tính của
output, hay là đặc tính riêng của một checkpoint học từ nhãn của một trường?* Hai instrument dẫn xuất độc lập hoàn
toàn — một từ 21 380 nhãn người, một từ A&K Table 5.1 — và **đo được là chúng khác nhau thật** (đồng thuận chỉ κ
0,665), nên đây không phải đồng thuận rẻ tiền kiểu các encoder neural cùng học contrastive trên web corpus.

Chi phí trục này gần bằng 0: Bloom chạy CPU, embedding lấy từ cache SQLite (`--embed-cache-only`), nên arm BERT
**không cần dựng pod**. Chi phí thật chỉ là một lần fine-tune (~21k dòng, vài phút GPU).

**Thống kê nào được báo.** Claim của paper là *harness > từng đối sánh*, nên số liệu robustness đúng là **chiều so
sánh theo cặp giữ nguyên qua các arm**, KHÔNG phải ρ Spearman của thứ tự đầy đủ 7 hệ — 5 hệ giữa bảng bám nhau quá
sát nên thứ tự giữa chúng vốn không phân giải được, và paper chưa bao giờ claim thứ tự đó.

*(Không có trục threshold sensitivity: endpoint liên tục nên không tồn tại tham số nào để "chọn cho đẹp".)*

### 7. Validity evidence & limitations

Validity của khung gốc KHÔNG tự thừa hưởng qua trích dẫn: công thức tổng hợp thừa hưởng trực tiếp (số học không đổi),
nhưng input đo lường (topic/Bloom/link) phải bắc cầu bằng bằng chứng. Tầng evidence có trong protocol:

- **Declared-link agreement** (`details.validation.declared_link_agreement`): % link objective↔item mà similarity
  matching tái tạo đúng link agent tự khai (`aligned_objective`) — convergent evidence cho khâu matching (link tự khai
  không bao giờ dùng để chấm).
- **Bloom-vs-declared agreement** (`details.sanity.bloom_vs_declared_agreement`, kèm `sanity.classifier`) —
  calibration cho Bloom classifier của arm đang chấm. Key mang chữ "bloom" chứ không phải "lexicon" vì trục Bloom có
  hai arm (§6); cùng lý do, mức Bloom per-objective là `details.objectives[].bloom_level`.
- **Benchmark cả hai Bloom arm trên EDM2022CLO** (`00_validate_bloom.py` — coverage/accuracy/κ/confusion cho từng arm,
  cộng κ agreement giữa hai arm; English đại diện tốt vì corpus ~91% English). BERT báo số trên **held-out split**,
  không báo số trên tập đã train — nếu không thì so sánh với lexicon là vô nghĩa. Kết quả đã đo: BERT κ 0,926 /
  coverage 100% vs lexicon κ 0,650 / coverage 83,4% trên cùng 3 755 dòng held-out; artifact
  `docs/generated/bloom_arms_validation.md`.
- **Convergence với judge rubric** (corroboration RQ1) — hai instrument độc lập cơ chế.
- **Expert study (Tier 3, để dành ETR&D)**: 2 chuyên gia blind code mẫu phân tầng theo thủ tục gốc, κ máy-vs-người —
  bước hoàn tất cây cầu validity, nằm ngoài phạm vi hiện tại.

Limitations phải khai trong paper: classifier/encoder error có thể **differential** (ngôn ngữ, mức paraphrase, cách
agent lặp objective) → **ranking cũng có thể đổi**, mitigation = 3 trục sensitivity; arm Bloom chính là một checkpoint
học từ quy ước mã hoá của **một** trường, nên nó khớp corpus đó κ 0,926 nhưng chưa được validate trên objective do
agent sinh ra — và không giải thích được từng quyết định (mục 3); protocol là operationalization tự động — không đo learning outcomes; **similarity không
phải alignment** — 4 tín hiệu họ A đo textual correspondence, và cầu nối sang construct alignment nằm ở tầng bằng
chứng trên, không nằm ở tên metric (§4) và bản thân cách đặt tên không mua validity; layer chính là complete-case
trên output có sẵn nên phải đọc kèm failure=0.

### 8. Citation checklist cho task update-paper

(Verify metadata trước khi viết bib.)

- Encoder: Llama-Embed-Nemotron-8B — arXiv 2511.07025 (NVIDIA, 2025).
- Rule-based Bloom: Omar et al. 2012 "Automated Analysis of Exam Questions According to Bloom's Taxonomy" (Procedia
  SBS); Haris & Omar (rule-based NLP classification); Jayakodi et al. (rules + N-gram).
- **Bloom sensitivity arm**: Li et al. (2022), *Automatic Classification of
  Learning Objectives Based on Bloom's Taxonomy*, EDM 2022 — nguồn của **corpus 21 380 nhãn** và là precedent cho
  việc fine-tune BERT trên learning objective (thiết kế classifier của ta khác họ, xem mục 3.4). Kèm dòng BERT/LLM
  Bloom nói chung: fine-tuned BERT for MOOCs (IRRODL); BloomLLM 2024 (Springer).
- Item–standards alignment bằng LM/embeddings (precedent): arXiv 2510.05129 (2025).
- Đã có trong bib: biggs1996enhancing, biggs2011teaching, qm2018rubric, porter2002measuring, fulmer2011estimating,
  webb1997criteria, clelandhuang2018traceability, feng2022labse (LaBSE — vai trò related work).

## Kết quả chính

*(Số cụ thể luôn lấy từ artifact sinh tự động — `pooled_ladder.json` → `09_gen_paper_tables.py` → `docs/generated/`,
và bản đọc được cho người ở `docs/results.md`. Đừng chép số vào đây: mục này mô tả **hình dạng** của kết quả và thứ tự
dẫn dắt narrative, số thì đọc từ artifact của lần chạy hiện hành.)*

1. **Robustness theo scale** — hệ đề xuất sinh output dùng được cho 100% scenario ở mọi size; các hệ không có scaffold
   hỏng phần lớn scenario ở model nhỏ (Fisher exact + Holm). Một phần failure có thể do truncation dưới trần token dùng
   chung — vẫn là failure ở cấp hệ thống.
2. **Điểm trên ISD-Agent-Bench** — vượt các hệ quy trình cùng lớp ở mọi size, dẫn điểm nội dung ADDIE. Ghi nhận trung
   thực: tương đương react-isd ở model lớn, và thua một đối sánh ở size nhỏ nhất về Total dù vẫn dẫn ADDIE và alignment.
3. **Bù scale (dạng defensible)** — lợi thế Total co lại có ý nghĩa khi model lớn lên (kiểm định tương tác/DiD);
   failure differential tập trung ở model nhỏ. Delta ở size nhỏ nhất với các hệ hỏng nhiều chỉ kiểm định được dưới
   sensitivity imputation — không claim từ DiD với n nhỏ.
4. **Alignment (RQ2)** — dẫn đầu ở mọi size **trên toàn bộ panel** (đọc profile, không đọc một số), rõ nhất ở
   `objective_assessment_similarity`; khoảng cách nới rộng khi model nhỏ đi (kiểm định tương tác âm). Robustness: giữ
   nguyên khi chỉ chấm scenario mọi hệ đều có output, và chiều so sánh theo cặp giữ nguyên qua cả ba trục sensitivity
   (§6 của section protocol) — gồm cả khi đổi Bloom classifier, tức thứ hạng không phải đặc tính của một
   classifier cụ thể.
5. **Ablation** — bộ nhớ đồ thị chung là cơ chế giữ alignment (gỡ ra thì giảm có ý nghĩa ở mọi size, mạnh nhất ở model
   nhỏ); verifier đứng riêng không đổi điểm nhưng skeleton rớt sâu hơn −GraphCtx ở mọi size → verifier là backstop
   tương tác + nguồn audit trail. Judge Total gần như bất biến giữa các arm trong khi alignment dịch rõ → LLM-judge
   không đo được alignment, củng cố lý do tồn tại của RQ2 protocol. 0 output failure ở mọi arm → robustness đến từ
   decomposition + kiểm tra cấu trúc, không phải từ hai cơ chế bị ablate.

## Ý nghĩa và phạm vi kết luận

Nếu giả thuyết được xác nhận, kết quả cho thấy các cơ chế ở cấp harness giúp chất lượng và alignment của hệ ISD ổn định
hơn khi mô hình nền được thu nhỏ, đồng thời cung cấp một quy trình audit alignment tự động, tái sử dụng được cho các
benchmark ISD. Kết
luận về cơ chế được giới hạn cẩn trọng ở hai mức: claim hệ thống (so với baseline) từ ladder, và claim cơ chế từ
ablation study — ablation tách được đóng góp của graph-context (có ý nghĩa, mọi size) và vai trò backstop của verifier
trên trục alignment, nhưng không tách phân rã tác vụ đa-agent (không có arm single-agent — decomposition là nền của mọi
arm), nên claim về decomposition vẫn ở mức hệ thống.

Hệ thống được định vị là decision support cho chuyên gia ISD với educator-in-the-loop, không thay thế chuyên gia; graph
dump là cơ chế audit và override cụ thể phục vụ định vị này. Các kết quả tạo cơ sở cho hướng triển khai hệ ISD bằng
open-weight SLM với chi phí thấp hơn và quyền kiểm soát dữ liệu tốt hơn tại các cơ sở giáo dục.
