# Backlog hoàn thiện manuscript Q2

Backlog canonical cho các việc phải làm trước khi nộp Q2. Nguồn: góp ý của GVHD 2026-08-17 (`Góp_ý_Phương.docx`) và nhận xét sau Sprint 1 nhận 2026-09-10 (`feedbacks/sprint1_20260828_0908/`). Khi hai nguồn lệch nhau thì nhận xét Sprint 1 thắng — nó chốt lại cả thiết kế thí nghiệm.

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

- [~] **T12 — Expert validation tối thiểu.** 3–5 giảng viên/chuyên gia chấm 10–15 scenario theo rubric 4 trục: alignment, tính khả thi, tính sư phạm, mức cần chỉnh sửa. Reviewer có thể kiểm tra thông tin chuyên gia độc lập. Công cụ tại `isd-exp expert`; việc mời chuyên gia và thu phiếu do tác giả làm.
- [x] **T13 — Tăng số lượng ablation.** Đã chốt trong nhận xét Sprint 1: ablation là 2x2 `agent_mode` × `context_mode` chạy trên `test_30` ở hai size, A0 chạy lại bên trong nó. Không dùng nguyên ladder cho ablation nữa.

## Ràng buộc xuyên suốt

- Số liệu trong paper luôn sinh tự động vào `docs/generated/` (`isd-exp report sync`); không gõ tay. Thư mục đó bị xoá 2026-09-17 vì còn là số của kiến trúc đã bỏ — nó được tạo lại khi chạy lại TN1/TN2.
- Không claim tiết kiệm chi phí (R1). Không nới scope quá "trên dải Qwen 0.8B–9B".
- Paper không đề cập RAG.
- Không tự chạy benchmark/thí nghiệm; mọi run do tác giả thực hiện thủ công.
