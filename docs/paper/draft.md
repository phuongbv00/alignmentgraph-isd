# AlignmentGraph-ISD: Một alignment-graph harness cho tinh chỉnh có kiểm soát các chương trình đào tạo do LLM agent thiết kế

> **Bản thảo v0.1 (markdown, tiếng Việt)** — dùng để duyệt lập luận trước khi đổ vào template venue (LNCS/IEEE).
> Quy ước: giữ keyword tiếng Anh (alignment, harness, artifact, agent, trajectory...); "chương trình đào tạo" (training program), không dùng "khoá học".
> Placeholder số liệu chưa chạy: `[SỐ LIỆU: chờ run]`. Placeholder citation chưa tra: `[TODO-cite]`.

---

## Abstract

Các hệ LLM agent cho instructional systems design (ISD) hiện chủ yếu tối ưu chất lượng artifact ở lần sinh đầu tiên từ một design brief cố định. Nhưng một chương trình đào tạo trong corporate training cần được tinh chỉnh liên tục theo feedback triển khai và thay đổi công nghệ, đặt người thiết kế trước thế lưỡng nan: sinh lại toàn bộ thì tốn kém và mất phần đã tốt; để model sửa cục bộ mà không có cơ chế kiểm soát thì rủi ro phá vỡ constructive alignment. Bài báo này đề xuất **AlignmentGraph-ISD**, một harness có đặc trưng trung tâm là biểu diễn thiết kế dạy học thành một đồ thị alignment tường minh, có phiên bản; xoay quanh đồ thị đó là các kỹ thuật brief elicitation, multi-agent orchestration, agentic RAG, cascade-scoped revision, pedagogical verification và bộ nhớ đa phiên. Nhờ đó, nhu cầu mơ hồ được cụ thể hoá thành design brief, các thành phần thiết kế được sinh bởi đúng agent chuyên trách trên tri thức miền, mỗi yêu cầu tinh chỉnh chỉ sinh lại đúng phần bị ảnh hưởng, mọi thay đổi được kiểm tra nhất quán sư phạm, và toàn bộ trạng thái thiết kế sống qua nhiều phiên làm việc. Trên ISD-Agent-Bench, hệ thống giữ vị trí nhóm dẫn đầu so với sáu agent qua hai lượt benchmark với hai model khác nhau `[SỐ LIỆU: chờ run — lượt SLM 8–9B]`; thí nghiệm tinh chỉnh đa phiên với bốn điều kiện đối chứng cho `[SỐ LIỆU: chờ run]`. Kết quả cho thấy kiến trúc harness đề xuất là hướng khả thi để LLM agent — kể cả SLM chi phí thấp — hỗ trợ trọn vòng đời cải tiến liên tục của chương trình đào tạo.

**Keywords:** instructional systems design, LLM agent, harness, constructive alignment, multi-agent orchestration, continuous refinement

---

## 1. Introduction

### 1.1. Bối cảnh và vấn đề

Trong các doanh nghiệp phần mềm, đào tạo nội bộ là hoạt động liên tục: chương trình cho nhân viên mới, intern, fresher hoặc kỹ sư chuyển vai được cập nhật theo thay đổi công nghệ, yêu cầu dự án và phản hồi sau từng đợt triển khai. Kinh nghiệm xây dựng và vận hành các chương trình đào tạo như vậy cho thấy hai đặc điểm mà các công cụ hỗ trợ thiết kế hiện nay chưa phản ánh:

**Thứ nhất, design brief không có sẵn.** Bài báo dùng thuật ngữ *instructional design brief* (gọi tắt: *design brief*) theo nghĩa chuẩn trong design research: văn bản khởi đầu một dự án thiết kế, xác định vấn đề cần giải, mục tiêu và các ràng buộc `[TODO-cite: functions of the design brief — Design Society]`; trong ngôn ngữ ISD, nó tương đương với đầu ra của bước needs assessment (instructional goal, đặc điểm người học và bối cảnh, ràng buộc triển khai) và tương ứng khái niệm "learning design brief" trong thực hành thiết kế dạy học. Trong thực tế, yêu cầu này hình thành dần qua một quá trình brainstorm giữa người phụ trách đào tạo và các stakeholder (quản lý dự án, mentor, chính học viên); nhiều khi người thiết kế cũng chưa cụ thể hoá được nhu cầu thực sự trước khi bắt đầu. Một hệ hỗ trợ hữu ích cần tham gia được vào giai đoạn hình thành brief này, không chỉ nhận brief hoàn chỉnh.

**Thứ hai, và quan trọng hơn, thiết kế không dừng ở lần sinh đầu tiên.** Sau triển khai, feedback của học viên và giảng viên, tình huống phát sinh trong bối cảnh thực, và thay đổi công nghệ liên tục tạo ra các yêu cầu tinh chỉnh: thêm một learning objective, siết một rubric, đổi thời lượng, thay hình thức triển khai. Mỗi yêu cầu như vậy khởi động một vòng tinh chỉnh trên chương trình đang có.

Trong khi đó, các nghiên cứu 2024–2026 về LLM agent cho ISD — ISD-Agent-Bench với các agent theo lý thuyết như ReAct-ADDIE, ADDIE-Agent, Dick-Carey-Agent, RPISD-Agent [isdagentbench, yao2023react, branch2009addie, dick1978systematic, tripp1990rapid], EduPlanner [zhang2025eduplanner], LEA `[TODO-cite]` — tập trung vào việc áp dụng lý thuyết ISD và nguyên lý học để nâng chất lượng output trong **một lần sinh** (single-shot design): brief cố định đi vào, draft càng tốt càng tốt đi ra. Bản thân ISD-Agent-Bench cũng chỉ đánh giá một vòng thiết kế, không đo quá trình lặp dài hạn với người thiết kế.

### 1.2. Thế lưỡng nan của vòng tinh chỉnh

Khi phải xử lý một yêu cầu tinh chỉnh bằng các kiến trúc hiện có, người thiết kế chỉ có hai lựa chọn, và cả hai đều có vấn đề:

1. **Sinh lại toàn bộ** (full regeneration): đưa brief cập nhật vào và tạo lại cả chương trình. Cách này tốn token/thời gian tỷ lệ với cả chương trình thay vì với độ lớn của thay đổi, và — nghiêm trọng hơn về mặt chất lượng — không có cách nào giữ lại những phần đã được rà soát, chỉnh sửa và kiểm chứng qua các vòng trước.
2. **Sửa cục bộ theo yêu cầu** (targeted tuning): prompt cho model "đây là thiết kế cũ, hãy sửa X". Cách này rẻ hơn, nhưng nếu không có cơ chế kiểm soát thì không có gì đảm bảo phần sửa vẫn nhất quán với phần còn lại: một objective mới thêm vào có thể không được assessment nào đo, một rubric bị siết có thể lệch khỏi hoạt động đang có — tức là phá vỡ **constructive alignment** [biggs1996enhancing], nguyên lý nền tảng rằng objectives, activities và assessment phải ăn khớp với nhau. Rủi ro này không nhìn thấy được ở mức prompt, vì mối quan hệ giữa các thành phần thiết kế chỉ tồn tại ngầm trong văn bản.

Gốc rễ của thế lưỡng nan là **cấu trúc**: các kiến trúc hiện có không biểu diễn mối quan hệ alignment giữa các thành phần thiết kế thành trạng thái tường minh có thể truy vết. Không có trạng thái đó thì không thể trả lời "thay đổi này ảnh hưởng tới đâu", và do đó không thể sửa có mục tiêu một cách an toàn.

### 1.3. Tính cấp thiết

Ba yếu tố hội tụ khiến bài toán này cần được giải quyết ngay, thay vì để như một hạn chế "sẽ xử lý sau" của các hệ sinh nội dung:

1. **Bài toán bảo trì đang tích tụ trong hiện tại.** LLM đã đủ mạnh để đảm đương gần trọn pipeline ISD, nên các doanh nghiệp *đang* dùng chúng để sinh chương trình đào tạo ở quy mô ngày càng lớn. Mỗi chương trình được sinh ra hôm nay là một nghĩa vụ tinh chỉnh trong tương lai; càng trì hoãn việc có cơ chế tinh chỉnh có kiểm soát, khối lượng artifact phải bảo trì bằng hai cách tồi (sinh lại toàn bộ / sửa tay không kiểm soát) càng phình to.
2. **Suy giảm alignment là lỗi tích luỹ và không nhìn thấy được.** Khác với lỗi cú pháp hay schema, một chương trình bị phá constructive alignment vẫn "trông ổn" từng phần: chỉ khi triển khai mới lộ ra học viên được dạy một đằng, được đánh giá một nẻo. Không giải quyết, mỗi vòng sửa thủ công là một lần gieo lỗi ngầm vào chất lượng đào tạo — chi phí phát hiện muộn cao hơn nhiều chi phí phòng ngừa bằng cơ chế kiểm soát.
3. **Cửa sổ dịch chuyển giá trị sang harness đang mở.** Khi năng lực model nền bão hoà trên nhiều benchmark [deveci2025ouroboros, shukla2025scalingwall], khác biệt chất lượng của hệ agent phụ thuộc ngày càng nhiều vào lớp **harness** bao quanh model, và tác động của harness lớn nhất ở model nhỏ [cho2026harness]. Làn sóng doanh nghiệp chuyển sang SLM để tối ưu chi phí vận hành khuếch đại trực tiếp nhu cầu: model càng nhỏ càng cần cơ chế kiểm tra–sửa lỗi–khoanh vùng bên ngoài bù lại. Nghiên cứu harness cho ISD vì vậy đúng thời điểm cả về khoa học (khoảng trống cấu trúc chưa ai lấp) lẫn thực tiễn (điều kiện áp dụng đã chín).

### 1.4. Mục tiêu nghiên cứu

**Mục tiêu tổng quát:** Xây dựng và kiểm chứng thực nghiệm một harness cho LLM agent trong đó alignment giữa các thành phần thiết kế dạy học được biểu diễn thành trạng thái tường minh, sao cho một chương trình đào tạo trong bối cảnh corporate training có thể được **tinh chỉnh qua nhiều phiên một cách có kiểm soát** — sửa đúng phần liên quan, với chi phí tỷ lệ với thay đổi, mà không làm suy giảm constructive alignment — trong khi vẫn giữ chất lượng lần sinh đầu cạnh tranh với các agent hiện có.

Mục tiêu tổng quát được cụ thể hoá thành năm mục tiêu:

- **O1.** Hình thức hoá alignment thành cấu trúc dữ liệu hạng nhất: alignment graph với node artifact, edge quan hệ có kiểu (`measures`/`supports`/`evaluates`) và impact policy xác định phạm vi ảnh hưởng của mỗi loại thay đổi.
- **O2.** Thiết kế cơ chế tinh chỉnh giải thế lưỡng nan: tuning entrypoint + cascade-scoped revision (cascade invalidation + targeted repair) dưới sự kiểm soát của pedagogical verifier, vận hành trên graph có phiên bản và bộ nhớ đa phiên.
- **O3.** Kiểm chứng chất lượng lần sinh đầu: tích hợp harness như một agent trong ISD-Agent-Bench và so sánh với sáu agent hiện có trên nhiều model, gồm cả SLM (→ RQ1).
- **O4.** Kiểm chứng hiệu quả tinh chỉnh: thao tác hoá "tinh chỉnh hiệu quả" thành bốn process metric và đo trên giao thức bốn điều kiện đối chứng cross-agent phủ cả hai sừng của thế lưỡng nan (→ RQ2).
- **O5.** Minh hoạ tính ứng dụng trong bối cảnh doanh nghiệp: case study IT/Software Engineering với workflow trọn vẹn từ hình thành brief (elicitation) qua sinh chương trình (kèm agentic RAG theo domain) đến các phiên tinh chỉnh.

O1–O2 là mục tiêu *xây dựng* (design & development theo design science research), O3–O4 là mục tiêu *kiểm chứng* tương ứng với hai câu hỏi nghiên cứu, O5 là mục tiêu *ứng dụng*.

### 1.5. Hướng tiếp cận và đóng góp

Nghiên cứu này theo tiếp cận **design science research**: từ vấn đề thực tiễn trên, rút ra yêu cầu thiết kế cho từng module (trình bày theo khuôn bài toán → lý do → đặc tả ở Mục 3), xây dựng artifact là **AlignmentGraph-ISD** — một alignment-graph harness cho ISD agent theo công thức *Agent = Harness + Model* — và đánh giá thực nghiệm theo hai câu hỏi nghiên cứu:

- **RQ1** (chất lượng lần sinh đầu): Trên ISD-Agent-Bench, AlignmentGraph-ISD cải thiện chất lượng artifact như thế nào so với các agent hiện có?
- **RQ2** (hiệu quả tinh chỉnh): Trong vòng tinh chỉnh đa phiên, cơ chế alignment-graph có cho phép sửa đúng phần liên quan với chi phí thấp hơn sinh lại toàn bộ mà không làm suy giảm alignment, so với cả hai lựa chọn của thế lưỡng nan khi thực hiện bằng agent baseline mạnh nhất?

Đóng góp chính:

1. **AlignmentGraph-ISD**: harness biểu diễn artifact thiết kế và quan hệ alignment (`measures`/`supports`/`evaluates`) thành đồ thị tường minh có phiên bản, với cascade-scoped revision (cascade invalidation theo impact policy + targeted repair), pedagogical verifier, four-layer memory, multi-agent orchestration động, brief elicitation và agentic RAG (Mục 3).
2. **Tuning entrypoint và giao thức đo tinh chỉnh đa phiên**: thao tác hoá "tinh chỉnh hiệu quả" thành bốn process metric (cascade scope, edit locality, cost per tuning round, alignment preservation) đo trên bốn điều kiện đối chứng cross-agent (Mục 5.1).
3. **Bằng chứng thực nghiệm** trên ISD-Agent-Bench (hai lượt, hai model) và trên thí nghiệm tinh chỉnh trong miền IT/Software Engineering, cùng một case study minh hoạ workflow thực tế gồm cả giai đoạn hình thành brief (Mục 4–5).

## 2. Related Work

*Cách tổ chức: mỗi tiểu mục là một mảnh của gap; kết mỗi tiểu mục bằng phần còn thiếu.*

### 2.1. LLM agent cho ISD: tối ưu chất lượng một lần sinh

Các hệ thống gần nhất với công trình này áp dụng lý thuyết ISD vào kiến trúc agent. ISD-Agent-Bench [isdagentbench] hiện thực bốn agent theo lý thuyết: ReAct-ADDIE (vòng ReAct trên ISD tool [yao2023react]), ADDIE-Agent (StateGraph tuyến tính năm pha [branch2009addie]), Dick-Carey-Agent (systems approach với formative-evaluation loop [dick1978systematic]) và RPISD-Agent (rapid prototyping [tripp1990rapid]). EduPlanner [zhang2025eduplanner] dùng multi-agent generate-evaluate-optimize; LessonPlanner [lessonplanner2024] và các nghiên cứu sinh giáo án bằng GPT-4 [hu2024teachingplan] nâng chất lượng một artifact đơn lẻ; LearnLM [learnlm2024] tối ưu model cho tác vụ sư phạm; LEA `[TODO-cite]` *(bổ sung sau khi tra citation)*.

Điểm chung: tất cả nhận brief cố định và tối ưu draft đầu ra của **một vòng thiết kế**. Ngay cả các kiến trúc có vòng lặp nội bộ (Dick-Carey, EduPlanner) cũng lặp *bên trong* một lần sinh để nâng chất lượng draft, không duy trì trạng thái thiết kế *giữa các phiên làm việc* để phục vụ chỉnh sửa về sau. **Còn thiếu:** một kiến trúc coi chương trình đào tạo là living artifact được tinh chỉnh qua nhiều phiên.

### 2.2. Benchmark và đánh giá: đo một vòng thiết kế

OpenLearnLM [openlearnlm2026], EduBench [edubench2025], MathTutorBench [mathtutorbench2025], TutorBench [tutorbench2025] đánh giá năng lực giáo dục của model ở cấp tác vụ đơn lẻ. ISD-Agent-Bench [isdagentbench] tiến xa hơn khi chấm đồng thời chất lượng artifact theo rubric ADDIE và chất lượng trajectory của quá trình agent — nhưng mỗi scenario vẫn là một lượt thiết kế độc lập từ đầu. **Còn thiếu:** phương pháp và metric đánh giá *quá trình tinh chỉnh* — một yêu cầu tinh chỉnh được khoanh vùng ra sao, tốn bao nhiêu, alignment có được bảo toàn không. (Công trình này đề xuất bốn process metric cho đúng khoảng thiếu đó, dùng ISD-Agent-Bench cho RQ1 và mở rộng giao thức đo cho RQ2.)

### 2.3. Kiểm soát nhất quán trong hệ sinh đa artifact

Về lý thuyết, constructive alignment [biggs1996enhancing] định nghĩa tiêu chuẩn nhất quán giữa objectives–activities–assessment; systems approach [dick1978systematic] biện minh cho vòng revision có hệ thống. Về kỹ thuật, các cơ chế verifier/self-repair và agentic memory trong hệ agent tổng quát `[TODO-cite: chọn 1-2 công trình verifier/self-refine + agentic memory]` cho thấy giá trị của kiểm tra và sửa lỗi bên ngoài model — giá trị này càng lớn khi model nền bão hoà và khi dùng model nhỏ [cho2026harness, deveci2025ouroboros, shukla2025scalingwall]. Tuy nhiên, trong các hệ ISD hiện có, alignment chỉ được *khuyến khích* qua prompt hoặc *chấm* sau khi sinh, chứ chưa được biểu diễn thành **trạng thái hạng nhất** — một cấu trúc dữ liệu mà hệ thống có thể kiểm tra từng liên kết, đánh dấu phần bị ảnh hưởng khi có thay đổi, và lan truyền việc sửa một cách có kiểm soát. **Còn thiếu:** chính cấu trúc đó.

### 2.4. Tổng hợp gap

Ghép ba mảnh trên: các hệ ISD agent hiện có tối ưu một lần sinh (2.1), được đánh giá bằng benchmark một vòng (2.2), và không có biểu diễn tường minh cho alignment để kiểm soát thay đổi (2.3). Hệ quả là thế lưỡng nan ở Mục 1.2 chưa có lời giải: người thiết kế hoặc trả chi phí sinh lại toàn bộ, hoặc chấp nhận rủi ro phá alignment khi sửa cục bộ. Công trình này lấp khoảng trống bằng cách đặt alignment làm trạng thái đồ thị hạng nhất của harness và xây cơ chế tinh chỉnh có kiểm soát xung quanh nó.

## 3. Methodology

### 3.1. Tổng quan

Từ phân tích ở Mục 1, phương pháp đề xuất cần hỗ trợ trọn vòng đời của một chương trình đào tạo: cụ thể hoá nhu cầu mơ hồ thành design brief, sinh bản thiết kế đầy đủ từ brief đó, và biến mỗi yêu cầu tinh chỉnh về sau thành một phiên bản mới của thiết kế mà không phá vỡ constructive alignment. Quan sát dẫn dắt thiết kế là: những gì vòng đời này đòi hỏi — trạng thái bền vững, kiểm soát chất lượng, khoanh vùng thay đổi, điều phối chuyên môn — đều không phải năng lực của model mà là trách nhiệm của môi trường thực thi bao quanh model. AlignmentGraph-ISD vì vậy dồn toàn bộ các trách nhiệm đó vào một harness, để model chỉ giữ vai trò sinh nội dung và suy luận bên trong môi trường ấy; một agent hoàn chỉnh là kết hợp của hai phần (*Agent = Harness + Model*), và mọi thiết kế trong mục này đều thuộc về phần harness — độc lập với việc model là frontier LLM hay SLM chi phí thấp.

Trung tâm của harness là một **alignment graph có phiên bản** (Mục 3.2): mọi module còn lại đọc hoặc ghi trạng thái này. Một chương trình đào tạo đi qua harness theo luồng sau `[HÌNH: kiến trúc tổng quan]`: nhu cầu của người thiết kế được cụ thể hoá thành design brief qua một vòng hội thoại (brief elicitation, Mục 3.6); từ brief, orchestrator giao việc cho các specialist agent xây dựng graph (Mục 3.3), và khi thiếu ngữ liệu miền, chính specialist quyết định truy xuất từ các retrieval agent cắm thêm (agentic RAG, Mục 3.7); mỗi lần graph thay đổi — dù do sinh mới, sửa lỗi hay tuning request — thay đổi đều được kiểm tra và lan truyền có kiểm soát (pedagogical verification và cascade-scoped revision, Mục 3.4); kết quả mỗi phiên được commit thành một phiên bản trong bộ nhớ đa phiên (four-layer memory, Mục 3.5), làm điểm xuất phát cho phiên kế tiếp. Mọi module đều điều khiển được qua cấu hình; phạm vi bật/tắt trong từng thí nghiệm được nêu ở Mục 5.1.

### 3.2. Alignment graph

Gốc rễ của thế lưỡng nan ở Mục 1.2 nằm ở chỗ mối quan hệ giữa các thành phần thiết kế chỉ tồn tại ngầm trong văn bản: người đọc có thể *cảm nhận* một assessment đang đo một objective, nhưng hệ thống không có cách nào kiểm tra điều đó, càng không thể trả lời "thay đổi này ảnh hưởng tới đâu". Muốn tinh chỉnh có kiểm soát, alignment phải trở thành *dữ liệu* — kiểm tra được từng liên kết, đánh dấu được phần bị ảnh hưởng. AlignmentGraph-ISD vì vậy hiện thực hoá constructive alignment [biggs1996enhancing] thành một cấu trúc dữ liệu tường minh: tại mỗi bước $t$, trạng thái thiết kế là đồ thị $G_t = (V_t, E_t)$, với tập đỉnh phủ đủ artifact của năm pha ADDIE:

$$V_t = V_{\text{needs\_context}} \cup V_{\text{objective}} \cup V_{\text{assessment}} \cup V_{\text{activity}} \cup V_{\text{material}} \cup V_{\text{implementation\_plan}} \cup V_{\text{evaluation}}$$

Tập cạnh được giữ tối thiểu, gồm ba quan hệ nhiều-nhiều lấy `objective` làm tâm:

$$E_t = E_{\text{measures}} \cup E_{\text{supports}} \cup E_{\text{evaluates}}, \quad E_{\text{measures}} \subseteq V_{\text{assessment}} \times V_{\text{objective}}, \; E_{\text{supports}} \subseteq V_{\text{activity}} \times V_{\text{objective}}, \; E_{\text{evaluates}} \subseteq V_{\text{evaluation}} \times V_{\text{objective}}$$

Một objective được coi là aligned khi và chỉ khi có ít nhất một assessment đo nó, một activity hỗ trợ nó và một evaluation đánh giá nó:

$$\text{aligned}(o) \iff \big(\exists a: (a,o) \in E_{\text{measures}}\big) \wedge \big(\exists x: (x,o) \in E_{\text{supports}}\big) \wedge \big(\exists e: (e,o) \in E_{\text{evaluates}}\big), \quad \forall o \in V_{\text{objective}}$$

Chỉ `objective` được tách thành element node theo từng learning outcome (`objective:LO-*`) vì constructive alignment cần kiểm ở cấp từng mục tiêu; các loại đỉnh khác giữ ở mức section. Các loại node không tham gia alignment edge tĩnh (needs context, implementation plan, material) tác động đến thiết kế qua toán tử cascade dựa trên `IMPACT_POLICY` — ánh xạ mỗi loại node sang tập loại downstream phụ thuộc nó:

$$\text{cascade}(n) = \{\, m \in V_t : \text{type}(m) \in \text{IMPACT\_POLICY}(\text{type}(n)) \,\} \mapsto \text{stale}$$

Mỗi node mang trạng thái `stale` và `repair_history`, mỗi edge mang trạng thái `verified` — chính các trường trạng thái này biến alignment thành thứ đo được trong các thí nghiệm ở Mục 5.

### 3.3. Multi-agent orchestration và workflow động

Có được trạng thái tường minh rồi, câu hỏi kế tiếp là ai vận hành nó và theo trình tự nào. Hai đặc điểm của bài toán loại trừ pipeline cố định: mỗi loại artifact ISD đòi hỏi chuyên môn khác nhau — phân tích nhu cầu, thiết kế rubric và lập kế hoạch triển khai là ba kỹ năng khác hẳn nhau — và trong vòng tinh chỉnh, phần việc cần làm phụ thuộc vào *trạng thái hiện tại* của thiết kế, điều mà một chuỗi ADDIE chạy cứng không diễn đạt được ("chỉ sinh lại phần stale" không phải là một bước trong pipeline nào). Việc điều phối do đó phải đọc trạng thái graph để quyết định việc kế tiếp, và mỗi việc phải được giao đúng chuyên môn với phạm vi ghi giới hạn.

Cụ thể, mỗi ISD concern có một specialist agent (needs context, objective design, assessment design, activity & material, implementation plan, evaluation & revision), cộng pedagogical verifier và ADDIE aggregator. `MetaAgent` duy trì một dynamic task graph $T_t = \{\tau_1, \dots, \tau_k\}$ với mỗi tác vụ $\tau = (\mathrm{type}, \mathrm{owner}, \mathrm{prio}, \mathrm{deps})$; tại mỗi bước, policy $\pi$ của `ISDTaskPlanner` chọn tác vụ khả thi kế tiếp theo trạng thái graph, và agent sở hữu thực thi nó:

$$\tau^* = \pi(G_t, T_t), \qquad G_{t+1} = A_{\mathrm{owner}(\tau^*)}\big(G_t,\, c_{\tau^*}\big)$$

Mỗi agent là một toán tử cập nhật graph có phạm vi ghi giới hạn theo chuyên môn:

$$A_i : (G_t, c) \mapsto G_{t+1}, \qquad \Delta(G_t, G_{t+1}) \subseteq V^{(i)} \cup E^{(i)}$$

(ví dụ agent assessment chỉ ghi node `assessment` và cạnh `measures`). Planner chỉ tạo task cho node thiếu/stale/không hợp lệ — một graph hoàn chỉnh không stale sinh ra 0 task, nên chi phí một phiên tỷ lệ với kích thước tập stale chứ không với cả chương trình. ADDIE chỉ là output contract để tương thích benchmark, không phải ràng buộc thứ tự thực thi.

### 3.4. Pedagogical verification và cascade-scoped revision

Sừng thứ hai của thế lưỡng nan — sửa cục bộ thì phá alignment — xuất phát từ hai thiếu hụt: vi phạm alignment không được phát hiện, và ảnh hưởng dây chuyền của thay đổi không được xử lý. Lời giải vì vậy phải là một vòng khép kín — phát hiện vi phạm, giao đúng chuyên môn sửa, lan truyền ảnh hưởng, kiểm tra lại — về bản chất chính là vòng formative evaluation–revision trong systems approach của Dick và Carey [dick1978systematic], được tự động hoá trên cấu trúc graph.

Trong harness, sau mỗi lượt sinh hoặc sửa, hai lớp kiểm tra chạy độc lập: schema validation (JSON, required field, kiểu, ID) và pedagogical verification với bảy loại ràng buộc (coverage, Bloom-verb, activity support, rubric consistency, feasibility, actionability, evaluation alignment). Gọi $\Omega_t = \mathcal{V}(G_t)$ là tập vi phạm phát hiện trên $G_t$, mỗi vi phạm $\omega = (\mathrm{type}, x)$; hàm $\mathrm{owner}(\cdot)$ route vi phạm về agent chuyên môn. Một lượt revision và điều kiện dừng:

$$G_{t+1} = \mathrm{cascade}\Big(A_{\mathrm{owner}(\mathrm{type}(\omega))}\big(G_t,\, \omega\big)\Big), \; \omega \in \Omega_t; \qquad \text{dừng khi } \Omega_t = \emptyset \;\lor\; t \geq B$$

với $B$ là ngân sách retry: vòng lặp hoặc hội tụ về điểm bất động không còn vi phạm, hoặc dừng có kiểm soát và ghi rõ trong trajectory. Một phiên tinh chỉnh đi vào cùng đường này qua **tuning entrypoint**: tuning request $r$ (node đích + yêu cầu bằng ngôn ngữ tự nhiên) đánh dấu node đích stale, áp $\mathrm{cascade}(\cdot)$ để khoanh vùng, rồi để vòng trên sinh lại đúng tập stale. Cặp cơ chế "invalidation xác định phạm vi + sinh lại đúng trong phạm vi" được gọi chung là **cascade-scoped revision** — "revision" theo nghĩa của systems approach, bao trùm cả sửa lỗi do verifier phát hiện lẫn tinh chỉnh theo yêu cầu người dùng.

### 3.5. Four-layer memory và vòng đời phiên

Các cơ chế trên mới chỉ bảo đảm một phiên làm việc nhất quán; trong khi đó vòng đời ở Mục 1.1 kéo dài qua nhiều phiên, còn model thì stateless — một lượt chạy LLM chỉ thấy context của chính nó. Nếu không có trạng thái bền vững, mọi phiên tinh chỉnh đều thoái hoá thành sinh lại từ đầu, tức quay về đúng sừng thứ nhất của thế lưỡng nan. Harness vì vậy tổ chức bộ nhớ thành bộ bốn $M = (M_{\mathrm{w}}, M_{\mathrm{s}}, M_{\mathrm{e}}, M_{\mathrm{p}})$, phân theo vòng đời của thông tin: *working memory* giữ trạng thái phiên đang mở (hỗ trợ resume), *semantic memory* giữ tri thức ổn định (ADDIE, Bloom, rubric template), *episodic memory* giữ lịch sử session và repair case, *procedural memory* giữ policy đã version hoá như `IMPACT_POLICY`. Trên một chương trình đào tạo, vòng đời là chuỗi phiên bản graph đã commit (chỉ số trên $G^{(v)}$ phân biệt với chỉ số dưới $G_t$ trong một phiên):

$$G^{(1)} = \mathrm{init}(b), \qquad G^{(v+1)} = \mathrm{commit}\Big(\mathrm{cascade}\big(\mathrm{apply}(G^{(v)}, r_v)\big)\Big)$$

với $b$ là design brief ban đầu và $r_v$ là tuning request của phiên thứ $v{+}1$. Chính chuỗi này là đối tượng mà bốn process metric của RQ2 đo trên đó; một lượt benchmark RQ1 là trường hợp đặc biệt chỉ gồm $G^{(1)}$.

### 3.6. Brief elicitation

Toàn bộ chuỗi phiên ở trên khởi động từ một design brief — nhưng như Mục 1.1 đã chỉ ra, brief không có sẵn: nhu cầu hình thành qua brainstorm với stakeholder, và người thiết kế thường chưa cụ thể hoá được nó khi bắt đầu. Một hệ chỉ nhận brief hoàn chỉnh bỏ rơi người dùng ở đúng giai đoạn cần hỗ trợ. Vì giai đoạn hình thành brief là hội thoại human-in-the-loop nhiều lượt — khác về bản chất với vòng chạy thiết kế vốn là một lượt trọn vẹn trên brief đã chốt — nó được tách thành một module đứng trước design workflow thay vì nhúng vào trong đó. Elicitation agent duy trì hội thoại $h$; tại mỗi lượt với input người dùng $u$, nó trả về hoặc câu hỏi làm rõ kế tiếp hoặc một draft brief:

$$\varepsilon(h, u) \in \{\, \mathrm{ask}(q), \; \mathrm{propose}(\hat{b}) \,\}$$

Chỉ khi người dùng approve draft, $b := \hat{b}$ và phiên init $G^{(1)} = \mathrm{init}(b)$ khởi động theo chuỗi phiên ở Mục 3.5; transcript hội thoại được lưu vào working memory để phiên thiết kế nối tiếp cùng ngữ cảnh. Việc giới hạn đầu ra ở hai hành động (hỏi tiếp / đề xuất draft) giữ vòng lặp hội tụ và giữ quyền quyết định cuối ở người thiết kế.

### 3.7. Agentic RAG

Còn lại vấn đề tri thức miền: một agent tổng quát khó nắm quy ước riêng của từng miền — rubric nội bộ, template bài tập, chuẩn code review — chỉ qua system prompt, nhưng nhúng cứng tri thức miền vào prompt lại phá tính tổng quát của harness. Mâu thuẫn này được giải bằng cách làm cho tri thức miền *cắm thêm được*: mỗi miền được đóng gói thành một **retrieval agent** gồm ba thành phần do bên triển khai cung cấp — corpus, system prompt mô tả corpus giỏi trả lời gì, và các tool thao tác trên corpus đó. Với registry $R = \{s_1, \dots, s_m\}$, mở rộng sang miền mới chỉ là $R \leftarrow R \cup \{s_{m+1}\}$, không đổi prompt hay core harness — cơ sở cho giả định chuyển miền thảo luận ở Mục 6.

Tính chất *agentic* nằm ở hai tầng quyết định, đều thuộc về agent chứ không phải pipeline cố định. Ở tầng sử dụng, việc truy xuất là một **tool theo yêu cầu của specialist**: không có bước retrieval nào chạy sẵn ở đầu phiên; trong khi thực thi tác vụ $\tau$, chính specialist $A_i$ — bên duy nhất biết ngữ liệu đang thiếu gì — ra quyết định

$$\delta_i(\tau, c) \;\in\; \{\varnothing\} \;\cup\; \big(2^R \times \{\text{single}, \text{sequential}, \text{parallel}\} \times Q\big)$$

tức hoặc bỏ qua ($\varnothing$ — truy xuất tốn thời gian và token nên mặc định là không), hoặc chọn tập retrieval agent, chiến lược thực thi và câu truy vấn $q \in Q$ cho từng agent; chiến lược được gợi ý mặc định theo loại tác vụ ADDIE (các tác vụ phân tích/sáng tạo diện rộng thiên về parallel, các tác vụ thiết kế phạm vi hẹp thiên về single) nhưng quyền quyết định cuối thuộc specialist. Ở tầng thực thi, mỗi retrieval agent được chọn tự vận hành một vòng tool-use có giới hạn trên corpus của nó để trả về đúng ngữ liệu được hỏi. Toàn bộ kế hoạch chạy trong một **retrieval sandbox**: lỗi của một retrieval agent bị cô lập (không đổ phiên thiết kế), ngân sách tool-call và kích thước kết quả bị chặn trên, và retrieval agent chỉ nhận bản sao truy vấn — không chạm graph hay memory. Context pack của tác vụ vì vậy trở thành:

$$c_\tau = \rho(b) \;\cup\; \gamma(G_t) \;\cup\; \mu(M) \;\cup\; \mathrm{rag}\big(\delta_i(\tau, c)\big), \qquad \mathrm{rag}(\varnothing) = \varnothing$$

trong đó $\rho(b)$ là context prep từ brief, $\gamma(G_t)$ là graph-context retrieval, $\mu(M)$ là memory retrieval — hai cơ chế sau luôn bật và tách biệt với RAG. Mỗi quyết định $\delta_i$ cùng kết quả thực thi được ghi vào trajectory, nên hành vi truy xuất của hệ cũng là dữ liệu quan sát được trong case study.

## 4. Case study: IT/Software Engineering ISD prototype

Đánh giá benchmark (Mục 5) xử lý mỗi scenario như một lượt chạy độc lập — phù hợp để so sánh chất lượng giữa các agent, nhưng không phản ánh hai đặc điểm của bài toán ở Mục 1.1: chương trình đào tạo thật được tinh chỉnh qua nhiều phiên, và mỗi miền có tài liệu, quy ước riêng. Case study lấp khoảng đó bằng một ứng dụng thực tế trong chính bối cảnh doanh nghiệp của nhóm nghiên cứu: đào tạo nội bộ IT/Software Engineering cho nhân viên mới, intern và fresher.

**Kiến trúc ứng dụng và vòng đời phiên.** Ứng dụng bọc quanh core harness một lớp quản lý phiên, cho phép một alignment graph tồn tại lâu dài như *living artifact* cấp chương trình đào tạo: `training_program_id` làm khoá bền vững của graph, `session_id` (tuỳ chọn) để tiếp tục một phiên dang dở. Phiên đầu (`init`) tạo $G^{(1)}$; mỗi phiên sau (`tuning`) tải phiên bản mới nhất, áp tuning request và commit $G^{(v+1)}$ đúng theo chuỗi phiên ở Mục 3.5 — không cần cơ chế đo mới, vì trajectory, cascade event, repair history và graph version diff đã được harness ghi sẵn.

**Instantiation cho miền IT/Software Engineering.** Ba chương trình đào tạo đại diện được xây dựng: *Java/OOP cho fresher* (3 ngày, hybrid), *Software Testing* (2 ngày, instructor-led) và *Git/Agile mini-project* (2 ngày, cho thành viên mới vào dự án). Mỗi chuyên đề được đóng gói thành một retrieval agent theo đúng khuôn plug-and-play của Mục 3.7 — corpus (rubric mẫu 0–4, quy ước đề bài và starter repository, checklist SOLID/code review, quy ước PR và sprint simulation), system prompt mô tả phạm vi corpus, và bộ tool tra cứu chuẩn — rồi đăng ký vào registry $R$. Workflow trọn vẹn được minh hoạ từ đầu chuỗi: một yêu cầu mơ hồ ("cần đào tạo OOP cho fresher trước khi vào dự án") đi qua elicitation (Mục 3.6) thành design brief được approve, phiên init sinh $G^{(1)}$ với tri thức miền từ corpus, rồi các phiên tuning xử lý yêu cầu phát sinh sau triển khai (thêm objective, siết rubric, đổi thời lượng, chuyển hình thức).

Case study đồng thời là **giá đỡ của thí nghiệm RQ2**: 8 tuning request được thiết kế trên ba chương trình này, trải đều phổ `IMPACT_POLICY` từ hẹp nhất (evaluation) đến rộng nhất (needs context), để cascade scope kỳ vọng biến thiên thay vì phẳng; giao thức đo và bốn điều kiện đối chứng trình bày ở Mục 5.1.

## 5. Experiments

### 5.1. Experimental Setup

**RQ1 — benchmark một lần sinh.** ISD-Agent-Bench [isdagentbench]: scenario tổng hợp theo hai trục Context × ISD, evaluator chấm rubric ADDIE 100 điểm (33 sub-step → 13 item → 5 pha) + trajectory score, multi-judge (GPT + Gemini) để giảm self-preference. AlignmentGraph-ISD tích hợp như agent thứ bảy, cùng input/output schema. So sánh với sáu agent: baseline (single-prompt), react-isd (ReAct-ADDIE), addie-agent, dick-carey-agent, rpisd-agent, eduplanner. Hai lượt: subset `test_30` (30/1202 scenario, stratified 10 domain × 3 difficulty, agent model Gemma-4-26B-A4B) và `test_90` (90 scenario, lồng nhau, agent model DeepSeek-v4-flash-nitro). Để công bằng với các baseline, RQ1 chạy harness ở cấu hình benchmark: elicitation không áp dụng (scenario cấp sẵn brief cố định) và external-corpus RAG tắt (không agent nào được truy cập corpus ngoài). Mỗi lượt có run manifest (model, judge, prompt version, commit, seed, decoding config) để tái lập. `[SỐ LIỆU: chờ run — lượt bổ sung trên SLM 8–9B (dự kiến Qwen3.5-9B) cho cả 7 agent trên test_90]`

**RQ2 — thí nghiệm tinh chỉnh đa phiên.** Ba chương trình đào tạo và 8 tuning request của case study (Mục 4) chạy dưới **bốn điều kiện**:

| Điều kiện | Agent | Cơ chế tinh chỉnh |
|---|---|---|
| `harness_targeted_tuning` | AlignmentGraph-ISD | tuning request → cascade theo impact policy → targeted repair (đề xuất) |
| `harness_full_regen` | AlignmentGraph-ISD | cùng thông tin, mọi node bị invalidate → sinh lại toàn bộ (cô lập cơ chế khoanh vùng) |
| `react_full_regen` | ReAct-ADDIE (baseline mạnh nhất RQ1) | chạy lại toàn bộ từ scenario cập nhật — sừng (1) của thế lưỡng nan |
| `react_targeted_tuning` | ReAct-ADDIE + endpoint `adjust` | prompt gồm scenario cũ + output cũ + yêu cầu tinh chỉnh, không có cơ chế kiểm soát alignment — sừng (2) của thế lưỡng nan |

Bốn điều kiện nhận cùng thông tin (thiết kế trước đó + yêu cầu tinh chỉnh); khác biệt duy nhất là cơ chế. Khác với RQ1, hai điều kiện harness ở đây chạy **cấu hình kiến trúc đầy đủ** (gồm agentic RAG trên corpus IT/Software Engineering); elicitation được minh hoạ trong case study (Mục 4, kết quả ở Mục 5.4). Bốn **process metric** đo trên công cụ chung mức output để so sánh được cross-agent: (1) *cascade scope* — tỷ lệ node bị đánh dấu ảnh hưởng (chỉ có nghĩa cho hai điều kiện harness); (2) *edit locality* — tỷ lệ subsection của ADDIE output thay đổi giữa hai round liên tiếp (đo bằng content hash, mọi điều kiện); (3) *cost per tuning round* — token/latency, tuyệt đối và tương đối so với phiên init cùng chuỗi; (4) *alignment preservation* — điểm alignment (rubric item D1 của evaluator) và ADDIE score trước/sau mỗi round, chấm bằng cùng judge cho cả bốn điều kiện; hai điều kiện harness bổ sung audit coverage nội bộ (measures/supports/evaluates) làm phụ lục. Model: cùng SLM với lượt RQ1 bổ sung. Mọi phiên ghi trajectory + manifest.

### 5.2. Kết quả RQ1

Trên `test_30` (Gemma-4-26B-A4B): AlignmentGraph-ISD đạt 85.67 điểm trung bình hai judge — hạng 2 sau ReAct-ADDIE (87.18), dẫn đầu theo judge GPT (85.63), dẫn phase Implementation (82.3) và Evaluation (85.0). Trên `test_90` (DeepSeek-v4-flash-nitro): **dẫn đầu tổng hợp** (84.07 so với 82.70 của hạng nhì), dẫn ADDIE score (85.29) và cả ba mức difficulty, success rate 100% (Dick-Carey 88.9%, EduPlanner 94.4%). Điểm yếu nhất quán qua cả hai lượt: trajectory score thấp hơn ReAct-ADDIE (81.20 vs 87.26 trên `test_90`) — thảo luận ở Mục 6. `[SỐ LIỆU: chờ run — bảng test_90 trên SLM 8–9B; kiểm định thống kê bắt cặp (Wilcoxon signed-rank, hiệu chỉnh Holm) + bootstrap CI trên điểm per-scenario]`

### 5.3. Kết quả RQ2

`[SỐ LIỆU: chờ run — bảng 4 điều kiện × 4 metric × 8 round; kỳ vọng theo cơ chế đã kiểm chứng bằng dress rehearsal: cascade scope của harness_targeted_tuning phân tầng 0.17–1.0 theo loại node đích trong khi hai điều kiện full-regen ≈ 1.0; số LLM call round hẹp nhất = 2 so với 6 của full regen]`

Bằng chứng mức cơ chế đã có từ RQ1: cascade-scoped revision (verifier phát hiện → khoanh vùng → sinh lại) vận hành bên trong từng run benchmark, ghi trong trajectory và phản ánh qua repair success rate cùng success rate 100% trên `test_90`.

### 5.4. Kết quả case study

Minh hoạ định tính workflow trọn vẹn đã mô tả ở Mục 4 (elicitation → init → các phiên tuning). `[SỐ LIỆU/TRANSCRIPT: chọn 1 chuỗi phiên đại diện sau khi chạy thật]`

## 6. Discussion

**Diễn giải kết quả.** RQ1 cho thấy harness hướng-tinh-chỉnh không phải trả giá bằng chất lượng lần sinh đầu — trái lại dẫn đầu ADDIE score ổn định qua hai model. Khoảng cách trajectory score so với ReAct-ADDIE là nhất quán và phản ánh giới hạn hiện tại của cơ chế logging/dynamic orchestration (trace ghi kết quả mỗi bước nhiều hơn là quá trình ra quyết định). RQ2 `[SỐ LIỆU: chờ run — diễn giải theo bảng 4 điều kiện]`.

**Threats to validity.** *Internal:* prompt/model/judge ảnh hưởng kết quả — cố định manifest, cùng decoding config, đa judge, ngẫu nhiên hoá thứ tự chấm. Baseline `react_targeted_tuning` dùng adjust prompt do chính nhóm nghiên cứu viết: mitigate bằng cách công bố prompt và thiết kế có lợi nhất có thể cho baseline (cho phép model trả `unchanged` từng phase để tiết kiệm chi phí). Baseline ReAct trong RQ2 dùng bản prompt dịch sang tiếng Anh từ bản gốc tiếng Hàn của benchmark (loại confound ngôn ngữ; công bố cả hai bản, giữ nguyên semantics). *Construct:* benchmark và process metric đo chất lượng artifact và quá trình, không đo learning outcome của học viên; kết luận giới hạn ở đó. *External:* scenario benchmark tổng hợp đa domain; case study chỉ một miền (IT/SE); khả năng chuyển domain bằng cách thay corpus/template/verifier policy là giả định cần kiểm chứng thêm. *Cost:* multi-agent + repair tăng chi phí so với single-prompt ở lần sinh đầu; báo cáo đầy đủ trade-off điểm số/chi phí thay vì chỉ chất lượng.

**Ý nghĩa rộng hơn.** Mô hình "typed dependency graph + verifier + cascade-scoped revision" không đặc thù giáo dục: mọi bài toán sinh nhiều artifact phụ thuộc nhau (tài liệu kỹ thuật, quy trình, curriculum) đối mặt cùng thế lưỡng nan tinh chỉnh. Kết quả trên SLM `[SỐ LIỆU: chờ run]` củng cố luận điểm harness-over-model cho triển khai chi phí thấp trong doanh nghiệp.

## 7. Conclusion

Bài báo này chỉ ra rằng vòng đời thực của một chương trình đào tạo trong corporate training — brief hình thành qua brainstorm, tinh chỉnh liên tục sau triển khai — đặt ra một thế lưỡng nan mà các LLM agent tối ưu một lần sinh không giải được, và gốc rễ của nó là việc thiếu biểu diễn tường minh cho alignment. AlignmentGraph-ISD đặt alignment làm trạng thái đồ thị hạng nhất và tổ chức các module của harness — từ elicitation, orchestration, RAG đến verifier và bộ nhớ đa phiên — xoay quanh trạng thái đó, nhờ vậy một yêu cầu tinh chỉnh được khoanh vùng, sinh lại đúng chỗ, kiểm tra lại và commit thành phiên bản mới (cascade-scoped revision). Bằng chứng trên ISD-Agent-Bench xác nhận chất lượng lần sinh đầu cạnh tranh; thí nghiệm bốn điều kiện `[SỐ LIỆU: chờ run]` định lượng trực tiếp hai sừng của thế lưỡng nan. Hướng tiếp theo: hoàn thiện trace để thu hẹp khoảng cách trajectory, kiểm chứng tính trung lập domain của alignment graph, và đánh giá elicitation với người thiết kế thật.

---

## Ghi chú citation (đối chiếu `docs/thesis/reference.bib`)

Đã có key: `isdagentbench`, `yao2023react`, `zhang2025eduplanner`, `branch2009addie`, `dick1978systematic`, `tripp1990rapid`, `biggs1996enhancing`, `learnlm2024`, `lessonplanner2024`, `hu2024teachingplan`, `openlearnlm2026`, `edubench2025`, `mathtutorbench2025`, `tutorbench2025`, `deveci2025ouroboros`, `shukla2025scalingwall`, `cho2026harness`.

Cần tra và bổ sung: **LEA** (user nhắc trong khung lập luận — xác nhận tên đầy đủ + venue), 1–2 công trình **verifier/self-refine** và **agentic memory** cho Mục 2.3, và nguồn cho "von Neumann" nếu đúng là một agent/công trình (user nhắc, chưa rõ — hỏi lại).
