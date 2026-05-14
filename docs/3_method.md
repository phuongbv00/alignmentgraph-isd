# Chương 3 — Proposed Method: Pedagogy Agent Harness

## 3.1 Kiến trúc tổng thể

- Quan hệ cốt lõi: **Agent = Model + Harness** — LLM là pluggable component; Pedagogy Agent Harness là execution environment biến LLM thành Pedagogy Agent.
- Luồng vận hành chính: **IDA Loop** (Instructional Design–Assessment Loop) — giáo viên đánh giá nhóm (UC-AS) → diagnosis tổng hợp StudentGroupProfile → giáo viên thiết kế dạy học phân hoá (UC-ID) → dạy → đánh giá lại → lặp trong phạm vi một môn/khoá học.
- Điểm vào giáo viên: **giao diện chat hội thoại** — giáo viên gõ yêu cầu tự nhiên; Intent Router phân loại; pipeline tương ứng được kích hoạt trong nền; output stream về chat.
- Sơ đồ tổng thể: `[Chat UI] ↔ IPC ↔ [Main Process: Intent Router → UC-ID/UC-AS Pipeline → Memory (global/workspace/session) ↔ LLM ↔ Domain Plugin (optional)]`

## 3.2 Intent Router

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

## 3.3 UC-ID Pipeline — Thiết kế dạy học

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

## 3.4 UC-AS Pipeline — Kiểm tra, đánh giá

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
- Domain Verifier: nếu plugin được load → chạy verifier; nếu không có plugin → pipeline tiếp tục mà không verify.

## 3.5 Memory Architecture — 3-scope taxonomy

Harness quản lý memory theo ba tầng scope lồng nhau.

### Global scope — cá nhân hoá giáo viên/user

Duy trì xuyên suốt mọi khoá học và phiên làm việc. Không bị reset khi bắt đầu khoá mới.

```
GlobalMemory
├── teacher_id
├── preferences
│   ├── feedback_tone         (formal | encouraging | direct)
│   ├── default_bloom_target  (bloom level ưa dùng khi không chỉ định)
│   ├── difficulty_calibration_style
│   └── preferred_language_register
└── teaching_style_notes[]    (tổng hợp từ HITL history qua nhiều khoá)
```

### Workspace scope — context khoá học/môn học (phục vụ IDA Loop)

Một workspace = một môn học/khoá học cụ thể với tập hợp học viên xác định. Duy trì đến hết khoá, reset khi bắt đầu khoá mới.

```
WorkspaceMemory
├── workspace_id, teacher_id
├── CourseContext
│   ├── subject, syllabus, chuẩn đầu ra, số buổi
│   └── domain          (xác định plugin nào được load)
│
├── StudentGroupProfiles[]
│   ├── group_id, group_name, size
│   ├── readiness_level (beginner | intermediate | advanced)
│   ├── known_misconceptions[]
│   └── last_updated    (timestamp + source: manual | synthesized)
│
├── DiagnosisHistory[]
│   ├── round_id, timestamp, session_id, uc_as_artifact_id
│   └── group_diagnoses[]: {group_id, error_patterns[], strengths[]}
│
└── ArtifactLog[]
    ├── artifact_id, type  (lesson_plan | exam | rubric | feedback)
    ├── session_id         (session sinh ra artifact này)
    ├── status             (draft | approved | rejected)
    └── hitl_notes         (rejection reason, teacher edits)
```

- Hai nguồn cập nhật `StudentGroupProfiles`: (1) giáo viên nhập tay qua chat → `UPDATE_PROFILE` intent; (2) Profile Synthesis Pipeline sau mỗi vòng UC-AS → đề xuất giáo viên confirm.

### Session scope — phiên làm việc (nằm trong workspace)

Ephemeral. Khởi tạo khi giáo viên mở session trong một workspace, kết thúc khi đóng session.

```
SessionMemory
├── session_id, workspace_id, teacher_id
├── conversation_history[]   (toàn bộ chat messages của phiên này)
├── active_task_context      (task đang xử lý: intent, input params, draft output)
└── pending_artifacts[]      (draft chưa HITL approve → chưa commit vào Workspace)
```

**Session commit**: khi session kết thúc — artifact đã HITL-approve → commit vào `WorkspaceMemory.ArtifactLog`; diagnosis đã approve → trigger Profile Synthesis → update `WorkspaceMemory.StudentGroupProfiles`. Session memory bị xoá sau commit; không lẫn context giữa các phiên làm việc khác nhau.

### Context Injection order

Mỗi task invocation nhận context injection theo thứ tự ưu tiên (cao → thấp):
1. `SessionMemory.active_task_context` — task đang làm (ưu tiên cao nhất)
2. `WorkspaceMemory.StudentGroupProfiles` + `DiagnosisHistory` (N vòng gần nhất, mặc định N=3)
3. `WorkspaceMemory.CourseContext`
4. `GlobalMemory.preferences` — tone, style của giáo viên (inject nhẹ vào system prompt)

## 3.6 Profile Synthesis Pipeline

Cơ chế **episodic → semantic consolidation**: chuyển hoá DiagnosisHistory (episodic memory — sự kiện đánh giá cụ thể) thành StudentGroupProfiles (semantic memory — tri thức tổng hợp về đặc điểm nhóm). Chạy tự động sau khi UC-AS sinh diagnosis. Gồm 3 bước:

1. **Parse**: extract structured group-level patterns từ diagnosis output (LLM call với output schema).
2. **Merge**: so sánh với `StudentGroupProfiles` hiện tại; merge theo rule (misconception mới → append; readiness level thay đổi → update nếu confidence > threshold).
3. **Propose**: trình giáo viên summary ngắn qua chat + confirm/edit option (HITL nhẹ — giáo viên có thể gộp nhóm, tách nhóm, điều chỉnh label).

## 3.7 Context Injection

Chạy tự động trước mọi task invocation (UC-ID và UC-AS). Thứ tự inject đã mô tả trong §3.5. Không cần giáo viên nhắc lại ngữ cảnh mỗi lần.

- **Inject vào retrieval policy**: StudentGroupProfiles → ưu tiên chunk phù hợp trình độ nhóm (metadata `difficulty`, `topic` liên quan misconception đã biết trong workspace).
- **Inject vào generation prompt**: system context = CourseContext summary + StudentGroupProfiles + DiagnosisHistory (N vòng gần nhất từ workspace) + teacher preferences (từ global).
- **Context budget**: tổng token injected phải nằm trong budget định trước; nếu DiagnosisHistory dài → nén bằng summary (lấy ý tưởng từ ACON — §2.9). Session conversation history được inject riêng trong slot working memory.

## 3.8 Domain Plugin Interface

Optional layer. Core (§3.3–§3.7) hoạt động đầy đủ khi không có plugin.

Mỗi domain plugin implement interface:

```typescript
interface DomainPlugin {
  domain: string                    // "it" | ...
  metadataSchema: JSONSchema        // schema cho corpus chunk metadata
  taskSchemas: Record<string, JSONSchema>  // schema cho từng UC-ID/UC-AS output
  retrievalPolicy: RetrievalPolicy  // ưu tiên retrieval theo domain
  verifier?: Verifier               // optional — null nếu domain không có
  errorTaxonomy: ErrorTaxonomy      // bảng phân loại lỗi đặc thù lĩnh vực
  feedbackTemplates: FeedbackTemplates
  corpusIngestionPipeline: IngestionPipeline
}
```

Khi không có plugin, UC-AS Pipeline bỏ qua bước Domain Verifier và tiếp tục — không ném lỗi, không thay đổi core logic.

**IT plugin**: code verifier chạy test case (pytest / JUnit sandbox), báo compile error / runtime error / test failure → diagnosis chi tiết đến từng dòng code.

## 3.9 HITL Governance

Mọi output của UC-ID và UC-AS phải qua HITL Gate trước khi lưu vào ArtifactLog và trước khi Profile Synthesis Pipeline commit update.

- **Approve**: artifact lưu vào ArtifactLog với status `approved`; Profile Synthesis commit update nếu có.
- **Edit**: giáo viên chỉnh sửa trực tiếp qua chat; harness merge edit vào artifact; lưu với status `approved` + ghi lại diff.
- **Reject + lý do**: rejection reason được feed lại làm additional constraint cho targeted repair (retry generation với constraint mới); không retry toàn bộ pipeline — chỉ retry node bị reject.
- **Timeout / skip**: nếu giáo viên không phản hồi sau timeout, artifact ở status `draft` — không được dùng làm input cho vòng IDA tiếp theo cho đến khi approved.
