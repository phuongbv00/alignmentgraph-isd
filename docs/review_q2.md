# Backlog hoàn thiện manuscript Q2

File này là backlog canonical cho các việc phải làm trước khi nộp Q2. File cũ cùng tên đã mất; bản này tái lập 2026-08-17. Nguồn chính của bản tái lập là file góp ý của thầy (`Góp_ý_Phương.docx`, nhận 2026-08-17) cộng hai nhãn R2/R4 còn được `docs/summary.md` tham chiếu.

Trạng thái: `[ ]` chưa làm, `[~]` đang làm, `[x]` xong, `[?]` chờ quyết định.

## Nhóm R — backlog cũ (tái lập nhãn)

- [x] **R1 — Cost framing retarget.** Giữ motivation triển khai nhưng đổi luận điểm thành "chạy được và đáng chạy ở đầu nhỏ". Cấm mọi biến thể của claim "rẻ hơn". Đã áp vào `06_results.tex` và summary.md mục 10.4.
- [ ] **R2 — Prediction pre-specified cho hai cách đọc ablation.** Kết quả hiện tại: judge gần bất biến giữa các arm ablation trong khi alignment panel dịch rõ. Hai cách đọc: (thuận) LLM-judge không nhạy với alignment; (ngược) thiếu discriminant validity của panel. Phải ghi một dự đoán phân biệt hai cách đọc **trước** khi có nhãn chuyên gia. Dự đoán này nằm trong `expert_validation/protocol.md`. Tham chiếu: summary.md mục 10.5.
- [~] **R3 — Expert study.** Trùng với T12 dưới đây; package thiết kế tại `expert_validation/`. Vòng tối thiểu (3–5 chuyên gia × 12 scenario) phục vụ bài Q2; bản đầy đủ (blind-code theo thủ tục gốc, κ máy-vs-người) để dành hướng ETR&D.
- [?] **R4 — Sensitivity trần token cao hơn.** Chạy thêm một cấu hình với token cap cao hơn 8192 để preempt câu hỏi "cấp trọn 24 GB thì sao". Bị chặn trước đây vì 100% failure của baseline là truncation tại 8192. Là thí nghiệm mới; chỉ chạy khi thầy chốt scope (xem `docs/ablation_expansion_proposal.md`).

- [x] **R5 — Hình kiến trúc không khớp Algorithm 1.** Reviewer báo hình `figures/architecture.svg` phi logic so với thuật toán. Đối chiếu ba nguồn (hình / Algorithm 1 / `core/nodes.py:build_graph`) cho thấy code khớp thuật toán, hình mới là chỗ sai: hình cũ vẽ hub-and-spoke không có thứ tự thực thi, đặt verifier như cổng QC cuối, cho aggregator ăn output của verifier thay vì đọc G, giấu budget K và nhánh warning, và subgraph minh hoạ vi phạm chính Eq.(1) (hai cạnh *evaluates* không trỏ vào Objective nên objective chỉ có 2/3 facet). Đã vẽ lại hình theo đúng control flow của Algorithm 1 (chain 1–6, verify+repair cục bộ từng specialist, aggregate/audit sau vòng lặp) và sửa 3 chỗ Algorithm 1 lệch code: repair là patch có đích chứ không sinh lại cả phase; `verify` chỉ chạy trên checks specialist sở hữu nên `s_needs` không có QC node; `warn`/audit chạy một lần sau vòng lặp. Pass 2 cùng ngày soát tiếp hình mới với `core/alignment.py:REGISTRY` và `core/graph.py:NodeType`, bắt thêm 3 lỗi: hình bịa hai quan hệ không có trong 13 relation (Material→Activity, Implementation→Evaluation) — `implementation_plan` thực tế không tham gia relation nào nên đã bỏ khỏi hình; `tab:graph-spec` liệt kê 6 node type trong khi `NodeType` có 7 (thiếu `needs_context`, chính là nguồn của R1/R2) — đã sửa thành 7; và card 1 thiếu mũi tên read trong khi Algorithm 1 chạy `ctx ← C(s)` cho mọi `s` — đã thêm. Hình hiện chỉ vẽ quan hệ có thật: R1 *informs*, R3 *measures*, R4 *supports*, R5 *evaluates*. Sửa 2026-08-21 trong `04_method.tex` + `figures/architecture.svg`. Pass 3: đổi sang bảng màu nhạt hợp tạp chí (slate `#3E5F7E` / ochre `#8A6A3B` / brick `#8C4B47` + xám), bỏ icon robot, và thêm **bản draw.io editable** `figures/architecture.drawio` làm master; pipeline build đổi thành **.drawio → export SVG → `generate_figures.sh` → PDF**: script mới chỉ làm SVG→PDF, tự chạy `drawio_labels.py` trên bản copy tạm để đổi label HTML (`<foreignObject>`) của draw.io thành SVG `<text>` vì không renderer SVG nào vẽ được foreignObject; quy trình ghi trong `figures/README.md`. **Chưa port sang bản VN** (`vn/sections/04_method.tex`) vì VN đang freeze.

## Nhóm T — góp ý thầy 2026-08-17 (`Góp_ý_Phương.docx`)

### Định vị và metadata

- [x] **T1 — Title thêm "Auditable".** Title chốt: *AlignmentGraph-ISD: A Graph-Guided Multi-Agent Harness for Auditable Instructional Systems Design with Small Language Models*. Đã sửa `main.tex` + summary.md.
- [x] **T2 — Author block chuẩn quốc tế.** Thứ tự: Viet-Phuong Bui (chính) / Van-Hai Pham* (liên hệ) / Van-Tam Bui. Dạng tên gạch nối. Đã sửa `docs/authors.md` + `main.tex`. Lưu ý: hỏi lại thầy về dấu * khi submit.
- [ ] **T3 — Template journal mục tiêu.** User chốt trong session này: tạm giữ ACM preprint vì chưa chốt hẳn journal. Thứ tự nộp dự kiến (scan 2026-08-17): ① EAIT (Springer sn-jnl) → ② Expert Systems (Wiley) → ③ IJIMAI. Khi chốt thì port template, giữ nguyên cơ chế số liệu sinh tự động từ `docs/generated/`.

### Nội dung bản thảo

- [~] **T4 — Sync ngược VN → EN.** Bản VN đi trước ở một số section. Dịch/merge các phần VN mới sang EN. Sau sync, EN là bản chính duy nhất; VN freeze.
- [ ] **T5 — Claims sweep toàn bài theo quy tắc của thầy.** Cấm: "vượt trội toàn diện", "tốt nhất mọi chỉ số", "verifier cải thiện chất lượng đầu ra", "chứng minh constructive alignment đầy đủ". Dùng: robustness dưới SLM + token cap; ADDIE cạnh tranh, lợi ở model nhỏ, parity ở model lớn; graph context cải thiện *các tín hiệu đo được*; verifier = backstop + nguồn evidence audit. Đồng thời gỡ mọi mention RAG — paper không đề cập RAG (RAG chỉ thuộc luận văn).
- [ ] **T6 — Related Work theo 3 trục.** (1) LLM/AI agents for instructional design; (2) small/on-premise language models in education; (3) constructive alignment và alignment measurement.
- [ ] **T7 — Introduction định vị AI in Education.** Làm rõ vì sao bài thuộc AIED/EdTech, không chỉ LLM engineering: hệ hỗ trợ quyết định của instructional designer, không thay thế chuyên gia.
- [ ] **T8 — Method mapping thành phần → mức bằng chứng.** Decomposition → robustness; graph context → alignment signals; verifier → audit/backstop.
- [ ] **T9 — Results đọc cân bằng.** "Competitive and robust" thay cho "superior". Cost trade-off trung thực. Bảng lớn (full panel, sensitivity chi tiết, log thống kê) chuyển sang appendix/supplementary.
- [ ] **T10 — Discussion/Conclusion đối chiếu checklist thầy.** Implications for ISD; teacher-in-the-loop; khi nào ReAct/single-loop hiệu quả hơn; cost; limitations đủ 6 ý: một họ model, benchmark tự động, thiếu classroom deployment, LLM judge bias, automatic metric chưa validate construct, token cap confound.
- [ ] **T11 — Reproducibility statement.** Khai đủ: benchmark split, prompt, seed, decoding setting, judge model, metric scripts, graph dump format.

### Bằng chứng bổ sung

- [~] **T12 — Expert validation tối thiểu.** 3–5 giảng viên/chuyên gia chấm 10–15 scenario theo rubric 4 trục: alignment, tính khả thi, tính sư phạm, mức cần chỉnh sửa. Reviewer có thể kiểm tra thông tin chuyên gia độc lập. Package thiết kế tại `expert_validation/`; việc mời chuyên gia và thu phiếu do tác giả làm.
- [?] **T13 — Tăng số lượng ablation.** Hướng arm mới: single-agent (bỏ multi-agent), no-safeguards (gom verifier+repair+regen vào một arm). Thiết kế lại thực nghiệm ablation thay vì dùng nguyên ladder; thiết kế lại đồng nghĩa chạy lại toàn bộ arm. Proposal tại `docs/ablation_expansion_proposal.md`; chờ thầy chốt scope trước khi chạy.

## Ràng buộc xuyên suốt

- Số liệu trong paper luôn sinh tự động từ `docs/generated/`; không gõ tay.
- Không claim tiết kiệm chi phí (R1). Không nới scope quá "trên dải Qwen 0.8B–9B".
- Paper không đề cập RAG.
- Không tự chạy benchmark/thí nghiệm; mọi run do tác giả thực hiện thủ công.
