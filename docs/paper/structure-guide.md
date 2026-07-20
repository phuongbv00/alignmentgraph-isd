# Cấu trúc bài báo khoa học — Guide theo đề cương của thầy

> Nguồn: "Cấu trúc bài báo KH.pdf" (giáo sư hướng dẫn gửi). Lĩnh vực: CNTT, AI, ATTT, học máy, hệ phân tán.
> Đây là khung **tạp chí** đầy đủ; với bài hội nghị giới hạn trang, một số mục được nén/gộp — xem ghi chú từng mục và phần đối chiếu bản thảo ở cuối.

## Chuỗi logic tổng thể (nguyên tắc quan trọng nhất)

```
Bối cảnh → vấn đề → hạn chế nghiên cứu trước → khoảng trống → câu hỏi nghiên cứu
→ phương pháp đề xuất → thiết kế thực nghiệm → kết quả → giải thích kết quả
→ giới hạn → kết luận
```

Ba ràng buộc xuyên suốt:

1. **Mỗi khoảng trống** phải được xử lý bởi **một thành phần** của phương pháp.
2. **Mỗi thành phần** phải được kiểm chứng bằng **một thí nghiệm**.
3. **Mỗi kết luận** phải được hỗ trợ bởi **một kết quả cụ thể**.

---

## 1. Title

- Nêu gọn: vấn đề nghiên cứu chính + phương pháp/đặc trưng nổi bật + bối cảnh ứng dụng (khi cần).
- Phản ánh rõ **đối tượng – phương pháp – mục tiêu**.
- ❌ Tránh: quá dài, quá chung chung, từ quảng bá ("novel", "excellent", "optimal") khi chưa có bằng chứng mạnh.

## 2. Abstract

Một đoạn thống nhất, đúng trình tự:

```
Bối cảnh → vấn đề → khoảng trống → phương pháp đề xuất → thiết lập thực nghiệm
→ kết quả nổi bật (định lượng) → ý nghĩa
```

- Khoảng trống: chỉ ra **hạn chế cụ thể** của phương pháp hiện có, không nói chung chung.
- Kết quả: đưa **con số định lượng** nổi bật nhất.
- ❌ Không đưa: tài liệu tham khảo, bảng, hình, công thức dài, tuyên bố chưa chứng minh.

## 3. Keywords

- 4–7 từ khóa: lĩnh vực, bài toán chính, phương pháp chính, bối cảnh ứng dụng, công nghệ/cơ chế nổi bật.
- ❌ Tránh lặp lại toàn bộ cụm từ đã có trong tiêu đề.

## 4. Introduction

Viết **thu hẹp dần** từ bối cảnh chung đến vấn đề cụ thể, theo 7 khối:

| Khối | Nội dung | Lưu ý |
|---|---|---|
| 4.1 Bối cảnh & ý nghĩa | Lĩnh vực, vai trò thực tế, tác động nếu không giải quyết | Dẫn nghiên cứu/số liệu tin cậy để chứng minh tính cấp thiết |
| 4.2 Vấn đề khoa học | Xác định **chính xác bài toán**, khó khăn kỹ thuật đặc thù | Giải thích vì sao phương pháp thông thường không giải được |
| 4.3 Hạn chế nghiên cứu hiện có | Phân tích **theo nhóm phương pháp** | Phải nêu rõ: hạn chế gì? điều kiện nào? ảnh hưởng chỉ số nào? vì sao chưa xử lý được? — không viết suông "còn hạn chế" |
| 4.4 Khoảng trống | Tổng hợp hạn chế thành khoảng trống rõ ràng | Khoảng trống phải **dẫn trực tiếp** đến phương pháp đề xuất |
| 4.5 Ý tưởng & phương pháp | Tên, mục tiêu thiết kế, thành phần chính, cách xử lý khoảng trống | Không đi sâu công thức/thuật toán ở đây |
| 4.6 Đóng góp chính | **3–5 đóng góp**, theo thứ tự loại | Xem bảng dưới |
| 4.7 Cấu trúc bài báo | Một đoạn ngắn tóm tắt các phần còn lại | Bắt buộc có |

Thứ tự loại đóng góp (4.6):

1. Bài toán / mô hình hóa (xác lập bài toán, giả định, kiến trúc).
2. Phương pháp (cơ chế, thuật toán, hàm mục tiêu, chiến lược mới).
3. Lý thuyết (hội tụ, độ phức tạp, ổn định, giới hạn — nếu có).
4. Thực nghiệm (dữ liệu, kịch bản, đối chứng, chỉ số phù hợp).
5. Khả năng ứng dụng (mở rộng, hiệu quả tài nguyên, triển khai).

> Mỗi đóng góp phải là **kết quả kiểm chứng được** — không viết dạng nhiệm vụ ("nghiên cứu", "khảo sát", "thực hiện thí nghiệm").

## 5. Related Work

Tổ chức **theo chủ đề/nhóm phương pháp**, không liệt kê từng bài.

- 5.1 Nhóm nền tảng: khái niệm, phương pháp nền — chỉ chọn nội dung liên quan trực tiếp.
- 5.2 Nhóm trực tiếp giải bài toán: phân loại hướng tiếp cận, ưu/nhược từng nhóm, so sánh điều kiện áp dụng.
- 5.3 Các phương pháp **gần nhất với đề xuất**: điểm giống/khác, thành phần chưa xử lý.
- 5.4 Tổng hợp khoảng trống, kết thúc bằng:
  - **Bảng so sánh** các nghiên cứu tiêu biểu theo tiêu chí đã/chưa đáp ứng.
  - Vị trí của phương pháp đề xuất so với công trình trước.
- ❌ Không tuyên bố phương pháp đề xuất *tốt hơn* khi chưa có kết quả thực nghiệm.

## 6. System Model and Problem Formulation

- 6.1 Kiến trúc/mô hình hệ thống: thực thể, vai trò, luồng dữ liệu, môi trường, giới hạn — **nên có hình kiến trúc tổng thể**.
- 6.2 Ký hiệu & định nghĩa: tập hợp, biến, tham số, miền giá trị; dùng bảng ký hiệu nếu nhiều.
- 6.3 Giả định: dữ liệu, mạng/thiết bị, mô hình đe dọa, hành vi người dùng/tác tử, tài nguyên — mỗi giả định phải hợp lý, sát thực tế.
- 6.4 Mô hình toán học: các đại lượng cần tối ưu/kiểm soát (mất mát, độ trễ, chi phí, độ chính xác…).
- 6.5 **Phát biểu bài toán**: biến quyết định, hàm mục tiêu, ràng buộc, điều kiện khả thi, đặc điểm (lồi/không lồi/tổ hợp/đa mục tiêu/động).
- 6.6 Thách thức: vì sao bài toán khó (không gian trạng thái lớn, quan sát không đầy đủ, mục tiêu xung đột, chi phí cao…).

## 7. Proposed Method (phần trung tâm của bài báo)

- 7.1 Tổng quan: mục tiêu thiết kế, quy trình, đầu vào/đầu ra, các giai đoạn — kèm hình kiến trúc/lưu đồ.
- 7.2–7.3 Từng thành phần, cùng một cấu trúc: *vấn đề xử lý → ý tưởng thiết kế → công thức/mô hình → quy trình tính → đầu vào/đầu ra → liên hệ thành phần khác*.
  - Mỗi thành phần phải **có lý do tồn tại** và trực tiếp xử lý một hạn chế đã nêu ở Introduction.
- 7.4 Hàm mục tiêu / cơ chế cập nhật: ý nghĩa từng thành phần, hệ số cân bằng, cách chọn siêu tham số.
- 7.5 Thuật toán tổng thể: **pseudocode** — khởi tạo, trình tự, điều kiện dừng, đầu vào/đầu ra, cơ chế trao đổi giữa các thực thể.
- 7.6 Phân tích lý thuyết (tùy loại bài): hội tụ, ổn định, giới hạn sai số, tính đúng đắn, độ phức tạp tính toán/truyền thông/bộ nhớ. Định lý phải kèm điều kiện và chứng minh.
- 7.7 Phân tích sự khác biệt với baseline gần nhất: khác về thông tin đầu vào, hàm mục tiêu, cơ chế cập nhật, cách ra quyết định, khả năng xử lý điều kiện thực tế.

## 8. Experimental Methodology

- 8.1 **Câu hỏi nghiên cứu** cụ thể — mỗi câu hỏi trả lời bằng một nhóm thí nghiệm tương ứng.
- 8.2 Bộ dữ liệu: nguồn, thời gian, quy mô, đặc trưng, phân bố, tiền xử lý, **lý do lựa chọn**, cách chia train/val/test.
- 8.3 Thiết lập: phần cứng, phần mềm, framework, phiên bản, cấu hình, siêu tham số, số vòng, số seed, điều kiện dừng.
- 8.4 Kịch bản đánh giá: từ chuẩn → khó (mất cân bằng, non-IID, đổi quy mô, nhiễu/tấn công, hạn chế tài nguyên, dữ liệu lạ) — *áp dụng phần phù hợp với domain*.
- 8.5 Đối chứng: baseline cổ điển + baseline mạnh phổ biến + baseline **gần nhất về phương pháp** + công bố mới + **phiên bản đơn giản hóa của chính phương pháp đề xuất**. Huấn luyện/điều chỉnh công bằng.
- 8.6 Chỉ số: hiệu năng chính + ổn định + chi phí (thời gian, bộ nhớ, truyền thông) + khả năng mở rộng + bền vững.
- 8.7 Thống kê: nhiều seed độc lập, mean ± std, kiểm định phù hợp, khoảng tin cậy / effect size, ngưỡng ý nghĩa rõ ràng.
- 8.8 Tái lập: mã nguồn, cấu hình, seed, quy trình dữ liệu, môi trường, khả năng cung cấp dữ liệu/mô hình.

## 9. Results

- 9.1 Kết quả tổng thể: bảng so sánh với baseline, mean ± std, nổi bật kết quả tốt nhất/nhì, phân tích cải thiện tuyệt đối **và** tương đối.
- 9.2 Kết quả theo từng RQ, trình tự: *quan sát → giải thích nguyên nhân → ý nghĩa → ngoại lệ/giới hạn*.
- 9.3 **Ablation study**: loại bỏ/thay thế từng thành phần, xác định mức đóng góp của từng thành phần.
- 9.4 Sensitivity analysis: siêu tham số, quy mô dữ liệu, tài nguyên…
- 9.5 Robustness analysis: nhiễu, thiếu dữ liệu, lệch phân phối, điều kiện chưa gặp…
- 9.6 Scalability & efficiency: thời gian, bộ nhớ, chi phí, hiệu năng khi tăng quy mô.
- 9.7 Phân tích thống kê: kiểm định khác biệt, khoảng tin cậy, độ biến động giữa các lần chạy.

## 10. Discussion

- 10.1 Diễn giải: vì sao hoạt động tốt/chưa tốt, thành phần nào quan trọng, có khớp giả thuyết không, hiện tượng bất thường.
- 10.2 So sánh nghiên cứu trước — ❌ không so trực tiếp con số khi điều kiện thực nghiệm không tương đồng.
- 10.3 Ý nghĩa khoa học: đóng góp cho mô hình hóa, thiết kế thuật toán, lớp bài toán rộng hơn.
- 10.4 Ý nghĩa thực tiễn: bối cảnh triển khai, đối tượng hưởng lợi, yêu cầu tài nguyên, điều chỉnh cần thiết.
- 10.5 **Phân tích thất bại**: chỗ không vượt baseline, hiệu năng giảm, chi phí tăng, thành phần không như kỳ vọng — tăng độ tin cậy, tránh cảm giác cherry-picking.

## 11. Threats to Validity

Mỗi nguy cơ **kèm biện pháp giảm thiểu**:

- **Internal**: cài đặt, siêu tham số, cấu hình baseline, seed, rò rỉ dữ liệu, tiền xử lý.
- **External**: tổng quát sang dữ liệu/môi trường khác, giới hạn thiết bị/người dùng.
- **Construct**: chỉ số có đo đúng mục tiêu không, dữ liệu có đại diện không.
- **Conclusion**: số lần chạy/kích thước mẫu đủ chưa, kiểm định phù hợp chưa, kết luận có vượt bằng chứng không.

## 12. Limitations and Future Work

- Hạn chế **thực sự** (phạm vi dữ liệu, giả định, chi phí, tổng quát hóa, chưa thử môi trường thực) — ❌ không nêu kiểu phủ định toàn bộ giá trị nghiên cứu.
- Mỗi hướng tương lai **xuất phát trực tiếp từ một hạn chế**.

## 13. Conclusion

Trình tự 6 bước: ① nhắc lại bài toán & tầm quan trọng → ② tóm tắt phương pháp → ③ thành phần/đóng góp cốt lõi → ④ kết quả thực nghiệm quan trọng → ⑤ ý nghĩa tổng quát → ⑥ (tùy chọn) một hướng phát triển ngắn.

❌ Không đưa phương pháp, kết quả hoặc tuyên bố **mới** vào Conclusion.

## 14. Declarations (tùy yêu cầu tạp chí)

Funding · Conflict of Interest · Data Availability · Code Availability · Author Contributions (CRediT) · Ethics Statement · Consent for Publication.

## 15. References

- Ưu tiên tạp chí/hội nghị uy tín; đủ nghiên cứu nền tảng + mới nhất + các công trình gần nhất với đề xuất.
- Hạn chế nguồn không phản biện (blog, trang quảng cáo).
- Tuân thủ tuyệt đối định dạng của venue; mọi tài liệu trong danh mục đều được trích dẫn trong bài và ngược lại.
