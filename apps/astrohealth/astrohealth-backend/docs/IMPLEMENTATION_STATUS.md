# Trạng thái và kiểm chứng

Các giai đoạn đã có bản triển khai chạy cục bộ: DB/auth/audit; ingestion/simulator/live; alert riêng; ONNX/XAI mẫu; API domain/history; reports/assistant; sync/backup; UI/tài liệu/checks.

Phạm vi đã kiểm tra tự động: phân quyền cá nhân/Ground, xoay refresh/logout, chất lượng/hysteresis/duration/gap, alert không AI và replay không trùng, tamper audit, outbox mất mạng/idempotence/backoff, phê duyệt hai người và giữ rule demo khác, kích hoạt/rollback phiên bản ONNX và giải thích đúng checkpoint, truy vấn lịch sử giữ mẫu mới nhất, CSV/PDF, trợ lý từ chối chẩn đoán/thuốc, WebSocket không token, Parquet/DuckDB/checksum, bọc AES-GCM waveform, từ chối crew không tồn tại và dọn file sóng khi DB ghi thất bại, backup restore, docs offline, WAL/FULL. Có 22 kiểm thử pytest, bao gồm một kiểm thử thuộc tính Hypothesis. Ruff và mypy strict áp dụng cho mã app.

Đã quan sát supervisor khởi động tám service và health kiểm tra DB/audit đúng. Khi ổ đĩa thực đầy, các transaction thất bại; watchdog ghi nhận và restart ingestion. Đã dừng chạy liên tục, dọn cache phiên và chạy lại. Chưa thử cắt điện vật lý hay chứng minh bảo toàn khi thiết bị lưu trữ không tuân thủ fsync.

Kiểm tra UI bằng trình duyệt: 1280x800 và 1920x1080; DAY/NIGHT/RED-LIGHT; FREEZE, ACK; điều hướng, trợ lý demo và bảng component. Ảnh trước/sau lưu ở outputs của chat. Chưa có kiểm tra WCAG tự động đầy đủ hoặc đo FPS thiết bị đích.

Các phần chưa hoàn chỉnh: kiểm định y khoa; checkpoint thật cho bốn nhóm còn lại; chính sách INT8/NPU; tài nguyên hard limits; báo cáo tổng hợp dài hạn/mission phase trước-sau; schema quan hệ chuyên sâu cho mission/calibration/nutrition database; UI quản trị rule/model đầy đủ; sync HTTP/TCP/DTN thật và xung đột hai chiều; retention đo/sóng có phê duyệt; benchmark tải 100 Hz nhiều kênh và latency <1 giây; SQLCipher runtime/backup trên Windows; Docker build; phần cứng serial/BLE; xác thực broker operational. Không trình bày các mục này là đã hoàn tất.
