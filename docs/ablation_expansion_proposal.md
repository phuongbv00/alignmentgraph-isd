# Đề xuất mở rộng ablation study

Tài liệu này trả lời góp ý "Tăng số lượng Ablation" trong bản nhận xét ngày 2026-08-17. Em trình bày các arm mới, các phương án thiết kế thực nghiệm, và chi phí kèm theo. Em xin thầy chốt scope trước khi chạy.

## 1. Hiện trạng

Ablation hiện tại có 4 arm. Bốn arm tạo thành factorial 2×2 trên hai cơ chế:

| Arm | Verifier + repair | Graph context (đọc) | Ghi chú |
|---|---|---|---|
| A0 (full) | bật | bật | chính là hệ trong ladder |
| A1 (−Verifier) | tắt | bật | |
| A2 (−GraphContext) | bật | tắt | graph vẫn được ghi |
| A3 (skeleton) | tắt | tắt | chỉ còn decomposition |

Bốn arm chạy trong cùng session của ladder so sánh hệ (4 size × 3 run × 90 scenario). Kết quả chính: bỏ graph context kéo panel alignment xuống trên diện rộng nhưng gần như không đổi điểm judge; verifier không tạo score effect trong cấu hình đầy đủ.

Hạn chế của thiết kế hiện tại: cả 4 arm đều giữ multi-agent decomposition. Vì vậy claim "decomposition → robustness" chưa có arm kiểm trực tiếp. Các cơ chế phòng thủ khác (regen khi section thiếu field bắt buộc) cũng chưa được ablate.

## 2. Arm mới đề xuất

### A4 — `single-agent` (bỏ multi-agent)

Một agent monolithic sinh trọn chương trình ADDIE trong cùng package. Agent này dùng cùng schema đầu ra, cùng hướng dẫn ISD, và ngân sách token tương đương tổng ngân sách của sáu specialist. Arm này cô lập đóng góp của decomposition. Đây là arm quan trọng nhất: nó là monolithic control mà phần Results hiện phải thừa nhận là còn thiếu.

### A5 — `no-safeguards` (gom mọi cơ chế phòng thủ vào một arm) — khuyến nghị chính

Arm này tắt đồng thời verifier+repair và regen (regen_budget=0), giữ graph context. Lý do gom thay vì tách lẻ:

- Claim trong paper đứng ở mức bundle: "harness giữ được robustness". Một arm gom trả lời thẳng câu hỏi "các cơ chế phòng thủ có đáng giữ không" với chi phí một arm.
- Kết hợp các arm cũ, ta được một trục tháo dần: full → −GraphContext → no-safeguards → single-agent. Mỗi arm tháo thêm một lớp cơ chế.

Phương án tách lẻ (A5a `no-regen` riêng, A5b verifier chỉ kiểm không sửa) là arm phụ. Chỉ nên chạy khi A5 cho hiệu ứng rõ và ta cần quy công cho từng cơ chế.

### Không có arm RAG

Paper không đề cập RAG. Cơ chế retrieval chỉ thuộc phạm vi luận văn.

## 3. Thiết kế thực nghiệm: ba phương án

Thầy góp ý đúng rằng ablation không nhất thiết dùng nguyên ladder như thực nghiệm so sánh hệ. Em trình ba phương án. Điểm chung: **thiết kế lại đồng nghĩa chạy lại toàn bộ arm ablation (kể cả A0–A3) trong cùng thiết kế mới**, để mọi arm dùng chung judge session. Không giữ và không trộn kết quả ablation cũ.

Đơn vị chi phí: 1 arm-size-run = 90 scenario ≈ chi phí một agent trong một run của ladder hiện tại.

| Phương án | Thiết kế | Số run tổng (6 arm) | Ưu | Nhược |
|---|---|---|---|---|
| B1 — hai đầu ladder | 2 size (0.8B, 9B) × 3 run × 90 scenario | 36 arm-size-run | Giữ được DiD (interaction cần đúng hai đầu); chi phí bằng nửa B2 | Mất hai size giữa; hiệu ứng harness có thể không đơn điệu theo size nên đoạn giữa không quan sát được |
| B2 — nguyên ladder | 4 size × 3 run × 90 scenario | 72 arm-size-run | Power tối đa; so sánh trực tiếp với ladder chính | Đắt nhất; gấp đôi B1 |
| B3 — ladder rút scenario | 4 size × 3 run × 30 scenario (stratified, seed 42) | 72 arm-size-run nhưng mỗi run bằng 1/3 | Giữ đủ 4 size; chi phí ≈ 1/3 B2 | n=30 mỗi ô: paired Wilcoxon yếu đi rõ; các delta nhỏ (đặc trưng của ablation) dễ mất ý nghĩa sau Holm |

Khuyến nghị của em: **B1** nếu ưu tiên câu hỏi scale (DiD hai đầu); **B2** nếu ngân sách cho phép, vì delta giữa các arm ablation thường nhỏ hơn delta giữa các hệ, nên cần giữ n=90.

## 4. Việc code cần làm trước khi chạy (không tốn API)

- A4: viết agent monolithic trong package `alignmentgraph_isd` + đăng ký agent id mới trong `run_benchmark.py`.
- A5: thêm switch `regen_budget=0` vào đăng ký per-arm (cơ chế `HarnessRunConfig` đã có sẵn field này).
- Cập nhật `02_run_ladder.sh` (hoặc script ablation riêng theo phương án B1/B3) + pipeline pool/tables/figures cho 6 arm.

## 5. Câu hỏi xin thầy chốt

1. Bộ arm: {A4, A5} thêm vào 4 arm cũ (6 arm, khuyến nghị) hay thêm cả arm tách lẻ A5a/A5b (8 arm)?
2. Thiết kế: B1, B2 hay B3?
3. Thời điểm chạy: trước hay sau vòng expert validation?
