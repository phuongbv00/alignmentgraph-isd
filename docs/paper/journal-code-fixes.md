# Lỗi code và việc dời sang bài tạp chí

Nguồn: ba bản review biên tập cho bản REV-ECIT 2026 v2 (Claude, Codex, một biên tập viên độc lập;
2026-10-14), đối chiếu với run web app `c0dbcb933fb440a1aa45d59eb1b024e8` (bản sao ở
`rev-ecit2026-v2/case/run/`). Bản hội thảo được ưu tiên nộp trước nên chỉ sửa câu chữ và số liệu
của bài. Các mục dưới đây cần sửa trong `alignmentgraph-isd`, hoặc cần thực nghiệm, trước khi viết
bài tạp chí.

## A. Lỗi code đã xác minh

### A1. `Memory.settle` ghi sai "harness đã sửa" cho vi phạm không có tác tử phụ trách
- **Ở đâu:** `core/memory.py::settle` và `core/runner.py::_reconcile`.
  - `_reconcile` gom phần dư cuối từ `found`, là danh sách CHỈ gồm các loại vi phạm có tác tử phụ
    trách (owned). `settle` coi mọi finding không có trong danh sách đó là đã đóng, và đánh dấu
    `repaired_by_harness` cho finding chưa từng hiện cho tác tử.
- **Hậu quả:**
  - Một finding không có tác tử phụ trách (`measurability`) mà vẫn còn ở lần kiểm cuối thì bị ghi
    là đã sửa. Ví dụ trong run trên: ILO-02 ghi `repaired_by_harness`, `repaired_by=""`,
    `repaired_at_round=0`.
  - Thực tế không có sửa nào: `graph.json::node_violations` vẫn gắn cờ ILO-02, round 8 (reconcile)
    vẫn thấy vi phạm này, và câu mục tiêu không đổi.
  - Giao diện và đồ thị vì vậy nói hai điều khác nhau về cùng một nút.
- **Sửa:** `settle` phải nhận đủ phần dư, cả phần có lẫn phần không có tác tử phụ trách. Cách khác
  là chỉ đóng những finding thuộc loại có tác tử phụ trách. Cần thêm test: một finding không có tác
  tử phụ trách còn tồn tại ở lần kiểm cuối phải ra `open`/`unowned`.
  - Kiểm thêm điều kiện bất biến sẵn có trong `tests/test_violation_ledger.py`: đồ thị không được
    gắn cờ một loại vi phạm mà sổ không ghi. Điều kiện này cần mở rộng thành: sổ không được ghi
    "đã sửa" cho một cờ mà đồ thị vẫn còn.
- **Tạm thời cho bài hội thảo:** `rev-ecit2026-v2/case/reconcile_ledger.py` đã chạy trên cả bản sao
  lẫn thư mục run của app.
  - Script áp đúng một quy tắc: finding nào đồ thị cuối còn gắn cờ thì là `open`.
  - Bản gốc được giữ ở `violations.raw.json`.
  - `make_tables.py` dừng hẳn nếu sổ và đồ thị lệch nhau.
  - **Khi đã sửa code và chạy lại case thì bỏ script này.**

### A2. Phép kiểm tra không đọc văn bản tiếng Việt
- `checks.bloom_verbs_items` so trường `bloom_verb` (tiếng Anh, do mô hình tự điền) với `level`,
  không đọc câu mục tiêu.
  - Ví dụ: ILO-05 viết "áp dụng được…" nhưng khai `level/bloom_verb: evaluate`, và vẫn qua kiểm tra.
- `measurability` dùng regex động từ mơ hồ và mẫu mức độ/điều kiện bằng tiếng Anh.
- Hướng sửa: bổ sung từ điển động từ Bloom tiếng Việt, hoặc dùng bộ phân loại Bloom
  (`bertbloom`) cho câu mục tiêu.

### A3. Quy tắc mức Bloom của câu hỏi yếu hơn lời mô tả
- Một mục tiêu qua kiểm tra chỉ cần **một** câu hỏi ở mức ≥ mức của mục tiêu.
  - Ví dụ: AT-03 có 2 trên 3 câu ở mức understand cho ILO-05 (mức evaluate), và câu "evaluate"
    duy nhất lại yêu cầu "mô tả".
- Cần chọn và khai rõ: đòi mọi câu ≥ mức, đòi một tỉ lệ, hay đòi một câu.

### A4. Trường `objectives` của kế hoạch buổi học không được kiểm
- Mọi kế hoạch buổi học trỏ tới id không tồn tại: `OBJ-0001`, `MOD-02-01`, `OBJECTIVE:02-01`.
- Không quan hệ nào đọc trường này, nên `fanout.reference_errors` không chặn.
- Hướng sửa: khai trường này là `ref_fields`, hoặc bỏ trường khỏi schema rồi dẫn xuất từ hoạt động.

### A5. Vòng re-dispatch sinh kế hoạch buổi học chồng lấn
- SG-5201 và SG-5202 (vòng R1, ordinal stride 50) xếp lại TLA-0201..0204 của MOD-02, trong khi
  SG-0201 và SG-0202 đã xếp chúng. Số buổi 2 và 3 còn trùng với số buổi của mô-đun 1.
- Kiểm `redispatch.still_missing`: vòng này lẽ ra chỉ cần xếp TLA-0203/0204.
- Kiểm thêm `redispatch.next_session`.

### A6. Câu hỏi gần như trùng nhau nhưng gắn cho mục tiêu khác
- ATI-0203 gần như chép nguyên ATI-0202 nhưng gắn cho ILO-04, nên cạnh C2 của ILO-04 có được là
  nhờ một câu trùng.
- `dev_plans.same_artifact_key` coi cùng nội dung mà khác mục tiêu là hai câu khác nhau.
- Hướng sửa: thêm phép kiểm câu gần trùng trong cùng một task.

### A7. P6: bảng alias đọc sai loại học liệu
- MAT-0201 và MAT-0301 khai `type: simulation`, nhưng `format: video` và nội dung là kịch bản
  video. `_MEDIA_TYPE_ALIASES` đọc chúng là video vì "video" đứng trước trong bảng.
- Cần quyết định P6 so trường `type` hay so nội dung, và sửa thứ tự đối chiếu cho xác định.

### A8. Nội dung bịa ở pha triển khai
- `prototype_execution.issues_encountered` thuật lại một đợt thử nghiệm chưa hề diễn ra.
- Hướng sửa: rule và check tương tự quy tắc "a plan has no results" đã áp cho
  `summative_evaluation_plan`.

### A9. Tam giác khép kín qua một bài chẩn đoán trọng số 0%
- C2 duy nhất của ILO-01 và ILO-02 là AT-01: `diagnostic`, `weight_percent: 0`. Tổng trọng số các
  nhiệm vụ chỉ là 20%.
- `aligned(o)` vẫn tính là khép kín.
- Hướng sửa: thêm check "mục tiêu chỉ được đánh giá chẩn đoán". Hoặc cân nhắc yêu cầu đánh giá
  tổng kết hay hình thành mới tính là khép kín; nếu đổi định nghĩa thì phải nêu trong bài.

### A10. Vòng sửa hầu như không tới được tác tử
- Cả 6 vi phạm còn mở đều có `shown_to_agent = 0`: được phát hiện sau khi tác tử phụ trách đã kết
  thúc, hoặc không có tác tử phụ trách.
- Hướng sửa:
  - Gán `measurability` cho `outcome_designer`.
  - Cân nhắc một vòng trả lại tác tử phụ trách ở bước reconcile, có giới hạn để không treo.

### A11. Metadata thiếu posture suy luận
- `metadata.json` của run web app không ghi `thinking_budget`; phải tra trong `demo.db`.
- Hướng sửa: đưa vào `metadata.run_config` hoặc `metadata.llm`.

### A12. Đầu ra trộn ngôn ngữ, mẫu văn bản chưa bản địa hóa
- Kế hoạch đánh giá, các sản phẩm của pha triển khai, các hoạt động của MOD-01, `expert_review` và
  `alignment_matrix` ra tiếng Anh, dù `constraints.language = "Tiếng Việt"`.
- Hướng sửa: các mẫu văn bản của khung điều phối phải theo ngôn ngữ trong brief.

### A13. Web app: cạnh C2 bị che
- Cạnh ILO-01→AT-01 nằm thẳng hàng sau TLA-0101 nên không nhìn thấy (Hình 2b).
- Hướng sửa: định tuyến cạnh hoặc thêm khoảng cách trong layout.

### A14. Thời lượng mô-đun quá nhỏ so với thời lượng khóa học
- Ba mô-đun có tổng 150 phút cho khóa 30 giờ. Khung điều phối chỉ báo trần (`course_hours_ceiling`),
  không có sàn.
- Bài hội thảo không có claim nào về thời lượng. Bài tạp chí thì cần xử lý hoặc khai rõ.

## B. Việc dời sang bài tạp chí (không phải lỗi code)

- **Bằng chứng cho luận điểm động cơ (M2):** báo số vi phạm C2–C4 phát hiện và sửa trên 30 kịch
  bản, và một tín hiệu căn chỉnh của hệ so với React-ADDIE (panel 6 tín hiệu của v1).
- **Độ nhạy theo roster LLM judge:** kết quả dưới cặp judge mặc định của benchmark.
- **Lợi thế sân nhà:** tỉ lệ sản phẩm phải qua lượt giải mã có ràng buộc, và ablation khi bỏ lượt
  này.
- **Thời gian chạy đo không có hàng đợi**, kèm loại GPU.
- **Trích dẫn Qwen3.5:** cần tìm nguồn chính thức, không suy đoán.
- **Hình:** chữ trong ảnh chụp web app quá nhỏ khi in. Nên có giao diện tiếng Việt, hoặc vẽ lại
  đồ thị bằng công cụ vector.
- **Công bố mã nguồn và dữ liệu:** quyết định có công bố hay không, và khi nào.
