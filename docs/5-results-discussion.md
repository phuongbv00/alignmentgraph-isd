# Chương 5 — Kết quả và thảo luận

> File này là khung điền sau khi chạy thực nghiệm. Chương 4 đã cố định protocol; Chương 5 chỉ báo cáo kết quả theo đúng protocol đó, không thay đổi metric hoặc chọn lại baseline sau khi thấy kết quả.

## 5.1 Run summary

Mở đầu chương cần báo cáo ngắn gọn `run_manifest` để người đọc biết kết quả được tạo trong điều kiện nào.

| Nhóm thông tin | Giá trị báo cáo                                                                 |
| -------------- | ------------------------------------------------------------------------------- |
| Prototype      | commit hash, ngày chạy, benchmark version                                       |
| Corpus         | corpus version, nguồn mở/nội bộ, số source, số chunk, tỷ lệ metadata lỗi nếu có |
| Model          | model/checkpoint, runtime, decoding config                                      |
| Retrieval      | embedding, reranker, top-k, metadata filter                                     |
| Judge          | judge model, rubric version, human subset size                                  |
| Sample         | số sample hợp lệ/tổng số, số output failure sau retry                           |

Nếu corpus là tài liệu mở, phần này phải ghi rõ nguồn và phiên bản. Nếu corpus là tài liệu nội bộ, phần này phải mô tả mức truy cập và cách bảo vệ dữ liệu, không cần công bố nội dung nhạy cảm.

## 5.2 RQ1 — Main comparison results

Bảng chính báo cáo kết quả theo task family và variant. Các điểm số rubric được chuẩn hoá 0-100; binary metric báo cáo theo tỷ lệ phần trăm.

| Task family | Variant                  | Quality score | Schema validity | Citation coverage | Verifier pass | Pedagogical violation | Latency p50 |
| ----------- | ------------------------ | ------------: | --------------: | ----------------: | ------------: | --------------------: | ----------: |
| UC-ID       | LLM-only                 |           TBD |             TBD |               N/A |           N/A |                   TBD |         TBD |
| UC-ID       | Naive RAG                |           TBD |             TBD |               TBD |           N/A |                   TBD |         TBD |
| UC-ID       | Generic ReAct ARAG       |           TBD |             TBD |               TBD |           N/A |                   TBD |         TBD |
| UC-ID       | Fixed MA-ARAG            |           TBD |             TBD |               TBD |           N/A |                   TBD |         TBD |
| UC-ID       | Proposed - Domain Plugin |           TBD |             TBD |               TBD |           N/A |                   TBD |         TBD |
| UC-ID       | Full Proposed System     |           TBD |             TBD |               TBD |           N/A |                   TBD |         TBD |
| UC-AS       | LLM-only                 |           TBD |             TBD |               N/A |           TBD |                   TBD |         TBD |
| UC-AS       | Naive RAG                |           TBD |             TBD |               TBD |           TBD |                   TBD |         TBD |
| UC-AS       | Generic ReAct ARAG       |           TBD |             TBD |               TBD |           TBD |                   TBD |         TBD |
| UC-AS       | Fixed MA-ARAG            |           TBD |             TBD |               TBD |           TBD |                   TBD |         TBD |
| UC-AS       | Proposed - Domain Plugin |           TBD |             TBD |               TBD |       N/A/TBD |                   TBD |         TBD |
| UC-AS       | Full Proposed System     |           TBD |             TBD |               TBD |           TBD |                   TBD |         TBD |

Diễn giải cần trả lời trực tiếp:

- Hệ thống đề xuất hơn baseline nào, trên task nào, và theo metric nào?
- Cải thiện đến từ chất lượng sư phạm, grounding, schema/interface compliance, verifier hay giảm lỗi feedback?
- Trade-off latency, token usage và số tool call có chấp nhận được trong bối cảnh giáo viên không?
- Có metric nào hệ thống đề xuất không tốt hơn baseline không, và điều đó nói gì về giới hạn harness?

## 5.3 Statistical report

Bảng này chỉ báo cáo các so sánh chính đã định nghĩa trước trong Chương 4, tránh chọn cặp so sánh sau khi thấy kết quả.

| Comparison                                | Metric        | Test     | Delta | Effect size | p-value | Corrected p | Interpretation |
| ----------------------------------------- | ------------- | -------- | ----: | ----------: | ------: | ----------: | -------------- |
| Full Proposed vs Generic ReAct            | quality_score | Wilcoxon |   TBD |         TBD |     TBD |         TBD | TBD            |
| Full Proposed vs Fixed MA-ARAG            | quality_score | Wilcoxon |   TBD |         TBD |     TBD |         TBD | TBD            |
| Full Proposed vs Proposed - Domain Plugin | verifier_pass | McNemar  |   TBD |         TBD |     TBD |         TBD | plugin delta   |
| With-profile vs no-profile                | group_fit     | Wilcoxon |   TBD |         TBD |     TBD |         TBD | RQ2            |

Không kết luận chỉ dựa vào p-value. Nếu effect size nhỏ, confidence interval rộng, hoặc chi phí vận hành tăng lớn, phần thảo luận phải nói rõ.

## 5.4 Judge reliability

Trước khi dùng LLM-as-judge làm bằng chứng chính, báo cáo độ tin cậy của judge.

| Metric group        | Agreement metric          | Value | Threshold | Decision             |
| ------------------- | ------------------------- | ----: | --------: | -------------------- |
| Pass/fail labels    | Cohen's kappa             |   TBD |       0.6 | use / auxiliary only |
| Ordinal rubric 0-3  | weighted kappa hoặc alpha |   TBD |       0.6 | use / auxiliary only |
| LLM-human alignment | Spearman correlation      |   TBD |    report | use / auxiliary only |

Nếu judge agreement thấp, Chương 5 phải hạ mức khẳng định. Ví dụ: "metric này gợi ý xu hướng" thay vì "chứng minh hệ thống tốt hơn".

## 5.5 RQ2 — Personalization delta analysis

Phần này báo cáo paired analysis cho A1/A2, B1/B2 và C1/C2. Cần tách rõ khác biệt có ý nghĩa sư phạm khỏi khác biệt bề mặt.

| Pair group        | Variant       | Group-fit delta | Specificity delta | Misconception alignment | Non-harmful adaptation | Interpretation |
| ----------------- | ------------- | --------------: | ----------------: | ----------------------: | ---------------------: | -------------- |
| A1/A2 lesson plan | Full Proposed |             TBD |               TBD |                     TBD |                    TBD | TBD            |
| B1/B2 exercise    | Full Proposed |             TBD |               TBD |                     TBD |                    TBD | TBD            |
| C1/C2 feedback    | Full Proposed |             TBD |               TBD |                     TBD |                    TBD | TBD            |

Khi diễn giải, cần chỉ ra ví dụ cụ thể:

- Round-2 có thay đổi hoạt động, độ khó, scaffold hoặc feedback theo profile không?
- Output có dùng đúng evidence trong profile/diagnosis không?
- Có trường hợp cá nhân hoá sai hướng, gán nhãn nhóm hình thức hoặc hạ thấp kỳ vọng học sinh không?
- Profile giúp nhiều nhất ở lesson planning, exercise generation hay feedback?

## 5.6 Plugin and mechanism analysis

Không báo cáo đây là ablation study nếu chưa có ablation đầy đủ. Phần này dùng plugin delta, trace và phân tích lỗi để giải thích cơ chế.

| Analysis item               | Evidence                                                    | Interpretation                                           |
| --------------------------- | ----------------------------------------------------------- | -------------------------------------------------------- |
| Domain plugin delta         | `Proposed - Domain Plugin` vs `Full Proposed System`        | plugin CNTT cải thiện code/test/verifier ở mức nào       |
| Schema/interface compliance | schema validity, missing-field rate, malformed output rate  | typed workflow có giảm lỗi giao diện không               |
| Verifier/repair behavior    | pass rate, retry count, repaired issue types                | verifier bắt và sửa loại lỗi nào                         |
| Pedagogical constraint      | Bloom violation, rubric mismatch, feedback policy violation | constraint sư phạm kiểm soát chất lượng ở đâu            |
| Retrieval/grounding         | citation coverage, unsupported citation, retrieval miss     | RAG giúp đúng nguồn hay gây nhiễu                        |
| Cost/latency                | LLM calls, tool calls, token usage, latency                 | chất lượng tăng có đổi bằng chi phí chấp nhận được không |

## 5.7 Error analysis

Phân tích tối thiểu 30 output thất bại, stratified theo task và variant.

| Failure type                         | Count | Representative sample | Likely cause | Related component          | Fix direction |
| ------------------------------------ | ----: | --------------------- | ------------ | -------------------------- | ------------- |
| Hallucination / unsupported citation |   TBD | TBD                   | TBD          | retrieval / prompting      | TBD           |
| Off-Bloom / misalignment             |   TBD | TBD                   | TBD          | pedagogical verifier       | TBD           |
| Schema invalid                       |   TBD | TBD                   | TBD          | schema prompt / retry      | TBD           |
| Code/test failure                    |   TBD | TBD                   | TBD          | domain verifier            | TBD           |
| Wrong misconception label            |   TBD | TBD                   | TBD          | error taxonomy / judge     | TBD           |
| Superficial personalization          |   TBD | TBD                   | TBD          | profile injection / prompt | TBD           |

Mỗi ví dụ nên được rút gọn vừa đủ: input, lỗi chính, output fragment, trace liên quan và cách hệ thống nên sửa.

## 5.8 Threats to validity

**Internal validity**:

- LLM-as-judge có thể bias theo vị trí, style hoặc độ dài output; protocol đã giảm rủi ro bằng blind judging, random order, normalized format và human subset.
- Reference package do tác giả khởi tạo có thể thiên lệch; protocol giảm rủi ro bằng reviewer/adjudication, nhưng không loại bỏ hoàn toàn.
- Prompt và hyperparameter có thể ưu ái một variant; cần công bố prompt template và dùng cùng output schema.

**External validity**:

- Chỉ có một case study CNTT/lập trình; chưa kiểm chứng trên domain khác.
- Corpus được kiểm soát nhưng có thể chưa đại diện cho mọi chương trình đào tạo; nếu dùng corpus mở, kết quả không chứng minh lợi thế nhờ "LLM chưa biết tài liệu", mà chứng minh grounding/workflow trên nguồn đã đóng băng.
- Prototype local-first chưa phản ánh deployment LMS quy mô lớn.

**Construct validity**:

- `personalization_delta` đo chất lượng artifact theo profile, chưa chứng minh học sinh học tốt hơn.
- `verifier_pass_rate` bao quát correctness kỹ thuật của bài lập trình, không bao quát toàn bộ chất lượng sư phạm.
- Human subset nếu nhỏ sẽ chỉ đủ kiểm tra xu hướng judge, chưa thay thế đánh giá giáo viên diện rộng.

## 5.9 Discussion

Các điểm cần chốt trong phần thảo luận:

- Khi nào Pedagogy Agent Harness hơn agent framework tổng quát?
- Khi nào domain plugin tạo khác biệt rõ, và khi nào core harness đã đủ?
- Memory continuity và Context Injection có tạo giá trị thực hay chỉ tăng độ phức tạp?
- Teacher-in-the-loop nên nằm ở đâu để cân bằng autonomy, accountability và UX?
- Với domain ít verifier hình thức như Văn, Lịch sử hoặc Địa lý, metric nào cần thay thế verifier pass rate?
- Kết quả có đủ để claim giá trị sư phạm không, hay mới đủ claim giá trị kỹ thuật trong sinh artifact?
