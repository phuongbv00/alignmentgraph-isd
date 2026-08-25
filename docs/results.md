# Kết quả tổng hợp — RQ1 ladder + RQ2 alignment panel + ablation

> **Cập nhật: 2026-07-30.** Nguồn duy nhất: 12 run dir
> `isd-agent-benchmark/results/test_90_benchmark_Qwen3.5-{0.8B,2B,4B,9B}_r{1.2.3}_20260726_*`
> (chạy 2026-07-26, **10 agent trong cùng mỗi run**: 6 đối sánh + harness + 3 arm ablation) →
> `04_audit_postrun.py` → `06_score_alignment.py` (5 arm instrument) → `07_pool_ladder_runs.py` →
> `results/pooled_ladder.json` + `pooled_ablation.bk.json` → `09`/`10`/`11`/`12` → `docs/generated/`.
> Mọi số dưới đây đọc từ hai file pooled đó; đừng sửa tay file này, hãy sửa nguồn rồi sinh lại.
>
> **Bản dump gộp để tra số**: `15_gen_facts_sheet.py` → `results/generated/facts.md` (đủ) và `facts_brief.md`
> (mục 0–2). File này là **diễn giải**; facts.md là **số**. Trước khi viết bất kỳ câu nào có "mọi size", "mạnh nhất
> ở…", "N/M tín hiệu", đọc roll-up đã tính sẵn ở facts §2.3–2.5 thay vì đếm ô bằng mắt — đặc biệt §2.5, bảng liệt kê
> đúng những chỗ mà trích một họ tín hiệu thôi sẽ xuyên tạc kết quả. Toàn bộ số trong file này đã được đối chiếu với
> facts.md (2026-08-10): khớp.
>
> Dataset `test_90`: 90 scenario (10 domain × 3 difficulty, stratified), 2 judge/entry, 4 kích thước Qwen3.5 × 3 run.

## Quy ước đo lường

**RQ1 — ba tín hiệu judge báo song song, không có composite làm thước dẫn.**

| Tín hiệu | Đo gì | Vai trò |
|---|---|---|
| `addie_median` | rubric ADDIE /100 (33 sub-step → 13 item → 5 phase) | **thước dẫn** — chất lượng nội dung thiết kế giảng dạy, đúng construct của câu hỏi nghiên cứu |
| `trajectory_score` | BFCL tool-use /100 | process conformance — construct khác |
| `total_score` | `0.7·ADDIE + 0.3·Traj` | số canonical của ISD-Agent-Bench, báo để so sánh được với benchmark đó |

Cả ba nhận **thống kê y như nhau**: paired Wilcoxon per-scenario (mean-of-runs, exact null khi n≤25), Holm theo từng
cặp (tín hiệu × policy) với family = 6 so sánh, bootstrap CI 95% (10k, seed 42), rank-biserial, và **ba failure
policy** (complete-case / failure=0 / failure=min). Trọng số 0.7–0.3 của composite đến từ benchmark chứ không từ câu
hỏi nghiên cứu này, nên nó không giữ vai thước dẫn — nhưng vẫn báo đủ 4 size × 6 so sánh × 3 policy để người đọc tự
kiểm được mọi kết luận.

**RQ2 — panel 7 tín hiệu phẳng, không endpoint chính**, hai họ instrument độc lập cơ chế (họ A textual
correspondence do encoder đo; họ B cognitive demand do Bloom classifier đo). Hai định nghĩa phải nêu rõ: các tín hiệu
họ A là **mean-max cosine đã rectify** `max(0, cos)` trên [0,1] — đây là chọn thang, **không** phải ngưỡng khớp, và
protocol không có ngưỡng ở bất kỳ đâu; `porter_mean` là **trung bình của ba chỉ số Porter đôi một**
(mục tiêu↔đánh giá / ↔hoạt động / ↔lượng giá), không phải một chỉ số đơn. Multiplicity báo hai tầng: `p_holm`
trong từng tín hiệu và `p_holm_panel` trên toàn panel × baseline. Đặc tả: `docs/rq2_protocol.md`.

## 0. Audit + output failure

`04_audit_postrun.py`: 12/12 run OK về cấu trúc và judge. Scoring alignment phủ **1080/1080** scenario-file cho **cả
5 arm** instrument, mỗi arm đúng một cấu hình `(encoder, revision, bloom_classifier)` — pooling không phải hard-fail
vì trộn cấu hình. Score file ghi tổng **453** cell `missing_outputs` (agent có log nhưng không có output).

Số scenario mà agent thiếu output ở ≥1 run (Fisher exact hai phía vs harness, Holm/6 trong size):

| Size | baseline | eduplanner | rpisd | dick-carey | react-isd | addie-agent | **harness** |
|---|---|---|---|---|---|---|---|
| 0.8B | **85**/90 (p<1e-4) | **83**/90 (p<1e-4) | 2 | 0 | 0 | 0 | **0** |
| 2B | **43**/90 (p<1e-4) | **33**/90 (p<1e-4) | 0 | 0 | 0 | 0 | **0** |
| 4B | 8 (p=0.033) | 13 (p=9e-4) | 0 | 1 | 0 | 0 | **0** |
| 9B | 4 (n.s.) | 5 (n.s.) | 0 | 0 | 0 | 0 | **0** |

Đây là kết quả **mạnh và không phụ thuộc thước đo nào**: ở 0.8B hai hệ prompt-một-lượt (baseline, EduPlanner) hỏng
92–94% scenario, trong khi harness và các hệ có cấu trúc khác hỏng 0. Mọi so sánh điểm với baseline/eduplanner ở 0.8B–2B
vì thế nằm trên n complete-case rất nhỏ (5 và 7 ở 0.8B) và **chỉ diễn giải được kèm layer failure-imputed**.

## 1. RQ1 — chất lượng nội dung (ADDIE) theo thang model

**ADDIE — thước dẫn** (trung bình per-scenario, mean-of-runs, complete-case; `n` = scenario đủ cả 3 run):

| Agent | 0.8B | 2B | 4B | 9B |
|---|---|---|---|---|
| **AlignmentGraph-ISD** | **80.46** | **84.69** | **85.88** | 86.23 |
| ReAct-ISD | 77.48 | 82.19 | 85.08 | **86.30** |
| Dick-Carey-Agent | 79.74 | 79.62 | 81.84 | 78.88 |
| RPISD-Agent | 77.79 | 79.69 | 81.03 | 81.48 |
| ADDIE-Agent | 73.55 | 76.98 | 79.82 | 80.42 |
| Baseline | 44.52 *(n=5)* | 57.82 *(n=47)* | 78.68 *(n=82)* | 83.45 *(n=86)* |
| EduPlanner | 46.61 *(n=7)* | 55.12 *(n=57)* | 77.61 *(n=77)* | 80.31 *(n=85)* |

Harness dẫn ở **3/4 size**, ngang ở 9B. Paired Δ (harness − đối sánh), complete-case, `*` = p_holm < 0.05:

| Size | vs react-isd | vs dick-carey | vs rpisd | vs addie-agent | vs baseline | vs eduplanner |
|---|---|---|---|---|---|---|
| 0.8B | **+2.98\*** | +0.72 | +2.64\* | +6.91\* | +34.92 *(n=5)* | +33.33\* *(n=7)* |
| 2B | **+2.51\*** | +5.07\* | +5.00\* | +7.72\* | +26.83\* | +29.43\* |
| 4B | **+0.80\*** | +4.02\* | +4.85\* | +6.06\* | +7.15\* | +8.25\* |
| 9B | −0.08 | +7.34\* | +4.75\* | +5.80\* | +2.72\* | +5.98\* |

Dưới layer **failure=0** ở 0.8B, Δ vs baseline = **+61.35** và vs eduplanner = **+61.28** (cả hai p_holm = 1.3e-15) —
đây là con số phản ánh đúng việc hai hệ đó gần như không sinh được output dùng được ở size nhỏ.

**Vế scale — DiD ADDIE (9B − 0.8B)** trên delta paired per-scenario:

| So với | DiD | CI95 | p | Δ theo size (0.8B→9B) |
|---|---|---|---|---|
| react-isd | **−3.06** | [−3.82, −2.26] | 5.6e-10 | +2.98 → +2.51 → +0.80 → −0.08 |
| eduplanner | −28.85 | [−35.38, −21.99] | 1.6e-02 | +33.3 → +29.4 → +8.3 → +6.0 |
| baseline | −32.56 | [−42.16, −23.82] | 6.2e-02 *(n=5)* | +34.9 → +26.8 → +7.2 → +2.7 |
| addie-agent | −1.11 | [−2.26, −0.01] | 2.1e-01 | +6.9 → +7.7 → +6.1 → +5.8 |
| rpisd-agent | +2.13 | [+1.45, +2.80] | 2.3e-07 | +2.6 → +5.0 → +4.9 → +4.8 |
| dick-carey-agent | +6.63 | [+5.74, +7.52] | 8.9e-16 | +0.7 → +5.1 → +4.0 → +7.3 |

DiD **âm có ý nghĩa với đối sánh mạnh nhất (react-isd, p=5.6e-10)** và âm với baseline/eduplanner → lợi thế về chất
lượng nội dung **nới rộng về phía model nhỏ**, đúng giả thuyết thiết kế. Với dick-carey và rpisd thì DiD dương: hai hệ
này không cải thiện theo size (dick-carey còn tụt: 79.74 → 78.88), nên delta tăng vì *chúng* đứng yên, không phải vì
harness mạnh thêm — phải diễn giải đúng như vậy.

### 1b. Trajectory và composite — báo đầy đủ

| Tín hiệu | Agent | 0.8B | 2B | 4B | 9B |
|---|---|---|---|---|---|
| Trajectory | harness | 83.85 | 88.80 | 89.99 | 90.16 |
| | react-isd | **92.87** | **93.07** | **93.05** | **93.06** |
| Total | harness | 81.48 | **85.93** | 87.11 | 87.41 |
| | react-isd | **82.10** | 85.45 | **87.47** | **88.33** |

Bóc tách harness − react-isd:

| Size | ΔADDIE | ΔTraj | ΔTotal |
|---|---|---|---|
| 0.8B | **+2.98** | −9.02 | −0.62 |
| 2B | **+2.51** | −4.27 | +0.47 |
| 4B | **+0.80** | −3.06 | −0.36 |
| 9B | −0.08 | −2.89 | −0.92 |

**Toàn bộ khoảng cách composite của harness so với react-isd là khoảng cách Trajectory, không phải nội dung.** Trên
composite, harness chỉ thắng ở 2B và thua có ý nghĩa ở 9B (−0.92, p=2.2e-10); DiD composite vs react-isd = −0.30
[−0.92, +0.35], p=0.17 → **không có tương tác**. Nói cách khác: nếu đọc bằng composite thì hiệu ứng scale biến mất,
vì thành phần Trajectory (harness thấp đều ở mọi size) triệt tiêu nó. Đây là lý do kỹ thuật, ngoài lý do construct,
để không dùng composite làm thước dẫn.

Trajectory thấp của harness là kết quả **cần khai, không nên bào chữa**: kiến trúc nhiều tác tử với vòng verify+repair
tạo trajectory dài và ít "gọn" hơn theo tiêu chí BFCL so với một vòng ReAct đơn.

## 2. RQ2 — panel 7 tín hiệu alignment

Cấu hình chính: encoder `nvidia/llama-embed-nemotron-8b` (API), Bloom arm `bertbloom`. Harness vs **đối sánh tốt nhất
trong từng ô**. Cột "worst p_holm" bên dưới là p_holm lớn nhất trên **toàn panel** (7 tín hiệu × 6 đối sánh) tại size
đó, không phải trong riêng một tín hiệu.

| Tín hiệu | Họ | 0.8B | 2B | 4B | 9B |
|---|---|---|---|---|---|
| `objective_assessment_similarity` | A | **0.851** vs 0.595 | **0.850** vs 0.606 | **0.806** vs 0.608 | **0.832** vs 0.592 |
| `objective_activity_similarity` | A | **0.697** vs 0.445 | **0.680** vs 0.542 | **0.686** vs 0.545 | **0.678** vs 0.572 |
| `objective_evaluation_similarity` | A | **0.806** vs 0.596 | **0.806** vs 0.608 | **0.789** vs 0.608 | **0.811** vs 0.586 |
| `assessment_objective_similarity`† | A | **0.682** vs 0.528 | **0.652** vs 0.541 | **0.663** vs 0.564 | **0.693** vs 0.570 |
| `objective_cognitive_congruence` | B | **0.813** vs 0.766 | **0.865** vs 0.756 | **0.918** vs 0.791 | **0.918** vs 0.795 |
| `porter_mean` | B | **0.433** vs 0.355 | **0.448** vs 0.359 | **0.446** vs 0.393 | **0.458** vs 0.393 |
| `webb_bloom_consistency` | B | 0.682 vs **0.846** | 0.724 vs **0.761** | **0.871** vs 0.761 | **0.866** vs 0.765 |

† = diagnostic, hướng không đơn nghĩa (rất cao có thể là "không item mồ côi" mà cũng có thể là "assessment chép lại
objective") — đọc kèm, không tính vào đếm "thắng bao nhiêu vế".

**Tổng kết dẫn đầu và multiplicity:**

| Size | Harness dẫn | worst p_holm | worst p_holm_panel |
|---|---|---|---|
| 0.8B | 6/7 | 6.2e-02 | 7.3e-02 |
| 2B | 6/7 | 5.4e-02 | 5.4e-02 |
| 4B | **7/7** | 8.2e-06 | 8.2e-06 |
| 9B | **7/7** | 2.4e-08 | 2.4e-08 |

Ở 4B và 9B harness dẫn **cả 7 tín hiệu** và sống cả dưới hiệu chỉnh Holm trên toàn panel. Ở 0.8B và 2B thì **6/7**.

**Tín hiệu harness thua, phải báo:** `webb_bloom_consistency` ở 0.8B (0.682 vs dick-carey 0.846; paired Δ = −0.164
[−0.196, −0.130], **p_holm = 1.1e-11 nghịch harness**) và ở 2B (−0.036 [−0.068, −0.005], p_holm = 0.054, n.s.). Webb
là chỉ số **item-centric**: nó tính tỉ lệ assessment item có mức Bloom ≥ mức của objective gần nhất. Harness sinh
nhiều item hơn hẳn (≈22 item/scenario ở 0.8B so với ≈5 của dick-carey), nên mẫu số lớn hơn nhiều và những item mức
thấp (recall/hiểu) bị đếm vào. Đây là một mặt mà harness thực sự kém ở model nhỏ, và là ví dụ cụ thể cho lý do panel
tốt hơn một endpoint duy nhất: một endpoint đơn lẻ sẽ ém mất nó.

**Vế scale — DiD `objective_assessment_similarity` (9B − 0.8B)**: âm với **5/6** đối sánh nhưng **có ý nghĩa ở 4/6** (react-isd −0.086
p=4.8e-08; dick-carey −0.135 p=1.8e-15; baseline −0.484 p=6.5e-13; eduplanner −0.251 p=8.6e-11; addie-agent −0.010
n.s.), ngoại lệ rpisd +0.039 (p=1.3e-04, do rpisd tụt theo size). Khoảng cách `objective_assessment_similarity` **nới rộng về phía model nhỏ**.

## 3. Robustness: 3 trục sensitivity + validity evidence

Sweep hình sao (mỗi arm lệch đúng một trục khỏi cấu hình chính), phủ 1080/1080 mỗi arm:

| Arm | Trục | Đo agreement trên | min ρ | Harness top-1 |
|---|---|---|---|---|
| `lexicon` | Bloom (họ B) | `objective_cognitive_congruence` | 0.679 | 4/4 |
| `bgem3` | encoder | `objective_assessment_similarity` | 0.607 | 4/4 |
| `granite` | encoder | `objective_assessment_similarity` | 0.750 | 4/4 |
| `tfidf` | encoder (sàn không-ngữ-nghĩa) | `objective_assessment_similarity` | 0.607 | 4/4 |

**Harness đứng nhất ở 16/16 ô** (4 arm × 4 size), min Kendall τ-b = 0.524. Worst Holm p qua **cả hai trục**, mỗi arm đọc trên tín hiệu của trục mình = **1.7e-02**
(arm `lexicon` @0.8B); riêng 3 arm trục encoder trên `objective_assessment_similarity` thì worst = 3.6e-13. Trục Bloom được đo trên tín hiệu **họ B** — đo trên tín hiệu họ A sẽ cho ρ = 1.000 một cách hiển nhiên (đổi
Bloom classifier không làm đổi similarity), tức một con số rỗng.

**Hai Bloom arm khác nhau thật** (không phải bản sao): trên 3 755 dòng held-out của EDM2022CLO, `bertbloom` κ = 0.926
/ coverage 100% / accuracy 94.1%; lexicon κ = 0.650 / 83.4% / 72.3%; **đồng thuận giữa hai arm chỉ 73.5% raw, κ =
0.665**. Artifact: `docs/generated/bloom_arms_validation.md`.

**Validity evidence của harness** (không phải tín hiệu panel — đo instrument, không đo agent):

| Size | `declared_link_agreement` | `bloom_vs_declared_agreement` |
|---|---|---|
| 0.8B | 0.782 | 0.709 |
| 2B | 0.752 | 0.880 |
| 4B | 0.856 | 0.903 |
| 9B | 0.902 | 0.971 |

Cả hai tăng theo size: model lớn viết cấu trúc link và nhãn mức nhận thức tự khai sạch hơn, và việc matching bằng
similarity tái tạo đúng link tự khai tới 90% ở 9B — bằng chứng hội tụ cho khâu matching (link tự khai **không bao giờ**
dùng để chấm).

## 4. Chi phí vận hành

Tổng token trung bình mỗi scenario (metadata, **không** vào bất kỳ điểm nào):

| Agent | 0.8B | 2B | 4B | 9B |
|---|---|---|---|---|
| react-isd | 10 563 | 6 573 | 6 406 | 6 195 |
| baseline | 8 685 | 9 370 | 11 376 | 12 168 |
| dick-carey | 18 642 | 17 087 | 19 334 | 19 073 |
| addie-agent | 19 661 | 20 049 | 20 180 | 21 435 |
| **harness** | **33 027** | **24 458** | **21 973** | **22 583** |
| rpisd-agent | 28 648 | 33 878 | 37 501 | 38 981 |
| eduplanner | 45 145 | 52 342 | 63 682 | 60 737 |

Harness tốn ~3.6× react-isd ở 9B và ~3.1× ở 0.8B — đây là cái giá của phân rã nhiều tác tử cộng vòng verify+repair, và
phải nêu như một đánh đổi thật. Đáng chú ý: token của harness **giảm** khi model lớn lên (33k → 22.6k) vì ít lượt
regen/repair hơn, ngược với rpisd và eduplanner (tăng theo size). `execution_time_seconds` **không** dùng để so sánh —
nó phản ánh tải serving, không phản ánh phương pháp.

## 5. Ablation — cơ chế nào chịu lực?

4 arm chạy **bên trong chính run của ladder** (cùng judge session, cùng scenario), nên không có caveat judge-drift.
Kiểm tra invariant A0: `ablation − ladder Δ = +0.00` ở mọi size.

**Trên ADDIE (thước dẫn RQ1):**

| Arm | 0.8B | 2B | 4B | 9B |
|---|---|---|---|---|
| A0 — full | 80.46 | 84.69 | 85.88 | 86.23 |
| A1 — −Verifier | 80.11 | 84.82 | 85.84 | 86.10 |
| A2 — −GraphContext | 81.70 | 84.78 | 86.06 | 86.13 |
| A3 — skeleton (tắt cả hai) | 81.47 | 84.88 | 86.41 | 86.30 |

Δ (arm − A0), Holm/3 trong size: **không arm nào khác biệt đáng kể theo hướng "gỡ ra thì tệ hơn"**. |Δ| ≤ 1.24 ở mọi
ô; hai chỗ có ý nghĩa lại **dương** (A2 +1.24 p=3.8e-03 ở 0.8B; A3 +0.53 p=4.2e-04 ở 4B), tức gỡ cơ chế ra thì judge
chấm nhích lên.

**Trên `objective_assessment_similarity` (RQ2):**

| Arm | 0.8B | 2B | 4B | 9B | p_holm vs A0 |
|---|---|---|---|---|---|
| A0 — full | **0.851** | **0.850** | 0.806 | **0.832** | — |
| A1 — −Verifier | 0.835 | 0.841 | **0.811** | 0.827 | 0.083 / 0.22 / 0.67 / 0.32 → **n.s. mọi size** |
| A2 — −GraphContext | 0.751 | 0.700 | 0.717 | 0.755 | 1.6e-14 / 6.7e-16 / 1.2e-12 / 1.0e-13 |
| A3 — skeleton | 0.671 | 0.635 | 0.648 | 0.704 | 6.7e-16 mọi size |

**Verifier: đọc theo 2×2 chứ không theo "vs A0".** *(Số sinh tự động: `tab_ablation_factorial.tex`,
macro `\ablVerifCtxOff*` / `\ablInteraction*` / `\ablRepairs*`, hình `fig_ablation_factorial`, dump đầy đủ trong
`facts.md` §5.3 hoặc `stats_ablation.md` §"2x2 factorial".)* 4 arm là một **thiết kế giai thừa 2×2 đầy đủ** (verifier × graph
context). Chỉ so từng arm với A0 là đọc *main effect*, và nó giấu mất thứ quan trọng nhất. Tách hiệu ứng của verifier
theo từng điều kiện graph-context (paired per-scenario, n=90):

| Size | ctx BẬT: A0−A1 | p¹ | ctx TẮT: A2−A3 | p¹ | Tương tác | p¹ |
|---|---|---|---|---|---|---|
| 0.8B | +0.016 | 0.083 | **+0.080** | 7.8e-12 | −0.065 | 2.3e-05 |
| 2B | +0.010 | 0.22 | **+0.065** | 3.0e-12 | −0.055 | 1.9e-06 |
| 4B | −0.005 | 0.67 | **+0.069** | 8.5e-13 | −0.075 | 1.3e-10 |
| 9B | +0.005 | 0.32 | **+0.051** | 1.7e-13 | −0.046 | 1.5e-08 |

¹ p Wilcoxon hai phía **không hiệu chỉnh** — đây là contrast cấu trúc tiền định của thiết kế 2×2, không phải một
family so-sánh-với-A0 (khác với các bảng arm-vs-A0 ở trên, vốn dùng Holm). Lưu ý `V|ctx bật` **chính là** contrast
A0−A1, nên bản Holm của nó có trong bảng arm-vs-A0.

**Tương tác có ý nghĩa ở cả 4 size** (CI đều loại trừ 0), rank-biserial của hiệu ứng khi ctx tắt là 0.83–0.90 — hiệu
ứng **lớn**, không phải biên. Verifier hoàn toàn không vô dụng.

**Nhưng thay thế KHÔNG đồng đều trên panel** — chạy factorial trên **cả 10 tín hiệu được báo cáo** (3 judge + 7 panel;
artifact `tab_ablation_factorial_full.tex`) cho thấy pattern phụ thuộc tín hiệu, và đây là thứ mà việc chỉ chạy một
tín hiệu sẽ giấu mất:

| Tín hiệu | V\|ctx bật có ý nghĩa | V\|ctx tắt có ý nghĩa | Tương tác có ý nghĩa | Biên độ V\|ctx tắt |
|---|---|---|---|---|
| `objective_assessment_similarity` | 0/4 | **4/4** | **4/4** | +0.051 … +0.080 |
| `objective_evaluation_similarity` | 1/4 | **4/4** | **4/4** | +0.070 … +0.143 |
| `assessment_objective_similarity` | 0/4 | **4/4** | **4/4** | +0.026 … +0.038 |
| `porter_mean` | 0/4 | **4/4** | **4/4** | +0.029 … +0.067 |
| `objective_cognitive_congruence` | 0/4 | 3/4 | 2/4 | +0.011 … +0.070 |
| `webb_bloom_consistency` | 0/4 | 2/4 | 1/4 | +0.006 … +0.034 |
| `objective_activity_similarity` | 0/4 | **0/4** | **0/4** | −0.004 … +0.005 |
| `addie_median` | 0/4 | 1/4 | 0/4 | −0.352 … +0.223 |
| `trajectory_score` | 4/4 | 3/4 | 4/4 | **−3.10 … −0.61** |
| `total_score` | 3/4 | 3/4 | 2/4 | −1.05 … −0.03 |

Ba điều phải khai từ bảng này:

1. **Cơ chế thay thế chỉ áp cho các vế liên quan đánh giá** — objective↔assessment, ↔evaluation, chiều ngược, và
   Porter. Trên vế **hoạt động** (`objective_activity_similarity`) verifier **không có tác dụng ở bất kỳ điều kiện
   nào** (|Δ| ≤ 0.005, 0/4 có ý nghĩa). Hợp lý: các kiểm tra của verifier tập trung vào quan hệ mục tiêu–đánh giá và
   tầng Bloom, không kiểm quan hệ mục tiêu–hoạt động. Nên phát biểu đúng là *"verifier bù cho graph context **trên
   những quan hệ mà nó thật sự kiểm**"*, không phải bù toàn diện.
2. **Verifier làm giảm điểm Trajectory có ý nghĩa** (−0.61 … −3.10, 3/4 size khi ctx tắt và 3/4 khi ctx bật) và kéo
   theo composite `total_score` (−0.03 … −1.05). Ngoại lệ phải khai: ở **0.8B với ctx bật** verifier lại **tăng**
   Trajectory (+1.43, p=0.042) — chiều hiệu ứng không đồng nhất qua size. Đây là chi phí đo được của vòng verify+repair trên thước process
   conformance — phải báo, không được lờ.
3. **Trên ADDIE thì gần như không có gì**: 1/4 ô có ý nghĩa và theo chiều **âm**. Verifier không mua được điểm judge.

**Cơ chế xác nhận bằng số lần sửa thực tế** (đọc từ `verifier_events` / `repair_events` trong trajectory, 270
scenario-run mỗi ô):

| Arm | Số lần verifier chạy | Số lần **sửa** 0.8B → 9B |
|---|---|---|
| A0 (ctx bật) | 6.2–7.4 / scenario, **100%** scenario | 3.73 → 2.29 → 1.30 → **1.31** |
| A2 (ctx tắt) | 7.3–7.9 / scenario, **100%** scenario | 4.65 → 3.83 → 3.43 → **3.92** |

Khi graph context bật, **số lỗi cần sửa giảm ~2.8× theo size** (3.73 → 1.31) — model lớn cộng graph context thì gần như
không sinh vi phạm. Khi graph context tắt, số lần sửa **đứng yên ở mức cao** (3.92 ở 9B, gấp 3 lần A0 cùng size):
cùng một verifier, gấp ba khối lượng việc.

**Kết luận ablation:**

1. **Graph context là cơ chế chịu lực chính.** Gỡ ra giảm 0.08–0.15 với p_holm 1e-12…1e-16 ở mọi size, và simple
   effect của nó **dương có ý nghĩa dưới cả hai trạng thái** của verifier (+0.076…+0.206) — nó không phụ thuộc cơ chế
   kia. **Nhưng có đánh đổi phải khai**: trên ADDIE, graph context **làm giảm** điểm judge ở 0.8B (−1.24 khi verifier
   bật, p=1.3e-03; −1.36 khi tắt, p=6.8e-04). Tức ở model nhỏ nhất, nó đổi ~1.2 điểm rubric lấy +0.10 similarity.
2. **Verifier là cơ chế sửa lỗi thật, dư thừa khi graph context còn nguyên — nhưng chỉ trên những quan hệ nó kiểm.** Hai cơ chế tấn công **cùng một
   dạng lỗi từ hai đầu**: graph context **phòng ngừa** (bơm trạng thái vào prompt trước khi sinh), verifier **sửa
   chữa** (soát và vá sau khi sinh). Chúng là *substitute*, không phải *complement* — nên khi phòng ngừa hoạt động,
   sửa chữa gần như không còn việc. Phải khai đúng chữ: trên cấu hình được ship (A0), **verifier tốn token mà không
   đổi được điểm**; giá trị của nó là **backstop cho điều kiện mà graph context không phủ**, cộng audit trail. Đây là
   claim về một cấu hình phản thực, và phải viết đúng như vậy.
3. **Judge không "nhìn thấy" alignment.** Cùng tập arm: ADDIE gần như bất biến (spread ≤ 1.58 điểm) trong khi
   `objective_assessment_similarity` dịch tới 0.215. Đây là luận điểm tồn tại của protocol RQ2 — nhưng cũng có nghĩa **đóng góp của harness không bán
   được bằng bất kỳ thước judge nào**, kể cả ADDIE.

## 6. Mức claim tương ứng bằng chứng

**Nói được:**

- Harness **dẫn đầu chất lượng nội dung (ADDIE) ở 3/4 size**, ngang đối sánh mạnh nhất ở 9B; lợi thế so với react-isd
  **nới rộng về phía model nhỏ** (DiD −3.06, p=5.6e-10, n=90). Phải kèm caveat: ở 0.8B lead so với đối sánh mạnh nhất
  theo cột (Dick-Carey) **chưa có ý nghĩa** (+0.72, CI [−0.11, +1.54], p_holm=0.125).
- Harness **dẫn toàn bộ panel ở 4B/9B (7/7)**, sống dưới Holm toàn panel ở hai size này (worst `p_holm_panel`
  8.2e-06 / 2.4e-08), và 6/7 ở 0.8B/2B — nhưng ở hai size nhỏ tín hiệu yếu nhất **không** sống dưới Holm toàn panel
  (`p_holm_panel` 0.073 ở 0.8B, 0.054 ở 2B), nên claim "sống dưới Holm toàn panel" chỉ phát biểu được cho 4B/9B.
- **Thứ hạng không phụ thuộc instrument**: 16/16 ô qua 4 arm sensitivity (gồm sàn TF-IDF không-ngữ-nghĩa và đổi hẳn
  Bloom classifier). Hiệu lực thống kê gần như bất biến nhưng **không tuyệt đối**: 1/24 verdict Holm đổi (arm
  `lexicon` @0.8B, 5/6 verdict giữ), và worst Holm p qua cả hai trục là 0.017.
- Harness **không hỏng output lần nào** trên 1080 cell, trong khi hai hệ prompt-một-lượt hỏng 92–94% scenario ở 0.8B.
- **Graph context là cơ chế tạo ra tín hiệu alignment** — không riêng textual correspondence: gỡ nó ra (A2) làm
  **28/28 ô của panel** (7 tín hiệu × 4 size) giảm và **cả 28 đều có ý nghĩa** dưới Holm toàn panel (Δ −0.073…−0.249;
  riêng obj→assessment p_holm ≤ 1.2e-12 mọi size). Roll-up: facts §2.3.

**Không nói được:**

- Không nói harness tốt hơn trên **composite** `total_score`: nó thua react-isd có ý nghĩa ở **cả 4B (−0.36,
  p_holm=1.9e-03) và 9B** (−0.92, p=2.2e-10) — ở 0.8B (−0.62) thì n.s. (p_holm=0.125) — và hiệu ứng scale trên
  composite không có ý nghĩa (p=0.17).
- Không nói harness tốt hơn trên **Trajectory**: thua react-isd ở mọi size (−2.9 … −9.0).
- Không nói harness dẫn **mọi** tín hiệu alignment ở mọi size: thua `webb_bloom_consistency` ở 0.8B (p_holm=1.1e-11
  nghịch harness) và 2B (n.s.).
- Không nói **verifier** cải thiện chất lượng hay alignment **trên cấu hình được ship (A0)**: n.s. trên cả hai thước
  ở mọi size. Nhưng cũng **không nói nó vô dụng** — nó chạy 100% scenario, sửa 1.3–3.9 lỗi/scenario, và khi graph
  context vắng mặt thì nó bù lại +0.051…+0.080 (p ≤ 8e-12, r_rb 0.83–0.90). Câu đúng là: **cơ chế dư thừa, không phải
  cơ chế vô hiệu**.
- Không claim alignment tuyệt đối ("đạt đủ ăn khớp") — mọi claim RQ2 ở mức **tương đối** giữa các hệ và theo scale;
  mức tuyệt đối chỉ báo descriptive.
- Không claim đo **learning outcome**: protocol là operationalization tự động của tiêu chí thiết kế, không đo kết quả
  học tập của người học.

**Giới hạn phải khai:**

- **Phiên bản trọng số encoder (thông tin để tái hiện).** Lần chấm này dùng đúng các commit sau; ghi ra đây để người
  khác dựng lại được cùng điều kiện:

  | Encoder | Revision | Căn cứ |
  |---|---|---|
  | `nvidia/llama-embed-nemotron-8b` | `aa3b43a495a9b280d1bdb716da37c54bb495d630` | `main` trên HF, `lastModified` 2026-04-23 — trước đợt chấm 2026-07-30 hơn 3 tháng, nên pod kéo đúng commit này |
  | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` | snapshot chứa trọng số trong HF cache của máy đã chấm |
  | `ibm-granite/granite-embedding-311m-multilingual-r2` | `44399559930365213510b1ee2eb15ded83374f0e` | như trên |
  | `tfidf` | — | là code trong repo, không có trọng số HF |

  Muốn ràng buộc cứng thay vì chỉ ghi lại: set `<SLOT>_EMBED_REVISION` trong `.env` **trước** khi chấm (placeholder do
  `05_sync_embed_pod_env.py` sinh sẵn và giữ nguyên qua mỗi lần re-sync). Khi đó revision đi vào cả `encoder_revision`
  của score file lẫn key của embedding cache, nên đổi revision là re-embed thật chứ không phải dán nhãn mới.
- Arm Bloom chính là một **checkpoint học từ quy ước mã hoá của một trường** (κ 0.926 với corpus đó), chưa được validate
  trên objective do agent sinh ra, và **không giải thích được từng quyết định**; họ B do đó không còn tất định bit-wise
  (argmax rời rạc → nhiễu fp có thể lật một nhãn). Arm `lexicon` là đối trọng giải thích được.
- So sánh với baseline/eduplanner ở 0.8B–2B nằm trên n complete-case rất nhỏ → chỉ đọc được kèm layer failure-imputed.
- Layer chính của RQ2 là **complete-case trên output có sẵn**, không phải unconditional; phải đọc kèm failure=0.
- Similarity **không phải** alignment: 4 tín hiệu họ A đo textual correspondence, cầu nối sang construct nằm ở tầng
  bằng chứng (§3), không nằm ở tên metric.
