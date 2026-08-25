# Đề xuất mở rộng ablation study

Tài liệu này trả lời góp ý "Tăng số lượng Ablation" trong bản nhận xét ngày 2026-08-17. Em trình bày các arm mới, các phương án thiết kế thực nghiệm, và chi phí kèm theo. Em xin thầy chốt scope trước khi chạy.

## 1. Hiện trạng (thiết kế 2×2 mới, code đã xong 2026-08-26, chưa chạy)

Ablation được thiết kế lại thành factorial 2×2 trên hai trục: **decomposition** (`agent_mode`: multi/single) × **alignment machinery** (`context_mode`: graph/prose). Trục thứ hai thay thế hoàn toàn cặp switch verifier/graph-context cũ.

| Arm | agent_id | Decomposition | Alignment machinery |
|---|---|---|---|
| multi + graph (A0) | `alignmentgraph-isd` | multi | graph (đầy đủ) |
| multi + prose | `alignmentgraph-isd-multi-prose` | multi | prose blackboard |
| single + graph | `alignmentgraph-isd-single-graph` | single | graph (đầy đủ) |
| single + prose | `alignmentgraph-isd-single-prose` | single | prose blackboard |

**Arm `prose` là một hệ graph-free thật sự, không phải một cách render khác của graph.** Bản prose cũ (render node do graph chọn thành câu văn) đã bị loại: graph vẫn làm hết việc chọn lọc, tính gap docket, verifier, routing, audit — nên trục chỉ đo định dạng bề mặt và underestimate đóng góp của graph. Bản mới: mỗi specialist lưu nguyên cục JSON đã parse vào một blackboard (một document/step), specialist sau đọc lại verbatim theo read-list tĩnh (đúng pattern named-slice của các hệ multi-agent không-graph như addie-agent); safeguard chỉ còn 5 within-artifact check (bloom verbs, measurability, rubric consistency, evaluation quality, actionability) + self-repair/regen dùng chung; không cross-agent routing, không docket, không residual audit, không có file `graph.json`/`.dot` (chính là contrast auditability). Trục vì vậy là một **bundle** — "bỏ máy alignment thì harness còn gì" — và được disclose như bundle, không claim single-variable.

Arm `single` (đã có trong code) là monolithic control: một persona duy nhất, gộp các cặp plan/execute, cùng scaffolding regen/self-validation với multi.

Bốn arm chạy trong cùng session của ladder so sánh hệ. Kết quả cũ (thiết kế verifier × graph-context) bị bỏ; theo nguyên tắc đã thống nhất, thiết kế lại đồng nghĩa **chạy lại toàn bộ arm** trong thiết kế mới.

## 2. Arm mới đề xuất thêm

### A5 — `no-safeguards` (gom mọi cơ chế phòng thủ vào một arm) — khuyến nghị chính

Arm này tắt đồng thời verify+repair và regen (`regen_budget=0`), giữ nguyên graph machinery. Lý do gom thay vì tách lẻ:

- Claim trong paper đứng ở mức bundle: "harness giữ được robustness". Một arm gom trả lời thẳng câu hỏi "các cơ chế phòng thủ có đáng giữ không" với chi phí một arm.
- Kết hợp các arm 2×2, ta được một trục tháo dần: full → prose (bỏ máy alignment) → no-safeguards → single. Mỗi arm tháo thêm một lớp cơ chế.

Phương án tách lẻ (A5a `no-regen` riêng, A5b verifier chỉ kiểm không sửa) là arm phụ. Chỉ nên chạy khi A5 cho hiệu ứng rõ và ta cần quy công cho từng cơ chế.

### Không có arm RAG

Paper không đề cập RAG. Cơ chế retrieval chỉ thuộc phạm vi luận văn.

## 3. Thiết kế thực nghiệm: ba phương án

Thầy góp ý đúng rằng ablation không nhất thiết dùng nguyên ladder như thực nghiệm so sánh hệ. Em trình ba phương án. Điểm chung: **thiết kế lại đồng nghĩa chạy lại toàn bộ arm ablation (kể cả 4 arm 2×2) trong cùng thiết kế mới**, để mọi arm dùng chung judge session. Không giữ và không trộn kết quả ablation cũ.

Đơn vị chi phí: 1 arm-size-run = 90 scenario ≈ chi phí một agent trong một run của ladder hiện tại.

| Phương án | Thiết kế | Số run tổng (5 arm) | Ưu | Nhược |
|---|---|---|---|---|
| B1 — hai đầu ladder | 2 size (0.8B, 9B) × 3 run × 90 scenario | 30 arm-size-run | Giữ được DiD (interaction cần đúng hai đầu); chi phí bằng nửa B2 | Mất hai size giữa; hiệu ứng harness có thể không đơn điệu theo size nên đoạn giữa không quan sát được |
| B2 — nguyên ladder | 4 size × 3 run × 90 scenario | 60 arm-size-run | Power tối đa; so sánh trực tiếp với ladder chính | Đắt nhất; gấp đôi B1 |
| B3 — ladder rút scenario | 4 size × 3 run × 30 scenario (stratified, seed 42) | 60 arm-size-run nhưng mỗi run bằng 1/3 | Giữ đủ 4 size; chi phí ≈ 1/3 B2 | n=30 mỗi ô: paired Wilcoxon yếu đi rõ; các delta nhỏ (đặc trưng của ablation) dễ mất ý nghĩa sau Holm |

Khuyến nghị của em: **B1** nếu ưu tiên câu hỏi scale (DiD hai đầu); **B2** nếu ngân sách cho phép, vì delta giữa các arm ablation thường nhỏ hơn delta giữa các hệ, nên cần giữ n=90.

## 4. Việc code cần làm trước khi chạy (không tốn API)

- 2×2 mới (single + prose blackboard): **đã xong 2026-08-26**, test suite package xanh.
- A5: thêm switch tắt verify+repair + `regen_budget=0` vào đăng ký per-arm (cơ chế `HarnessRunConfig` đã có sẵn field regen).
- Cập nhật `02_run_ladder.sh` (hoặc script ablation riêng theo phương án B1/B3) + pipeline pool/tables/figures nếu thêm arm thứ 5/6.

## 5. Câu hỏi xin thầy chốt

1. Bộ arm: A5 thêm vào 4 arm 2×2 (5 arm, khuyến nghị) hay thêm cả arm tách lẻ A5a/A5b (7 arm)?
2. Thiết kế: B1, B2 hay B3?
3. Thời điểm chạy: trước hay sau vòng expert validation?
