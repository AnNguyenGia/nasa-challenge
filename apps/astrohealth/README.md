# AstroHealth 3.0 — Local Flight Medical Console

Đã thay giao diện Electron cũ bằng bảng điều khiển buồng lái, đồng thời bổ sung backend FastAPI cục bộ. Đây là bản demo kỹ thuật có kiểm thử, chưa phải phần mềm y tế được kiểm chứng.

## Chạy bằng Docker

Mở Docker Desktop, chờ Engine chạy. Trong thư mục ứng dụng AstroHealth, chạy: 

```powershell
.\run-docker.cmd start
.\run-docker.cmd account medical
```

Mở http://127.0.0.1:8000. Dùng `.\run-docker.cmd status`, `logs` hoặc `stop` để kiểm tra, xem log hoặc dừng. Docker volume giữ dữ liệu khi dừng. Cần Internet và vài GB dung lượng trống cho lần build đầu. Cấu hình Compose đã kiểm tra cú pháp; Docker Engine trên máy hiện chưa chạy nên chưa kiểm tra build thực tế.

## Chạy trên máy này

Từ thư mục dự án `C:\Users\LENOVO\Documents\Codex\2026-11-14\t`:

```powershell
npm start
```

Electron mở console cục bộ khi backend đang chạy; nếu chưa có backend, giao diện hiện trạng thái trống và chờ backend. Không tự hiển thị phi hành gia hoặc chỉ số sinh tồn mô phỏng. Nhật ký tự nhập được gắn nhãn nguồn riêng.

Trong SYSTEM PAGES, AI/XAI chỉ chạy ví dụ kỹ thuật có nhãn `model_is_placeholder=true`; không có kết quả sức khỏe khi chưa có phép đo thực. SYNC hiển thị trạng thái Ground và service từ `/health`; hàng đợi và nút retry cần tài khoản Medical Officer hoặc Ground Control Operator. REPORTS chỉ có số liệu đo thực khi backend đã nhận dữ liệu. Trong Electron, nút PDF mở hộp thoại lưu tệp trực tiếp; trong trình duyệt, chọn **Save as PDF** trong hộp thoại in.

Khởi động cả backend và các worker:

```powershell
.\outputs\astrohealth\start-local.ps1
```

Mở `http://127.0.0.1:8000`. Swagger offline tại `/docs`; bảng component tại `/design`. Dừng bằng Ctrl+C. Lần cài đặt đầu cần Internet để lấy dependency; khi chạy không cần Internet. Cần dung lượng trống cho thư viện, DB, WAL và bản sao lưu; nên dành ít nhất 1 GB trước khi bật mô phỏng liên tục.

Khi chưa có tài khoản, bấm **ĐĂNG NHẬP** trong giao diện để tạo tài khoản Medical Officer đầu tiên và tự đặt mật khẩu (ít nhất 12 ký tự). Tính năng này chỉ bật ở chế độ demo; các lần đăng nhập sau dùng tài khoản vừa tạo. Có thể tạo tài khoản qua terminal:

```powershell
cd .\outputs\astrohealth\astrohealth-backend
.\.venv\Scripts\python.exe -m app.cli bootstrap medical
```

CLI hỏi mật khẩu (tối thiểu 12 ký tự). Vai trò tùy chọn: `--role "Medical Officer"`, `Admin`, `Astronaut`, `"Ground Control Operator"`. Astronaut cần `--crew-id UUID` hiện có. Tạo Medical Officer thứ hai nếu cần phê duyệt rule.

Sau khi tài khoản Medical Officer đầu tiên đã được tạo, người dùng có thể bấm **ĐĂNG KÝ** ngay trong app, nhập tên đăng nhập, tên hiển thị và mật khẩu, rồi được đăng nhập vào **hồ sơ demo cá nhân mới**. Hồ sơ này chưa có dữ liệu đo và không được xem dữ liệu của phi hành đoàn hiện hữu. Tự đăng ký chỉ hoạt động ở chế độ demo cục bộ.

Medical Officer đăng nhập và mở **SYSTEM → TẠO HỒ SƠ PHI HÀNH ĐOÀN** để thêm hồ sơ trống, rồi **TẠO TÀI KHOẢN** để cấp vai trò hoặc gắn Astronaut với hồ sơ. Chế độ vận hành chỉ cho phép Medical Officer cấp tài khoản. Danh sách tài khoản trong SYSTEM không hiển thị mật khẩu. Mọi lần tạo hồ sơ và tài khoản được ghi audit.

Mở **SYSTEM → ĐỔI MẬT KHẨU** để thay mật khẩu; tất cả phiên cũ sẽ bị thu hồi.

## Đã triển khai

- DAY/NIGHT/RED-LIGHT, DIM, găng tay, soft key, EICAS/ACK/WHY, ECG Canvas tổng hợp, mô hình người 3D ngoại tuyến và 14 trang.
- FastAPI `/api/v1`, Pydantic v2, SQLAlchemy 2, Alembic; bảng chỉ số vật lý theo tháng và view `measurements`. WAL, FULL cho mọi kết nối ghi, UTC/MET, UUIDv7 cho dữ liệu nghiệp vụ.
- Argon2id, JWT, xoay refresh token, thu hồi phiên, khóa đăng nhập tạm thời, RBAC theo phi hành gia; Ground không được đọc chi tiết sức khỏe. Audit chuỗi hash và kiểm tra khi đọc health.
- Tám tiến trình qua supervisor: API, ingestion, alert, AI, XAI, sync, report, scheduler. Alert không import hoặc chờ AI. Worker có heartbeat và watchdog; hàng đợi AI/XAI/report lưu trong DB, giới hạn 64 tác vụ.
- Alert theo ngưỡng, hysteresis, thời gian kéo dài, chất lượng, gap và thứ tự đồng hồ. ACK không đồng nghĩa đã giải quyết. Rule cần người thứ hai phê duyệt.
- Hai checkpoint ONNX tuyến tính tổng hợp, kiểm tra SHA-256, lazy-load, CPU một luồng, giải phóng sau 60 giây không dùng. Bốn nhóm còn lại báo thiếu checkpoint. Giải thích mẫu là đóng góp tuyến tính chính xác; có adapter SHAP/Captum tùy chọn cho mô hình tương thích về sau.
- Kích hoạt/rollback chọn đúng phiên bản ONNX khi suy luận; XAI kiểm tra phiên bản và hash của lần chạy. Rule mới được duyệt không làm mất các rule demo khác. History giữ mẫu mới nhất khi vượt giới hạn; sync giảm tần suất thử lại khi mất liên lạc và không chặn gói khác đang chờ.
- Parquet lưu ECG/EEG; checksum, kiểm tra crew/đồng hồ, ghi file tạm rồi đổi tên và dọn file nếu DB commit thất bại; DuckDB thống kê mẫu sóng. Ngoài demo, file Parquet được bọc AES-GCM trước khi ghi đĩa.
- Lịch sử LTTB; tổng hợp theo giờ/ngày/tháng và nguồn; nhật ký giấc ngủ, dinh dưỡng, môi trường, lab/cognitive/questionnaire; báo cáo CSV/PDF có nguồn dữ liệu; trợ lý Việt/Anh theo luật, không dùng LLM.
- Outbox Zstd + AES-GCM, ưu tiên cảnh báo, checksum, truyền từng gói 16 KiB, file-drop idempotent và mô phỏng mất liên lạc. Mặc định không gửi bundle; để kiểm thử file-drop, tạo file `data/sim-contact-enabled` trong chế độ demo.
- Không seed hoặc phát dữ liệu mô phỏng khi khởi động. Dữ liệu demo cũ vẫn được giữ trong DB nhưng ẩn theo mặc định. Muốn chạy demo riêng, đặt `ASTRO_SHOW_DEMO_DATA=1`, `ASTRO_SIMULATOR_ENABLED=1` và chủ động chạy `python -m app.cli seed`; không dùng các cờ này khi theo dõi dữ liệu thật. File/UDP/serial/BLE bridge sang MQTT có trong `app.adapters`; phần cứng thật chưa được thử.
- Sao lưu SQLite demo qua online backup; SQLCipher qua `sqlcipher_export`; tối đa bảy bản sao DB. Sóng Parquet cần được sao lưu cùng thư mục `data/waveforms` và bảo quản khóa riêng.

## Kiểm tra

```powershell
npm test
```

Kiểm tra cú pháp JS/Electron, pytest + Hypothesis, Ruff và `mypy --strict`. Môi trường đã kiểm tra trên máy này: Windows, Python 3.13. Dockerfile nhắm Python 3.12 nhưng chưa chạy thử Docker tại đây. Lock dependency thực tế tại `astrohealth-backend/requirements-tested.txt`.

## Phím tắt

H: Dashboard; V: Vitals; O: Organs; S: Sleep; N: Nutrition; E: Env/Rad; X: AI/XAI; A: Alerts; T: History; R: Reports; I: Assistant; Y: Sync; Z: System; D: Design. F: Freeze; U: Cursor; W/C: Master ACK; G: Găng tay; L: Đăng nhập; `]`: Trang kế; Esc: Back/đóng hộp thoại. Không bắt phím khi đang nhập liệu.

## Chế độ mã hóa

Demo dùng SQLite thường và hiển thị `plaintext_demo`. Không được coi đây là lưu trữ an toàn cho dữ liệu y tế thật. Chế độ khác demo yêu cầu SQLCipher, `ASTRO_DB_KEY` hoặc `ASTRO_DB_KEY_FILE`, JWT secret đủ dài và khóa AES-GCM `ASTRO_SYNC_KEY` (64 ký tự hex). Thiếu SQLCipher thì dừng, không âm thầm hạ xuống SQLite thường. Dùng thư mục dữ liệu mới khi đổi từ plaintext sang SQLCipher; không mở DB demo như thể đã mã hóa.

## Giới hạn còn lại

Xem `astrohealth-backend/docs/DECISIONS.md` và `docs/IMPLEMENTATION_STATUS.md`. Ngưỡng đều là ví dụ. Mô hình chưa có kiểm chứng lâm sàng; không có chẩn đoán, chỉ định điều trị hoặc kết nối Ground thật. Chưa xác nhận an toàn vận hành, WCAG đầy đủ, 60 FPS trên phần cứng đích, cảnh báo <1 giây ở tải nhiệm vụ, SQLCipher Windows, Docker hoặc cảm biến thật. Một số bảng nghiệp vụ chuyên sâu hiện là schema mở rộng JSON có phiên bản, chưa hoàn chỉnh như hệ quản lý nhiệm vụ chuyên dụng.

Bản gốc được giữ ở thư mục `work/astrohealth-before` của chat sửa đổi; các asset UI cũ nằm trong `legacy/` của dự án và không được backend phục vụ.

## Mô hình người 3D cục bộ

Dashboard hiển thị mô hình **Man** của mattmerk từ BlendSwap. Kéo chuột hoặc chạm để xoay, nhấp đúp để đặt lại góc nhìn; nút **MỞ RỘNG MÔ HÌNH 3D** mở toàn màn hình. Các điểm đánh dấu mở dữ liệu theo hệ cơ quan như trước. Mô hình chỉ minh họa hình thể tổng quát, không thể hiện nội tạng hoặc cấu trúc giải phẫu được kiểm chứng.

Tệp `dist/assets/man.glb` được chuyển từ bản Blender gốc và được nạp hoàn toàn cục bộ. Mã bộ xem trong `src/man-viewer.js`; sau khi sửa, chạy `npm run build:model-viewer`. Nguồn và giấy phép CC BY-SA 3.0 nằm trong `dist/assets/MAN-ATTRIBUTION.md`. Phần mô hình chuyển đổi thuộc CC BY-SA 3.0, tách khỏi giấy phép mã ứng dụng.

