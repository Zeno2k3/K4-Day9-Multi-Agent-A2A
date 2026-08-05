# Member Role Report — Day 9: Multi Agent A2A

> Ghi chú: mục 7 của template gốc chứa các câu hỏi của một lab khác (Crossref/vector index/retrieval) không liên quan tới bài lab e-commerce dispute resolution này. Tôi đã thay bằng 5 câu hỏi tương đương về luồng end-to-end của chính lab này, giữ nguyên tinh thần "hiểu toàn bộ pipeline, không chỉ phần mình phụ trách".

## 1. Thông tin cá nhân

| Thông tin       | Nội dung        |
| --------------- | --------------- |
| Họ và tên       | Trần Minh Quân  |
| MSSV            | 2A202601768     |
| Khóa/Lớp        | K4              |
| Vai trò chính   | Full Stack (solo — toàn bộ hệ thống) |
| Ngày hoàn thành | 2026-08-05      |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

Làm solo nên sở hữu toàn bộ pipeline, từ data layer đến output cuối cùng.

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------- | ------------------- | --------------- | ----------------- | ---------- |
| Data layer | `src/data/loader.py::load_data_store` | 7 CSV Olist | `DataStore` đã index theo order_id/customer_unique_id/seller_id/product_id | Hoàn thành |
| Deterministic tools | `src/tools/{order,customer,payment,delivery,policy}_tools.py`, `evidence.py`, `confidence.py` | Records từ `DataStore` | Số liệu/ID/quyết định chính sách tất định | Hoàn thành |
| LLM client & prompts | `src/llm/groq_client.py`, `src/llm/prompts.py` | Fact sheet đã tính sẵn | JSON boolean/enum đóng từ Groq | Hoàn thành |
| 6 domain agent + Coordinator | `src/agents/*.py` | Case input + `DataStore` | Handoff pydantic model giữa các agent | Hoàn thành |
| Verifier Agent | `src/agents/verifier_agent.py` | Draft output | Output đã sửa lỗi cấu trúc + corrections | Hoàn thành |
| Runner + CLI | `src/runner.py`, `main.py` | `input/EC_0NN.json` × 50 | `output/EC_0NN.json` × 50, `trace.jsonl`, `metadata.json` | Hoàn thành |
| architecture.md | `architecture.md` | Toàn bộ thiết kế trên | Tài liệu kiến trúc | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ------------------------------ | -------- |
| Không áp dụng (làm solo) | — | — |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| ---------------------- | ---------------------------- | ------------------ | -------------- |
| Chạy dry-run 50 case (không gọi Groq) để bắt lỗi cấu trúc rẻ trước khi tốn API | `main.py --dry-run` | 50/50 succeeded, 0 exception, 0 policy_edge_case | `python main.py --dry-run` |
| Chạy thật 50 case qua Groq | `main.py` | `output/EC_001.json`…`EC_050.json`, `logging/trace.jsonl`, `logging/metadata.json` | `python main.py`, kiểm tra `output/` có đúng 50 file |
| Validate schema toàn bộ output | script kiểm tra ad-hoc dùng `src/schemas/output_models.CaseOutput` | 0 lỗi validate trên 50/50 file | `CaseOutput.model_validate(...)` từng file |

Một output cụ thể: `output/EC_012.json` — case `unavailable`, 0 item row. Hệ thống trả đúng `item_total_brl=0.0` (không null) nhưng `expected_total_brl/difference_brl/reconciled=null`, `recommended_refund_brl=226.23` (đúng bằng `payment_total_brl`), evidence chỉ gồm `order:`/`payment:`/`policy:` (không có `item:`/`seller:` vì order không có item) — khớp chính xác cách đọc README §4 về null-handling cho order không có item.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Bài toán chấm điểm theo exact-match tuyệt đối (so khớp ID, số tiền, giờ chênh lệch với ground truth suy từ CSV), nhưng đề bài lại yêu cầu multi-agent có LLM thật, có handoff, có kiểm chứng — không được là "một prompt lớn gắn tên nhiều agent". Hai yêu cầu này xung đột nhau nếu để LLM 8B tham số tự do sinh số liệu/ID (rủi ro hallucination rất cao ở model nhỏ).

### Cách triển khai

Tách bạch tuyệt đối: mọi ID/số tiền/giờ/ngày đều do hàm Python tất định tính từ `DataStore` (không LLM nào chạm vào các trường này). Mỗi agent có LLM đều tính sẵn "đáp án đúng" bằng code, gọi Groq hỏi lại đúng câu hỏi đó dưới dạng JSON boolean/enum đóng, rồi so sánh — nếu lệch thì giá trị tất định vẫn thắng nhưng sự bất đồng được log thật vào `trace.jsonl` và trừ điểm `confidence` (công thức tại `src/tools/confidence.py`). Evidence được ghép từ chính các ID đã build từ `DataStore` (`src/tools/evidence.py::build_evidence_ids`), không bao giờ do LLM gõ ra, nên "false positive evidence" không thể xảy ra về mặt cấu trúc; Verifier vẫn kiểm tra lại độc lập bằng `filter_valid_evidence` như lớp phòng thủ thứ hai.

### Input, output và contract

| Thành phần | Mô tả |
| ----------- | ------ |
| Input | `input/EC_0NN.json` (case_id, claimed_order_id, investigation_scope, policy_version) + 7 CSV Olist |
| Output | `output/EC_0NN.json` theo schema README §6, validate bằng `src/schemas/output_models.CaseOutput` (`extra="forbid"`) |
| Module phụ thuộc | `src/data/loader.py` (DataStore), `src/llm/groq_client.py` (Groq API) |
| Module sử dụng output | `src/runner.py` ghi file, không có module downstream nào khác trong repo |
| Điều kiện lỗi cần xử lý | Order không tồn tại trong CSV, Groq timeout/rate-limit/JSON không parse được, order 0 item, order chưa delivered, case nào đó raise exception không lường trước |

### Cách xác minh

```bash
python main.py --dry-run --case-ids EC_001,EC_012,EC_004
python main.py --dry-run
python main.py --case-ids EC_001,EC_012,EC_004
python main.py
```

- **Kết quả mong đợi:** 50/50 case thành công, đúng 50 file output, 0 lỗi schema, evidence luôn tồn tại thật trong CSV.
- **Kết quả thực tế:** 50/50 thành công cả dry-run lẫn run thật; 300/300 lệnh gọi Groq thành công (50 case × 6 agent); 0 lần Verifier phải sửa dữ liệu (evidence/mảng/null-handling đã đúng ngay từ đầu); `mean_confidence=0.777`, dao động 0.3–1.0 tuỳ số lần LLM bất đồng thật với deterministic engine.
- **Artifact/log:** `logging/trace.jsonl` (không chứa secret), `logging/metadata.json`, `output/EC_001.json`…`EC_050.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần vừa đảm bảo output đúng tuyệt đối với ground truth tất định, vừa phải có LLM tham gia thật (không phải chỉ đặt tên agent) theo yêu cầu chấm điểm README §7/§9.
- **Các phương án đã cân nhắc:**
  1. Để LLM tự do sinh toàn bộ output JSON theo schema (rủi ro hallucinate ID/số tiền rất cao với model 8B, không thể đảm bảo exact-match).
  2. Chạy hoàn toàn tất định, không gọi LLM thật, chỉ log giả một số câu như thể "agent nói" (vi phạm tinh thần đề bài, dễ bị phát hiện qua trace không có lệnh gọi API thật).
  3. **(Đã chọn)** LLM chỉ trả lời boolean/enum đóng để cross-check lại giá trị đã tính tất định; giá trị tất định luôn thắng khi ghi ra output, bất đồng được log thật.
- **Phương án đã chọn:** Phương án 3.
- **Lý do:** Đảm bảo đúng 100% với exact-match grading vì LLM không có kênh nào ghi trực tiếp ID/số tiền vào output, đồng thời vẫn có LLM reasoning thật, có ý nghĩa, có thể kiểm chứng qua trace — đúng yêu cầu "phân công, handoff và kiểm chứng giữa các agent" của README §7.
- **Bằng chứng quyết định phù hợp:** `logging/trace.jsonl` case `EC_022` — Policy Agent LLM đề xuất sai `primary_issue` (`unsupported_late_claim` thay vì `valid_split_payment` đúng theo thứ tự ưu tiên EC_POLICY_V2), bất đồng này được ghi log thật (`llm_agrees: false`) và kéo `confidence` xuống 0.3, nhưng **output cuối cùng vẫn đúng** vì giá trị tất định được ghi ra, không phải giá trị LLM đề xuất.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** API key Groq thật bị đặt nhầm vào `.env.example` (file dự định sẽ được commit lên git làm template) thay vì `.env` (file đã có trong `.gitignore`).
- **Lệnh hoặc bước tái hiện:** Xảy ra trong lúc thiết lập `.env.example` ban đầu — file bị ghi đè với nội dung chứa key thật thay vì placeholder `your_groq_api_key_here`.
- **Nguyên nhân gốc:** Nhầm lẫn giữa file template (`.env.example`, dự định commit) và file cấu hình thật (`.env`, không commit) khi dán giá trị key vào.
- **Cách xử lý:** Tạo `.env` (đã nằm trong `.gitignore`) chứa key thật, ghi đè lại `.env.example` về giá trị placeholder ban đầu.
- **Cách xác minh sau khi sửa:** Chạy `git status` xác nhận `.env` không xuất hiện trong danh sách file sẽ được track; gọi thử Groq API bằng key trong `.env` (`python -c "..."` gửi 1 request test) trả về `"OK"` thành công, xác nhận key vẫn hoạt động đúng sau khi di chuyển.
- **Điều học được:** Luôn tạo `.gitignore` chứa `.env` trước khi tạo bất kỳ file cấu hình nào có khả năng chứa secret, và luôn `git status` kiểm tra lại trước khi commit dù chỉ là file "example".

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn (5 câu hỏi đã điều chỉnh cho đúng nội dung lab này — xem ghi chú đầu file):

1. Dữ liệu đi từ CSV Olist đến `output/EC_0NN.json` như thế nào?
2. Vì không có ground-truth chính thức, hệ thống dùng gì để tự đối chiếu đúng/sai trước khi nộp bài?
3. Ngoài dry-run, còn quality check nào khác tồn tại trong pipeline?
4. Vì sao phải dùng cùng bộ 50 case cho cả lượt dry-run và lượt chạy thật với Groq?
5. Một correction của Verifier được xem là "thành công" dựa trên artifact/metric nào?

**Câu trả lời:**

1. `main.py` đọc từng `input/EC_0NN.json`, lấy `claimed_order_id`, đưa vào `Coordinator.run_case`. Coordinator gọi lần lượt Order & Product → Customer → Payment → Delivery Agent, mỗi agent tra `DataStore` (đã nạp toàn bộ CSV vào RAM và index sẵn) để lấy dữ liệu domain của mình, tính số liệu tất định, rồi hỏi Groq một câu hỏi đóng để cross-check. Coordinator gộp 4 kết quả thành `CaseFacts`, đưa cho Policy Agent để áp bảng EC_POLICY_V2, rồi đưa toàn bộ draft cho Verifier kiểm tra/sửa lần cuối trước khi Coordinator ghi ra `output/EC_0NN.json`.
2. Vì Olist không có ground-truth chính thức cho từng case, "ground truth" thực chất chính là kết quả suy ra tất định từ bảng EC_POLICY_V2 áp lên CSV — đây là lý do toàn bộ logic tính toán (không phải LLM) phải đúng tuyệt đối. Việc tự đối chiếu được thực hiện bằng cách chạy `--dry-run` (không tốn API) trên cả 50 case thật, kiểm tra 0 exception và 0 case rơi vào nhánh chính sách chưa định nghĩa (`policy_edge_case`), rồi đọc tay vài case đại diện (0-item, canceled, multi-seller, split-payment) so với CSV gốc.
3. Có: schema validation bằng pydantic (`extra="forbid"`, giới hạn mảng, `Literal` cho enum) chạy ngay khi lắp output; Verifier kiểm tra tồn tại thật của từng evidence ID trong CSV (không chỉ tin tưởng dữ liệu đã build); rounding lại toàn bộ số thực về 2 chữ số để tránh sai số float.
4. Vì đó là cách duy nhất để tách bạch "lỗi cấu trúc do code" (sẽ lộ ra ở cả hai lượt) với "hành vi của LLM thật" (chỉ khác nhau giữa hai lượt) — nếu dry-run đã sạch mà lượt thật vẫn lỗi thì biết chắc nguyên nhân nằm ở tầng gọi Groq (timeout, JSON không parse được...) chứ không phải ở logic tất định.
5. Dựa trên số dòng `event: "correction"` trong `logging/trace.jsonl` (mỗi dòng có `field/before/after/reason`) và số liệu tổng hợp: trong lượt chạy thật 50 case, số correction là 0 — nghĩa là dữ liệu output đã đúng cấu trúc/giới hạn/evidence ngay từ khi Coordinator lắp draft, Verifier chỉ đóng vai trò lưới an toàn chứ không phải bước sửa lỗi bắt buộc.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Minh Quân
**Ngày xác nhận:** 2026-08-05
