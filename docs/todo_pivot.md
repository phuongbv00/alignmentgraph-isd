# TODO — pivot agentic (2026-08-31)

Trạng thái: `[ ]` chưa làm, `[~]` đang làm, `[x]` xong, `[?]` chờ quyết định.
Kế hoạch gốc: `~/.claude/plans/nh-gi-t-ng-frolicking-clock.md`.

## Đã xong (Phase 1 lõi)

- [x] `control_mode` thành field của `HarnessRunConfig`, mặc định `agentic`; `runner.run_workflow` dispatch.
- [x] Transport native tool calling (`bind_tools` + `.tool_calls`); `submit` mang args schema từ `AgenticStep.submit_fields`.
- [x] `agent_mode` = ranh giới context (multi reset mỗi stage, single giữ một `messages`); thứ tự ADDIE instruct y hệt hai nhánh.
- [x] `context_mode="prose"` chạy được ở arm agentic (commit prose, tool `list_documents`/`read_document`, không sinh graph dump).
- [x] Pass hoà giải sau stage 7, bounded; `OWNER_BY_VIOLATION`, `Violation.target_designer`, `TrajectoryAction.RECONCILE`.
- [x] `metadata.autonomy` theo stage + `trim_history`.
- [x] Adapter + đăng ký benchmark (4 arm agentic, `alignmentgraph-isd-scripted*` làm đường lui).
- [x] `08_pool_ablation_runs.py`: pin `control_mode`, thêm tầng `autonomy`.
- [x] Script probe Phase 0 (`00_probe_tool_calling.py`).
- [x] Golden fixture pin cả prompt lẫn tool schema.
- [x] **Ba lỗi bắt từ run `single_20260831_152628`** — xem §Sự cố bên dưới.

## Phải chạy lại trước khi kết luận bất cứ điều gì

- [ ] **Chạy lại `single_*` một scenario, 4 arm.** Run 2026-08-31 15:26 VÔ GIÁ TRỊ với nghiên cứu: 28/28 stage đều rơi vào scripted fallback vì lỗi transport (xem §Sự cố 1). Mọi số trong đó — chi phí, context, điểm — đo đường hỏng.
  Kiểm ngay sau khi chạy: `via_fallback` phải THẤP, `submits_rejected` không còn kịch trần 2, và output không còn tên tool.
- [ ] **Phase 0 probe** trên pod sống, 4 size. Con số well-formed rate vào §Experimental Setup.
- [ ] **Phase 3 cổng đo** `train_30`, 4 arm, 0.8B + 9B, 1 run. Ba câu hỏi trong plan §Trình tự.

## Còn lại — code

- [ ] `11_gen_ablation_tables.py` / `12_gen_ablation_figures.py`: bảng autonomy; hình context-length-theo-stage (hai đường tách nhau); hình điểm-phase-theo-vị-trí.
- [ ] Ba lỗ thống kê ở factorial layer (`08`): thiếu **marginal main effect** mỗi trục; **không correct multiplicity**; **không áp 3 failure policy** như RQ1.
- [ ] Tương tác `arm × stage_position` trên điểm từng phase ADDIE (dữ liệu đã có ở `autonomy` + `phase_scores`).
- [ ] `metadata.autonomy` chưa ghi `reconcile` counts theo arm — cần cho bảng.

## Còn lại — paper + docs

- [ ] `main.tex:38` title → "Multi-Agent **System**"; rà 10 chỗ dùng "harness" trong `sections/*.tex`; sync `docs/summary.md` (T1), `docs/authors.md`.
- [ ] `02_related_work.tex` + `04_method.tex`: viết vào đó *loại* MAS này là gì (`summary.md:204-208` hiện vắng mặt trong mọi `.tex`). Nêu deepagents làm reference architecture.
- [ ] `05_experiment.tex:14,23-31`, `06_results.tex:153-183`, `07_discussion.tex:100-103`, `09_conclusion.tex:21`: đang kể thiết kế verifier×graph-context đã bỏ.
- [ ] `07_discussion.tex:108-126`: đoạn "state-driven variant là future work" nay ĐẢO CHIỀU.
- [ ] `docs/summary.md:150-152,237-238,400`: bỏ "không kiểm decomposition" / "không có arm single-agent" — nay có kiểm, bằng cơ chế ranh giới context.
- [ ] `docs/benchmark_guides.md`: §5.4 còn ghi "3 arm"; thêm mục control mode + `metadata.autonomy` + probe Phase 0.
- [ ] `docs/rq2_protocol.md`: kiểm xem có chỗ nào giả định arm scripted.
- [ ] **§5 fairness**: hệ đề xuất dùng tool calling còn 6 baseline thì không — thuộc tính của hệ, không phải ưu đãi serving. Phải nói rõ một câu.
- [ ] `docs/ablation_expansion_proposal.md`: bản amend gửi thầy (6 mục a–f trong plan §Việc với thầy).

## Sự cố phát hiện từ run `single_20260831_152628` — đã sửa, cần verify lại bằng run mới

1. **Transport: tham số cấu trúc về dạng chuỗi.** vLLM `--tool-call-parser qwen3_coder` dựng lại LỜI GỌI, không dựng lại KIỂU mà schema khai. Model gọi `submit` đúng nhưng `{"needs_analysis": "{\"problem_definition\": ...}"}` → validator báo `expected list, got str` → **28/28 stage rơi fallback**.
   Sửa: `tools.coerce_args` ở biên transport + khai `items`/`additionalProperties` cho parser có cái để ép kiểu. 3 test regression.
2. **Fallback được xem tool menu.** `_fallback` khai "no tool protocol" nhưng truyền nguyên `stage_message` (có menu) làm user turn. Tách `_stage_context()` (docket + scenario) khỏi phần instruction; fallback chỉ nhận context.
3. **Tên tool rò vào nội dung giảng dạy.** Cả 4 arm (A0: 33 lần; react-isd sạch). Một assessment item bắt học viên "map each phase to `read_nodes`/`read_edges`". Development của A0 = 28,9/100.
   Sửa: `protocol_leak_errors` làm chốt deterministic (cùng kiểu placeholder gate), `check_artifact` chạy CÙNG validator với `submit`, và protocol nói thẳng quy tắc cho model.

**Một điều đáng ghi nhận từ run đó:** lưới an toàn hai bậc làm đúng việc — transport hỏng hoàn toàn mà cả 4 arm vẫn ra ADDIE đầy đủ, `validation_errors = 0`, `errors = 0`. Đó là bằng chứng robustness thật, dùng được cho paper.

## Run 2 — `single_20260831_160530` (sau 3 bản vá)

Bản vá ăn ở đúng chỗ nhắm:
- **Rò tên tool: 33 → 0**, sạch cả 4 arm.
- **A0 development: 28,9 → 84,1** (+55,2) — xa ngoài dải nhiễu.
- `submits_rejected` phần lớn về 0; fallback 28/28 → 13/28.

Nhưng **không kết luận được gì thêm**: n=1, và `react-isd` — code không đổi — tự dịch **−6,26 addie** giữa hai run. Nhiễu judge trùm mọi delta khác.

Ba việc đã sửa tiếp (chưa verify bằng run mới):
- [x] Bỏ `submit` khỏi `_PROTOCOL_WORDS` — là từ tiếng Anh thường, gate bắt nhầm nội dung thật rồi model đốt 2 lượt cãi với lỗi nó không sửa được.
- [x] Ghi **shape của args** khi submit bị từ chối — `expected dict, got str` có hai nguyên nhân rất khác nhau (parser trả text vs model viết văn xuôi) mà run này không phân biệt được.
- [x] Đếm ngược lượt còn lại vào observation — 10/13 fallback là `turn budget exhausted`; single+graph đốt cả 8 lượt để đọc ở 6/7 stage.

## Lỗi history (phát hiện 2026-08-31, sau run 2) — CHUỖI BA LỚP, đã sửa

Câu hỏi "cái gì đang được đưa vào history?" phơi ra ba lỗi chồng nhau, và cả ba đều làm
trục `agent_mode` đo sai thứ:

1. **Submit thành công không bao giờ vào history.** Loop `return` ngay sau `_commit`, nên
   lượt submit không được ghi lại. Arm `single` do đó **không mang theo bất cứ thứ gì nó
   đã sinh ra**. Dump thực tế: transcript cuối cùng = 1 system + 4 bản sao hướng dẫn stage,
   không có artifact nào.
2. **Scenario lặp lại mỗi stage.** Tôi cố ý làm vậy "để parity", nhưng nó byte-identical
   qua cả 7 stage → là nhân bản, không phải tích luỹ. Cộng với (1), thứ arm `single` tích
   được chỉ là **boilerplate gửi lại nhiều lần**. Trục đang đo "ta gửi lại hướng dẫn bao
   nhiêu lần", không phải "agent có mang theo việc đã làm không".
3. **`context_len` đếm thiếu phần lớn nhất.** Artifact nằm trong `tool_calls`, không nằm
   trong `.content`, mà hàm đo chỉ đọc `.content`. Nên `context_len` báo ~24k ký tự trong
   khi chính run đó đốt 744k token. Kéo theo `trim_history` cũng cắt sai thời điểm.

Sửa: submit turn + tool result vào history; scenario chuyển lên system turn (miễn trim,
nêu đúng một lần, giống nhau hai arm); `message_size` đếm cả `tool_calls`. 3 test regression.

Sau khi sửa, đo trên fake — lần đầu tiên chuỗi context phản ánh đúng cơ chế:
- multi: 4514 → 5969, phẳng, 0 trim
- single: 4548 → 23463, đơn điệu, trim từ stage 4

**Hệ quả: mọi `context_len` trong run 1 và run 2 đều sai.** Bất kỳ đọc nào về "arm single
phình context" từ hai run đó phải bỏ.

## Bỏ `check_artifact` (chốt 2026-08-31)

Generation trong arm agentic KHÔNG có bước riêng: artifact chính là `arguments` của
`submit`. Hệ quả là `check_artifact` — vốn chạy CÙNG validator với `submit` và trả CÙNG
bộ lỗi — bắt model **viết lại nguyên artifact** làm tham số mỗi lượt gọi.

Đo trên run 16:05: `single-graph` gọi 18 lần, `single-prose` 17 lần (A0 chỉ 1). Completion
token: single-graph 64,4k vs multi 37,6k.

Đã bỏ hẳn; `SUBMIT_BUDGET` 2 → 3. Cùng luồng thông tin (submit bị từ chối trả đúng lỗi đó),
không viết artifact hai lần, ngân sách thử lại thành tường minh và bằng nhau hai arm.
Tool set còn: graph = `read_nodes`/`read_node`/`read_edges`/`coverage_gaps`/`submit`;
prose = `list_documents`/`read_document`/`submit`.

## Tầng Developer / fan-out (khôi phục 2026-08-31)

**Lỗ đã tìm ra:** arm agentic bỏ mất hẳn tầng fan-out mà arm scripted có (4 family:
assessment, activities, content, rubrics). Hệ quả đo được trên cùng scenario — một `submit`
phải chở trọn danh sách item của cả family, mà trần completion là 8192:

| arm | field | scripted | agentic (trước sửa) |
|---|---|---|---|
| `alignmentgraph-isd` | learner_materials | 38,5 | **6,0** |
| `multi-prose` | learning_activities | 90,0 | **6,0** |
| `single-graph` | learner_materials | 16,5 | **2,5** |

Mọi arm, mọi family, tụt 50–93%.

**Thiết kế đã chốt (user):** cả hai arm đều chia work set và gọi cùng số call; khác nhau ở
**ai làm mỗi set**. `multi` spawn Developer (`AssessmentDeveloperAgent`/`ActivityDeveloperAgent`/
`MaterialDeveloperAgent`/`RubricDeveloperAgent`) — context mới, persona riêng. `single` **không
spawn gì cả**, tự viết từng set trong context đang chạy và trả bằng context phình ra.
Cho fan-out riêng multi sẽ để multi thắng nhờ lọt trần token còn single thì không — confound
mà audit 08-30 đã phải đóng một lần.

**Đã làm:** `core/agentic/fanout.py` mới (SPECS 4 family, `set_step`, `commit_sets`,
`committed_set_ids`, cap 6000 ký tự cho assignment); 4 stage chuyển thành dispatch-only
(schema/validate/commit chỉ còn kế hoạch, thêm trường `dev_plan` cho assessment/activities);
`rubrics` không có dispatch hop; driver `_run_fanout` trong `run.py`; `ToolLoop` thêm `capture`.
Tái dùng nguyên `core/dev_plans.py` — không viết lại normalization.

**Bốn lỗi bắt trong lúc xây:**
- `remap_and_tag` cần payload `{"set_id","items"}`, tôi đưa raw submit → fan-out trả 0 item,
  và **repair net tự vá 15 assessment** khiến nó *trông như* có output. Lưới an toàn che mất lỗi.
- Driver chạm graph ngoài scope `acting_as` → event mất attribution (lớp lỗi 2026-08-27).
- Prompt per-set thiếu header `=== YOUR ASSIGNED SET/BLOCK/MODULE/ITEM ===` mà Developer
  scripted dùng → fixture trả nguyên danh sách thay vì lát của set (104 item, id đụng nhau,
  bị remap đổi tên, tham chiếu downstream treo).
- Renderer assignment không có cap → stage message 39k ký tự, vượt trần context 16k.

**Một test over-assert lộ ra:** `test_run_establishes_all_18_relations_and_repairs_gaps` đòi
KHÔNG quan hệ nào còn gap sau repair, nhưng P7/P10/P11 là secondary và **không family nào sở
hữu** → không có repair nào đóng được. Nó pass trước đây chỉ vì arm sinh ít node nên phủ hết
tình cờ. Đã thu hẹp assert về các quan hệ thực sự có repair. Đáng báo trong paper: sinh nhiều
hơn thì residual gap ở nhóm secondary hiện ra nhiều hơn — đó là việc của audit, không phải lỗi.

## Bề mặt audit của trajectory (2026-08-31)

Judge chỉ đọc `tool_calls` / `reasoning_steps` / `agent_interactions` — **không đọc `events`**
(`evaluator/.../metrics/trajectory.py:250-293`). Nên thêm event là an toàn, không đổi đầu vào
chấm điểm. Ba lỗ đã vá:

1. **Arm prose không ghi lại gì nó sinh ra.** Graph arm ghi 54 `node_add`; prose ghi 0, vì
   `store.put` không log. "Run này làm ra cái gì" đọc được ở một context mode và mù ở mode kia —
   bất đối xứng ở BỀ MẶT AUDIT, không phải ở treatment. Thêm `TrajectoryAction.DOC_WRITE` +
   `log_doc_write`; ghi trong `_put()` chứ không ở từng call site, cùng lý do `_decompose` tự log.
2. **Fan-out bị gộp vào stage.** `via_fallback` của một stage khi đó nghĩa là "dispatch HOẶC một
   trong mười set bỏ cuộc" — không đọc được. Tách `n_sets` / `sets_via_fallback` / `set_turns` /
   `set_submits_rejected`, và cho **mọi stage cùng hình dạng khoá** qua `empty_stage_stats()`
   (rubrics không có dispatch nên trước đó thiếu khoá — không phân biệt được "không gọi dispatch"
   với "trường chưa bao giờ được ghi").
3. **Pass hoà giải không ghi check.** Giờ ghi cả khi không tìm thấy gì: "đã soi và sạch" khác
   "chưa bao giờ chạy", và audit phải phân biệt được. Ghi dưới tên **family bị kiểm**, không phải
   dưới orchestrator — một `check` nêu thứ nó soi (`test_trajectory_attribution` bắt đúng chỗ này).

**Test chốt:** `test_the_trajectory_records_everything_a_run_audit_needs` quét cả 4 arm, kiểm 8
bất biến: mọi event có `agent`; `tool_calls ≤ llm_calls` và phần dư giải thích được bằng repair;
có bản ghi thứ đã sinh ra ở CẢ hai context mode; check ≥ số stage; `dev_plan` có `set_count`;
`autonomy` đủ khoá và đồng hình; identity phân biệt được hai arm; `run_config` tự mô tả.

## Lỗi transport thứ hai: tool call về dưới dạng text (2026-08-31)

Log run 18:09:
```
'<tool_call>\n<function=read_nodes>\n<param...'
'<tool_call>\n<function=read_document>\n(ke...'
```
Model gọi tool ĐÚNG, nhưng server trả nguyên markup `qwen3_coder` trong `content` với
`tool_calls` rỗng. Trước bản vá mỗi lần như vậy bị tính "invalid turn" → tốn một lượt →
đẩy stage về fallback, vì lý do không liên quan tới năng lực model.

**KHÔNG phải do không hỗ trợ native tool calling.** Run 16:05: `submits_rejected` phần lớn
về 0, `check_artifact` được gọi 17–18 lần — parser có dựng lại tool call bình thường. Raw
markup chỉ 1 lần trên cả 4 arm. Đây là hỏng **không liên tục**.

Đã vá: `tools.parse_tool_call_markup` dựng lại call khi server không dựng, và **đếm** nó
(`TrajectoryAction.TOOL_CALL_MARKUP_RECOVERED` + `autonomy.markup_recovered`) — tỉ lệ đó chặn
xem bao nhiêu phần hành vi của arm agentic thực ra thuộc về serving stack. Cũng tắt warning
`parse_json_response` trên đường không-có-tool-call: model đâu được yêu cầu trả JSON ở lượt đó.

**Đã LOẠI TRỪ hai giả thuyết bằng probe (2026-08-31, qwen2b, 20 call/cell):**
- `AGENT_MODEL_STREAMING=1` — **không phải**. plain 100%, streaming 100%, chênh 0.
- Độ phức tạp tool schema — **không phải**. Với đúng 5 tool harness bind (schema 1741 ký tự,
  prompt 5234 ký tự) vẫn 100% well-formed.

**Đã LOẠI TRỪ tiếp: lượt thứ hai.** Probe 4 cell (turn 1/2 × plain/streaming) trên qwen2b:
**100% cả bốn**. Nên transport sạch ở mọi điều kiện probe kiểm được.

**NGUYÊN NHÂN THẬT (truy bằng cách diff payload, không tốn pod): thiếu `tool_choice`.**
LangChain `bind_tools(specs)` gửi `tools` nhưng **không gửi `tool_choice`**; probe thì gửi
`"tool_choice": "auto"` tường minh. Mà `--enable-auto-tool-choice` của vLLM chính là thứ engage
parser — thiếu trường đó, server có thể trả nguyên markup trong `content` thay vì parse vào
`tool_calls`. Đây là trường DUY NHẤT khác giữa payload harness và payload probe (message
serialize thì giống hệt: `{"role":"assistant","content":null,"tool_calls":[...]}`).

Sửa: `bind_tools(specs, tool_choice="auto")`, kèm fallback `TypeError` cho backend không nhận
tham số đó. 2 test.

**Ghi chú giả thuyết cũ (chưa đo, giữ lại phòng khi markup còn):** Probe cũ chỉ gửi một lượt sạch. Trong
vòng lặp thật, mọi lượt sau lượt đầu mang theo **một trao đổi tool đã hoàn tất** (assistant
message chứa `tool_calls`, rồi message role `tool`). Nếu chat template render sai lượt assistant
mang tool_calls, model bắt đầu **bắt chước chính markup nó được cho xem** — khớp đúng triệu
chứng "lượt đầu sạch, giữa run mới rơi ra markup".

`00_probe_tool_calling.py` giờ có 4 cell/slot: turn 1/2 × plain/streaming, và bind tool thật
của harness (`--stage`, mặc định `assessment`). **User chạy** — tôi đã lỡ tự chạy một lần
(40 call) và không lặp lại.

## Tái thiết kế 2026-09-01 — `single` thành MỘT ReAct loop + ba việc cắt chi phí

Nguồn: run `single_20260901_133402` (A0 300 call / 1,28M token / 1.298 s/scenario → ladder
11–22 ngày, không chạy được) và phát hiện `single` chưa bao giờ là single agent
(`run.py` chạy `for step in STEPS` cho CẢ HAI arm; nhánh single chỉ khác ở chỗ chia `messages`).

**Đã làm — B: rubric gộp vào Assessment Developer.**
`STEPS` 7 → 6, `fanout.SPECS` 4 → 3 family, `RubricDeveloperAgent` biến mất khỏi arm agentic.
`FanoutSpec` mang nhiều `SetOutput`, nên assessment submit cả `assessment_tools` lẫn
`rubric_criteria` trong một call. C6/C7 thiết lập trong `commit_sets` của assessment.
`repairs.OWNED_BY_FAMILY["rubric_designer"]` giữ nguyên, chạy qua `AgenticStep.also_repairs`.
**Chỉ output ĐẦU bắt buộc** — thiếu rubric không được phép vứt cả set item tốt.
Cắt được: **32/55 work set của A0**.

**Đã làm — A: agent quyết số lượng, `MAX_*` xuống backstop.**
`MAX_SET_FACTOR` 2→1, `MAX_SETS_HARD_CAP` 24→12. Fallback của `dev_plans` gộp theo
OBJECTIVE thay vì theo (objective, category). `dev_plan` thành trường submit BẮT BUỘC ở
dispatch — `src=fallback` ở mọi family nghĩa là agent chưa bao giờ tự quyết.
Đo trên đúng hình dạng thật: A0 assessment 12→**4** set; multi-prose 24→**12**, activity 24→**12**.

**Đã làm — C: bỏ `NODE_COUNT_CAP`.**
Cơ chế thật của bất đối xứng: cả hai mode cap 600 ký tự/item, nhưng CHỈ graph cap số lượng
(25 node). Nay cả hai trả đủ item. An toàn vì A đã giữ số item ở mức hợp lý.

**Đã làm — `core/agentic/react.py` (mới, 361 dòng).**
Một agent, một loop. System prompt = persona + 7 stage + schema/rules TỪNG stage + scenario.
Tool = read (hợp mọi stage) + `submit_<stage>` cho mỗi stage CHƯA xong; menu co lại khi stage
xong, và menu rỗng = xong việc. **Submit cộng dồn** và prompt nói rõ — điều kiện để "agent tự
chia" là lựa chọn thật. Ngân sách 96 lượt, cố ý KHÔNG ràng buộc, kèm `via_budget_exhaustion`
cho cả hai arm: thứ kiểm được không phải "ngân sách bằng nhau" mà "ngân sách không cắt arm nào".

**Năm lỗi bắt trong lúc xây:**
- `submit_<stage>` của single chỉ nhận KẾ HOẠCH (schema dispatch) → stage không bao giờ xong,
  94 lần submit. Single không có Developer nên phải nhận cả item.
- Prompt cho agent xem schema kế hoạch nhưng submit lại nhận `assessment_tools` — bảo nó nộp
  thứ chưa bao giờ được cho xem hình dạng.
- React loop **không log tool_call nào judge nhìn thấy** (chỉ log read). Judge chấm trên
  `tool_calls`, nên arm single trông như không làm gì.
- React loop **không được đẩy docket** → bất đối xứng `context_mode` giữa hai arm decomposition,
  đúng thứ làm nhiễu tương tác hai trục.
- Fixture `_flaky_design_factory` hỏng MỌI lần chứ không phải một lần; với react loop (mọi
  schema nằm trong một system prompt) nó bôi trắng cả run.

**Trạng thái:** 337 test xanh, `run_benchmark.py --check` sạch, 4 arm smoke 0 lỗi validation.
`run.py` chỉ còn 4 chỗ `if single`, tất cả ở điểm rẽ trên cùng.

**Chưa làm:** dòng code KHÔNG giảm (2.831 → 3.384) vì `react.py` là code mới; cái giảm là độ
phức tạp cấu trúc (hết threading `carried`, hết nhánh single trong `_run_fanout`/vòng stage).
`loop.py` 845 dòng vẫn chưa tách `run()`. Và **chi phí thật chưa đo** — ước tính sau A+B là
~447 s/scenario cho A0 (mốc arm scripted: **206 s**), nhưng đó là ngoại suy tuyến tính, phải
chạy thật mới biết.

## Run `single_20260901_151738` — sau tái thiết kế. Chi phí cắt mạnh, ReAct loop SẬP.

| arm | calls | tokens | sec | errs |
|---|---|---|---|---|
| `alignmentgraph-isd` | 300 → **146** | 1,28M → **512k** | 1298 → **577** | 0 |
| `multi-prose` | 437 → **59** | 1,04M → **170k** | 1628 → **275** | 0 |
| `single-graph` | 112 → 48 | 674k → 424k | 412 → 505 | **11** |
| `single-prose` | 50 → 49 | 279k → 382k | 303 → **231** | **13** |

A0 giảm 56% thời gian, multi-prose giảm 83%. Nhưng **hai arm single sập hoàn toàn**:
`turns=96` (kịch trần), `via_budget_exhaustion=True`, single-graph **0 submit thành công**,
21 lần bị từ chối, 26 lần gọi trùng, `history_dropped=189`.

**Nguyên nhân — lỗi thiết kế của tôi, không phải tính chất single-agent:**
```
system prompt        23.668 ký tự   (6 stage × schema + mọi output schema + scenario)
HISTORY_CHAR_BUDGET  24.000 ký tự
```
System turn ăn gần trọn ngân sách → `trim_history` giữ system, vứt sạch phần còn lại. Agent
không có trí nhớ làm việc: mỗi lượt thấy toàn bộ đặc tả và gần như không thấy việc vừa làm.
Đó là lý do gọi trùng 26–42 lần và 0 stage hoàn tất.

**Đã sửa:** schema từng stage chuyển ra sau tool `stage_brief(stage)` — lấy khi cần, không nhồi
hết vào system turn. **System prompt 23.668 → 2.899 ký tự**, chừa ~21k cho transcript. Prompt
nói rõ: gọi `stage_brief` trước khi submit một stage lần đầu. Test
`test_the_system_turn_leaves_room_for_the_transcript` chặn tái phát (system < 1/3 ngân sách).

**Chưa verify bằng run thật.** Phải chạy lại 1 scenario và kiểm: `via_budget_exhaustion=False`,
`stage_order` đủ 6 stage, `submits_per_stage` khác rỗng, `validation_errors=0`.

## Tối ưu arm multi (2026-09-01, sau run 15:17)

**Chất lượng — hình dạng đã tốt ở giữa, yếu ở hai đầu.** A0 phase scores:
`anal=64  desi=93  deve=96  impl=94  eval=70` so với react-isd phẳng `84/86/86/82/86`.
Tức fan-out ĐANG hiệu quả (design/development/implementation đều hơn react), và thứ kéo tụt
tổng điểm là **analysis 64** và **evaluation 70**. Đối chiếu nội dung hai bên thì tương đương
về chất — n=1 không phán được, nên **chưa động vào**; cần nhiều scenario mới biết là thật hay nhiễu.

**Chi phí — đo được chỗ tiền đi.** A0: prompt 478k vs completion 33k, tỉ lệ **14:1** — ta trả
tiền cho thứ GỬI ĐI, không phải thứ model viết. Và:

| identity | calls | ghi chú |
|---|---|---|
| MaterialDeveloperAgent | **54** | cho 10 work set; chỉ **10** là submit, **44 là đọc** |
| ActivityDeveloperAgent | 27 | |
| AssessmentDeveloperAgent | 14 | |
| 6 stage designer | 51 | |

**Developer chiếm 95/146 call (65%), và ~80% lượt của chúng là ĐỌC** — đọc topic, activity,
objective, edge, coverage gap, trong khi assignment đã được render sẵn vào prompt. Riêng
`coverage_gaps` trả về gap của các set KHÁC: tốn một lượt để biết một thứ Developer đó
không được phép làm gì.

**Đã sửa hai việc:**
- **Thu hẹp phạm vi đọc của Developer** (`FanoutSpec.developer_reads`): assessment chỉ đọc
  objective; activities đọc objective + assessment; content đọc content + activity. Bỏ hẳn
  relation reads và docket khỏi Developer — coverage gap là việc của bên chia set, không phải
  của một Developer bên trong set nó không tự chọn. Đúng với claim "specialist có context slice
  `C(s)`" ở `04_method.tex`.
- **Trần lượt riêng cho Developer** (`DEVELOPER_MAX_TURNS = 3` thay vì 8): việc của Developer
  nhỏ hơn việc của một stage, và assignment đã nằm trong prompt.
- **Gọi trùng không còn tốn lượt** (`REPEAT_ALLOWANCE = 3`): một repeat không sinh observation
  cũng không sinh artifact, nên tính phí nó là tiêu ngân sách vào sự bối rối của model — 19 lượt
  của A0 đi theo đường đó. Hoàn lại nhưng có trần, để model chỉ biết lặp vẫn tới được fallback.

**Ước tính:** A0 146 → **87–105 call**, 577 → **~344–415 s**, prompt 478k → ~344k.
Mốc arm scripted: 206 s / 56 call. **Chưa verify bằng run thật.**

## Run `single_20260901_154303` — A0 tốt nhất từ trước tới nay; prose và single vẫn hỏng

**A0 (`alignmentgraph-isd`) — thắng react-isd trên ADDIE lần đầu:**

| | calls | tokens | sec | addie | phases |
|---|---|---|---|---|---|
| A0 run trước | 146 | 512k | 577 | 82,29 | 64/93/96/94/**70** |
| **A0 run này** | **83** | **281k** | **456** | **85,21** | 83/83/85/85/85 |
| react-isd | 5 | 14k | 68 | 84,32 | 83/86/79/82/84 |

Đúng ước tính (87–105 call). Vấn đề `anal=64`/`eval=70` biến mất, phase cân bằng.
`total` vẫn thua (85,37 vs 87,07) vì `trajectory_score` — vòng lặp tool thật sinh repeat thật.

**`multi-prose` NỔ: 59 → 147 call, 275 → 1182 s.** Nguyên nhân đo được: model viết **10 objective
→ 112 material**, 32 work set, **28/32 rơi fallback**, context chạm **68.786 ký tự**. So sánh:
A0 viết 2 objective → 12 material, 12 set, context 23.598.

Tức bỏ `NODE_COUNT_CAP` (việc C) an toàn cho A0 nhưng không an toàn cho prose — lập luận
"an toàn vì A đã giữ số item hợp lý" ĐÚNG với A0, SAI với prose.

**Đã sửa — cap đọc theo KÍCH THƯỚC, không theo số lượng.** `READ_CHAR_BUDGET = 8000` cho cả hai
context mode, kèm dòng "... and N more not shown". Bounded thứ thật sự vỡ (byte prompt), cùng
một luật ở hai mode, và không giả vờ 25 là con số đúng của bất cứ thứ gì.

**Đã sửa — `DEVELOPER_MAX_TURNS` 3 → 4.** Ở 3, một nửa content set của A0 và 28/32 set của prose
rơi fallback. Set do fallback sinh ra không phải set do tool loop sinh ra.

**Hai arm `single` vẫn hỏng (9 và 14 lỗi), hai kiểu khác nhau:**
- `single-prose`: submit `design_analysis` **61 lần**. Menu co lại khi stage xong, **nhưng loop
  vẫn nhận** — model nhỏ vẫn gọi tool nó từng được mời, và ta vẫn commit đè. Cả 96 lượt tiêu vào
  một stage đã xong.
  **Sửa:** `SUBMIT_CAP = 8` mỗi stage. Vẫn CỘNG DỒN (đợt hai là mục đích của thiết kế) nhưng có
  trần, và lời từ chối nói rõ phải làm gì tiếp.
  **Sửa kèm:** `_doc_keys` trả tên FAMILY (`outcome_designer`) chứ không phải khoá document
  (`objective`) → merge cộng dồn đọc khoá chưa ai từng ghi, nên mọi submit thứ hai âm thầm ĐÈ
  chứ không cộng.
- `single-graph`: 59 submit bị từ chối, 18 `llm_error`, 17 `invalid_action`, chỉ 14 read trong
  96 lượt. **Chưa rõ nguyên nhân** — cần run mới sau các bản vá trên rồi đọc lại.

## Run `single_20260901_162455` — A0 dẫn CẢ HAI tín hiệu lần đầu

| | total | addie | phases |
|---|---|---|---|
| **`alignmentgraph-isd`** | **85,06** | **86,37** | 86/84/89/84/84 |
| `react-isd` | 84,80 | 81,29 | 79/78/95/84/81 |
| `multi-prose` | 83,63 | 83,04 | 85/81/85/81/66 |

Lưu ý nhiễu: `react-isd` (code không đổi) dịch −3,03 addie so với run trước. Biên total 0,26
nằm trong nhiễu; biên addie 5,08 thì lớn hơn, nhưng vẫn n=1.

**Chi phí A0 tăng 83 → 139 call — chủ yếu do scenario, không do bản vá.** Run này model viết
**5 objective** (run trước: 2) → 21 work set thay vì 12. Per-set thì ổn hơn: content 3,5 lượt/set.
`multi-prose` cải thiện rõ nhờ cap đọc theo byte: 147 → 108 call, 1182 → 580 s, setfb 28 → 1.

**Chỗ đắt mới lộ:** `implementation` — 18 lượt ở A0, 0 work set, rơi fallback ở CẢ HAI arm multi.
`analysis` cũng rơi fallback ở cả hai. Hai stage ở hai đầu, không fan-out, đang tốn nhiều và hỏng.

**Hai arm `single`: `SUBMIT_CAP` chặn được vòng 61 lần** (nay analysis 8, assessment 8), nhưng
lộ nguyên nhân thật:

```
single-graph : 15× "assessment_plan.lo_coverage_targets: required field is missing"
single-prose : 48× "needs_analysis.gaps must be a non-empty list; improvement_plan..."
history_dropped = 170 / 186
```

Agent bị kẹt ở CÙNG một lỗi, nộp lại cùng một hình dạng hỏng. Vì `trim_history` bỏ observation
cũ nhất trước, mà `stage_brief` chính là cái cũ nhất và lớn nhất (tới 7.400 ký tự) — **agent bị
sửa lỗi dựa trên một đặc tả nó không còn nhìn thấy.**

**Đã sửa:** `_respec()` — đính lại schema vào thông báo từ chối, và **chỉ khi nó thực sự đã biến
mất** khỏi transcript (dán vào mọi lần từ chối sẽ đẩy nốt phần transcript mà nó cần nằm cạnh).

## [x] Nén sau khi commit — CHỐT (user 2026-09-01)

`context_len` của arm single ghim ở trần 23,9k mọi lúc, `history_dropped` 170–186. Phần lớn
transcript là **payload `tool_calls` của chính các submit đã commit** — mỗi artifact ~5k, 8 submit
là 40k. Chúng đã nằm trong design state và đọc lại được bằng tool.

Hai hướng, hệ quả nghiên cứu khác nhau:
- **Giữ nguyên văn** (hiện tại): trung thực với "một agent, một context", và context phình đúng
  như giả thuyết dự đoán. Nhưng phần phình lớn nhất là JSON dư thừa, không phải suy luận.
- **Nén sau khi commit** (thay payload bằng tóm tắt + "đọc lại bằng read_nodes"): giống thứ một hệ
  single-agent thật sẽ làm, và giải phóng ngân sách cho suy luận. Nhưng nó **làm yếu chính cơ chế
  trục đang đo**.

**Chốt: nén.** Và có lý do NGHIÊN CỨU ủng hộ chứ không chỉ thực tế: arm multi cũng không mang
payload (context mới mỗi stage), nên trước bản vá này một phần khoảng cách giữa hai arm chỉ là
*single tự gửi lại JSON của chính nó*. Nén xong, trục đo thứ agent phải GIỮ TRONG ĐẦU — mọi
instruction, mọi observation, và một bản ghi những gì đã sinh ra — chứ không phải thứ ta lười xoá.

**Đã làm, hai lớp:**
- `_compact()`: sau khi commit, payload trong `tool_calls` được thay bằng bản ghi
  (`"5 committed: AT-01, AT-02, ..."`). Artifact thật đã nằm trong design state, đọc lại bằng tool.
- Nhả `stage_brief` của stage đã submit: đây là observation lớn nhất transcript (tới 7.400 ký tự),
  và giữ đặc tả cho việc đã làm xong thì chèn ép việc chưa làm. `_respec()` đính lại đúng lúc có lỗi.

**Đo trên fixture:** peak context 23.936 → **15.363**, `history_dropped` 11 → **0**, transcript giữ
26 message thay vì 15 — agent giữ được TOÀN BỘ lịch sử làm việc thay vì bản bị cắt cụt đầy JSON dư.

## Điểm trajectory — khoảng cách nằm gọn ở MỘT chiều

Phân rã BFCL (run 16:24):

| arm | traj | tool_correct | arg_acc | **redundancy** | result_util |
|---|---|---|---|---|---|
| `react-isd` | 93,00 | 22,0 | 20,0 | **23,0** | 21,0 |
| `alignmentgraph-isd` | 82,00 | **22,5** | 21,0 | **18,0** | 20,5 |

Ba chiều kia tương đương — A0 còn dẫn `tool_correctness`. **Toàn bộ chênh lệch nằm ở
`redundancy_avoidance`.** Nhìn đúng thứ judge đọc (nó chỉ lấy 20 call đầu):

```
react-isd : run_analysis, run_design, run_development, run_implementation, run_evaluation  (5, khác nhau hết)
A0        : ... tool_read_nodes_objective ở vị trí 12, 14, 17, 19
```

Bốn lần đọc trùng đó là **bốn AssessmentDeveloper khác nhau**, mỗi cái một context mới — đúng
thiết kế. Nhưng judge đọc danh sách phẳng, không biết ai gọi, nên thấy là lặp.

**Nguyên nhân thật là thiết kế của TA, không phải model.** `render_assessment_set` chỉ đưa
**id** ("ILO-01 x formative"), không đưa nội dung objective. Nên mọi Developer buộc phải đọc
để biết ILO-01 nói gì. Không thể bảo một Developer viết đề cho một objective rồi không cho nó
biết objective ấy nói gì.

**Đã sửa:** `_resolved_references()` — nội dung của các artifact mà work set NÊU TÊN được resolve
thẳng vào assignment. Đây cũng chính là "context slice `C(s)`" mà §4 của paper tuyên bố mỗi
specialist được nhận. Kỳ vọng: read của Developer giảm mạnh, kéo theo cả chi phí lẫn
`redundancy_avoidance`.

**Chưa verify bằng run thật.**

## [?] Trần trajectory của judge: 20 → 120 — ĐÃ REVERT 2026-09-03, chờ quyết định

**Trạng thái: code đã revert về nguyên bản của ISD-Agent-Bench** (`tool_calls[:20]`,
`reasoning_steps[:15]`, `agent_interactions[:20]`). Đã bỏ:

- `evaluator/src/isd_evaluator/metrics/trajectory.py` — hằng `MAX_TRAJECTORY_ITEMS = 120`
  và dòng báo "… N call bị bỏ".
- `evaluator/tests/test_composite_metrics.py` — test
  `test_the_trajectory_cap_does_not_favour_agents_that_call_less`.

Lý do revert: sửa evaluator là **sửa thước đo của benchmark mình đang dùng làm chuẩn so sánh**.
Chưa chốt được nên khai nó là deviation trong paper hay giữ nguyên mặc định và xử lý confound
theo cách khác, nên để nguyên gốc đã, không mang một evaluator đã bị sửa vào ladder.

### Chẩn đoán vẫn còn nguyên giá trị — ĐỪNG bỏ

Trần cũ được viết cho agent gọi ~10 lần, và mọi baseline vẫn thế (react-isd 5 call, các agent
khác 1–11). Nó **chỉ ràng buộc các arm phân rã** (đo trên run `single_20260901_162455`):

| arm | call | judge thấy |
|---|---|---|
| `react-isd` | 5 | **100%** |
| `single-prose` | 4 | **100%** |
| `single-graph` | 28 | 71% |
| `multi-prose` | 88 | 22,7% |
| `alignmentgraph-isd` | 98 | **20,4%** |

Tức **tỉ lệ nhìn thấy là hàm của mức phân rã** — mà phân rã chính là một biến độc lập của
nghiên cứu. Chênh lệch `trajectory_score` trên trục `agent_mode` khi đó không tách được khỏi
artefact cắt cụt. Lập luận này **không phụ thuộc vào chiều của hiệu ứng**: nó đúng kể cả nếu
việc cắt cụt đang có lợi cho ta.

Cả ba trần confound như nhau (arm multi có 88/98 mục ở cả ba danh sách), nên bất cứ phương án
nào cũng phải xử lý cả ba, không riêng `tool_calls`.

### [?] Ba đường đi, phải chọn trước khi chạy ladder

1. **Giữ nguyên mặc định (đang là trạng thái hiện tại).** Số so được trực tiếp với ISD-Agent-Bench,
   nhưng phải KHAI trong §Limitations rằng `trajectory_score` bị cắt cụt lệch theo mức phân rã,
   và **không được đọc chênh lệch trajectory trên trục `agent_mode`** như một kết quả.
2. **Nâng trần lên 120 và khai là deviation** ở §Measures / §Experimental Setup kèm lý do confound.
   Số cũ (trần 20) không so được với số mới → phải chạy lại phần trajectory.
3. **Báo sensitivity cả hai trần** (20 và 120) cho các arm alignmentgraph. Tốn thêm một lượt chấm
   judge nhưng cho người đọc thấy hiệu ứng thay vì tin lời — mạnh nhất về validity.

Quyết xong thì cập nhật mục này và §Measures của paper cùng lúc.

## [x] Xoá hẳn `control_mode` (2026-09-03)

Sau khi bỏ bản scripted (2026-09-01), `control_mode` là `Literal["agentic"]` — **một giá trị,
không chỗ nào branch trên nó, không caller nào truyền, không có run dir scripted nào tồn tại**
để mà phải phân biệt. Nó chỉ còn là một hằng số ghi vào mọi `metadata.run_config`. Đã xoá:

- `config.py` — field + block comment.
- `core/agentic/run.py` — `"control_mode": "agentic"` trong dump `run_config`.
- adapter `agents/alignmentgraph-isd/.../agent.py` — kwarg + pass-through.
- `08_pool_ablation_runs.py` — 4 entry `EXPECTED_FLAGS`.
- test: `test_agentic_run.py` (4 chỗ), `test_ablation_flags.py` (7 chỗ, gồm vòng lặp
  `for control_mode in ("agentic",)` — tàn dư thời hai mode), `test_benchmark_contract.py`
  (`RUN_CONFIG_KEYS`), `conftest.py` (fixture `scripted_config` chết + docstring `FakeChatModel`).
- README package + CLAUDE.md.

440 test package pass, `run_benchmark.py --check` 7/7 agent, `test_token_accounting_reaches_agents`
7/7 pass.

**Lưu ý:** `HarnessRunConfig` là pydantic mặc định `extra="ignore"`, nên caller cũ truyền
`control_mode=` sẽ bị **bỏ qua im lặng**, không lỗi. Không còn caller nào như vậy trong repo.

**[?] Provenance:** nếu vẫn muốn results dir tự khai nó do bản nào sinh ra thì thêm
`package_version` (từ `importlib.metadata`) vào `run_config` — nó bắt được cả những drift mà
`control_mode` mù tịt (ví dụ `max_turns` đã đổi 8 → 12 giữa các run hiện có trong `results/`).
Chưa làm.

## [x] Bug kèm theo: `via_fallback` đã chết mà `08` vẫn đọc (2026-09-03)

`autonomy_layer` trong `08_pool_ablation_runs.py` đọc `stats.get("via_fallback")` — cờ của
scripted single-shot, **đã biến mất từ 2026-09-01**. Record thật giờ mang `gave_up` và
`sets_gave_up`. Hệ quả: `pct_via_fallback` và `pct_stages_via_fallback` **luôn bằng 0,0** — báo
"không arm nào bỏ cuộc" như một kết quả đo, trong khi thực ra không đo gì cả. Đúng cái zero câm
mà docstring của chính nó cảnh báo. Đã đổi sang `gave_up` / `pct_gave_up` / `pct_stages_gave_up`.

## [x] Rà sạch CLAUDE.md + README + docstring stale (2026-09-04)

Sau khi bỏ scripted (2026-09-01) và `control_mode` (2026-09-03), tài liệu còn mô tả một hệ thống
không còn tồn tại. Đã rà hết. Sau đợt này **0 chuỗi "control mode" và 0 câu "scripted" ở thì hiện
tại** trong `src/` + `tests/`; những chỗ còn chữ "scripted" đều là ghi chú lịch sử ("retired",
"used to", "went 2026-09-01") — cố ý giữ vì đó là provenance.

### CLAUDE.md — 10 chỗ sai

| chỗ | sai gì |
|---|---|
| §layout | "LangGraph-based … fixed StateGraph topology, **not an autonomous agentic loop**" — ngược hẳn |
| `core/runner.py` | "builds and invokes the compiled LangGraph `StateGraph`" — giờ là shim mỏng |
| `core/agents/` | cả bullet mô tả 6 specialist + `BaseISDAgent` — **package đã xoá**, tên module cũng là tên cũ (`needs_context`, `objective_design`, …) |
| `core/workflow.py` | "LangGraph StateGraph layer, `build_workflow`" — **file đã xoá** |
| `core/` list | thiếu `aggregate.py`, `dev_plans.py`, `llm_io.py`, `memory.py`, `outputs.py` |
| budget | `MAX_TURNS=8` (thật: `STAGE_MAX_TURNS=12`), `SUBMIT_BUDGET=2` (thật: 3 — **tự mâu thuẫn với "(3)" ở câu sau**) |
| guards | liệt kê "the two-tier scripted fallback" như guard đang chạy |
| RAG | `BaseISDAgent._maybe_retrieve` → giờ là tool `retrieve` trong loop |
| on_event | `phase_started` "from `workflow.py`", `llm_started` "from `agents/base.py`" — cả hai file đã xoá |
| ids | "follow the renumbering through `SetOutput.ref_fields`" trong khi đoạn trên nói chính nó **đã bị thay** bằng `self_ref_fields` |

### CLAUDE.md — một sai lệch đáng kể hơn phần còn lại

Đoạn `llm_max_concurrency` mô tả "multi arm peaks at **~12 concurrent LLM requests**" như hiện
trạng. **Harness giờ tuần tự hoàn toàn**: không còn `ThreadPoolExecutor` nào trong `core/` (chỉ
RAG parallel plan và executor của server). Số 429 đo được là của pipeline LangGraph cũ. Đã viết
lại thành ghi chú lịch sử + lý do giữ cổng (fan-out concurrent quay lại là confound quay lại).

**[?] Hệ quả chưa xử lý:** `llm_max_concurrency` (mặc định map 2/3/4/6 theo `-r`) hiện **không
ràng buộc gì**. Chưa bỏ — chỉ ghi nhận.

### README của package — 6 chỗ

- "LangGraph-based" ở dòng 3.
- **Relation-join context injection** (`_element_context_joined`, header `NOT-YET-LINKED`) —
  **cơ chế này không còn tồn tại**, grep toàn repo không ra. Đã xoá bullet.
- `_element_context` → giờ agent tự gọi tool `read_nodes`/`read_node`/`read_edges`/`coverage_gaps`
  (fetch chứ không inject).
- `_alignment_state` → `tools.alignment_docket` (vẫn inject up front — chỗ này chỉ sai tên).
- Bullet "Bounded repair loop" tả repair cũ; `agent_mode` tả "only persona + task granularity
  differ" — mâu thuẫn với định nghĩa CONTEXT BOUNDARY.

### [x] Xoá `fallback_block()` + `JSON_ONLY` (2026-09-04)

`specialists.py::AgenticStep.fallback_block` không có caller nào trong `src/` kể từ khi bỏ
scripted rescue; nó sống được chỉ vì `regen_golden_prompts.py` pin nó. Đã xoá cả method,
dòng pin, và `rulebook.JSON_ONLY` — hằng này có **đúng một** user là `fallback_block`.

Golden fixture regenerate: **32 → 26 key**, removed đúng 6 key `*.fallback_block`, added 0,
**changed 0**. Tức mọi prompt SỐNG (persona, task_block, tool schema graph/prose) byte-identical —
comparability không đứt. Docstring `task_block` trước đây giải thích mình bằng cách đối lập với
JSON_ONLY, đã viết lại cho tự đứng được.

### [x] Bỏ 2 dependency chết + `threading.local()` (2026-09-04)

- `pyproject.toml`: bỏ `langgraph>=0.2` và `langchain-core>=0.1` khỏi `dependencies`. Harness chỉ
  nói chuyện với model qua `llm_factory` được inject và gọi duck-typed (`invoke`/`bind_tools`),
  không import package LangChain nào. Provider client thật nằm ở extra `[llm]` và tự khai
  langchain-core.
  **Verify bằng venv sạch** (`pip install .`, không extra): import OK, chạy trọn 1 design brief
  6 stage, `langgraph`/`langchain_core` **không có trong `sys.modules`**.
- `core/trajectory.py`: `_actor`/`_phase`/`_identity` từ `threading.local()` → thuộc tính instance
  thường (bỏ luôn 3 cặp property). Thread-local sinh ra để chống race khi LangGraph chạy
  content_designer/rubric_designer trên 2 worker thread; executor giờ tuần tự nên không còn thread
  nào để cách ly — và ở chỗ DUY NHẤT còn concurrency (RAG parallel plan) thì thread-local là
  **sai**: worker thread sẽ đọc actor rỗng thay vì agent đã dispatch nó. Ghi rõ trong comment là
  phải khôi phục nếu có fan-out concurrent trở lại.
- `_counter_lock` **GIỮ**: `core/rag/sandbox.py` chạy retrieval plan trên worker thread và được
  đưa thẳng `log_llm_call`.

440 test package pass sau toàn bộ đợt sửa; `run_benchmark.py --check` 7/7;
`test_token_accounting_reaches_agents` 7/7.

## [x] Quét 4 subagent + dọn nhóm A & C (2026-09-04)

4 agent song song, scope không chồng: `core/*` · `core/agentic/*` · `server`+`webapp`+`config` ·
`tests/` (agent thứ 4 tự spawn thêm một con soi riêng `tests/server/`). Em verify lại mọi claim
nặng trước khi sửa — **agent `core/` sai một chỗ**: nó nghi `aggregate._HARNESS_ONLY_SECTION_KEYS`
không tồn tại (ngụ ý `dev_plan` lọt vào deliverable); thực tế nó ở `aggregate.py:519`.

### [x] Đã sửa — dead code (~35 mục, -849 dòng)

`repairs.context_for` · `checks._RERUNNABLE_RELATIONS` · `brief.RETRIEVAL_STRATEGY_HINTS` +
`_RETRIEVAL_DECISION_SYSTEM` · `rulebook.SCHEMA_COURSE_GOAL` + `SCHEMA_LEARNING_OBJECTIVES` ·
3 × `_SCHEMA_*_MERGED` trong `specialists.py` (64 dòng, bản assessment còn mang `expert_review`) ·
`FanoutSpec.has_dispatch` + nhánh chết ở `run.py` · `audit._uncovered_objectives(reverse=…)` ·
`server.artifacts.trajectory_bundle` · `server.planner.is_configured` · webapp
`Selection{kind:'event'}` + `EventDetail` + `RunStreamState.events` + `deepTimeline.regen` ·
~12 fixture/helper mồ côi trong `tests/` · toàn bộ import/biến thừa (ruff F401/F841 giờ sạch).

### [!] MỘT MỤC CỐ Ý KHÔNG XOÁ — và nó lộ ra một lỗi prompt

`rulebook.SCHEMA_CONTENT_MODULES` không có caller, nhưng **KHÔNG phải bản sao** của
`specialists._SCHEMA_CONTENT_DISPATCH` đang sống. Diff:

- bản chết (rulebook) có `"for_modules": ["MOD-01"]` trong ví dụ `media_selections`
- bản **đang dùng** (dispatch) **không có**

Trong khi `RULES_CONTENT_MODULES` — đang sống — bắt buộc: *"Every media selection should also set
`for_modules` to the content module id(s) it serves"*. Tức **schema example đang mâu thuẫn với
rule ngay trong cùng một prompt**: model bị bảo phải điền một trường mà ví dụ không hề cho thấy.

**[?] Chưa sửa** vì sửa là đổi prompt sống → regen `golden_prompts.json`. Đây là ứng viên nhóm C
thứ 5, không phải dọn dẹp. Xoá mù hằng chết kia sẽ vứt luôn bằng chứng, nên em giữ nguyên.

### [x] Đã sửa — doc trôi

- **Số quan hệ**: ~14 chỗ ghi "18-relation / C1–C7" → thật là **16 = C1–C5 + P1–P11** (chạy
  `REGISTRY` để xác nhận). Gồm cả `tests/server/test_runs.py:237` tự mâu thuẫn với assertion
  `== 16` cách đó 4 dòng.
- **Hai legend rò ra bề mặt người dùng**: DOT legend `objective aligned (M/S/E ok)` trong khi
  `_node_label` chỉ vẽ M/S; legend webapp còn nêu verb `measures` đã retire.
- **Số stage**: 4 chỗ ghi "seven stages" → sáu.
- **11 comment** trỏ `NodeFactory` / `run_generation_step` — cả hai đã bốc hơi.
- `config.py` 3 khối (SingleDesignerAgent như class, family `rubric`, "superstep").
- **5 file test có header khẳng định ngược với thân file** (`test_call_gate`,
  `test_no_invented_content`, `test_item_completeness`, `test_trajectory_metadata`,
  `test_agentic_loop` compaction) — body đã cập nhật 2026-09-01/03, header thì không.
- Loạt con trỏ chết: `_element_context`, `_alignment_state`, `SingleDesignerAgent.<method>`,
  `OWNED_VIOLATION_TYPES`, `PlannedTask`, `RefinementRequest`, `PedagogicalVerifierAgent`,
  `core/store.py`, `core/alignment.py`, `match_id`, `R3-measures`/`R1..R13`, `workflow.py`.
- `test_dev_plans.py`: assertion `<= 10` siết về `<= 5` (bound thật; comment ghi cap cũ 24).

### [x] Nhóm C — cả 4 điểm anh chốt

1. **`agent_mode` = BUNDLE, disclose như `context_mode`.** CLAUDE.md + README package sửa lại:
   bỏ "CONTEXT BOUNDARY and nothing else" + "equal effort is the parity requirement", thay bằng
   khung bundle và điều kiện thật sự kiểm được (*neither arm was CUT by its turn budget*). Tên test
   ma `test_agentic_axis_changes_the_context_boundary_and_nothing_else` bị trỏ ở **3 chỗ** —
   xoá hết, trỏ về `test_the_agentic_arms_are_two_shapes_not_two_settings` là test có thật.
2. **Thêm 4 recovery action vào webapp**: `context_compacted`, `duplicate_submit`,
   `dropped_argument`, `bare_artifact_wrapped`. `context_compacted` được cấp `WorkKind` riêng
   (`compact`, tone warn) thay vì `error` — nó là giá của trục, không phải lỗi. Diff lại:
   python 21 / webapp 19, chỉ còn `repair` (có case riêng) và `repair_unfilled` (không thể fire),
   đã ghi chú để người sau không "sửa" nhầm.
3. **`[server]` extra**: cài vào môi trường dev → **suite từ 440 lên 538 pass, 0 skip**. 98 test
   server chạy thật lần đầu và xanh hết. README nêu thành yêu cầu bắt buộc của dev/CI;
   `tests/server/conftest.py` thêm `AGISD_REQUIRE_SERVER_TESTS=1` để biến skip thành fail cứng.
4. **Prompt sai**: `tools.py` description của mọi `submit_*` nói schema *"shown in the system
   prompt"* — sai từ khi hợp đồng chuyển sang fetch qua `stage_brief`. Đổi thành *"matching this
   stage's artifact schema"*. Regen fixture: **26 key, removed 0, added 0, changed 12** (toàn bộ
   là `*.tools.graph|prose`), và **chỉ 2 dòng khác biệt distinct**. Persona/task_block không đổi
   một byte.

### [ ] Nhóm B chưa làm — test tưởng có mà không có

- `test_empty_section_regen.py:226,263` gọi `FakeChatModel._submit_name()` **không tồn tại** →
  2 test ném `AttributeError`, harness nuốt thành `llm_error`, chúng đang test generic retry.
  **Sửa xong nhiều khả năng ĐỎ THẬT** — đó là điểm.
- `test_call_gate` peak = 1 với mọi setting; `test_the_graph_arm_is_pushed_the_docket…` cả hai
  nhánh trả `''`; `test_dev_plans.py:205,253` pin id scheme đã bỏ qua nhánh `else` chết;
  `assert repair_events >= 0`; 2 assert trên `agentic_fallback` không còn emitter;
  `test_trajectory_attribution` `parametrize(range(20))` lắc một race đa luồng không còn tồn tại;
  `tests/server`: `status_code in (200, 404)`, `accessibility in ("", None)`,
  `test_a_partial_run_is_still_a_success` không dựng run partial.

**Verify cuối:** 538 pass / 0 skip (python), ruff F401/F811/F841 sạch, webapp typecheck sạch +
44 test pass, venv sạch vẫn chạy được package.

## [x] Nhóm B — test tưởng có mà không có (2026-09-04)

Nguyên tắc áp dụng cho mọi mục: sửa xong phải trả lời được *"hôm nay phải hỏng cái gì thì test
này mới đỏ"*. Chỗ nào sửa được thì em chạy **negative control thật** (cố tình phá cơ chế, xác
nhận test đỏ) rồi mới tính là xong.

### Hai test regen — hỏng nặng nhất, và đã lộ ra cơ chế thật

`FakeChatModel._submit_name()` **không tồn tại** → `_ManualsMissingOnce` và
`_PartialImplementationOnce` ném `AttributeError`, harness nuốt thành `llm_error` rồi retry.
Chúng đang test generic exception recovery, payload chưa từng được giao.

Sửa transport (`_stage_submit` + `_respond`) thì hết `llm_error`, **nhưng vẫn `submit_rejected: 0`**
— vẫn không chạm guard, vì fake chỉ withhold ở call #1 còn stage cần 6 call (một submit / artifact
từ 2026-09-03). Nên phải siết tiếp:

- `_ManualsMissingOnce.WITHHOLD_CALLS = 4` — giữ lại 2 manual cho tới khi 4 artifact kia đã
  landed. **Negative control** (withhold = 999): loop hỏi **27 lần**, manuals rỗng → test đỏ. ✅
- `_PartialImplementationOnce` viết lại quanh **empty-not-absent**: `monitoring` về dạng `{}`
  thay vì vắng mặt. Đây mới là ca đáng lo (truncation sinh ra key có mặt nhưng rỗng).
  **Negative control**: 27 call, ship `{}`, và metadata ghi
  `implementation.monitoring: required field is missing or empty` → test đỏ. ✅

Nhân tiện xác nhận được kiến trúc: validator per-artifact **cố ý** chấp nhận `{"monitoring": {}}`
(nó chỉ chặn submit RỖNG HOÀN TOÀN); thứ bắt được artifact rỗng là `step_done` hỏi STATE cộng
`_empty_required_fields`. Hai tầng, và cả hai đều còn sống.

### Các test còn lại

| test | sai gì | sửa thành |
|---|---|---|
| `test_the_graph_arm_is_pushed_the_docket…` | graph rỗng ⇒ **cả hai** `_docket()` trả `''`, lại còn có escape hatch `or … == ""` | commit analysis+outcomes trước, rồi assert graph arm CÓ docket (bỏ escape hatch) |
| `test_the_submit_menu_shrinks…` | `[len(before):]` luôn rỗng vì binding all-done NHỎ hơn | so SET, assert không còn `submit_*` và read tool không đổi |
| `test_a_stage_that_is_already_done…` | bind `model` rồi không hề kiểm | assert `submit_analysis` không được chào + `model._cursor[0] == 0` |
| `test_a_run_never_exceeds_the_configured_concurrency` | executor tuần tự ⇒ peak = 1 với mọi setting | thêm assert **mọi model call đi qua gate của run** (phân biệt "gate giữ" với "gate chưa nối dây") |
| `test_dev_plans` ×2 | pin id scheme đã bỏ (`AT-01-AS-02`) qua nhánh `else` chết (`id_prefix=""`) | truyền `id_prefix="AT"` → đường sống: `AT-0101`/`AT-0201`, và "model không viết id" là ca BÌNH THƯỜNG |
| `test_ablation_flags` (2 run thừa) | chạy lại full pipeline 2 lần rồi assert tập con | xoá; check duy nhất khác biệt đã được `identities(single)` bao (tool = `f"{agent}.{action}"`) |
| `test_ablation_flags` rules | `step.rules in step.task_block()` — tautology vì `task_block` nội suy chính nó | assert `step.rules` **là** text của rulebook (`RULES_*` hoặc `rules_for(...)`) |
| `test_agentic_loop` ×2 | assert vắng `agentic_fallback` — không còn emitter | đổi sang `agentic_gave_up`, cái CÓ THỂ fire |
| `test_trajectory_metadata` | `assert repair_events >= 0` | xoá; ghi rõ vì sao repair không giải thích được chênh lệch |
| `test_compaction` | `"compact(" in source` khớp cả `def compact(` | `"self.messages = compact("` — CALL, không phải định nghĩa |
| `test_no_invented_content` | guard `hasattr(checks, "alignment_coverage")` = **False** ⇒ body không chạy | `checks.relation_coverage` + assert fixture thật sự sinh gap C3 |
| `test_trajectory_attribution` | `parametrize(range(20))` lắc race đa luồng không còn | bỏ; 19 bản sao tất định, ~1s pipeline mỗi bản |
| `test_the_agentic_arm_also_logs_the_residual_audit` | cùng code path với test trên, assert yếu hơn, "also" ám chỉ executor thứ hai | xoá, để lại ghi chú |
| `tests/server` ×3 | `status_code in (200, 404)`; `accessibility in ("", None)`; "partial run" không hề partial | dùng `blocked_run` ép đúng điều kiện → assert `== 404`; assert `== ""`; đổi tên test cho đúng thứ nó kiểm |

**Số test: 538 → 518** (−19 parametrize, −1 test trùng). Không mất coverage nào — cả 20 mục đều
là bỏ bản sao hoặc bỏ assert không thể đỏ.

**Verify:** 518 pass, ruff F401/F811/F841 sạch, webapp typecheck sạch + 44 test.

## [x] `for_modules`: schema mâu thuẫn với rule trong CÙNG một prompt (2026-09-04)

Phát hiện khi định xoá `rulebook.SCHEMA_CONTENT_MODULES` như dead code — **may là không xoá**.
Nó không phải bản sao của `specialists._SCHEMA_CONTENT_DISPATCH` đang sống, mà là bản ĐÚNG.

**Triệu chứng.** `RULES_CONTENT_MODULES` (sống) yêu cầu: *"Every media selection should also set
`for_modules` to the content module id(s) it serves"*. Nhưng ví dụ JSON đi kèm — bản chép tay,
đã trôi khỏi rulebook — **không hề có `for_modules`**. Model bị bảo điền một trường nó chưa từng
thấy, trên đúng lớp SLM mà nghiên cứu này nói về.

**Hậu quả đo được.** `dev_plans.material_work_units:505-510` đọc chính trường đó; media không có
nó thì **gắn vào MỌI module unit**:

```
WITH for_modules       -> 3 units, 3 media-slots ([1, 1, 1])
WITHOUT (schema đang chạy) -> 3 units, 9 media-slots ([3, 3, 3])
```

`RULES_MATERIALS_UNIT` nói mỗi material hiện thực MỘT media selection, nên mỗi Developer bị đòi
**gấp 3** số material đáng ra phải viết — vừa tốn call, vừa sai output (mọi module lặp lại mọi
dạng media).

**Sửa tận gốc, không vá.** `_SCHEMA_CONTENT_DISPATCH = rules.SCHEMA_CONTENT_MODULES` — lấy từ
rulebook đúng như hai anh em của nó (`_SCHEMA_ASSESSMENT_DISPATCH`, `_SCHEMA_ACTIVITIES_DISPATCH`)
vốn đã làm. Chép tay chính là cách chúng trôi ra nhau; content là cái duy nhất còn viết tay.

Golden fixture: **26 key, removed 0, added 0, changed 1** — đúng `agentic.content.task_block`.
Không stage nào khác đổi một byte.

**Guard mới** `test_no_rule_demands_a_field_its_schema_example_never_shows`: với mỗi family, mọi
field trong `_HARNESS_READ_FIELDS` mà RULES nhắc thì phải xuất hiện trong schema của **stage HOẶC
Developer** của family đó. Gộp cả hai tầng là điểm mấu chốt — so riêng stage thì 7 false positive
(activities/assessment nhắc field mà Developer mới là nơi viết chúng); gộp lại thì **`for_modules`
là vi phạm duy nhất trong toàn bộ 6 stage**. **Negative control**: dựng lại bản chép tay đã trôi →
guard đỏ đúng thông điệp. ✅

**Verify:** 519 pass, ruff sạch.

## [x] Hai lỗi từ run RunPod `single_20260904_020259` (2026-09-04)

Bối cảnh: run 01:44 trên HF router/featherless **không phải regression** — endpoint đó không làm
native tool calling, model trả tool call dưới dạng văn xuôi (`read_node(id="course_goal")`,
`` `coverage_gaps (relation_id: P11)` ``), cả hai parser đều trả None, 156/160 call là
`invalid_action`, `submits_rejected=0`. RunPod chạy được. Diff hôm nay vào `loop.py`/`tools.py`
toàn bộ là comment trừ một chuỗi description.

Run RunPod thì chạy nhưng **955s / 347 call / 1,19M token / 373 node**. Hai nguyên nhân độc lập:

### [x] A. 50 objective, 4 câu khác nhau — không có dedup ở nguồn

Truy chuỗi sự kiện: **một** step `design_outcomes_learning_objectives`, 50 id riêng, 50
`node_add` — model đẻ 50 cái trong MỘT submit, một câu lặp **32 lần**. Không phải harness tích luỹ
qua retry.

Mọi family phía sau tự định cỡ theo số objective: 50 LO → **63** assessment work set → **126**
item → **36** activity block → **161** activity. `RULES_OUTCOMES` đã ghi *"Do not pad"*; model 2B
vẫn pad — đúng lớp model nghiên cứu này nói tới, nên harness không được trông vào việc nó tuân thủ.
`dev_plans` đã có cap/dedup nhưng tất cả nằm SAU số objective.

Sửa: `_decompose(..., dedup_field=...)` — hai item cùng `statement` là một objective, chỉ commit
cái đầu. **Không phải cap**: model viết bao nhiêu tuỳ nó, phần bỏ được ĐẾM qua
`TrajectoryAction.DUPLICATE_ELEMENT_DROPPED` mới, vì *tỉ lệ pad theo size chính là một finding*.
Khai ở đủ 4 nơi (enum + `_RECOVERY_ACTIONS`, `test_benchmark_contract`, `conftest._EVENT_ACTIONS`,
webapp `phaseTimeline`/`deepTimeline`) — contract test bắt được ngay khi thiếu.

Nếu áp lên chính run đã đo: objectives 50→4, sets 63→~5, items 126→~10, activities 161→~13.

### [x] B. `course_goal` gửi dưới dạng chuỗi trần → C1 coverage 0/50

```
submit_rejected x3 | raw=course_goal:str | args=course_goal:dict
                     "course_goal.statement must be a non-empty string"
agentic_gave_up    | submit budget spent
```

Model gửi câu goal trần thay vì `{"statement": …}`. Ba lần từ chối → hết budget → bỏ stage →
`design.course_goal` **null** và **C1 edges = 0** (một trong 5 quan hệ core construct-validity).

Sửa: `ToolLoop._fill_single_key_object`. Field đích **suy từ chính schema exemplar**, không khai
tay: artifact nào có object ví dụ đúng MỘT key thì chuỗi trần chỉ có thể là key đó. Suy ra đúng
`course_goal→statement`, và `dev_plan→instrument_sets`/`activity_blocks`; không suy gì cho các
artifact nhiều field, nơi đoán sẽ là đoán mò.

**Đánh đổi phải khai:** test `test_a_value_that_is_genuinely_wrong_is_still_rejected` đỏ vì nay
`course_goal: "not json at all"` được nhận. Em giữ thay đổi và viết lại test cho đúng phạm vi
(`test_a_string_where_a_structure_was_declared_is_dropped_not_swallowed`): chuỗi vào chỗ khai
ARRAY vẫn bị `dropped_argument` và nói rõ — guard còn răng ở đó; ngoại lệ chỉ là object một-field.
Lý do chấp nhận: một goal dở mà judge chấm được vẫn hơn không có goal và mất luôn C1.

### Kiểm chứng

Hai test mới tái hiện đúng hai ca đo được, mỗi cái có **negative control**: tắt dedup → `committed
33`; tắt salvage → `a bare-string course goal was not read as its only field`. 521 pass,
`golden_prompts.json` **không đổi** (không sửa prompt nào), ruff sạch, webapp typecheck + 44 test,
`run_benchmark.py --check` 7/7.

### [?] Còn treo: có cap số objective không

Chưa làm và **không nên tự quyết**: cap cứng chạm vào chính thứ trục RQ1 đang đo (model nhỏ pad
nhiều hơn là KẾT QUẢ, không phải nhiễu). Dedup an toàn vì nó không giấu hành vi — số thô vẫn nằm
trong trajectory. Cap thì có thể làm phẳng tín hiệu.

## [ ] Nợ kỹ thuật có sẵn trong evaluator (KHÔNG do pivot)

- `evaluator/tests/test_trajectory_metrics.py` không collect được: `pydantic.VERSION` —
  lệch phiên bản openai/pydantic trong venv.
- 7 test evaluator fail sẵn (`test_context_weights.py` và các file khác). Đã xác minh có trước
  mọi thay đổi của đợt pivot (164 pass trước, 165 sau khi thêm test mới).

## Run `single_20260901_171408` — A0 tụt vì `analysis`; lộ hai lỗi transport nữa

| arm | total | addie | traj | calls | sec |
|---|---|---|---|---|---|
| `multi-prose` | **85,53** | **84,91** | 87,00 | 105 | 646 |
| `react-isd` | 84,57 | 80,11 | 95,00 | 5 | 98 |
| `alignmentgraph-isd` | 68,63 | 63,01 | 81,75 | 97 (−42) | 528 (−279) |

Chi phí A0 tiếp tục giảm (139 → 97 call, 807 → 528 s) nhưng **addie sập 86,37 → 63,01**, và lần
đầu có lỗi validation: `analysis.learner_analysis: required field is missing or empty`.

**Nguyên nhân: stage `analysis` hỏng ở CẢ HAI arm multi** — 3 lần bị từ chối, rơi fallback, và ở
A0 fallback cũng ra artifact thiếu field. Đây là stage đầu tiên, không fan-out, và nó rơi fallback
ở 3 run liên tiếp.

**Chẩn đoán `args=` (thêm hôm 08-31) trả công — thấy đúng hình dạng lỗi:**
```
analysis        args=needs_analysis:str          → ta báo "gaps must be a non-empty list"
implementation  args=instructor_guide:str,...    → "expected dict, got str"
assessment      args=assessment_tools:str        → "must be a non-empty list"
invalid_action  in={"name":"submit","arguments":{"needs_analysis":{...
```

**Hai lỗi transport, đã sửa:**
1. **Thông báo lỗi nói về NỘI DUNG cho một vấn đề về HÌNH DẠNG.** Giá trị tới dưới dạng `str`
   không parse được, nhưng ta bảo model "gaps rỗng" — nó sửa nhầm chỗ, nộp lại đúng chuỗi đó
   3 lần rồi stage rơi fallback. `tools.shape_errors()` giờ báo **trước** mọi lỗi khác:
   *"needs_analysis arrived as text, not as a JSON object"*.
2. **Dạng tool call thứ ba chưa được cứu**: model viết `{"name":"submit","arguments":{...}}`
   thành JSON trong content, không có `tool_calls`. Loop chỉ đọc được là văn xuôi → tốn một lượt
   và nudge protocol cho một model thực ra ĐÃ gọi tool. `tools.parse_tool_call_json()`.

**`redundancy_avoidance` vẫn 18 — và run này ĐÃ chấm bằng trần 120** (user xác nhận). A0 có 97
call < 120, tức **judge nhìn 100% quỹ đạo**. Nên 18 điểm là THẬT, không phải artefact cắt cụt.

> Lưu ý sau 2026-09-03: trần 120 đã được revert (xem §Trần trajectory của judge). Con số 18 ở
> đây được sinh bởi evaluator ĐÃ SỬA, nên **không so trực tiếp** với số của bất kỳ run nào chấm
> bằng evaluator gốc (trần 20).

Bóc tách 67 call judge nhìn thấy:
- **11 call trùng TUYỆT ĐỐI** (cùng agent + cùng tool + cùng args) — lãng phí thật. Guard chống
  lặp chỉ chạy TRONG một loop, mà mỗi Developer là một loop riêng.
- `tool_read_node` 11 lần / 4 agent, `tool_read_nodes_objective` 9 lần / 4 agent — phần này là
  phân rã thật, không phải lãng phí.
- Developer: **22/33 call là đọc**, chỉ 11 là submit.

**Nguyên nhân còn lại và bản vá:** `render_activity_set` nêu assessment item **bằng ID**, không nêu
nội dung — một Developer được bảo "chuẩn bị cho AT-03" mà không được cho biết AT-03 hỏi gì thì
buộc phải đi đọc. Đã mở rộng `_resolved_references` để resolve **mọi** thứ work set nêu tên
(objective + assessment item; material set vốn đã đủ).

**Chốt (user): GIỮ tool đọc cho Developer** — nó vẫn là agent thật, được quyền tự quyết. Thay vì
bỏ tool, nói thẳng trong prompt của nó: *"Everything your assignment names is written out below
in full. You do not need to look them up. Use the read tools only for something your assignment
does NOT name."* Giữ claim "mọi agent đều là agent", và vẫn cắt được phần đọc thừa.

## Bỏ scripted fallback + xoá hẳn control mode scripted (2026-09-01)

### 1. Bỏ scripted fallback — đo được vì sao phải bỏ

| arm | % artifact do **script** sinh (3 run) |
|---|---|
| `alignmentgraph-isd` | **26–35%** |
| `multi-prose` | 12–**76%** |
| `single-graph` / `single-prose` | **0%** |

Hai vấn đề chồng nhau: (a) gọi là "arm agentic" trong khi một phần ba output do script sinh là
claim mà trace không đỡ nổi; (b) **`ToolLoop` có đường cứu còn `ReactLoop` không hề có** — một
bên trục được cứu, bên kia bị thả, nên một phần khoảng cách đo được là chuyện đó chứ không phải
phân rã.

`_fallback` → `_give_up`: step kết thúc bằng **thứ model làm được**, và ghi rõ nó không hoàn tất
(`TrajectoryAction.AGENTIC_GAVE_UP`, `autonomy.gave_up`). Lưới còn lại bắt lỗi cho **cả hai** arm
là repair net deterministic. Con số trước đây bị giấu trong `via_fallback` giờ chính là phát hiện.

### 2. Xoá hẳn bản scripted (user: "all-in vào agentic rồi")

Xoá **~3.750 dòng**: `core/workflow.py` (941), 6 Designer + 4 Developer + `single_designer.py`
(2.290), và `control_mode="scripted"`.

Tách trước khi xoá: `core/outputs.py` (100 dòng) giữ 5 thứ agentic vẫn cần và vốn chưa bao giờ
thuộc về topology — `SELF_VALIDATION_BUDGET`, `_empty_required_fields`, `_collect_violations`,
`_collect_violations_prose`, `empty_addie`. `agents/` còn `base.py` + `addie_aggregator.py`.
**Prompt không mất gì**: chúng ở `rulebook.py`, thứ cả hai mode luôn compose từ đó.

**Hệ đang chạy đúng:** 4 arm smoke 0 lỗi validation, artifact đúng theo context mode,
`run_benchmark.py --check` sạch.

### [x] 28 test đã viết lại (không map cơ học)

`test_empty_section_regen.py` (8), `test_fanout.py` (5), `test_id_hygiene.py` (4),
`test_ablation_flags.py` (3), `test_call_gate.py` (1) và vài chỗ lẻ. Chúng **không phải đổi tên**
— là khác biệt hành vi thật giữa hai executor: regen ghi event khác, rubric nay mang `plan_set`
của set assessment, fan-out song song (LangGraph `Send`) không còn nên test parallelism mất tiền đề.

**339 test xanh**, `--check` sạch, 4 arm smoke 0 lỗi. Đã gỡ 2 đăng ký `alignmentgraph-isd-scripted*`.

Cách xử từng nhóm — mỗi cái nghĩ lại theo executor agentic, không đổi tên cho qua:
- **`test_fanout.py`**: 4 family → 3 (rubric không còn fan-out riêng); `dev_plan` nay do
  ORCHESTRATOR ghi chứ không phải Designer dispatch; arm single **không có** dev_plan event nào —
  và sự VẮNG MẶT đó chính là trục, thứ nó batch nằm ở `submits_per_stage`.
- **`test_empty_section_regen.py`**: executor mới hấp thụ câu trả lời rỗng NGAY TRONG stage
  (thêm một lượt) thay vì re-run cả node. Chuyển assert từ "có event regen" sang **tính chất**:
  không mất section, thử lại có ghi lại, và emptiness dai dẳng thì `gave_up` có ghi.
- **`test_id_hygiene.py`**: bắt được **2 bug thật** — xem dưới.
- **`test_ablation_flags.py`**: bỏ 5 test topology StateGraph; thay 2 test parity RULES/SCHEMA
  bằng test canh **cả hai arm đều đọc từ `AgenticStep.task_block()`** (parity nay đúng theo cấu
  tạo, không phải do canh gác); `test_scaffolding_*` bỏ phần joined-rendering đã mất.
- **`test_call_gate.py`**: fan-out song song qua LangGraph `Send` không còn — chuyển từ "chứng
  minh có song song" sang "không bao giờ vượt trần cấu hình".
- **`golden_prompts.json`**: 61 → 32 entry, chỉ còn bề mặt agentic.
- **conftest**: thêm `RepairActor` (dựng `RepairContext` không cần agent scripted); fixture
  assessment set nay trả **cả `rubric_criteria`** — trước đó thiết kế mới chưa hề được tập dượt,
  rubric toàn do repair net vá.

**2 BUG THẬT do test bắt được** (id hygiene là test đáng giá nhất đợt này):
1. `tools.render_nodes` in `[OBJECTIVE:objective:ILO-01]` — id có namespace, đúng thứ model nhại
   lại vào field tham chiếu rồi không khớp gì. Arm scripted có `_bare()`; bản agentic của tôi
   làm mất. Đã vá.
2. `tools.alignment_docket` rò namespace y hệt ở cả EDGES lẫn GAPS. Đã vá.
Cộng thêm: node SECTION nay header bằng type trần (`[ASSESSMENT_PLAN]`), bỏ id vô nghĩa
`assessment_plan_0` — một chuỗi nữa để model nhại.

## Refactor `base.py` + dời aggregator (2026-09-01)

`core/agents/` **đã xoá hẳn**. Nó chứa hai thứ không liên quan nhau bị gộp:

- **354 dòng hàm thuần** (parse/salvage JSON, truncation, token usage) → `core/llm_io.py`.
  Không dính agent, graph hay config; mọi control mode đều cần. Mỗi hàm ở đó trả lời một lỗi ĐO
  ĐƯỢC chứ không phải giả định.
- **`_format_design_brief`** → `core/brief.py`, cùng `_DESIGN_GUIDANCE` mà nó nối vào — nó format
  một `DesignBrief`, chỗ của nó là cạnh `DesignBrief`.
- **`BaseISDAgent`** (~520 dòng) → xoá. Subclass thật duy nhất còn lại là `ADDIEOutputAggregator`,
  và nó chỉ dùng `self.graph` + `self.trajectory`; toàn bộ phần còn lại (element context,
  alignment state, decompose, regen sets, maybe_retrieve) đã chết theo các specialist.
- **`addie_aggregator.py`** → `core/aggregate.py`. Nó chưa bao giờ là agent: không persona, không
  self-validation, không gọi model — nó đọc state rồi serialize theo contract ở `validation.py`,
  nên chỗ của nó là cạnh contract đó. Kế thừa `BaseISDAgent` chỉ để lấy hai thuộc tính chính là
  lý do nó kéo theo 886 dòng máy móc gọi model.

`core/` giờ: `aggregate brief checks dev_plans llm llm_io outputs prose_store ratelimit repairs
rulebook runner trajectory validation` + `agentic/` + `alignment_graph/` + `rag/`.

339 test xanh, `--check` sạch, 4 arm smoke 0 lỗi.

## Webapp + `on_event` theo hướng agentic (2026-09-01)

Demo app vẫn nói bằng từ vựng của pipeline scripted đã xoá. Ba nhóm, hai nhóm đầu là **sai thật**
chứ không phải cũ:

1. **Tên phase chết hết.** `PHASE_LABELS` khoá theo tên node LangGraph (`outcome_designer`,
   `rubric_designer`, `monolithic_designer`); harness giờ phát tên stage
   (`analysis outcomes assessment activities content implementation` + `aggregate`), single arm
   phát đúng một phase `design`. Chỉ `aggregate` còn khớp — 6 nhãn còn lại rơi về `humanise()`.
2. **Card ghi tên sai agent.** `agent_step` cũ ghi *last wins*; Developer step SAU Designer trong
   CÙNG phase (fan-out không đổi phase), nên stage assessment bị gán cho
   `AssessmentDeveloperAgent`. Đổi thành *first wins* + thêm `block.agents` (mọi agent đã hành
   động trong block) → chip lọc có Developer, pill hiện cả hai tầng.
3. **Không thấy phần agentic.** `dev_plan` (fan-out), `reconcile` (routing), `doc_write` (prose)
   đều rơi vào `'other'`. Thêm hai kind `plan`/`route`, `doc_write` → `write`; đổi
   `agentic_fallback` (đã chết) sang `agentic_gave_up` + `budget_exhausted` +
   `tool_binding_unavailable` + `tool_call_markup_recovered`.

Hai sửa **upstream** vì UI không hiển thị được thứ không được phát ra:

- `log_reconcile_result` / `log_doc_write` chỉ ghi `events`, không vào deep action log → live
  stream mù. Mirror thêm `log_action` (đúng pattern `log_dev_plan` đã dùng). Prose arm từ chỗ
  "18 model turn, không sản phẩm nào" giờ ghi 10 `doc_write`.
- **Pass reconciliation giờ là một phase riêng** (`_phase(trajectory, "reconcile", ...)`).
  Trước đó nó chạy NGOÀI mọi bracket, mà nó log một check round cho mỗi family + một route cho
  mỗi owner → tất cả rơi vào stage đóng cuối cùng. Người xem đọc ra stage `implementation` đã
  tự kiểm lại những artifact nó chưa từng đụng. `phase_total` 7→8 (multi), 2→3 (single).

Giữ lại có chủ đích: `parallelGroup`. Thiết kế hiện tại **không bao giờ** overlap phase (stage
tuần tự, Developer chạy một work set một lần), nhưng run cũ trong DB replay qua đúng hàm fold
này, nên cơ chế bracket-driven ở lại — comment nói rõ vậy thay vì mô tả concurrency không còn.

**Chưa làm, có chủ đích**: app vẫn chỉ chạy `HarnessRunConfig(llm_factory=...)`, tức luôn
multi+graph. Cho chọn `agent_mode`/`context_mode` là biến app từ demo đóng góp thành công cụ
ablation — nếu cần cho buổi bảo vệ thì nói, không thì để nguyên.

339 test Python + 44 test webapp xanh, `tsc -b` + `vite build` sạch.

## Chẩn đoán run `single_20260901_205901` (2026-09-01)

Điểm: react-isd 80,9 | main 79,7 | single-prose 77,3 | **multi-prose 60,1** | **single-graph 49,0**.
Không phải model yếu. **Một lỗi ở biên transport, kéo theo bốn lỗi khuếch đại.**

### Gốc: `coerce_args` chỉ dùng `json.loads`

Parser `qwen3_coder` trả giá trị có cấu trúc dưới dạng text, và chuỗi nó sinh ra **không phải JSON
hợp lệ**: đo được, một `instructional_strategies` dài 4.371 ký tự là JSON nháy kép nhưng có một
phần tử nháy đơn chèn giữa mảng —
`"resources": ["Planning template", 'Documentation of project scope']` — nên `json.loads` chết ở
ký tự 1.979 và **toàn bộ artifact bị tính là lỗi của model** ("arrived as text").

Harness ĐÃ có parser khoan dung cho đúng lớp near-JSON này (`parse_json_response`, đường plain-text
vẫn dùng). Kiểm chứng trên chính giá trị đo được: nó trả về đủ 4 khoá, đủ 9 phần tử `sequence`.
Sửa = gọi nó làm bước hai sau `json.loads` (strict trước, để run nào cũng đo được sức khoẻ
transport thay vì để salvage âm thầm gánh ca thường).

### Bốn lỗi khuếch đại

1. **Cap chỉ đếm submit ĐƯỢC NHẬN.** `submits_per_stage.assessment == 1` trong khi bị từ chối thêm
   76 lần → `SUBMIT_CAP` không bao giờ chạm. single-graph cháy đủ 96 turn, tới 3/6 stage,
   Analysis 0,0 và Implementation 0,0. Nay đếm cả hai; `submits_per_stage` vẫn chỉ ghi cái đã
   commit (gộp vào sẽ khiến stage kẹt đọc ra như stage năng suất).
2. **Lỗi phái sinh dẫn model đi sai.** `validate_assessment` báo ĐỒNG THỜI "assessment_plan …
   got str" và "assessment_plan.pilot_data_plan.anticipated_difficulties must be a non-empty
   list". Cái thứ hai là HỆ QUẢ của cái thứ nhất, không sửa được khi cái thứ nhất còn — nhưng nó
   nghe cụ thể hơn, và model đuổi theo nó 61 lần liên tiếp. Nay: một sự thật gốc → một lỗi.
3. **Hai reader cho `lo_coverage_targets`, và chúng bất đồng.** Model viết dạng giàu hơn
   (`{plan_category, instrument}`). `dev_plans` chặn bằng `_VALID_CATEGORIES` → bỏ sạch cặp →
   **âm thầm** tụt về work set summative-only. `checks.plan_coverage` không chặn → lấy
   `str(dict).lower()` làm category → mọi cặp đọc ra là chưa thực hiện. Nay một reader chung
   (`dev_plans.plan_category_pairs`) nhận cả hai dạng.
4. **Repair tự sinh ra chính vi phạm nó đi sửa.** `f"AT-{category[:1].upper()}-{lo_id}"` với
   category là dict cho ra id `AT-{-ILO-01` — **một id cho cả ba category của một objective**, nên
   ba item repair đè lên một node, 8/12 cặp hứa mãi không thành, repair bắn lại mỗi vòng:
   21 repair, `repair_success_rate` **0,0**, 16 residual. Id hỏng còn rò vào
   `prepares_for_assessment` của 4 activity và vào alignment matrix (tức vào cả tín hiệu RQ2).
   Nay dùng bảng tag tường minh D/F/S.

Cộng thêm một crash thật: `_invoke_with_retry` gọi `m.get("content")` trần trên transcript HỖN HỢP
(vòng tool-call để lại message object của model; repair arm single chạy trên chính transcript đó)
→ `'AIMessage' object has no attribute 'get'`, mất trắng 4/84 call. Và `_prompt_chars` bản
dict-only là bản sao sai âm thầm của `_prompt_chars_any`: nó bỏ qua mọi assistant turn mang
artifact — đúng thứ duy nhất đáng đếm. Đã xoá, còn một hàm.

### Hệ quả cho kết luận

Xếp hạng của run này bị chi phối bởi các lỗi trên, **không** bởi hai trục ablation. Không đọc
`agent_mode`/`context_mode` từ nó. Kiểm sau khi chạy lại: `submit_rejected` phải về mức một chữ
số/arm, `via_budget_exhaustion=False`, `stage_order` đủ 6, `repair_success_rate` > 0, và không còn
id nào khớp `AT-{`.

10 test hồi quy mới (`tests/test_transport_recovery.py` + cap-đếm-từ-chối), 350 test xanh.

## Bỏ fallback text soạn sẵn trong repair (2026-09-01)

Nguyên tắc mới, ghi trong docstring `core/repairs.py`: **repair không bao giờ tự viết nội dung
sư phạm.** Chỉ còn hai loại — *structural* (sắp xếp lại id mà thiết kế đã có: C4/C7/P5, orphan,
evidence, Bloom verb tra bảng) và *generative* (giao cho model viết; model không viết thì
KHÔNG viết gì).

Đã xoá: `OBSERVABLE_RUBRIC`, `OBSERVABLE_DESCRIPTION`, `FALLBACK_METHODS`, `_fallback_item_text`,
`_fallback_pilot_data_plan`, activity "Guided practice for ILO-01" / "Hands-on practice for
ILO-01", module "Support module for TLA-01", câu "Re-scope delivery constraints after verifier
feasibility warning.", và câu nối thêm vào statement khi sửa Bloom verb. Mỗi cái đều **thoả chính
check của nó bằng cách tồn tại** — đúng lý do P6 đã audit-only từ đầu, giờ áp dụng nhất quán.

**Hệ quả có chủ đích**, đóng gói trong `repairs.REPORT_ONLY`:
`C3 C5 C6 P4 P6 activity_engagement bloom_mismatch_activity rubric_consistency feasibility
actionability`. Chúng vẫn nằm trong `OWNED_BY_FAMILY` (reconciliation vẫn gọi tên owner) nhưng bị
lọc ra trong `repair()` **trước** khi dispatch. Lọc ở một chỗ chứ không ở ba family: test tôi vừa
viết bắt được đúng lỗi này — sau khi bỏ template, cả ba dispatcher vẫn nhận C3/C5/C6 rồi **nuốt
mất** chúng khỏi `remaining`, tức lặp lại đúng khuyết điểm của template.

Số residual và `ready_to_aggregate: false` sẽ tăng. Đó là số trở nên thật, không phải regression.
Trên fixture: multi+graph residual 12 (trước bị template lấp), single+graph 4 + 4 `repair_unfilled`.

Thêm `TrajectoryAction.REPAIR_UNFILLED`: repair generative gọi model mà không nhận được gì thì ghi
`repair_unfilled` (recovery event, không lọt vào judge) thay vì ghi `repair`. Cần vì (a) một
`repair` event báo "không đổi gì" chính là thứ làm `repair_success_rate` vô nghĩa, và (b) không có
nó thì một model call biến mất khỏi sổ sách — hai test bất biến "mọi call là step hoặc repair" đã
đỏ đúng chỗ đó.

Cũng vá luôn `EVENT_ACTIONS` trong `test_benchmark_contract.py`: nó thiếu `reconcile` từ
2026-08-27 mà không ai biết, vì fixture chưa từng để sót vi phạm cross-family nào để route. Giờ
danh sách được đối chiếu với `TrajectoryAction` nên không thể lệch âm thầm.

356 test xanh, `--check` sạch.

## Cascade 3+1+1+1 của OutcomeDesigner: truncation, không phải model dốt (2026-09-01)

**Bốn event đó là MỘT lỗi**, báo ở bốn tầng: 3× `submit_rejected` (hết `SUBMIT_BUDGET`) →
`submit_invalid_final` → `agentic_gave_up` → `commit_invalid_section` (commit cái tốt nhất model
làm được). Rồi `regen_empty_section` chạy lại cả stage, nên `multi-prose` có 9/3/3/3 = ba lần lặp
y hệt của stage `analysis`.

Nội dung thật nằm ở trường chẩn đoán: **`args=` RỖNG** ở 6 lần đầu, `args=needs_analysis:dict`
(đúng một khoá, khoá ĐẦU TIÊN) ở 3 lần sau. Model không sai nội dung — arguments không tới nơi.
Đó là chữ ký của generation bị cắt ở trần token (8192): native tool call hết token trả về một call
**đúng cú pháp** với argument thiếu hoặc dở dang, **không có parse error nào để bắt**.

Vòng lặp: model bị báo "learner_analysis must be a non-empty object" → tưởng trường đó sai → viết
lại toàn bộ artifact → lại bị cắt ở đúng chỗ đó → 3 lần → give up.

Ba sửa:

1. `llm_io.finish_reason()` / `was_truncated()` đọc `response_metadata` (`length` /`max_tokens`).
   Trước đó không chỗ nào trong đường tool-call nhìn `finish_reason`.
2. `ToolTurn.truncated` → rejection nói TRƯỚC TIÊN "câu trả lời bị cắt, gửi NGẮN hơn, đừng viết
   lại tất cả", rồi mới liệt kê trường thiếu. Danh sách lỗi vẫn giữ vì "trường nào chưa tới" vẫn
   là nửa hữu ích.
3. Ghi cả shape **THÔ** lẫn shape sau coerce: `coerce_args` trả `{}` cho argument object không
   parse được, nên chỉ ghi shape sau coerce khiến "parser không đưa gì" và "model không gửi gì"
   thành cùng một chuỗi rỗng. Chín rejection của run này không phân biệt được là do vậy.

Thêm `truncated_turns` vào `autonomy` mỗi stage — nếu nó cao ở size nhỏ thì trần 8192 là ràng buộc
thật của thí nghiệm và phải nói trong §Threats, không phải đổ cho model.

358 test xanh.

## `analysis` có role riêng: NeedsAnalyst (2026-09-01)

`analysis` chạy dưới `identity="OutcomeDesignerAgent"`, trong khi persona của chính step đó viết
*"performing the Analysis phase of ADDIE"* — tên nói Design, việc nói Analysis. Đó là role duy
nhất ôm hai phase ADDIE, và là chỗ reviewer sẽ chọc vào định vị "role-decomposed MAS".

Sửa: `identity="NeedsAnalystAgent"`, `family="needs_analyst"`, persona nói rõ *"You do not design
the course — you establish what the design will have to answer to."* Rẻ: `multi` vốn đã mở context
mới cho mỗi stage, nên identity chỉ là **bản ghi ai làm việc gì**, không phải ranh giới context.

`needs_analyst` **không sở hữu check nào** (narrative phân tích không có check tất định nào soi),
nên nó vắng mặt hoàn toàn khỏi `repairs.OWNED_BY_FAMILY` — đọc bảng đó bằng `.get`. Trước đây vòng
repair per-stage sẽ log một round rỗng cho nó, tức báo "đã tìm, không thấy" về một lần tìm chưa
từng xảy ra; giờ skip.

Golden prompts đã regenerate (đúng 1 khoá đổi: `agentic.analysis.persona`). Webapp có hue riêng.
358 test xanh.

### Và analysis giờ submit theo TỪNG PHẦN

Tách *artifact* thay vì tách *stage*: `AgenticStep.submit_parts` khai báo 5 khoá top-level của
analysis. `stage_order` vẫn 6, và **không ép thêm call nào** — agent nào nhét vừa một lần vẫn nhét
một lần; chỉ agent không nhét vừa mới trả thêm turn.

Bốn thay đổi ăn khớp:

1. `validate_analysis` chỉ soi phần ĐÃ TỚI. Từ chối instalment đầu vì những phần nó chưa mang
   chính là lỗi mà việc tách này sinh ra để xoá. Yêu cầu "phải có improvement_plan" chuyển từ
   validator sang `missing_parts()`.
2. `missing_parts(step, state)` hỏi TRẠNG THÁI (section node ở graph, khoá document ở prose), không
   hỏi bộ đếm trong loop — bộ đếm sẽ bị regen reset và hai arm sẽ lệch nhau.
3. `ToolLoop` không `return` ở submit đầu nữa khi step có parts: nó nói "còn thiếu X, Y" rồi tiếp.
   Cap = 1 turn/phần + 3 slack.
4. `parts_block()` sinh instruction TỪ `submit_parts` chứ không viết tay vào prose của step — để
   hai arm nhận đúng cùng một câu chữ (khác đi là thêm biến thứ hai vào trục).

**Hai bug bắt được trong lúc làm:**

- `commit_analysis_prose` dùng `store.put` = GHI ĐÈ, nên submit thứ hai chỉ mang `task_analysis` sẽ
  xoá mất `needs_analysis`. Arm graph không dính (commit từng section độc lập) → nếu để nguyên,
  arm prose mất việc mà arm graph giữ, **đúng trên trục so sánh hai arm**. Đã merge top-level.
- `AGENTIC_GAVE_UP` thay `AGENTIC_FALLBACK` từ 2026-09-01 nhưng **chưa từng được thêm vào
  `_RECOVERY_ACTIONS`**, nên mọi lần give-up đều vắng mặt khỏi `recovery_events` — đúng cái view
  trả lời "run này hỏng chỗ nào". Đã thêm cả nó lẫn `BUDGET_EXHAUSTED`, và pin bằng test đối chiếu
  trọn vẹn với `TrajectoryAction`.

363 test xanh. Golden prompts regenerate (đổi persona + schema `required` của analysis).

## "Bỏ cái đọc không được, RỒI mới xét phần còn lại" (2026-09-01)

Bằng chứng: `AssessmentDeveloperAgent`, attempt 2, `args=assessment_tools:list,rubric_criteria:str`.
`assessment_tools` ĐÃ đúng — validator của `set_step` chỉ đòi output PRIMARY nên nó sẽ pass — mà cả
submit vẫn bị vứt vì trường **thứ cấp** `rubric_criteria` là string. Nguyên một set item tốt bị
ném đi vì phần rubric bên cạnh.

Trớ trêu: docstring của `set_step` đã viết đúng lý do không được gate lên output thứ cấp
(*"making it a hard gate would throw away a whole set of good items"*) — nhưng `shape_errors` lại
gate đúng chỗ đó, cao hơn một tầng.

Sửa: **drop-then-judge**. Bỏ mọi argument không đọc được ra, validate phần còn lại.
- Còn lại hợp lệ → NHẬN, ghi `dropped_argument` (recovery event, có `dropped_args` trong autonomy).
  Rubric có repair riêng; item tốt không đáng chết theo.
- Còn lại không hợp lệ → shape error nổi lên dẫn đầu như cũ, vì đó ĐÚNG là lý do nó hỏng.

Tôi đã thử tiêu chí `required` trước và **sai**: analysis giờ không trường nào `required` (do
`submit_parts`), nên một submit toàn string sẽ bị drop sạch rồi im lặng. Tiêu chí đúng không phải
"trường này có bắt buộc không" mà là "bỏ nó ra rồi còn artifact hợp lệ không".

Áp cho cả hai vòng lặp — hai arm phải đồng ý về "khi nào một submit được chấp nhận", nếu không trục
đo lại đo chính sách chấp nhận thay vì ranh giới context.

Ghi chú về chính dữ liệu này: attempt 1 cả hai đều `str`, attempt 2 trường ĐẦU thành `list` còn
trường CUỐI vẫn `str` — cùng chữ ký truncation như ca `analysis` (khoá đầu sống, khoá cuối bị cắt).
Model đã đọc hiểu và sửa đúng một trường; nó không dốt, nó bị cắt.

365 test xanh.

**Đòn bẩy tiếp theo nếu vẫn còn**: cho `submit_parts` xuống tầng Developer (items trước, rubrics
sau). Giá: +1 turn cho MỖI work set (2–5 set/family), nên chỉ làm nếu run mới còn thấy
`rubric_criteria` bị drop nhiều.

## Đính chính: truncation KHÔNG phải nguyên nhân chính (2026-09-01)

Tôi đã gọi trần 8192 là chữ ký của ca `analysis`. **Số đo không ủng hộ điều đó.** Cùng run:

- completion trung bình **470 token / 95 call**. Nếu nhiều call chạm 8192 thì trung bình đã kéo lên.
- work set thực tế **1 objective/set, 4 set** — mỗi Developer call viết ~3 item + 3 criterion
  ≈ 4,5k ký tự ≈ 1,2k token. Xa trần.

Nguyên nhân trội vẫn là **parser**: cả `args=` rỗng lẫn `rubric_criteria:str` khớp với
"argument object là chuỗi near-JSON, `json.loads` chết" — đúng thứ có bằng chứng trực tiếp trong
run này (chuỗi 4.371 ký tự nháy kép lẫn nháy đơn) và đúng thứ `coerce_args` salvage đã sửa.

Phần instrument `finish_reason`/`truncated_turns` vẫn giữ: nó rẻ, và nó là thứ **kết luận được**
câu hỏi này ở run sau thay vì phải suy từ dấu hiệu gián tiếp. Nhưng nó là công cụ đo, không phải
chẩn đoán đã xác nhận.

## Work set: giữ nhóm LO, chia tiếp TRONG mỗi LO theo SỐ LƯỢNG ĐÃ PLAN

Chia theo LO không nói gì về việc set đòi bao nhiêu. 3 objective là set nhỏ với activity nhưng lớn
với assessment, vì một obligation assessment đẻ ra một item VÀ criterion chấm nó.

`UNIT_CHARS` = chi phí ước tính của MỘT obligation, ghép từ hai nửa đều đo được:
- kích thước element: item ~1.140 (max 2.973) + criterion ~355; activity ~635; material ~1.240
- sản lượng: 2,5 item/objective; 1,5 activity/objective (biên độ 1,0–4,2 và 0,8–2,5 giữa các arm)

→ `{assessment: 1800, activity: 1300, material: 1800}`, `SET_OUTPUT_BUDGET = 11000`
→ 6 / 8 / 6 unit mỗi set.

**Đơn vị chia là SỐ ARTIFACT ĐÃ PLAN, không phải số LO** — và nó được lấy từ rule đang có hiệu lực
cho từng family, không phải ước lượng:

| family | số lượng đã plan | nguồn |
|---|---|---|
| assessment | số (objective, category) pair trong set | `RULES_ASSESSMENT_ITEMS_SET`: *"exactly one item for every pair it lists"* |
| content | số media selection của module | `RULES_MATERIALS_UNIT`: material phải hiện thực một trong các media selection |
| activity | `expected_activities` do chính planner khai | **mới thêm** vào `SCHEMA/RULES_ACTIVITY_DEV_PLAN` |

Activity là family duy nhất **không có** số lượng nào được plan — không rule nào nói một objective
cần mấy activity. Nên planner được hỏi thẳng (nó là bước duy nhất biết block là "một bài tập" hay
"tiến trình sáu bước"), và **không được tin**: `_expected()` clamp về [1, 12], thiếu/rác thì rơi về
yield đo được (3/objective).

**Giữ ranh giới LO.** Chia theo danh sách pair phẳng sẽ đưa đuôi của ILO-01 và đầu của ILO-02 vào
cùng một piece — vứt đi chính nhóm mà plan đã chọn và cái stem chung mà set được dựng quanh. Nên:
tách theo objective trước, objective nào tự nó vẫn quá lớn thì mới chia batch trong nội bộ nó.

Ví dụ của bạn (LO1 20 item, LO2 25 item, limit 6): **9 set — 4 cho LO1, 5 cho LO2**, không set nào
lẫn hai LO.

**Scope là việc của PLAN, không phải của backstop.** "Viết khác batch kia" là lời khẩn cầu, không
phải ràng buộc — hai Developer viết độc lập, không thấy nhau. Nên `RULES_ACTIVITY_DEV_PLAN` giờ
nói thẳng: (a) hai block không được trùng địa hạt vì mỗi block do một developer khác viết mà không
thấy các block kia; (b) mỗi block phải viết được trong MỘT lần trả lời, tối đa N activity; (c) một
objective cần nhiều hơn thì tách thành NHIỀU block, mỗi block mang `block_theme` nêu scope riêng
(giai đoạn của tiến trình), không phải chép lại objective.

Con số N được **import từ chính `max_units("activity")`**, không viết tay: planner bị bảo "tối đa 8"
mà harness cắt ở 6 thì nhóm nó vừa lập bị tháo ra sau lưng, và scope nó viết không còn khớp set
thực sự được dispatch.

Backstop tất định vẫn còn nhưng giờ đúng nghĩa cuối cùng, và được ĐẾM: `oversized_splits` trong
`dev_plan` event — số duy nhất phân biệt "plan làm đúng việc" với "backstop đang gánh". Khi nó
phải cắt, phần được cắt nêu theme mà nó đang chia (`part 2 of 2 of 'pipeline'`) thay vì chỉ số thứ
tự trần. Quota được **chia** chứ không lặp: plan 10, limit 8 → 2 × 5, không phải 2 × 8.

**Lỗi bắt được khi kiểm chính thay đổi này**: cap số set tính theo số OBJECTIVE
(`MAX_SET_FACTOR × len(los)`), nên một objective chỉ được một block — hai block đã scope đúng cho
ILO-01 bị **gộp lại và mất theme**, tức harness tháo đúng thứ nó vừa yêu cầu. Cap giờ tính theo
tổng activity đã plan: không bao giờ cần nhiều block hơn số activity.

**Lỗi ngược đã sửa**: `_cap_and_number` khi vượt trần số set thì **GỘP** phần dư vào một set đuôi.
Tức trần số CALL làm cho chính các call trở nên không trả lời nổi. Trên ca 33 objective mà comment
trong code đã cảnh báo: 12 set, trong đó set đuôi ôm **88 obligation trong một call**. Giờ size
được áp SAU merge và thắng count → 22 set, tối đa 6 pair/set.

Đánh đổi nói thẳng: số set có thể vượt `MAX_SETS_HARD_CAP`. Một set không trả lời nổi mất trắng
mọi thứ nó định sản xuất; một call thừa chỉ tốn một call. Ngân sách 11.000 nằm ~2,5× dưới trần
28k ký tự — không siết hơn, vì siết gấp đôi thì 99 obligation thành 33 call thay vì 22, mà trần
lại không phải chỗ các run này đang hỏng.

Scenario nhỏ không đổi gì (fixture: 5/5/2 set như trước). 370 test xanh.

## Webapp: tab Trajectory + tab Context + export (2026-09-01)

**Tab `Activity` → `Trajectory`.** Mục đích của nó là visualize trajectory 1:1, tên cũ không nói
điều đó.

**Export nằm TRONG tab Trajectory**, và chỉ chở trajectory: `trajectory` (bộ ba judge đọc + event
log) + `trajectory_deep` (action log). Không metadata, không graph, không ADDIE output — mỗi thứ đó
đã có artifact và endpoint riêng, gộp vào sẽ khiến "export trajectory" nghĩa là "export cả run", và
rồi không ai export được trajectory nữa. Nút đặt cạnh toggle Story/Audit chứ không ở run header:
cạnh Run/Cancel thì nó đọc như hành động cấp-run.

**Tab `Context` mới: lưới theo agent.** Trả lời "agent ĐƯỢC XEM gì", nửa còn lại của câu hỏi mà tab
Trajectory ("agent ĐÃ LÀM gì") không trả lời được. Trước đó **không nơi nào ghi lại**: `autonomy`
chỉ có `context_len` (một con số), còn transcript sống trong bộ nhớ vòng lặp rồi mất khi run kết
thúc.

Cơ chế: `emit_context()` phát `context_snapshot` qua `on_event` — hook quan sát vốn "purely
additive, không consumer thì mọi emit là no-op". **Cố ý KHÔNG ghi vào
`trajectory`/`trajectory_deep`**: judge đọc hai cái đó, benchmark so sánh chúng giữa các arm, nhân
đôi kích thước bằng bản sao thứ hai của mọi artifact là đổi thứ đang được ĐO để phục vụ người xem.

- `serialize_messages()` phẳng hoá transcript HỖN HỢP (dict + message object của model) và **luôn
  copy**: list sống bị append, bị trim, và ở arm single bị `_compact` ghi đè tại chỗ.
- Tool schema đi kèm. Dưới native tool calling **schema là một nửa những gì model thấy**, nên
  context không có schema là nửa context. (`golden_prompts.json` pin cả hai vì đúng lý do này.)
- Server giữ như STATE chứ không forward như event, đúng lý lẽ đã áp cho graph: transcript to, chỉ
  bản cuối đáng đọc. Lưu thành `contexts.json`, endpoint `GET /runs/{id}/contexts`.
- Card mở ra thì span hết chiều rộng — transcript trong cột 340px là không đọc được.

Số lượng snapshot tự nó là trục decomposition: arm multi phát 18 (6 stage + 12 Developer work set),
arm single phát **đúng 1**. Đó là hình dạng của trang, không phải một con số trong bảng.

470 test xanh (377 package + 93 server), `tsc -b` + `vite build` sạch.

### Chi tiết export (giữ nguyên từ bản đầu)

`GET /api/runs/{id}/trajectory/export` → MỘT file JSON tải về, gồm `metadata` (autonomy theo
stage, residual audit, repair metrics, token usage) + `trajectory` (bộ ba judge đọc + event log) +
`trajectory_deep` (action log đầy đủ) + định danh run.

Bốn mảnh này server đã phục vụ riêng lẻ qua `/artifacts/{name}` (UI đang đọc thế). Đó **không phải**
export: ghép lại một run từ bốn lần fetch chính là bước người làm tay hay sai, và bốn mảnh chỉ có
nghĩa khi đọc cùng nhau — action log mà không có `autonomy` thì không nói được stage có cháy turn
hay không, và `autonomy` mà không có log thì không nói được nó đã làm gì với số turn đó.

Export **giữa lúc đang chạy** trả về phần đã ghi, từ live event log, dưới khoá `live_events` và
`complete: false`. Đây đúng là lúc người ta cần đọc trace nhất (run trông như treo). Trả file bán
phần dưới **cùng hình dạng** với file hoàn chỉnh mới là cái bẫy, nên wire event giữ khoá riêng.

Nút ở `RunHeader`, là `<a download>` thật chứ không fetch-rồi-blob: server đã đặt tên file trong
`Content-Disposition`, kéo JSON vào bộ nhớ chỉ để serialize lại sẽ mất tên đó và mã hoá lại đúng
thứ vốn đã sẵn sàng ghi ra đĩa. Mid-run nút đổi nhãn thành "Export so far".

467 test xanh (377 package + 90 server), `tsc -b` + `vite build` sạch.

## Salvage phải theo ĐÚNG KIỂU đã khai (2026-09-02)

Payload thật từ một submit 2B: `assessment_tools` là chuỗi chứa mảng 3 item, mọi ký tự của cả 3
item nguyên vẹn, chỉ **hai dấu ngoặc cuối bị đảo** — đóng bằng `..."]}` thay vì `..."}]`.

`json.loads` chết. Salvage CÓ chạy nhưng **trả về `dict` 8 khoá** = đúng item đầu tiên, bỏ hai item
sau. Nguyên nhân: `parse_json_response` **dict-oriented ở mọi nhánh** — nhánh "Try 1b" gọi
`raw_decode` từ dấu `{` đầu tiên, nên trên một MẢNG hỏng nó vớ phần tử một rồi coi đó là câu trả
lời.

Chỉ có type check trong `coerce_args` (`isinstance(parsed, wanted)`) chặn không cho 1 item được
commit như thể là cả bộ. Nhưng vì kiểu sai nên giá trị bị giữ nguyên chuỗi → `shape_bad_keys` gắn cờ
→ bị pop → submit bị từ chối. Mất trắng cả 3 item.

Sửa: `llm_io.parse_json_array()` — quét khối `{...}` top-level bằng cân bằng ngoặc (bỏ qua ngoặc
trong chuỗi, xử lý escape), parse từng phần tử ĐỘC LẬP. Một phần tử hỏng chỉ mất phần tử đó, không
mất cả submit. Gặp dấu đóng thừa thì resync thay vì bỏ phần còn lại — đó chính là ca transposition
này. `coerce_args` chọn parser theo kiểu schema KHAI BÁO (`want_array`), không dùng chung một parser
cho mọi kiểu nữa.

Trên payload thật: **3/3 item được vớt, dropped=0**, submit từ chối → được chấp nhận, validator sạch.

`dropped` được trả về chứ không nuốt, và đi vào `args_salvaged` dưới dạng `"assessment_tools (-1)"`:
vớt 2/3 rồi im lặng cũng là cùng một lớp lỗi với vớt 1/3.

474 test xanh. Test hồi quy dùng chính payload đo được.

## Nâng turn budget (2026-09-02)

`ToolLoop.MAX_TURNS` 8→**12**, `DEVELOPER_MAX_TURNS` 4→**6**.

Bằng chứng: **cả 5 `agentic_gave_up` của run f42dceff đều là "turn budget exhausted"**. Và một
stage give-up thì bị REGEN — implementation tiêu 16 call = 8×2 lần. 12 turn một lần rẻ hơn 8 turn
hai lần bất cứ khi nào nó biến give-up thành hoàn thành. Với Developer, 4 nằm **dưới** nhu cầu đã
đo (5,4 turn/material set): cap thấp hơn công việc thật không tiết kiệm, nó chế ra give-up.

**Sửa kèm một bẫy parity**: `react.MAX_TURNS` viết cứng `8 * len(STEPS) * 2`. Nâng bên multi mà để
nguyên số 8 đó thì hai phía của trục decomposition có trần khác nhau một cách âm thầm. Giờ cả hai
suy từ `loop.STAGE_MAX_TURNS` (single = 12×6×2 = 144).

**Nói thẳng giới hạn**: nâng trần KHÔNG chữa nguyên nhân. 62% call của run đó là đọc/lặp lại thứ
prompt đã chứa sẵn. Trần cao hơn phủ lên phần lãng phí đó chỉ mua thêm lãng phí — nó chỉ mua đúng
những stage đang chết vì thiếu 1–4 turn. Việc phải làm vẫn là chặn lần đọc thừa đầu tiên.

## Đọc thừa: từ lời khuyên sang ràng buộc (2026-09-02)

Instruction `_ASSIGNMENT_IS_COMPLETE` đã có, đặt ở vị trí tốt nhất (dòng đầu intro của Developer,
ngay trên chính khối dữ liệu nó nói tới), và **đã hết dư địa**: read/Developer-call 22/33 = 67%
(run 171408) → 26/63 = 41% (run f42dceff), nhưng cộng cả lặp lại thì vẫn 42/63 = **67%**. Phần tiết
kiệm bị lặp-lại ăn hết.

Sửa: `ToolLoop._already_in_assignment()` trả lời con trỏ thay vì render lại. Harness BIẾT nó resolve
gì vào assignment (`fanout.resolved_labels`), nên "đừng đọc lại" thôi là thứ model phải **nhớ**, giờ
thành thứ nó **quan sát** ngay tại chỗ. Tool vẫn bound — Developer vẫn là agent thật — chỉ là lần
đọc thừa không còn trả về phần thưởng.

`_reference_blocks()` khai báo MỘT lần, dùng cho cả render lẫn con trỏ: hai danh sách sẽ trôi khỏi
nhau, và con trỏ chỉ tới một heading không tồn tại còn tệ hơn không có con trỏ.

## Webapp: Context dạng list + thanh context window (2026-09-02)

Đổi grid → list, mỗi agent một dòng. So sánh đáng quan tâm chạy DỌC theo cột: mỗi agent mang bao
nhiêu context và nó đi vào đâu.

Thanh dùng **một thang chung cho mọi dòng** — thang riêng từng dòng sẽ khiến context nhỏ nhất trông
đầy như context lớn nhất, đúng phép so sánh mà view này sinh ra để làm.

**Hiển thị bằng TOKEN**, không phải ký tự: token là đơn vị cửa sổ được đo và là thứ thật sự cạn; ký
tự chỉ là đơn vị code này đếm. Quy đổi đi qua tỉ lệ đo được của run.

**Ba phần là một PHÂN HOẠCH THẬT**, cộng đúng bằng tổng — có test chốt:

| phần | là gì |
|---|---|
| System prompt | chỉ dẫn và luật cho model |
| Messages | hội thoại thật: text của user và assistant |
| Tools | tool call VÀ kết quả — tên hàm, tham số model yêu cầu, dữ liệu trả về |

Bản đầu của tôi **sai**: phần "Tools" đo bound SCHEMA, thứ không hề nằm trong message list, nên ba
phần chồng lên tổng thay vì chia tổng — thanh nói dối về cái gì đã lấp đầy cửa sổ. Schema vẫn là
context thật nên được báo **BÊN CẠNH** phân hoạch ("Sent alongside: N tokens"), không gộp vào.

Điểm dễ sai thứ hai: artifact của một submit nằm trong **tool call**, không nằm trong `content` —
assistant turn khi submit có content RỖNG. Tách theo `content` sẽ hiển thị run không sản xuất gì.

**Transcript phải nói cùng ngôn ngữ với ba phần đó** (sửa tiếp): trước đó nó tô màu theo ROLE
(assistant tím / tool xanh lá / user xanh dương) và gộp tool call chung khối với text của assistant —
tức transcript mâu thuẫn với chính thanh ngay phía trên nó. Một assistant turn gọi tool đóng góp
vào HAI phần khác nhau: text là Messages, tool call là Tools. Giờ nó render thành hai khối riêng,
tô đúng ba màu của thanh, và nhãn nói rõ `tool call · submit` / `tool result · submit`.

Va chạm tên cũng phải xử: section "Tools" vốn là SCHEMA, trong khi phần "Tools" của budget là
call+result. Đổi thành **"Tool schemas"**, và cố ý KHÔNG cho nó chấm màu — nó gửi kèm mọi request
nhưng không nằm trong message list, nên không phải một trong ba phần.

Thanh context window bỏ khỏi list view, chỉ hiện khi mở một item — ở list view nó chiếm chỗ mà
không trả lời câu hỏi nào của list.

## Trim budget suy từ cửa sổ phục vụ (2026-09-02)

`HISTORY_CHAR_BUDGET = 24000` là con số ma, không liên hệ gì với model đang được phục vụ. Giờ nó
suy ra: `history_budget(config)` = `(llm_context_window − llm_completion_reserve) × CHARS_PER_TOKEN`.

Tỉ lệ char/token **được ĐO trên chính traffic của run**, không phải hằng số và không phải thư viện
tokenizer. Lý do không dùng thư viện: `tiktoken` là vocabulary của OpenAI còn ladder phục vụ Qwen —
nó cho một ước lượng KHÁC chứ không phải một ước lượng ĐÚNG; còn tokenizer thật của model thì phải
kéo `transformers` + vocab vào một package mà benchmark cài trần (`test_import_isolation.py` canh
đúng chuyện đó).

Câu trả lời chính xác vốn đã tự đến: **mỗi response đều báo `prompt_tokens`** cho một prompt mà ta
biết số ký tự. Chia ra là có tỉ lệ thật của model này trên nội dung thật của run này — phán quyết
của chính tokenizer, quan sát được chứ không xấp xỉ, miễn phí và không phụ thuộc. Nó tự hiệu chỉnh
theo model và theo hình dạng artifact, thứ mà không hằng số nào và không vocabulary ngoại lai nào
làm được.

`TokenRatio` cache theo RUN (đúng pattern `ratelimit.gate_for`) nên cả hai arm hiệu chỉnh trên cùng
traffic. Đo được rồi vẫn **không bao giờ nâng** ước lượng lên trên `COLD_CHARS_PER_TOKEN = 3.0`:
budget này là giới hạn an toàn, tỉ lệ đo trên các lượt nhiều văn xuôi sẽ cho phép một prompt mà lượt
nhiều JSON làm tràn. Provider không báo usage thì tỉ lệ giữ nguyên chứ không tụt về 0.

**Bất biến thật là budget theo TOKEN** (`window − reserve`), giống hệt nhau ở cả hai arm. Ký tự chỉ
là đơn vị `trim_history` đếm, và quy đổi đi qua tỉ lệ đo được — nên arm nhiều transcript và arm
nhiều schema có thể ra budget KÝ TỰ hơi khác nhau trong khi giữ cùng budget token. Thế mới đúng:
cào bằng ký tự sẽ cho hai arm lượng khác nhau của thứ thật sự cạn.

Con số thực tế:

| cấu hình | budget |
|---|---|
| không set (standalone) | 24.000 — y như cũ |
| window 16384, reserve 8192 (ladder) | **24.576** |
| window 32768 | 73.728 |
| window 8192 = reserve (sai cấu hình) | 3.072 (sàn) |

Trên cấu hình ladder, khởi đầu lệch **2,4%** so với hằng số cũ — hằng số đó chọn khéo — rồi sắc dần
theo số đo. Kiểm end-to-end với model có báo usage: cold 3,00 → đo được 2,00, budget 24.576 → 16.385.

**MỘT số cho CẢ HAI arm** — có test chốt. Trục `agent_mode` là ranh giới context; budget khác nhau
theo arm sẽ khiến hai bên tiêu effort khác nhau và trộn lẫn "thấy ít hơn" với "làm ít hơn".

Adapter đọc `AGENT_MODEL_CONTEXT_WINDOW` (window pod được khởi chạy) và `AGENT_MODEL_MAX_TOKENS_CAP`
(reserve — chính biến benchmark áp đồng đều cho mọi agent). Không set thì không đổi gì.

479 test xanh.

## Rubric ra khỏi graph: 7 core relation còn 5 (2026-09-02)

Lý do không phải chi phí mà là **mô hình sai**: rubric là rubric CỦA assessment, chỉ phục vụ
assessment, và Assessment Developer đã viết chúng như một cặp trong cùng một call.

**Bằng chứng quyết định — C6/C7 không thể sai:**

- `C6` được lập bằng `record_provenance` ngay trong `commit_sets`, tức ghi lại quan hệ chứa mà chính
  commit vừa tạo ra cả hai đầu. Không khớp gì cả.
- `C7` = `C6 ∘ C2`. `RULES_RUBRICS` bắt buộc *"aligned_objective must name the SAME objective that
  item already measures"*, và khi sai thì repair sửa bằng cách lấy objective của chính item đó.
  Không mang thông tin độc lập nào.
- Đo được: **28/28 run, C6 = C7 = coverage 1.0.**

Một quan hệ không thể sai thì không phải bằng chứng construct validity. Nói "7 core, mỗi cái có
citation" trong khi 2 cái được bảo đảm về cấu trúc thì **yếu hơn** nói 5 cái mà mỗi cái thật sự gãy
— và reviewer đọc bảng coverage thấy 1.0 ở mọi cell sẽ hỏi đúng câu này.

**Thay đổi**: `SetOutput.attach_to` — output con được file thẳng lên artifact cha
(`fanout._attach_to_parent`), trên CẢ HAI substrate. Nội dung rubric không mất gì: nó vốn đã tới
output bằng một phép join theo id (`_attach_rubrics`, nay là `_shape_rubrics`) chưa bao giờ cần
graph — chính vì thế arm prose không graph vẫn xuất được rubric.

Đi theo C6/C7: `NodeType.RUBRIC`; `orphan_rubric` (criterion không thể mồ côi khi nó nằm TRONG item);
`alignment.match_id` (C7 là caller duy nhất); `audit.unevaluated_objectives`; và chân rubric của
`viz.objective_alignment` — chân đó chưa bao giờ thu hẹp `aligned` vì nó đúng với mọi objective có
item. `rubric_consistency` và `evidence_alignment` **ở lại**, đọc criteria từ item bằng MỘT
implementation dùng chung cho hai substrate (trước đây graph và prose có hai đường riêng).

Cũng xoá theo vì hết caller: `rubric_work_units`, `render_rubric_set`, `MAX_RUBRIC_UNITS`,
`_rubric_sets`, `commit_rubrics`, `commit_rubrics_prose`, `validate_rubrics`.

Kết quả trên fixture, cả 4 arm: **10/10 item mang rubric**, 0 rubric node, 0 validation error, core
coverage C1–C5. Graph nhẹ đi 19/81 node và 38/185 edge trên scenario thật.

**Việc paper còn nợ**: §04_method khi viết phải nói 5 core (không phải 7) và nêu lý do — nó là lập
luận MẠNH, không phải lời xin lỗi. `docs/summary.md` và `rq2_protocol.md` không nêu số quan hệ nên
không phải sửa; RQ2 panel không đọc rubric nên không ảnh hưởng.

472 test xanh (379 package + 93 server), webapp 44 test + build sạch.

## Bốn quan sát từ tab Context (2026-09-02)

**1. Một submit hiện thành HAI lượt với hai tool result mâu thuẫn.** Lỗi tôi vừa gây ra:
`_append_committed` (assistant + "Move on to the next stage") chạy vô điều kiện, rồi nhánh parts
`_append_tool_turn` thêm một cặp NỮA ("still needs: ..."). Một call → hai assistant turn trong
transcript. Sửa: commit trước, trả lời MỘT lần, nội dung tuỳ theo còn thiếu gì. Kiểm: 5 submit từng
phần → đúng 5 assistant turn, 5 tool result, cái cuối mới nói "Move on".

**2. `dev_plan` lọt vào artifact được chấm.** Schema đặt `dev_plan` là SIBLING của `assessment_plan`
(đúng), nhưng model thấy cả hai trong một object nên nhét thêm một bản sao VÀO TRONG plan. Bản lồng
đó được commit thẳng vào plan node → metadata điều phối nằm trong artifact judge chấm, đúng thứ hợp
đồng của `dev_plans` cấm. `_without_dev_plan()` lọc lúc commit: bản top-level mới là bản fan-out
đọc, nên mất bản lồng không tốn gì.

**3. Rubric vẫn được HỎI dưới dạng danh sách độc lập** dù lưu trữ đã là field của item — và model
lẫn đúng chỗ đó (nó nhét một object `{"rubric_criteria": [...]}` làm phần tử thứ hai của mảng
`assessment_tools`). Sửa: criterion vào thẳng schema của item, bỏ `aligned_assessment`/
`aligned_objective` (item đã nêu objective rồi; lặp lại là bản sao thứ hai có thể mâu thuẫn). Kéo
theo: bỏ `SCHEMA_RUBRICS`, bỏ output thứ hai của fan-out, bỏ `SetOutput.attach_to` và
`_attach_to_parent` mà tôi vừa viết hôm nay — Developer giờ nộp MỘT mảng, không còn tham số thứ hai
để đến nơi dưới dạng chuỗi (đúng lỗi đã thấy hai lần).

**4. "Chỉ có 1 AT" là plan sai, harness thực thi đúng.** Set khai `objectives:[ILO-01, ILO-02],
plan_categories:[formative]` nhưng `lo_coverage_targets` chỉ hứa (ILO-01, formative) và
(ILO-02, summative) → cặp (ILO-02, formative) là filler, bị drop (`dropped_pairs`), còn 1 cặp = 1
item. `render_assessment_set` giờ nói thẳng số: *"write exactly N items"* thay vì để suy từ độ dài
danh sách — Developer viết thiếu sẽ lộ ra thay vì trông như đã xong.

**5. `check`/`repair` không có trong context — đúng thiết kế.** Chúng chạy trong `run.py` SAU khi
loop trả về, tác động lên state chứ không đi qua transcript của agent. Agent không bao giờ thấy
violation của chính nó. Đây là hạn chế thật đáng nêu trong §Discussion: repair là mạng lưới tất
định, không phải vòng phản hồi cho agent.

**Lỗi test bắt được**: cận số call trong `test_end_to_end...` đếm `repair_events`, nhưng một
generative repair trả về rỗng thì ghi `repair_unfilled` chứ không ghi `repair` — mà call vẫn tốn.
Đếm thiếu đúng 4 call. Cận giờ đếm ATTEMPTS.

472 test xanh.

## Context của repair, và tool schema thành phần thứ 4 (2026-09-02)

**Repair PHẢI nằm trong context — bạn đúng, và nó lộ ra một lỗ.** Repair sinh nội dung CÓ gọi model
(một prompt persona-free mỗi batch), nhưng ở arm multi đó là prompt riêng chứ không phải transcript
của agent — nên nó là context DUY NHẤT trong run mà không ai xem được. `_ObservedLLM` bọc caller
của repair ở cả hai arm và publish context của chính nó.

Kết quả làm trục hiện ra ở chỗ trước giờ chỉ được mô tả bằng lời:

| | prompt repair |
|---|---|
| multi | 2 message, 480 token |
| single | **27 message, 3.568 token** |

Cùng routine, cùng số vòng, cùng budget — khác lượng context. Đó chính là claim.

**Lỗi bắt được trong chính bản sửa**: lần đầu tôi publish `messages` truyền VÀO, tức prompt hai
message trước khi `_CarriedContextLLM` ghép transcript. Arm single sẽ báo thiếu đúng phần là trục
đo. Giờ publish `last_sent` — thứ thật sự được gửi.

**Tool schema thành segment thứ 4.** Thanh giờ vẽ TOÀN BỘ request (transcript + schema) thay vì chỉ
transcript, và bỏ dòng chú thích "sent alongside". Schema gửi kèm mọi request và tính vào cùng cửa
sổ; để nó ngoài là hiểu thấp chi phí thật của call.

**Còn cần schema trong system prompt không? CÓ.** Chúng không trùng nhau:

- bound schema (1.753 ký tự): chỉ khai TÊN KHOÁ và KIỂU — `{"type":"object", "description":"a JSON
  object, per the schema shown in the system prompt"}`
- prompt schema (3.963 ký tự): hình dạng LỒNG NHAU và exemplar — `lo_coverage_targets`,
  `pilot_data_plan.anticipated_difficulties[].detected_by`, ...

Bound schema cố ý là tuyến đầu YẾU HƠN `validate`, không bao giờ là nguồn chân lý thứ hai. Bỏ phần
trong prompt thì model không còn biết bên trong mỗi khoá có gì.

**Bỏ ILO khỏi user turn? KHÔNG.** Đo trên 3 objective: injection tốn **523 ký tự (~174 token)**. Bỏ
nó đi thì lần đọc trở thành BẮT BUỘC — **+1 call cho mọi work set**. Giữ lại thì chỉ tốn thêm call
khi model phớt lờ, đo được 41%. Kỳ vọng 0,41 call thừa so với 1,0 — giữ rẻ hơn.

Và hai thứ này đã bị khoá vào nhau: `_already_in_assignment` trả con trỏ *"bạn đã có trong mục X"*.
Bỏ injection mà không bỏ con trỏ thì con trỏ nói dối; bỏ cả hai thì mất luôn khoản tiết kiệm.

472 test xanh.

## Check-repair vào trong tool loop (2026-09-02)

Luồng mới, đúng như đề xuất: stage submit xong → structural fix chạy trước (tất định, miễn phí) →
violation còn lại quay vào **user turn của chính loop đó** → agent sửa và submit lại → tối đa
`REPAIR_TURNS = 3` vòng.

**Phần thưởng lớn hơn auditability**: 9 loại `REPORT_ONLY` tồn tại vì một fix TẤT ĐỊNH cho chúng sẽ
là harness bịa nội dung giảng dạy. Agent viết nội dung thì không phải bịa — đó là agent làm việc của
nó, có phản hồi. Giờ agent thấy chúng.

**Ranh giới giữ nguyên** (đã chốt):
- `repairs.STRUCTURAL` = `{bloom, C4, P5, orphan_content, evidence_alignment}` — tra bảng, sắp xếp
  lại id đã có. Chạy trước, không hiện cho agent: tiêu một turn cho việc một phép tra làm hoàn hảo
  chính là lãng phí đang cắt ở mọi chỗ khác.
- Reconciliation liên-family vẫn ngoài loop: khi biết một C4, loop của stage đó ĐÃ đóng, và tái nhập
  giữa pipeline là rủi ro treo đã đo được.
- Developer loop nhận `repair_turns=0`: check là cấp family, Developer làm một work set sẽ bị cho
  xem violation của những artifact nó không được giao.

**Cả hai arm đều có** — thiếu một bên là thêm biến thứ hai vào trục. Dùng chung
`ToolLoop.own_violations()`.

## Attribution: ngoài tool loop thì thuộc orchestrator

Check, structural fix, reconcile, audit giờ ghi cho `WorkflowOrchestrator`, không ghi cho agent.
Attribution trả lời **AI ĐÃ LÀM**, mà những việc này chạy sau khi loop trả về — agent không chọn,
không thấy, không thể làm khác. Ghi cho agent là thổi phồng những gì trace nói nó đã làm.

Không mất thông tin: family bị soi vẫn là một field trên bản ghi, và `OWNER_BY_VIOLATION` map mọi
loại về chủ của nó. Đảo lại một quyết định cũ ("credit the family whose output is being checked") —
quyết định đó trả lời câu "soi cái gì", không phải "ai làm".

**Lỗi bắt được**: submit trong vòng repair log thành `design_assessment` lặp 4 lần — judge đọc danh
sách phẳng và chấm lặp là redundancy, đúng chỉ số codebase này đã chiến đấu. Giờ đặt tên theo vòng:
`design_assessment_fix1/2/3`. Không phải lách metric — chúng là những act KHÁC nhau, và tên cũ mới
là tên sai.

**Chi phí**: fixture multi 18→28 call (repair_turns=6). Mỗi vòng mang cả context stage. Trên run
thật tỉ lệ sẽ thấp hơn (model thật sửa được rồi dừng), nhưng phải theo dõi `repair_turns` trong
`autonomy` ở lần chạy tới.

472 test xanh.

## `_WORKFLOW_OVERVIEW` trôi khỏi bảng STEPS (2026-09-02)

System prompt vẫn nói `6. rubrics / 7. implementation` — tức **mọi agent trong mọi run đều được bảo
là có bước thứ bảy không tồn tại**, hàng tháng sau khi stage rubrics bị xoá. Nó là danh sách viết
tay nằm cạnh `STEPS`, và `STEPS` mới là nguồn thật.

Sửa không phải xoá dòng đó mà là **sinh danh sách từ `STEPS`** — cùng bài học với per-block budget
của planner (nội suy từ `max_units` thay vì gõ tay). Một danh sách đặt cạnh cái bảng định nghĩa nó
là một danh sách sẽ bất đồng với nó. Có test chốt: mọi step phải xuất hiện đúng số thứ tự, không
được có số thứ tự thừa, và hai arm phải nhận cùng một chuỗi.

Dọn theo, cũng chết từ lúc bỏ stage rubrics: `_STATE_FAMILIES["rubrics"]` và `RULES_RUBRICS` (bản
whole-family; consumer duy nhất là `rules_for("rubrics")`). Bản Developer thật sự dùng là
`RULES_RUBRICS_ITEM`.

473 test xanh. Golden prompts regenerate.

## Tải Transcript (2026-09-02)

`GET /api/runs/{id}/transcript/export` → Markdown; `?index=N` lấy một context.
Nút "Export all transcripts" ở thanh trên tab Context, và "Export this transcript" trong mỗi dòng
đã mở.

**Markdown chứ không JSON**: `/contexts` đã phục vụ JSON cho tooling rồi; đây là artifact **con
người đọc từ đầu tới cuối**. Một hội thoại 27 message dưới dạng mảng JSON thì không phải thứ đó.
Giữ nguyên mọi phần — system turn, từng message theo thứ tự, tool schema — vì mục đích tải
transcript là đọc **đúng** những gì model được xem; tóm tắt là phá mục đích.

**INDEX chứ không label**: một stage bị regen phát mỗi lần thử một context, chúng trùng label và
chỉ phân biệt được bằng vị trí + `attempt`.

476 test xanh (380 package + 96 server). Ghi chú: `test_sse.py::test_a_finished_run_replays_from_disk_and_closes`
đỏ một lần rồi xanh 3 lần liên tiếp — flake sẵn có về timing, không liên quan thay đổi này.

## Bỏ hẳn generative repair — một agent, một system prompt (2026-09-03)

Phát hiện từ tab Context: luồng repair hiện ra như **một block mới của cùng một agent**, với
system prompt hoàn toàn khác và không có tool nào. Nó **phản ánh đúng thực tế**: các repair sinh
nội dung (`_llm_repair_items`, `_llm_item_options`, `_llm_formative_methods`,
`_llm_pilot_data_plan`) tự soạn một prompt hai message, persona-free, rồi gọi model **nhân danh
agent sở hữu violation**.

Đây không phải lỗi hiển thị. **Ranh giới context CHÍNH LÀ trục `agent_mode`.** Một đường repair tự
mở conversation riêng đặt thêm một ranh giới nữa **bên trong** treatment — và chỉ với những family
có generative repair, theo tỉ lệ thuận với việc run đó tệ đến đâu. Tức lượng "nhiễu trục" mà mỗi
run nhận được phụ thuộc vào chính chất lượng output đang đo.

**Sau thay đổi**: mọi routine trong `repairs.py` đều là *structural* — sắp xếp lại thứ thiết kế đã
có (Bloom verb tra từ taxonomy, C4/P5, evidence rule, C2/P3 re-point item trỏ hụt, item trắc
nghiệm mất đáp án → `short_answer`). Việc cần **VIẾT** quay về đúng agent sở hữu, dưới dạng một
user turn trong tool loop của chính nó (`ToolLoop._own_violations` → `_repair_request`, chặn bởi
`REPAIR_TURNS`): yêu cầu, câu trả lời của model, và artifact nằm ba turn liên tiếp trong **một**
transcript.

Xoá theo: `RepairContext.call_llm`, `_ObservedLLM`, `_CarriedContextLLM`, `repair_plan_coverage`,
`repair_assessment_items`, `repair_formative_methods`, `repair_pilot_data_plan`, `_CATEGORY_TAG`,
và `repair_unfilled` (không còn đường nào phát; enum giữ lại để đọc được trajectory cũ).

`REPORT_ONLY` đổi nghĩa: nó chỉ nói **harness** không được viết. Các type đó **vẫn được đưa cho
agent** như mọi violation khác — chúng đúng là loại chỉ người viết mới trả lời được.

Guard: `tests/test_one_agent_one_system_prompt.py` — (1) mỗi agent chỉ một system prompt trên toàn
bộ context nó phát, (2) không context nào được phát mà không có tool bound (một context không tool
= một lời gọi model ngoài mọi tool loop). Đã kiểm chứng guard **bắt đúng hình dạng cũ**, không chỉ
suy đoán. Cộng thêm assertion trên field của `RepairContext` + source của `repairs.py` trong
`test_no_invented_content.py`.

379 test package + 96 server xanh, `run_benchmark.py --check` sạch.

**Hệ quả cần theo dõi ở run tới**: `repair_turns` tăng (việc từng do net âm thầm làm nay tốn turn
của agent), và residual có thể tăng nữa vì `REPORT_ONLY` giờ mới thực sự được đưa ra hỏi.

## Một submit / một artifact + Memory + Designer re-plan (2026-09-03)

### A. Tách `submit` theo artifact

`submit_assessment_plan`, `submit_assessment_dev_plan`, và 6 tool riêng cho `implementation`. Đây là
bản tổng quát hoá của `submit_parts` mà `analysis` đang dùng — lý do vẫn là trần completion 8192, và
giờ một artifact bị reject chỉ tốn artifact đó chứ không phải cả stage.

Ba thứ **bắt buộc** đi kèm, thiếu là tách xong mất việc:

- **Commit phải MERGE** (`_merge_section` / `_merge_document`). `add_node` thay thế data, nên
  `submit_dev_plan` sau `submit_assessment_plan` sẽ để lại section chỉ còn dev plan.
- **Validator chỉ xét cái đã tới, nhưng vẫn chặn RỖNG** (`_nothing_arrived`). Không chặn thì
  `validate({})` sạch, và `unwrap_section` — vốn coi "validator chấp nhận" là "đã unwrap rồi" — sẽ
  commit nguyên vỏ `{"artifact": …}`, đúng lỗi 2B mà nó sinh ra để chữa.
- **Hoàn thành = `parts_of(step)` hỏi STATE.** Không thì `outcomes` return ngay sau
  `submit_course_goal` và không bao giờ có objectives.

Artifact OPTIONAL được hỏi **đúng một lần** mỗi stage. `media_selections` (P8 + rubric item),
`non_instructional_strategies`, `dev_plan` trước đây đi ké cùng payload; giờ loop return khi đủ
required nên chúng sẽ không bao giờ được gửi. Chặn ở một vì model yếu trả lời "không còn gì" lặp lại
tới hết `MAX_TURNS`.

Nhãn commit mang tên artifact; submit gửi lại thứ đã commit ghi `duplicate_submit` chứ không phải
design step thứ hai (judge đọc tên tool phẳng, sáu dòng giống nhau = redundancy).

**Lỗi tìm được**: `dev_plan` model submit đang **bị vứt** — `commit_assessment` strip,
`commit_activities` bỏ qua, `_dispatch_payload` đọc lại từ graph. Đo trên fixture: assessment và
activities **luôn** `source=fallback`. Mất đúng thứ ablation quan tâm: quyết định nhóm của agent,
`instrument_hint`/`block_theme` giữ hai Developer khỏi viết trùng, và `expected_activities`. Giờ giữ
trên plan section (graph dump thấy), strip ở aggregation.

Cũng tìm được: `submit_fields=(... for ...)` là **generator** — ai đọc trước tiêu thụ hết. Test pass
một mình, fail trong suite.

### B. Memory (`core/memory.py`)

Ba thứ, một chỗ: `transcripts` (mỗi agent), substrate (`graph` XOR `store`), `plans` (theo VÒNG).

Hai trong ba gần như không tồn tại. Transcript chỉ publish vào `on_event` — chỉ webapp truyền
consumer, nên CLI/benchmark chạy cả ladder mà context không còn ở đâu. Plan sống đúng một lời gọi
`_run_fanout` rồi bị vứt.

`state` **vẫn là substrate** trong `run.py`: nửa module đó dò `hasattr(state, "element_nodes")` để
phân nhánh arm; một wrapper không trả lời được câu đó đẩy mọi graph run xuống nhánh prose. Đã thử
`state = memory` rồi rút lại vì đúng lý do này.

### C. Gap quay về Designer, Designer lập PLAN

`core/agentic/replan.py`. Developer commit **từng set** ngay khi xong (`commit_sets` per set, ids
không đụng nhau nhờ đưa remapper các id state đang giữ qua `taken`), nên output của family nhìn thấy
được **trong khi loop của Designer vẫn còn đó để nối tiếp**.

Orchestrator check → gap nào một work set mới đóng được (`C2 P3 plan_coverage` cho assessment,
`C3 C4` cho activities; `content` không có vì check của nó structural hoặc report-only) đưa vào
**message list của chính Designer**. Câu trả lời là `dev_plan`, không phải artifact — Designer lập
kế hoạch, Developer viết.

Ba thứ chặn:
- **Ground truth là GAP, không phải family.** `gap_targets` dựng coverage targets từ metadata của
  violation. Normalize theo family sẽ tái sinh mọi set đã có.
- **Set id gắn vòng** (`AS-01R1`). Không gắn thì `committed_set_ids` thấy id vòng 0 và bỏ qua mọi set
  mới — vòng chạy mà không ra gì.
- **`REPLAN_ROUNDS = 1`.** Gap sống sót qua một lần re-plan + một Developer call là gap model không
  đóng được; hỏi tiếp là cách một stage thành treo.

### D. ID an toàn theo cấu trúc, không theo thứ tự commit

Developer tự commit nên **ai commit trước quyết định tên** — quy tắc cũ là "giữ id của model, chỉ
đổi nếu ai đó đã lấy". Trước đây cả family deposit một cục nên người thắng là thứ tự plan, tất định;
với per-set commit nó thành thứ tự arrival. Hôm nay vẫn giống nhau vì fan-out tuần tự, nhưng khác
ngay khi có concurrency hoặc retry một set.

**Model KHÔNG khai id nữa** — trường id đã bỏ khỏi `SCHEMA_ASSESSMENT_ITEMS`/`SCHEMA_ACTIVITIES`/
`SCHEMA_MATERIALS`. Hỏi model một id rồi ghi đè nó mỗi lần là tốn thuần: không mua được gì, mà mọi
id sai (`AT-{`, trùng, chép từ ví dụ schema) đều là một lỗi thật. Bỏ trường cũng làm artifact ngắn
lại dưới trần completion.

**Hệ quả: tham chiếu CÙNG family thành VỊ TRÍ.** `prerequisite_activities` gọi tên activity trong
chính block đang submit theo vị trí 1-based (`[1]` = cái đầu tiên nó viết), `_resolve_positions`
phân giải sang id đã gán và **drop** cái không phân giải được (id treo trong graph thì vô hình,
tham chiếu bị drop thì hiện ra ở số coverage). Trường này vốn đã hỏng sẵn vì cùng một nguyên nhân:
nó chưa bao giờ được khai là reference field, nên mọi tham chiếu vào graph đều gọi tên id đã bị đánh
số lại — **đo được 0/3 phân giải** trên fixture, trong khi `_establish` đọc đúng nó để dựng cạnh
`precedes`. `SetOutput.ref_fields` thay bằng `self_ref_fields` (các mục cũ đều là CROSS-family —
objective, assessment, module — vốn không cần và chưa bao giờ được remap).

**Mỗi id GHÉP ordinal của set với ordinal của artifact**: `AT-0203` = artifact thứ 3 của work set
thứ 2 (`WorkSet.ordinal`, `_composite_id`). Nửa của set được cố định lúc plan được đánh số — trước
khi Developer nào chạy — và mỗi set đếm artifact của nó từ 1 nên **đánh số liền, không có khoảng
trống**. (Cấp dải riêng cho mỗi set thì có: set 1 dừng ở `AT-10`, set 2 bắt đầu `AT-21`, và cái
khoảng đó là biên khối lộ ra tận deliverable.) Vòng replan stride ordinal
(`ROUND_ORDINAL_STRIDE = 50` → `AT-5101`); quét qua `taken` là backstop cho Developer dùng trùng id
trong chính set của nó. `commit_sets` chạy trong một
`AlignmentGraph.transaction()` (RLock re-entrant): đọc id đang có rồi ghi node dựa trên cái vừa đọc
chỉ đúng nếu không có gì chen vào giữa.

**Id vẫn NGẮN** (`AT-0203`, không phải `AT-01-AS-02`). Mọi cạnh cross-artifact ở hệ này đều là
**tham chiếu id do model viết**: item gọi tên objective, activity gọi tên item nó chuẩn bị cho,
implementation plan gọi tên activity nó xếp lịch. Id dài/khó đoán làm tăng tỉ lệ hỏng của từng tham
chiếu đó, đúng trên nhóm model nhỏ mà nghiên cứu này nói về — tôi đã thử namespacing đầy đủ và nó
**làm chết P10/P11 ngay**.

Thứ làm cho việc đánh số lại an toàn là: **family nào tham chiếu family khác đều ĐỌC nó trước**
(activity Developer có ASSESSMENT trong `developer_reads`; ImplementationPlanner đọc
ACTIVITY/MATERIAL và docket của nó liệt kê gap P10/P11 theo id). Nên tham chiếu được viết dựa trên
id đã commit, không phải dựa trên ví dụ trong schema. Ref trong-set theo được nhờ `ref_fields`; ref
ghi cứng thì KHÔNG — nên fixture phải phân giải id từ state (`conftest._named_from_prompt`).

Guard: `tests/test_id_safety.py` — không đụng id, không phụ thuộc thứ tự arrival, per-set bằng
batched, tràn dải không ăn dải kế, id đủ ngắn, ref trong-set theo được việc đánh số lại.

Kéo theo: `step_done` giờ tôn trọng `AgenticStep.done` — pool của family đầy dần khi các set ANH EM
commit, nên guard mặc định báo set 2 xong trước khi Developer của nó kịp nói câu nào.

Đo trên fixture (multi): 31 → 37 call, 4 work set mới, `plan_coverage` residual 0.

513 test xanh, `run_benchmark.py --check` sạch. Golden prompts đã regenerate.

## Context stream realtime (2026-09-03)

Mỗi loop republish context của nó **sau mỗi lượt**, nên tab Context điền dần và thanh đo chạy trong
khi agent còn đang làm — thay vì một dòng chỉ hiện ra khi agent đó xong.

Ba thứ giữ cho nó không tốn:

- **Bỏ hẳn khi không ai xem** (`TrajectoryLogger.is_observed`). Emit là no-op khi không có consumer,
  nhưng *serialize transcript để dựng payload* thì không — benchmark không được trả giá đó. Đo: 0.17s
  cả hai chiều.
- **UPSERT theo `id` của context** ở cả `RunState.add_context` và `Memory.remember_context`. Không
  thì `result["contexts"]` thành một chồng tiền tố của chính nó.

  Id đó là **agent run id** (`core.memory.new_agent_run_id`), cấp phát ở nơi **hội thoại bắt đầu** và
  mang trên loop, nên nó đi trong mọi snapshot và cả server lẫn browser đều không cần biết danh tính
  context làm bằng gì. Trước đó danh tính này có **ba định nghĩa ở hai ngôn ngữ**, lệch giữa hai cái
  bất kỳ là âm thầm gộp những context mà cái còn lại giữ riêng.

  **KHÔNG suy ra từ nội dung.** Bản đầu tôi hash `(agent, phase, label, attempt)` — và vòng replan,
  vốn nối tiếp chính message list của Designer dưới một step name mới, hash ra id khác. Tab hiện
  **một hội thoại thành hai dòng**, dòng sau chứa dòng trước. Cùng system prompt nên
  `test_one_agent_one_system_prompt` cho qua: vết nứt chỉ chuyển từ prompt sang label. Guard cho nửa
  đó là `test_one_conversation_is_one_context`.

  Loop nào NỐI TIẾP message list của loop khác thì thừa kế **mọi thứ mô tả HỘI THOẠI chứ không phải
  công việc**: `agent_run_id`, `label`, `compacted`, và `attempt` (chỗ duy nhất là
  `run._replan_rounds`). `attempt` đếm **regen** — stage trả về rỗng thì chạy lại từ context mới;
  đánh số theo vòng replan thì một Designer hoàn toàn bình thường bị tính là chạy hai lần. Nó là
  **dữ liệu, không phải nhãn**: badge "retry #N" đã bỏ khỏi tab, vì ai nhìn thấy nó cũng phải tự
  đoán xem có gì hỏng không, trong khi các dòng vốn đã theo thứ tự publish nên các lần thử của
  cùng một stage đọc từ trên xuống là ra. Regen, fan-out work set, và design
  loop của mỗi arm đều bắt đầu message list mới nên tự có id riêng.

  Export transcript giờ địa chỉ hoá theo id (`?context=`) thay vì theo vị trí — vị trí chỉ ổn định
  khi run đã xong, mà context giờ republish sau mỗi lượt.
- **Frame SSE chỉ mang ROWS, không mang transcript lẫn tool schema** (`contexts_light()`) — đúng phần
  list view cần. Transcript + schema nạp **theo từng dòng** từ `/contexts?context=<id>` khi người đọc
  MỞ dòng đó, và nạp lại khi dòng đó dài ra: dòng chỉ nằm trong danh sách gần như không tốn gì, còn
  dòng đang nhìn thì live. (Hồi quy đã sửa: khi live rows mới vào, mục "Tool schemas" hiện rỗng vì nó
  đọc từ row — thứ theo thiết kế không mang schema.)

**Auto-compact hiển thị, không bị đếm.** `trim_history` trả về chính các message nó bỏ (không phải
một con số), loop tích luỹ vào `compacted`, và `compacted_transcript` republish **toàn bộ hội thoại
theo đúng thứ tự** với các lượt đó gắn cờ `compacted: true` — mờ đi + badge trong tab, và **cố ý
không nằm trong số token**, vốn đo cái đang thực sự gửi đi. Dải bị bỏ là **liên tiếp và bắt đầu ngay
sau system message**, nên thứ tự phục dựng được bằng `[system] + mọi thứ đã bỏ + phần còn lại`, không
cần sổ sách vị trí.

Trước đó transcript đã trim chỉ trả lời "agent này được cho xem gì" **cho lời gọi cuối cùng**; mọi
thứ các lời gọi trước thấy đều biến mất, chỉ còn `history_dropped` — một con số nói mất bao nhiêu và
không nói gì về cái gì.

`add_context` **cố ý không `_notify()`**: đánh thức stream mỗi lượt làm nó rút cạn nhanh hơn hẳn
flusher events.jsonl, biến một race hiếm thành race chắc chắn. Frame đi ké lượt đánh thức của event
kế tiếp — `llm_started`/`llm_finished` kẹp mọi lời gọi model nên luôn có một cái ngay sau.

**Và race đó sửa tận gốc**: `_flush_state` giờ chạy TRƯỚC `state.finish()`. `finish` chính là thứ
đóng live stream, nên reader quay về đúng khoảnh khắc đó — mọi thứ chưa flush sẽ không có trên đĩa
cho lần replay mà restart (hoặc reader thứ hai) rơi vào. Đây là fragility thật của app, không phải
chỉ của test: `test_a_finished_run_replays_from_disk_and_closes` giờ xanh 4/4 thay vì đỏ ngẫu nhiên.

518 test xanh (ba lần liên tiếp), webapp 44 test, `tsc -b` + `vite build` sạch.

## Ba lỗi quanh compaction và tool menu (2026-09-03)

**1. Hợp đồng artifact chuyển ra sau tool `stage_brief`.** Trước đó schema nằm trong stage turn — mà
stage turn là thứ ĐẦU TIÊN bị nén. Cách chữa đầu tiên của tôi là giữ `messages[:2]`; sai, vì nó ghim
một khối lớn dần theo schema ngay đầu cái cửa sổ mà nó phải dọn chỗ. Giờ:

- **task** sống sót dưới dạng nội dung trong summary của compaction;
- **schema + rules** không nằm trong turn nữa, gọi `stage_brief` lấy lại bất cứ lúc nào;
- **tool menu** thừa so với binding — schema tool đi kèm MỌI request dưới native tool calling — nên
  mất phần prose của nó không tốn gì.

Nên `trim_history` chỉ bảo vệ system turn + compaction note.

**Và nó sửa một bất đối xứng do harness tạo ra**: `multi` được cho schema sẵn trong prompt, còn
`single` phải tốn một call gọi `stage_brief`. Đó mới đúng là confound. Giờ `multi` trả đúng cái
`single` vẫn trả (đo trên fixture: 31 → 45 call).

Ngoại lệ: **fan-out work set** giữ hợp đồng inline (`contract_inline`). Loop của nó tối đa
`DEVELOPER_MAX_TURNS` trên một assignment, không bao giờ chạm cửa sổ — fetch không mua được gì mà tốn
một call mỗi set, cộng chín dòng `tool_stage_brief` giống hệt dưới cùng một identity, thứ judge chấm
là redundancy.

**2. Menu không khớp binding.** `tool_menu` viết tay và vẫn công bố một `submit` duy nhất, hàng tháng
sau khi submit đã tách theo artifact — nên **mọi stage của mọi arm đều bảo agent gọi một tool không
tồn tại**, và `_submit_alias` âm thầm cứu. Giờ menu **render từ chính `tool_specs`** nên không thể
lệch; `test_the_tool_menu_cannot_disagree_with_the_binding` so từng dòng với binding.

**3. Context công bố tool set của lần bind CUỐI.** Binding thu hẹp dần: vòng replan chỉ bind
`submit_dev_plan`, còn `react_specs` bỏ submit của stage đã xong. Nên hàng gộp khẳng định Designer
chưa từng có `submit_assessment_plan` — thứ nó vừa dùng để viết plan. Giờ `_specs` **tích luỹ**
(`_merge_specs`), dedupe theo tên, thứ tự gặp trước.

**Compact có ghi chú.** Trước đó model **mất turn trong im lặng**: một khoảng trống nó không thấy và
không có lý do gì để đọc lại thứ đã mất. Giờ có một note trong hội thoại — được bảo vệ khỏi lần trim
sau, và **ghi đè chứ không nhân đôi** — nói bao nhiêu turn đã đi và rằng phát hiện của chúng đọc lại
được từ design state.

**Có tóm tắt bằng model** (`core/agentic/compaction.py`), rolling: mỗi lần nén gộp summary trước đó
với phần vừa bị bỏ, nên note luôn là một khối cỡ cố định và input mỗi call luôn bị chặn.

Tôi từng phản đối điều này là confound. **Phản đối đó lẫn lộn hai thứ.** Chi phí lệch theo arm vì
*cơ chế* chính là hiệu ứng cần đo — giống hệt việc `single` gọi model nhiều hơn, thứ ta vẫn báo cáo
chứ không cân bằng đi. Chi phí lệch vì *lựa chọn harness* mới là confound. Trigger, prompt, budget,
fallback là **một implementation cả hai arm gọi y hệt**; khác nhau chỉ ở tần suất cửa sổ thật sự đầy
— đúng cơ chế mà trục decomposition nói về. `autonomy.compactions` / `compaction_summaries` báo giá
theo từng stage để nêu được con số thay vì ngụ ý.

Call này là của **ORCHESTRATOR**: agent không chọn nén và không được xem cuộc hội thoại đó, nên nó
không publish thành context của agent — nhưng `AgenticLLM` vẫn đếm token của nó. Hỏng thì luôn an
toàn: câu trả lời không dùng được thì giữ summary cũ, note đếm vẫn đứng.

**Chưa đo được bất đối xứng trên fixture**: ở cửa sổ mặc định cả hai arm đều 0 lần nén (transcript
của fake quá ngắn), ở cửa sổ 3072 thì `multi` nén nhiều hơn vì nó có ~15 loop nhỏ chứ không phải vì
nó chạm trần. Con số thật phải đến từ ladder ở cửa sổ 16384.

538 test xanh. Golden prompts đã regenerate.

## Violation: tự giải thích, được ghi nhớ, đếm đúng (2026-09-04)

Khởi đầu từ một câu hỏi về app: violation "Bloom level consistent" hiện ra mà không có dấu hiệu gì
về **tại sao**; muốn biết phải mở trajectory đọc từng check event. Kéo ra thì lộ năm vấn đề.

**1. Violation không tự giải thích.** Hai loại `bloom_mismatch_*` dựng ở `checks.py:673-690`
**không truyền `repair_hint`** — mà `_repair_request` chỉ in dòng `Fix:` khi có hint, và hai loại đó
cũng không có repairer. Nên agent nhận một câu trần trụi, không chỉ dẫn. Message thì in **số nguyên
trần** ("elicits more than level 1") — con số suy từ *loại item*, thứ hoàn toàn nói ra được. Sáu
message Bloom viết lại: gọi tên level, nói loại item nào chặn trần, nêu trường phải sửa.

**Bề mặt prompt lớn nhất chưa được canh**: `_repair_request` in message + hint **nguyên văn** vào
user turn cho cả hai arm, mà `golden_prompts.json` không ghim message của check. Đã thêm mục
`checks.messages.*` (23 loại, dựng trên `tests/fixtures/broken_design.py`) — **ghim TRƯỚC khi sửa**.
Nó bắt lỗi ngay lần chạy đầu: hint liệt kê verb từ một `set`, thứ tự đổi giữa hai process.

**2. Violation không được ghi nhớ ở đâu.** `_serialize` vứt 4/8 trường. Không có
`result["violations"]`. Thân violation chỉ tới `metadata.audit` — mà arm prose bỏ qua audit nên mất
sạch. Giờ `core/memory.py` có thứ thứ tư: `Finding`, theo suốt vòng đời.

**3. Đếm lặp.** Trên trajectory user gửi: 10 violation phân biệt, cộng `by_type` qua 20 vòng ra 40 —
mỗi cái đếm 4 lần, và `_review_findings` cộng đúng kiểu đó (báo 28 cho tập 7). Giờ đếm theo khoá.

**4. Reconcile làm lại y hệt.** Điều kiện dừng là `if not pending` **toàn cục trên 6 family** — một
family sạch từ vòng 1 vẫn bị check lại vì family khác còn việc. Giờ budget **theo từng family**, cộng
luật hội tụ: check là hàm thuần của state và không gì khác ghi state giữa hai lần collect, nên *không
phát repair event nào* là **bằng chứng** lần collect sau giống hệt — dừng trước khi trả tiền cho nó.
Đo: **12 → 6 vòng**.

Kèm ba khiếm khuyết kế toán: `residual +=` nằm ngoài vòng family (step có `also_repairs` chỉ đếm
family cuối, và `found` không reset nên rò từ family trước); residual luôn là lần check **trước**
repair cuối; `or residual` khiến "reconcile không thấy gì" rơi về danh sách cũ. Đã **xoá hẳn**
accumulator per-stage — `_reconcile` duyệt cả 6 family sau stage cuối nên lần nhìn cuối của nó *chính
là* residual.

**5. "Còn violation" gộp bốn nguyên nhân.** `loop.py` còn violation mà hết `REPAIR_TURNS` thì ghi
"COMMITTED" rồi đi, **không một event nào** — trong khi nhánh ngay dưới lại `_give_up`. Giờ
`Finding.open_reason` phân biệt `converged` / `budget` / `unowned` / `unseen`, với **precedence
`unowned > budget > converged`**: reconcile hội tụ trên một loại nó không được phép chạm là đúng một
cách tầm thường, và để nó ghi đè `budget` là biến "ta cắt ngắn" thành "model không làm được". Đo trên
fixture: **4 budget, 4 converged**.

**Nếu residual cao vì budget chật, đó là tham số harness, không phải phát hiện về năng lực model.**
Báo cáo gộp trong paper là claim sai.

**Webapp**: tab Violations (nhóm theo kết cục, mỗi dòng có message + hint + ai sở hữu + vòng
đầu/cuối + lý do còn mở), `node_violations` đánh dấu **mọi loại node** trên graph — trước đó
`objective_alignment` chỉ duyệt objective nên TLA mồ côi, material mồ côi, item thiếu đáp án không có
tín hiệu nào — flag Bloom tách làm hai kèm message nguyên văn, và `lib/violations.ts` là **bảng nhãn
đầu tiên** trong repo (trước đó app hiện snake_case thô).

**Node detail: mục "Failed checks" cho MỌI loại node.** Viền cảnh báo và mục này đọc cùng một
`node_violations` nên không thể lệch nhau. Danh sách lấy từ GRAPH (live, chỉ có loại), câu chữ lấy từ
SỔ khi nó đã chốt — nên trong lúc chạy node hiện tên check hỏng, và cuối run có thêm message + repair
hint của chính check đó. Với objective thì bỏ bốn loại `AlignmentFlags` đã vẽ, để không nói cùng một
điều hai lần bằng hai hình dạng; mọi thứ CÒN LẠI hỏng trên nó (`measurability`, `bloom`,
`activity_engagement`, C1/P1/P2) trước đây **không có chỗ nào hiện ra cả**.

553 test package + 48 webapp xanh, `run_benchmark.py --check` sạch. Golden prompts đã regenerate.

## Rủi ro còn treo

- **Chi phí — đây là vấn đề lớn nhất, và nó KHÔNG do lỗi transport.** Run 2 (đường đã sửa phần lớn): multi 36–53 call / 183k–211k token; single 37–65 call / **364k–744k** token. `react-isd` cùng scenario: 5 call / 13,6k token. Tức hệ đề xuất tốn **15–55×** baseline mạnh nhất, và ~9–33× so với arm scripted cũ (22,6k). Ngưỡng 3× của cổng Phase 3 **đã vỡ trên bằng chứng hiện có**.
  Arm `single` đắt gấp ~3,5× arm `multi` — đúng cơ chế context đang đo, nhưng nó ĐẢO NGƯỢC bức tranh trước pivot (single từng ít call hơn). Phải quyết trước khi chạy ladder: chấp nhận, hay siết `MAX_TURNS`/`HISTORY_CHAR_BUDGET`, hay thu thiết kế về B1 (2 size).
- **`trajectory_score` đi ngược như dự đoán**: `redundancy_avoidance` 18–21 ở các arm so với 25 của react-isd. Vòng lặp tool thật sinh repeat thật. Cần một câu trong §Results, không để reviewer tự suy.
- **react-isd vẫn dẫn** (87,57 vs 79,5–81,1 ở n=1) với 5 call / 14,7k token. Độc lập với pivot; xem plan §7.
