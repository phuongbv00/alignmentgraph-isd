# Thiết kế và triển khai hệ thống — Chương 4

*(Chi tiết từng thành phần — xem phác thảo cấu trúc trong [1_outline.md](1_outline.md) §Chương 4)*

## 4.1 Kiến trúc tổng thể

- Quan hệ cốt lõi: **Agent = Model + Harness** — LLM là pluggable component; Pedagogy Agent Harness là execution environment biến LLM thành Pedagogy Agent.
- Luồng vận hành chính: **IDA Loop** (Instructional Design–Assessment Loop) — giáo viên đánh giá nhóm (UC-AS) → diagnosis tổng hợp StudentGroupProfile → giáo viên thiết kế dạy học phân hoá (UC-ID) → dạy → đánh giá lại → lặp trong phạm vi một môn/khoá học.
- Điểm vào giáo viên: **giao diện chat hội thoại** — giáo viên gõ yêu cầu tự nhiên; Intent Router phân loại; pipeline tương ứng được kích hoạt trong nền; output stream về chat.
- Sơ đồ tổng thể: `[Chat UI] ↔ IPC ↔ [Main Process: Intent Router → UC-ID/UC-AS Pipeline → Course Memory ↔ LLM ↔ Domain Plugin (optional)]`

## 4.2 Intent Router

Thành phần đầu tiên xử lý mọi chat input từ giáo viên. Phân loại input thành một trong năm intent:

| Intent | Ví dụ trigger | Pipeline kích hoạt |
|---|---|---|
| `UC_ID` | "Soạn kế hoạch bài dạy chủ đề X" | UC-ID Pipeline |
| `UC_AS` | "Tạo đề kiểm tra / chấm bài / tạo rubric" | UC-AS Pipeline |
| `UPDATE_PROFILE` | "Nhóm B 10 em hay nhầm push/pop" | Profile update → Course Memory |
| `QUERY` | "Tuần trước dạy đến đâu?" / "Nhóm C đang thế nào?" | Course Memory read → format response |
| `FEEDBACK` | "Chỉnh lại phần hoạt động 2" | Artifact revision → HITL retry |

- Cơ chế phân loại: LLM call nhẹ (classifier prompt) + keyword heuristic fallback.
- Khi input ambiguous: Router hỏi lại một câu ngắn ("Bạn muốn soạn kế hoạch bài dạy hay tạo đề kiểm tra?") trước khi kích hoạt pipeline.

## 4.3 UC-ID Pipeline — Thiết kế dạy học

Input: `{chủ đề, bloom_target, số buổi}` + `student_group_profile` (optional, từ Course Memory hoặc nhập tay).

```
Context Injection
    → [Retrieval] corpus query (scoped theo domain + group readiness)
    → [Generation] kế hoạch bài dạy với Bloom/constructive alignment constraints
    → [Schema Validation] typed schema check
    → [HITL Gate] giáo viên duyệt/chỉnh qua chat
    → [ArtifactLog] lưu vào Course Memory
```

- Nếu có `student_group_profile`: retrieval policy ưu tiên tài liệu phù hợp trình độ nhóm yếu nhất; generation prompt thêm constraint phân hoá hoạt động theo nhóm (A: nâng cao, B+C: bổ trợ).
- Output phân hoá: kế hoạch bài dạy có section riêng cho từng nhóm học sinh.
- HITL: giáo viên có thể chỉnh sửa trực tiếp qua chat hoặc reject kèm lý do → rejection reason feed lại làm constraint retry (targeted repair).

## 4.4 UC-AS Pipeline — Kiểm tra, đánh giá

Input phân theo sub-task:

| Sub-task | Input | Output |
|---|---|---|
| Sinh đề/bài tập | `{topic, difficulty, type}` + optional `student_group_profile` | Đề + đáp án + rubric |
| Xây dựng công cụ đánh giá | `{topic, assessment_type, bloom_target}` | Rubric / ma trận đề / tiêu chí phân mức |
| Chấm bài + feedback | Bài nộp + optional `student_group_profile` | Feedback + misconception label + diagnosis |

```
Context Injection
    → [Generation / Grading]
    → [Domain Verifier] (optional — từ plugin; nếu null → bỏ qua bước này)
    → [Diagnosis Generation] tổng hợp pattern lỗi theo nhóm
    → [Profile Synthesis Pipeline] cập nhật StudentGroupProfile
    → [HITL Gate] giáo viên duyệt
    → [ArtifactLog] lưu vào Course Memory
```

- Khi có `student_group_profile`: feedback nhấn đúng điểm yếu của nhóm; đề bài calibrate độ khó phù hợp nhóm.
- Domain Verifier: nếu plugin loaded → chạy verifier (code verifier / SymPy checker); nếu plugin = null → pipeline tiếp tục mà không verify (null-plugin contract).

## 4.5 Course Memory

Stateful layer duy trì xuyên suốt một môn học/khoá học. Reset khi bắt đầu khoá mới.

```
CourseMemory
├── CourseContext
│   ├── subject, syllabus, chuẩn đầu ra, số buổi
│   └── domain (xác định plugin nào được load)
│
├── StudentGroupProfiles[]
│   ├── group_id, group_name, size
│   ├── readiness_level (beginner / intermediate / advanced)
│   ├── known_misconceptions[]
│   └── last_updated (timestamp + source: manual | synthesized)
│
├── DiagnosisHistory[]
│   ├── round_id, timestamp, uc_as_artifact_id
│   └── group_diagnoses[]: {group_id, error_patterns[], strengths[]}
│
└── ArtifactLog[]
    ├── artifact_id, type (lesson_plan | exam | rubric | feedback)
    ├── status (draft | approved | rejected)
    └── hitl_notes (rejection reason, teacher edits)
```

- Hai nguồn cập nhật `StudentGroupProfiles`: (1) giáo viên nhập tay qua chat → `UPDATE_PROFILE` intent; (2) Profile Synthesis Pipeline sau mỗi vòng UC-AS → đề xuất giáo viên confirm.
- Context Injection tự động đọc và inject profile + DiagnosisHistory (N vòng gần nhất, mặc định N=3) vào prompt mọi task.

## 4.6 Profile Synthesis Pipeline

Chạy tự động sau khi UC-AS sinh diagnosis. Gồm 3 bước:

1. **Parse**: extract structured group-level patterns từ diagnosis output (LLM call với output schema).
2. **Merge**: so sánh với `StudentGroupProfiles` hiện tại; merge theo rule (misconception mới → append; readiness level thay đổi → update nếu confidence > threshold).
3. **Propose**: trình giáo viên summary ngắn qua chat + confirm/edit option (HITL nhẹ — giáo viên có thể gộp nhóm, tách nhóm, điều chỉnh label).

## 4.7 Context Injection

Chạy tự động trước mọi task invocation (UC-ID và UC-AS). Không cần giáo viên nhắc lại ngữ cảnh mỗi lần.

- **Inject vào retrieval policy**: nếu có StudentGroupProfile của nhóm yếu → ưu tiên chunk có metadata `difficulty: basic` hoặc `topic` liên quan misconception đã biết.
- **Inject vào generation prompt**: prepend system context gồm CourseContext summary + StudentGroupProfiles + DiagnosisHistory (N vòng gần nhất).
- **Context budget**: tổng token injected phải nằm trong budget định trước; nếu DiagnosisHistory dài → nén bằng summary (lấy ý tưởng từ ACON — §3.9).

## 4.8 Domain Plugin Interface

Optional layer. Core (§4.3–§4.7) hoạt động đầy đủ khi không có plugin.

Mỗi domain plugin implement interface:

```typescript
interface DomainPlugin {
  domain: string                    // "it" | "math" | ...
  metadataSchema: JSONSchema        // schema cho corpus chunk metadata
  taskSchemas: Record<string, JSONSchema>  // schema cho từng UC-ID/UC-AS output
  retrievalPolicy: RetrievalPolicy  // ưu tiên retrieval theo domain
  verifier?: Verifier               // optional — null nếu domain không có
  errorTaxonomy: ErrorTaxonomy      // bảng phân loại lỗi domain-specific
  feedbackTemplates: FeedbackTemplates
  corpusIngestionPipeline: IngestionPipeline
}
```

**Null-plugin contract**: nếu `verifier` là null hoặc plugin không được load, UC-AS Pipeline bỏ qua bước Domain Verifier và tiếp tục — không ném lỗi, không thay đổi core logic.

**IT plugin**: code verifier chạy test case (pytest / JUnit sandbox), báo compile error / runtime error / test failure → diagnosis chi tiết đến từng dòng code.

**Toán plugin**: SymPy checker verify tính đúng của phép tính và lời giải; structural completeness check (có đủ các bước không).

## 4.9 HITL Governance

Mọi output của UC-ID và UC-AS phải qua HITL Gate trước khi lưu vào ArtifactLog và trước khi Profile Synthesis Pipeline commit update.

- **Approve**: artifact lưu vào ArtifactLog với status `approved`; Profile Synthesis commit update nếu có.
- **Edit**: giáo viên chỉnh sửa trực tiếp qua chat; harness merge edit vào artifact; lưu với status `approved` + ghi lại diff.
- **Reject + lý do**: rejection reason được feed lại làm additional constraint cho targeted repair (retry generation với constraint mới); không retry toàn bộ pipeline — chỉ retry node bị reject.
- **Timeout / skip**: nếu giáo viên không phản hồi sau timeout, artifact ở status `draft` — không được dùng làm input cho vòng IDA tiếp theo cho đến khi approved.
