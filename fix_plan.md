# Fix Plan: Đồng Bộ `alignmentgraph-isd/` Và `docs/`

## Mục Tiêu

Tài liệu trong `docs/` đang mô tả AlignmentGraph-ISD như một harness khá đầy đủ: có CLI benchmark adapter, dynamic task graph, agentic RAG, schema validation chi tiết, pedagogical verifier, targeted repair, four-layer memory và prototype UI. Code trong `alignmentgraph-isd/` đã có lõi harness thật sự, nhưng một số phần trong tài liệu hiện vẫn là claim hoặc chưa được implement đầy đủ.

Kế hoạch này nhằm đưa code và docs về cùng một sự thật:

- Nếu tính năng cần thiết cho luận văn hoặc benchmark: implement trong code.
- Nếu tính năng chưa nằm trong phạm vi hiện tại: hạ claim trong docs thành “current implementation” hoặc “planned extension”.
- Ưu tiên loại bỏ các điểm có nguy cơ làm evaluation sai: CLI/adapter, schema validation, verifier, hard-code domain và RAG claim.

## Nguyên Tắc Sửa

- Giữ `AlignmentGraph-ISD` là core library/harness trước; UI/prototype chỉ mô tả nếu có artifact thực.
- Không viết docs như đã có tính năng nếu code chưa có.
- Các thay đổi P0 phải có verification tối thiểu bằng unit test hoặc smoke run.
- Các thay đổi liên quan benchmark phải tạo output gồm `addie_output`, `trajectory`, `metadata` ổn định.
- Hard-code domain VR/mobile/language chỉ được giữ nếu được cấu hình theo scenario; mặc định phải domain-neutral hoặc IT/Software Engineering.

## P0 - Cần Sửa Ngay

### P0.1 Thêm Public Entry Point Rõ Ràng, Không Cần Benchmark Adapter

**Trạng thái:** Done. Đã export `HarnessRunConfig` và thêm public helper `run_design_brief(DesignBrief, HarnessRunConfig)`. Đã thêm CLI smoke `alignmentgraph-isd run` nhận `DesignBrief` JSON, không map raw benchmark scenario. CLI/public helper fail rõ nếu thiếu `llm_factory`.

**Vấn đề**

Docs mô tả lệnh CLI:

```bash
alignmentgraph-isd run \
  --input scenario.json \
  --output result.json \
  --trajectory trajectory.json
```

Nhưng hướng tích hợp benchmark thực tế là benchmark sẽ gọi code trực tiếp, không cần adapter map scenario JSON vào `DesignBrief` ở trong package này. Vì vậy không nên thiết kế P0.1 như một benchmark adapter bắt buộc. Thứ cần có là public API ổn định cho benchmark import/call, còn CLI chỉ là tiện ích smoke/manual nếu vẫn muốn giữ command trong docs.

**File liên quan**

- `alignmentgraph-isd/pyproject.toml`
- `alignmentgraph-isd/src/alignmentgraph_isd/orchestrator.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/schema.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/__init__.py`
- Có thể tạo mới: `alignmentgraph-isd/src/alignmentgraph_isd/cli.py`

**Hướng sửa**

1. Chuẩn hoá public API cho benchmark gọi trực tiếp:

- Export rõ `MetaAgent`, `HarnessRunConfig`, `MemoryConfig`, `DesignBrief` trong `alignmentgraph_isd.__init__`.
- Bảo đảm `MetaAgent.run(DesignBrief)` trả về object ổn định gồm `addie_output`, `trajectory`, `metadata`.
- Document một snippet Python ngắn trong docs thay cho việc coi CLI là integration path chính.

2. Không implement adapter map scenario vào `DesignBrief` trong harness:

- Benchmark layer bên ngoài chịu trách nhiệm map scenario schema của benchmark vào `DesignBrief`.
- Harness chỉ định nghĩa input contract (`DesignBrief`) và output contract.
- Nếu benchmark cần nhiều input shape khác nhau, xử lý ở benchmark repo, không đẩy vào core harness.

3. Nếu vẫn giữ CLI trong docs, chỉ làm CLI dạng developer smoke/manual:

- CLI nhận JSON đã là `DesignBrief` shape, không phải raw benchmark scenario.
- `alignmentgraph-isd run --input design_brief.json --output result.json --trajectory trajectory.json`
- `--ablation full|no_ext_corpus|no_verifier|no_repair|single_agent|linear_addie_only`
- `--training-program-id`, `--session-id` nếu dùng app/session path

4. Output `result.json` nên gồm:

```json
{
  "addie_output": {},
  "trajectory": {},
  "metadata": {}
}
```

**Acceptance Criteria**

- Benchmark có thể import package và gọi `MetaAgent.run(DesignBrief)` trực tiếp.
- Không có `benchmark_adapter.py` map scenario nếu không thật sự cần.
- Nếu có CLI, docs ghi rõ CLI nhận `DesignBrief` JSON, không phải raw scenario JSON.
- Nếu không có `llm_factory`, public entry point/CLI fail rõ ràng bằng message hướng dẫn cấu hình model, không silent ra output rỗng.

### P0.2 Làm Schema Validation Khớp Với Docs

**Vấn đề**

Docs nói có schema validation cho required fields, type, enum, ID format, field completeness. Code hiện chỉ validate schema ADDIE rất lỏng: required 5 phase, `additionalProperties=true`, không validate subfields. `_validate_addie()` chỉ warning.

**File liên quan**

- `alignmentgraph-isd/src/alignmentgraph_isd/schema/addie_output.json`
- `alignmentgraph-isd/src/alignmentgraph_isd/orchestrator.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/audit.py`
- Có thể tạo mới: `alignmentgraph-isd/src/alignmentgraph_isd/validation.py`
- `docs/proposal.md`

**Hướng sửa**

1. Bổ sung schema chi tiết cho ADDIE output:

- `analysis.needs_analysis`, `learner_analysis`, `context_analysis`, `task_analysis`
- `design.learning_objectives`, `instructional_strategies`
- `development.learner_materials`, `assessment_tools`, `expert_review`
- `implementation.instructor_orientation`, `system_check`, `prototype_execution`, `monitoring`
- `evaluation.formative`, `summative`, `improvement_plan`

2. Thêm node-level validation:

- Validate output sau mỗi specialist agent.
- Nếu parse fail hoặc missing required fields, ghi validation violation vào state.
- Route validation violation về owner agent tương ứng.

3. Phân biệt:

- Schema errors: structural, missing required, wrong type, invalid enum, bad id format.
- Pedagogical violations: alignment, Bloom, coverage, feasibility.

4. Update docs để mô tả đúng cơ chế validation sau khi code được nâng cấp:

- `SchemaValidation` chạy ở cấp graph element và ADDIE aggregate.
- Validation error được route về owner agent.
- `GraphAuditor` vẫn kiểm completeness/coverage ở mức graph state, nhưng không thay thế schema validation.

**Acceptance Criteria**

- Invalid/missing specialist output không bị aggregate im lặng.
- `metadata.errors` hoặc `metadata.violations` cho biết validation problem.
- Test có case missing `learning_objectives` và wrong `assessment_tools` type.
- Docs không còn mô tả validation như future/planned nếu code đã implement.

### P0.3 Mở Rộng `PedagogicalVerifier`

**Vấn đề**

Docs claim verifier kiểm Bloom alignment, constructive alignment, coverage, actionability, rubric consistency, feasibility theo duration/resources. Code hiện mới có:

- assessment coverage
- Bloom verb
- activity support

Chưa có feasibility/actionability/rubric/evaluation alignment thật sự.

**File liên quan**

- `alignmentgraph-isd/src/alignmentgraph_isd/agents/pedagogical_verifier.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/agents/implementation_constraint.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/agents/evaluation_revision.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/memory.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/planner.py`

**Hướng sửa**

Thêm verifier checks:

1. `rubric_consistency`

- Mỗi assessment item cần có `aligned_objective`.
- Performance task cần có rubric/scoring criteria cụ thể.
- Rubric không được quá vague: “good”, “clear”, “appropriate” mà không có observable criteria.

2. `feasibility`

- Đọc `DesignBrief.context.duration`, `class_size`, `learning_environment`, `constraints.resources`.
- Check activity/implementation có phù hợp duration/resources không.
- Nếu duration ngắn nhưng output có quá nhiều session/module, tạo warning/error.

3. `actionability`

- Instructor guide, learner materials, system check, monitoring phải có thao tác cụ thể.
- Flag placeholder, generic text, hoặc missing facilitator notes.

4. `evaluation_alignment`

- Mỗi objective nên có evaluation evidence/metric.
- `evaluation.summative.assessment_tools` nên link về objective hoặc assessment evidence.

5. Đảm bảo `REPAIR_OWNER_MAP` có owner cho các violation mới:

- `rubric_consistency` -> `AssessmentDesignAgent`
- `feasibility` -> `ImplementationConstraintAgent`
- `actionability` -> role gần section lỗi
- `evaluation_alignment` -> `EvaluationRevisionAgent`

**Acceptance Criteria**

- Verifier tạo structured `VerifierViolation` cho ít nhất 5 loại: `coverage`, `bloom`, `activity_support`, `rubric_consistency`, `feasibility`.
- Planner route được các violation mới đến repair node hoặc aggregate với residual violation rõ ràng.
- Docs chỉ claim những checks đã implement.

### P0.4 Gỡ Hard-code VR/Mobile/Language Và Chuyển Sang Domain-neutral

**Trạng thái:** Done. Đã gỡ fallback VR/mobile/language khỏi implementation prompt và `ADDIEOutputAggregator`; các default implementation checks hiện là domain-neutral về learning environment, access, resource, fallback, privacy và accessibility.

**Vấn đề**

Docs case study là IT/Software Engineering, nhưng code hard-code VR/mobile và collaborative language practice trong implementation prompt/aggregator. Điều này có thể làm output Java/OOP/Testing bị sai domain.

**File liên quan**

- `alignmentgraph-isd/src/alignmentgraph_isd/agents/implementation_constraint.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/agents/addie_aggregator.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/rag/planner.py`

**Hướng sửa**

1. Sửa prompt `ImplementationConstraintAgent`:

- Bỏ bắt buộc VR headset/tablet/audio/analytics nếu scenario không yêu cầu.
- Thay bằng domain-neutral:
  - learning platform/LMS
  - lab environment
  - IDE/tooling
  - repo access
  - network/device/accessibility
  - fallback delivery plan

2. Sửa `_strengthen_implementation()`:

- Không auto chèn VR/mobile.
- Không auto chèn checklist IT/SE trong core harness.
- Chỉ thêm các default domain-neutral như learning platform, access, facilitation readiness, resource availability, fallback plan, accessibility.
- Domain-specific checklist phải đi qua RAG/retrieval subagent add-on hoặc context pack được cấu hình từ bên ngoài.

3. Cập nhật docs:

- Core harness sinh implementation constraints domain-neutral.
- Case study IT/SE có thể bổ sung domain context qua external retrieval subagents, không hard-code trong core.

**Acceptance Criteria**

- Smoke input “Java OOP for fresher” không sinh VR/mobile/language practice mặc định.
- Implementation section có resource/access/fallback/accessibility checks domain-neutral.
- IT/SE-specific checklist chỉ xuất hiện nếu context pack/retrieval subagent cung cấp.

### P0.5 Thiết Kế RAG Hai Lớp: Internal AlignmentGraph RAG Và External Corpus Add-ons

**Vấn đề**

Khi chạy benchmark thì không cần external corpus; benchmark nên đo core harness trên cùng input contract. Nhưng trong case study, external corpus lại cần thiết để đưa tri thức IT/SE, templates, rubric, ví dụ bài tập vào workflow. Vì vậy RAG trong AlignmentGraph-ISD cần được mô tả và implement theo hai lớp:

1. **RAG on AlignmentGraph - internal and always**: mọi agent luôn retrieve subgraph/context từ trạng thái `AlignmentGraph` hiện tại. Đây là core của harness.
2. **RAG on external corpus - add-on for case study**: harness cho phép gắn retrieval subagents tương ứng với các corpus source. Đây không phải core bắt buộc của benchmark, nhưng là extension point cho case study/prototype.

**File liên quan**

- `alignmentgraph-isd/src/alignmentgraph_isd/rag/planner.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/agents/base.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/config.py`
- Có thể tạo: `alignmentgraph-isd/src/alignmentgraph_isd/rag/corpus.py`
- Có thể tạo: `alignmentgraph-isd/src/alignmentgraph_isd/rag/subagents.py`
- `docs/proposal.md`

**Hướng sửa code**

1. Làm rõ internal AlignmentGraph RAG:

- `BaseISDAgent._graph_context(...)` là retrieval nội bộ từ graph state.
- Đổi docs/code comments để gọi đúng: `AlignmentGraph context retrieval` hoặc `internal graph RAG`.
- Internal graph RAG always-on, không phụ thuộc external corpus.

2. Thiết kế external retrieval subagent interface:

```python
class RetrievalSubagent:
    name: str
    source_type: str

    def can_handle(self, design_brief, task_name: str) -> bool: ...
    def retrieve(self, design_brief, task_name: str, graph_context: str) -> dict: ...
```

3. `RetrievalPlanner` có khả năng discover/chọn subagents:

- Nhận danh sách subagents từ config hoặc registry.
- Với mỗi task, chọn subagents bằng `can_handle`.
- Merge kết quả thành `context_pack["external_retrieval"]`.
- Mỗi result có `source`, `subagent`, `task_name`, `content`, `citations` nếu có.

4. Benchmark/default config:

- Không cấu hình external retrieval subagents.
- `RetrievalPlanner` luôn trả internal design brief focus/rubric focus tối thiểu.
- `use_ext_corpus=False` chỉ tắt external retrieval subagents/corpus grounding; internal graph/memory retrieval vẫn bật.

5. Case study config:

- Gắn IT/SE corpus subagents, ví dụ Java/OOP, Testing, Git/Agile, code review rubric.
- External retrieval có thể dùng local corpus trước; network/vector store không phải yêu cầu P0.

**Hướng sửa docs**

- Viết rõ: Agentic RAG trong core harness gồm internal graph RAG luôn có.
- External corpus RAG là add-on qua retrieval subagents; cần cho case study nhưng không bắt buộc cho benchmark.
- Sửa diagram để `RetrievalPlanner` discover và route retrieval subagents theo corpus source/task need.

**Acceptance Criteria**

- Benchmark run không phụ thuộc external corpus.
- Code có extension point để đăng ký retrieval subagents.
- `RetrievalPlanner` chọn subagents theo task/source thay vì chỉ trả một context pack tĩnh.
- Docs phân biệt rõ internal graph RAG và external corpus add-on.

## P1 - Cần Sửa Để Docs/Code Khớp Chặt Hơn

### P1.1 Update Code Theo Ý Tưởng Element-level Graph Trong Docs

**Vấn đề**

Docs nói mỗi artifact element là node riêng. Code hiện là section-node graph: `objective_0`, `assessment_0`, `activity_0`, ... và per-LO alignment nằm trong edge evidence.

**Hướng sửa**

1. Giữ section nodes nếu cần cho compatibility, nhưng bổ sung element-level nodes như trạng thái chính:

- `objective:LO-01`, `objective:LO-02`
- `assessment:AT-01`
- `activity:ACT-01`
- `material:MAT-01`
- `constraint:CON-01`
- `evaluation:EV-01`

2. Điều chỉnh agents:

- Khi agent sinh section JSON, tách các list item thành element nodes.
- Vẫn có thể lưu raw section payload trong section node hoặc metadata để aggregator dễ serialize ADDIE.
- Edge không chỉ trỏ vào `objective_0`; edge nên trỏ tới objective element node tương ứng.

3. Điều chỉnh `GraphAuditor`:

- Coverage tính trên objective element nodes.
- `measures`, `supports`, `evaluates` phải nối tới từng objective element.
- Stale cascade xử lý theo element node và có thể propagate lên section aggregate.

4. Điều chỉnh `ADDIEOutputAggregator`:

- Aggregate từ element nodes về schema ADDIE.
- Nếu section node còn tồn tại, dùng làm fallback hoặc raw source, không phải source of truth duy nhất.

**Acceptance Criteria**

- Code có element-level nodes cho objectives, assessments, activities/materials tối thiểu.
- Coverage/alignment không phụ thuộc `edge.evidence=LO-id` trên một `objective_0` duy nhất.
- Docs giữ được ý tưởng graph artifact elements là first-class nodes.

### P1.2 Đồng Bộ Vocabulary Edge

**Trạng thái:** Done. Code đã dùng `constrains`/`evaluates`; `docs/proposal.md` đã được cập nhật để dùng cùng vocabulary thay cho `constrained_by`/`evaluated_by`.

**Vấn đề**

Docs dùng `constrained_by`, `evaluated_by`, trong khi code dùng `constrains`, `evaluates`.

**Hướng sửa**

- Chọn một bộ edge type duy nhất.
- Để giảm sửa code, nên chọn theo code:
  - `measures`
  - `supports`
  - `requires`
  - `constrains`
  - `evaluates`
  - `revises`
  - `depends_on`

**Acceptance Criteria**

- `docs/proposal.md`, graph diagram, role table, `REPAIR_OWNER_MAP`, `AlignmentGraph.EDGE_TYPES` dùng cùng vocabulary.
- Vocabulary chọn theo code hiện tại: `constrains`, `evaluates`, không dùng `constrained_by`, `evaluated_by`.

### P1.3 Update Code Theo Docs: Dynamic ISD Task Graph Builder

**Vấn đề**

Docs nói `MetaAgent` tạo dynamic ISD task graph. Code hiện là audit-driven dynamic router: `GraphAuditor` tạo audit, `ISDTaskPlanner` build candidate tasks mỗi vòng và chọn task ưu tiên.

**Hướng sửa**

1. Thêm explicit `DynamicISDTaskGraph` hoặc `TaskGraphBuilder`:

- Input: `DesignBrief`, current `AlignmentGraph`, audit result, ablation config, memory context.
- Output: task graph gồm task nodes, dependency edges, priority, owner agent, status.
- Task nodes có thể là generation, verification, repair, aggregation.

2. `ISDTaskPlanner` dùng task graph thay vì chỉ build list candidate tạm thời:

- Build/update task graph mỗi audit round.
- Chọn next runnable task từ graph.
- Lưu task graph snapshot vào `planner_decisions`/trajectory.

3. Dynamic behavior:

- Missing/stale graph element tạo task mới.
- Violation tạo repair task với dependency tới failed node/edge.
- Repair cascade tạo downstream refresh tasks.
- Aggregation chỉ runnable khi required tasks complete hoặc khi attempt limits reached.

4. Docs giữ nguyên ý tưởng dynamic task graph, nhưng bổ sung chi tiết audit-driven update nếu cần.

**Acceptance Criteria**

- Code có artifact task graph rõ ràng, không chỉ list candidate trong planner.
- Trajectory ghi được task graph snapshots hoặc selected task kèm dependencies.
- Docs khớp với implementation mới.

### P1.4 Chỉnh Memory/`use_ext_corpus` Semantics

**Trạng thái:** Done. `MemorySession.augment_context_pack()` luôn inject internal memory context vì đây là core graph/memory retrieval. Flag `use_ext_corpus` chỉ dành cho external corpus retrieval add-ons.

**Vấn đề**

Tên flag cũ cho retrieval gây nhập nhằng vì internal graph/memory retrieval luôn là một phần của harness. Thứ cần bật/tắt cho benchmark/case study là external corpus retrieval.

**Hướng sửa**

- Dùng `AblationConfig.use_ext_corpus` làm flag duy nhất cho external corpus retrieval.
- Dùng preset `no_ext_corpus` cho ablation tắt external corpus.
- Memory context luôn được inject như internal retrieval.
- `RetrievalPlanner` luôn trả internal context từ `DesignBrief`; `use_ext_corpus` chỉ điều khiển external corpus subagents khi có.

**Ghi chú**

- Benchmark pure run vẫn không phụ thuộc external corpus.
- Case study có thể bật `use_ext_corpus=True` và đăng ký retrieval subagents.
- Nếu sau này cần ablate internal graph context riêng, tạo flag khác như `use_graph_context`; không dùng `use_ext_corpus` cho việc đó.

**Acceptance Criteria**

- `MemorySession.augment_context_pack()` behavior khớp docs.
- Không còn usage legacy retrieval flag trong code.
- `no_ext_corpus` không tắt internal graph/memory retrieval.

### P1.5 Update Code Theo Docs: Structured Trajectory Cho Validation/Verifier/Repair/Cascade

**Vấn đề**

Docs nói trajectory ghi retry count, violation type, repaired fields, cascade count. Code có text summary nhưng chưa structured đầy đủ.

**File liên quan**

- `alignmentgraph-isd/src/alignmentgraph_isd/trajectory.py`
- `alignmentgraph-isd/src/alignmentgraph_isd/agents/base.py`
- Specialist repair methods

**Hướng sửa**

1. Thêm methods:

- `log_validation_result(...)`
- `log_verifier_result(...)`
- `log_repair_event(...)`
- `log_cascade_event(...)`

2. Metadata mới nên có:

```json
{
  "repair_events": [
    {
      "agent": "AssessmentDesignAgent",
      "violation_type": "coverage",
      "node_id": "objective_0",
      "repaired_fields": ["assessment_tools", "measures_edges"],
      "cascade": {"nodes": 3, "edges": 5}
    }
  ]
}
```

**Acceptance Criteria**

- Trajectory evaluator/human reviewer có thể tính `repair_success_rate` mà không parse text.
- `trajectory` có structured events cho validation, verifier, repair và cascade.
- `metadata` expose summary metrics: `repair_success_rate`, `cascade_count`, `validation_error_count`, `residual_violation_count`.

## P2 - Scope/Documentation Cleanup

### P2.1 Prototype UI/Export

**Vấn đề**

Docs mô tả teacher-facing prototype, subject selector, Markdown/PDF export và trace UI. Code trong `alignmentgraph-isd/` chưa có UI/export.

**Quyết định**

- Prototype hiện tại chưa cần implement.
- Vẫn giữ trong `fix_plan.md` vì đây là phần scope của luận văn/case study, nhưng đánh dấu rõ là planned case-study interface, không phải P0/P1 của core harness.
- Docs cần nói prototype là target/case-study extension nếu chưa có artifact.

**Acceptance Criteria**

- Docs không claim prototype UI/export đã implement nếu repo chưa có.
- Fix plan vẫn giữ P2.1 để nhắc scope prototype sau core harness.

### P2.2 Sync `proposal.html`

**Trạng thái:** Done. Đã thêm slide benchmark `test_30` ngày 18/06/2026 vào phần Evaluation và sync `docs/proposal.html` với `docs/proposal.md`.

**Vấn đề**

Docs có cả `proposal.md` và `proposal.html`. Sửa Markdown xong mà không regenerate HTML sẽ tạo vênh mới.

**Hướng sửa**

- Xác định tool generate hiện tại.
- Regenerate `docs/proposal.html` từ `docs/proposal.md`.
- Nếu HTML là generated artifact, cần ghi vào README hoặc comment quy trình regenerate.

**Acceptance Criteria**

- Nội dung Markdown/HTML đồng bộ sau khi sửa.

### P2.3 Thêm Tests/Smoke Fixtures

**Hướng sửa**

Tạo fixture inputs:

- `tests/fixtures/java_oop_brief.json`
- `tests/fixtures/software_testing_brief.json`
- `tests/fixtures/minimal_brief.json`

Test tối thiểu:

- Public API `MetaAgent.run(DesignBrief)` trả output đúng contract.
- CLI parse input/output nếu vẫn giữ CLI smoke.
- No VR/mobile/language hard-code cho bất kỳ design brief mặc định nào.
- Verifier bắt missing assessment coverage.
- Schema validation bắt missing required section.
- `no_ext_corpus` không gọi external corpus subagents nhưng vẫn giữ internal graph/memory context.
- External retrieval subagent registry hoạt động với fake subagent.

**Acceptance Criteria**

- Có command test rõ trong README hoặc docs.
- Smoke tests chạy không cần network/LLM bằng fake `llm_factory`.

## Đề Xuất Thứ Tự Thực Hiện

### Milestone 1 - Make It Runnable And Honest

1. Chuẩn hoá public API để benchmark gọi trực tiếp.
2. Nếu giữ CLI, làm CLI smoke nhận `DesignBrief` JSON, không raw benchmark scenario.
3. Bỏ VR/mobile/language hard-code và chuyển core sang domain-neutral.
4. Thêm smoke fixture minimal.

**Done khi**

- Benchmark/test harness có thể gọi `MetaAgent.run(DesignBrief)` trực tiếp trong local env/fake LLM.
- Nếu có CLI, `alignmentgraph-isd run --input tests/fixtures/minimal_brief.json ...` chạy được với input shape là `DesignBrief`.
- Output có `addie_output`, `trajectory`, `metadata`.

### Milestone 2 - Make Validation Meaningful

1. Mở rộng schema ADDIE hoặc thêm Pydantic contracts.
2. Route validation errors về owner agent.
3. Thêm tests cho missing/wrong type.

**Done khi**

- Invalid graph element không silently pass.
- `metadata.errors`/`metadata.violations` giải thích được lỗi.

### Milestone 3 - Make Verifier Match Thesis Claims

1. Thêm rubric consistency.
2. Thêm feasibility.
3. Thêm actionability/evaluation alignment.
4. Thêm structured repair/cascade trajectory.

**Done khi**

- Verifier coverage khớp với docs.
- Repair events structured, không chỉ nằm trong summary text.

### Milestone 4 - Implement RAG Extension Point And Clarify Prototype Scope

1. Làm rõ internal AlignmentGraph RAG là always-on core behavior.
2. Thêm external retrieval subagent interface/registry cho case study corpus.
3. Update docs để external corpus RAG là add-on, không phải benchmark dependency.
4. Đồng bộ prototype section và proposal HTML.

**Done khi**

- Benchmark không phụ thuộc external corpus.
- Case study có extension point để gắn corpus retrieval subagents.
- Prototype UI/export được ghi là planned case-study interface nếu chưa implement.

## Checklist Cuối

- [x] Benchmark có thể gọi public API trực tiếp, không cần adapter map scenario trong core.
- [x] CLI command trong docs, nếu giữ, chạy được với `DesignBrief` JSON.
- [x] `pyproject.toml` có console script nếu docs vẫn giữ CLI smoke.
- [ ] Schema validation khớp với docs.
- [ ] Verifier checks khớp với docs.
- [x] Không còn VR/mobile/language hard-code trong core output mặc định.
- [ ] RAG docs phân biệt internal AlignmentGraph RAG và external corpus subagent add-on.
- [ ] Retrieval planner discover/chọn được retrieval subagents.
- [ ] Graph granularity được update theo element-level docs.
- [x] Edge vocabulary đồng bộ theo code: `constrains`, `evaluates`.
- [ ] Dynamic ISD task graph builder được implement theo docs.
- [x] Memory/`use_ext_corpus` semantics đồng bộ theo docs.
- [ ] Trajectory có structured validation/verifier/repair/cascade events.
- [ ] Prototype UI/export được ghi là planned case-study interface nếu chưa implement.
- [ ] `docs/proposal.html` đồng bộ với `docs/proposal.md`.
