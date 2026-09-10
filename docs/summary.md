# AlignmentGraph-ISD — giàn ý paper

> **Vai trò file này**: giàn ý đã chốt cho paper — mọi section của bản thảo đối chiếu với file này.
> Bám khung 15 mục trong [`docs/paper/structure-guide.md`](paper/structure-guide.md) (đề cương của thầy);
> mỗi mục ghi rõ map sang file `.tex` nào trong `docs/paper/acm/sections/`.
>
> - Đặc tả canonical RQ2 protocol (đầy đủ, không nén): [`docs/rq2_protocol.md`](rq2_protocol.md) — paper được cập nhật
    TỪ file đó.
> - Workflow benchmark + metrics reference: [`docs/benchmark_guides.md`](benchmark_guides.md).
> - **Số liệu**: mọi con số trong paper sinh tự động (`pooled_ladder.bk.json` → `09/13/14_gen_*` + `ablation/11_gen_*` →
    `docs/generated/`), không gõ tay. Bản đọc cho người: `docs/results.md`. Mục 9 dưới đây chỉ mô tả **hình dạng** kết
    quả và thứ tự narrative.
> - **Văn phong & độ dài (2026-08-11)**: bám khung 15 mục nhưng KHÔNG bôi cho đủ mục — mục ít nội dung viết ngắn;
    văn xuôi lập luận liền mạch (topic sentence, chuyển ý), không "chép giàn ý thành câu"; độ dài paper vừa phải,
    không ép số trang cụ thể.
> - **Quy tắc claim (thầy chốt 2026-08-17, `docs/review_q2.md` T5)**: CẤM "vượt trội toàn diện"/"tốt nhất mọi chỉ
    số"/"verifier cải thiện chất lượng đầu ra"/"chứng minh constructive alignment đầy đủ". DÙNG: robustness dưới SLM +
    token cap; ADDIE cạnh tranh — lợi ở model nhỏ, parity ở model lớn ("competitive and robust", không "superior");
    graph context cải thiện *các tín hiệu đo được*; graph dump → auditability + teacher-in-the-loop; verifier =
    backstop check/repair + nguồn evidence audit. **Paper không bao giờ đề cập RAG** (RAG chỉ thuộc luận văn).
> - **Thuật ngữ điểm số (chốt 2026-08-29)**: điểm từ ISD-Agent-Bench = **"LLM judge score(s)"** (không "judge
    signal" / "judge-based measures"); giá trị panel = **"alignment score(s)"** (không "alignment signal" / "panel
    signal"); tập hợp vẫn là "alignment panel". Tên từng score vẫn theo phép toán (`*_similarity`, congruence,
    Porter, Webb), không score nào tên "precision". Riêng câu guard *"measurable signals of constructive
    alignment"* giữ nguyên chữ "signal" — vai trò claim-scoping (score là tín-hiệu-của construct, không phải
    construct).
> - **Backlog Q2**: `docs/review_q2.md` (tái lập 2026-08-17 từ góp ý thầy; giữ nhãn R2/R4 cũ).
> - **Bản VN (`acm/vn/`) đã XOÁ 2026-08-29** (freeze từ 2026-08-17, khôi phục được qua git history nếu cần) — chỉ còn bản EN.
> - **SKELETON 7 MỤC (user chốt 2026-08-11, theo khảo sát 12 paper — đồng hình EduPlanner TLT 2025)**: thân bài =
    Introduction / Related Work / **AlignmentGraph-ISD** (problem setting nén → MAS → protocol) /
    **Experimental Design** (đổi tên từ "Experimental Methodology") / Results / **Discussion** (kết bằng subsection
    "Threats to validity and limitations" — giữ đủ construct/internal/external/conclusion + future work) /
    Conclusion. File: `03_problem_formulation.tex` và `08_threats_limitations.tex` **bỏ** (nội dung gộp vào 04 và 07);
    khung 15 mục dưới đây vẫn là danh mục NỘI DUNG phải có, không còn là danh mục section.

## 1. Title

- **Đã chốt** (thầy chốt 2026-08-17, thêm "Auditable"): *AlignmentGraph-ISD: A Graph-Guided Multi-Agent Harness for
  Auditable Instructional Systems Design with Small Language Models* (khớp `main.tex`).
- Phủ: phương pháp (graph-guided multi-agent harness) + tính chất (auditable) + đối tượng (ISD) + bối cảnh (SLM —
  positioning của bài là open-weight SLM triển khai tại chỗ).

## 2. Abstract — `00_abstract.tex`

Một đoạn thống nhất, 7 phần theo đúng trình tự; mỗi phần viết gì:

1. **Bối cảnh** (1 câu): LLM thương mại sinh được chương trình giảng dạy chất lượng cao và ngày càng được dùng trong
   ISD.
2. **Vấn đề** (1–2 câu, sửa 2026-08-29 — burden-shift, KHÔNG viết "phụ thuộc vào MAS" vì MAS là giải pháp đề xuất,
   không phải tiên đề): chi phí suy luận, phụ thuộc API, dữ liệu người học qua bên thứ ba → cơ sở giáo dục cần
   open-weight SLM tại chỗ; model nhỏ đi thì gánh nặng chất lượng dịch chuyển từ model sang hệ bao quanh nó — và thứ
   lâm nguy trước tiên là sự ăn khớp mục tiêu↔hoạt động↔đánh giá (constructive alignment), vốn được các hệ hiện có phó
   thác cho model tự duy trì ngầm.
3. **Khoảng trống** (1 câu, MỘT gap duy nhất — chốt 2026-08-29, bỏ gap đo lường khỏi hàng gap): duy trì chất lượng
   khi thu nhỏ model nền chưa được nghiên cứu như mục tiêu thiết kế + đánh giá của hệ tác tử ISD.
4. **Phương pháp** (1 câu, map vào gap duy nhất): AlignmentGraph-ISD — MAS tổ chức sinh quanh alignment graph, trạng
   thái alignment tường minh + kiểm được + audit được (graph dump). Phép đo alignment không-LLM KHÔNG đứng thành câu
   phương pháp/đóng góp riêng — chỉ xuất hiện trong câu evaluation của phần thiết lập ("We evaluate it with
   ISD-Agent-Bench and a deterministic, no-LLM alignment-score measurement…").
5. **Thiết lập thực nghiệm** (1 câu): 90 scenario ISD-Agent-Bench, 6 hệ đối sánh, dải Qwen 0.8B–9B (4 size × 3 run độc
   lập), chấm bằng cả judge rubric lẫn alignment panel; ablation 3 arm bên trong ladder.
6. **Kết quả định lượng** (2–3 câu, số nổi bật nhất — lấy từ macro `docs/generated/`, không gõ tay):
    - Robustness: output dùng được 100% scenario mọi size, trong khi hệ một-lượt hỏng phần lớn ở model nhỏ (kèm
      failure-rate của baseline tại size nhỏ nhất).
    - Judge: **cả ba tín hiệu nêu ngang nhau** (`addie_median` + con số, `trajectory_score`, `total_score`) — dẫn ADDIE
      mọi size; nếu nêu total_score thì nói thật chỗ thua ở size nhỏ nhất.
    - Alignment + scale: dẫn panel mọi size theo quy tắc đọc pre-specified; khoảng cách nới rộng khi model nhỏ đi
      (DiD + p).
7. **Ý nghĩa** (1 câu): cơ chế cấp MAS giữ chất lượng và tín hiệu alignment ổn định hơn khi thu nhỏ model trên dải
   Qwen 0.8B–9B → hướng triển khai ISD bằng SLM tại chỗ, kèm alignment graph xuất được để audit
   (teacher-in-the-loop) — KHÔNG nêu "quy trình audit tái sử dụng được" (protocol không còn là deliverable,
   2026-08-29).

**Ràng buộc:**

- Giới hạn tối đa 200 từ
- **Đổi 2026-08-12 (user)**: abstract KHÔNG liệt kê đủ ba tín hiệu judge và **không nhắc `total_score`**; vế negative
  trung thực của abstract = Trajectory thua react-isd + ADDIE-Agent mọi size + chi phí token trên trung vị baseline.
  Ghi nhận `total_score` thua (hai đầu ladder) vẫn BUỘC ở Results (mục 9.2); nguyên tắc "ba tín hiệu ngang hàng, không
  endpoint" vẫn áp cho bảng chính + Results.
- **Buộc (số liệu đã verify 2026-08-12)**: ADDIE dẫn ở **3/4 size, ngang react-isd tại 9B** (mean −0.08 ns) — mọi chỗ
  trong paper KHÔNG được viết "dẫn ADDIE mọi size" theo mean; Trajectory thua react-isd VÀ ADDIE-Agent mọi size (không
  viết "chỉ thua react-isd"); coverage 38% = hệ tệ nhất, tính theo (scenario, run) có sinh artifact.
- **Buộc**: RQ2 phát biểu ở mức "tín hiệu đo được của alignment", không phải "đo được alignment" (mục 8.1).
- **Cấm**: nới phạm vi ra "SLM nói chung" — kết luận chỉ ở "trên dải Qwen 0.8B–9B" (mục 11).
- **Cấm**: mọi biến thể của claim "tiết kiệm chi phí" (mục 10.4).
- **Cấm** (đề cương): tài liệu tham khảo, bảng/hình, công thức, tuyên bố chưa chứng minh, từ quảng bá.

## 3. Keywords

4–7 từ: instructional systems design, multi-agent LLM, constructive alignment, small language models, ADDIE, benchmark
evaluation. Không lặp nguyên cụm của title.

## 4. Introduction — `01_introduction.tex`

> **CẤU TRÚC (cập nhật 2026-08-29 — lean: MỘT gap, MỘT đóng góp; thay khối 2026-08-12):** 4 khối kinh điển:
> (1) **Bối cảnh chung** — giới thiệu lĩnh vực + tầm quan trọng: LLM thương mại hỗ trợ tốt ISD end-to-end (có cite
> củng cố; mức claim: chất lượng "tiệm cận, một số thiết lập ngang bằng Ở CẤP THÀNH PHẦN" — không claim parity cho
> trọn bộ chương trình), rồi vấn đề triển khai — API bên thứ 3, chi phí cao, rủi ro an toàn dữ liệu (có cite;
> **mức claim CHỐT 2026-08-12: "được ghi nhận là rào cản triển khai" — KHÔNG viết "gây khó khăn lớn"**, evidence chỉ
> đỡ mức documented-barrier; caveat cite: zesch2024flexi không dùng cho vế privacy), dẫn tới hướng SLM on-premise,
> rồi KẾT bằng **nấc alignment** (chốt 2026-08-29): (i) burden-shift — model nhỏ đi thì gánh nặng chất lượng dịch
> chuyển sang hệ bao quanh, decomposition là lối ra có literature đỡ nhưng KHÔNG đơn điệu (`cho2026harness`) nên
> phải đo; **KHÔNG viết "chất lượng phụ thuộc vào MAS"** — MAS chỉ xuất hiện từ phần method trở đi; (ii) cái khó
> của ISD trọn gói là constructive alignment — chất lượng nằm ở quan hệ objective↔activity↔assessment; hệ hiện có
> để coherence này NGẦM trong model (văn xuôi + context); khả năng tự giữ nhất quán dài hơi là thứ **kỳ vọng** suy
> giảm trước khi model nhỏ đi (mức claim: expectation có cơ sở, không phải định luật) → alignment vỡ trước, theo
> kiểu "đọc mượt nhưng lệch" (câu fluent-but-misaligned kéo từ đoạn measurement cũ lên đây);
> (2) **Khoảng trống nghiên cứu** — **MỘT gap duy nhất, thuần thiết kế** (2026-08-29; gap đo lường cũ bị hạ khỏi
> hàng gap): hệ hiện có xây/kiểm chứng trên model thương mại mạnh, và không hệ nào trong số khảo sát biểu diễn quan
> hệ objective–activity–assessment thành trạng thái tường minh kiểm được (claim khảo sát được về văn liệu); **dạng
> phát biểu giữ nguyên chốt 2026-08-12: claim-về-công-trình ("chưa có công trình nào cho thấy…"), KHÔNG
> claim-về-hệ**; cite danger papers;
> (3) **Aim + objectives** — aim mang câu cầu nối (từ 4.5): thay vì trông vào model tự giữ nhất quán ngầm, hệ duy
> trì quan hệ alignment thành trạng thái tường minh mà model cỡ nào cũng kiểm được; 4 objectives giữ nguyên
> (objective 3 = alignment panel, phát biểu như objective ĐÁNH GIÁ, không phải đóng góp);
> (4) **Đóng góp (MỘT — mục 4.6) + preview đánh giá 2–3 câu + đoạn cấu trúc bài (4.7)** — phép đo alignment justify
> như **instrument requirement sinh từ chính claim** (judge không lộ được quan hệ alignment; phép đo sẵn có cần bộ
> chuẩn tiền-soạn mà thiết kế máy sinh không có → lắp tín hiệu deterministic từ tiêu chí established, đặc tả ở
> Experimental Design §Measures); **KHÔNG claim novelty của phép đo, KHÔNG gọi nó là protocol/method/đóng góp** —
> văn phong "we assemble/operationalize established criteria".
> Khối "ý tưởng & phương pháp" (4.5 cũ) không còn là khối riêng trong intro — tiền đề decomposition + demarcation
> vẫn BUỘC ở Method; riêng CÂU CẦU NỐI (giả thuyết ngoại hiện hoá coherence) phải có mặt trong khối (1)/(3) dạng
> nén, nếu không gap→method thành non sequitur. Các mục 4.1–4.5 dưới đây giữ làm kho nội dung/ràng buộc, không còn
> là dàn bài intro.

**4.1–4.2 Bối cảnh & vấn đề.** LLM thương mại sinh được chương trình giảng dạy chất lượng cao, nhưng chi phí suy luận,
phụ thuộc API và việc chuyển dữ liệu người học qua bên thứ ba cản trở triển khai tại cơ sở giáo dục. Open-weight SLM
triển khai tại chỗ là cân bằng thực tế hơn (chất lượng / chi phí / kiểm soát dữ liệu) — nhưng model nhỏ đi thì gánh
nặng chất lượng dịch chuyển từ model sang **hệ bao quanh nó** (phân rã, điều phối, kiểm soát chất lượng), và thứ lâm
nguy trước tiên là constructive alignment, vốn đang được model tự duy trì ngầm (sửa 2026-08-29 — không viết "phụ
thuộc vào MAS": premise phải trung tính, MAS là giải pháp).

**4.3–4.4 Hạn chế nghiên cứu trước & khoảng trống** (chi tiết ở mục 5; từ 2026-08-29 chỉ còn MỘT gap):

1. Nghiên cứu ISD/lesson-plan tập trung tự động hoá, cá nhân hoá, chất lượng trên model mạnh; không hệ nào biểu diễn
   quan hệ objective–activity–assessment thành trạng thái tường minh kiểm được trong lúc sinh; **duy trì chất lượng
   khi thu nhỏ model nền chưa được nghiên cứu như một mục tiêu thiết kế + đánh giá** của hệ tác tử ISD.
2. *(Hạ cấp 2026-08-29 — không còn là gap/đóng góp, chỉ là **justification cho instrument** trong Experimental
   Design và Related Work §5.3):* benchmark hiện có chấm chủ yếu bằng LLM-judge rubric (bias hệ thống, cùng họ với
   generator, không lộ quan hệ alignment); đo alignment tự động sẵn có (Porter/Webb, embedding item↔standards) cần
   **bộ chuẩn tiền-soạn** mà thiết kế do máy sinh không có → phải lắp tín hiệu deterministic từ tiêu chí established
   để chấm chính thiết kế được sinh. KHÔNG phát biểu các câu này dưới dạng gap-claim ("chưa ai…", "không benchmark
   nào tích hợp…") ở bất kỳ đâu trong paper.

**4.5 Ý tưởng & phương pháp** (nén — lập luận đầy đủ ở mục 7):

- Ràng buộc triển khai → SLM → SLM yếu ở tác vụ mở, đa ràng buộc → hướng cấp MAS: **thu hẹp tác vụ mỗi lời gọi model
  phải gánh** (phân rã theo mối quan tâm ISD).
- Tiền đề "tác vụ hẹp nằm trong tầm với model yếu hơn tác vụ rộng" **kế thừa từ literature** (`zhou2023leasttomost`,
  `khot2023decomposed`, `ferraz2024decrim`, `shen2024multillmagent`, `belcak2025slm`), **không phải claim nghiên cứu này
  kiểm** — không có arm single-agent, phân rã là nền của mọi arm.
- **Cấm**: viết như thể literature bảo chứng vế mạnh hơn "lợi ích phân rã lớn dần khi model nhỏ đi" — `cho2026harness`
  cho kết quả không đơn điệu; quan hệ đó là **thứ được đo** (RQ1b, DiD).
- Phân rã sinh vấn đề mới: các mảnh phải nhất quán với nhau — trong ISD, chính là **ăn khớp sư phạm** → cần substrate
  chung, lược đồ do constructive alignment (Biggs–Tang) định hình → **alignment graph**. Giả thuyết: MAS tổ chức
  sinh quanh trạng thái tường minh này giảm phụ thuộc vào khả năng tự duy trì nhất quán của model — khả năng suy giảm
  khi model nhỏ đi.

**4.6 Đóng góp** (CHỐT 2026-08-29: đúng **MỘT** đóng góp — hạ "evaluation protocol" khỏi hàng đóng góp theo hướng
paper lean; thay chốt HAI đóng góp 2026-08-11. Ladder 4 size × 3 run + SD giữa run vẫn là đặc điểm rigor của
methodology (mục 8.3, 9.7), nêu trong câu preview thực nghiệm, KHÔNG đánh số đóng góp):

1. **AlignmentGraph-ISD** — MAS với alignment graph là trạng thái alignment tường minh, kiểm được, audit
   được, cho sinh chương trình ADDIE.

Phép đo alignment không-LLM: trình bày trọn trong mục 8.6 (Experimental Design §Measures) như **measurement setup**
— văn phong "assemble/operationalize established criteria", không claim novelty, không đánh số đóng góp, không có
đề mục "protocol" trong Method. Đặc tả kỹ thuật + mức claim vẫn theo `docs/rq2_protocol.md` (file đó là spec nội
bộ; positioning trong paper đã hạ cấp — xem note đầu file đó). Nếu sau này nhắm venue khác muốn nâng lại thành
đóng góp: nâng ngược từ 8.6 lên, spec không đổi.

**4.7 Cấu trúc bài** — một đoạn, bắt buộc.

## 5. Related Work — `02_related_work.tex`

Tổ chức theo nhóm, không liệt kê từng bài:

- **5.1 Nền**: constructive alignment (Biggs–Tang), Quality Matters, Porter/Webb alignment indices, Bloom taxonomy (A&K
  2001).
- **5.2 Hệ tác tử ISD / lesson-plan generation**: ISD-Agent-Bench và các agent của nó; các hệ sinh chương trình bằng
  LLM.
- **5.3 Gần nhất với đề xuất**: Small Models Big Support (SLM cục bộ hỗ trợ biên soạn), LessonPlanLM (fine-tune 7B),
  Instructional Agents (báo cost nhưng vẫn API thương mại); precedent đo alignment bằng LM/embedding (arXiv 2510.05129);
  BERT-Bloom classification (Li et al. 2022 EDM; BloomBERT chỉ là related work). Phạm vi khảo sát:
  `docs/paper/refs-deployment-survey.md`.
- **5.4 Bảng so sánh + vị trí đề xuất** (sửa 2026-08-29 theo hướng MỘT gap): bảng positioning theo tiêu chí **hệ**
  (ISD end-to-end / Local SLM / Scale / Explicit alignment state) — bỏ hai cột đo lường (Intr./Bench) và hai hàng
  measurement-only; synthesis nêu MỘT unresolved combination (hệ ISD on-premise đánh giá theo dải size + trạng thái
  alignment tường minh), dẫn thẳng tới phương pháp. Mảng đo lường (5.3) giữ nguyên trong prose làm justification
  cho instrument của 8.6, không claim gap.
- **Cấm**: tuyên bố đề xuất *tốt hơn* trong Related Work; phát biểu gap-claim cho phép đo ("chưa ai đo…", "không
  benchmark nào tích hợp…").

## 6. System Model & Problem Formulation — GỘP VÀO `04_method.tex` (2026-08-11)

> File `03_problem_formulation.tex` đã bỏ; nội dung mục này tinh giảm và trở thành phần mở đầu của mục 7 (Method):
> giữ hình kiến trúc (`fig:architecture`), predicate `aligned(o)` (`eq:aligned`) và deployment envelope
> (`sec:assumptions`) — ba thứ load-bearing; ký hiệu rút gọn tối đa (bảng notation bỏ được nếu thừa, kèm dọn hết
> tham chiếu); problem statement + challenges nén thành một đoạn dẫn vào MAS.

- **6.1** Kiến trúc hệ: meta-agent LangGraph + specialist agents (
  needs/objective/assessment/activity/implementation/evaluation) + verifier + aggregator; hình kiến trúc tổng thể.
  **Positioning "đa tác tử" (chốt 2026-08-26)**: gọi đúng loại hệ là **workflow-style / role-decomposed multi-agent**
  (họ SOP-style như MetaGPT: điều phối tĩnh, không negotiation/dynamic planning — nói rõ, không claim quá). Hai cơ chế
  cấu thành tính multi-agent, nêu tường minh trong §6.1: (1) **role specialization** — mỗi specialist một persona +
  phạm vi artifact riêng; (2) **scoped state access** — mỗi agent chỉ đọc/ghi phần trạng thái thuộc phạm vi mình
  (graph-context injection).
- **6.2–6.4** Ký hiệu: đồ thị node kiểu `objective/activity/material/assessment/implementation/evaluation`, edge kiểu
  `measures/supports/evaluates`; predicate **`aligned(o)` 3 vế** (measures/supports/evaluates) — RQ2 protocol map thẳng
  vào 3 vế này.
- **6.3 Giả định + deployment envelope**: target triển khai là **một GPU 12–16 GB** (thứ cơ sở giáo dục thực có) → bf16:
  0.8B ~1,6 GB, 2B ~4 GB, 4B ~8 GB, **9B ~18 GB không vừa** → 4B là model lớn nhất vừa target → phần VRAM còn lại cho KV
  cache → **ngân sách ~8k token/lời gọi**. Chuỗi suy luận này kiểm được, đứng độc lập với thứ tự thời gian; 9B là mốc
  tham chiếu ngoài target, không phải cấu hình đề xuất.
- **6.5–6.6** Phát biểu bài toán + thách thức (tác vụ mở đa ràng buộc trên model yếu; nhất quán liên-artifact).

## 7. Proposed Method — `04_method.tex`

- **7.1** Tổng quan: alignment graph là cấu trúc dữ liệu trung tâm — substrate mà phân rã và điều phối vận hành trên đó;
  hình + lưu đồ.
- **7.2–7.3** Thành phần (mỗi cái gắn một hạn chế ở Introduction):
    - **Graph-context injection**: specialist chỉ cập nhật phần trạng thái thuộc phạm vi mình; chính **phân rã có ràng
      buộc** này (không phải bản thân cấu trúc đồ thị) tạo liên kết bắt buộc ngay khi sinh.
    - **Verifier**: sau mỗi lượt cập nhật, kiểm phù hợp sư phạm/nhận thức ở mức nội dung + LLM repair.
    - **Graph dump**: cuối run xuất JSON đầy đủ node/edge/state + Graphviz DOT, tách khỏi trajectory — hiện thực hoá "
      explicit and auditable" thay cho tuyên bố "aligned by construction"; educator kiểm được từng mục tiêu đo bởi đánh
      giá nào, can thiệp/override khi cần (educator-in-the-loop).
    - **Trần số mục tiêu học tập (ILO ceiling, 2026-09-10)**: harness tính một con số từ chính design brief và
      đưa vào rules của stage `outcomes`. Công thức là `per_goal(context.duration) × len(learning_goals)`, với 2/3/4
      cho ngắn/vừa/dài. Trên 90 scenario của test_90, trần rơi vào 6/8/9/12/16. Hai trường `class_size` và
      `difficulty` cố ý không nằm trong công thức. Số học viên đổi cách triển khai khoá học chứ không đổi số mục tiêu.
      `difficulty` mô tả ràng buộc của đề bài, phân bố 30/30/30 và độc lập với duration, nên nó không đo khối lượng
      nội dung. **Trần chỉ được thông báo, không được cưỡng chế**: không có cơ chế nào cắt bớt danh sách dài hơn.
      Vì vậy `metadata.objective_ceiling` ghi lại trần, số thực tế và cờ `respected`, và **tỷ lệ tuân thủ mới là
      kết quả cần báo cáo**. Lý do phải nêu trong Method: đây là ràng buộc harness đặt lên quyền tự quyết của agent,
      có ở cả bốn arm alignmentgraph và không có ở sáu baseline.
- **7.5** Pseudocode quy trình ISD cố định.
- **7.7** Khác biệt với baseline gần nhất (react-isd, addie-agent…): trạng thái alignment tường minh dùng chung vs. văn
  xuôi/trajectory ngầm.
- **7.8 — BỎ (2026-08-29, đảo chốt 2026-08-11)**: Method KHÔNG có đề mục evaluation protocol. Toàn bộ phép đo
  alignment (panel 7 tín hiệu, hai họ instrument, naming rule, mức claim "tín hiệu đo được") nằm trong mục 8.6
  (Experimental Design §Measures) như measurement setup — xem 4.6 và 8.6. Method chỉ giữ predicate `aligned(o)`
  (`eq:aligned`) mà phép đo map vào.
- **Phân định kiểm/kế thừa (buộc phải có)**: nghiên cứu kiểm **substrate** (graph-context + verifier, tách bằng
  ablation); **không** kiểm decomposition (tiền đề có nguồn, mục 4.5); ai muốn số riêng cho decomposition → future work
  arm monolithic (mục 12).

## 8. Experimental Design — `05_experimental_methodology.tex` (đổi tên section 2026-08-11, tên file giữ nguyên)

**PHÁT BIỂU CƠ CHẾ BA TẦNG (chốt 2026-08-13, sửa theo comment reviewer):** ablation KHÔNG giải thích được khoảng
cách RQ1 (lợi thế ADDIE còn nguyên khi tắt graph context) — cấm mọi câu gán khoảng cách ADDIE cho graph/verifier.
Ba tầng tách bạch: (1) **phân rã** (chưa ablate) → robustness + khoảng cách ADDIE, chỉ ở cấp hệ thống, chưa quy
nhân quả; (2) **graph context** (đã ablate) → các tín hiệu alignment; (3) **verifier** → không mua được cải thiện
đo được, phần lớn kích thước còn giảm Trajectory; vai trò backstop + audit. Kèm 2 disclosure buộc ở RQ1: delta
ADDIE không đồng đều (0.8B vs dick-carey ns; 4B +0.80; 9B −0.08 ns) và delta +34/+33 vs baseline/eduplanner ở 0.8B
là artifact của failure rate (n=5–7 complete-case), không phải khoảng cách chất lượng.

**8.1 RQ** — mỗi câu một nhóm thí nghiệm, hai vế RQ1 **đồng hạng** (co-primary). **Nhãn (user 2026-08-12): paper
KHÔNG dán nhãn "RQ1a/RQ1b"** — RQ1 phát biểu một câu gộp hai vế (mức + khoảng cách nới rộng khi thu nhỏ); phần thống
kê vẫn tách hai phép phân tích (per-size + DiD) nhưng gọi là "hai vế của RQ1".
**Phát biểu RQ chốt lại 2026-08-12 (gap–RQ–experiment align, bản VN):** narrative intro = MỘT khoảng trống trung tâm
(duy trì chất lượng khi thu nhỏ) → RQ1 dùng đúng từ khoá "duy trì chất lượng"; bài toán đo lường NẢY SINH khi trả lời
RQ1 (LLM-judge bias + human-eval không scale + không cách nào làm tường minh tín hiệu alignment — thiết kế "nhìn qua
có vẻ tốt" vẫn có thể hỏng alignment, khung CA) → giao thức → **RQ2 nhúng instrument trong câu hỏi** ("Khi được làm
tường minh bằng giao thức đo không dùng LLM, các tín hiệu alignment nội tại... thay đổi thế nào theo kích thước
model, và khoảng cách so sánh có nới rộng khi model nhỏ đi không?"). Không còn "hai khoảng trống" trong intro:

- **RQ1a (mức)**: tại mỗi size Qwen 0.8B–9B, chất lượng AlignmentGraph-ISD vs. đối sánh? → paired Wilcoxon per-size.
- **RQ1b (độ dốc)**: khoảng cách có nới rộng khi model nhỏ đi? → interaction `method × size` (bootstrap DiD,
  largest−smallest). Chỉ báo RQ1a thì vế "khi thu nhỏ" không được trả lời bởi test nào.
- **RQ2**: các *tín hiệu đo được* của constructive alignment diễn biến thế nào theo size, khoảng cách có nới rộng
  không? — phát biểu cố ý dừng ở "tín hiệu đo được", không phải "đo được alignment" (validate construct cần expert
  study).

**8.2 Dữ liệu**: `test_90` của ISD-Agent-Bench (90 scenario, stratified, seed 42); 6 tác tử đối sánh.

**8.3 Thiết lập**: 4 size Qwen cùng họ × **3 run độc lập**; 2 judge độc lập, điểm mỗi scenario = trung bình 2 judge (quy
ước benchmark); agent/judge model tách riêng chống self-preference. Serving: vLLM trên RunPod, 3 cờ bảo vệ uniform mọi
agent.

- **Trần token — câu chuẩn nguyên văn cho methodology**: *"we cap generation at 8192 tokens per call — the budget a 4B
  model leaves on a single 12–16 GB GPU, the deployment target this work claims. The 24–32 GB pods were rental
  convenience for running the ladder in parallel, not the claimed envelope."* Tương tác trần×kiến trúc là **thứ được đo,
  không phải confound phải xin lỗi**: "phân rã giữ mọi lời gọi cách xa giới hạn serving" là một tính chất triển khai.
- **Can thiệp duy nhất lên một baseline (buộc khai)**: prompt scaffolding của ReAct-ISD dịch sang tiếng Anh (chỉ đổi
  ngôn ngữ, không đổi phương pháp) — ngôn ngữ corpus đồng nhất tiếng Anh **bằng thiết kế** (scenario + prompt cả 7
  agent), không bằng chỉ thị.

**8.5 Đối chứng**: 6 agent benchmark + **3 arm ablation của chính đề xuất** (đúng yêu cầu "phiên bản đơn giản hoá" của
đề cương): −Verifier, −GraphContext, skeleton — chạy như 4 agent **bên trong chính các run ladder** (cùng judge
session → delta arm−A0 không nhiễm judge drift; A0 in-session đối chiếu 3 run ladder làm consistency check).

**8.6 Chỉ số**:

- **RQ1**: ba tín hiệu judge báo song song, thống kê y hệt nhau, hiện ngang nhau ở abstract + bảng chính —
  `addie_median` (dẫn narrative: đo đúng construct của RQ1), `trajectory_score` (tuân thủ quy trình — construct khác),
  `total_score` (0.7/0.3 là trọng số của benchmark, giữ để so được với cách báo của ISD-Agent-Bench).
- **RQ2** (2026-08-29 — 8.6 là NƠI DUY NHẤT trong paper trình bày phép đo, sau khi bỏ 7.8): mở đầu bằng
  justification instrument (judge bias + không lộ quan hệ alignment; phép đo sẵn có cần bộ chuẩn tiền-soạn), rồi
  toàn bộ đặc tả: panel 7 tín hiệu phẳng không endpoint, hai họ instrument (A: mean-max rectified cosine; B:
  Porter/Webb + Bloom), không LLM / không threshold, naming rule, mức claim ("tín hiệu đo được", không "đo
  alignment"), phần vận hành (chấm offline, preset encoder/Bloom, sensitivity star, quy tắc đọc panel ≥4/6, failure
  layer). Văn phong: measurement setup — "the measurement", không "the protocol"/"our protocol"; kèm câu chuẩn:
  *"quy trình chấm không dùng LLM và không có thành phần ngẫu nhiên; kết quả tái lập được nhờ pin phiên bản encoder
  và cache embedding"*. Đặc tả đầy đủ: [`docs/rq2_protocol.md`](rq2_protocol.md).
- Cost: token_usage per agent×size (chỉ đọc `metadata.token_usage.*` — bẫy artifact xem mục 9.6).

**8.7 Thống kê**:

- Paired Wilcoxon per-scenario trên mean-of-3-runs (**exact permutation null khi n≤25**), Holm với family tường minh = 6
  so sánh/size (RQ2 thêm Holm panel-wide ở footnote), bootstrap 95% CI (10k, seed 42), rank-biserial; DiD cho vế scale.
- **Failure policy — layer chính = `failure=0`, complete-case là sensitivity** (cả RQ1 lẫn RQ2): agent crash → không có
  output file → scenario rơi khỏi tập ghép cặp = **điều kiện hoá trên biến hậu-treatment** (crash rate khác nhau theo
  agent×size, loại đúng scenario baseline thua nặng nhất, mạnh nhất ở model nhỏ — đúng nơi giả thuyết sống). Không sinh
  được output **là** chất lượng 0, không phải missing data. Báo kèm: complete-case, `failure=min` (chỉ RQ1),
  failure-rate riêng (Fisher exact). Complete-case **không bao giờ được gọi là unconditional**.

**8.8 Tái lập**: số sinh tự động từ artifact; encoder revision pin + embedding cache; kết quả trước pivot không dùng.

## 9. Results — `06_results.tex`

*(Chỉ hình dạng + thứ tự narrative; số đọc từ `docs/generated/`. Trình tự mỗi RQ: quan sát → nguyên nhân → ý nghĩa →
ngoại lệ.)*

**9.1–9.2 Theo RQ:**

1. **Robustness theo scale** — hệ đề xuất ra output dùng được 100% scenario mọi size; hệ không scaffold hỏng phần lớn ở
   model nhỏ (Fisher + Holm). **Nguyên nhân failure phải nói theo từng hệ**: 100% failure của `baseline` là
   `LengthFinishReasonError` đúng tại `completion_tokens = 8192`; EduPlanner là lỗi parse schema — khác cơ chế. Với trần
   đã biện minh theo envelope (mục 6.3), đây là **kết quả deployability, không phải caveat**: trong ngân sách token một
   GPU 12–16 GB cho phép, agent một-lượt không hoàn thành thiết kế ở model nhỏ, hệ phân rã giữ mọi lời gọi ~1,6k token
   nên không chạm trần. Vẫn báo truncation rate per agent×size (`stats_cost.md`).
2. **Điểm judge (RQ1a)** — vượt các hệ quy trình cùng lớp mọi size, dẫn `addie_median` mọi size. **Ghi nhận trung thực
   đặt ngay trong results**: tương đương react-isd ở model lớn; **thua một đối sánh ở size nhỏ nhất trên `total_score`**
   dù dẫn ADDIE + alignment. Ba tín hiệu hiện ngang nhau nên người đọc tự đánh giá được ô này; lý do ADDIE dẫn
   narrative (construct match) đứng độc lập với kết quả.
3. **Scale (RQ1b)** — lợi thế co lại có ý nghĩa khi model lớn lên (DiD, cả ba tín hiệu); failure differential tập trung
   ở model nhỏ; ô complete-case n nhỏ không kiểm định được — chính là lý do layer chính failure=0.
4. **Alignment (RQ2)** — dẫn mọi size theo **quy tắc đọc panel pre-specified** (`rq2_protocol.md` §4: ≥4/6 tín hiệu định
   hướng dương sau Holm, không tín hiệu định hướng nào âm có ý nghĩa), rõ nhất ở `objective_assessment_similarity`;
   khoảng cách nới rộng khi model nhỏ đi (interaction âm).

**9.3 Ablation** — graph-context là cơ chế giữ alignment (trên panel RQ2), verifier là backstop + nguồn audit trail;
0 output failure mọi arm → robustness đến từ decomposition, không từ hai cơ chế bị ablate. Hình dạng
judge-bất-biến/alignment-dịch → hai cách đọc bắt buộc, mục 10.

- **Buộc**: mỗi phát biểu nói rõ đang đứng trên **họ tín hiệu nào** — ADDIE (judge) và panel RQ2 cho hai kết luận khác
  nhau, và đó là phát hiện, không phải mâu thuẫn cần giấu.
- **Cấm** "graph-context mạnh nhất ở model nhỏ" và "skeleton rớt sâu hơn −GraphCtx mọi size" — cả hai không đỡ được
  (rà 2026-08-10). Muốn nói về scale thì nói theo tín hiệu cụ thể.
- **Cấm** claim verifier có hiệu ứng điểm trên cấu hình được ship.

**9.4 Sensitivity** — thứ hạng (chiều so sánh theo cặp, KHÔNG phải ρ của thứ tự đầy đủ 7 hệ) giữ nguyên qua **3 trục** (
encoder-independence, sàn TF-IDF, Bloom BERT↔lexicon — `rq2_protocol.md` §6) và qua lát cắt complete-case.

**9.6 Cost/scalability** — ~22k token, 8 lời gọi cho một thiết kế ADDIE ở 2B/4B trên một GPU 24 GB; chi phí
phẳng-đến-giảm theo scale. Nhưng **1,1–1,7× baseline trung vị**, **2,7–4,0× baseline rẻ nhất chạy trọn (react-isd)**;
token/điểm ADDIE: đáng ở 0.8B–2B, tệ ở 4B, **lỗ ở 9B** (react-isd ngang-hơn với chi phí 1/3,6). Overhead theo thành
phần (từ arm ablation): verifier +0,6–2,5% token; graph-context **+25–31% tổng** (+58–78% prompt) — cơ chế đắt nhất, và
đóng góp nhiều nhất **trên panel RQ2**. **Caveat coverage**: cột chi phí của `baseline`/`eduplanner` là **số của
người sống sót** (ca đắt bị cắt cụt) — so sánh chi phí chỉ dùng đối sánh coverage đầy đủ. **Bẫy artifact**: `metadata.cost_usd` sai (giá API
thương mại trên pod tự host); `metadata.total_tokens` top-level = 0 với 6/10 agent — chỉ đọc `token_usage.*`; wall-clock
là **throughput có xếp hàng, không phải latency** (150 thiết kế in-flight) — không được gọi là latency.

**9.7** Mean ± SD giữa run cho mọi ô; **SD phải cùng tín hiệu với mean** (`RQ1_SD_FIELD`); ô nào n < 90 phải có
footnote.

## 10. Discussion — `07_discussion.tex`

- **10.1 Diễn giải**: cơ chế nào quan trọng (graph-context theo ablation, trên panel RQ2 — giới hạn câu chữ ở 9.3);
  khớp giả thuyết (lợi thế lớn nhất ở model nhỏ). **Cấm** trộn hai thứ này trong một câu: "lợi thế lớn nhất ở model
  nhỏ" là claim hệ thống vs. baseline từ ladder (RQ1), KHÔNG phải gradient của ablation.
- **10.2** Không so trực tiếp số với nghiên cứu khác khi điều kiện thực nghiệm khác.
- **10.4 Ý nghĩa thực tiễn — motivation triển khai retarget**: luận điểm là *"chạy được và đáng chạy ở đầu nhỏ"*, *
  *không phải "rẻ hơn"**. Hai mặt cost cùng hình dạng với DiD của RQ1 (lợi thế co khi model lớn). **Câu không bao giờ
  được viết**: bất kỳ biến thể nào của "hệ chúng tôi tiết kiệm chi phí". Định vị: decision support cho chuyên gia ISD,
  educator-in-the-loop, graph dump là cơ chế audit/override phục vụ định vị này — không thay thế chuyên gia.
- **10.5 Phân tích thất bại (bắt buộc, chống cherry-picking)**:
    - Thua ở size nhỏ nhất trên `total_score`; react-isd ngang-hơn ở 9B với chi phí thấp hơn nhiều.
    - **Judge gần bất biến giữa các arm ablation trong khi alignment dịch rõ — phải trình bày cả hai cách đọc**: (thuận)
      LLM-judge không nhạy với alignment, đúng lý do tồn tại của RQ2 protocol; (ngược) instrument duy nhất phân biệt
      được các arm chia sẻ construct với chính thiết kế bị ablate, còn instrument độc lập cơ chế không thấy hiệu ứng =
      mô tả của **thiếu discriminant validity**. Cần một dự đoán phân biệt hai cách đọc nêu **trước** khi kiểm (
      `docs/review_q2.md` R2).

## 11. Threats to Validity — SUBSECTION CUỐI CỦA DISCUSSION trong `07_discussion.tex` (2026-08-11; file 08 bỏ)

- **Trần ILO là ràng buộc chỉ có ở hệ đề xuất (2026-09-10)**: bốn arm alignmentgraph được cho biết một trần số mục
  tiêu suy ra từ brief; sáu baseline không có. Trần đẩy số mục tiêu xuống, nên mọi tín hiệu panel tính trung bình
  trên tập mục tiêu đều được tính trên một tập bị chặn ở phía hệ đề xuất và không bị chặn ở phía baseline. Phải nói
  rõ điều này. Mức claim phải hẹp đúng cơ chế: agent được cho biết một trần, không có gì cưỡng chế nó, và tỷ lệ tuân
  thủ được báo cáo kèm. Đo trên 63 run đã có, trung vị là 4 mục tiêu và trần chỉ chạm khoảng 11% đuôi trên.

Mỗi nguy cơ kèm mitigation:

- **Internal**: trần 8192 tương tác với kiến trúc → biện minh theo envelope kiểm được (mục 6.3) + báo truncation rate;
  can thiệp dịch prompt ReAct-ISD → khai tường minh; judge drift → alignment protocol không LLM + ablation cùng judge
  session.
- **External**: **một họ model** — 4 size Qwen chia sẻ công thức pretraining nên hiệu ứng scale **lẫn với recipe nội bộ
  họ**; kết luận phát biểu ở "trên dải Qwen 0.8B–9B", ngoại suy sang Llama/Gemma/Phi là giả thuyết. Nêu đúng một lần, *
  *không nới ở abstract/conclusion**.
- **Construct**: **similarity không phải alignment** — 4 tín hiệu họ A đo textual correspondence, cầu sang construct nằm
  ở tầng bằng chứng, không ở tên metric; `assessment_objective_similarity` không đơn nghĩa; Bloom arm chính là
  checkpoint học từ quy ước một trường — không truy được về A&K từng ca, chưa validate trên objective máy sinh;
  classifier/encoder error có thể **differential** → ranking có thể đổi, mitigation = 3 trục sensitivity. Chi tiết:
  `rq2_protocol.md` §7.
- **Conclusion**: n=90 paired, 3 run/ô, exact test ở n nhỏ, Holm hai tầng; khai thời điểm chốt các lựa chọn phân tích
  (failure policy, quy tắc đọc panel — đều pre-specified trước khi đọc kết quả RQ2).

## 12. Limitations & Future Work — CÙNG SUBSECTION VỚI MỤC 11 trong `07_discussion.tex` (2026-08-11; file 08 bỏ)

Mỗi hướng tương lai xuất phát từ một hạn chế:

- Không có arm single-agent → **arm monolithic cùng package, cùng ngân sách token** (tách số cho decomposition).
- Validity bridge chưa có nhịp con người → **expert study Tier 3** (2 chuyên gia blind-code, κ máy-vs-người; để dành
  ETR&D).
- Protocol không đo learning outcomes; chỉ đo dấu hiệu văn bản.
- Sensitivity trần token cao hơn (tuỳ chọn, `docs/review_q2.md` R4) — preempt câu hỏi "cấp trọn 24 GB thì sao".

## 13. Conclusion — `09_conclusion.tex`

6 bước của đề cương; giới hạn kết luận **hai mức**: claim hệ thống (vs. baseline, từ ladder) và claim cơ chế (từ
ablation: graph-context có ý nghĩa mọi size trên panel RQ2, kèm caveat ADDIE bất biến — mục 9.3; verifier backstop)
— claim về decomposition chỉ ở mức hệ thống. **Cấm**:
đưa claim/kết quả mới; nới phạm vi họ model.

## 14. Declarations

Theo yêu cầu venue (TLT chính, EAIT fallback). Data/Code availability: repo + artifact sinh tự động. Tác giả:
`docs/authors.md`.

## 15. References

Checklist citation của RQ2 protocol: `rq2_protocol.md` §8. Tiền đề decomposition đã có trong `references.bib` (
zhou/khot/ferraz/shen/belcak + cho2026harness cho vế không đơn điệu). Mọi ref trong bib đều được cite và ngược lại.
