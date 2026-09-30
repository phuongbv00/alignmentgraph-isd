# Backlog hoàn thiện manuscript Q2

Backlog canonical cho các việc phải làm trước khi nộp Q2. Nguồn: góp ý của GVHD 2026-08-17 (`Góp_ý_Phương.docx`), nhận xét sau Sprint 1 nhận 2026-09-10 (`feedbacks/sprint1_20260828_0908/`) và nhận xét Sprint 2 nhận 2026-09-28 (`feedbacks/sprint2_20260928/`). Khi các nguồn lệch nhau thì nguồn mới hơn thắng; nhận xét Sprint 2 thay thế thiết kế thí nghiệm của Sprint 1.

Trạng thái: `[ ]` chưa làm, `[~]` đang làm, `[x]` xong, `[?]` chờ quyết định.

## Nhóm R — backlog cũ (tái lập nhãn)

- [x] **R1 — Cost framing retarget.** Giữ motivation triển khai nhưng đổi luận điểm thành "chạy được và đáng chạy ở đầu nhỏ". Cấm mọi biến thể của claim "rẻ hơn". Đã áp vào `06_results.tex`.
- [ ] **R2 — Prediction pre-specified cho hai cách đọc ablation.** Kết quả hiện tại: LLM judge gần bất biến giữa các arm ablation trong khi alignment panel dịch rõ. Hai cách đọc: (thuận) LLM judge không nhạy với alignment; (ngược) thiếu discriminant validity của panel. Phải ghi một dự đoán phân biệt hai cách đọc **trước** khi có nhãn chuyên gia. Dự đoán chưa có chỗ ghi cố định — viết vào `docs/paper/claim-rules.md` (mục phải khai) trước khi chạy `isd-exp expert sample`.
- [~] **R3 — Expert study.** Trùng với T12 dưới đây; công cụ là `isd-exp expert sample` / `aggregate` (`experiments/src/isd_experiments/expert/`). Vòng tối thiểu (3–5 chuyên gia × 12 scenario) phục vụ bài Q2; bản đầy đủ (blind-code theo thủ tục gốc, κ máy-vs-người) để dành hướng ETR&D.
- [?] **R4 — Sensitivity trần token cao hơn.** Chạy thêm một cấu hình với token cap cao hơn 8192 để preempt câu hỏi "cấp trọn 24 GB thì sao". Bị chặn trước đây vì 100% failure của baseline là truncation tại 8192. Là thí nghiệm mới, nằm ngoài lộ trình Sprint 1; chỉ chạy nếu thầy mở thêm scope.

- [x] **R5 — Hình kiến trúc không khớp Algorithm 1.** Reviewer báo hình `figures/architecture.svg` phi logic so với thuật toán. Đối chiếu ba nguồn (hình / Algorithm 1 / `core/nodes.py:build_graph`) cho thấy code khớp thuật toán, hình mới là chỗ sai: hình cũ vẽ hub-and-spoke không có thứ tự thực thi, đặt verifier như cổng QC cuối, cho aggregator ăn output của verifier thay vì đọc G, giấu budget K và nhánh warning, và subgraph minh hoạ vi phạm chính Eq.(1) (hai cạnh *evaluates* không trỏ vào Objective nên objective chỉ có 2/3 facet). Đã vẽ lại hình theo đúng control flow của Algorithm 1 (chain 1–6, verify+repair cục bộ từng specialist, aggregate/audit sau vòng lặp) và sửa 3 chỗ Algorithm 1 lệch code: repair là patch có đích chứ không sinh lại cả phase; `verify` chỉ chạy trên checks specialist sở hữu nên `s_needs` không có QC node; `warn`/audit chạy một lần sau vòng lặp. Pass 2 cùng ngày soát tiếp hình mới với `core/alignment.py:REGISTRY` và `core/graph.py:NodeType`, bắt thêm 3 lỗi: hình bịa hai quan hệ không có trong 13 relation (Material→Activity, Implementation→Evaluation) — `implementation_plan` thực tế không tham gia relation nào nên đã bỏ khỏi hình; `tab:graph-spec` liệt kê 6 node type trong khi `NodeType` có 7 (thiếu `needs_context`, chính là nguồn của R1/R2) — đã sửa thành 7; và card 1 thiếu mũi tên read trong khi Algorithm 1 chạy `ctx ← C(s)` cho mọi `s` — đã thêm. Hình hiện chỉ vẽ quan hệ có thật.

  Lưu ý khi đọc lại mục này: nó ghi lại trạng thái 2026-08-21, trước khi pipeline LangGraph bị bỏ (2026-09-01). Tên module và số quan hệ trong đoạn trên không còn khớp code; hình phải soát lại với `core/alignment_graph/alignment.py::REGISTRY` khi vẽ lại cho kiến trúc hiện tại. Sửa 2026-08-21 trong `04_method.tex` + `figures/architecture.svg`. Pass 3: đổi sang bảng màu nhạt hợp tạp chí (slate `#3E5F7E` / ochre `#8A6A3B` / brick `#8C4B47` + xám), bỏ icon robot, và thêm **bản draw.io editable** `figures/architecture.drawio` làm master; pipeline build đổi thành **.drawio → export SVG → `generate_figures.sh` → PDF**: script mới chỉ làm SVG→PDF, tự chạy `drawio_labels.py` trên bản copy tạm để đổi label HTML (`<foreignObject>`) của draw.io thành SVG `<text>` vì không renderer SVG nào vẽ được foreignObject; quy trình ghi trong `figures/README.md`.

## Nhóm T — góp ý thầy 2026-08-17 (`Góp_ý_Phương.docx`)

### Định vị và metadata

- [x] **T1 — Title thêm "Auditable".** Title chốt: *AlignmentGraph-ISD: A Graph-Guided Multi-Agent Harness for Auditable Instructional Systems Design with Small Language Models*. Đã sửa `main.tex`.
- [x] **T2 — Author block chuẩn quốc tế.** Thứ tự: Viet-Phuong Bui (chính) / Van-Hai Pham* (liên hệ) / Van-Tam Bui. Dạng tên gạch nối. Đã sửa `docs/supervision/authors.md` + `main.tex`. Lưu ý: hỏi lại thầy về dấu * khi submit.
- [ ] **T3 — Template journal mục tiêu.** User chốt trong session này: tạm giữ ACM preprint vì chưa chốt hẳn journal. Thứ tự nộp dự kiến (scan 2026-08-17): ① EAIT (Springer sn-jnl) → ② Expert Systems (Wiley) → ③ IJIMAI. Khi chốt thì port template, giữ nguyên cơ chế số liệu sinh tự động từ `docs/generated/`.

### Nội dung bản thảo

- [x] **T4 — Sync ngược VN → EN.** Đã merge xong; bản VN xoá hẳn 2026-08-29. EN là bản chính duy nhất.
- [ ] **T5 — Claims sweep toàn bài theo quy tắc của thầy.** Cấm: "vượt trội toàn diện", "tốt nhất mọi chỉ số", "verifier cải thiện chất lượng đầu ra", "chứng minh constructive alignment đầy đủ". Dùng: robustness dưới SLM + token cap; ADDIE cạnh tranh, lợi ở model nhỏ, parity ở model lớn; graph context cải thiện *các tín hiệu đo được*; verifier = backstop + nguồn evidence audit. Đồng thời gỡ mọi mention RAG — paper không đề cập RAG (RAG chỉ thuộc luận văn).
- [ ] **T6 — Related Work theo 3 trục.** (1) LLM/AI agents for instructional design; (2) small/on-premise language models in education; (3) constructive alignment và alignment measurement.
- [ ] **T7 — Introduction định vị AI in Education.** Làm rõ vì sao bài thuộc AIED/EdTech, không chỉ LLM engineering: hệ hỗ trợ quyết định của instructional designer, không thay thế chuyên gia.
- [ ] **T8 — Method mapping thành phần → mức bằng chứng.** Decomposition → robustness; graph context → alignment signals; verifier → audit/backstop.
- [ ] **T9 — Results đọc cân bằng.** "Competitive and robust" thay cho "superior". Cost trade-off trung thực. Bảng lớn (full panel, sensitivity chi tiết, log thống kê) chuyển sang appendix/supplementary.
- [ ] **T10 — Discussion/Conclusion đối chiếu checklist thầy.** Implications for ISD; teacher-in-the-loop; khi nào ReAct/single-loop hiệu quả hơn; cost; limitations đủ 6 ý: một họ model, benchmark tự động, thiếu classroom deployment, LLM judge bias, automatic metric chưa validate construct, token cap confound.
- [ ] **T11 — Reproducibility statement.** Khai đủ: benchmark split, prompt, seed, decoding setting, LLM judge model, metric scripts, graph dump format.

### Bằng chứng bổ sung

- [~] **T12 — Expert validation tối thiểu.** 3–5 giảng viên/chuyên gia chấm 10–15 scenario theo rubric 4 trục: alignment, tính khả thi, tính sư phạm, mức cần chỉnh sửa. Reviewer có thể kiểm tra thông tin chuyên gia độc lập. Công cụ tại `isd-exp expert`; việc mời chuyên gia và thu phiếu do tác giả làm. Tiêu chí đã đổi theo nhận xét Sprint 2, xem S17.
- [x] **T13 — Tăng số lượng ablation.** Đã chốt trong nhận xét Sprint 1: ablation là 2x2 `agent_mode` × `context_mode` chạy trên `test_30` ở hai size, A0 chạy lại bên trong nó. Không dùng nguyên ladder cho ablation nữa.

## Nhóm S — nhận xét Sprint 2 (2026-09-28), theo gate

Thầy chưa phê duyệt chạy lại TN1/TN2. Chỉ chạy chính thức sau khi đạt Gate 1 và Gate 2. Sau freeze không thêm tính năng, không tối ưu theo kết quả test. Chi tiết: `feedbacks/sprint2_20260928/README.md`.

### Gate 1 — hoàn tất protocol (chỉ dùng `train_10`)

- [x] **S1 — Quy đổi thời lượng khoá học.** Band độ dài thành trần giờ học (`dev_plans.course_hours_ceiling`, `fanout.cap_module_minutes`), 2026-09-24. Cần báo lại thầy vì báo cáo Sprint 2 chưa có.
- [x] **S2 — Kế hoạch evaluation/summative.** `summative_evaluation_plan`, `adoption_criteria`, finding `no_summative_task`/`thin_summative_task`, 2026-09-24. Cũng cần báo lại thầy.
- [ ] **S3 — Đọc trajectory của hai scenario điểm thấp** trong tune đợt 2 và ghi nguyên nhân.
- [~] **S4 — Tune light và full trên cùng scenario.** Quyết định 2026-09-29: chạy `full` trước (`[harness].development_mode = "full"`) để đo tốc độ và chi phí, rồi chạy `light` trên cùng scenario. So từng rubric item, đặc biệt 12, 17, 19, 22, 30. Kết quả quyết định scope của TN1 và mức claim (xem `claim-rules.md` §2).
- [ ] **S5 — Tune thêm 0.8B và 4B** (hiện mới có 2B và 9B; 9B đi qua router).
- [ ] **S6 — Tune đủ bốn arm ablation** trên `train_10`. Working tree đang tạm để `[experiment.ablation]` ở `train_10`/`qwen9b` cho việc này; phải trả về `test_30` + `qwen08b`/`qwen4b` trước freeze.
- [ ] **S7 — Chốt output cap, thinking budget, temperature, decoding** và lưu metadata backend cùng run. `thinking_budget = 32` chỉ hợp lệ khi mọi nấc đều tự host; nếu không thì posture duy nhất hợp lệ là `0`.
- [ ] **S8 — Xác minh hai LLM judge nhận đủ output dài** (chunking) và không chấm nội dung dài thành "vắng mặt". Đối chiếu lại các ca ABSENT đã gặp ở tune-10.
- [ ] **S9 — Hiện thực `isd-exp trajectory rescore`** (cap 120, chấm offline từ trajectory đã lưu). Hiện hàm vẫn raise.
- [ ] **S10 — Định nghĩa cost** sẽ báo: token tuyệt đối, tỷ lệ so với ReAct-ISD, số call, thời gian.
- [ ] **S11 — Commit và đóng băng `PROTOCOL_REV`.** Code đang ở rev 10; báo cáo cho thầy phải dùng số thật, và cam kết không đổi sau Gate 1.

### Gate 2 — freeze và preflight

- [ ] **S12 — Run design TN1**: một run chung cho bảy hệ (`c1`), cộng hai repeat độc lập **chỉ cho A0 và ReAct-ISD** ở cả 4 size × 90 scenario. Runner hiện chưa có cách chạy thêm tag cho riêng hai agent — cần thiết kế (ví dụ một profile riêng cho repeat).
- [ ] **S13 — Run design TN2**: 0.8B và 4B × 4 arm × `test_30` × 3 run (`a1`–`a3`).
- [ ] **S14 — Kế hoạch phân tích viết trước**: so sánh ghép cặp theo scenario, effect size, CI, Holm; phân tích repeat làm riêng; failure = 0 là layer chính, complete-case là sensitivity; ba nguồn biến thiên (generation / judge chấm lại cùng output / scenario) được tách.
- [ ] **S15 — Chốt judge roster** (GPT-4o-mini + Gemini 2.5 Flash-Lite, full TN1, điểm từng judge lưu riêng, cách gộp chốt trước, cache theo hash output) và sáu tín hiệu panel. Encoder chính là `nemotron` (quyết định 2026-09-29): khi TN thì phải có pod embed; khi tune thì bỏ qua nó — `judge alignment` tự skip arm không có endpoint, và `isd-exp pool tune --encoder bgem3` đọc panel của `bgem3`.
- [ ] **S16 — Smoke test** cache/resume, chấm offline, chuyển backend; kiểm split disjoint; `freeze write` + `audit preflight` + ước lượng chi phí.

### Gate 4 — expert validation

- [ ] **S17 — Tiêu chí chuyên gia theo nhận xét Sprint 2**: constructive alignment, feasibility, audit usefulness, thời gian sửa (T12 cũ thiếu hai tiêu chí sau). 3–5 chuyên gia, ẩn danh, mẫu phân tầng, cùng mẫu cho mọi hệ. `isd-exp expert aggregate` vẫn chưa hiện thực.

### Gate 5 — manuscript

- [ ] **S18 — Áp các luật mới trong `claim-rules.md`** (cost nguyên văn, structural compliance, bundle ablation, không "tương đương" theo biên 10,8, không "deterministic", scope light/full) và đồng bộ với 17 quan hệ (3 core, 14 phụ).

## Nhóm M — thiết kế đo lường sau tune-10 (phân tích 2026-09-26, chờ quyết cùng GVHD)

Phân tích ngang sáu run tune-10 (4 run 2B, 2 run 9B; `isd-exp pool tune`) cho kết luận: khoảng cách LLM judge còn
lại không nằm ở harness, và vá theo điểm judge trên `train_10` là overfit vào hai model judge trên chính tập tune.
Harness đóng băng theo điểm judge; chỉ sửa khi bộ đếm tất định (`ATTENTION`) báo lỗi.

- [x] **M1 — Trajectory báo theo từng judge.** Thầy chốt 2026-09-28: lưu điểm từng judge riêng, cách gộp chốt trước (S15). Pooled 5 run: gemini-2.5-flash-lite chấm ours − react = −13.6,
  gpt-4o-mini +1.5. Gemini cho react 100/100 ở 49/50 lần, với trace 5 lời gọi không tham số, không kết quả. Riêng
  judge này kéo Total ~2 điểm. Đề xuất: bảng Trajectory tách judge; không kết luận gì về quy trình từ Trajectory
  gộp.
- [?] **M2 — Item thưởng bằng chứng bịa sau pilot.** Ta thua ổn định ở Dev2 (expert review), E1 (dữ liệu pilot),
  E2 (kết quả tổng kết, quyết định chấp nhận); ngang hoặc hơn ở A2, D1–D3, I1–I2, E3. react-isd nêu trường kết quả
  pilot và reviewer là người ở 10/10 output, dù chưa có pilot; hệ đề xuất 0/10 theo thiết kế. Đề xuất: khai báo
  trước freeze một phân tích độ nhạy ADDIE loại Dev2/E1/E2, và báo số đếm `post-pilot claims` cạnh điểm ADDIE như
  bằng chứng auditability. Cần thầy chốt có đưa vào paper không.
- [?] **M3 — Claim khác biệt đặt ở panel, không ở LLM judge.** Lưu ý thêm từ Sprint 2: C2–C4 = 1,00 chỉ là structural compliance, và phần panel trùng tiêu chí harness cưỡng chế lúc submit phải khai là phép kiểm tuân thủ ràng buộc. LLM judge ADDIE bão hoà ~82–85 cho cả hai hệ; panel
  thắng 5/6 tín hiệu ở cả 5 run với cách biệt lớn (C3 0.77 vs 0.59, C4 0.75 vs 0.58, porter ~2×), riêng
  `objective_cognitive_congruence` dao động. Hệ tốn 20–30× token và 10–15× thời gian so với react-isd. RQ1 nhiều
  khả năng ra "cạnh tranh", RQ2 là nơi có khác biệt — khớp câu chuẩn trong `claim-rules.md`.
- [?] **M4 — Quy tắc đánh giá thay đổi harness.** Một run tune-10 (se ~1.2) không phát hiện được thay đổi dưới ~3
  điểm Total. Đánh giá bằng bộ đếm harness; chỉ dùng điểm judge khi |Δ| ≥ 2·se hoặc gộp nhiều run
  (`pool tune --against`).

## Ràng buộc xuyên suốt

- Số liệu trong paper luôn sinh tự động vào `docs/generated/` (`isd-exp report sync`); không gõ tay. Thư mục đó bị xoá 2026-09-17 vì còn là số của kiến trúc đã bỏ — nó được tạo lại khi chạy lại TN1/TN2.
- Không claim tiết kiệm chi phí (R1). Không nới scope quá "trên dải Qwen 0.8B–9B".
- Paper không đề cập RAG.
- Không tự chạy benchmark/thí nghiệm; mọi run do tác giả thực hiện thủ công.
