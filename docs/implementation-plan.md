# Implementation Plan: AlignmentGraph-ISD

## 1. Repository Layout

Harness được tổ chức thành hai phần song song: package core `alignmentgraph_isd` và adapter tích hợp vào ISD-Agent-Bench. Việc tách này đảm bảo harness có thể chạy độc lập (prototype UI) và qua benchmark (evaluation) mà không phụ thuộc lẫn nhau.

```
master-thesis/
├── isd-agent-benchmark/               # git submodule (benchmark gốc, không sửa)
│   ├── agents/
│   │   └── alignmentgraph-isd/        # adapter package (thêm mới)
│   │       ├── pyproject.toml
│   │       └── src/alignmentgraph_isd_agent/
│   │           ├── __init__.py
│   │           ├── adapter.py         # AlignmentGraphISDAgent (bridge → core)
│   │           └── config.py          # AblationConfig, HarnessRunConfig
│   └── run_benchmark.py               # thêm case "alignmentgraph-isd" (patch nhỏ)
│
└── harness/                           # package core (độc lập)
    ├── pyproject.toml
    └── src/alignmentgraph_isd/
        ├── __init__.py
        ├── orchestrator.py            # MetaAgent, dynamic task graph
        ├── graph.py                   # AlignmentGraph: G_t = (V_t, E_t)
        ├── agents/                    # các role agent
        │   ├── needs_context.py       # → need/context nodes and edges
        │   ├── objective_design.py    # → objective nodes and prerequisite edges
        │   ├── assessment_design.py   # → assessment/rubric nodes and `measures` edges
        │   ├── activity_material.py   # → activity/material nodes and `supports` edges
        │   ├── implementation_constraint.py  # → constraint nodes and `constrained_by` edges
        │   ├── evaluation_revision.py # → evaluation nodes and `evaluated_by` edges
        │   ├── pedagogical_verifier.py
        │   ├── repair.py              # sửa node/edge vi phạm
        │   └── addie_aggregator.py    # serialize AlignmentGraph → addie_output
        ├── rag/                       # agentic RAG layer
        │   ├── planner.py             # RetrievalPlanner
        │   ├── retriever.py           # vector search + reranking
        │   └── corpus/                # ISD theory, Bloom verbs, templates
        ├── schema/                    # JSON schema contracts
        │   ├── addie_output.json      # schema tương thích ISD-Agent-Bench
        │   └── elements/              # schema từng loại node/edge
        ├── verifier.py                # PedagogicalVerifierAgent logic
        ├── trajectory.py              # TrajectoryLogger
        └── config.py                  # AblationConfig, HarnessConfig
```

## 2. AlignmentGraph — Trạng Thái Làm Việc Trung Tâm

`AlignmentGraph` là trạng thái làm việc chung của harness trong suốt quá trình thiết kế, không chỉ là hình vẽ minh hoạ. Toàn bộ agent đọc và ghi vào graph này thay vì truyền fragments rời nhau.

```
G_t = (V_t, E_t)

V_t = V_objective ∪ V_assessment ∪ V_activity
      ∪ V_material ∪ V_constraint ∪ V_evaluation

E_t = {measures, supports, requires, constrains,
       evaluates, revises, depends_on}
```

Mỗi node lưu một artifact element có schema riêng (objective, rubric item, activity, coding exercise, implementation constraint, evaluation criterion). Mỗi edge lưu relation type, source node, target node, evidence/rationale, verification status và repair history.

`ADDIEOutputAggregator` serialize `G_t` cuối thành schema `addie_output` để benchmark đánh giá. ADDIE là output contract, còn execution state bên trong là graph.

## 3. Adapter cho ISD-Agent-Bench

Benchmark gốc đăng ký agent qua `_get_agent_runner()` trong `run_benchmark.py` và cài agent dưới dạng editable package. Adapter `alignmentgraph-isd` tuân thủ đúng pattern này.

**Cấu trúc adapter (`adapter.py`):**

```python
from alignmentgraph_isd.orchestrator import MetaAgent
from alignmentgraph_isd.config import HarnessRunConfig
from alignmentgraph_isd_agent.config import AblationConfig
from shared.llm import LLMConfig

class AlignmentGraphISDAgent:
    def __init__(self, llm_config: LLMConfig, ablation: AblationConfig | None = None):
        self.llm_config = llm_config
        self.ablation = ablation or AblationConfig()

    def run(self, scenario: dict) -> dict:
        config = HarnessRunConfig.from_ablation(self.ablation, self.llm_config)
        orchestrator = MetaAgent(config)
        result = orchestrator.run(scenario)
        return {
            "addie_output": result.addie_output,
            "trajectory": result.trajectory.to_dict(),
            "metadata": result.metadata,
        }
```

**Patch `run_benchmark.py` (thêm một case):**

```python
elif agent_id == "alignmentgraph-isd":
    from alignmentgraph_isd_agent.adapter import AlignmentGraphISDAgent
    from alignmentgraph_isd_agent.config import AblationConfig
    ablation_key = os.getenv("HARNESS_ABLATION", "full")
    def run_harness(scenario: dict) -> dict:
        agent = AlignmentGraphISDAgent(
            llm_config=llm_config,
            ablation=AblationConfig.from_key(ablation_key),
        )
        return agent.run(scenario)
    return run_harness
```

Cách đăng ký này giữ nguyên benchmark runner, chỉ thêm một nhánh mới. Không sửa code của các agent hiện có.

**Cài đặt:**

```bash
# trong isd-agent-benchmark/
pip install -e agents/alignmentgraph-isd
pip install -e ../../harness   # hoặc khai báo harness như dependency trong pyproject.toml
```

**Chạy thử single scenario:**

```bash
python run_benchmark.py \
  --scenario scenarios/test/scenario_bal_large2_0075.json \
  --agents alignmentgraph-isd \
  --gen-llm-profile openrouter \
  --gen-llm-model anthropic/claude-opus-4-5
```

## 4. Cấu hình Ablation

Toàn bộ ablation được điều khiển bằng `AblationConfig`, một dataclass với các flag boolean. Mỗi flag bypass một thành phần harness cụ thể — bypass (skip) chứ không xoá, để có thể bật lại mà không cần viết lại code.

```python
@dataclass
class AblationConfig:
    use_rag: bool = True           # False → no_rag
    use_verifier: bool = True      # False → no_verifier
    use_repair: bool = True        # False → no_repair
    multi_agent: bool = True       # False → single_agent
    dynamic_graph: bool = True     # False → linear_addie_only

    @classmethod
    def from_key(cls, key: str) -> "AblationConfig":
        presets = {
            "full":              cls(),
            "no_rag":            cls(use_rag=False),
            "no_verifier":       cls(use_verifier=False),
            "no_repair":         cls(use_repair=False),
            "single_agent":      cls(multi_agent=False),
            "linear_addie_only": cls(dynamic_graph=False),
        }
        return presets[key]
```

Mỗi flag tương ứng với một ablation trong proposal (Section 3.3):

| `HARNESS_ABLATION` | Flag bị tắt | Thành phần bị bypass | Mục tiêu đo |
| --- | --- | --- | --- |
| `full` | — | — | proposed method |
| `no_rag` | `use_rag=False` | RetrievalPlanner + ContextPack | tác động của retrieval/context grounding |
| `no_verifier` | `use_verifier=False` | PedagogicalVerifierAgent | lỗi alignment và rubric consistency |
| `no_repair` | `use_repair=False` | specialist repair methods trong từng role agent | giá trị của targeted repair |
| `single_agent` | `multi_agent=False` | role decomposition, AlignmentGraph shared state | giá trị của multi-agent orchestration |
| `linear_addie_only` | `dynamic_graph=False` | dynamic orchestration policy | so sánh với ADDIE sequential |

**Chạy từng ablation variant:**

```bash
HARNESS_ABLATION=full              python run_benchmark.py --agents alignmentgraph-isd ...
HARNESS_ABLATION=no_rag            python run_benchmark.py --agents alignmentgraph-isd ...
HARNESS_ABLATION=no_verifier       python run_benchmark.py --agents alignmentgraph-isd ...
HARNESS_ABLATION=no_repair         python run_benchmark.py --agents alignmentgraph-isd ...
HARNESS_ABLATION=single_agent      python run_benchmark.py --agents alignmentgraph-isd ...
HARNESS_ABLATION=linear_addie_only python run_benchmark.py --agents alignmentgraph-isd ...
```

Mỗi variant tạo run directory riêng theo naming convention `test_benchmark_<model>_<timestamp>/` và có thể so sánh bằng `isd-evaluator compare` của benchmark.

## 5. Phases Triển Khai

| Phase | Mục tiêu | Output kiểm chứng |
| --- | --- | --- |
| **P1 · Skeleton & Contract** | Thiết lập package, schema `addie_output`, `AlignmentGraph` data structure, `AblationConfig`, adapter stub trả hardcoded output | `pytest` schema validation pass; adapter chạy được trong benchmark runner với `--agents alignmentgraph-isd` |
| **P2 · Single-agent baseline** | `single_agent` mode: một agent đọc scenario, sinh toàn bộ graph nodes trong một lần, aggregate thành ADDIE output, không RAG, không verifier | `HARNESS_ABLATION=single_agent` cho kết quả tương đương `baseline` agent; graph có đủ node types |
| **P3 · Multi-agent + AlignmentGraph** | Tách thành 6 role agent, mỗi agent thêm/sửa nodes và edges trực tiếp vào `AlignmentGraph`; `MetaAgent` điều phối theo graph state | Trajectory log đầy đủ agent steps và edge additions; `ImplementationConstraintAgent` có thể push constraint ngược về `ActivityMaterialAgent` |
| **P4 · Schema validation + specialist repair** | JSON schema check từng node/edge sau khi agent ghi; policy route violated element về đúng owner agent để sửa và kích hoạt cascade invalidation | `no_repair` vs `full` cho thấy repair_success_rate, stale cascade events và retry count trong trajectory |
| **P5 · PedagogicalVerifier** | Kiểm tra Bloom alignment, `measures` edge coverage, rubric consistency; trigger specialist repair với target node/edge cụ thể | `no_verifier` vs `full` cho thấy alignment_score delta |
| **P6 · Agentic RAG** | `RetrievalPlanner` decompose query theo ISD task; vector index ISD corpus + Bloom verbs + templates; ContextPack per agent | `no_rag` vs `full` cho thấy phase_coverage và alignment_score delta |
| **P7 · Dynamic orchestration** | `MetaAgent` quyết định bước kế tiếp dựa trên graph state (missing edges, failed nodes) thay vì linear order | `linear_addie_only` vs `full` cho thấy sự khác biệt khi có constraint feedback loop |
| **P8 · Full evaluation run** | Chạy `alignmentgraph-isd` (full + 5 ablation) + 6 baseline agents trên test split; thu thập tất cả metrics | Bảng kết quả đầy đủ cho RQ1 và RQ2 |
| **P9 · Prototype UI** | FastAPI/Streamlit frontend: nhận yêu cầu → gọi harness → hiển thị ADDIE artifact + graph trace + verifier warnings; export JSON + Markdown | 3–5 case study IT/Software Engineering artifact + trace export |

## 6. Invariants Cần Giữ Trong Mọi Phase

- **Output contract không thay đổi.** `adapter.run()` luôn trả về `{addie_output, trajectory, metadata}` đúng schema benchmark, bất kể ablation flag.
- **Ablation bypass, không xoá.** Khi một flag bị tắt, component tương ứng bị skip; code path vẫn tồn tại để bật lại mà không cần viết lại.
- **AlignmentGraph là nguồn sự thật duy nhất.** Mọi agent đọc và ghi vào `G_t`; không truyền fragments rời giữa agents. `ADDIEOutputAggregator` serialize `G_t` cuối, không gộp từng agent output riêng lẻ.
- **Cascade invalidation là policy tường minh.** Khi một owner agent sửa node, `AlignmentGraph.IMPACT_POLICY` đánh dấu stale các node/edge downstream bị ảnh hưởng; policy router sẽ rerun specialist agent tương ứng. Stale edge không được tính là coverage hợp lệ và không được đưa vào alignment evidence cuối.
- **Trajectory ghi ở mọi mode.** Ngay cả `single_agent` và `no_rag` vẫn log đủ `agent_steps`, `node_edits`, `edge_edits`, `llm_calls`, `token_usage`, `latency_ms` để so sánh chi phí.
- **Run manifest bắt buộc.** Mỗi run ghi `manifest.json` gồm `model`, `ablation_key`, `prompt_version`, `commit_hash`, `temperature`, `max_tokens`, `sample_list`, `seed`. Không so sánh hai run có manifest khác nhau trừ khi đó là biến ablation có chủ đích.

## 7. Cascade Invalidation Policy

Targeted repair không chỉ sửa node bị lỗi. Mỗi thay đổi có thể làm downstream artifact mất đồng bộ, nên harness dùng impact matrix để tạo task refresh tiếp theo:

| Node thay đổi | Node bị mark stale |
| --- | --- |
| `needs_context` | `objective`, `assessment`, `activity`, `material`, `constraint`, `evaluation` |
| `objective` | `assessment`, `activity`, `material`, `evaluation` |
| `assessment` | `activity`, `material`, `evaluation` |
| `activity` | `material`, `assessment`, `constraint`, `evaluation` |
| `material` | `activity`, `assessment`, `constraint`, `evaluation` |
| `constraint` | `objective`, `assessment`, `activity`, `material`, `evaluation` |
| `evaluation` | `assessment` |

Luồng xử lý:

1. Specialist agent sửa node thuộc chuyên môn của mình.
2. `AlignmentGraph.invalidate_impacted(...)` mark stale các node/edge theo matrix.
3. `GraphAuditor` xem stale node như graph gap và bỏ qua stale edge khi tính `measures/supports/evaluates`.
4. `HarnessPolicy` route task refresh về agent chuyên môn kế tiếp.
5. `ADDIEOutputAggregator` chỉ dùng fresh edge làm alignment evidence cuối.
