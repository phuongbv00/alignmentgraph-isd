# Proposal: AlignmentGraph-ISD for Continuous Instructional Design

## 1. Introduction

### 1.1 Problem Statement

Trong bối cảnh **corporate training** tại các doanh nghiệp phần mềm, chương trình đào tạo nội bộ hiếm khi là một sản phẩm thiết kế một lần. Các khoá học dành cho nhân viên mới, intern, fresher hoặc kỹ sư chuyển đổi vai trò thường phải được cập nhật liên tục theo thay đổi của công nghệ, yêu cầu dự án, đặc điểm người học và phản hồi sau mỗi đợt triển khai. Trong thực tế, một module về Java, lập trình hướng đối tượng, cấu trúc dữ liệu, kiểm thử phần mềm hoặc quy trình phát triển phần mềm có thể cần được cải tiến nhiều lần về mục tiêu học tập, bài tập, rubric, tài liệu giảng dạy, ràng buộc triển khai và kế hoạch đánh giá.

Vấn đề này xuất phát từ trải nghiệm của tác giả trong quá trình xây dựng và cải tiến các khoá học nội bộ cho nhân viên, intern và fresher. Trong luận văn này, **instructional design** được hiểu là quá trình thiết kế có hệ thống các trải nghiệm học tập: phân tích nhu cầu và người học, xác định mục tiêu, thiết kế đánh giá, phát triển hoạt động/tài liệu, lập kế hoạch triển khai và cải tiến dựa trên phản hồi. Các mô hình ngôn ngữ lớn có thể hỗ trợ từng tác vụ riêng lẻ trong quá trình này, nhưng khi được sử dụng như chatbot độc lập, chúng còn hạn chế trong việc duy trì một lifecycle ISD nhất quán cho toàn bộ khoá học.

Các phương pháp gần đây trong AI for education đã tiếp cận bài toán này từ nhiều hướng. Một nhóm tập trung vào benchmark cho năng lực giáo dục của LLM, như OpenLearnLM, EduBench, MathTutorBench và TutorBench, nhưng chủ yếu đánh giá kiến thức, kỹ năng hoặc tutoring thay vì toàn bộ lifecycle ISD. Một nhóm khác tập trung vào hỗ trợ thiết kế bài học hoặc lập kế hoạch dạy học, như LearnLM, LessonPlanner, EduPlanner và các nghiên cứu về teaching plan generation bằng GPT-4. Gần hơn với ISD, ISD-Agent-Bench đề xuất benchmark dựa trên ADDIE và các agent dựa trên lý thuyết như ReAct-ADDIE, ADDIE-Agent, Dick-Carey-Agent và RPISD-Agent. Các hướng này cho thấy nhiều cách kiểm soát quá trình sinh artifact, từ one-shot prompting, tool-use, workflow tuần tự, multi-agent generation đến các mô hình ISD cổ điển.

Tuy vậy, các kiến trúc hiện có vẫn chủ yếu xem ISD như một quá trình sinh artifact tương thích với ADDIE. Chúng chưa đặt **mức độ khớp nhau giữa các thành phần thiết kế** như một trạng thái trung tâm có thể truy xét, kiểm tra và sửa có mục tiêu. Đây là một giới hạn quan trọng đối với bài toán cải tiến khoá học liên tục, vì chất lượng thiết kế không chỉ phụ thuộc vào việc có đủ mục tiêu, hoạt động, bài tập, rubric và kế hoạch triển khai, mà còn phụ thuộc vào việc các thành phần đó có ăn khớp với nhau hay không. Nói cách khác, cần biết mục tiêu nào được đo bởi bài đánh giá nào, hoạt động nào hỗ trợ mục tiêu nào, rubric nào phản ánh đúng evidence of learning nào, và ràng buộc triển khai nào có thể làm kế hoạch dạy học không khả thi.

Từ khoảng trống này, luận văn đề xuất **AlignmentGraph-ISD**, một alignment-graph harness cho ISD agents. Harness đề xuất biểu diễn các instructional design artifacts và sự ăn khớp giữa chúng như một graph tường minh. Hệ thống được thiết kế để tạo output tương thích với ADDIE, đồng thời duy trì một biểu diễn quá trình đủ chi tiết để có thể đánh giá bằng ISD-Agent-Bench.

### 1.2 Contributions

Luận văn đề xuất 1 đóng góp chính: **AlignmentGraph-ISD**, một alignment-graph harness cho Instructional Systems Design agents. Harness này đặt model trong một execution framework chuyên cho ISD, gồm dynamic task graph, multi-agent orchestration, four-layer memory, graph-context retrieval (core) và RAG external corpus (case study), schema-constrained generation, pedagogical verification, targeted repair và workflow trace. Thay vì chỉ sinh một artifact cuối, AlignmentGraph-ISD tổ chức quá trình thiết kế dạy học thành các artifact nodes và alignment edges có quan hệ rõ ràng, cho phép kiểm soát chất lượng, tái chạy phần lỗi và thu thập dữ liệu đánh giá quá trình.

Bên cạnh đóng góp chính là case study trong miền IT/Software Engineering, minh hoạ cách AlignmentGraph-ISD được dùng trong một workflow thực tế: nhận yêu cầu thiết kế hoặc cải tiến một module đào tạo, truy xuất tài liệu miền phần mềm, tạo ADDIE-compatible artifact, kiểm tra alignment giữa mục tiêu-hoạt động-đánh giá, sinh rubric/bài tập, ghi trajectory và xuất kết quả theo format có thể đưa vào pipeline đánh giá. Case study không nhằm chứng minh hiệu quả học tập dài hạn, mà nhằm cho thấy AlignmentGraph-ISD có thể trở thành một công cụ hỗ trợ instructional designer/giảng viên nội bộ trong bối cảnh đào tạo phần mềm.

### 1.3 Research Questions

**RQ1.** Trên ISD-Agent-Bench, AlignmentGraph-ISD cải thiện chất lượng artifact instructional design như thế nào so với các agent baseline và ISD agents hiện có?

**RQ2.** Các thành phần của AlignmentGraph-ISD như dynamic task graph, multi-agent orchestration, graph-context/memory retrieval, schema validation, pedagogical verifier và targeted repair ảnh hưởng như thế nào đến trajectory quality, schema validity, failure rate, latency và token/tool cost? (RAG/external corpus được đánh giá riêng qua case study, không nằm trong ablation grid của benchmark — xem §2.6.)

## 2. Method

### 2.1 Overview

Luận văn đề xuất **AlignmentGraph-ISD** theo công thức:

```text
AlignmentGraph-ISD Agent = AlignmentGraph-ISD Harness + Model
```

Trong đó, AlignmentGraph-ISD Harness cung cấp môi trường thực thi chuyên cho ISD; model cung cấp năng lực ngôn ngữ, reasoning và generation bên trong môi trường đó. Harness không gắn cứng với một mô hình thiết kế dạy học duy nhất. Thay vào đó, nó biểu diễn ISD workflow như một graph có thể cấu hình, trong đó ADDIE là output contract chung để tương thích với ISD-Agent-Bench, còn các chiến lược như backward design, constructive alignment, Gagne sequencing hoặc rubric-first design được dùng như policy/verifier bên trong.

Kiến trúc tổng thể gồm năm lớp:

```text
Scenario / Teacher Request
  -> Orchestrator
  -> Dynamic ISD Task Graph
  -> Four-layer Memory + Graph-context retrieval (core) + RAG external corpus (case study) and Tool Layer
  -> Schema Validation + Pedagogical Verification + Targeted Repair
  -> ADDIE Output Aggregator + Trajectory + Prototype UI Artifact
```

### 2.2 The Alignment Graph

AlignmentGraph-ISD chọn alignment graph vì chất lượng của một instructional design artifact không chỉ nằm ở việc sinh đủ năm mục ADDIE, mà nằm ở mức độ các thành phần thiết kế dạy học khớp với nhau. Trong một khoá học, learning objectives, assessments, activities, materials, implementation constraints và evaluation plan không độc lập. Yêu cầu các thành phần này khớp với nhau chính là nguyên lý **constructive alignment** (Biggs, 1996) `[biggs1996enhancing]`: objectives, learning activities và assessment tasks phải nhất quán với nhau. Một objective có thể được đo bởi nhiều assessment; một assessment có thể bao phủ nhiều objective; một activity có thể hỗ trợ nhiều objective; một constraint về thời lượng, môi trường lab hoặc năng lực đầu vào có thể làm một activity không còn khả thi. Các quan hệ nhiều-nhiều này phù hợp với biểu diễn graph hơn là một workflow tuyến tính.

Trong phương pháp đề xuất, `AlignmentGraph` không chỉ là hình vẽ minh hoạ mà là trạng thái làm việc chung của harness trong suốt quá trình thiết kế:

```text
G_t = (V_t, E_t)                          # alignment graph tại bước t

V_t = V_needs_context ∪ V_objective ∪ V_assessment ∪ V_activity
      ∪ V_material ∪ V_implementation_plan ∪ V_evaluation
      # phủ đủ artifact 5 phase ADDIE: Analysis(needs_context), Design(objective),
      # Development(assessment/activity/material), Implementation(implementation_plan), Evaluation

# Mỗi edge type là một quan hệ nhiều-nhiều có kiểu giữa hai lớp node:
measures  ⊆ V_assessment × V_objective
supports  ⊆ V_activity   × V_objective
evaluates ⊆ V_evaluation × V_objective
E_t = measures ∪ supports ∪ evaluates

# Constructive alignment — bất biến verifier kiểm ở cấp từng objective:
aligned(o) ⇔ (∃ a ∈ V_assessment : (a,o) ∈ measures)
           ∧ (∃ x ∈ V_activity   : (x,o) ∈ supports)
           ∧ (∃ e ∈ V_evaluation : (e,o) ∈ evaluates)   , ∀ o ∈ V_objective

# Node không tham gia alignment edge (needs_context, implementation_plan, material) tác động
# design không qua edge tĩnh mà qua toán tử cascade dựa trên IMPACT_POLICY (xem §2.7);
# needs_context là source gốc (Analysis) lan tới toàn bộ downstream:
cascade(n) = { m ∈ V_t : type(m) ∈ IMPACT_POLICY(type(n)) } ↦ stale
```

![Hình 2.1. AlignmentGraph G_t phủ đủ artifact 5 phase ADDIE: objective làm tâm với ba quan hệ alignment measures/supports/evaluates; needs_context (Analysis) và implementation_plan (Implementation) tác động design qua cascade-invalidation (đứt nét) thay vì cạnh tĩnh; material thuộc V_t nhưng không mang alignment edge.](proposal/assets/alignment-graph.svg)

*Hình 2.1. AlignmentGraph `G_t` — bảy lớp node của `V_t` phủ đủ 5 phase ADDIE (tô màu theo phase) và ba edge alignment của `E_t` lấy `objective` làm tâm; đường đứt nét là cascade theo `IMPACT_POLICY` (§2.7), không thuộc `E_t`. Nguồn chỉnh sửa: `assets/alignment-graph.drawio`.*

Mỗi node lưu một artifact element có schema riêng, ví dụ objective, rubric item, activity, coding exercise, implementation plan hoặc evaluation criterion. Mỗi edge lưu quan hệ khớp-nối giữa hai node, gồm relation type, source node, target node, evidence hoặc rationale, verification status và repair history. ADDIE vẫn được giữ như output contract cuối để tương thích với ISD-Agent-Bench, nhưng execution state bên trong là graph.

`E_t` được giữ tối thiểu và có cơ sở lý thuyết tường minh, lấy `objective` làm tâm. Hai cạnh `measures` (assessment đo objective) và `supports` (activity hỗ trợ objective) trực tiếp hiện thực **constructive alignment** — nguyên lý rằng learning activities và assessment tasks phải khớp với intended learning outcomes (Biggs, 1996) `[biggs1996enhancing]`. Cạnh `evaluates` (evaluation plan đánh giá objective) đóng vòng phase Evaluation của ADDIE (Branch, 2009) `[branch2009addie]`, để output 5-phase vẫn được phủ alignment ở cấp đánh giá. Đây cũng đúng là tam giác objective–activity–assessment mà metric `alignment_score` (§3.2) đo. Các quan hệ ISD khác được biểu diễn bằng cơ chế phù hợp hơn cạnh tĩnh, theo systems approach có vòng formative-evaluation/revision (Dick & Carey, 1978) `[dick1978systematic]`: ràng buộc triển khai (feasibility) không tạo cạnh `constrains` mà lan truyền qua **cascade-invalidation** dựa trên `IMPACT_POLICY` (implementation_plan thay đổi → đánh dấu các node design downstream là stale để planner tái sinh); quan hệ prerequisite được lưu trong `node.data` của objective; còn lịch sử chỉnh sửa (revision) được lưu ở `node.repair_history` và trajectory thay vì một cạnh `revises`. Nhờ vậy harness chỉ vật chất hoá những cạnh có người tiêu thụ thật (verifier/auditor đọc để tính coverage) và có nguồn học thuật rõ, thay vì một bộ quan hệ rộng nhưng phần lớn không được dùng.

Cùng nguyên tắc "chỉ mịn khi có consumer" áp dụng cho *độ mịn của node*. Mỗi artifact type có một section node gộp (`<type>_0`) giữ toàn bộ payload của section đó; riêng những type cần suy luận theo từng phần tử mới được tách thêm thành element node (`<type>:<id>`). Cụ thể, `objective` là element-level vì coverage của constructive alignment được kiểm ở cấp *từng* learning outcome — mỗi objective phải có assessment đo và activity hỗ trợ — nên alignment edge cần trỏ tới đúng `objective:LO-xx` chứ không chỉ tới section gộp. Các type còn lại (assessment, activity, material, implementation_plan, evaluation) được giữ ở mức section vì verifier/auditor suy luận theo cả section là đủ; item của chúng đã nằm dạng danh sách trong `node.data` và mapping tới objective (vd `assessment_tools[i].aligned_objective`) được lưu như thuộc tính, không cần vật chất hoá thành cạnh riêng. Độ mịn của graph vì thế đi theo nhu cầu kiểm tra thực tế, giữ trạng thái nhỏ gọn để kiểm soát token/latency cost.

**Node type ≠ artifact type.** Mỗi node type là một *category* artifact ADDIE, không phải một artifact đơn lẻ: toàn bộ nội dung phong phú của một phase (nhiều sub-artifact) nằm trong `node.data`, chứ không tách thành nhiều node. Ví dụ một run điển hình có 7 node type nhưng ~12 node instance (7 section + ~5 element `objective:LO-*`) và hàng chục sub-artifact bên trong `data`. Bảng dưới đặc tả artifact chính mỗi node type mang (theo schema; agent có thể thêm field mô tả như `storyboard`, `media_selection`, `operator_manual`, `pilot_data_collection`):

| Node type | ADDIE phase | Artifact chính trong `node.data` | Element node |
| --- | --- | --- | --- |
| `needs_context` | Analysis | `needs_analysis`, `learner_analysis`, `context_analysis`, `task_analysis` | — |
| `objective` | Design | `learning_objectives[]`, `instructional_strategies` (+ `content_structure`, `assessment_plan`, `storyboard`, `alignment_matrix`) | `objective:LO-*` |
| `assessment` | Development | `assessment_tools[]`, `expert_review` | — |
| `activity` | Development | `learner_materials[]`, `instructor_guide` (+ `operator_manual`) | — |
| `material` | Development | `learner_materials[]` | — |
| `implementation_plan` | Implementation | `instructor_orientation`, `system_check`, `prototype_execution`, `monitoring` | — |
| `evaluation` | Evaluation | `formative`, `summative`, `improvement_plan` (+ `pilot_data_collection`) | — |

Nói cách khác, alignment graph là *lớp alignment/control mỏng* (node = điểm neo alignment + đơn vị cascade) phủ lên *payload artifact giàu*; `ADDIEOutputAggregator` serialize các payload này thành 5 phase của `addie_output`. Element node chỉ tách ra ở nơi có consumer cấp phần tử: hiện chỉ `objective` (coverage per-LO); các type còn lại (kể cả `assessment`, `material`) giữ ở mức section vì verifier/auditor suy luận theo cả section là đủ.

Cách biểu diễn này tạo ra bốn lợi ích kiến trúc. Thứ nhất, verifier có thể kiểm tra alignment có cấu trúc ở cấp edge, ví dụ assessment có thật sự đo objective hay activity có thật sự hỗ trợ outcome. Thứ hai, repair trở nên có mục tiêu: khi một rubric không đo đúng objective, harness sửa assessment node hoặc `measures` edge liên quan thay vì sinh lại toàn bộ lesson plan. Thứ ba, orchestration trở nên phi tuyến: `MetaAgent` có thể nhìn trạng thái graph, missing edge hoặc failed node để quyết định bước kế tiếp, thay vì chạy cứng Analysis -> Design -> Development -> Implementation -> Evaluation. Thứ tư, trajectory trở nên đánh giá được vì mỗi thao tác thêm, sửa, kiểm tra hoặc repair node/edge đều có thể được log lại cùng agent, retrieval context, verifier result, token/cost và latency.

Vì vậy, alignment graph là cơ sở để nối ba yêu cầu của luận văn: giữ chất lượng sư phạm thông qua alignment, hỗ trợ execution phi tuyến thay vì ADDIE tuyến tính cứng, và tạo trajectory đủ chi tiết để đánh giá bằng ISD-Agent-Bench.

### 2.3 Architectural Comparison with ISD-Agent-Bench Agents

Điểm khác biệt chính của AlignmentGraph-ISD so với các agent trong ISD-Agent-Bench là nó không chỉ là một agent strategy đơn lẻ. Nó là harness điều phối nhiều role, nhiều nguồn tri thức, nhiều checkpoint và nhiều cơ chế kiểm tra. Các agent hiện có trong benchmark đại diện cho các chiến lược riêng: single-prompt generation, ReAct tool-use, sequential ADDIE, process-model-specific workflow hoặc generate-evaluate-optimize loop. AlignmentGraph-ISD kết hợp các lợi thế này trong một kiến trúc có thể đo lường: workflow có graph-element contract, agentic RAG có policy truy xuất, verifier có tiêu chí rõ, repair có target, và trajectory được log thống nhất.

| Agent/Architecture | Kiến trúc lõi | Điểm mạnh | Giới hạn chính | Khác biệt của kiến trúc đề xuất |
| --- | --- | --- | --- | --- |
| `baseline` | Một prompt sinh toàn bộ ADDIE output | Đơn giản, chi phí thấp, dễ chạy | Không có workflow trace giàu thông tin, không có kiểm tra pha, lỗi một phần khó sửa có mục tiêu | AlignmentGraph-ISD chia workflow thành artifact nodes và alignment edges, validate từng phần và log trajectory |
| `react-isd` | ReAct agent dùng các ISD tools | Linh hoạt, có tool-use, gần agentic pattern phổ biến | Tool choice phụ thuộc mạnh vào model; thứ tự ISD và chất lượng output khó kiểm soát tất định | AlignmentGraph-ISD dùng graph policy để kiểm soát transition, tool permission và graph-element contract |
| `addie-agent` | StateGraph tuyến tính qua 5 pha ADDIE | Rõ lifecycle, dễ tương thích output schema | Tuyến tính cứng; ít cơ chế repair/verifier và ít linh hoạt với domain/corpus | AlignmentGraph-ISD giữ ADDIE contract nhưng cho phép dynamic orchestration, verifier và targeted repair |
| `dick-carey-agent` | Workflow theo Dick & Carey, có formative-evaluation loop | Mạnh ở systems approach và revision | Bám một process model cụ thể; mapping về ADDIE là lớp chuyển đổi | AlignmentGraph-ISD không gắn cứng với một model ISD, dùng policy/verifier để kết hợp nhiều nguyên tắc |
| `rpisd-agent` | Rapid prototyping loop với feedback nhiều phía | Phù hợp cải tiến prototype và usability feedback | Phức tạp, cần nhiều giả định về feedback; không phải mọi scenario đều cần prototyping | AlignmentGraph-ISD có thể bật/tắt loop repair theo verifier result thay vì ép mọi task vào prototyping |
| `eduplanner` | Multi-agent generate-evaluate-optimize | Có evaluator/optimizer loop, cải thiện artifact qua phản hồi | Tập trung vào tối ưu output, chưa nhấn mạnh agentic RAG, schema contract và trace chuẩn hoá ở mọi node | AlignmentGraph-ISD dùng multi-agent theo role ISD, context pack theo task, verifier/repair và trace thống nhất |
| **AlignmentGraph-ISD** | Harness gồm orchestrator, dynamic task graph, role-based agents, agentic RAG, schema/verifier/repair, trace | Kiểm soát được workflow, truy xuất tri thức theo task, sửa lỗi có mục tiêu, đánh giá được cả output và process | Chi phí latency/token cao hơn, cần thiết kế policy và corpus cẩn thận | Dùng ADDIE như output contract, nhưng execution bên trong là non-linear ISD orchestration |

### 2.4 Proposed Workflow

Workflow đề xuất bắt đầu từ scenario của ISD-Agent-Bench hoặc yêu cầu của giảng viên nội bộ. `MetaAgent` không chạy cứng chuỗi Analysis -> Design -> Development -> Implementation -> Evaluation. Thay vào đó, nó tạo một **dynamic ISD task graph**, trong đó needs/context analysis, objective design, assessment design, activity/material design, implementation planning và evaluation/revision planning có thể tương tác lặp quanh một `AlignmentGraph`. ADDIE chỉ là output contract ở bước cuối: `ADDIEOutputAggregator` serialize AlignmentGraph đã được kiểm tra vào schema `addie_output` để benchmark có thể đánh giá.

```mermaid
flowchart TD
    A["ISD-Agent-Bench Scenario or Teacher Request"] --> B["MetaAgent"]
    B --> C["Dynamic ISD Task Graph Builder"]
    B --> D["ContextPlanner (context prep) + memory/graph-context retrieval (core)"]
    B --> D2["RetrievalPlanner = RAG external corpus (case study, use_rag)"]
    D --> F["ContextPack by task"]
    D2 --> F

    C --> G["AlignmentGraph: objectives <-> assessment <-> activities"]
    F --> G
    G <--> H["Needs/Context Analysis Agent"]
    G <--> I["Objective Design Agent"]
    G <--> J["Assessment Design Agent"]
    G <--> K["Activity and Material Agent"]
    G <--> L["Implementation Plan Agent"]
    G <--> M["Evaluation and Revision Agent"]

    G --> N["Validated Graph Elements"]
    N --> O["SchemaValidation"]
    O --> P{"Schema valid?"}
    P -- "No" --> Q["Policy-routed specialist repair + cascade invalidation"]
    Q --> G
    P -- "Yes" --> R["PedagogicalVerifierAgent"]
    R --> S{"Aligned and feasible?"}
    S -- "No" --> Q
    S -- "Yes" --> T["ADDIEOutputAggregator"]
    T --> U["ADDIE Output + Trajectory + Metadata"]
    U --> V["ISD Evaluator or Prototype Export"]
```

### 2.5 Multi-agent Orchestration

AlignmentGraph-ISD dùng multi-agent workflow gồm các role sau:

| Role | Trách nhiệm | Output chính |
| --- | --- | --- |
| `MetaAgent` | Phân tích request/scenario, tạo dynamic task graph, chọn policy, điều phối retry và ghi trace | execution graph, transition decision |
| `NeedsContextAgent` | Phân tích target audience, prior knowledge, context, constraints và task structure | need/context nodes and edges |
| `ObjectiveDesignAgent` | Thiết kế mục tiêu học tập, Bloom level, measurable criteria và prerequisite assumptions | objective nodes and prerequisite edges |
| `AssessmentDesignAgent` | Thiết kế evidence, rubric, formative/summative assessment và success criteria | assessment/rubric nodes and `measures` edges |
| `ActivityMaterialAgent` | Tạo learning activities, materials, exercises, examples và facilitator notes | activity/material nodes and `supports` edges |
| `ImplementationPlanAgent` | Phân tích duration, resource, delivery mode, risk và deployment constraints; đẩy ràng buộc feasibility ngược về design | implementation_plan nodes |
| `EvaluationRevisionAgent` | Thiết kế evaluation plan, feedback loop và revision strategy | evaluation nodes and `evaluates` edges |
| `AlignmentGraph` | Đồng bộ objectives, assessment, activities, implementation plan và evaluation criteria; quản lý stale cascade khi node thay đổi | aligned artifact graph + stale impact state |
| `PedagogicalVerifierAgent` | Kiểm tra Bloom alignment, constructive alignment, coverage, actionability và consistency | verifier report |
| Specialist repair methods | Mỗi role agent tự sửa graph element thuộc chuyên môn của mình khi schema hoặc verifier policy báo lỗi | repaired node/edge patch |
| `ADDIEOutputAggregator` | Map artifact graph cuối vào schema `addie_output` của ISD-Agent-Bench | ADDIE-compatible output |

Các role có thể dùng cùng một model backend nhưng khác system prompt, tool permission, context pack và output schema. `MetaAgent` không sinh toàn bộ nội dung thay các agent khác; nó giữ vai trò controller. Khác với ADDIE tuyến tính, các agent làm việc trên graph elements: thêm, sửa hoặc liên kết artifact nodes và alignment edges trong `AlignmentGraph`. Ví dụ, `AssessmentDesignAgent` có thể buộc `ObjectiveDesignAgent` sửa objective node nếu không có evidence đo được; `ImplementationPlanAgent` có thể đẩy implementation_plan node ngược lại để `ActivityMaterialAgent` điều chỉnh activity nodes. Điều này giúp AlignmentGraph-ISD giữ ADDIE-compatible output mà không bị ràng buộc vào execution order của `addie-agent`.

### 2.6 RAG (External Corpus Retrieval)

Trong AlignmentGraph-ISD, **RAG chỉ đại diện cho external corpus retrieval**. Đây là một add-on cho case study/app, không phải thành phần của benchmark.

Cần phân biệt rõ ba loại truy xuất, trong đó chỉ loại thứ ba được gọi là RAG:

1. **Context preparation — `ContextPlanner`, always-on, KHÔNG phải retrieval.** Restructure design brief thành design-brief focus, alignment requirements và rubric focus cho từng agent. Đây chỉ là biến đổi input, không đọc store nào, nên **không** phải retrieval/RAG.
2. **Graph-context retrieval — core, always-on.** Mỗi agent truy xuất subgraph liên quan từ trạng thái `AlignmentGraph` hiện tại (`BaseISDAgent._graph_context`). Là retrieval nhưng **không** gọi là RAG.
3. **Memory retrieval — core, always-on.** Working/episodic memory được inject vào context pack (`MemorySession.augment_context_pack`). Là retrieval nhưng **không** phải RAG.
4. **RAG = external corpus retrieval — add-on.** `RetrievalPlanner` chỉ làm đúng một việc: chạy các *retrieval subagents* (`RetrievalSubagent`) qua `RetrievalSubagentRegistry`, discover/chọn theo task bằng `can_handle`, rồi trả kết quả (`source`, `subagent`, `task_name`, `content`, `citations`). `RetrievalPlanner` **không** dựng context pack nội bộ — đó là việc của `ContextPlanner`.

`MetaAgent` lắp context pack từ ba nguồn trên (context prep + memory + RAG). RAG chỉ bật khi `use_rag=True` (preset `case_study`) và có subagents được đăng ký; kết quả merge vào `context_pack["rag"]`. **Benchmark mặc định dùng `no_rag`** (`use_rag=False`, không đăng ký subagent nào), nên `RetrievalPlanner` trả về kết quả rỗng/disabled và mọi agent chỉ dùng context prep + graph-context + memory trên cùng một input contract. Hệ quả: đóng góp của RAG được minh hoạ định tính qua case study/app, không nằm trong ablation grid của benchmark.

Quy trình (lắp trong `MetaAgent.run`):

```text
Request/Scenario
  -> ContextPlanner.build(brief)                 # context prep, KHÔNG phải retrieval
  -> + memory retrieval (core, always-on)         # MemorySession.augment_context_pack
  -> + graph-context retrieval (core, in agents)   # BaseISDAgent._graph_context
  -> + RAG (gated by use_rag): RetrievalPlanner -> Registry.select(task) -> retrieve   # external corpus only
  -> ContextPack per agent
  -> Citation/grounding metadata trong retrieval result (RetrievalResult.citations; chưa bắt buộc chèn vào final artifact)
```

Ví dụ, trong case study/app khi yêu cầu một khoá Software Testing cho fresher, registry chọn subagent corpus Testing (rubric test plan, unit test assignment, test-case design examples) cho `AssessmentDesignAgent` và `ActivityMaterialAgent`; với một brief Java/OOP thì subagent Testing không được chọn còn subagent OOP được chọn. Khi chạy benchmark (`no_rag`), không có subagent nào nên các agent chỉ dùng graph-context + design-brief context.

### 2.7 Schema Contracts and Verification

Để tương thích với ISD-Agent-Bench, output cuối của AlignmentGraph-ISD tuân thủ schema ADDIE:

```text
addie_output.analysis
addie_output.design
addie_output.development
addie_output.implementation
addie_output.evaluation
trajectory
metadata
```

Mỗi graph element có schema nội bộ chi tiết hơn schema cuối. Sau khi agent sinh hoặc cập nhật node/edge, AlignmentGraph-ISD chạy hai lớp kiểm tra:

1. **Schema validation**: kiểm tra JSON parseability, required fields, type, enum, ID format và field completeness.
2. **Pedagogical verification**: kiểm tra learning objectives có measurable/action verbs, objective-activity-assessment alignment, coverage giữa goals và artifacts, rubric consistency, feasibility theo duration/resources, và actionability cho người dạy.

Nếu lỗi thuộc schema, policy route validation error và graph element liên quan về đúng owner agent để sửa cấu trúc. Nếu lỗi thuộc pedagogy, verifier report được route theo loại violation: objective/Bloom về `ObjectiveDesignAgent`, coverage về `AssessmentDesignAgent`, activity support về `ActivityMaterialAgent`, feasibility về `ImplementationPlanAgent`, evaluation alignment về `EvaluationRevisionAgent`.

Sau mỗi targeted repair, AlignmentGraph chạy cascade invalidation thay vì chỉ sửa cục bộ. Impact matrix hiện tại:

| Node thay đổi | Node downstream cần refresh |
| --- | --- |
| `needs_context` | `objective`, `assessment`, `activity`, `material`, `implementation_plan`, `evaluation` |
| `objective` | `assessment`, `activity`, `material`, `evaluation` |
| `assessment` | `activity`, `material`, `evaluation` |
| `activity` / `material` | peer development node, `assessment`, `implementation_plan`, `evaluation` |
| `implementation_plan` | `objective`, `assessment`, `activity`, `material`, `evaluation` |
| `evaluation` | `assessment` |

Các node/edge bị ảnh hưởng được đánh dấu `stale`; stale edge không được tính là coverage hợp lệ và không được đưa vào alignment evidence cuối. `GraphAuditor` biến stale state thành task mới, rồi `ISDTaskPlanner` route task đó về specialist agent tương ứng. AlignmentGraph-ISD ghi rõ retry count, violation type, repaired fields và cascade count vào trajectory. Nhờ đó, evaluation không chỉ nhìn output cuối mà còn thấy quá trình hệ thống phát hiện, sửa lỗi và xử lý hiệu ứng downstream.

### 2.8 Four-layer Memory and Session Lifecycle

Trong app thực tế, `AlignmentGraph` không chỉ là working state tạm thời của một lần chạy. Nó là training-program-level living artifact: phiên đầu tạo graph, các phiên sau tuning graph đó bằng specialist patch và cascade invalidation. Harness tổ chức memory thành bốn layer:

| Layer | Scope | Nội dung |
| --- | --- | --- |
| Working | active session | user intent hiện tại, `entrypoint_mode`, graph version đang mở, message history, audit state, pending tasks, verifier violations |
| Semantic | global stable knowledge | ADDIE, Bloom, constructive alignment, rubric templates, domain corpus IT/SE |
| Episodic | training program/session history | session events, accepted/rejected patches, repair/cascade history, metric summaries |
| Procedural | versioned policy | agent protocols, repair owner map, verifier rules, `IMPACT_POLICY`, ablation policy |

Vì vậy, benchmark run được xem như **pure new run**: nó mô phỏng lượt build graph đầu tiên nhưng chưa attach vào persisted training program:

```text
ISD-Agent-Bench scenario
  -> pure_new_run
  -> AlignmentGraph v1
  -> self-check + specialist repair
  -> ADDIE artifact + trajectory + memory metadata
```

Prototype app mở rộng cùng core đó thành nhiều phiên:

```text
Session 1: init AlignmentGraph v1
Session 2..N: load vN, apply user tuning request, cascade stale downstream nodes, commit vN+1
```

Trong benchmark, adapter không truyền `training_program_id` hoặc `session_id`, nên mỗi run là `pure_new_run`: graph mới trong memory tạm, không load graph cũ và không persist session. Trong app, API runtime dùng `training_program_id` làm khóa bền vững của graph; `session_id` chỉ truyền khi muốn tiếp tục working memory/message history của một phiên cụ thể:

```python
# Benchmark/default.
MemoryConfig()

# App: new session on a training program graph.
MemoryConfig(
    training_program_id="java-oop-training-v1",
)

# App: resume an existing session.
MemoryConfig(
    training_program_id="java-oop-training-v1",
    session_id="tuning-session-002",
)
```

Harness tự load latest graph nếu `training_program_id` đã tồn tại, tự sinh `session_id` cho phiên mới, và tự gán `session_type=init` hoặc `session_type=tuning` theo graph version hiện có. Nếu có cả `training_program_id` và `session_id`, harness thêm `entrypoint_mode=resume_session` và load working memory của session. Internal graph/memory retrieval là core behavior và luôn bật; flag `use_rag` (preset `case_study`) chỉ điều khiển external corpus retrieval add-ons cho case study.

### 2.9 Prototype for IT/Software Engineering Case Study

> **Trạng thái:** *planned case-study interface.* Core harness (`alignmentgraph_isd`) đã sẵn sàng — public API `MetaAgent.run(DesignBrief)`/`run_design_brief`, CLI smoke, output `addie_output`/`trajectory`/`metadata` — nhưng UI teacher-facing và Markdown/PDF export **chưa được implement** trong repo. Phần dưới mô tả giao diện mục tiêu của case study, không phải artifact đã có.

Prototype (planned) là một sản phẩm teacher-facing cho miền IT/Software Engineering. Giao diện tối thiểu dự kiến gồm:

- nhập yêu cầu thiết kế/cải tiến module đào tạo;
- chọn subject area như Java/OOP, Data Structures, Software Testing, Git, Agile/Scrum hoặc Software Engineering fundamentals;
- chọn duration, target audience, delivery mode, resource constraints;
- xem artifact ADDIE đã sinh;
- xem verifier warnings và repair history;
- xuất JSON theo schema benchmark và Markdown/PDF lesson package cho người dạy;
- xem workflow trace gồm agent steps, retrieval sources, validation result, verifier result, token/cost/latency.

Prototype phục vụ hai mục tiêu. Thứ nhất, nó chứng minh AlignmentGraph-ISD có thể vận hành như một sản phẩm thực tế chứ không chỉ là script benchmark. Thứ hai, nó cung cấp case study để phân tích sâu các artifact trong miền phần mềm, nơi yêu cầu thiết kế thường có nhiều ràng buộc domain-specific như bài tập code, rubric chấm correctness/design/readability, môi trường lab, test case và feedback vòng lặp.

## 3. Evaluation

### 3.1 Evaluation Goals

Evaluation của luận văn tập trung vào hai câu hỏi nghiên cứu: AlignmentGraph-ISD có tạo output ISD tốt hơn không, và các thành phần của AlignmentGraph-ISD có làm quá trình tạo output đáng tin cậy hơn không. Luận văn không tự xây benchmark mới. Đánh giá định lượng chính dùng ISD-Agent-Bench, vì benchmark này đã có scenario set, input/output schema, nhiều agent baseline và evaluator dựa trên ADDIE rubric cùng trajectory scoring. Bên cạnh đó, prototype IT/Software Engineering được dùng như một case study định tính để minh hoạ AlignmentGraph-ISD trong bối cảnh đào tạo nội bộ thực tế.

### 3.2 Quantitative Evaluation on ISD-Agent-Bench

AlignmentGraph-ISD được tích hợp như một agent mới trong pipeline ISD-Agent-Bench. Nó nhận cùng scenario JSON với các agent khác và trả về cùng output schema.

Trong diễn giải session lifecycle, mỗi benchmark run tương đương lượt build graph đầu tiên: scenario tạo `alignment_graph_v1`, chạy self-check/repair trước khi aggregate, rồi trả metadata. Benchmark không attach graph vào persisted training program và không đo toàn bộ quá trình tuning dài hạn; phần đó thuộc case study/prototype evaluation.

```bash
# Package CLI nhận DesignBrief-shaped JSON (scenario của benchmark được
# adapter map scenario_id -> id trước khi vào harness).
alignmentgraph-isd run \
  --input design_brief.json \
  --output result.json \
  --trajectory trajectory.json
```

Các biến thể so sánh:

| Variant | Mục đích |
| --- | --- |
| `baseline` | lower bound single-prompt generation |
| `react-isd` | so sánh với ReAct tool-use agent |
| `addie-agent` | so sánh với sequential ADDIE workflow |
| `dick-carey-agent` | so sánh với systems approach có feedback loop |
| `rpisd-agent` | so sánh với rapid prototyping workflow |
| `eduplanner` | so sánh với generate-evaluate-optimize multi-agent strategy |
| `alignmentgraph-isd` | proposed method |

Các metric chính:

| Metric | Ý nghĩa |
| --- | --- |
| `total_score` | điểm tổng hợp của evaluator |
| `addie_score` | chất lượng artifact theo ADDIE rubric |
| `trajectory_score` | chất lượng quá trình/tool-use nếu có trajectory |
| `schema_validity` | tỷ lệ output hợp lệ theo schema |
| `phase_coverage` | năm pha ADDIE có đủ nội dung cần thiết không |
| `alignment_score` | mục tiêu, hoạt động, assessment và rubric có nhất quán không |
| `repair_success_rate` | tỷ lệ lỗi schema/verifier được sửa thành công |
| `latency_ms`, `llm_calls`, `tool_calls`, `token_usage` | chi phí vận hành |

Kết quả được báo cáo theo toàn bộ test split hoặc một subset cân bằng nếu giới hạn chi phí. Subset phải được chọn trước khi chạy, stratified theo domain, difficulty, duration, learning environment và class size. Mỗi run cần có manifest ghi rõ model, judge, prompt version, commit hash, sample list, seed, temperature, max tokens và adapter version.

### 3.3 Preliminary Benchmark Result on `test_30` (18/06/2026)

Một benchmark sơ bộ đã được chạy ngày **18/06/2026** trên subset `test_30`, dùng agent model **Gemma 4 26B A4B**. Kết quả được lưu tại:

```text
isd-agent-benchmark/results/test_30_benchmark_gemma-4-26b-a4b-it-nitro_20260618_193248/aggregate_table.md
```

Kết quả này được dùng như checkpoint kỹ thuật để xem proposed agent đang đứng ở đâu trước khi hoàn thiện các phần còn thiếu của system design. Vì subset chỉ có 30 scenarios, kết quả chưa được dùng để claim statistical superiority.

**Thành phần subset so với full testset.** `test_30` gồm 30/1202 scenarios (≈ 2.5%) của full test split, lấy mẫu stratified ngẫu nhiên có seed (`seed=42`) theo **10 domain × 3 mức difficulty × 1 scenario**, và lồng nhau `test_30 ⊂ test_90 ⊂ test`. Theo trục **difficulty**, subset gần khớp full test (≈ 33% mỗi mức Easy/Moderate/Hard so với 33.0 / 33.7 / 33.3 của full test). Theo trục **domain**, subset cố ý phủ đều 10% mỗi domain, khác với full test vốn lệch mạnh về 4 domain lớn — Language, Mathematics, Science, Social Studies chiếm ≈ 78% — trong khi mỗi domain chuyên biệt (gồm Software Development/IT) chỉ ≈ 3.5%. Nói cách khác, `test_30` ưu tiên **độ phủ cân bằng giữa các domain** thay vì khớp tỉ lệ tự nhiên của full test, nên kết quả mang tính smoke-test đa domain (đại diện theo difficulty nhưng over-sample các domain chuyên biệt) chứ chưa phản ánh phân phối domain thật của 1202 scenarios.

| Agent | GPT | Gemini | Avg |
| --- | ---: | ---: | ---: |
| React-ADDIE | 85.40 | **88.96** | **87.18** |
| AlignmentGraph-ISD (proposed) | **85.63** | 85.70 | 85.67 |
| EduPlanner | 83.68 | 86.10 | 84.89 |
| RPISD-Agent | 83.43 | 83.23 | 83.33 |
| ADDIE-Agent | 82.78 | 83.57 | 83.18 |
| Dick-Carey-Agent | 80.86 | 81.33 | 81.09 |
| Baseline | 79.97 | 82.13 | 81.05 |

Các điểm đáng chú ý:

- AlignmentGraph-ISD đạt **85.67 Avg**, đứng thứ hai sau React-ADDIE (**87.18**).
- AlignmentGraph-ISD đạt điểm cao nhất theo evaluator GPT (**85.63**).
- Theo phase-wise average, AlignmentGraph-ISD đang dẫn ở **Implementation** (**82.3**) và **Evaluation** (**85.0**).
- Khoảng cách lớn nhất hiện nằm ở **Trajectory**: AlignmentGraph-ISD đạt **88.38**, thấp hơn React-ADDIE (**93.08**), cho thấy cần tiếp tục hoàn thiện logging, repair trace và dynamic orchestration.

Tại thời điểm chạy `test_30` (18/06/2026), một số thành phần của proposed system design còn là gap. **Tính đến hiện tại, các gap chính đã được đóng** trong package `alignmentgraph_isd`:

- schema validation chi tiết (`validation.py`) và routing lỗi schema về owner agent qua `GraphAuditor`;
- verifier mở rộng đủ bảy kiểm tra, gồm rubric consistency, feasibility, actionability và evaluation alignment (`pedagogical_verifier.py`);
- element-level AlignmentGraph: `objective` được biểu diễn thành first-class element node (`objective:LO-*`), coverage tính trên từng element thay vì chỉ section node (`graph.py`, `audit.py`); các type còn lại (assessment, material, …) giữ ở mức section theo nguyên tắc "chỉ mịn khi có consumer";
- Dynamic ISD Task Graph Builder (`task_graph.py`) sinh task graph có owner/priority/dependency và snapshot mỗi planner round, thay cho planner chỉ dựa trên candidate list;
- retrieval subagent interface cho external corpus trong case study (`rag/`), gated bởi `use_rag`;
- structured trajectory cho validation, verifier, repair và cascade events (`trajectory.py`).

Các phần còn lại chủ yếu nằm ở case study/prototype (UI teacher-facing và Markdown/PDF export, xem §2.9) chứ không phải core harness. Sau khi các gap chính được đóng, evaluation sẽ mở rộng từ `test_30` sang `test_90`, sau đó tăng dần độ robust trên các subset lớn hơn trước khi chạy full testset **1202 scenarios**.

### 3.4 Ablation Study

Để trả lời RQ2, luận văn chạy các ablation:

Benchmark luôn chạy `no_rag` (RAG = external corpus chỉ dùng cho case study/app, xem §2.6), nên RAG không nằm trong ablation grid của benchmark. Các ablation trên benchmark:

| Ablation | Thành phần bị tắt | Mục tiêu |
| --- | --- | --- |
| `no_verifier` | bỏ pedagogical verifier | đo lỗi alignment và rubric consistency |
| `no_repair` | phát hiện lỗi nhưng không sửa | đo giá trị của targeted repair |
| `single_agent` | thay multi-agent workflow bằng một agent sinh toàn bộ output | đo giá trị của role decomposition |
| `linear_addie_only` | giữ graph tuyến tính, bỏ dynamic orchestration policy | so sánh AlignmentGraph-ISD với ADDIE sequential agent |

Lưu ý: graph-context và memory retrieval là core (always-on) nên không có ablation tắt chúng; tác động của RAG được minh hoạ định tính trong case study/app (preset `case_study`, `use_rag=True`).

Ablation không nhằm tạo thêm nhiều claim rời rạc. Nó giúp giải thích contribution chính: AlignmentGraph-ISD tốt hơn vì thành phần nào, trong điều kiện nào, và trade-off chi phí ra sao.

### 3.5 Case Study Evaluation for IT/Software Engineering Prototype

Case study dùng 3-5 tác vụ thiết kế/cải tiến khoá học trong miền IT/Software Engineering, ví dụ:

- thiết kế module OOP Java cho fresher trong 2 tuần;
- cải tiến bài tập Data Structures để tăng độ rõ của rubric;
- tạo lesson package cho Software Testing gồm lab, checklist, rubric và formative quiz;
- thiết kế mini-project Git/Agile cho nhóm mới vào dự án;
- chuyển một workshop Code Review thành blended learning module.

Mỗi case study được phân tích theo các tiêu chí:

| Tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| Domain relevance | Artifact có đúng với thực hành IT/Software Engineering không? |
| Instructional alignment | Objectives, activities, materials và assessment có khớp nhau không? |
| Actionability | Giảng viên có thể dùng hoặc chỉnh ít để triển khai không? |
| Trace usefulness | Trace có giúp hiểu vì sao artifact được tạo/sửa như vậy không? |
| Prototype usability | Workflow có phù hợp với thao tác thiết kế/cải tiến khoá học nội bộ không? |

Phần này có thể dùng expert review nhỏ với 2-3 người có kinh nghiệm đào tạo nội bộ hoặc software engineering education. Nếu chưa đủ điều kiện human evaluation, case study được báo cáo như qualitative analysis, không dùng để claim statistical superiority.

### 3.6 Threats to Validity

**Internal validity.** Prompt, model và judge có thể ảnh hưởng kết quả. Luận văn cần cố định run manifest, chạy cùng model/decoding config cho các variant khi khả thi, randomize order khi dùng LLM-as-judge và báo cáo lỗi connection/schema đầy đủ.

**Construct validity.** ISD-Agent-Bench đánh giá chất lượng artifact và trajectory, không đo trực tiếp learning outcome của học viên. Vì vậy, kết luận chỉ nằm ở chất lượng instructional design output và quá trình agentic workflow.

**External validity.** Prototype IT/Software Engineering chỉ minh hoạ một miền ứng dụng. AlignmentGraph-ISD được thiết kế để mở rộng sang domain khác qua corpus, templates và verifier policy, nhưng luận văn không claim hiệu quả tương đương trên mọi môn học.

**Cost validity.** Multi-agent và agentic RAG có thể tăng latency/token cost. Vì vậy, evaluation cần báo cáo trade-off giữa điểm số, độ ổn định, số lần repair và chi phí vận hành, thay vì chỉ báo cáo chất lượng artifact.
