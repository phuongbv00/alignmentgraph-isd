# AlignmentGraph-ISD

## Bối cảnh

Các mô hình ngôn ngữ lớn thương mại có thể tạo ra chương trình giảng dạy chất lượng cao và ngày càng được ứng dụng trong dạy học, sinh học liệu và thiết kế hệ thống giảng dạy (Instructional Systems Design — ISD). Tuy nhiên, chi phí suy luận, sự phụ thuộc vào API và việc phải chuyển dữ liệu người học hoặc học liệu nội bộ qua dịch vụ bên thứ ba gây trở ngại cho việc triển khai rộng rãi tại các cơ sở giáo dục.

Các mô hình ngôn ngữ nhỏ có trọng số mở (open-weight SLM) có thể được triển khai tại chỗ, nhờ đó đem lại sự cân bằng thực tế hơn giữa chất lượng, chi phí và quyền kiểm soát dữ liệu. Khi mô hình nền nhỏ đi, khả năng duy trì chất lượng của toàn hệ thống phụ thuộc nhiều hơn vào harness — bộ khung chịu trách nhiệm quản lý trạng thái, điều phối quy trình và kiểm soát chất lượng.

## Khoảng trống nghiên cứu

Các nghiên cứu về ISD và sinh lesson plan chủ yếu tập trung vào tự động hoá quy trình, giảm khối lượng công việc, cá nhân hoá hoặc nâng cao chất lượng đầu ra trên các mô hình mạnh. Một số công trình đã sử dụng mô hình nhỏ để hỗ trợ giáo viên hoặc tinh chỉnh mô hình 7B cho sinh lesson plan, nhưng việc duy trì chất lượng khi thu nhỏ mô hình nền vẫn chưa được nghiên cứu rõ như một mục tiêu thiết kế và đánh giá của hệ tác tử ISD.

Trên cơ sở khoảng trống này, nghiên cứu hướng tới hai mục tiêu:

1. Đánh giá mức độ duy trì chất lượng của harness ISD đề xuất khi chuyển từ LLM sang SLM trong tương quan với các tác tử ISD tiêu biểu.
2. Ước lượng đóng góp của các cơ chế harness được khảo sát và xem xét sự thay đổi của các đóng góp này giữa LLM và SLM.

Các công trình lân cận gồm Small Models Big Support, tập trung vào hỗ trợ biên soạn nội dung bằng SLM cục bộ; LessonPlanLM, tinh chỉnh mô hình 7B cho sinh lesson plan; và Instructional Agents, báo cáo chi phí sử dụng nhưng vẫn dựa trên API thương mại. Phạm vi liên quan được tổng hợp trong `docs/paper/refs-deployment-survey.md`.

## Giả thuyết thiết kế

Xuất phát điểm của thiết kế là ràng buộc kỹ thuật của bài toán: để triển khai tại chỗ, mô hình nền phải là SLM, mà SLM lại yếu đi rõ rệt khi phải xử lý một tác vụ mở, đồng thời chịu nhiều ràng buộc — điều mà việc sinh trọn một chương trình ISD trong một lượt đòi hỏi. Một hướng đối phó là fine-tune SLM cho tác vụ, nhưng cách này gắn với từng mô hình và từng miền dữ liệu. Nghiên cứu này chọn hướng ở cấp harness: giữ mô hình nền nguyên trạng và **thu hẹp tác vụ mà mỗi lời gọi mô hình phải gánh**. Một tác vụ hẹp, được định phạm vi rõ, nằm trong tầm với của mô hình yếu hơn so với một tác vụ rộng, đa mục tiêu. Đây là lý do phân rã theo mối quan tâm ISD — mỗi tác tử chuyên biệt chỉ lo một phần — thay vì một tác tử đơn với prompt phức tạp hơn.

Phân rã lại làm nảy sinh một vấn đề mới: khi mỗi mảnh được sinh riêng, chúng phải **nhất quán với nhau**. Trong ISD, chất lượng không nằm ở từng đầu ra riêng lẻ mà ở sự ăn khớp giữa mục tiêu học tập, hoạt động, học liệu, đánh giá và lượng giá. Vì vậy các tác tử cần một substrate chung để phối hợp — và thứ cần được phối hợp, cụ thể trong ISD, chính là **sự ăn khớp về sư phạm**. Constructive alignment cung cấp cơ sở lý thuyết để xác định đúng các quan hệ phải duy trì giữa mục tiêu, hoạt động và đánh giá, qua đó định hình *lược đồ* của substrate này — các kiểu node và edge nào là hợp lệ, và verifier phải kiểm những quan hệ nào.

Trên cơ sở đó, AlignmentGraph-ISD hiện thực hoá substrate điều phối dưới dạng alignment graph: một trạng thái thiết kế tường minh, dùng chung, để các tác tử sinh nội dung khớp với nhau và để cơ chế kiểm chứng có thể kiểm được. Giả thuyết là một harness tổ chức quá trình sinh xoay quanh trạng thái này sẽ giảm được sự phụ thuộc vào khả năng tự duy trì nhất quán của bản thân mô hình — khả năng vốn suy giảm khi thu nhỏ mô hình nền.

## AlignmentGraph-ISD

Alignment graph là cấu trúc dữ liệu trung tâm của harness — substrate mà quá trình phân rã và điều phối vận hành trên đó. Đồ thị gồm các node có kiểu `objective`, `activity`, `material`, `assessment`, `implementation` và `evaluation`; cùng các edge có kiểu `measures`, `supports` và `evaluates`, phản ánh các quan hệ ăn khớp mà constructive alignment đòi hỏi.

Các tác tử chuyên biệt xây dựng đồ thị theo một quy trình ISD cố định và chỉ được cập nhật phần trạng thái thuộc phạm vi trách nhiệm của mình. Chính cách phân rã có ràng buộc này — chứ không phải bản thân cấu trúc đồ thị — là thứ tạo ra các liên kết bắt buộc ngay trong quá trình sinh. Sau mỗi lượt cập nhật, cơ chế kiểm chứng và sửa lỗi kiểm tra tính phù hợp về sư phạm và nhận thức, sau đó sửa các vi phạm được phát hiện.

Kiến trúc của harness không gắn với một mô hình cụ thể. Đóng góp thực sự của từng cơ chế — phân rã, cấu trúc đồ thị, kiểm chứng–sửa lỗi — và mức độ chúng thay đổi khi thu nhỏ mô hình nền được xác định bằng thực nghiệm, chứ không được giả định trước.

## Câu hỏi nghiên cứu

- **RQ1 — Duy trì chất lượng:** AlignmentGraph-ISD duy trì chất lượng ở mức nào khi chuyển từ LLM sang SLM, so với các hệ tác tử đối sánh?
- **RQ2 — Cơ chế harness:** Phân rã đa tác tử trên đồ thị và cơ chế kiểm chứng–sửa lỗi đóng góp như thế nào vào chất lượng, và mức đóng góp có thay đổi theo kích thước mô hình hay không?

## Thiết lập thực nghiệm

Thực nghiệm sử dụng 90 tình huống trong tập `test_90` của ISD-Agent-Bench và sáu tác tử đối sánh. Mỗi hệ thống được chạy với DeepSeek-v4-flash và Qwen3.5-9B; kết quả được chấm bởi hai judge và lấy trung bình.

RQ1 được phân tích bằng Wilcoxon signed-rank ghép cặp theo tình huống, hiệu chỉnh Holm và bootstrap 95% CI. RQ2 sử dụng ablation study, lần lượt loại bỏ phân rã đa tác tử và cơ chế kiểm chứng–sửa lỗi, kết hợp với kiểm toán các lỗi alignment còn sót.

## Kết quả chính

AlignmentGraph-ISD đứng đầu cả bảy tác tử trên hai mô hình, với composite 87,77 trên LLM và 86,47 trên SLM; mọi so sánh ghép cặp đều có ý nghĩa sau hiệu chỉnh Holm. Khi chuyển từ LLM sang SLM, điểm chỉ giảm 1,30, trong khi các đối sánh giảm từ 1,66 đến 23,46 điểm.

Trong ablation study, phân rã đa tác tử trên đồ thị là cơ chế đóng góp lớn nhất trong số các cơ chế được kiểm tra. Mức đóng góp ước lượng tăng từ 3,90 điểm trên LLM lên 7,94 điểm trên SLM. Cơ chế kiểm chứng–sửa lỗi không làm thay đổi điểm judge nhưng giảm 69% số lỗi alignment do verifier nội bộ phát hiện, từ 39 xuống 12.

## Ý nghĩa và phạm vi kết luận

Kết quả cho thấy các cơ chế ở cấp harness có tiềm năng giúp chất lượng của hệ ISD ổn định hơn khi mô hình nền được thu nhỏ. Trong phạm vi thực nghiệm hiện tại, phân rã đa tác tử trên alignment graph có đóng góp lớn nhất. Tuy nhiên, thiết kế thí nghiệm chưa tách riêng ảnh hưởng của cấu trúc đồ thị khỏi ảnh hưởng của phân rã tác vụ và lượng tính toán tại thời điểm suy luận.

Các kết quả này tạo cơ sở cho hướng triển khai hệ ISD bằng open-weight SLM với chi phí thấp hơn và quyền kiểm soát dữ liệu tốt hơn tại các cơ sở giáo dục.
