# Kiểm tra key, đo tốc độ và chuyển máy

Trạng thái mới nhất (2026-11-01): mạng đã hoạt động sau khi chuyển phiên sang Full Access. Đã phân loại 220 credential/account binding duy nhất bằng request xác thực hoặc inference thật. Có **99 credential tạo text thành công khi tắt thinking**, cộng 2 credential phụ trợ (Tavily/Jina). Không coi xác thực thành công là đã dịch được.

| Provider | Credential text đã chạy | Model đã chạy |
| --- | ---: | --- |
| Cloudflare | 23 | GLM-4.7-Flash, Gemma 4 26B A4B, Llama 3.3 70B Fast |
| NVIDIA | 21 | Nemotron 3.5 Lightning 30B A3B |
| Ollama Cloud | 19 | Gemma 4 31B Cloud |
| Google AI | 14 | Gemini 2.5 Flash / Flash Lite |
| OpenRouter | 22 | Nemotron 3 Nano Omni 30B A3B, reasoning disabled |

Đã làm sạch `.env` và TXT: chỉ giữ 101 credential được xác minh theo đúng chức năng; không có key trùng, lỗi hoặc chưa xác minh trong bộ active. Bản gốc trước làm sạch được giữ riêng ở `.secrets/env-before-clean-1793503619519030801` (0600). 69 credential sai xác thực được cách ly. 31 credential Google chưa tạo text thành công vì quota/xác thực-only, cùng các trường hợp thiếu quyền hoặc không có model dùng được, đều không được xuất. Chúng còn trong bản kiểm kê riêng tư để phân biệt lỗi tạm thời với key sai vĩnh viễn. Datalab không có key thành công.

Thinking đã tắt trong payload từng provider và cấu hình xuất; loại model không cho tắt. Bài kiểm tra loại cặp key/model khi một lượt trả reasoning hoặc thiếu ý. Một cặp Cloudflare không đạt GLM được kiểm tra lại bằng Gemma 4, đạt cả 3 mẫu.

Số đo nhận đủ output trên mẫu ngắn: Cloudflare Llama 70B median 0,6088s (3 mẫu/1 key), GLM 0,6222s (53 mẫu/18 key), Gemma 4 0,7915s (11 mẫu/4 key). NVIDIA median 0,6279s, Ollama 0,7201s. P95 Cloudflare GLM/Gemma và OpenRouter cao hơn nhiều median; xem báo cáo đầy đủ, không coi đây là bảo đảm mọi request nhanh. Cloudflare Free có hạn mức [10.000 Neurons/ngày](https://developers.cloudflare.com/workers-ai/platform/pricing/); không phải vô hạn. Các model yêu cầu Paid không được chọn tự động.

## Chạy kiểm tra trong terminal có mạng

Từ thư mục project:

```bash
python3 tools/key_audit.py audit --env .env --repeats 3
```

Không cần cài thư viện Python hoặc đưa key vào tham số lệnh. Công cụ chỉ dùng các endpoint chính thức cố định, không đi theo redirect có thể mang key tới nơi khác.

Đầu ra:

- `reports/key-benchmark.txt`: bảng đọc được, key chỉ có ID che.
- `reports/key-benchmark.csv`: thời gian nhận đủ response của từng lần gọi model, kết quả và số ký tự output.
- `reports/key-benchmark.json`: số liệu và trạng thái chi tiết, không chứa secret.
- `exports/q-translate-import.txt`: file JSON dạng TXT **chỉ có credential và model đã kiểm tra thành công**; quyền `0600`, thư mục mới `0700`, bị loại khỏi Git.
- `.secrets/key-audit-inventory.json`: bản kiểm kê riêng tư, gồm cả phần chưa xác minh để tiếp tục xử lý; không phải file import dùng chính thức. Backup của export cũ cũng chỉ ở `.secrets/portable-backups/`.

File import hiện chứa 101 credential đã xác minh theo chức năng. Lỗi mạng, quota, 403 hoặc thiếu capability vẫn được phân loại riêng; loại khỏi bộ active theo yêu cầu người dùng, giữ bản kiểm kê và backup riêng tư, không gắn nhãn sai xác thực vĩnh viễn.

Audit text thử các model khai báo trước; khi không dùng được thì khám phá model từ endpoint của provider trong ngân sách validation. OpenRouter discovery chỉ chọn model có giá input/output bằng 0. Mỗi key thành công được đo bằng bộ câu ngắn Việt, Anh và hỗn hợp; xếp hạng provider/model bằng median các lượt thành công và ghi p95 cùng số mẫu. Provider khác model vẫn có thể khác độ dài output/độ trễ; đây là số đo tham khảo trên máy và thời điểm thử, không phải bảo đảm nhanh nhất trong mọi trường hợp. Model được liệt kê chưa đủ chứng minh hoạt động. Chưa benchmark AI vision hoặc chất lượng dịch bằng review con người.

Tavily thử endpoint usage, Jina thử một embedding ngắn, Datalab gửi một PDF mẫu một trang rồi chờ job hoàn tất. Chúng được phân loại riêng và không tham gia xếp hạng tốc độ viết lại tiếng Anh. Các request thử dùng quota/credit của dịch vụ theo cấu hình hiện có. Chiến lược đo của tool audit không phải controller deadline cho app desktop.

## Import sang máy khác

Copy file TXT đã có credential được xác minh cùng `tools/key_audit.py`, rồi chạy:

```bash
python3 tools/key_audit.py import --bundle q-translate-import.txt --out .secrets/credentials-imported.json
```

Không thực thi TXT như shell script. File giữ provider, model đã chạy được, key, account binding và số đo; không phụ thuộc đường `.env` cũ. Import lọc lại theo trạng thái verified-only. Native dashboard import chưa được triển khai; lệnh này hiện là công cụ import độc lập.

## Nhớ lần thành công gần nhất

Spec đã đổi từ luân phiên sau mỗi thành công sang giữ provider/key/model vừa thành công cho từng luồng. `remember_success` ghi state riêng tư và `route_candidates` tạo một vòng ứng viên key trước, provider sau, bắt đầu từ state đã nhớ. Khi chưa có state hợp lệ, dùng median TTFT: provider được xếp theo model nhanh nhất của provider, model trong từng provider nhanh trước. Giữ quy tắc key trước/provider sau nên không xen provider khác vào giữa pool Cloudflare. Hết vòng quay về đầu cho lượt tiếp theo; controller phải xử lý cooldown và deadline tổng 30 giây, không lặp request vô hạn.

Các helper này có kiểm tra offline; chưa được nối vào app desktop vì app native chưa được xây. Benchmark không tự ghi đè state thành công của tác vụ người dùng. Sau yêu cầu mới nhất ưu tiên model nhanh, đã xóa override khởi đầu Gemma 4 cũ khỏi state text và chọn Cloudflare/Llama 3.3 70B Fast làm mặc định. Không giả lập tác vụ người dùng thành công để ghi last_success; lần chạy thành công tiếp theo sẽ được nhớ như trước. Đây vẫn là cấu hình/helper, chưa phải runtime app desktop.

## Tài liệu API đã đối chiếu

- [Gemini generateContent](https://ai.google.dev/api)
- [Ollama cloud authentication](https://docs.ollama.com/api/authentication)
- [OpenRouter chat completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion)
- [NVIDIA model endpoint](https://docs.api.nvidia.com/nim/docs/models), [model catalog](https://docs.nvidia.com/nim-operator/latest/guardrail.html)
- [Cloudflare AI endpoints](https://developers.cloudflare.com/api/resources/ai/)
- [Tavily usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage)
- [Jina API](https://docs.jina.ai)
- [Datalab Marker](https://documentation.datalab.to/docs/welcome/api), [job result](https://documentation.datalab.to/api-reference/marker-result-check)

## Đo streaming bổ sung

Đã đo riêng TTFB/TTFT bằng 3 câu ngắn trên mỗi model (8 model, 24 lượt; 23 hoàn tất, 1 OpenRouter timeout). Cloudflare/Llama 3.3 70B Fast có median TTFB 0,2116s, TTFT 0,3380s; Gemma 4 Cloudflare đo được 0,6375s / 0,6806s. Đây là 1 credential/model, không phải benchmark lại toàn bộ 99 credential. Xem [bảng streaming](../reports/stream-benchmark.txt) và [từng lượt](../reports/stream-benchmark.json). Sau khi người dùng chốt dùng model nhanh trước, đã áp dụng thứ tự TTFT vào `.env`, TXT và dashboard; quy tắc fallback key trước/provider sau giữ nguyên. Cloudflare: Llama 70B → Gemma 4 26B → GLM-4.7-Flash. Sau đó NVIDIA → Ollama → Google (Flash Lite → Flash) → OpenRouter. Xem [cấu hình thứ tự](../reports/model-priority.json).
