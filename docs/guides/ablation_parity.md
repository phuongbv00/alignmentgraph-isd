# Ablation parity — trục `agent_mode` (multi vs single)

> **Trạng thái: đã duyệt 2026-10-06**, cả ba đề xuất ở §5 được chấp nhận. Light mode bị bỏ cùng
> ngày, nên mọi output được viết ở toàn bộ quy mô plan nêu.
> Nó thay cách làm cũ: chạy một run, tìm một chỗ hai arm lệch nhau, vá, rồi chạy lại.
> Từ rev 13 tới rev 19, mỗi run lộ thêm một chỗ hai arm lệch nhau, mỗi lần tốn một run thật,
> và hai bản vá tự gây ra lỗi kế tiếp (rev 15, rev 18).

## 1. Luật

Mọi khác biệt giữa hai arm phải nằm ở **§2 (cố ý khác)**. Mọi thứ còn lại nằm ở **§3 (giữ như
nhau)** và phải đi qua **một đường code duy nhất** mà cả hai arm cùng gọi. Viết hai bản "cho
giống nhau" thì không đạt yêu cầu. Một luật có mặt ở một arm mà không có ở arm kia là biến thứ
hai trên trục, và paper không được phép có biến thứ hai.

Phép thử cho một luật bất kỳ: *Nếu một nhà thiết kế thay đổi cách chia việc (một người làm hết
hay nhiều người cùng làm), luật này có đổi theo không?* Có thì nó thuộc §2. Không thì nó thuộc §3.

## 2. Cố ý khác (treatment, đã đăng ký là một bundle)

Đây là bundle đã đăng ký trong `claim-rules.md` và §5.4 của `benchmark_guides.md`, cộng D7 (regen)
được chốt ở §5. Paper liệt kê đúng các dòng này, không hơn.

| # | Thành phần | multi | single |
|---|---|---|---|
| D1 | Ranh giới context | Mỗi stage, mỗi Developer bắt đầu một context mới | Một context xuyên sáu stage |
| D2 | Persona | Một persona cho mỗi stage, cộng persona Developer | Một persona `SingleDesignerAgent` |
| D3 | Giao việc | Designer viết khung, Developer viết item theo work set | Một agent viết cả khung lẫn item |
| D4 | Thứ tự trong stage | Harness đi: khung, rồi các work set theo thứ tự plan | Agent tự chọn thứ tự và cách chia batch |
| D5 | Re-dispatch | Gap còn lại được giao lại cho work set sở hữu nó, một vòng | Không có Developer nên không có re-dispatch |
| D6 | Thời điểm repair net | Sau mỗi stage | Một lần ở cuối run |
| D7 | Regen khi stage ra rỗng | Chạy lại stage hoặc work set trong một context mới | Không có (gắn với D1) |

Không có dòng nào khác. Chi phí (số call, token) khác nhau là **hệ quả** của D1–D7, không phải
một dòng riêng.

## 3. Giữ như nhau — hiện trạng và đích

Cột **Hiện trạng**:
- **chung**: một đường code, cả hai arm gọi.
- **chép**: hai bản code viết để khớp nhau, có test đối chiếu.
- **LỆCH**: hai arm làm khác nhau và không có lý do ở §2.

| # | Luật | multi hiện nay | single hiện nay | Hiện trạng | Đích |
|---|---|---|---|---|---|
| C1 | Lời giao stage (task, rules) | `stage_brief_block` | `stage_brief_block` + rules của item | chung | giữ |
| C2 | Hình dạng artifact (schema) | `artifact_schemas` qua `submit_specs` | `artifact_schemas` qua `react_specs(open_fields)` | chung (nguồn) | giữ |
| C3 | Validator của artifact | `step.validate`, `output_errors` | như multi | chung | giữ |
| C4 | Constrained pass (pass 2) | `turn.constrained_pass` | như multi | chung | giữ |
| C5 | Siết schema pass 2 theo giao việc | có `work_set`: số lượng là `minItems`/`maxItems`, module là `const` | không có `work_set`: chỉ enum | **LỆCH** | Pass 2 của single siết theo đúng work set mà artifact thuộc về |
| C6 | **Nội dung giao việc** (đơn vị nào, viết bao nhiêu, cho cặp objective × timing nào, xếp lịch id nào) | Dòng giao việc trong assignment của Developer | Một câu ghi chú độ sâu | **LỆCH** | Một hàm dẫn xuất từ design; cả hai arm nhận cùng danh sách. Ai nhận (D3) mới là khác biệt. |
| C7 | Quota mỗi đơn vị (task, module) | `trim_to_quota` trên work set | `fanout.unit_quotas` + `_within_quota` (rev 19) | chép | Một hàm: commit đơn vị nào thì cắt theo quota đơn vị đó |
| C8 | Bỏ artifact trùng | `without_repeats` khi ghép instalment, trim | `without_repeats` trong `ReactLoop._commit` (rev 18) | chép | Gộp vào đường commit chung |
| C9 | Đường commit item | `fanout.commit_sets` theo work set thật | `commit_sets` với một set giả `S{n}` mỗi submit | **LỆCH** | Single commit vào đúng work set dẫn xuất mà item thuộc về |
| C10 | "Còn nợ gì" (instalment, owes) | `AgenticStep.owes` + `keep_items` cho Developer | `_owed` = phần chưa landed + đơn vị chưa có item | **LỆCH** | Một hàm: phần chưa landed + đơn vị chưa đủ quota |
| C11 | Ngân sách submit | `SUBMIT_BUDGET=3` mỗi artifact; instalment có tiến triển không tính | `SUBMIT_CAP=8` mỗi stage, chỉ tính submit không tiến triển (rev 18) | **LỆCH** | Một luật: N submit *không tiến triển* cho mỗi artifact, cả hai arm |
| C12 | Định nghĩa "tiến triển" | ngầm trong `keep_items` | `_progress_mark` (rev 18) | **LỆCH** | Một hàm dùng cho C10 và C11 |
| C13 | Khi nào stage xong | `step_done` + `dispatch_done` + Developer xong | `step_done` + `missing_outputs` rỗng | chép | Một hàm: không còn nợ theo C10 |
| C14 | Regen khi stage ra rỗng | `regen_budget` (stage và Developer) | không có | đã chuyển | Xếp vào §2 (D7) |
| C15 | Refund turn (lặp, ERROR, endpoint, overflow) | `TurnMeter` | `TurnMeter` | chung | giữ |
| C16 | Dừng khi prompt không vừa cửa sổ | `cannot_fit` | `cannot_fit` | chung | giữ |
| C17 | Transcript budget, trim, compaction, user turn | `transcript`, `compaction` | như multi | chung | giữ |
| C18 | Repair turn (agent sửa lỗi của chính nó) | `REPAIR_TURNS` mỗi stage, qua state read | `REPAIR_TURNS` mỗi stage, qua state read | chép | Một hàm chọn violation và soạn lượt repair |
| C19 | Repair net (harness) | `_verify_family` | `_verify_family` | chung | giữ (thời điểm là D6) |
| C20 | Trần thời lượng module, dừng khi không có module | `cap_module_minutes`, `NO_MODULES` | như multi | chung | giữ |
| C21 | Bind tool đọc | theo stage | hợp các stage, state read theo stage hiện tại | chép | giữ, có test |

Tóm tắt: 9 dòng **chung**, 5 dòng **chép**, 6 dòng **LỆCH** (C5, C6, C9, C10, C11, C12); C14 đã
chuyển sang §2 (D7).
Các lỗi bất đối xứng lộ ra ở rev 13, 18 và 19 rơi đúng vào các dòng LỆCH (C9–C12). Lỗi ở rev 16
và 17 nằm ở dòng chung (C3, C17), nên đã sửa một lần cho cả hai arm; chúng không phải lỗi parity.

## 4. Đích kiến trúc

Arm single **tự điền vào chính các work set dẫn xuất** mà arm multi giao cho Developer:
- Cùng hàm dẫn xuất work set (`plan_sets` trên `dispatch_payload`).
- Cùng nội dung giao việc (C6).
- Cùng đường commit vào work set (C9), nên quota (C7) và bỏ trùng (C8) đi theo luôn.
- Cùng luật "còn nợ" và "tiến triển" (C10, C12), cùng ngân sách submit (C11).

Phần còn lại của single đúng là D1–D6: một context, một persona, không giao việc, tự chọn thứ
tự, không re-dispatch, repair net ở cuối. Các mảnh vá riêng cho single (`unit_quotas`,
`_within_quota`, `_progress_mark`, ngữ nghĩa riêng của `SUBMIT_CAP`) sẽ được gỡ, thay bằng các
hàm chung.

## 5. Quyết định (đã chốt 2026-10-06)

1. **C6 — nội dung giao việc cho single.** Chốt: single nhận cùng danh sách giao việc,
   trình bày theo từng đơn vị khi stage tới (ví dụ "task AT-02: 3 item, ILO-01 apply
   short_answer, ..."). Lý do: danh sách này dẫn xuất từ design, không phải sản phẩm của việc
   chia người. Nếu bạn coi nó là một phần của D3, single chỉ nhận số lượng, và bundle phải ghi
   thêm dòng "nhận giao việc chi tiết".
2. **C14 — regen.** Regen là chạy lại một context mới, nên về bản chất nó gắn với D1. Chốt: xếp
   vào §2 (dòng D7) và khai báo; không thêm cơ chế tương đương cho single.
3. **C11 — con số N.** Chốt: N = 3 submit không tiến triển cho mỗi artifact, ở cả hai arm,
   bằng `SUBMIT_BUDGET` hiện tại.

## 6. Bất biến kiểm offline (bước 3)

Chạy cả bốn arm với model giả trả cùng một bộ artifact, rồi kiểm:
- **I1:** Deliverable của bốn arm có cùng số item, activity, material trên mỗi đơn vị.
- **I2:** Không stage nào bị trần turn hoặc ngân sách submit cắt khi model có tiến triển.
- **I3:** Model chỉ gửi lại (không tiến triển) thì stage đóng sau đúng N submit, ở cả hai arm.
- **I4:** Không đơn vị nào vượt quota. Không có artifact trùng.
- **I5:** Cùng một submit sai thì bị từ chối cùng lỗi, cùng constrained pass, ở cả hai arm.
- **I6:** Lời giao việc (C6) cho cùng một design là cùng một danh sách ở cả hai arm.
- **I7:** Mỗi luật ở §3 được gọi từ đúng một hàm. Test kiểm trên source, kiểu
  `test_neither_arm_reads_its_settings_off_the_other`.

## 7. Nghiệm thu bằng run thật (bước 4)

Một run `train_10` ở cả 2B và 0.8B. Chỉ đọc các bất biến sau, không đọc transcript để tìm thêm
việc vá:
- Dòng ATTENTION của `pool tune` không có `stage_abandoned`, `budget_exhausted` do trần turn,
  `prompt_exceeds_window`, `context_overflow`.
- Điều kiện fidelity của §5.5 trong `benchmark_guides.md`.
- Số item trên mỗi đơn vị của bốn arm nằm trong quota.

Thứ gì không nằm trong danh sách này là kết quả về model, không phải việc cần vá.
