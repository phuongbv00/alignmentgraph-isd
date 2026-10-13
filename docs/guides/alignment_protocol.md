# Alignment evaluation protocol (RQ2) — đặc tả chốt

> **Đây là đặc tả canonical của RQ2 protocol** — paper được cập nhật TỪ file này (methodology §RQ2,
> results §RQ2, threats/limitations). Bản thảo là source of truth cho nội dung, file này cho phép đo.
>
> - Mức claim + luật viết: [`docs/paper/claim-rules.md`](../paper/claim-rules.md); nội dung paper: `docs/paper/acm/`
> - Lệnh chạy scorer/pooling + metrics reference: [`docs/guides/benchmark_guides.md`](benchmark_guides.md) (§7, Appendix A)
> - Code: `experiments/src/isd_experiments/alignment/protocol.py`, scorer `isd-exp judge alignment`,
>   pooling `isd-exp pool comparison`

## 1. Định vị & claim

> **Positioning trong paper (chốt 2026-08-29, hướng paper lean)**: protocol **KHÔNG còn là đóng góp** và không được
> trình bày như một phương pháp/đề mục trong Method. Trong paper nó là **measurement setup** trong Experimental
> Design §Measures, justify như instrument requirement (LLM judge không lộ quan hệ alignment; phép đo sẵn có cần bộ
> chuẩn tiền-soạn), văn phong "assemble/operationalize established criteria", không claim novelty, chữ dùng là
> "the measurement" thay vì "the/our protocol". Thuật ngữ điểm số trong paper: giá trị panel =
> **"alignment signal(s)"**, điểm benchmark = **"LLM judge score(s)"** (luôn đủ chữ "LLM judge", không gọi cụt
> là "judge"); tên từng signal vẫn operation-named.
> File này vẫn là **spec canonical** cho code + số liệu + mức claim;
> tên "protocol" giữ trong tài liệu nội bộ. Mức claim: [`docs/paper/claim-rules.md`](../paper/claim-rules.md).

Tên gọi (nội bộ): **automated constructive-alignment evaluation protocol operationalizing established criteria**
(VN: quy trình đánh giá constructive alignment tự động, operationalize các tiêu chí đã được thiết lập). **Không phải metric mới**;
không claim kế thừa validity của Porter/Webb/QM sang implementation — validity được bắc cầu bằng validation evidence
(mục 7). Chữ "proxy" chỉ dùng trong limitations như đặc tính phải khai, không dùng làm tên gọi. Mọi claim RQ2 ở mức
**tương đối** (comparative primary); mức tuyệt đối chỉ báo descriptive (mean + CI).

## 2. Nền lý thuyết

Khung Biggs–Tang (constructive alignment: ILO — hoạt động dạy học — đánh giá) làm nền; các tiêu chí review kiểu Quality
Matters rubric làm nguồn operationalize: (i) assessment đo đúng objective; (ii) activity phục vụ objective;
(iii) cognitive demand tương thích. Map thẳng vào predicate `aligned(o)` 3 vế (measures/supports/evaluates) của
problem formulation trong paper.

## 3. Pipeline (đúng runtime, không hứa quá)

1. **Extract text-only** từ ADDIE output (objectives, assessment items, activities, evaluation texts) — không đọc
   nhãn/ID tự khai để chấm (chỉ dùng làm validation evidence). Activity = hoạt động dạy-học (TLA) trong
   `design.learning_activities` và các layout tương đương (`lesson_plan.modules[].activities`,
   `instructional_strategies.activities`); chuỗi sự kiện Gagné trong `instructional_strategies.sequence` là cấu
   trúc của một buổi, không phải activity, nên không đưa vào tập này.
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

   **Vai trò của Bloom trong panel.** Bloom nuôi **3 trong 6 tín hiệu panel** — `objective_cognitive_congruence`, `porter_*`,
   `webb_bloom_consistency` — cộng `sanity.*` ở tầng validity. Vì panel không có endpoint chính (§4), họ tín hiệu này
   phải có **trục sensitivity riêng**, y hệt encoder:

    - **Arm chính = `TransformerBloomClassifier`**, checkpoint `models/bloom-bert-objectives-and-questions`, train gộp
      trên objective EDM2022CLO và 4 bộ câu hỏi thi. Trên held-out: κ **0,918** với objective và **0,730** với câu
      hỏi (lexicon: 0,649 và 0,543), coverage 100%. Chọn theo **độ chính xác đo được**, và điều đó có giá: quyết định của nó không truy được về A&K
      cho từng ca (xem mục 3, phần "cái mất").
    - **Arm sensitivity = `LexiconBloomClassifier`** — tất định, dẫn thẳng từ A&K, giải thích được từng quyết định.
      Đây là arm kiểm mạnh nhất có thể có cho một model học từ nhãn: nó dẫn từ **taxonomy**, không dẫn từ dữ liệu, nên
      đồng thuận giữa hai arm (κ **0,667** trên objective, 73,6% raw; κ 0,620 trên câu hỏi) không phải đồng thuận rẻ
      tiền — hai instrument thật sự khác nhau, không phải hai bản sao.

   Chi tiết cách train arm chính — `bert-base-uncased` fine-tune trên **corpus** EDM2022CLO
   của Li et al. (2022) **cộng** 4 bộ câu hỏi thi do người gán nhãn (`faraji2026crossdataset`), vì classifier gán
   cấp cho cả objective lẫn item (xem §7). Lệnh: `isd-exp bloom train`; tập test của mỗi corpus do lệnh tự sinh từ corpus
   (EDM2022CLO theo đúng cách chia của createBERT), nên không có file test tĩnh nào phải giữ. Checkpoint
   được train trên GPU (MPS). Dữ liệu, các tập chia và công thức tái lập chính xác từ git, hai submodule corpus và
   revision của `bert-base-uncased` ghi trong `training_record.json`. **Trọng số thì không tái lập từng bit**: hai lần
   train trên MPS lệch κ tới ~0,02 và cho nhãn khác nhau ở 8–19% text của agent. Vì vậy checkpoint là validity
   evidence phải giữ (MOVED, không train lại), và phải khai trong limitations. Train trên CPU (`--device cpu`) thì
   trọng số trùng từng bit. Bám sát **`createBERT`** trong `EDM2022 CLO.ipynb` — cùng base model, `max_length` 55,
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
  được (0.19–0.30 giữa MAS và á quân) khoảng **5 bậc** nên không đảo được thứ hạng. Với Bloom, hệ quả khác về
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
  trọng số của mỗi đợt chấm nằm trong `encoder_revision` của chính score file, nên thông tin tái hiện đi cùng
  số chứ không nằm ở tài liệu riêng; muốn ràng buộc cứng thì set `<SLOT>_EMBED_REVISION` **trước** khi chấm.

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

**Họ A đúng bằng ba cạnh của tam giác Constructive Alignment (Biggs)** — ILO↔AT, ILO↔TLA, TLA↔AT — và mỗi cạnh ứng
1-1 với một quan hệ core của graph (C2/C3/C4). Không tín hiệu panel nào đo thứ mà ontology không mô hình hoá.

| Tín hiệu                          | Trả lời câu gì                                                                  | Quan hệ core | Hướng     |
|-----------------------------------|---------------------------------------------------------------------------------|--------------|-----------|
| `objective_assessment_similarity` | vế `measures` của `aligned(o)` — mean-max rectified cosine objective→assessment | C2 `assessed_by`  | cao = tốt |
| `objective_activity_similarity`   | vế `supports` — cùng công thức, với activities                                  | C3 `practiced_by` | cao = tốt |
| `activity_assessment_similarity`  | cạnh thứ ba: activity có chuẩn bị cho assessment không — mean-max activity→assessment | C4 `prepares_for` | cao = tốt |

**Họ B — cognitive demand** (đo bằng Bloom classifier; 3 tín hiệu, không dùng similarity):

| Tín hiệu                         | Trả lời câu gì                                                                                                                         | Hướng     |
|----------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|-----------|
| `objective_cognitive_congruence` | % objective mà best assessment item (argmax, không ngưỡng) có Bloom level ≥ level của objective, trên objectives classifiable hai phía | cao = tốt |
| `porter_mean` (+ 3 cặp)          | phân bố topic×level của hai đầu mỗi cạnh có cân không (Porter/Fulmer), trung bình trên **đúng 3 cạnh của họ A**   | cao = tốt |
| `webb_bloom_consistency`         | nhất quán mức nhận thức nhìn từ phía item (Webb)                                                                                       | cao = tốt |

**Vì sao congruence chỉ nhìn MỘT assessment item.** Muốn dùng "mọi item liên quan tới objective" thì phải có một hằng
số quyết định thế nào là liên quan, tức là một ngưỡng, thứ mà panel loại bỏ có chủ đích. Lấy hết mọi item không lọc thì
tín hiệu hỏng theo cách khác: một đề 40 câu chỉ cần có một câu ở cấp Create là mọi objective đều được tính congruent,
kể cả objective thực tế chỉ được hỏi ở cấp Remember, vì phép đo không còn biết item nào đo objective nào. Trọng số theo
similarity thì không cần ngưỡng nhưng lại cần chọn dạng hàm trọng số, tức đổi một hằng số tuỳ ý lấy một hằng số tuỳ ý
khác. `argmax` là cách duy nhất chọn được đúng một đối tác mà không so với hằng số nào, và nó theo đúng nguyên tắc
*central performance* của Webb. Các item còn lại không hề bị bỏ qua: `webb_bloom_consistency` duyệt từng item một
không sót cái nào, `porter_mean` đưa toàn bộ item vào ma trận phân bố.

**Congruence và Webb dùng hai quy ước chọn đối tác khác nhau, có chủ đích.** Congruence lấy argmax trên **toàn bộ**
assessment item, rồi bỏ objective đó khỏi mẫu số nếu item vừa chọn không phân loại được. Webb lấy argmax **trong số
các objective phân loại được**. Hai quy ước trả lời hai câu khác nhau. Congruence nói item gần nhất là item đại diện
cho objective này, không chấm được nó thì không kết luận. Webb chấp nhận thay bằng ứng viên gần nhất chấm được. Quy
ước của congruence chặt hơn, vì nó không thay thầm một item khác với item thực sự đại diện.

**Hệ quả phải khai: mẫu số của congruence co theo coverage của Bloom arm.** Arm chính `bertbloom` không bao giờ abstain
nên chuyện này không xảy ra lần nào, và mọi số RQ2 headline đều thuộc arm này. Arm sensitivity `lexicon` abstain
khoảng 17% nên nó xảy ra thường xuyên. Đo trên toàn bộ run dir `r1` (4 size × 10 agent × 90 scenario, encoder
`nemotron` đọc từ embedding cache, 16 784 objective có cấp phân loại được): **2 018 objective bị loại, tức 12,0%**,
trong đó 1 786 vẫn chấm được nếu dùng quy ước của Webb. Đây cùng loại với chênh lệch mẫu số đã khai giữa hai arm
(coverage 84% vs 100%) và được xử lý giống hệt: khai ra chứ không chỉnh cho hai arm bằng nhau. Thứ hạng sống sót qua
hai instrument có mẫu số lệch nhau là bằng chứng mạnh hơn thứ hạng đo trên hai instrument đã được chỉnh cho giống nhau.

**Hai họ đo CÙNG ba cạnh, chỉ khác instrument (sửa 2026-08-30).** Porter trước đây luôn lấy objectives làm mốc
(`objectives↔assessment`, `↔activities`, `↔evaluation`) — khung của thiết kế cũ, có từ trước khi C4 vào panel. Hệ quả:
cạnh `activity↔assessment` chỉ được đo bằng textual correspondence, trong khi hai cạnh kia được đo bằng cả hai họ. Nay
`PORTER_PAIRS` = `objective_assessment`, `objective_activity`, `activity_assessment`, khớp 1-1 với họ A. Hai họ khác
nhau ở **instrument** và không khác gì nữa — đó mới là lý do có hai họ.

**Đã xoá hẳn khỏi phép đo (2026-08-30):**

- `objective_evaluation_similarity` — tín hiệu họ A **duy nhất không ứng với quan hệ core nào**. Sau khi kiến trúc bỏ
  `evaluation` khỏi `NodeType`, nó đo phần text mà graph không mô hình hoá.
- `assessment_objective_similarity` — chiều ngược, **hướng không đơn nghĩa**: rất cao có thể là "không có item thừa",
  mà cũng có thể là "assessment chỉ chép lại objective".
- **Cặp Porter `objectives↔evaluation`** — cùng một lý do. Giữ nó lại thì evaluation bị đuổi khỏi họ A rồi quay lại
  panel qua họ B, chiếm 1/3 của `porter_mean`, và lập luận "đã bỏ evaluation" chỉ đúng hai phần ba.
- Kéo theo: `extract_evaluation_texts`, `counts["evaluation"]`, `best_evaluation*` trong `details.objectives`,
  `NON_PANEL_DIAGNOSTICS`, `NON_DIRECTIONAL_SIGNALS`. Không còn tín hiệu nào đọc text pha evaluation.

Trước đây hai tín hiệu đầu được giữ lại làm diagnostic để "số cũ truy hồi được". Lý do đó không còn: panel đã phải
re-score toàn bộ (xem §4 degenerate), nên không có tập số nào đang sống mà việc xoá làm gãy. Giữ code chết quanh một
phép đo là cách chắc chắn để nó bò lại vào bảng.

Về mối lo mất khả năng phát hiện item mồ côi/thừa khi bỏ chiều ngược: mối lo đó chuyển sang **phía sinh**, nơi
`checks.plan_coverage` của MAS buộc sinh đúng các cặp (objective, plan_category) mà assessment plan đã hứa và không
sinh filler. Đây là dịch chuyển thật, phải khai: panel không còn *đo* được item thừa.

**Thời điểm thay đổi.** Đổi panel sau khi đã thấy kết quả là đúng dạng selective reporting mà panel phẳng sinh ra để
chặn. Ba điều giữ cho thay đổi này hợp lệ, và phải nêu cả ba khi viết: (1) căn cứ là **lý thuyết** — hoàn tất tam giác
CA ở cả hai họ và buộc mọi tín hiệu ứng với một quan hệ core — không phải kết quả; (2) tín hiệu bị bỏ là tín hiệu hệ
thống đang **THẮNG** (`objective_evaluation_similarity`: +0.072…+0.326, mọi so sánh đều có ý nghĩa trên tập tune khi đó), nên
đây là bỏ tín hiệu có lợi, ngược với cherry-pick; (3) `test_90` **chưa** được score với kiến trúc mới, nên đây là thời
điểm hợp lệ cuối cùng để chốt thước đo.

**`porter_mean` đổi định nghĩa, phải khai.** Nó không còn là trung bình của ba cặp objective-vs-X mà là trung bình
trên ba cạnh tam giác. Mọi con số `porter_*` trong paper phải sinh lại từ đợt re-score sau 2026-08-30; số sinh trước mốc đó
**không so sánh được**.

**Quy tắc đọc panel — pre-specified, phải viết trước khi đọc kết quả.** Không có endpoint chính thì kết luận RQ2 phụ
thuộc vào việc đọc profile, mà đọc profile không có quy tắc thì mọi hình dạng kết quả đều kể được thành một câu chuyện
thuận. Vì vậy quy tắc quyết định được chốt trước, áp dụng như nhau cho mọi cặp so sánh và mọi size:

> Kết luận **có lợi thế alignment** so với một đối sánh tại một size khi: **≥4/6 tín hiệu định hướng** dương có ý nghĩa
> sau Holm (trong-tín-hiệu), **trong đó mỗi họ có ít nhất một tín hiệu**, **và không tín hiệu định hướng nào âm có ý
> nghĩa**. Ngược dấu thì kết luận ngược. Mọi hình
> dạng khác — kể cả "5 dương, 1 âm có ý nghĩa" — được báo là **hỗn hợp**, và phải mô tả đúng vế thua, không được gộp
> thành một câu "vượt trội".

Vế "mỗi họ ít nhất một" có lý do riêng. Ba tín hiệu họ A dùng chung một encoder, nên chỉ riêng họ A cộng một tín
hiệu họ B đã đủ 4/6. Không có vế này thì câu "không họ nào một mình gánh construct" chỉ là mô tả thiết kế, không phải
điều kiện của kết luận.

Mẫu số là **6 = toàn bộ panel**: sau khi tín hiệu không đơn nghĩa ra khỏi panel, mọi tín hiệu panel đều đơn hướng nên
không còn tín hiệu nào bị loại khỏi phép đếm (`NON_DIRECTIONAL_SIGNALS` rỗng theo cấu trúc). Quy tắc này **không phải
composite**: nó không cộng/chuẩn hoá tín hiệu nào thành một số, mỗi tín hiệu vẫn được báo riêng với p riêng; nó chỉ cố
định trước cách phát biểu kết luận từ một tập tín hiệu.

Ngoài panel: `details.validation.declared_link_agreement` và `details.sanity.*` **không phải tín hiệu panel** — chúng
đo instrument chứ không đo agent, nằm ở tầng validity evidence (§7).

- **Degenerate input — phân biệt lỗi của agent với giới hạn của instrument (sửa 2026-08-30).** Hai sự kiện này
  trước đây cùng cho `None` nên cùng bị loại khỏi mẫu số khi pooling. Quy tắc chốt:
    - **Agent không sinh ra set** (không objective, không assessment item, không activity) là **lỗi của agent** và
      phải nhận **0.0 + note**, không phải undefined. Áp dụng cho *mọi* tín hiệu phía objective, kể cả
      `objective_cognitive_congruence`, `porter_*`, `webb_bloom_consistency`. Nếu để undefined thì output tệ nhất
      lại rời khỏi mẫu số thay vì bị tính điểm, và tỉ lệ parse-fail cao ở model nhỏ nên phần thiếu tương quan
      thẳng với biến độc lập của RQ1.
    - **Set có nhưng classifier không gán được cấp Bloom** là **giới hạn instrument** và giữ `None` (undefined).
      Đây mới là trường hợp đúng để loại khỏi mẫu số.
    - **C4 (`activity_assessment_similarity`) không phụ thuộc objective** nên luôn được tính khi có đủ activity và
      assessment, kể cả khi không có objective nào. Cả hai phía trống → 0.0 + note (không phải undefined: sinh ra
      không gì cả không được điểm cao hơn sinh ra một phía).
  Hệ quả cho §5: layer `failure=0` chỉ còn phải bù các cell **không có file output**; cell có output nhưng rỗng đã
  được chấm 0.0 ngay từ scorer.
- Per-objective audit trail trong `details.objectives`: best_item/activity/evaluation + similarity liên tục + Bloom
  level. Toàn số thực, không có cờ boolean matched/covered nào.

## 5. Statistical analysis

**Multiplicity — một tầng.** Panel không có thứ bậc *báo cáo* (§4), nhưng mỗi so sánh vẫn được hiệu chỉnh. Phòng
thủ chống fishing có hai phần: Holm trong từng tín hiệu, và quy tắc đọc ở §4 được cố định trước khi có kết quả, đọc
trên mọi tín hiệu của mọi so sánh.

- **Holm riêng cho từng tín hiệu**: mỗi tín hiệu một family = 6 so sánh/size, tính riêng cho layer chính và cho layer
  sensitivity → `p_holm`. Phòng thủ chống selective reporting nằm ở chỗ **mọi tín hiệu đều báo cho mọi so sánh**,
  thắng hay thua, chứ không nằm ở việc gộp family. Giữ nguyên power. Quy tắc đọc panel (§4) đọc đúng `p_holm` này.

- **Comparative (mỗi tín hiệu panel)**: paired Wilcoxon signed-rank hai phía per-scenario (mean-of-runs, `failure=0`),
  proposed vs từng đối sánh — p là exact null có hạng trùng tới `n_effective` 500 (routine riêng, đối chiếu với SciPy
  trong `tests/test_stats.py`), bootstrap BCa 95% CI (SciPy, 10k, seed 42), rank-biserial. Key pooled:
  `alignment.stats.per_model[].panel[<signal>].comparisons`; cùng phép thử trên complete-case (sensitivity) ở
  `comparisons_complete_case`.
- **Scale**: **DiD** (largest − smallest size) trên paired delta per-scenario dưới `failure=0`, bootstrap CI + Wilcoxon
  p — key `alignment.stats.interaction_align`. Chạy cho `objective_assessment_similarity` (vế `measures`, tín hiệu dẫn
  dắt narrative scale) và báo bảng phụ cho các tín hiệu còn lại.
- **Descriptive**: mean + bootstrap BCa CI per agent/size dưới `failure=0` (`align_descriptive`), mean complete-case
  (`complete_case_descriptive`) + phân bố per-scenario, **cho mọi tín hiệu panel**; `conditional_align` (chỉ scenario
  mà mọi run được chấm đều cho ≥1 objective, đọc `counts.objectives`) tách chất lượng khỏi parse failure.
- **Failure policy** (một policy cho mọi claim — RQ1, panel và ablation; key
  `alignment.stats.per_model[].align_failures`): **layer chính = `failure=0`** — scorer ghi roster `missing_outputs`,
  pooling tính các cell đó là 0.0 trong mọi so sánh và mọi mean mô tả ở trên. **Sensitivity duy nhất = complete-case
  trên output có sẵn** (`comparisons_complete_case`, `complete_case_descriptive`), **không bao giờ gọi là
  unconditional**: agent crash thì benchmark không ghi `*_output.json` nên ở layer này scenario rơi khỏi tập ghép cặp và
  cú crash không tốn gì cho agent (điều kiện hoá trên biến hậu-treatment — rationale failure policy nằm ở §Experimental
  Design của bản thảo). Tỉ lệ failure chỉ báo mô tả (`align_failures`), không kiểm định lại: dưới `failure=0` mỗi
  failure đã tính 0 trong phép thử. **Artifact không ghi roster** thì không có cell nào để tính 0 và layer chính suy
  biến thành complete-case; phải re-score `--overwrite`.
- Macros LaTeX: `alignmentHarnessSim*`, `alignmentHarnessSimCILo/Hi*`, `alignmentSimPHolmMax*`, `alignmentSimDiDVsBaseline*` — tên
  macro luôn bám tên metric; để hai thứ lệch nhau là cách chắc chắn nhất để prose nói sai về số.

## 6. Sensitivity — bốn trục, mỗi trục một câu hỏi khác nhau

Instrument là **chiều được sweep** như kích thước mô hình: cùng một tập run được chấm lại bằng từng arm, rồi
`isd-exp pool comparison --auto-encoders --auto-bloom` gộp thành `alignment_sensitivity` và tính mức đồng thuận với
cấu hình chính.

**Thiết kế star, KHÔNG phải grid.** Cấu hình chính = (encoder `nemotron` + Bloom `bertbloom`); mỗi arm lệch **đúng một
chiều** khỏi nó. Tổng cộng 6 arm (1 chính + 3 encoder + 1 baseline + 1 Bloom), không phải một grid. Grid không mua thêm câu trả lời
nào cho câu hỏi đang hỏi ("thứ hạng có phụ thuộc lựa chọn instrument không") mà nhân đôi chi phí và diện tích cần
kiểm.

Panel có hai họ instrument (§4) thì **mỗi họ phải có trục riêng** — đó là lý do trục 3 tồn tại: nếu chỉ sweep encoder,
3 trong 6 tín hiệu (họ B) không được kiểm bởi trục nào cả.

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
output, hay là đặc tính riêng của một checkpoint học từ nhãn người?* Hai instrument dẫn xuất độc lập hoàn toàn — một
từ nhãn người của hai corpus, một từ A&K Table 5.1 — và **đo được là chúng khác nhau thật** (đồng thuận chỉ κ 0,667
trên objective và 0,620 trên câu hỏi), nên đây không phải đồng thuận rẻ tiền kiểu các encoder neural cùng học contrastive trên web corpus.

Chi phí trục này gần bằng 0: Bloom chạy CPU, embedding lấy từ cache SQLite (`--embed-cache-only`), nên arm BERT
**không cần dựng pod**. Chi phí thật chỉ là một lần fine-tune (`isd-exp bloom train`, ~16,5k dòng, ~25 phút GPU).

**Thống kê nào được báo.** Claim của paper là *MAS > từng đối sánh*, nên số liệu robustness đúng là **chiều so
sánh theo cặp giữ nguyên qua các arm**, KHÔNG phải ρ Spearman của thứ tự đầy đủ 7 hệ — 5 hệ giữa bảng bám nhau quá
sát nên thứ tự giữa chúng vốn không phân giải được, và paper chưa bao giờ claim thứ tự đó.

**Trục 4 — Hiệu chỉnh mức nền (họ A).** → `alignment_scores.contrast.json` (`alignment/contrast.py`, khai báo ở
`[judge.alignment.baseline]`). Trục này không đổi instrument nào. Nó đọc cache embedding của encoder chính và thay ba
tín hiệu họ A của scenario *s* bằng `own − foreign`:

- `own` = mean-max của chính scenario *s*;
- `foreign` = trung bình mean-max của objective (hoặc activity) ở *s* so với item (hoặc activity) của **các scenario
  khác, cùng agent, cùng run**.

Họ B được chép nguyên từ file chính, nên arm chỉ lệch đúng một trục. Câu hỏi: *thứ hạng có sống sót khi trừ đi phần
similarity mà encoder cho mọi text cùng miền, bất kể có liên quan hay không?*

Lý do có trục này là số đo trên tune-10 (bge-m3): objective của một agent so với item nó viết cho scenario **khác**
vẫn đạt mean-max 0,51–0,58. Như vậy hơn nửa thang [0, 1] là sàn. Sàn này còn khác nhau giữa các agent: agent viết
theo một template quen thuộc thì gần với item "lạ" của chính nó hơn. Trừ theo từng agent nghĩa là mỗi hệ được hiệu
chỉnh bằng mức nền của chính nó. Phép trừ không có tham số, và giá trị nằm trên [−1, 1].

Trục này **không** khử được việc item chép objective: một item chép lại là đặc thù cho đúng scenario đó, nên vẫn sống
sót qua phép trừ. Chép objective được xử lý ở §7 (chẩn đoán trùng từ) và ở phía sinh.

*(Không có trục threshold sensitivity: endpoint liên tục nên không tồn tại tham số nào để "chọn cho đẹp".)*

## 7. Validity evidence & limitations

Validity của khung gốc KHÔNG tự thừa hưởng qua trích dẫn: công thức tổng hợp thừa hưởng trực tiếp (số học không đổi),
nhưng input đo lường (topic/Bloom/link) phải bắc cầu bằng bằng chứng. Tầng evidence có trong protocol:

- **Declared-link agreement** (`details.validation.declared_link_agreement`): % link objective↔item mà similarity
  matching tái tạo đúng link agent tự khai (`aligned_objective`) — convergent evidence cho khâu matching (link tự khai
  không bao giờ dùng để chấm).
- **Độ trùng từ objective–item** (`details.validation.objective_item_lexical_overlap`, và
  `details.objectives[].best_item_lexical_overlap` cho từng objective): Jaccard của từ nội dung giữa objective và item
  gần nó nhất, sau khi bỏ stopword và động từ Bloom của lexicon. Giá trị liên tục, không ngưỡng, và không phải tín
  hiệu panel. Lý do: một item chép lại câu objective được **mọi** encoder đọc là tương ứng gần hoàn hảo. Đo trên
  tune-10, độ trùng này tương quan r = 0,85–0,87 với `objective_assessment_similarity` theo scenario. Ở 2B có run tới
  26/58 objective có item gần như chép nguyên văn (react-isd 3/44); ở 9B là 0. Tỉ lệ chép tăng khi model nhỏ đi, nên
  nó chạm vào biến độc lập của RQ1. Phía sinh, harness từ chối item chép objective ngay lúc submit
  (`fanout.item_restatement_errors`, `PROTOCOL_REV` 9); chẩn đoán này là cách đọc lại mức còn sót trên output của
  **mọi** hệ. Báo theo agent trong `facts.md` §4.
- **Bloom-vs-declared agreement** (`details.sanity.bloom_vs_declared_agreement`, kèm `sanity.classifier`) —
  calibration cho Bloom classifier của arm đang chấm. Key mang chữ "bloom" chứ không phải "lexicon" vì trục Bloom có
  hai arm (§6); cùng lý do, mức Bloom per-objective là `details.objectives[].bloom_level`.
- **Bloom classifier trên hai thể loại nó gán cấp** (`isd-exp bloom validate`; báo cáo
  `results/generated/bloom_{objectives,questions}_validation.md`; bằng chứng giữ trong git ở
  `experiments/tests/fixtures/bloom/`). Classifier gán cấp cho objective, item và activity, nên nó được train và chấm
  trên hai corpus có nhãn người:
    - EDM2022CLO (learning objective);
    - 4 bộ câu hỏi thi đã công bố (Yahya 2012, Sangodiah 2017, Mohammed & Omar 2020, Gani 2023; 2 341 câu). Bộ 1 838 câu
      do LLM sinh trong cùng repo bị loại.
  Tập test của mỗi corpus do `isd-exp bloom train` sinh từ chính corpus đó (seed 666): 3 755 objective theo cách chia
  của createBERT, và 464 câu hỏi phân tầng theo nguồn × nhãn. Không text nào của chúng nằm trong train/val
  (13 229 / 3 309). Chỉ báo số trên tập held-out, vì báo trên tập đã train thì so sánh với lexicon vô nghĩa. Kết quả:
    - objective: BERT κ **0,918** (93,4% đúng); lexicon κ 0,649 trên 83,5% câu nó phân loại được;
    - câu hỏi: BERT κ **0,730** (79,1% đúng); lexicon κ 0,543 trên 84,7%;
    - lỗi có dấu của BERT ≈ 0 trên cả hai (+0,01 mức). Điều này quan trọng vì congruence và Webb tính một item là đạt
      khi cấp của nó ≥ cấp objective. Một classifier chấm item cao hơn thực tế sẽ thổi phồng cả hai tín hiệu;
    - đồng thuận giữa hai arm: κ 0,667 trên objective, 0,620 trên câu hỏi.
  **Độ biến thiên giữa các lần train (phải khai):** train lại cùng dữ liệu, cùng công thức trên MPS làm κ trên câu hỏi
  lệch tới ~0,02. Trên text thật của agent (tune-10), hai lần train chỉ trùng nhãn ở 92% objective, 81% item và 85%
  activity. Họ B vì thế phụ thuộc vào đúng checkpoint này, nên checkpoint là bằng chứng phải giữ. Activity **chưa có**
  bằng chứng validate nào.
- **max_length của `bertbloom`**: train dùng 55, lúc chấm dùng 128. Trên hai tập test, κ lệch ≤ 0,003 giữa hai mức, nên
  giữ 128.
- **Convergence với judge rubric** (corroboration RQ1) — hai instrument độc lập cơ chế.
- **Expert study (Tier 3, để dành ETR&D)**: 2 chuyên gia blind code mẫu phân tầng theo thủ tục gốc, κ máy-vs-người —
  bước hoàn tất cây cầu validity, nằm ngoài phạm vi hiện tại.

Limitations phải khai trong paper: classifier/encoder error có thể **differential** (ngôn ngữ, mức paraphrase, cách
agent lặp objective) → **ranking cũng có thể đổi**, mitigation = 4 trục sensitivity; arm Bloom chính là một checkpoint
học từ quy ước mã hoá của một trường (objective) và của bốn bộ đề thi đã công bố (câu hỏi). Nó đạt κ 0,918 và 0,730 trên
held-out của hai thể loại đó, nhưng chưa được validate trên objective hay câu hỏi do agent sinh ra, và **activity chưa
có bằng chứng nào**. Nó không giải thích được từng quyết định (mục 3); protocol là operationalization tự động — không đo
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
- **Validate Bloom trên câu hỏi**: `faraji2026crossdataset`. Đây là bài AIED 2026, LNCS, trang 198–207, DOI
  10.1007/978-3-032-29760-0_22, metadata đã kiểm qua Crossref. Bài này phát hành 4 bộ câu hỏi dùng ở §7 trong repo
  của nó; repo đó là submodule `bloom-classification-aied2026`. Đã có trong `references.bib`.
- **Related-work contrast — các họ quantification khác cho CA/alignment** (thêm 2026-08-30, deep-research xác nhận gap):
  cả ba đều KHÔNG đo trọn tam giác Biggs bằng panel tự động deterministic, nên trích để khoanh gap chứ không phải để
  kế thừa phương pháp.
   - `zhao2023alignment` — áp dụng Porter formula thực nghiệm (2 trường phổ thông, κ liên-rater 0,781), chỉ ra
     instruction↔assessment thường đạt "high alignment" (P>0,5) trong khi alignment với objectives/standards thấp hơn.
     Dùng làm precedent cho việc Porter/Webb khi áp dụng thực tế cần một **ngưỡng** — tương phản trực tiếp với thiết kế
     **không ngưỡng** của panel (§4).
   - `barthakur2022aligning` — multidimensional IRT kiểm định thống kê cấu trúc alignment outcome↔assessment từ dữ
     liệu **phản hồi sinh viên** (không phải text). Trích ở related work để phân biệt: protocol của ta text-based, áp
     dụng được ngay lúc sinh output, không cần dữ liệu điểm số người học.
   - `rossnagel2021revisiting` — thang tự báo cáo CALEQ đo CA **cảm nhận** của sinh viên (perceived alignment), không
     đo trực tiếp trên artifact. Trích để tương phản: panel của ta đo trên chính output (objective/assessment/activity
     text), deterministic, không qua khảo sát.
   - `pawar2018similarity` — "Bloom Index": similarity cặp động từ cho Bloom-level matching. Thêm vào dòng rule-based
     Bloom cùng Omar/Haris/Jayakodi — precedent gần nhất cho thiết kế `LexiconBloomClassifier` (dẫn từ động từ, không
     học từ nhãn).
- **Tiền đề task decomposition** (nợ R7 — **đã trả**, metadata đã verify, đã có trong
  `docs/paper/acm/references.bib`): zhou2023leasttomost (Least-to-Most, ICLR 2023), khot2023decomposed (Decomposed
  Prompting, ICLR 2023), ferraz2024decrim (DeCRIM, Findings of EMNLP 2024), shen2024multillmagent (Small LLMs Are Weak
  Tool Learners, EMNLP 2024 main) — kèm belcak2025slm đã có sẵn. Bốn nguồn này chỉ đỡ vế "tác vụ hẹp dễ hơn tác vụ rộng
  đa mục tiêu"; **không** trích chúng cho vế "phân rã có lợi nhiều hơn khi model nhỏ đi" (vế đó là RQ1b, và
  cho2026harness cho kết quả không đơn điệu).
- Đã có trong bib: biggs1996enhancing, biggs2011teaching, qm2018rubric, porter2002measuring, fulmer2011estimating,
  webb1997criteria, clelandhuang2018traceability, feng2022labse (LaBSE — vai trò related work).
