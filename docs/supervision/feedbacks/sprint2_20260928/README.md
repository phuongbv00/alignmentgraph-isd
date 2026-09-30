# Sprint 2 — Nhận xét của GVHD và giao thức thực nghiệm thống nhất

> Bản đọc được của `Nx_Sprint2_định_hướng.docx` trong chính thư mục này. File DOCX là nguồn thẩm
> quyền. File này tồn tại vì DOCX không diff được trong git và không grep được khi viết bài.
>
> Nhận ngày 2026-09-28. Khi lệch với nhận xét Sprint 1 (`../sprint1_20260828_0908/`) thì file này
> thắng: nó thay thế thiết kế thí nghiệm của Sprint 1. Luật viết bài rút ra từ đây nằm ở
> `docs/paper/claim-rules.md`, việc phải làm nằm ở `docs/supervision/backlog.md` (nhóm S).

## 1. Kết luận chốt

- **Chưa phê duyệt chạy lại TN1/TN2.** Chỉ phê duyệt chạy chính thức sau khi đạt Gate 1 và Gate 2.
- Tiếp tục **PA2**: graph-guided multi-agent harness với SLM.
- **Q2 là mức đầu ra tối thiểu**, không phải lý do hạ chuẩn khoa học. Giữ khả năng nâng lên Q1 nếu
  bằng chứng cho phép.
- **Không thêm tính năng mới, không tối ưu sau khi nhìn kết quả test chính thức.**
- Ưu tiên thí nghiệm one-shot, resumable, không phải rerun vì những lỗi có thể chặn trước.
- Báo đúng cả kết quả bất lợi: cost, Trajectory, cognitive congruence. Giá trị nghiên cứu phải đến
  từ bằng chứng về robustness, measurable alignment signals và auditability, không phải từ điểm số
  chọn hậu nghiệm.

## 2. Đánh giá kết quả Sprint 2

Hai thí nghiệm chính thức đã khởi chạy nhưng bị gián đoạn vì GPU RunPod exhausted. Không ô nào đủ
scenario. Dữ liệu dở dang chỉ dùng để chẩn đoán kỹ thuật, không được dùng làm kết quả khoa học,
cũng không được dùng làm căn cứ hậu nghiệm để chọn tham số.

Hai đợt tune trên `train_10`, Qwen3.5-9B:

| Tham số | Đợt 1 | Đợt 2 | Nhận xét của thầy |
|---|---|---|---|
| `ready_to_aggregate` | 8/10 | 10/10 | Hệ hoàn thiện khả năng kết xuất. |
| Stage `gave_up` | 0 | 0 | Duy trì được ở cả hai đợt. |
| C2/C3/C4 | 1,00/1,00/1,00 | 1,00/1,00/1,00 | Chỉ chứng minh coverage cấu trúc. |
| Token/run | 255k | 178k | Giảm khoảng 30%; chưa tách tác động của việc tắt thinking. |
| Thời gian/run | 533 s | 309 s | Giảm khoảng 42%; không thể quy hết cho harness. |
| LLM calls/run | 53,8 | 52,3 | Không giảm đáng kể. |
| Số test harness | 621 | 837 | Tăng phạm vi regression test. |

**Được ghi nhận:** sửa từ nguyên nhân gốc; loại các quan hệ không thể thất bại khỏi phần bằng
chứng; tách generation và evaluation; ghi `protocol_rev`, cache và manifest; phát hiện lỗi đo token
của baseline và lỗi extractor lẫn activity stub trước khi có kết quả chính thức; phản biện có căn
cứ đề xuất chỉ dùng một judge full.

**Chưa đạt:** chưa có kết quả TN1/TN2; mới tune 9B qua router trong khi trọng tâm là 0.8B–4B; bốn
arm ablation chưa qua tune; cost vẫn cao; `PROTOCOL_REV` còn thay đổi và chưa commit.

**Kết quả tune đợt 2** (chỉ là tune, không được dùng để kết luận trên quần thể scenario): ADDIE
84,6 (hệ đề xuất) so với 85,9 (ReAct-ISD); Total 85,7 so với 88,1. Alignment panel cao hơn ở 5/6
tín hiệu, nhưng cognitive congruence thấp hơn (0,760 so với 0,800).

## 3. Các vấn đề khoa học phải khóa trước khi chạy lớn

1. **Nhiễu của LLM judge.** Không dùng biên độ 10,8 điểm của Sprint 1 làm ngưỡng kiểm định hay căn
   cứ tuyên bố "tương đương". Phải tách ba nguồn biến thiên: giữa các lần sinh, giữa các lần judge
   chấm cùng một output, và giữa các scenario. Kết luận dựa trên phân tích ghép cặp, effect size, CI
   và multiplicity correction đã định trước.
2. **Tính độc lập của alignment panel.** C2–C4 = 1,00 là structural compliance, không chứng minh
   pedagogical validity. Nếu harness cưỡng chế một tiêu chí Bloom rồi chính tiêu chí đó được dùng
   làm evidence, phải công khai đó là phép kiểm sự phù hợp với ràng buộc, không phải xác nhận độc
   lập về chất lượng giáo dục. Kiểm tra bằng chuyên gia trên output ẩn danh, cùng một mẫu cho mọi hệ.
3. **Ablation là bundle.** Multi/single × graph/prose thay đổi cả một bundle cơ chế: multi còn có
   fan-out, Developer tier, replan, và thời điểm repair khác single. Chỉ suy luận về bundle đã thử,
   không quy nhân quả quá mức cho riêng "số agent" hay "graph".
4. **Thinking, router và backend.** Khóa thinking, temperature và decoding cho mọi hệ; lưu metadata
   của backend. Thinking bị tắt cùng lúc với các bản vá khác, nên không được claim toàn bộ mức giảm
   token là nhờ thuật toán.
5. **Output dài và trajectory.** Xác minh cả hai LLM judge nhận đủ output (có chunking nếu cần) và
   không chấm nhầm nội dung dài thành "vắng mặt". Báo Trajectory ở cap 20 (benchmark) song song với
   cap 120 (diagnostic, chấm offline). Không dùng Total làm thước đo duy nhất, vì giới hạn hiển thị
   tạo khác biệt với baseline chỉ khoảng 5 call.

## 4. Phản hồi ba đề xuất

**Hai LLM judge full — đồng ý.** Giữ GPT-4o-mini và Gemini 2.5 Flash-Lite trên toàn bộ output TN1.
Lưu điểm từng judge riêng, chốt trước phương thức gộp, chấm offline và cache theo hash output. Nếu
TN2 dùng ADDIE làm bằng chứng kết luận thì các output liên quan cũng phải chấm theo cùng quy tắc.
Với hai judge, median bằng trung bình cộng và không tự loại bias; cần chuyên gia để kiểm giá trị
của phép chấm.

**Cost cao hơn khoảng 12 lần — đưa vào limitation và trade-off.** Báo số tuyệt đối, tỷ lệ so với
ReAct-ISD, số call và thời gian, đặt cạnh measurable alignment signals, traceability và khả năng
audit. Không tuyên bố "chi phí được bù đắp" khi chưa có đánh giá người dùng chứng minh. Baseline
workflow và harness agentic khác cơ chế vận hành, nhưng điều đó không làm mất ý nghĩa so sánh
triển khai. Không được kết luận tiết kiệm chi phí. Mức giảm so với Sprint 1 không phải before–after
tương đương, vì cách đo token, kiến trúc và thinking đều đã đổi. Câu dùng trong manuscript (giữ
nguyên văn, đã chép vào `claim-rules.md` §4):

> *AlignmentGraph-ISD incurs substantial computational overhead relative to lightweight
> workflow-based baselines. We report this cost alongside its measurable alignment signals,
> structural traceability, and auditability, without interpreting the approach as computationally
> more efficient.*

**Light thay hoàn toàn full — không đồng ý. Thầy yêu cầu đặc biệt lưu ý điểm này.** Light chỉ phát
triển một lát cắt đại diện; full là thiết kế ở quy mô triển khai. Không được chấm light rồi claim
chất lượng một chương trình ADDIE hoàn chỉnh. Cụ thể:

- Light dùng cho tune và các phân tích phù hợp.
- Trước freeze phải so light với full trên cùng scenario, đặc biệt các rubric item phụ thuộc số
  lượng (12, 17, 19, 22, 30).
- Full cần một tập đánh giá độc lập, đủ đại diện.
- Mọi baseline phải được so trong phạm vi output tương thích.
- Chỉ dùng light làm đánh giá chính cho một claim giới hạn rõ ràng, và chỉ sau khi có bằng chứng
  xác nhận tính đại diện.

## 5. Giao thức thực nghiệm thống nhất

Thay thế đề xuất trước đây. Nguyên tắc: chất lượng khoa học trước. Tiết kiệm bằng cách loại rerun,
chấm offline, kiểm thử sớm và lặp có mục tiêu, không cắt những yếu tố quyết định độ tin cậy. Sinh
dùng temperature 0,7, nên **một run không được gọi là deterministic**, và bootstrap theo scenario
không thay thế hoàn toàn việc đo biến thiên giữa các lần sinh.

| Thành phần | Quyết định chốt |
|---|---|
| TN1: ladder | 4 size × 7 hệ × 90 scenario, **một run chung** cho cả bảy hệ. **A0 và ReAct-ISD chạy thêm hai lần độc lập** trên toàn bộ 4 size × 90 scenario. |
| TN2: ablation | 2 size (0.8B, 4B) × 4 arm × 30 scenario × **3 run độc lập**; A0 chạy ngay trong TN2. |
| LLM judge | Hai judge full cho TN1, chấm từ output đã lưu. Trajectory cap 20 là benchmark, cap 120 là diagnostic; không sinh lại. |
| Alignment panel | Cấu hình chính chấm mọi output chấm được; sensitivity (encoder/Bloom) chấm từ output đã lưu, không sinh lại. |
| Thống kê | Tầng chung 7 hệ dùng run chung, so sánh ghép cặp theo scenario. Phân tích repeat của A0/ReAct làm riêng, không coi ba lần sinh của cùng một scenario là ba scenario độc lập. |
| Failure | Failure = 0 là layer triển khai nếu đã định trước; complete-case chỉ là sensitivity; báo riêng fail rate và nguyên nhân. |
| Expert validation | 3–5 chuyên gia, chấm ẩn danh, mẫu phân tầng. Tiêu chí: constructive alignment, feasibility, audit usefulness, thời gian sửa. |

Khối lượng generation theo kế hoạch: TN1 = 4 × 90 × (3 + 3 + 5 × 1) = 3.960 scenario-run; TN2 =
2 × 4 × 30 × 3 = 720; tổng 4.680 (thiết kế cũ là 8.280). Đây là khối lượng, không phải dự báo ngân
sách; ước lượng token/giờ và dự phòng failure lấy từ tune sau freeze.

**Ranh giới suy luận:** bảng so sánh bảy hệ chỉ dùng bộ run chung. Hai repeat bổ sung chỉ để kiểm
độ ổn định của A0 và ReAct-ISD. Không lấy 3 run của A0 so với 1 run của các baseline khác như thể
đó là thiết kế lặp cân bằng.

## 6. Lộ trình Sprint 3 và các gate

| Giai đoạn | Nội dung | Gate chuyển bước |
|---|---|---|
| 1. Hoàn tất protocol | Sửa quy đổi thời lượng và kế hoạch evaluation/summative; đọc trajectory của hai scenario điểm thấp. Tune `train_10` ở cả light và full, thêm 0.8B và 4B, đủ bốn arm ablation. Không dùng `test_90`/`test_30` để tune. | **Gate 1:** mọi arm hoàn tất được; không có lỗi parse/fallback/`gave_up` bất thường; output cap, thinking, budget, scope light/full và cost đã định nghĩa; không còn thay đổi phương pháp nào đang chờ. |
| 2. Freeze và preflight | Chốt judge roster, hai lớp trajectory, sáu tín hiệu panel, failure policy, thống kê, run design. Khóa code/prompt/model/config/split/protocol_rev. Kiểm split disjoint; smoke test cache/resume, chấm offline và chuyển backend. | **Gate 2:** manifest, checksum, test package, preflight và ước lượng chi phí đều Pass. Mọi thay đổi sau freeze phải ghi lý do và phạm vi ảnh hưởng. |
| 3. TN1 chính thức | Chạy rung nhỏ trước, checkpoint từng scenario, không trộn protocol version; lưu generation, trajectory, token, judge và panel riêng. GPU bị ngắt thì resume ô còn thiếu; đổi backend thì phải xác minh cấu hình suy luận tương đương. | **Gate 3:** đủ coverage các ô; không còn output lỗi chưa giải trình; bảng sinh tự động từ artifact đã khóa. |
| 4. TN2 + expert | Chạy factorial và repeat; chọn mẫu ẩn danh cho 3–5 chuyên gia; kiểm các ca phản ví dụ, trade-off cost/failure/quality và điều kiện đại diện light/full. | **Gate 4:** phân tích đúng đơn vị scenario, báo CI/effect size/multiplicity, không bỏ kết quả bất lợi. |
| 5. Manuscript | Đồng bộ toàn bộ manuscript với phương pháp mới (17 quan hệ: 3 core, 14 phụ); hoàn thiện Related Work, Discussion, Threats, Conclusion, bản reproducibility; rà soát claim. | **Gate 5:** không còn TBD; không lệch code–paper–artifact; bản tiếng Anh đúng template tạp chí; không tuyên bố vượt bằng chứng. |
