# Thesis template guides (backup)

Bản sao nội dung hướng dẫn gốc (tiếng Việt, dạng "sinh viên cần trình bày...") của template LaTeX ĐATN trước khi bị thay bằng nội dung thật của luận văn AlignmentGraph-ISD. Trích xuất bằng `git diff HEAD` tại thời điểm soạn thảo (commit gốc: template ĐATN chưa chỉnh sửa). Dùng để đối chiếu/audit khi cần kiểm tra nội dung luận văn có còn đáp ứng đúng các yêu cầu trình bày ban đầu của template hay không (độ dài chương, cấu trúc Tổng quan/Kết chương, quy định trích dẫn, v.v.).

Lưu ý: `4_Theoretical_Analysis.tex` đã bị xoá hẳn khỏi luận văn (không giữ placeholder); `5_Numerical_results.tex` đã đổi tên thành `4_Numerical_results.tex` sau khi bỏ chương Theoretical Analysis, nên chương Numerical Results hiện là Chapter 4 chứ không phải Chapter 5 như trong bản gốc.

Các mục sau Chapter 6 (Chapter 7 "SHORT NOTICES ON REFERENCE", Appendix A, Appendix B) **chưa được chỉnh sửa** — vẫn còn nguyên placeholder hướng dẫn của template, nên nội dung dưới đây được chép trực tiếp từ file hiện tại (không phải trích từ `git diff`) để đầy đủ toàn bộ hướng dẫn gốc của template, không chỉ sáu chương nội dung chính.

## main.tex — cấu trúc chương gốc (trước khi bỏ Theoretical Analysis, thêm Case Study)

`docs/thesis/main.tex`

```text
\def \TITLE{GRADUATION THESIS}
\chapter{THEORETICAL ANALYSIS}
\subfile{Chapter/4_Theoretical_analysis}
\chapter{NUMERICAL RESULTS}
\subfile{Chapter/5_Numerical_results}
```

## Cover.tex — placeholder gốc

`docs/thesis/Cover.tex`

```text
{\textbf{\huge{GRADUATION THESIS}}}\\[1cm]
{\textbf{\Large{Thesis title}}\\[1cm]
{\textbf{\large{NGUYỄN DOÃN A}}}\\
{\large{nguyenvanabc@sis.hust.edu.vn}}\\[0.5cm]
{\textbf{\large{Program: Global ICT}}}\\
\vspace{4cm}
 \multicolumn{1}{l}{\textbf{Supervisor:}} & Associate Professor Lê  Tùng ABC \hspace{0.5cm} 
  \\[0.5cm]
 \multicolumn{1}{l}{\textbf{Department:}} & Computer Engineering \hspace{0.5cm} \\ [0.5cm]
 \multicolumn{1}{l}{\textbf{School:}} & School of Information and Communications Technology \hspace{0.5cm} \\ [5.5cm]
% \underline{\hspace{3cm}}  \\[0.5cm]
%   & \multicolumn{1}{r}{Chữ kí GVHD}     \\[0.5cm]
% \textbf{Khoa:} & Kỹ thuật máy tính                 \\[0.5cm]
% \textbf{Trường:} & Công nghệ Thông tin và Truyền thông \\[5cm]
\multicolumn{2}{c}{\textbf{HANOI, 06/2022}}                                            
```

## Cover2.tex — placeholder gốc

`docs/thesis/Cover2.tex`

```text
{\textbf{\huge{GRADUATION THESIS}}}\\[1cm]
{\textbf{\Large{Thesis title}}\\[1cm]
{\textbf{\large{NGUYỄN VĂN A}}}\\
{\large{nguyenvanabc@sis.hust.edu.vn}}\\[0.5cm]
{\textbf{\large{Program: Global ICT
%{\textbf{\large{Chuyên ngành Hệ thống thông tin}}}\\
\vspace{4cm}
\multicolumn{1}{l}{\textbf{Supervisor:}} & Associate Professor Lê  Tùng ABC \hspace{0.5cm} \underline{\hspace{3cm}}  \\[0.5cm]
  & \multicolumn{1}{r}{Signature}     \\[0.5cm]
\textbf{Department:} & Computer Engineering                 \\[0.5cm]
\textbf{School:} & School of Information and Communications Technology \\[5cm]
\multicolumn{2}{c}{\textbf{HANOI, 06/2022}}                                            
```

## Chapter 0.2 — Acknowledgment (hướng dẫn gốc)

`docs/thesis/Chapter/0_2_Acknowledgment.tex`

```text
Lời cảm ơn của sinh viên (SV) tới người yêu, gia đình, bạn bè, thầy cô, và chính bản thân mình vì đã chăm chỉ và quyết tâm thực hiện ĐATN để đạt kết quả tốt nhất, nên viết phần cảm ơn ngắn gọn, tránh dùng các từ sáo rỗng, giới hạn trong khoảng 100-150 từ. 
```

## Chapter 0.3 — Abstract (hướng dẫn gốc)

`docs/thesis/Chapter/0_3_Abstract.tex`

```text
Sinh viên viết tóm tắt ĐATN của mình trong mục này, với 200 đến 350 từ. Theo trình tự, các nội dung tóm tắt cần có: (i) Giới thiệu vấn đề (tại sao có vấn đề đó, hiện tại được giải quyết chưa, có những hướng tiếp cận nào, các hướng này giải quyết như thế nào, hạn chế là gì), (ii) Hướng tiếp cận sinh viên lựa chọn là gì, vì sao chọn hướng đó, (iii) Tổng quan giải pháp của sinh viên theo hướng tiếp cận đã chọn, và (iv) Đóng góp chính của ĐATN là gì, kết quả đạt được sau cùng là gì. Sinh viên cần viết thành đoạn văn, không được viết ý hoặc gạch đầu dòng.
```

## Chapter 1 — Introduction (hướng dẫn gốc)

`docs/thesis/Chapter/1_Introduction.tex`

```text
Lưu ý: Mẫu ĐATN này được thiết kế phù hợp với đồ án tốt nghiệp theo hướng nghiên cứu. Mẫu đề tài này là gợi ý tham khảo. Tuỳ từng đề tài, cấu trúc có thể thay đổi ít nhiều. Sinh viên cần tham khảo ý kiến của giáo viên hướng dẫn để đưa ra cấu trúc hợp lý nhất cho đề tài của mình. 

Trước khi viết ĐATN, sinh viên cần đọc kỹ hướng dẫn và quy định chi tiết về cách viết ĐATN trong Phụ lục A. 

Khi đóng quyển ĐATN, sinh viên cần lưu ý tuân thủ hướng dẫn ở phụ lục A.9

SV cần đặc biệt lưu ý cách hành văn. Mỗi đoạn văn không được quá dài và cần có ý tứ rõ ràng, bao gồm duy nhất một ý chính và các ý phân tích bổ trợ để làm rõ hơn ý chính. Các câu văn trong đoạn phải đầy đủ chủ ngữ vị ngữ, cùng hướng đến chủ đề chung. Câu sau phải liên kết với câu trước, đoạn sau liên kết với đoạn trước. Trong văn phong khoa học, sinh viên không được dùng từ trong văn nói, không dùng các từ phóng đại, thái quá, các từ thiếu khách quan, thiên về cảm xúc, về quan điểm cá nhân như "tuyệt vời", "cực hay", "cực kỳ hữu ích", v.v. Các câu văn cần được tối ưu hóa, đảm bảo rất khó để thể thêm hoặc bớt đi được dù chỉ một từ. Cách diễn đạt cần ngắn gọn, súc tích, không dài dòng.

Chương 1 có độ dài từ 3 đến 6 trang với các nội dung sau đây

Phần này sinh viên mô tả bài toán cần giải quyết, lý do tại sao lại chọn bài toán đó, ý nghĩa/tầm quan trọng của bài toán.

Tiêu đề của chương này có thể để là ``đặt vấn đề'', hoặc lấy chính tên của bài toán mà sinh viên định giải quyết, ví dụ có thể đặt tiêu đề là ``Bài toán dự đoán …" 


\section{Background and Problems of Research} 
\label{sec:giaiphap}
Sinh viên trước tiên cần trình bày tổng quan các kết quả của các nghiên cứu hiện nay cho bài toán giới thiệu ở phần \ref{sec:dvd}. Sau đấy, sinh viên đưa ra các hạn chế của các giải pháp hiện tại. 
\section{Research Objectives and Conceptual Framework}
Trong chương này, sinh viên trước hết trình bày mục tiêu của đồ án là gì, sau đấy sinh viên đề xuất định hướng giải pháp của mình. Tốt nhất là với trình bày từng giải pháp đối với mỗi vấn đề nêu ra trong chương \ref{sec:giaiphap}. 
\section{Contributions}
Trong phần này sinh viên liệt kê cụ thể, ngắn gọn các đóng góp của đồ án. Ví dụ: 
Đồ án này có 3 đóng góp chính như sau:
\begin{enumerate}
\item Đồ án đề xuất một phương pháp tiền xử lý dữ liệu nhằm loại bỏ nhiễu và dữ liệu ngoại lai trước khi đưa vào huấn luyện mô hình.
\item \ldots
\item \ldots 
\end{enumerate}
\section{Organization of Thesis}
Phần còn lại của báo cáo đồ án tốt nghiệp này được tổ chức như sau. 
Chương 2 trình bày về v.v. 
Trong Chương 3, em/tôi giới thiệu về v.v.
Chú ý: Sinh viên cần viết mô tả thành đoạn văn đầy đủ về nội dung chương. Tuyệt đối không viết ý hay gạch đầu dòng. Chương 1 không cần mô tả trong phần này. 
Ví dụ tham khảo mô tả chương trong phần bố cục đồ án tốt nghiệp: Chương *** trình bày đóng góp chính của đồ án, đó là một nền tảng ABC cho phép khai phá và tích hợp nhiều nguồn dữ liệu, trong đó mỗi nguồn dữ liệu lại có định dạng đặc thù riêng. Nền tảng ABC được phát triển dựa trên khái niệm DEF, là các module ngữ nghĩa trợ giúp người dùng tìm kiếm, tích hợp và hiển thị trực quan dữ liệu theo mô hình cộng tác và mô hình phân tán.  
Chú ý: Trong phần nội dung chính, mỗi chương của đồ án nên có phần Tổng quan và Kết chương. Hai phần này đều có định dạng văn bản "Normal", sinh viên không cần tạo định dạng riêng, ví dụ như không in đậm/in nghiêng, không đóng khung, v.v... 
Trong phần Tổng quan của chương N, sinh viên nên có sự liên kết với chương N-1 rồi trình bày sơ qua lý do có mặt của chương N và sự cần thiết của chương này trong đồ án. Sau đó giới thiệu những vấn đề sẽ trình bày trong chương này là gì, trong các đề mục lớn nào.
Ví dụ về phần Tổng quan: Chương 3 đã thảo luận về nguồn gốc ra đời, cơ sở lý thuyết và các nhiệm vụ chính của bài toán tích hợp dữ liệu. Chương 4 này sẽ trình bày chi tiết các công cụ tích hợp dữ liệu theo hướng tiếp cận "mashup". Với mục đích và phạm vi của đề tài, sáu nhóm công cụ tích hợp dữ liệu chính được trình bày bao gồm: (i) nhóm công cụ ABC trong phần 4.1, (ii) nhóm công cụ DEF trong phần 4.2, nhóm công cụ GHK trong phần 4.3, v.v...
Trong phần Kết chương, sinh viên đưa ra một số kết luận quan trọng của chương. Những vấn đề mở ra trong Tổng quan cần được tóm tắt lại nội dung và cách giải quyết/thực hiện như thế nào. Sinh viên lưu ý không viết Kết chương giống hệt Tổng quan. Sau khi đọc phần Kết chương, người đọc sẽ nắm được sơ bộ nội dung và giải pháp cho các vấn đề đã trình bày trong chương. Trong Kết chương, Sinh viên nên có thêm câu liên kết tới chương tiếp theo.
Ví dụ về phần Kết chương: Chương này đã phân tích chi tiết sáu nhóm công cụ tích hợp dữ liệu. Nhóm công cụ ABC và DEF thích hợp với những bài toán tích hợp dữ liệu phạm vi nhỏ. Trong khi đó, nhóm công cụ GHK lại chứng tỏ thế mạnh của mình với những bài toán cần độ chính xác cao, v.v. Từ kết quả nghiên cứu và phân tích về sáu nhóm công cụ tích hợp dữ liệu này, tôi đã thực hiện phát triển phần mềm tự động bóc tách và tích hợp dữ liệu sử dụng nhóm công cụ GHK. Phần này được trình bày trong chương tiếp theo – Chương 5.
```

## Chapter 2 — Literature Review (hướng dẫn gốc)

`docs/thesis/Chapter/2_Literature_review.tex`

```text
Chương này có độ dài không quá 10 trang. Chương này sinh viên trình bày về phân tích rõ ngữ cảnh bài toán cũng như các kết quả nghiên cứu tương tự. Đồng thời, sinh viên có thể trình bày thêm về các kiến thức nền tảng.
\textbf{Lưu ý}: Mỗi chương nên có thêm 1 đoạn mở đầu chương và kết thúc chương, mở đầu giới thiệu những nội dung sẽ trình bày trong chương, kết thúc tổng kết lại các nội dung đã trình bày.
\ldots
Trong phần này sinh viên trình bày các nghiên cứu liên quan (related work), chú ý phân tích rõ những ưu nhược điểm của chúng. Từ đó, nêu bật lên động lực để thực hiện nghiên cứu của đồ án này.
\section{Tên của kiến thức nền tảng số 1}
Tiêu đề và nội dung của chương này sẽ thay đổi tuỳ thuộc vào từng đồ án. Chú ý trình bày những kiến thức có liên quan mật thiết nhất đối với đồ án của mình, Tránh trình bày lan man những kiến thức phổ thông không cần thiết. 
\section{Tên của kiến thức nền tảng số 2}
Tiêu đề và nội dung của chương này sẽ thay đổi tuỳ thuộc vào từng đồ án. Chú ý trình bày những kiến thức có liên quan mật thiết nhất đối với đồ án của mình, Tránh trình bày lan man những kiến thức phổ thông không cần thiết. 
```

## Chapter 3 — Methodology (hướng dẫn gốc)

`docs/thesis/Chapter/3_Methodology.tex`

```text
Phần này mô tả tổng quan giải pháp gồm những bước chính nào, hoạt động ra sao. Mục tiêu của phần này là cho người đọc một cái nhìn tổng thể về giải pháp. Để cho dễ hiểu thì nên có một biểu đồ mô tả luồng hoạt động của giải pháp đề xuất. 
\section{Tên của nội dung chi tiết thứ 1}
Tên của các chương này đặt theo nội dung mà sinh viên sẽ trình bày trong từng chương. 
Các chương tiếp theo mô tả chi tiết về các bước, các thuật toán trong giải pháp đề xuất. Có thể trình bày pseudocode cho từng bước. Chú ý, pseudocode chỉ có tác dụng làm chi tiết hoá giải thuật chứ không thay thế được phần thuyết minh về giải thuật. Đối với những chi tiết kỹ thuật khó hiểu nên có các hình minh hoạ để người đọc dễ hiểu. Mỗi một thuật toán/bước thực hiện nên tách ra thành một chương. 
\section{Tên của nội dung chi tiết thứ 2}
```

## Chapter 4 (cũ) — Theoretical Analysis (đã XOÁ khỏi luận văn, lưu lại để tham khảo)

`docs/thesis/Chapter/4_Theoretical_Analysis.tex`

```text

\textcolor{red}{Chú ý: Chương này là không bắt buộc. Nếu nghiên cứu chỉ có đánh giá thực nghiệm mà không có phần thích lý thuyết thì sinh viên không cần trình bày chương này.} 

\section{Tên của kết quả phân tích số 1}

Nếu đồ án có phần phân tích lý thuyết thì sinh viên trình bày ở chương này. 

Kết quả lý thuyết có thể là phần tính toán về độ phức tạp tính toán của thuật toán hoặc chứng minh về tỉ số hiệu năng, \ldots

Nếu đồ án không có phần phân tích lý thuyết thì sinh viên không cần viết chương này. 

\section{Tên của kết quả phân tích số 2}


```

## Chapter 5 (cũ, nay là Chapter 4) — Numerical Results (hướng dẫn gốc)

`docs/thesis/Chapter/5_Numerical_results.tex`

```text

\textcolor{red}{Chú ý: Chương này là không bắt buộc. Nếu nghiên cứu chỉ có phân tích lý thuyết mà không có thực nghiệm thì sinh viên không cần trình bày chương này }

\section{Evaluation Parameters}

Sinh viên trình bày cụ thể về các tham số dùng trong đánh giá 

\section{Simulation Method}

Sinh viên trình bày chi tiết cách thức tiến hành thí nghiệm, ví dụ: các baseline chọn để so sánh là gì? tại sao lại chọn các baseline đấy? Tiến hành bao nhiêu thí nghiệm? mỗi thí nghiệm được thực hiện bao nhiêu lần? Các tham số của thuật toán được chọn như thế nào? Kịch bản thí nghiệm được tạo ra sao? Dữ liệu xử lý thế nào? … Có thể chia  chương này thành các chương nhỏ hơn để tiện trình bày. 

\section{Tên của kết quả thí nghiệm 1}

Các chương tiếp theo sinh viên trình bày các kết quả thí nghiệm thu được. Mỗi kết quả nên cho vào một chương. Đối với mỗi kết quả thí nghiệm, cần trình bày các bảng biểu, đồ thị minh hoạ cho kết quả thí nghiệm. Sinh viên cần nêu nhận xét chi tiết về kết quả thí nghiệm, so sánh các phương pháp với nhau, giải thích tại sao kết quả lại như vậy. 

\section{Tên của kết quả thí nghiệm 2}

```

## Chapter 6 — Conclusions (hướng dẫn gốc)

`docs/thesis/Chapter/6_Conclusions.tex`

```text
Sinh viên nhắc lại các vấn đề mà đồ án đã giải quyết được, cũng như những vấn đề còn tồn đọng của đồ án.  
\section{Suggestion for Future Works }
Sinh viên đề xuất hướng phát triển trong tương lai (nếu có) .  
```

## Chapter 7 — SHORT NOTICES ON REFERENCE (chưa chỉnh sửa, vẫn là placeholder)

`docs/thesis/Chapter/7_Reference.tex`

```text
Lưu ý: Sinh viên không được đưa bài giảng/slide, các trang Wikipedia, hoặc các trang web thông thường làm tài liệu tham khảo. 

Một trang web được phép dùng làm tài liệu tham khảo \textbf{chỉ khi} nó là công bố chính thống của cá nhân hoặc tổ chức nào đó. Ví dụ, trang web đặc tả ngôn ngữ XML của tổ chức W3C \url{https://www.w3.org/TR/2008/REC-xml-20081126/} là TLTK hợp lệ.

Có năm loại tài liệu tham khảo mà sinh viên phải tuân thủ đúng quy định về cách thức liệt kê thông tin như sau. Lưu ý: các phần văn bản trong cặp dấu < > dưới đây chỉ là hướng dẫn khai báo cho từng loại tài liệu tham khảo; sinh viên cần xóa các phần văn bản này trong ĐATN của mình.

<\textbf{Bài báo đăng trên tạp chí khoa học}: Tên tác giả, tên bài báo, tên tạp chí, volume, từ trang đến trang (nếu có), nhà xuất bản, năm xuất bản >

\cite{hovy1993automated} E. H. Hovy, ``Automated discourse generation using discourse structure relations," \textit{Artificial intelligence}, vol. 63, no. 1-2, pp. 341–385, 1993

<\textbf{Sách}: Tên tác giả, tên sách, volume (nếu có), lần tái bản (nếu có), nhà xuất bản, năm xuất bản>

\cite{peterson2007computer}	L. L. Peterson and B. S. Davie, \textit{Computer networks: a systems approach}. Elsevier, 2007.

\cite{NguyenThucHai}	N. T. Hải, \textit{Mạng máy tính và các hệ thống mở}. Nhà xuất bản giáo dục, 1999. 

<\textbf{Tập san Báo cáo Hội nghị Khoa học}: Tên tác giả, tên báo cáo, tên hội nghị, ngày (nếu có), địa điểm hội nghị, năm xuất bản>

\cite{poesio2001discourse}	M. Poesio and B. Di Eugenio, ``Discourse structure and anaphoric accessibility," in \textit{ESSLLI workshop on information structure, discourse structure and discourse semantics}, Copenhagen, Denmark, 2001, pp. 129–143.

<\textbf{Đồ án tốt nghiệp, Luận văn Thạc sĩ, Tiến sĩ}: Tên tác giả, tên đồ án/luận văn, loại đồ án/luận văn, tên trường, địa điểm, năm xuất bản>

\cite{knott1996data}	A. Knott, ``A data-driven methodology for motivating a set of coherence relations," Ph.D. dissertation, The University of Edinburgh, UK, 1996.

<\textbf{Tài liệu tham khảo từ Internet}: Tên tác giả (nếu có), tựa đề, cơ quan (nếu có), địa chỉ trang web, thời gian lần cuối truy cập trang web>

\cite{BernersTim}	T. Berners-Lee, \textit{Hypertext transfer protocol (HTTP)}. [Online]. Available: \url{ftp:/info.cern.ch/pub/www/doc/http-spec.txt.Z} (visited on 09/30/2010).

\cite{LectureA} Princeton University, \textit{Wordnet}. [Online]. Available: \url{http://www.cogsci.princeton.edu/~wn/index.shtml} (visited on 09/30/2010).
```

## Appendix A — GRADUATION THESIS GUIDANCE (chưa chỉnh sửa, vẫn là placeholder)

`docs/thesis/Chapter/Appendix_A.tex`

Ghi chú quy định trình bày ĐATN nói chung: font/căn lề thống nhất theo template, cấm đạo văn, mọi hình/bảng/công thức/TLTK phải được giải thích và tham chiếu ít nhất một lần, không viết theo kiểu gạch đầu dòng (chỉ liệt kê La Mã khi thật cần), quy định về ngành/chuyên ngành ghi trên bìa và gáy, cách dùng `itemize`/`enumerate`, cách chèn bảng/hình/phương trình trong LaTeX, cách trích dẫn IEEE qua `\cite{}`, và quy cách đóng quyển (đóng gáy bằng keo nhiệt, thông tin ghi trên gáy).

```text
\section{General Regulations}
Dưới đây là một số quy định và hướng dẫn viết đồ án tốt nghiệp mà bắt buộc sinh viên phải đọc kỹ và tuân thủ nghiêm ngặt.

Sinh viên cần đảm bảo tính thống nhất toàn báo cáo (font chữ, căn dòng hai bên, hình ảnh, bảng, margin trang, đánh số trang, v.v.). Để làm được như vậy, sinh viên chỉ cần sử dụng các định dạng theo đúng template ĐATN này. Khi paste nội dung văn bản từ tài liệu khác của mình, sinh viên cần chọn kiểu Copy là "Text Only" để định dạng văn bản của template không bị phá vỡ/vi phạm.

Tuyệt đối cấm sinh viên đạo văn. Sinh viên cần ghi rõ nguồn cho tất cả những gì không tự mình viết/vẽ lên, bao gồm các câu trích dẫn, các hình ảnh, bảng biểu, v.v. Khi bị phát hiện, sinh viên sẽ không được phép bảo vệ ĐATN.

Tất cả các hình vẽ, bảng biểu, công thức, và tài liệu tham khảo trong ĐATN nhất thiết phải được SV giải thích và tham chiếu tới ít nhất một lần. Không chấp nhận các trường hợp sinh viên đưa ra hình ảnh, bảng biểu tùy hứng và không có lời mô tả/giải thích nào.

Sinh viên tuyệt đối không trình bày ĐATN theo kiểu viết ý hoặc gạch đầu dòng. ĐATN không phải là một slide thuyết trình; khi người đọc không hiểu sẽ không có ai giải thích hộ. Sinh viên cần viết thành các đoạn văn và phân tích, diễn giải đầy đủ, rõ ràng. Câu văn cần đúng ngữ pháp, đầy đủ chủ ngữ, vị ngữ và các thành phần câu.
Khi thực sự cần liệt kê, sinh viên nên liệt kê theo phong cách khoa học với các ký tự La Mã.

Trong một số trường hợp nhất thiết phải dùng các bullet để liệt kê, sinh viên cần thống nhất Style cho toàn bộ các bullet các cấp mà mình sử dụng đến trong báo cáo.

\section{Majoring}
Sinh viên lưu ý viết đúng ngành/chuyên ngành trên bìa và trên gáy theo đúng quy định của Trường. Ngành học hay chuyên ngành học phụ thuộc vào ngành học mà sinh viên đăng ký.

Một số ví dụ (trong trường hợp có chuyên ngành thì sinh viên không cần ghi chuyên ngành):
- Đối với kỹ sư chính quy: Từ K61 trở về trước: Ngành Kỹ thuật phần mềm; Từ K62 trở về sau: Ngành Khoa học máy tính
- Đối với cử nhân: Ngành Công nghệ thông tin
- Đối với chương trình EliteTech: Chương trình Việt Nhật/KSTN: Ngành Công nghệ thông tin; Chương trình ICT Global: Ngành Information Technology; Chương trình DS&AI: Ngành Khoa học dữ liệu

\section{Bulleting and Numbering}
Hướng dẫn dùng `itemize` (không thứ tự) và `enumerate` (có thứ tự) trong LaTeX. Nội dung trình bày theo sau lệnh `\item`.

\section{Table insertion}
Ví dụ tạo bảng bằng `tabular`, dùng `\caption`/`\label`, tham chiếu bằng `\ref{}`. Mọi bảng biểu phải được đề cập và phân tích trong nội dung. Gợi ý dùng công cụ hỗ trợ tạo bảng (tablesgenerator.com).

\section{Figure Insertion}
Ví dụ chèn ảnh bằng `\includegraphics`, `\caption` đặt ngay dưới hình. Mọi hình vẽ phải được đề cập và phân tích trong nội dung.

\section{Reference}
\paragraph{Listing} Áp dụng cách liệt kê theo quy định của IEEE, dùng lệnh `\cite{}`. Chỉ những tài liệu được trích dẫn mới xuất hiện trong Tài liệu tham khảo. Tài liệu tham khảo cần có nguồn gốc rõ ràng và đáng tin cậy; hạn chế trích dẫn từ website/Wikipedia.
\paragraph{Types of Reference} Các nguồn tài liệu tham khảo chính là sách, bài báo tạp chí, bài báo hội nghị khoa học và tài liệu tham khảo khác trên internet.

\section{Equations}
Ví dụ tạo phương trình có đánh số (`equation` + `\label` + `\eqref`) và không đánh số (`equation*`), dùng các gói amsmath/amssymb/amsfonts đã có sẵn trong main.tex.

\section{Qui cách đóng quyển}
Bìa trước/sau là giấy liền khổ, dán gáy bằng keo nhiệt (không dùng băng dính/dập ghim). Phần gáy ĐATN ghi: Kỳ làm ĐATN - Ngành đào tạo - Họ và tên sinh viên - Mã số sinh viên (ví dụ: `2022.1 - KỸ THUẬT MÁY TÍNH - NGUYỄN VĂN A - 20221234`).
```

## Appendix B — USE CASE DESCRIPTIONS (chưa chỉnh sửa, vẫn là placeholder)

`docs/thesis/Chapter/Appendix_B.tex`

Placeholder ví dụ cho một đề tài quản lý thư viện (không liên quan tới AlignmentGraph-ISD), dùng để minh hoạ chỗ đặc tả thêm các use case phụ khi nội dung chính không đủ chỗ.

```text
Nếu trong nội dung chính không đủ không gian cho các use case khác (ngoài các use case nghiệp vụ chính) thì đặc tả thêm cho các use case đó ở đây.

\section{Đặc tả use case ``Thống kê tình hình mượn sách''}
\ldots

\section{Đặc tả use case ``Đăng ký làm thẻ mượn''}
\ldots
```
