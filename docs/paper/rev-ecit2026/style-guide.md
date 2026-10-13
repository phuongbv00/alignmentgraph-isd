# Cẩm nang viết bài REV-ECIT 2026 (tiểu ban AI và ứng dụng liên ngành)

Cẩm nang này tổng hợp từ **21 bài** của tiểu ban AI trong kỷ yếu REV-ECIT 2025 (tr. 294–430).
Bốn agent đọc trọn văn bản và ảnh trang của 20 bài. Bài thứ 21 (*Mô hình học sâu đa phương thức
cho dự báo rủi ro học tập*, ĐHBK Hà Nội, tr. 331–336) được đọc trực tiếp vì gần đề tài nhất.
Số "x/20" là số bài theo quy ước đó trong mẫu.

Cẩm nang có hai lớp:
- **Quy ước của hội nghị:** làm theo để bài trông như một bài đã được nhận.
- **Chỗ ta làm khác có chủ đích:** mức claim và cách báo kết quả vẫn theo `docs/paper/claim-rules.md`.
  Khi hai lớp mâu thuẫn, `claim-rules.md` thắng.

---

## 1. Khung trình bày

| Hạng mục | Quy ước trong mẫu | Ta làm |
|---|---|---|
| Template | IEEEtran LaTeX 13/20, Word 6/20, sai template 1/20 | IEEEtran `conference,a4paper`, biên dịch bằng XeLaTeX |
| Số trang | 6 trang là chuẩn; 4 bài 7 trang và 1 bài 15 trang vẫn được nhận | **Đúng 6 trang**, kể cả tài liệu tham khảo |
| Header, footer | Ban tổ chức tự thêm ("Hội nghị Quốc gia lần thứ…", ISBN) | Không tự thêm |
| Tác giả | Tên tiếng Việt có dấu kèm chỉ số đơn vị (phổ biến), hoặc lưới tác giả IEEE với tên không dấu | Tên có dấu, chỉ số trên `1,2`, `*` cho tác giả liên hệ, đơn vị viết bằng tiếng Việt |

## 2. Tiêu đề, tóm tắt, từ khóa

- **Tiêu đề:** tiếng Việt, viết hoa kiểu câu, 13–25 từ, 2–3 dòng. Tên hệ hoặc mô hình giữ nguyên tiếng
  Anh. Mẫu "Tên hệ: mô tả" khá phổ biến (DurNet:…, TripFishNet:…, CacaoShield:…).
- **Nhãn tóm tắt:** "Tóm tắt—" (đa số bài LaTeX), "Tóm tắt nội dung—" (mặc định của babel) hoặc
  "Abstract—" (bài Word). **Ta dùng "Tóm tắt—".**
- **Độ dài tóm tắt:** 170–300 từ, một đoạn, chữ đậm (IEEEtran tự đặt).
- **Cấu trúc tóm tắt:** bối cảnh → "Tuy nhiên…" (hạn chế) → "Bài báo này đề xuất…" → thực nghiệm →
  kết quả **có số** (11/20 có số) → ý nghĩa. **Ta có số**, lấy từ file sinh ra, không gõ tay.
- **Từ khóa:** "Từ khóa—" (phổ biến nhất), 4–5 cụm tiếng Việt. Thuật ngữ tiếng Anh để trong ngoặc khi
  cần.

## 3. Bố cục mục

Đề mục đánh số La Mã và viết hoa toàn bộ, ví dụ `I. GIỚI THIỆU` (20/20). IEEEtran đặt chúng ở dạng
small caps. Mục con dùng "A.", "B." in nghiêng; mức dưới nữa là "1)" in nghiêng, viết liền vào đoạn.

Bố cục ta chọn, theo nhóm bài hệ thống hoặc ứng dụng:

| Mục | Mẫu | Độ dài |
|---|---|---|
| I. GIỚI THIỆU | 20/20 | khoảng 0,8 trang |
| II. CÁC NGHIÊN CỨU LIÊN QUAN | Tách riêng ở 12/20 bài, phổ biến ở bài hệ thống | khoảng 0,5 trang |
| III. HỆ THỐNG ĐỀ XUẤT | Tên mục tùy bài: "Phương pháp đề xuất", "Mô hình hệ thống đề xuất" | khoảng 1,5 trang, kèm hình 1 trải rộng cả trang |
| IV. THỰC NGHIỆM VÀ ĐÁNH GIÁ | A. Thiết lập, B. Kết quả, C. Thảo luận | khoảng 2 trang |
| V. KẾT LUẬN | 19/20 | 0,2–0,3 trang |
| TÀI LIỆU THAM KHẢO | | khoảng 0,7 trang |

- **Thảo luận** đứng thành mục riêng chỉ ở 3/20 bài. Nhiều bài đặt nó làm mục con cuối của phần thực
  nghiệm. Ta đặt nó ở **IV.C**.
- Bài mẫu gần đề tài viết các nhận xét thảo luận dạng **(1), (2), … in đậm ở đầu đoạn**, trong đó có
  một nhận xét riêng cho trường hợp hệ đề xuất không vượt trội. Ta làm theo cách này.

## 4. Giới thiệu: trình tự lập luận

1. **Bối cảnh và tầm quan trọng của bài toán.** Các nghiên cứu lồng vào đoạn văn kèm trích dẫn.
2. **Khoảng trống.** Câu khoảng trống gần như luôn theo các dạng: "Tuy nhiên…", "…chưa được…",
   "…còn hạn chế", "có thể thấy thiếu…", "Khoảng trống này đặt ra nhu cầu…".
3. **Đề xuất.** "Vì vậy, bài báo này đề xuất…" hoặc "Trong nghiên cứu này, chúng tôi đề xuất…".
4. **Đóng góp.** 15/20 bài liệt kê 2–4 đóng góp đánh số. **Bài này nêu đúng MỘT đóng góp** (hệ
   AlignmentGraph-ISD), theo quyết định của tác giả và `claim-rules.md`. Đóng góp được viết thành một
   câu văn ("Vì vậy, đóng góp của bài báo này là…"), không viết thành danh sách. Phần đánh giá thực
   nghiệm là một câu riêng, không gọi là đóng góp.
5. **Đoạn cấu trúc bài** ("Phần còn lại của bài báo được tổ chức như sau…") chỉ có ở 7/20 bài, và
   nhiều bài ghi sai số mục. Ta giữ đoạn này nhưng **phải khớp đúng số mục thật**.

## 5. Hình

- **Chú thích:** `Hình N.` đặt dưới hình (20/20). Bài LaTeX hay dùng dấu ":", bài Word dùng ".".
  IEEEtran với `\figurename{Hình}` cho ra "Hình 1." và ta giữ như vậy.
- Chú thích ngắn, 1–2 câu.
- **Hình kiến trúc** có ở 20/20 bài: sơ đồ khối vẽ tay, ô bo góc màu nhạt (pastel), mũi tên. Thường đặt
  trải rộng cả trang (`figure*`).
  - Chữ trong hình bằng tiếng Anh ở khoảng 3/4 số bài, nhưng bài tiếng Việt cũng phổ biến.
  - **Ta dùng nhãn tiếng Anh** (như khoảng 3/4 số bài), kể cả mã quan hệ (C2–C4, P…) và tên tệp
    (`graph.json`). Chú thích hình viết bằng tiếng Việt.
  - Nguồn hình: `figures/make_architecture_timeline.py` sinh SVG, `rsvg-convert` chuyển sang PDF.
- **Biểu đồ:** gần như toàn bộ dùng matplotlib hoặc seaborn mặc định, nhãn trục thường bằng tiếng Anh.
  Biểu đồ cột có in giá trị trên cột; ma trận nhầm lẫn theo bảng màu "Blues".
  - **Ta:** matplotlib, nhãn trục tiếng Việt cho thống nhất với bài, cỡ chữ đọc được ở khổ một cột.
- **Số hình:** 3 hình ở bài mô hình, 8–10 hình ở bài ứng dụng. **Ta dùng 2–3 hình** vì 6 trang không
  chứa được nhiều hơn.

## 6. Bảng

- **Số bảng:** La Mã "Bảng I" (bài LaTeX, đa số). Chú thích **đặt trên** bảng (19/20). IEEEtran tự cho
  kiểu hai dòng small caps.
- **Kẻ bảng:** booktabs và kẻ lưới đầy đủ đều phổ biến như nhau. **Ta dùng booktabs.**
- **Đánh dấu kết quả:** **in đậm** giá trị tốt nhất (hầu hết bài). Vài bài gạch chân giá trị tốt thứ
  hai. Nên có mũi tên ↑/↓ ở tiêu đề cột để chỉ chiều tốt.
- **Dấu thập phân:** trong mẫu, nhiều bài trộn "0,94" ở văn bản với "0.94" ở bảng. **Ta dùng dấu chấm ở
  mọi nơi**, khớp với quy ước artifact của repo (`87.77`).

## 7. Phương trình

- Bài hệ thống thường chỉ có các công thức chỉ số (Accuracy, F1…). Bài mô hình có 10–17 công thức.
- Ta đánh số khoảng 3–4 công thức: định nghĩa đồ thị, điều kiện `aligned(o)`, độ phủ quan hệ, và điểm
  Total.

## 8. Giọng văn và thuật ngữ

- **Ngôi:** "chúng tôi" là mặc định (18/20); dùng thêm "nghiên cứu này" và "bài báo này".
- **Thuật ngữ:** viết tiếng Việt trước, tiếng Anh trong ngoặc, có thể kèm viết tắt sau gạch nối. Ví dụ:
  "căn chỉnh kiến tạo (constructive alignment)", "hệ đa tác tử (Multi-Agent System – MAS)". Tên riêng
  (ADDIE, ReAct, ISD-Agent-Bench, Qwen) giữ nguyên.
- **Câu văn:** mẫu thường viết câu dài nhiều mệnh đề. **Ta viết câu thẳng, mỗi câu một ý** (theo quy ước
  văn phong tiếng Việt của dự án).
- **Mức claim:** mẫu dùng tự do các từ "vượt trội", "khẳng định", "chứng minh", "ấn tượng".
  - **Ta không dùng các từ này.** Câu thay thế lấy theo `claim-rules.md`, ví dụ: cạnh tranh, ổn định,
    kiểm toán được hơn trong điều kiện SLM đã thử.
  - Đây là điểm cộng so với mặt bằng của hội nghị, không phải điểm trừ.

## 9. Kết quả và thống kê

- Gần như toàn bộ mẫu báo **một lần chạy**, không có độ lệch chuẩn, không kiểm định (trong 20 bài: 0 bài có kiểm định,
  1 bài có mean ± SD từ cross-validation). Ngoại lệ là bài mẫu gần đề tài: có mean ± SD qua tám học phần
  và paired t-test.
- **Ta:** báo mean ± SD theo kịch bản, kèm kiểm định theo cặp (Wilcoxon) cho phép so sánh chính. Giải
  thích ngắn gọn bằng tiếng Việt vì người đọc của hội nghị ít gặp kiểu báo cáo này.
- **Hạn chế:** chỉ khoảng 6/20 bài nêu tường minh. **Ta có một đoạn hạn chế** (đặt ở IV.C hoặc trong
  KẾT LUẬN): mẫu nhỏ, chỉ một nấc mô hình, LLM judge có thiên lệch, và kết quả là thử nghiệm sơ bộ.
- **Đối chứng:** nhiều bài lấy số của bài khác trên dữ liệu khác để so. **Ta chỉ so các hệ chạy trên cùng
  kịch bản, cùng mô hình và cùng LLM judge.**

## 10. Tài liệu tham khảo

- **Kiểu trích dẫn:** IEEE dạng số (19/20). Phần lớn bài có khoảng 20 mục, dao động 8–35.
- **Nguồn:** gần như toàn bộ là tài liệu quốc tế, giai đoạn 2019–2025. DOI ít gặp trong mẫu nhưng bài mẫu
  gần đề tài có DOI đầy đủ.
- **Ta:** 18–22 mục, kèm DOI khi có, tất cả được `\cite` trong bài. Không có mục trùng lặp và không có
  mục không kiểm chứng được.

## 11. Lỗi mẫu đã mắc mà ta phải tránh

Mức đòi hỏi về độ chỉn chu của hội nghị thấp, nên một bài sạch sẽ nổi bật. Các lỗi đã được nhận trong
kỷ yếu, ta không được mắc:

- Lỗi chính tả, kể cả trong tiêu đề ("ảnh ý tế", "chuẩn đoán").
- Trộn dấu thập phân; viết sai dấu phân cách hàng nghìn.
- Đoạn cấu trúc bài nhắc tới các mục không tồn tại; tham chiếu chéo trỏ sai mục.
- Chữ còn sót từ luận văn ("Chương III", "Hình 4.8"); viết "tôi" thay vì "chúng tôi".
- Chú thích "(placeholder)", tô vàng sửa bài, khung link màu của hyperref.
- Tài liệu tham khảo trùng, bị cắt cụt, hoặc được trích mà không có trong danh sách.
- Khẳng định "vượt trội trên mọi chỉ số" trong khi bảng không cho thấy như vậy.
- Bảng hoặc hình đánh số sai thứ tự; chữ trong hình quá nhỏ để đọc.

## 12. Danh sách kiểm tra trước khi nộp

- [ ] `./compile.sh` không lỗi, ra **≤ 6 trang**.
- [ ] Tóm tắt có số, và số đó lấy từ file sinh ra.
- [ ] Đúng một đóng góp, viết thành câu văn (không đánh số).
- [ ] Đoạn cấu trúc bài khớp đúng số mục.
- [ ] Mọi hình có "Hình N." ở dưới; mọi bảng có "Bảng N" ở trên, dùng booktabs, in đậm giá trị tốt nhất.
- [ ] Cả bài chỉ dùng dấu chấm thập phân.
- [ ] Không có "vượt trội", "chứng minh", "tốt nhất mọi chỉ số".
- [ ] Không nhắc RAG.
- [ ] Không còn `\TBD` hay TODO.
- [ ] Đã rà chính tả tiếng Việt; tên hệ viết nhất quán.
- [ ] Tác giả, đơn vị và tác giả liên hệ đã được thầy xác nhận.
- [ ] Kiểm tra trùng lặp ≤ 30% (bài này viết mới bằng tiếng Việt, không chép từ bản ACM).
