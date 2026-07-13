# Báo cáo về sự thay đổi phát biểu bài toán

## 1. Bối cảnh cho lý do thay đổi

Đề tài khởi đầu là bài toán **controlled refinement** — chỉnh sửa chương trình
ISD do LLM sinh ra qua nhiều phiên. Tuy nhiên trong trong quá trình thực nghiệm, 3
quan sát hội tụ khiến việc **thu hẹp và tái định vị phát biểu bài toán** trở nên
hợp lý hơn:

**(a) Bằng chứng mạnh nhất đã có nằm ở chất lượng single-pass, không ở refinement.**
Trên ISD-Agent-Bench, AlignmentGraph-ISD dẫn đầu cả 7 agents ở *2* điểm rất khác nhau của phổ quy mô model — DeepSeek-v4-flash (LLM) và Qwen3.5-9B (SLM).
Điểm cốt lõi: khi hạ từ LLM xuống SLM, harness **gần như bất biến**, trong khi các baselines so sanh rớt hoặc sụp lượng lớn điểm.
Đây là một **kết quả sạch, đã hoàn tất**, và trực tiếp cho thấy giá trị của harness tăng lên khi model yếu đi. Ngược lại, nhánh refinement (RQ2 cũ) vẫn dang dở, tốn nhiều công đo mà settings cho thí nghiệm này khi nhìn lại cũng chưa đủ thuyết phục.

**(b) Phù hợp với xu hướng triển khai thực tế (tính cấp thiết cao)**
Chi phí suy luận đẩy các tổ chức chuyển từ LLM lớn sang **SLM** cho các tác vụ nội bộ như sinh chương trình đào tạo, đúng lúc năng lực của model nền đang bão hòa trên nhiều benchmark. Khi khả năng của model tự thân không còn là đòn bẩy, chất lượng của một agentic system phụ thuộc ngày càng nhiều vào **harness** bao quanh model — và hiệu ứng này lớn nhất trên model
nhỏ.
**Kết quả (a) chính là một minh chứng thực nghiệm** cho luận điểm harness-over-model này trong bối cảnh ISD.

**(c) Cơ chế trung tâm không đổi, chỉ đổi bài toán nó phục vụ.** 
Alignment graph — biểu diễn constructive alignment thành trạng thái kiểm tra được — vốn được thiết kế để bảo toàn alignment khi *chỉnh sửa*. Nhưng cùng cơ chế đó giải quyết một bài toán
phổ quát và cấp thiết hơn: **duy trì alignment ngay khi *sinh*, bất kể model yếu hay mạnh**.
Alignment là thứ sụp đầu tiên trên model nhỏ, và là một defect *tích lũy, vô hình* — chương trình vẫn "nhìn ổn" từng phần và chỉ lộ lỗi khi triển khai.
**Các khung agent hiện tại chỉ định hướng alignment qua prompt, không biểu diễn nó thành trạng thái mà hệ thống có thể kiểm tra và sửa**. Đây chính là gap mà harness lấp, và nó không phụ thuộc vào việc có kịch bản refinement hay không.

⇒ Quyết định:
- Giữ nguyên cơ chế lõi: alignment graph + multi-agent decomposition + verify/repair
- Thu hẹp phạm vi từ "controlled refinement" về "chất lượng single-pass, đặc biệt cho SLM" - nơi đã có **bằng chứng thực nghiệm vững và tính thời sự cao nhất**.
- Refinement đa phiên trở thành hướng mở rộng tự nhiên (future work).

## 2. Phát biểu bài toán — TRƯỚC (controlled refinement)

**Bài toán.** Cho phiên bản thiết kế đã triển khai `D^(v)` (các artifact + quan hệ
alignment) và yêu cầu chỉnh sửa `r`, tạo `D^(v+1)` sao cho:
- (i) chỉ vùng bị `r` ảnh
hưởng được sửa (edit locality)
- (ii) constructive alignment được bảo toàn
- (iii) chi phí một vòng co giãn theo **kích thước thay đổi**, không theo kích thước
chương trình.

**Phạm vi.** Multi-session refinement; alignment graph versioned + cascade-scoped
revision; brief elicitation; agentic RAG.

**Câu hỏi nghiên cứu.**
- RQ1: chất lượng first-pass.
- RQ2: hiệu quả refinement.

**Đóng góp.**
- (1) harness với alignment graph versioned + cascade-scoped revision +
refinement entrypoint;
- (2) bằng chứng thực nghiệm + case study.

## 3. Phát biểu bài toán — SAU (quality-preserving ISD for SLM)

**Động lực (chuỗi thực tế triển khai).**
LLM agents sinh chương trình ISD ở quy mô lớn → áp lực chi phí → đẩy sang **SLM** → nhưng chất lượng ISD phụ thuộc **constructive alignment** giữa objectives–activities–assessments, và alignment là thứ *sụp đầu tiên* trên model yếu (defect tích lũy, vô hình).
Các khung agent hiện tại chỉ định hướng alignment qua prompt, **không** biểu diễn thành trạng thái kiểm tra được → chất lượng phó mặc cho năng lực model.

**Bài toán.**
Cho một design brief `b`, sinh chương trình ISD hoàn chỉnh sao cho:
- (i) mọi learning objective đều được aligned — có assessment đo, activity hỗ trợ, evaluation đánh giá, và ở đúng cấp độ nhận thức (thoả constructive alignment)
- (ii) chất lượng được harness đảm chứ không phụ thuộc hoàn toàn vào năng lực model (bất biến theo model scale)

**Phạm vi.** Single-pass generation; alignment graph là first-class verifiable
state; verify/repair là công cụ per-agent; đối sánh ngang hàng 6 agents của
ISD-Agent-Bench trên cả LLM và SLM. **Giữ làm future work:** multi-session refinement, elicitation, agentic RAG.

**Câu hỏi nghiên cứu.**

- **RQ1 (chất lượng single-pass):** trên ISD-Agent-Bench, AlignmentGraph-ISD so với
  6 agents về chất lượng artifact thế nào trên LLM và SLM?
- **RQ2 (ablation):** cơ chế nào của harness đóng góp vào chất lượng, và đóng góp đó có tăng khi model nhỏ đi không?

**Đóng góp.**
- (1) harness: alignment graph là first-class state + multi-agent decomposition + pedagogical verify/repair
- (2) bằng chứng: benchmark 2 model + ablation study, duy trì chất lượng ISD trên SLM chi phí thấp

## 4. Bảng giữ / bỏ

| Thành phần                                   | Trước                                                                                 | Sau                                                                                                              |
|----------------------------------------------|---------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Bài toán trung tâm                           | Controlled refinement                                                                 | Duy trì chất lượng ISD, bất kể model scale                                                                       |
| Alignment graph                              | Trung tâm                                                                             | Vẫn trung tâm                                                                                                    |
| Verify + repair                              | Thực hiện sau cùng, sau đó chuyển tiếp cho các agent chuyên môn sửa                   | Để từng agent chuyên gia thực hiện ngay tại lượt sinh                                                            |
| RQ2                                          | Refinement efficiency (chưa thực hiện, settings cho thí nghiệm này cũng chưa đủ mạnh) | Ablation study (đóng góp từng cơ chế, giải thích cơ chế nào tác động mạnh để duy trì chất lượng trên model nhỏ ) |
| Multi-session refinement / Elicitation / RAG | Trong phạm vi                                                                         | Future work                                                                                                      |
| Trục "harness-over-model"                    | Phụ                                                                                   | Trục chính (đặc biệt cho SLM)                                                                                    |

## 5. Bằng chứng trung thực định hình quyết định

- **RQ1 (vững):** harness bất biến theo scale (84.07 → 84.65 khi LLM→SLM), dẫn đầu
  cả hai run; p_Holm < 0.01 mọi so sánh.
- **RQ2 — ablation (đang củng cố), trên Qwen3.5-9B, n=90:**
    - **Multi-agent decomposition** là trụ cột: bỏ đi rớt ~10 điểm ADDIE (p ≈ 1e-14)
      — đóng góp chính, ủng hộ mạnh phát biểu mới.
    - **Verify/repair:** giảm ~99% lỗi sư phạm đo được (residual violations 312 → 3)
      nhưng chỉ tăng nhẹ điểm judge tổng.

⇒ Câu chuyện mới trung thực và mạch lạc: lợi thế trên SLM đến chủ yếu từ **cấu trúc
(decomposition + graph)**; verify/repair là cơ chế *đảm bảo* bổ sung.
