# Q Translate

Ứng dụng riêng cho Ubuntu GNOME. Bản hiện tại là **bản thử nghiệm**, chưa đạt ma trận phát hành Ubuntu 24.04/26.04.

- **Alt+C**: bôi đen rồi dịch Anh ↔ Việt bằng Microsoft Translator API (resource Free F0 do bạn tạo trên Azure). Đoạn trộn có câu/cụm tiếng Anh → Việt; câu Việt có thuật ngữ như key/model/region vẫn dịch sang Anh. Khung đóng khi click ngoài.
- **Alt+V**: AI viết lại thành tiếng Anh giao tiếp dễ hiểu, hiển thị streaming, tự copy khi hoàn tất. Không sửa hay tự dán vào terminal. Khung giữ đến khi đóng, gọi mới hoặc 30 giây sau copy thành công.
- **Alt+X**: kéo chọn vùng màn hình, gửi ảnh tới AI dịch. Khung kết quả chỉ có text dịch, không hiển thị ảnh. Không tự copy ảnh hoặc kết quả. Nguồn trộn → Việt.
- **Alt+D**: mở trợ lý **Q-translate**, chat AI và giữ ngữ cảnh trong phiên. Enter gửi, Shift+Enter xuống dòng. Nút **Ẩn** hoặc Esc giữ lịch sử/bản nháp, Alt+D mở lại; nút **×** dừng request và xóa phiên. Câu trả lời không tự copy; dùng icon copy. Dùng chung provider/model text với Alt+V, prompt chat riêng trong dashboard.
- Có thể bôi đen một phần kết quả trong cả bốn khung rồi Ctrl+C; icon copy ưu tiên đoạn đã chọn, không chọn thì copy toàn bộ. Thay đổi giao diện GNOME Shell được nạp khi đăng nhập lại Ubuntu.
- Cửa sổ chat/cài đặt ẩn khỏi dock và danh sách chuyển cửa sổ; dùng icon thanh trên hoặc phím tắt để mở.
- Dashboard: provider/model riêng cho text/ảnh, thứ tự fallback, import/export, prompt, phím tắt, cỡ chữ và nhật ký.

Mỗi lần gọi AI có tối đa **5 giây cho toàn bộ output**, tổng tác vụ 30 giây. Dùng lại cặp key/model thành công, hết vòng fallback quay lại từ đầu ở tác vụ tiếp theo. Model yêu cầu thinking hoặc OpenRouter trả phí bị loại.

## Chạy thử

Cần Python hệ thống, GTK4, PyGObject, GNOME Shell và curl. Adapter Codex trong Orca còn cần XWayland và libxres1. Extension thử nghiệm cho phép nạp trên **GNOME 46 và 50**. GNOME 46/Ubuntu 24.04 chưa được kiểm thử runtime; cho phép nạp không đồng nghĩa đã nghiệm thu.

```sh
./run.sh settings
./run.sh import --file exports/q-translate-import.txt
./run.sh serve
```

Trong phiên GNOME 46/50, cài extension của dự án vào tài khoản hiện tại:

```sh
./packaging/install_extension.sh
```

Wayland có thể cần đăng xuất/đăng nhập để Shell nhận extension mới. Sau đó bật trong Extensions hoặc nút “Kích hoạt phím tắt” ở dashboard. Extension cần backend đang chạy. `./run.sh status` kiểm tra IPC; `./run.sh quit` dừng backend và gỡ phím tắt. Đóng dashboard vẫn giữ backend.

**Autostart cần launcher `qtranslate` được cài bằng gói**, bật mặc định sau import/setup đầu tiên; có thể tắt trong dashboard.

## Gói thử nghiệm

```sh
./packaging/build_deb.sh
sudo apt install ./dist/q-translate.deb
qtranslate settings
qtranslate import --file /đường/dẫn/q-translate-import.txt
```

Gói không chứa `.env`, key, báo cáo riêng tư, ảnh chụp, clone Pot hoặc file TXT export. File TXT có key thật: chỉ chia sẻ riêng giữa máy của bạn.

## Dữ liệu và kiểm thử

Config/key: `$XDG_CONFIG_HOME/q-translate` (mặc định `~/.config/q-translate`). Log input/output/lỗi: `$XDG_STATE_HOME/q-translate/q-translate.log`, quyền riêng tư, tự xóa mỗi 24 giờ kể cả khi mở lại app; không có lịch sử riêng. Crop nằm tạm trong cache riêng và được xóa khi đóng khung. Key không xuất hiện trong dòng lệnh curl hay log.

```sh
./scripts/run-tests.sh
```

Kết quả chạy thật và các điều kiện còn thiếu: [release](docs/validation/release.md), [desktop matrix](docs/validation/desktop-matrix.md), [providers](docs/validation/providers.md). Alt+C đã chuyển sang Azure Translator chính thức. Nhập key và region ở **Dịch vụ & model → Alt+C → Kiểm tra & lưu key**; thiếu key sẽ báo hướng dẫn thiết lập. Key import từ .env cần kiểm tra trước khi dùng. Không tự quay lại Google/Bing web hoặc gọi AI. Xem docs/validation/azure-translator-setup.txt và .env.azure-translator.example.

Codex v0.166.0 trong Orca trên Wayland đã được thử bằng kéo chuột thật rồi Alt+V: nhận vùng chọn mới thay vì PRIMARY cũ. Adapter lấy chữ bằng Ctrl+Insert, giữ lại các định dạng clipboard và không sửa nguồn. Những TUI/terminal khác chưa được coi là đã hỗ trợ chỉ từ kết quả này; xem docs/validation/tui-selection-research.txt.
