# Khảo sát: vấn đề triển khai LLM trong giáo dục & khoảng trống của các ISD agent

> Tư liệu cho abstract (xác minh claim) và lit review (Intro §4.1–4.4, Related Work).
> Cập nhật 2026-07-15. Trạng thái xác minh: ✅ = đã đọc abstract/metadata gốc; 🔎 = đang chờ xác minh thêm.

## A. Nhóm citation cho vấn đề ② (thực tiễn triển khai: chi phí + privacy → open-weight/SLM)

### ✅ Chan et al. 2026 — "Bigger Isn't Always Better: Choosing the Right Size LLM for Locally Hosted School Settings"
- Cecilia Ka Yuk Chan, Wei Dai, Kepan Cao, Alan T. Y. Poon, Tom Colloton. *Applied Sciences* 16(11):5268, 2026. doi:10.3390/app16115268.
- Nội dung: đánh giá LLaMA open-source 1B–70B tự host cho trường học; model nhỏ (1B–3B) nhanh và ổn định hơn dưới tải đồng thời; đưa guidance chọn model tự host cho giáo dục.
- Hỗ trợ claim: **trường học tự host open-weight model nhỏ là xu hướng thực tế**; dùng ở Intro (bối cảnh thực tiễn) + Related Work.

```bibtex
@article{chan2026bigger,
  title={Bigger Isn't Always Better: Choosing the Right Size Large Language Model for Locally Hosted School Settings},
  author={Chan, Cecilia Ka Yuk and Dai, Wei and Cao, Kepan and Poon, Alan T. Y. and Colloton, Tom},
  journal={Applied Sciences},
  volume={16},
  number={11},
  pages={5268},
  year={2026},
  doi={10.3390/app16115268}
}
```

### ✅ Zesch et al. 2024 — FLEXI (open LLM infrastructure cho higher education)
- Torsten Zesch, Michael Hanses, Niels Seidel, Piush Aggarwal, Dirk Veiel, Claudia de Witt. arXiv:2407.13013, 2024.
- Nội dung: hạ tầng open-LLM tại FernUniversität Hagen; so sánh thực tế "trả tiền cloud LLM vs. tự vận hành open LLM" cho cơ sở giáo dục.
- Hỗ trợ claim: cơ sở giáo dục cân nhắc tự host open LLM (chi phí/kiểm soát/tiếp cận). Lưu ý: abstract không nói thẳng "privacy" — khi trích cần diễn đạt theo hướng access/cost/control.

```bibtex
@article{zesch2024flexi,
  title={FernUni LLM Experimental Infrastructure (FLEXI) -- Enabling Experimentation and Innovation in Higher Education Through Access to Open Large Language Models},
  author={Zesch, Torsten and Hanses, Michael and Seidel, Niels and Aggarwal, Piush and Veiel, Dirk and de Witt, Claudia},
  journal={arXiv preprint arXiv:2407.13013},
  year={2024}
}
```

### ✅ Pan et al. 2025 — cost-benefit on-premise vs commercial LLM
- Guanzhong Pan, Vishal Chodnekar, Abinas Roy, Haibo Wang. "A Cost-Benefit Analysis of On-Premise Large Language Model Deployment: Breaking Even with Commercial LLM Services." arXiv:2509.18101, 2025.
- Nội dung: khung phân tích điểm hoà vốn; ở mức sử dụng đủ cao, tự host open-source model (Qwen, Llama, Mistral) rẻ hơn API thương mại.
- Hỗ trợ claim: **chi phí inference là động lực chuyển sang self-host** (tổng quát, không riêng giáo dục) — dùng phụ trợ ở Intro.

```bibtex
@article{pan2025onpremise,
  title={A Cost-Benefit Analysis of On-Premise Large Language Model Deployment: Breaking Even with Commercial LLM Services},
  author={Pan, Guanzhong and Chodnekar, Vishal and Roy, Abinas and Wang, Haibo},
  journal={arXiv preprint arXiv:2509.18101},
  year={2025}
}
```

### Đã có sẵn trong `references.bib`
- `belcak2025slm` — SLM là tương lai của agentic AI (chi phí, đủ năng lực cho tác vụ agent).
- `cho2026harness` — harness sensitivity theo tier model (kỹ thuật ②-2).
- `shukla2025scalingwall`, `deveci2025ouroboros` — bão hoà năng lực model nền.

## B. Nhóm citation cho bối cảnh ① (LLM ứng dụng rộng vào giáo dục)

### ✅ Wang et al. 2024 — "Large Language Models for Education: A Survey and Outlook"
- Shen Wang, Tianlong Xu, Hang Li, et al. arXiv:2403.18105, 2024.
- Survey ứng dụng LLM trong giáo dục (student support, instructor assistance, personalized learning, nền tảng thương mại).
- Hỗ trợ claim ①: LLM được ứng dụng ngày càng rộng vào giáo dục. Lưu ý: là survey công nghệ, không phải nghiên cứu đo mức độ adoption — trích ở mức "ứng dụng ngày càng rộng", không claim số liệu adoption.

```bibtex
@article{wang2024llmedu,
  title={Large Language Models for Education: A Survey and Outlook},
  author={Wang, Shen and Xu, Tianlong and Li, Hang and Zhang, Chaoli and Liang, Joleen and Tang, Jiliang and Yu, Philip S. and Wen, Qingsong},
  journal={arXiv preprint arXiv:2403.18105},
  year={2024}
}
```

## C. Nhóm xác minh khoảng trống ③ (ISD agent hiện có tập trung automation/quality, không tập trung triển khai)

### ✅ Survey "LLM Agents for Education: Advances and Applications" (arXiv:2503.11733)
- Mục curriculum design (§3.3): các agent tập trung **personalization, automation, quality/explainability**.
- **Không bàn** chi phí inference; **không bàn** open-weight/SLM; privacy chỉ nhắc thoáng ở §5.1 challenges.
- → Bằng chứng survey-level cho khoảng trống.

### ✅ Instructional Agents (Yao et al., arXiv:2508.19611) — đã có trong bib (`yao2025instructionalagents`)
- Mục tiêu: **giảm workload giảng viên + chất lượng** ("scalable and cost-effective framework to democratize access"); "cost-effective" ở nghĩa giảm công sức con người, không phải chi phí model.
- Abstract **không nhắc** SLM/open-weight/inference cost/privacy.

### ✅ Scoping review pedagogical agents (Li, Zheng, et al., arXiv:2604.12253, 2026)
- Phân loại agent theo interaction/domain/role/integration; nêu "significant research gaps" và ethical concerns (privacy, accuracy, autonomy) là vấn đề **chưa được giải quyết** trong văn liệu.
- **Không có** nhóm công trình nào về triển khai SLM/open-weight → củng cố khoảng trống.

### ✅ 6 hệ ISD/lesson-plan agent tiêu biểu — đã xác minh từng paper (dựa trên abstract + metadata gốc)

| Paper | Venue/Năm | DOI | Focus | SLM/open-weight/cost/privacy? |
|---|---|---|---|---|
| COMA | WWW '26 | 10.1145/3774904.3792982 | 3 agent vai trò sư phạm cộng tác lặp; automation + quality/coherence | **No mention** |
| AgentLesson | BESC 2025 / LNCS 16431 (2026), tr. 155–170 | 10.1007/978-981-95-7138-3_11 | Writer + Evaluator (rubric 5 chiều, Gagné); automation + iterative quality | **No mention** |
| EduPlanner | IEEE TLT 18 (2025), tr. 416–427 | 10.1109/TLT.2025.3561332 | Evaluator/optimizer/analyst đối kháng; customization + optimization | **No mention** |
| LessonPlanner | UIST '24 | 10.1145/3654777.3676390 | Công cụ tương tác cho novice teacher (Gagné); giảm workload + quality (dùng ChatGPT) | **No mention** |
| Hu et al. | IEEE TLT 17 (2024), tr. 1471–1485 | 10.1109/TLT.2024.3384765 | Đánh giá năng lực GPT-4 sinh teaching plan (toán THPT) | **No mention** |
| Self-critique | AIED 2024 companion, tr. 163–178 | 10.1007/978-3-031-64315-6_13 | RAG + self-critique + refinement; automation cá nhân hoá | **No mention** |

- **Kết luận**: cả 6 abstract đều motivate bằng automation / giảm workload / quality-pedagogical alignment / personalization; mặc định LLM thương mại lớn (paper 4, 5 nêu đích danh GPT-4/ChatGPT). Không paper nào coi SLM, open-weight/self-host, chi phí inference hay privacy của API thương mại là mối quan tâm thiết kế.
- Caveat: xác minh ở mức abstract; nếu reviewer thách thức, đọc full text COMA và EduPlanner (2 đối thủ gần nhất).
- Bib entry mới cần thêm (chưa có trong `references.bib`): COMA, Hu et al. cần sửa DOI/pages (bib hiện ghi tr. 1445–1459 — **số đúng là 1471–1485, DOI 10.1109/TLT.2024.3384765**), LessonPlanner cần bổ sung DOI.

```bibtex
@inproceedings{zeng2026coma,
  title={COMA: A Collaborative Multi-Role Agent Framework for Automated Lesson Plan Generation},
  author={Zeng, Xiaoli and Zheng, Ying and Huang, Shuyan and Liu, Zitao and Tian, Mi and Hou, Mingliang and Zheng, Jia-qi and Dou, Wenzhou},
  booktitle={Proceedings of the ACM Web Conference 2026 (WWW '26)},
  pages={9745--9756},
  year={2026},
  doi={10.1145/3774904.3792982}
}

@inproceedings{zheng2024selfcritique,
  title={Automatic Lesson Plan Generation via Large Language Models with Self-critique Prompting},
  author={Zheng, Ying and Li, Xueyi and Huang, Yaying and Liang, Qianru and Guo, Teng and Hou, Mingliang and Gao, Boyu and Tian, Mi and Liu, Zitao and Luo, Weiqi},
  booktitle={Artificial Intelligence in Education. Posters and Late Breaking Results, Workshops and Tutorials, Industry and Innovation Tracks, Practitioners, Doctoral Consortium and Blue Sky (AIED 2024)},
  pages={163--178},
  year={2024},
  publisher={Springer},
  doi={10.1007/978-3-031-64315-6_13}
}
```

### ✅ Kiểm tra phản ví dụ (falsification search) — 3 "danger papers" cần dẫn và phân biệt

**(a) Reza et al. 2025 — "Small Models, Big Support" (arXiv:2506.05925)** — `reza2025smallmodels`
- Framework local-LLM (LangGraph, model open-weight 3B–7B tự host) cho giáo viên tạo bài tập/rubric/chấm điểm; motivate ĐÚNG bằng privacy + cost + institutional sovereignty.
- **Không phải ISD**: sinh content authoring/assessment đơn lẻ, không có quy trình thiết kế giảng dạy (không ADDIE, không objective–assessment–activity alignment); pipeline RAG/CAG một-LLM, không phải multi-agent ISD.
- ⚠️ Đây là paper reviewer sẽ dẫn nếu ta claim "none" quá rộng → PHẢI cite và phân biệt trong Related Work.

**(b) LessonPlanLM — Zheng et al. 2025, *Humanities and Social Sciences Communications* 12:1784, doi:10.1057/s41599-025-06004-2** — `zheng2025lessonplanlm`
- **Fine-tune Qwen2-7B** với knowledge base lesson-plan; bản 7B thắng GPT-4/GLM-4/Claude 3.5/Gemini 1.5 Pro về chất lượng lesson plan.
- Là fine-tuning framework, **không phải agent system**; motivate bằng chất lượng, không phải deployment. → Điểm phân biệt của ta: **không cần fine-tune**, chất lượng do harness.

**(c) Instructional Agents (Yao et al., arXiv:2508.19611)** — có báo cáo **chi phí $/course** ($0.22–$0.36) và kết luận GPT-4o-mini cân bằng quality/cost tốt nhất "for scalable deployment".
- Nhưng GPT-4o-mini là **API thương mại**, không phải open-weight/SLM; cost là metric báo cáo, không phải design constraint/RQ; không bàn privacy.
- → Không được claim "không hệ nào quan tâm chi phí"; phải nói "cost chỉ xuất hiện như metric báo cáo/limitation, không phải ràng buộc thiết kế".

**Near-misses (ủng hộ claim):** EduPlanner dùng Llama-3-**70B** casual cạnh GPT-4, cost chỉ nêu ở limitation; CourseGPT-zh (distillation nhưng là chatbot Q&A, không phải ISD); RAM2C (chatbot đa vai, không phải ISD); UBC LLM Sandbox (hạ tầng, không phải ISD agent).

**Wording an toàn cho claim ③** (dùng cho Intro/Related Work):
> Các hệ LLM-agent ISD/lesson-plan hiện có [EduPlanner, AgentLesson, Instructional Agents, COMA, …] nhắm automation, giảm workload, chất lượng và cá nhân hoá, được thiết kế và đánh giá trên các frontier model thương mại; chi phí nhiều nhất chỉ xuất hiện như một metric báo cáo [Instructional Agents] hoặc một limitation [EduPlanner]. Các công trình lân cận đã bắt đầu chạm tới triển khai cục bộ — một framework RAG một-LLM cho content authoring trên model 3–7B tự host [reza2025smallmodels] và một model 7B fine-tune cho chất lượng lesson plan [zheng2025lessonplanlm] — nhưng, theo hiểu biết của chúng tôi, **chưa có hệ agentic instructional-design nào coi triển khai SLM/open-weight (chi phí inference, riêng tư dữ liệu trong cơ sở giáo dục) là ràng buộc thiết kế hạng ưu tiên, và chưa hệ nào duy trì chất lượng ISD trên model nhỏ mà không cần fine-tune**.

## D. Kết luận khảo sát

1. **Claim ② đứng vững**: có citation trực tiếp cho cả hai vế (chi phí + privacy → open-weight/SLM tự host trong giáo dục: chan2026bigger, zesch2024flexi, pan2025onpremise, belcak2025slm).
2. **Claim ③ đứng vững khi scope đúng, KHÔNG được viết dạng "none" tuyệt đối**: cả 6 hệ ISD agent tiêu biểu đều "no mention" về SLM/deployment, nhưng tồn tại 3 danger papers (mục C) — mỗi qualifier trong claim ("agentic", "instructional-design", "không fine-tune") đều load-bearing. Dùng wording an toàn ở cuối mục C, kèm "theo hiểu biết của chúng tôi", và **chủ động cite + phân biệt** reza2025smallmodels và zheng2025lessonplanlm trong Related Work thay vì hy vọng reviewer không thấy.
3. Abstract không chứa citation (theo guide) — các entry trên dùng cho Intro/Related Work. Trong abstract, claim đã được scope vào "các LLM-agent ISD hiện có" nên vẫn đúng.
4. Nếu reviewer thách thức sâu: đọc full text COMA và EduPlanner (2 đối thủ gần nhất, hiện mới xác minh mức abstract).
