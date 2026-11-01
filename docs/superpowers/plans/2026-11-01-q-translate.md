# Q Translate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây app riêng cho Ubuntu 24.04/26.04: Alt+C dịch miễn phí Anh ↔ Việt; Alt+V stream tiếng Anh giao tiếp rồi tự copy; Alt+X chụp vùng và gửi ảnh trực tiếp tới AI dịch.

**Architecture:** Python điều phối tác vụ/provider, giữ secret và dựng dashboard GTK4. Extension GJS phụ trách phím tắt, vùng chọn, clipboard, chụp vùng; spike ưu tiên popup St/Clutter trong Shell để đặt đúng vị trí trên Wayland, mạng luôn ở app Python. Desktop bridge và renderer dùng giao thức có version/generation; quyết định backend popup được ghi bằng bằng chứng Task 1, không suy từ demo HTML.

**Tech Stack:** Python >=3.12, PyGObject/GTK4, Gio/GLib, GJS ES modules cho GNOME 46/50; HTTP trong worker có giới hạn, unittest và node:test; gói `.deb`. Đây là lựa chọn kỹ thuật của tác giả để thực hiện hành vi đã được duyệt.

**Spec:** [2026-11-01-q-translate-design.md](../specs/2026-11-01-q-translate-design.md).

## Global Constraints

- Ubuntu 24.04 GNOME X11, Ubuntu 24.04 GNOME Wayland, Ubuntu 26.04 GNOME Wayland; có ca native Wayland và XWayland, không cam kết mọi desktop Linux.
- Alt+C: Anh ↔ Việt bằng dịch vụ miễn phí thông thường; không LLM, không tự copy kết quả. Google web trước/Bing dự phòng là ứng viên phải smoke test.
- Alt+V: nguồn Anh/Việt/hỗn hợp → tiếng Anh giao tiếp A1–A2, giữ đủ ý, câu hỏi/phủ định/tên/số; hiện streaming, chỉ tự copy text thuần khi hoàn tất. Không thay nguồn, tự dán, Ctrl+C đại trà vào terminal hoặc phát Enter/Delete/Backspace.
- Alt+X: crop → model đã xác minh image input → bản dịch Anh ↔ Việt; nguồn trộn dịch về Việt. Không OCR riêng, không gọi dịch miễn phí sau AI, không tự copy ảnh/bản dịch.
- Mỗi lượt gọi key AI có hạn trả xong toàn bộ output `min(attempt_start + 5s, task_deadline)`, không reset khi nhận chunk. Deadline tác vụ `task_deadline = task_start + 30s`, gồm chuẩn bị/fallback; task_start tính khi có nguồn hợp lệ hoặc thả crop, không tính thời gian người dùng chọn vùng.
- Không đặt trần ký tự tùy ý và không cắt âm thầm. Có thể chia/ghép theo giới hạn provider; chỉ công bố/copy hoàn tất khi đã xử lý đủ nguồn trong deadline.
- Fallback key trước/provider sau, một vòng ứng viên, tôn trọng Retry-After/cooldown key/account/provider. Giữ cặp provider/key/model thành công gần nhất qua restart; khi chưa có state dùng thứ tự TTFT trong [model-priority.json](../../../reports/model-priority.json).
- Cloudflare text mặc định Llama 3.3 70B Fast; trong provider Llama → Gemma 4 → GLM-4.7; provider Cloudflare → NVIDIA → Ollama → Google → OpenRouter. Chỉ dùng cặp key/model đã xác minh; không giả định 23 key Cloudflare đều chạy được Llama.
- Thinking tắt ở request; model bắt buộc reasoning không vào pool. Giữ chính sách chi phí, không tự chọn model trả phí thay model/free tier đã chọn. Text-verified không đồng nghĩa vision-verified.
- Import `.env`/TXT gộp và bỏ trùng theo provider/key/account binding, hợp nhất model/capability; không mặc định thay toàn bộ. Không thực thi dotenv/TXT như shell.
- Kiểm tra credential đồng thời tối đa 2 request. Audit/benchmark độc lập không dùng timeout runtime 5s để thay kết quả đo cũ; không chạy lại toàn bộ 220 credential nếu không có lý do mới.
- Bộ active hiện có 99 credential text và Tavily/Jina riêng. Giữ backup/kiểm kê/quarantine; lỗi quota/mạng/403/model không tương đương key sai xác thực vĩnh viễn. Datalab/Tavily/Jina chỉ là adapter phân loại, không bật thêm tính năng sản phẩm.
- Dashboard tại [HTML đã duyệt](../../../preview/q-translate-dashboard.html) là nguồn tham chiếu, không đưa JS/localStorage giả API vào app thật.
- Alt+C đóng khi bấm ngoài/Escape/nút đóng; click ngoài tới đích đúng một lần. Alt+V bấm ngoài/chuyển app vẫn giữ; đóng/gọi mới hoặc hết 30 giây từ khi hoàn tất thì ẩn. Timer cũ không ẩn tác vụ mới, copy lại không reset timer.
- Alt+C tự co giãn: tối đa 680 logical px/60% work area/margin 18px; Alt+V 480px/50%; ảnh 900px/60%, hai cột hoặc xếp dọc khi hẹp. Đây là giới hạn hình học đề xuất có thể tinh chỉnh theo desktop, không phải giới hạn nội dung.
- Log runtime JSONL chứa input/output/lỗi, metadata crop, ID key che; không chứa secret/header/ảnh. Quyền file 0600/thư mục 0700, clear mỗi 24 giờ, startup quá hạn clear trước ghi mới, không giữ archive hoặc kho lịch sử riêng. Báo cáo công khai/package không chứa dữ liệu riêng.
- Autostart bật sau setup lúc login, một instance/phiên; đóng dashboard không thoát engine. Không cài extension, chiếm phím hoặc bật autostart trong bước viết kế hoạch.
- Người dùng yêu cầu bỏ qua thiết kế riêng lỗi giữa stream: không mở rộng UI hoặc cơ chế tiếp nối stream; quy tắc không copy output dở dang vẫn áp dụng.

## Review Focus

1. Nguồn rỗng hoặc PRIMARY còn dữ liệu cũ khi đổi app: không lấy nhầm nguồn; Task 1 kiểm tra native/XWayland, Task 7 kiểm tra generation và clipboard tạm.
2. Chunk/kết quả/copy acknowledgment/timer cũ đến sau cancel hoặc tác vụ mới: không ghi clipboard, mở lại hoặc ẩn nhầm khung; Task 2/6/7 dùng fake clock và D-Bus owner epoch.
3. Request còn gửi chunk sau giây thứ 5, hoặc retry kéo dài quá 30 giây: dừng theo deadline tuyệt đối, không sinh worker vô hạn; Task 2/4/5 kiểm tra transport chậm và deadline còn lại.
4. Import cùng TXT nhiều lần, token giống nhau khác account, hoặc 429 dùng chung tài khoản: không mất credential/model hay retry vượt quota chung; Task 3/4/5 kiểm tra identity, binding và scope cooldown.
5. Crop/popup ở hai màn hình khác scale, chữ dài và click ngoài: crop đúng, không tràn/cuộn ngang, không đổi clipboard ảnh và không nuốt click; Task 1/6/9 có bằng chứng desktop thật.

---

## Scope, trạng thái và cách thực thi

Đây là một ứng dụng với desktop contract chung, không phải nhiều dự án độc lập. Chia thành chín deliverable có test riêng; Task 1 là spike chạy được với text cố định, Task 2–5 là lõi kiểm tra không cần GUI, Task 6–9 ghép sản phẩm và nghiệm thu. Không đánh dấu Task 1 hoàn tất bằng mock hoặc nguồn đọc online.

**Hiện đã có:** `tools/key_audit.py`, 27 test audit đang đạt, báo cáo API/TTFT, export riêng tư và prototype đã duyệt. Tận dụng parser/phân loại/fallback đã kiểm tra, không viết lại bộ audit từ đầu hoặc đưa fixture chứa key thật vào test.

**Preflight 2026-11-01:** Ubuntu 26.04.1, GNOME Shell 50.1, `/usr/bin/python3` 3.14.4, GTK 4.22 import được qua Python hệ thống. Python venv mặc định thiếu `gi`; phiên tool không có DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS. Dùng `/usr/bin/python3` cho app; core không import GTK. [Bản ghi môi trường](../../validation/planning-environment.json).

- Desktop preflight thiếu session phải trả exit 2/BLOCKED, không tự khởi động hoặc điều khiển desktop thật. Xvfb chỉ là GTK smoke test, không thay nghiệm thu Wayland.
- Khi Task 1 chưa có bằng chứng runtime, được viết harness và lõi/test độc lập; chưa kết luận backend desktop đạt hoặc mở rộng tích hợp native/provider dựa trên giả định. Không phát hành trước khi ma trận desktop đạt.
- Thư mục hiện không có `.git`; không tự `git init` hoặc tạo worktree/commit giả. Khi có repo hợp lệ, dùng branch/workspace được cấp và commit từng deliverable bằng danh sách file rõ ràng, không `git add .`. Nếu chưa có Git, ghi checkpoint/test/ruling vào `docs/validation/implementation-ledger.md`, ghi rõ chưa commit.
- Trong mỗi task: viết test → chạy thấy FAIL đúng → implement → chạy GREEN → full suite liên quan → checkpoint. Không checkbox nào bên dưới được đánh dấu hoàn tất trong lượt lập kế hoạch.

## File Structure

```text
pyproject.toml
src/qtranslate/
  __init__.py, __main__.py, app.py
  desktop/{context,capabilities,protocol,bus}.py
  tasks/{types,controller}.py
  config/{settings,secrets,env_import}.py
  logging.py
  providers/{base,http,registry,health}.py
  providers/free/{google,bing,language}.py
  providers/ai/{google,ollama,openrouter,nvidia,cloudflare}.py
  providers/audit/{datalab,tavily,jina}.py
  actions/{translate,rewrite,image_translate}.py
  ui/{state,dashboard,text_popup,image_result,theme}.py
  audit/{runner,report,cleanup}.py
extension/qtranslate@local/
  package.json, metadata.json, extension.js, stylesheet.css
  {keybindings,selection,clipboard,capture,bridge,popups}.js
  schemas/org.qtranslate.desktop.gschema.xml
  tests/{view_state,protocol}.test.js
  view_state.js
  interfaces/org.qtranslate.Desktop1.xml
data/{org.qtranslate.App.desktop,org.qtranslate.App.service}
packaging/{build_deb,install_extension}.sh
packaging/org.qtranslate.Autostart.desktop
scripts/run-tests.sh
tests/{__init__.py,unit/__init__.py,integration/__init__.py,fixtures/}
tests/fixtures/{clock,transport,desktop,images}.py
tools/{desktop_probe,benchmark_translation}.py
docs/validation/{desktop-matrix,desktop-backend,providers,release}.md
```

Các đoạn assertion dưới đây là phần thân kiểm tra cần viết trong task; biến kết quả/counter do fixture của test chuẩn bị, không phải biến toàn cục của app. Các đường rút gọn ở trên đều tương đối root, còn file Python trong từng task dưới đây tương đối `src/qtranslate/` trừ khi ghi `tests/`, `tools/`, `scripts/` hoặc `packaging/`. Giữ nguyên ảnh/HTML tham chiếu, `reference/` và các backup riêng tư. Không tách module chỉ để có thêm lớp wrapper.

## Shared Interfaces và thứ tự phụ thuộc

Task 1 tạo `desktop/context.py` và `desktop/protocol.py` trước, tránh vòng phụ thuộc cũ giữa spike và core. Task 2 tạo kiểu tác vụ, Task 3 tạo store/log, Task 4 tạo provider, Task 5 tạo engine, Task 6 tạo renderer, Task 7 nối giao thức, Task 8 nối dashboard, Task 9 đóng gói.

- `SourceContext(window_id: str, app_id: str, source_epoch: str, monitor: int)` là metadata snapshot, không chứa quyền thay editor; kiểm tra focus lúc lấy nguồn, không bắt buộc giữ focus khi chờ AI.
- `CapabilityReport(platform: str, shell_version: str, selection: bool, clipboard: bool, capture: bool, popup: bool, popup_backend: str, status: str)`. `status` là PASS/FAIL/BLOCKED; thiếu session không được tự đặt PASS.
- `Action`: `translate`, `rewrite`, `image_translate`. `TaskRequest(id: str, action: Action, text: str | None, image_path: str | None, context: SourceContext, target: str | None)`; nguồn ảnh chỉ từ cache riêng của task.
- `TaskResult(id: str, action: Action, state: str, text: str, provider: str | None, model: str | None, error_code: str | None)`. State: `waiting`, `streaming`, `ready`, `success`, `error`, `cancelled`, `no_text`, `unreadable`. `ready` chỉ Alt+V có text hoàn chỉnh đang chờ ghi clipboard; `success` Alt+V chỉ sau acknowledgment. Alt+C/ảnh có thể success trực tiếp.
- `TaskController(runner, emit, clock, max_workers=2)`: `submit(request: TaskRequest) -> str`, `cancel(id: str) -> bool`, `is_current(id: str) -> bool`, `confirm_copy(id: str, ok: bool) -> None`, `shutdown() -> None`. Một current task mỗi action; tối đa 2 worker và một pending mới nhất mỗi action. Emit qua main loop/IPC, không gọi GTK từ worker.
- `SettingsStore.load() -> Settings`, `save(settings: Settings) -> None`; settings có `task_timeout=30`, `key_timeout=5`, `thinking=False`, prompt text/vision, thứ tự/provider/model/key refs riêng cho text/vision và cài đặt UI. Task nhận snapshot settings khi submit.
- `SecretStore.merge(bundle: dict) -> ImportReport`, `get(ref: CredentialRef) -> str`, `export_verified(path: Path) -> None`. `CredentialRef(id, provider, secret_ref, account_ref)` không chứa key. `ImportReport(added, duplicates, quarantined, model_pairs)` chỉ có số/ID che.
- `RuntimeLog(path: Path, secrets, clock)`: `record(event: dict) -> None`, `clear() -> None`, `maintain() -> None`. Clock có wall time cho mốc dọn bền vững và monotonic cho tác vụ; không nhập nhằng hai loại thời gian.
- `Candidate(provider: str, credential: CredentialRef, model: str, capability: str)`. Registry chỉ tạo candidate từ cặp đã probe, không áp default model của provider lên mọi key.
- `ProviderChunk(delta: str)` là text tăng thêm, không mang task/UI ID. `ProviderResponse(text: str, complete: bool, finish_reason: str | None, error_code: str | None)`. `ProviderAdapter.run(payload: dict, candidate: Candidate, deadline: float, cancelled, on_delta=None) -> ProviderResponse`; `on_delta(ProviderChunk) -> None` gọi trong worker, không gọi widget/clipboard. `probe(candidate, capability, deadline) -> ProbeResult` và `list_models(credential) -> list[ModelCapability]` dùng trong audit, không khám phá model tùy tiện trong tác vụ dịch.
- Các action `translate_text(request, settings, deadline, cancelled, on_update) -> TaskResult`, `rewrite_text(...) -> TaskResult`, `translate_image(...) -> TaskResult` đều có cùng tham số. Action ghép delta thành text tạm và phát `TaskResult(state='streaming')`; rewrite trả `ready`, translate/ảnh trả `success` hoặc lỗi chuẩn hóa. `on_update(TaskResult) -> None` do controller bọc generation.
- `ModelCapability(model: str, capability: str, verified_at: str, thinking_disabled: bool)` gắn với credential trong store; `ProbeResult(status, candidate, latency, error_code)` không giữ raw response/secret.
- `ViewState(task_id, action, text, phase, copy_enabled, success_icon, expires_at, visible, scroll_offset)` là kiểu thuần Python; `reduce_view(state: ViewState, event: TaskResult, now: float) -> ViewState`, `expire_view(state, task_id, now) -> ViewState`. Renderer nhận state qua giao thức; timer phải gắn task ID.
- D-Bus: app sở hữu `org.qtranslate.App`, path `/org/qtranslate/App`, interface `org.qtranslate.App1`; extension sở hữu `org.qtranslate.Desktop`, path `/org/qtranslate/Desktop`, interface `org.qtranslate.Desktop1`. App có `Submit(json:s)->id:s`, `Cancel(id:s)->accepted:b`, `Capabilities()->json:s`, signal `TaskChanged(id:s,json:s)`. Extension có `CopyText(id:s,text:s)->ok:b`; app chỉ gọi cho task rewrite ở ready còn current. Hai phía xác minh unique owner và protocol version 1, đổi owner làm mất hiệu lực epoch cũ.
- Text lớn qua `BeginText(id:s,json:s)`, `AppendText(id:s,index:u,text:s)`, `FinishText(id:s)->id:s` trên App1; metadata có source context và tổng số chunk, từng frame tối đa 64 KiB UTF-8, index liên tiếp. Không đặt trần tổng ký tự; dùng spool riêng tư, cleanup theo deadline/cancel. Không đánh giá limit frame thành limit nguồn.
- `scripts/run-tests.sh` dùng `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v`, sau đó node:test khi có extension test. Test từ Task 2 thêm `__init__.py` để unittest thực sự duyệt cả unit/integration; luôn gồm 27 test audit cũ.

## Task 1: Spike phím tắt, vùng chọn, clipboard, popup và capture

**Files:** Create `desktop/{context,capabilities,protocol}.py`, `tools/desktop_probe.py`, extension `metadata.json`, `package.json` (type module), `extension.js`, `{keybindings,selection,clipboard,capture,bridge,popups}.js`, schema/XML ở File Structure; `tests/integration/test_desktop_probe.py`, `docs/validation/{desktop-matrix,desktop-backend}.md`.

**Interfaces:** Produces SourceContext, CapabilityReport và schema protocol v1 ở Shared Interfaces. Probe Python dùng phản hồi text cố định/trễ, không gọi provider hoặc đọc secret. Extension chưa tự được cài vào phiên người dùng.

- [ ] **Step 1 — RED:** viết `test_missing_session_is_blocked` (env rỗng → status BLOCKED, không chạy lệnh cài extension), `test_source_context_rejects_stale_epoch` (epoch cũ bị từ chối), `test_protocol_rejects_unknown_version` (version 2 bị từ chối). Ghi checklist thật cho PRIMARY rỗng/cũ, terminal input/output, phím xung đột, copy mới nhất và crop HiDPI.
- [ ] **Step 2 — Observe FAIL:** `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/integration -p 'test_desktop_probe.py' -v`; expected FAIL vì module probe/contract chưa tồn tại, không phải thiếu `gi`.
- [ ] **Step 3 — Implement:** probe `collect_capabilities(env: dict) -> CapabilityReport`, validate protocol/context; keybinding GSettings khi enable, tháo khi disable. Thử St.Clipboard PRIMARY/CLIPBOARD theo mã gắn tag; source không chắc đúng phải báo không lấy được vùng chọn, không lấy clipboard cũ hoặc phát Ctrl+C vào terminal.
- [ ] **Step 4 — Spike renderer/capture:** ưu tiên popup St/Clutter không modal, chọn/copy/cuộn được; kiểm chứng click ngoài truyền đúng một lần và Alt+V không giành focus. Crop riêng qua Shell.Screenshot/output stream; không gọi helper lưu ảnh clipboard/ổ đĩa mặc định. Nếu Shell renderer không đạt, chỉ chọn GTK+bridge khi cùng checklist đạt, ghi lý do/backend vào desktop-backend; nếu cả hai không đạt, ghi FAIL/BLOCKED và sửa thiết kế, không giả lập đạt.
- [ ] **Step 5 — Verify:** chạy lại test Step 2 → PASS; `glib-compile-schemas --strict extension/qtranslate@local/schemas` → exit 0; `node --check` từng JS extension → exit 0. `PYTHONPATH=src /usr/bin/python3 tools/desktop_probe.py --check --report docs/validation/desktop-probe.json` → hiện tại dự kiến exit 2/BLOCKED do thiếu session. Trong desktop thật, probe phải PASS với browser, editor, GTK, Qt, PDF có text và terminal; mỗi phiên Wayland có native/XWayland, thêm nhiều màn hình/scale và click vào app khác/desktop. Không coi exit 2 hoặc syntax check là nghiệm thu runtime.
- [ ] **Step 6 — Checkpoint:** ghi môi trường/app version, evidence và backend chọn; commit nhóm file Task 1 khi Git có sẵn, nếu chưa thì ledger. Chưa có PASS thật thì giữ phần desktop của Task 1 mở.

Các assertion của Step 1 (fixture environment không có session):

```python
report = collect_capabilities({})
self.assertEqual(report.status, "BLOCKED")
self.assertFalse(report.selection)
self.assertFalse(report.capture)
self.assertEqual(installer_calls, [])
```


## Task 2: Core tác vụ, streaming, deadline và generation

**Files:** Create `pyproject.toml`, `src/qtranslate/__init__.py`, `tasks/{__init__,types,controller}.py`, `config/{__init__,settings}.py`, `tests/{__init__,unit/__init__,integration/__init__}.py`, `tests/fixtures/{__init__,clock,transport,desktop}.py`, `tests/unit/test_tasks.py`, `scripts/run-tests.sh`.

**Interfaces:** Consumes Task 1 context/protocol; produces TaskRequest/TaskResult, TaskController, Settings. Fixture `FakeClock.advance(seconds)`, `FakeRunner.emit(id,state,text)`, `FakeDesktop.copies` chỉ ghi nhận lời gọi test, không phát phím thật.

- [ ] **Step 1 — RED:** viết `test_latest_rewrite_owns_copy` (A rồi B: A ready/confirm muộn không success), `test_actions_have_independent_generation` (Alt+C mới không hủy Alt+X), `test_stream_has_no_copy_or_success` (streaming giữ text, không ready/success), `test_settings_snapshot` (đổi prompt khi A chạy không đổi A), `test_watchdog_expires_even_when_runner_stalls` (clock=30 → timeout và late update bị bỏ).
- [ ] **Step 2 — Observe FAIL:** `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -p 'test_tasks.py' -v` → FAIL vì controller chưa có.
- [ ] **Step 3 — Implement:** controller theo Shared Interfaces, deadline monotonic, current task riêng mỗi action, 2 worker + pending latest; hủy/gọi mới vô hiệu stream và quyền copy cũ. Đầu vào chỉ whitespace báo không có vùng chọn, không gọi runner; text >10.000 ký tự vẫn được submit. Core không import `gi`.
- [ ] **Step 4 — GREEN:** chạy lại Step 2 → PASS. Thêm `test_repeated_shortcuts_bound_workers` (nhiều submit khi runner kẹt: active <=2, pending <=3, chỉ current được emit); Step 2 và `bash scripts/run-tests.sh` đều PASS, test audit cũ vẫn được discover.
- [ ] **Step 5 — Checkpoint:** lưu test count/command và quyết định dùng ready trước clipboard acknowledgment; commit đúng nhóm file Task 2 hoặc ledger khi Git chưa có.

Các assertion với FakeRunner/FakeClock ở Step 1 và Step 4:

```python
self.assertFalse(controller.is_current(req_a.id))  # A rồi B cùng action rewrite
self.assertTrue(controller.is_current(req_b.id))
self.assertNotIn(req_a.id, success_ids)
self.assertEqual(timed_out.error_code, "TASK_TIMEOUT")
self.assertLessEqual(active_worker_count, 2)
self.assertLessEqual(pending_task_count, 3)
```


## Task 3: Settings, secret store, import gộp và log 24 giờ

**Files:** Create `config/{secrets,env_import}.py`, `logging.py`, `tests/unit/{test_settings,test_import_merge,test_runtime_log}.py`. Modify `config/settings.py`; reuse `tools/key_audit.py` qua phần logic được chuyển vào package có regression test, giữ CLI cũ tương thích.

**Interfaces:** Consumes Settings; produces SecretStore, CredentialRef, ImportReport, RuntimeLog. `parse_import(path: Path) -> dict` đọc schema portable v1 hoặc dotenv; `merge` không đưa key vào DTO UI/report. Store model/capability là tập cặp đã xác minh, không chỉ một default model/provider.

- [ ] **Step 1 — RED:** `test_import_twice_is_idempotent` (lần 2 added=0, số credential không tăng), `test_same_token_two_accounts_survive` (giữ đủ 2 binding), `test_merge_keeps_existing_keys_and_models`, `test_conflicting_model_names_preserve_values`, `test_failed_import_does_not_replace_store` (store cũ nguyên vẹn), `test_secrets_private_and_redacted` (file 0600, dir mới 0700, repr/report không có dummy key).
- [ ] **Step 2 — Observe FAIL:** `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -p 'test_import_merge.py' -v` → FAIL vì store chưa có. Fixture chỉ dùng dummy key; không lấy `.env` thật làm snapshot test.
- [ ] **Step 3 — Implement:** parse/gộp identity provider/key/account, hợp nhất model/capability, giữ provenance và quarantine dòng mơ hồ; source không bị thực thi. Ghi atomic có backup, từ chối source/destination collision, kiểm tra nguồn thay đổi trước cleanup. Chuẩn hóa routes từ TXT đã xác minh; file nguồn phát triển không hardcode vào package/runtime.
- [ ] **Step 4 — Log/settings RED→GREEN:** trước khi implement viết `test_log_clears_at_24h_and_startup`, `test_concurrent_clear_and_write`, `test_log_failure_does_not_fail_translation`, `test_log_redacts_key_inside_input_output`, `test_settings_persist_and_reject_empty_pool`. Chạy từng module thấy FAIL rồi implement RuntimeLog/settings; wall-clock mốc dọn qua restart, không archive, ảnh chỉ metadata, lỗi log không chặn dịch.
- [ ] **Step 5 — Verify:** `bash scripts/run-tests.sh` → PASS; kiểm tra import core không cần GUI và parser 27 regression cũ không mất. `export_verified` loại unverified/quarantine/model pair không đạt; .env và backup thật không thay đổi trong unit test.
- [ ] **Step 6 — Checkpoint:** commit nhóm Task 3 hoặc ledger; ghi rõ CLI native import mới dùng merge, không nhầm với công cụ portable export cũ.

Các assertion merge/log trong fixture store tạm:

```python
first = store.merge(bundle)
second = store.merge(bundle)
self.assertGreater(first.added, 0)
self.assertEqual(second.added, 0)
self.assertEqual(len(account_bindings), 2)  # cùng token, hai account
self.assertNotIn(dummy_key, public_report_json)
self.assertEqual(log_lines_after_overdue_startup, [])
```


## Task 4: HTTP streaming, năm provider AI và audit capability

**Files:** Create `providers/{__init__,base,http,registry,health}.py`, các module AI/audit theo File Structure, `audit/{__init__,runner,report,cleanup}.py`, `tests/unit/{test_http_stream,test_provider_adapters,test_provider_health}.py`, `tests/integration/test_provider_audit.py`.

**Interfaces:** Consumes Candidate/credential refs/store; produces ProviderChunk, ProviderResponse, ModelCapability, ProbeResult và registry. Transport `request_stream(url, headers, body, deadline, cancelled, on_event) -> ProviderResponse` chỉ cho endpoint HTTPS chính thức và không theo redirect mang auth.

- [ ] **Step 1 — RED:** `test_sse_frames_split_across_reads` (UTF-8 và event chia chunk vẫn ghép đúng), `test_ndjson_waits_for_complete_line`, `test_role_comment_and_reasoning_are_not_text`, `test_eof_without_completion_is_not_success`, `test_untrusted_redirect_never_gets_authorization`. Fake transport không mở HTTP public hoặc dùng credential thật.
- [ ] **Step 2 — Observe FAIL:** `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -p 'test_http_stream.py' -v` → FAIL vì transport chưa có.
- [ ] **Step 3 — Implement:** parser SSE/NDJSON theo adapter, complete marker/finish_reason/provider error chuẩn hóa. Tận dụng payload thinking-off đã đo ở audit cũ; đối chiếu tài liệu hiện hành qua ctx7 trước API chưa tra. Body/request/log không đưa key vào URL; request timeout theo ngân sách còn lại, watchdog Task 2 vẫn là deadline tổng.
- [ ] **Step 4 — Adapter/health RED→GREEN:** viết `test_each_provider_disables_thinking`, `test_mandatory_thinking_model_excluded`, `test_google_thought_part_rejected`, `test_auth_403_quota_distinct`, `test_account_cooldown_does_not_skip_other_account`, `test_success_then_bad_repeat_not_verified`, `test_text_success_does_not_verify_image`. Chạy từng test thấy FAIL rồi implement bằng cách trích/đối chiếu logic đã có, không nhân bản parser audit thứ hai.
- [ ] **Step 5 — Audit integration:** giữ Tavily/Jina/Datalab kiểm tra chức năng riêng và concurrency<=2; live discovery chỉ trong bước kiểm tra và cùng chính sách chi phí. `cleanup.apply(report, env_path)` chỉ áp report có source hash khớp, có backup; source thay đổi từ chối. Không xóa vĩnh viễn vì timeout/quota/403.
- [ ] **Step 6 — Verify/checkpoint:** `bash scripts/run-tests.sh` → PASS; fixture public report không chứa dummy key, raw auth hoặc ảnh. Giữ báo cáo 99 text/2 auxiliary làm baseline; live recheck chỉ cho model mới/lỗi chưa rõ hoặc thay adapter. Commit nhóm Task 4 hoặc ledger.

Các assertion qua transport/adapter thật với fake I/O:

```python
self.assertEqual(response.text, "Hello, Việt Nam")  # UTF-8 chia giữa read
self.assertTrue(response.complete)
self.assertFalse(incomplete_response.complete)
self.assertEqual(untrusted_endpoint_requests, [])
self.assertNotIn((credential_id, model_id, "image"), verified_capability_pairs)
self.assertNotIn(dummy_key, normalized_error)
```


## Task 5: Ba action, chọn model/key và chia đoạn đầy đủ

**Files:** Create `providers/free/{__init__,google,bing,language}.py`, `actions/{__init__,translate,rewrite,image_translate}.py`, `tests/unit/{test_free_translation,test_ai_routing,test_action_output}.py`, `tests/fixtures/images.py`, `tools/benchmark_translation.py`, `docs/validation/providers.md`.

**Interfaces:** Consumes provider transport/registry, settings/store, task types/clock; produces ba action theo Shared Interfaces. Quyền copy thuộc controller/bridge, action không gọi clipboard. Probe ảnh dùng ảnh Anh/Việt/hỗn hợp tự tạo, không crop màn hình thật.

- [ ] **Step 1 — RED:** `test_free_translate_joins_all_segments` (ghép đủ response Google), `test_english_vietnamese_mixed_direction` (Anh→Việt, Việt→Anh, trộn→Việt), `test_unaccented_text_is_not_assumed_english`, `test_url_number_only_has_no_network`, `test_free_never_calls_llm`. Chạy `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -p 'test_free_translation.py' -v` → FAIL vì action/adapter chưa có.
- [ ] **Step 2 — Implement free:** tham khảo adapter Pot ở commit đã clone, chỉ lấy bản dịch; Bing/Edge cache token theo hạn, không log token. Text mơ hồ dùng provider detect và cho đảo chiều trong popup; text rõ ngôn ngữ dùng quy tắc spec, không thêm màn từ điển.
- [ ] **Step 3 — Routing RED:** viết `test_key_first_provider_second`, `test_model_pair_is_verified_for_that_key`, `test_last_success_survives_restart`, `test_disabled_sticky_falls_back_to_ttft`, `test_five_seconds_is_whole_attempt` (stream còn chạy ở t=5 vẫn bị timeout), `test_last_attempt_uses_remaining_budget` (t=28 → hạn=30), `test_one_cycle_has_no_repeat` và `test_quota_scope_skips_shared_account`. Chạy `... -p 'test_ai_routing.py' -v` → FAIL, rồi implement candidate order/cooldown và deadline Task 2/4; thành công mới ghi last-success, không ghi từ probe/cancel.
- [ ] **Step 4 — Output RED→GREEN:** `test_rewrite_prompt_preserves_questions_negation` kiểm payload prompt đúng mục 8 spec; `test_chunking_keeps_unicode_all_paragraphs` so ghép đủ nguồn >10.000 ký tự và thứ tự; `test_incomplete_rewrite_never_ready`; `test_image_routes_only_verified_vision`, `test_image_does_not_call_ocr_or_free`, `test_image_no_text_and_unreadable_are_not_success`. Chạy FAIL rồi implement prompts riêng và chia/ghép theo giới hạn provider; không output/copy thành công một phần hoặc tự tóm tắt.
- [ ] **Step 5 — Verify live tối thiểu:** khi desktop spike đủ căn cứ, chạy `PYTHONPATH=src /usr/bin/python3 tools/benchmark_translation.py --free --vision --report docs/validation/provider-probe.json`. Free: mẫu hai chiều/hỗn hợp, median/tỉ lệ lỗi; vision: probe ảnh thực, thinking off, deadline 5s/key. Expected: chỉ cặp đã tạo bản dịch đúng ảnh vào pool; lỗi/quota giữ đúng trạng thái, không sửa số đo cũ hoặc chọn model ngoài chi phí đã chốt. Nếu mạng/quota cản, ghi BLOCKED, không nhận mock làm thành công thật.
- [ ] **Step 6 — GREEN/checkpoint:** `bash scripts/run-tests.sh` → PASS; review nội dung mẫu dài/câu hỏi/phủ định/tên/số thủ công, không dùng heuristic ba câu audit ngắn như validator tổng quát. Commit nhóm Task 5 hoặc ledger, ghi pool vision nào còn chưa xác minh.

Các assertion routing với sáu ứng viên đều timeout hết 5 giây:

```python
self.assertEqual(attempt_deadlines, [5, 10, 15, 20, 25, 30])
self.assertEqual(fallback_trace[:3], ["cf/key1", "cf/key2", "nvidia/key1"])
self.assertLessEqual(clock.monotonic(), 30)
self.assertEqual(last_attempt_deadline_when_start_is_28, 30)
self.assertEqual(llm_calls_from_free_action, 0)
self.assertEqual(ocr_or_free_calls_from_image_action, 0)
```


## Task 6: State giao diện và ba khung kết quả đã duyệt

**Files:** Create `ui/{__init__,state,text_popup,image_result,theme}.py`, `tests/unit/test_view_states.py`, extension `view_state.js`, `tests/view_state.test.js`; Modify `popups.js`, `stylesheet.css`.

**Interfaces:** Consumes TaskResult, generation và popup_backend Task 1; produces ViewState/reducer và renderer. Backend Shell dùng state JS thuần kiểm tra node:test; backend GTK chỉ dùng nếu Task 1 chứng minh cùng hành vi, không chạy GTK trong tiến trình Shell. Cả hai nhận cùng semantics và kích thước.

- [ ] **Step 1 — RED:** `test_stream_does_not_enable_copy_or_timer` (stream/ready không copy/dấu tích/timer), `test_success_starts_30s_timer`, `test_old_timer_cannot_hide_new_task`, `test_recopy_does_not_reset_timer`, `test_rewrite_outside_click_does_not_close`, `test_translate_outside_click_closes`, `test_short_after_long_resets_size_and_scroll`, `test_copy_failed_keeps_result`. Chạy `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/unit -p 'test_view_states.py' -v` và `node --test extension/qtranslate@local/tests/view_state.test.js` → FAIL trước implement.
- [ ] **Step 2 — Implement state:** reducers theo Shared Interfaces; ảnh waiting có crop/copy disabled, no_text/unreadable khác success, retry tạo task mới cùng crop. Chỉ Alt+V success sau copy acknowledgment mới bật dấu tích/timer; hủy/cũ không tự mở lại.
- [ ] **Step 3 — Implement renderer:** đúng ảnh Alt+C tối đã duyệt; Alt+V toast góc dưới phải, stream thật không hiệu ứng gõ giả, cuối chỉ text/dấu tích/copy/đóng; ảnh crop trái/dịch phải, placeholder/vòng chờ nhẹ. Không thêm nhãn “Đã copy tiếng Anh” hoặc “Bạn có thể dán ngay”. Tôn trọng reduced motion.
- [ ] **Step 4 — Layout:** giới hạn Global Constraints, cỡ chữ mặc định 18px có thể đổi; wrap URL/từ dài, cuộn dọc, icon luôn ngoài vùng cuộn. Khung co lại khi kết quả ngắn, reset scroll khi kết quả mới; stream cập nhật không giành focus hoặc làm nhảy cửa sổ.
- [ ] **Step 5 — GREEN/visual:** test Step 1 và `bash scripts/run-tests.sh` → PASS. Trong desktop thật thử ngắn→dài→ngắn, đổi font/scale, mép monitor, bấm/copy/cuộn/đóng; lưu ảnh chụp UI với nguồn fixture, không dùng thông tin riêng làm evidence public. Xvfb hoặc demo HTML không thay PASS Wayland.
- [ ] **Step 6 — Checkpoint:** commit nhóm Task 6 hoặc ledger, ghi backend đã dùng và giới hạn chưa đạt.

Các assertion reducer (state được tạo từ chuỗi sự kiện test):

```python
self.assertFalse(streaming.copy_enabled)
self.assertFalse(streaming.success_icon)
self.assertIsNone(streaming.expires_at)
self.assertEqual(success.expires_at, completed_at + 30)
self.assertEqual(recopied.expires_at, success.expires_at)
self.assertTrue(after_old_timer.visible)  # timer A không ẩn B
```


## Task 7: Nối D-Bus, acknowledgment clipboard và vòng đời extension

**Files:** Create `desktop/bus.py`, `tests/integration/test_desktop_protocol.py`, extension `tests/protocol.test.js`; Modify `desktop/protocol.py`, `bridge.js`, `clipboard.js`, `extension.js`, schema XML giao thức.

**Interfaces:** Consumes Task 1 protocol, controller Task 2, store Task 3 và renderer Task 6; implements App1/Desktop1 ở Shared Interfaces. Secret không qua D-Bus; input/output theo yêu cầu chỉ gửi đến bridge/UI đang có epoch hợp lệ.

- [ ] **Step 1 — RED:** `test_wrong_owner_or_epoch_rejected`, `test_copy_only_current_ready_rewrite`, `test_cancel_before_ack_ignores_late_success`, `test_large_text_chunk_order_and_utf8`, `test_crop_path_outside_cache_or_symlink_rejected`, `test_extension_restart_invalidates_old_requests`. Chạy `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/integration -p 'test_desktop_protocol.py' -v` và `node --test extension/qtranslate@local/tests/protocol.test.js` → FAIL trước implement.
- [ ] **Step 2 — Implement IPC:** Gio async, schema/version/unique owner/epoch validation hai phía, text frame 64KiB và cleanup spool theo task. Không dùng shell command chứa nội dung nguồn; crop path chỉ regular file trong private cache, không symlink/path tùy ý.
- [ ] **Step 3 — Wire:** Alt+C→translate, Alt+V→rewrite, Alt+X→image; provider callback→controller→TaskChanged→renderer. Rewrite ready còn current mới CopyText; acknowledgment đúng ID/epoch mới confirm_copy(success). Copy fail giữ text để copy lại, không gọi model lại.
- [ ] **Step 4 — Clipboard/lifecycle:** success thay clipboard hiện tại bằng text thuần Unicode/newline và không restore snapshot cũ; lỗi/hủy trước commit giữ clipboard. Copy tạm lấy nguồn chỉ dùng adapter đã kiểm chứng và không ghi đè clipboard người dùng vừa thay. Disable/exit tháo keybinding/signal/timer, hủy task và xóa ảnh/spool; khung cũ không tự mở sau reconnect.
- [ ] **Step 5 — GREEN/E2E:** tests Step 1, `bash scripts/run-tests.sh` → PASS. Session D-Bus fixture kiểm serialization/owner thật; sau đó thử desktop thật chuyển app/gõ tiếp, gọi phím liên tiếp và disable/re-enable. Chỉ task rewrite mới nhất có quyền copy; app nguồn không nhận paste/Enter hoặc sửa text.
- [ ] **Step 6 — Checkpoint:** commit nhóm Task 7 hoặc ledger, cập nhật desktop-matrix với bằng chứng runtime, không suy XWayland là native Wayland.

Các assertion sau flow thực của controller/bridge với fake clipboard:

```python
self.assertEqual(fake_desktop.copies, [(req_b.id, "New English text")])
self.assertEqual(source_editor_text_after, source_editor_text_before)
self.assertNotIn(req_a.id, success_ids)
self.assertEqual(image_bytes_sent, expected_crop_bytes)
self.assertEqual(secret_values_in_ipc, [])
```


## Task 8: Dashboard GTK4, CLI và vòng đời ứng dụng

**Files:** Create `src/qtranslate/{__main__,app}.py`, `ui/dashboard.py`, `tests/unit/test_dashboard_model.py`, `tests/integration/test_application.py`; Modify `config/settings.py`, `pyproject.toml` và `ui/theme.py`.

**Interfaces:** `qtranslate` chạy nền, `qtranslate settings` mở dashboard, `qtranslate import --file PATH` dùng merge, `qtranslate audit-keys` dùng audit hiện có. `Gtk.Application` sở hữu app ID/single instance; controller/store/renderer đều có cùng composition root ở app.py, import CLI kiểm tra không bắt buộc display.

- [ ] **Step 1 — RED:** `test_provider_change_affects_next_task_only`, `test_cannot_save_empty_enabled_pool`, `test_text_capability_is_not_vision_green`, `test_import_view_uses_masked_report`, `test_prompt_reset_restores_spec`, `test_settings_close_keeps_service`, `test_second_instance_activates_existing_app`. Chạy từng module bằng unittest → FAIL trước implement.
- [ ] **Step 2 — Implement dashboard:** theo HTML đã duyệt: dịch vụ/model/text/vision riêng, key và probe/merge TXT, thứ tự fallback và trạng thái thật, phím tắt/font/theme, prompt/khôi phục, log input/output/lỗi/xóa ngay. Có thể dùng engine thật trong phần thử; không hiển thị nút giả thành công hoặc key thật trong widget/console.
- [ ] **Step 3 — Compose:** SettingsStore + SecretStore + RuntimeLog + TaskController + engines + DesktopBus. GTK main thread, worker cập nhật qua GLib; app khởi động không tự gửi clipboard/ảnh/provider probe nếu chưa có thao tác. Tác vụ user và audit có ngân sách riêng, pool/task đang chạy dùng snapshot.
- [ ] **Step 4 — GREEN/smoke:** `bash scripts/run-tests.sh` → PASS. `PYTHONPATH=src xvfb-run -a dbus-run-session /usr/bin/python3 -m qtranslate settings --smoke` → exit 0, tạo/destroy window một lần và không gọi network/cài extension. Đây chỉ là GTK smoke, không PASS desktop bridge. So dashboard với HTML trên desktop thật, kiểm phím tắt xung đột không bị đổi âm thầm.
- [ ] **Step 5 — Checkpoint:** commit nhóm Task 8 hoặc ledger; mô tả lệnh chạy bằng Python hệ thống và đường store/log, không buộc dùng venv thiếu gi.

Các assertion qua composition root và dashboard model:

```python
self.assertEqual(active_task_prompt, original_prompt)
self.assertEqual(next_task_prompt, saved_new_prompt)
self.assertFalse(unverified_vision_row["enabled_for_image"])
self.assertNotIn(dummy_key, rendered_key_labels)
self.assertEqual(engine_shutdown_calls_after_dashboard_close, 0)
```


## Task 9: Đóng gói, autostart và nghiệm thu ba phiên Ubuntu

**Files:** Create launcher/service/autostart template và scripts packaging ở File Structure, `tests/integration/test_package.py`, `docs/validation/release.md`; Modify desktop-matrix/providers với kết quả cuối.

**Interfaces:** launcher và D-Bus activation gọi cùng entrypoint; autostart sau setup dùng ~/.config/autostart, bật/tắt idempotent. Gói `.deb` không chứa `.env`, exports/private inventory/backup, crop, log riêng hoặc reference clone.

- [ ] **Step 1 — RED:** `test_package_excludes_secrets_and_private_files`, `test_autostart_enable_disable_is_idempotent`, `test_desktop_exec_uses_system_python_entrypoint`, `test_single_instance_autostart_and_activation`, `test_uninstall_does_not_delete_user_source_env`. Chạy `PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests/integration -p 'test_package.py' -v` → FAIL trước implement.
- [ ] **Step 2 — Implement packaging:** `bash packaging/build_deb.sh --output dist/q-translate.deb` dựng từ manifest allowlist file, dependency hệ thống GTK/Gio/Python và extension. Installer đặt extension phù hợp phiên bản GNOME; runtime không cần root, không hardcode đường repo/secret. Menu mở/thoát và launcher luôn có dù không thấy tray.
- [ ] **Step 3 — Verify artifact:** Step 1 và `bash scripts/run-tests.sh` → PASS; `dpkg-deb --info dist/q-translate.deb`, `dpkg-deb --contents dist/q-translate.deb` → exit 0 và không có file cấm; `desktop-file-validate data/org.qtranslate.App.desktop` → exit 0. Quét artifact giải nén đối chiếu secret trong bộ private, chỉ báo đường file nếu phát hiện, không in giá trị secret.
- [ ] **Step 4 — Desktop acceptance:** trên 24.04 Xorg, 24.04 Wayland, 26.04 Wayland thực hiện đủ 19 ca mục 15 spec; app native/XWayland, terminal đang chạy lệnh, multi-monitor/fractional HiDPI, ngắn/dài/URL, logout/login, disable/re-enable, mạng lỗi/quota, cancel và clipboard đổi khi chờ. Mỗi ca có PASS/FAIL/BLOCKED, môi trường/version/thời điểm và evidence; thiếu một phiên không tuyên bố hỗ trợ đã nghiệm thu đầy đủ.
- [ ] **Step 5 — Final review/checkpoint:** reviewer mới đọc toàn bộ thay đổi theo Spec/Review Focus, không đọc/export secret. Sửa lỗi Critical/Important bằng regression test RED→GREEN và full suite; ghi các mục chưa xác minh. Commit bản đóng gói khi Git có sẵn, giữ ledger nếu chưa; không tự publish/merge hoặc cài trên máy khác.

Các assertion package/autostart trong thư mục tạm:

```python
self.assertEqual(private_file_members, [])
self.assertEqual(secret_matches_in_package, [])
self.assertEqual(autostart_files_after_enable_twice, [desktop_entry])
self.assertEqual(autostart_files_after_disable, [])
self.assertEqual(source_env_after_uninstall, source_env_before)
```


## Spec coverage và self-review

| Spec | Task sở hữu |
| --- | --- |
| 1–5: ba thao tác, Ubuntu, mặc định, phạm vi | 1, 5, 7, 9 |
| 6: Alt+C, ngôn ngữ/nguồn dài, lỗi | 1, 5, 6, 7 |
| 7–8: Alt+V, stream, prompt, clipboard, 30s hiển thị | 2, 5, 6, 7 |
| 9: crop/vision, source trộn, không OCR/lưu ảnh | 1, 4, 5, 6 |
| 10: popup/ảnh/dashboard đã duyệt, font/scroll | 6, 8 |
| 11–12: provider/key/model, timeout 5/30, audit/import | 3, 4, 5 |
| 13–14: bridge/runtime/store/log/setup/autostart | 1, 2, 3, 7, 8, 9 |
| 15: 19 ca nghiệm thu và ma trận desktop | 9, với test logic ở các task trước |
| 16–18: trạng thái, nguồn tham khảo, kiểm chứng | preflight, 1, 4, 5, 9 |

- Không còn vòng phụ thuộc Task 1/2: context/protocol thuộc Task 1, controller không cần GTK/secret store thật để test.
- Provider callback chỉ phát delta, action ghép text và controller kiểm tra generation; không dùng DTO UI trong transport. `ready` và acknowledgment giải quyết việc hiện success/copy giả.
- Thứ tự model/key được kiểm tra trên cặp đã probe, không suy model mặc định áp dụng cho mọi key; TXT import được merge đúng yêu cầu.
- Review Focus năm mục đều có test cụ thể và ca runtime tương ứng. Test logic không được nâng thành bằng chứng desktop hoặc API vision.
- Kế hoạch không yêu cầu chạy lại audit diện rộng khi đã có kết quả thật; giữ số đo cũ, chỉ thử capability/endpoint còn thiếu.
- Môi trường đang thiếu session được ghi rõ, không dùng lệnh giả để vượt gate hoặc cài extension trong bước planning. Không tự tạo repo/commit khi chưa có `.git`.
- Chỉ thay tài liệu trong lượt này; tất cả checkbox là việc cần làm. Trước triển khai, người dùng duyệt kế hoạch và chọn cách thực thi theo writing-plans.
