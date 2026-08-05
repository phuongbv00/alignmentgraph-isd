# Alignment evaluation protocol (RQ2) — đặc tả chốt

> **Đây là đặc tả canonical của RQ2 protocol** — paper được cập nhật TỪ file này (methodology §RQ2,
> results §RQ2, threats/limitations). Trước đây nội dung này nằm trong `docs/summary.md`
> §"Alignment evaluation protocol"; tách ra 2026-08-03 khi summary.md được tái cấu trúc thành giàn ý paper.
>
> - Giàn ý paper + RQ context: [`docs/summary.md`](summary.md)
> - Lệnh chạy scorer/pooling + metrics reference: [`docs/benchmark_guides.md`](benchmark_guides.md) (§7, Appendix A)
> - Code: `isd-agent-benchmark/evaluator/src/isd_evaluator/metrics/alignment.py`, scorer
>   `scripts/alignmentgraph-isd-bench/06_score_alignment.py`, pooling `07_pool_ladder_runs.py`

## 1. Định vị & claim

Tên gọi: **automated constructive-alignment evaluation protocol operationalizing established criteria** (VN: quy trình
đánh giá constructive alignment tự động, operationalize các tiêu chí đã được thiết lập). **Không phải metric mới**;
không claim kế thừa validity của Porter/Webb/QM sang implementation — validity được bắc cầu bằng validation evidence
(mục 7). Chữ "proxy" chỉ dùng trong limitations như đặc tính phải khai, không dùng làm tên gọi. Mọi claim RQ2 ở mức
**tương đối** (comparative primary); mức tuyệt đối chỉ báo descriptive (mean + CI).

## 2. Nền lý thuyết

Khung Biggs–Tang (constructive alignment: ILO — hoạt động dạy học — đánh giá) làm nền; các tiêu chí review kiểu Quality
Matters rubric làm nguồn operationalize: (i) objective measurable; (ii) assessment đo đúng objective; (iii) activity
phục vụ objective; (iv) cognitive demand tương thích. Map thẳng vào predicate `aligned(o)` 3 vế
(measures/supports/evaluates) của problem formulation trong paper.

## 3. Pipeline (đúng runtime, không hứa quá)

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
  hard-fail nếu các run dir trộn nhiều cặp `(encoder, revision)`, và in `revision UNPINNED` khi chưa set. Phiên bản
  trọng số dùng cho đợt chấm hiện
  hành được ghi lại ở `docs/results.md` §6 (nemotron `aa3b43a4…`, bge-m3 `5617a9f6…`, granite `44399559…`) như thông
  tin tái hiện; muốn ràng buộc cứng thì set `<SLOT>_EMBED_REVISION` **trước** khi chấm.

Câu chuẩn dùng cho paper/slide: *"quy trình chấm không dùng LLM và không có thành phần ngẫu nhiên; kết quả tái lập
được nhờ pin phiên bản encoder và cache embedding"* — thay cho *"deterministic protocol"*.

## 4. Panel tín hiệu alignment — liên tục, không ngưỡng, không thứ bậc

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

| Tín hiệu                          | Trả lời câu gì                                                                  | Hướng               |
|-----------------------------------|---------------------------------------------------------------------------------|---------------------|
| `objective_assessment_similarity` | vế `measures` của `aligned(o)` — mean-max rectified cosine objective→assessment | cao = tốt           |
| `objective_activity_similarity`   | vế `supports` — cùng công thức, với activities                                  | cao = tốt           |
| `objective_evaluation_similarity` | vế `evaluates` — cùng công thức, với evaluation texts                           | cao = tốt           |
| `assessment_objective_similarity` | chiều ngược: có assessment item mồ côi không                                    | **không đơn nghĩa** |

**Họ B — cognitive demand** (đo bằng Bloom classifier; 3 tín hiệu, không dùng similarity):

| Tín hiệu                         | Trả lời câu gì                                                                                                                         | Hướng     |
|----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|-----------|
| `objective_cognitive_congruence` | % objective mà best assessment item (argmax, không ngưỡng) có Bloom level ≥ level của objective, trên objectives classifiable hai phía | cao = tốt |
| `porter_mean` (+ 3 cặp)          | phân bố topic×level của objectives vs counterpart có cân không (Porter/Fulmer)                                                         | cao = tốt |
| `webb_bloom_consistency`         | nhất quán mức nhận thức nhìn từ phía item (Webb)                                                                                       | cao = tốt |

`assessment_objective_similarity` là chỗ duy nhất **hướng không đơn nghĩa**: rất cao có thể là "không có item thừa",
mà cũng có thể là "assessment chỉ chép lại objective". Nó vẫn nằm trong panel và vẫn có test, nhưng khai là
**diagnostic không định hướng** — đọc kèm, KHÔNG cộng vào đếm "thắng bao nhiêu vế".

**Quy tắc đọc panel — pre-specified, phải viết trước khi đọc kết quả.** Không có endpoint chính thì kết luận RQ2 phụ
thuộc vào việc đọc profile, mà đọc profile không có quy tắc thì mọi hình dạng kết quả đều kể được thành một câu chuyện
thuận. Vì vậy quy tắc quyết định được chốt trước, áp dụng như nhau cho mọi cặp so sánh và mọi size:

> Kết luận **có lợi thế alignment** so với một đối sánh tại một size khi: **≥4/6 tín hiệu định hướng** dương có ý nghĩa
> sau Holm (trong-tín-hiệu), **và không tín hiệu định hướng nào âm có ý nghĩa**. Ngược dấu thì kết luận ngược. Mọi hình
> dạng khác — kể cả "5 dương, 1 âm có ý nghĩa" — được báo là **hỗn hợp**, và phải mô tả đúng vế thua, không được gộp
> thành một câu "vượt trội".

Mẫu số là **6, không phải 7**: `assessment_objective_similarity` bị loại khỏi phép đếm vì hướng không đơn nghĩa (đoạn
trên) — đây là quy tắc viết trước, không phải nhận xét sau khi thấy nó rơi vào phía nào. Quy tắc này **không phải
composite**: nó không cộng/chuẩn hoá tín hiệu nào thành một số, mỗi tín hiệu vẫn được báo riêng với p riêng; nó chỉ cố
định trước cách phát biểu kết luận từ một tập tín hiệu.

Ngoài panel: `details.validation.declared_link_agreement` và `details.sanity.*` **không phải tín hiệu panel** — chúng
đo instrument chứ không đo agent, nằm ở tầng validity evidence (§7).

- Degenerate: no objectives → 3 tín hiệu similarity họ A = 0.0; congruence undefined; set trống → tín hiệu tương ứng
  0.0 + note.
- Per-objective audit trail trong `details.objectives`: best_item/activity/evaluation + similarity liên tục + Bloom
  level. Toàn số thực, không có cờ boolean matched/covered nào.

## 5. Statistical analysis

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
  `comparisons_failure_zero`): **layer chính = `failure=0`** — scorer ghi roster `missing_outputs`, pooling chạy paired
  test với các cell đó impute 0.0. Hai layer comparative/descriptive ở trên tính trên **complete-case trên output có
  sẵn**, tức **không phải unconditional** và là **sensitivity, không phải kết quả chính**: agent crash thì benchmark
  không ghi `*_output.json` nên scenario rơi khỏi tập ghép cặp và cú crash không tốn gì cho agent (điều kiện hoá trên
  biến hậu-treatment — xem rationale failure policy ở giàn ý `summary.md` mục 8). Không có `failure=min` vì endpoint đã sàn ở 0.0. **Artifact chấm
  trước 2026-07-27 chưa có roster** → pooling báo `UNKNOWN` (không phải "không có failure"); phải re-score
  `--overwrite` mới có layer chính này.
- Macros LaTeX: `rqTwoHarnessSim*`, `rqTwoHarnessSimCILo/Hi*`, `rqTwoSimPHolmMax*`, `rqTwoSimDiDVsBaseline*` — tên
  macro luôn bám tên metric; để hai thứ lệch nhau là cách chắc chắn nhất để prose nói sai về số.

## 6. Sensitivity — ba trục, mỗi trục một câu hỏi khác nhau

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

## 7. Validity evidence & limitations

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
agent sinh ra — và không giải thích được từng quyết định (mục 3); protocol là operationalization tự động — không đo
learning outcomes; **similarity không
phải alignment** — 4 tín hiệu họ A đo textual correspondence, và cầu nối sang construct alignment nằm ở tầng bằng
chứng trên, không nằm ở tên metric (§4) và bản thân cách đặt tên không mua validity; layer chính là failure=0 nên phải
đọc kèm lát cắt complete-case (và complete-case không bao giờ được gọi là unconditional).

## 8. Citation checklist cho task update-paper

(Verify metadata trước khi viết bib.)

- Encoder: Llama-Embed-Nemotron-8B — arXiv 2511.07025 (NVIDIA, 2025).
- Rule-based Bloom: Omar et al. 2012 "Automated Analysis of Exam Questions According to Bloom's Taxonomy" (Procedia
  SBS); Haris & Omar (rule-based NLP classification); Jayakodi et al. (rules + N-gram).
- **Bloom sensitivity arm**: Li et al. (2022), *Automatic Classification of
  Learning Objectives Based on Bloom's Taxonomy*, EDM 2022 — nguồn của **corpus 21 380 nhãn** và là precedent cho
  việc fine-tune BERT trên learning objective (thiết kế classifier của ta khác họ, xem mục 3.4). Kèm dòng BERT/LLM
  Bloom nói chung: fine-tuned BERT for MOOCs (IRRODL); BloomLLM 2024 (Springer).
- Item–standards alignment bằng LM/embeddings (precedent): arXiv 2510.05129 (2025).
- **Tiền đề task decomposition** (giàn ý `summary.md` mục 4.5, nợ R7 — **đã trả**, metadata đã verify, đã có trong
  `docs/paper/acm/references.bib`): zhou2023leasttomost (Least-to-Most, ICLR 2023), khot2023decomposed (Decomposed
  Prompting, ICLR 2023), ferraz2024decrim (DeCRIM, Findings of EMNLP 2024), shen2024multillmagent (Small LLMs Are Weak
  Tool Learners, EMNLP 2024 main) — kèm belcak2025slm đã có sẵn. Bốn nguồn này chỉ đỡ vế "tác vụ hẹp dễ hơn tác vụ rộng
  đa mục tiêu"; **không** trích chúng cho vế "phân rã có lợi nhiều hơn khi model nhỏ đi" (vế đó là RQ1b, và
  cho2026harness cho kết quả không đơn điệu).
- Đã có trong bib: biggs1996enhancing, biggs2011teaching, qm2018rubric, porter2002measuring, fulmer2011estimating,
  webb1997criteria, clelandhuang2018traceability, feng2022labse (LaBSE — vai trò related work).
