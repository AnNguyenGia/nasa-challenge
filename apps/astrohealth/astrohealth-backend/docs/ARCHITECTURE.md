# Kiến trúc

```mermaid
flowchart LR
  Sensor[MQTT / local adapters] --> Ingest[ingestion process]
  Simulator[simulated 1 Hz] --> Ingest
  Ingest --> DB[(SQLite / SQLCipher WAL FULL)]
  DB --> Alert[deterministic alert process]
  Alert --> DB
  DB <--> API[FastAPI gateway]
  UI[Electron / offline web console] <--> API
  API --> Jobs[(durable bounded job queues)]
  Jobs --> AI[ONNX process]
  Jobs --> XAI[XAI process]
  Jobs --> Report[report process]
  AI --> DB
  XAI --> DB
  Report --> DB
  DB --> Sync[sync process]
  Sync --> FileDrop[encrypted local Ground simulator]
  Scheduler[scheduler / backup process] --> DB
  Supervisor[watchdog supervisor] -. restart .-> Alert
  Supervisor -. restart .-> AI
```

Worker không phụ thuộc API khi chạy độc lập. Alert đọc chỉ số đã commit trong SQLite; không cần AI, Ground hay MQTT còn kết nối. Thời gian phản ứng còn phụ thuộc poll 100 ms, writer contention và tải đĩa, chưa phải bảo đảm hard realtime.

Hàng đợi lưu payload và kết quả trong DB. Khi worker khởi động lại, các job running được đặt pending; inference dùng job UUID làm khóa để tránh tạo hai inference khi replay. Task timeout trả 503 và giữ job; không bịa kết quả.

File waveform dùng tên UUID do hệ thống tạo, không nhận đường dẫn từ client. Ghi file tạm/fsync/rename trước khi lưu con trỏ DB. Nếu DB commit lỗi, có thể còn file mồ côi để phục hồi, chưa tự xóa. Operational bọc file bằng AES-GCM trước khi ghi ra đĩa; DuckDB đọc Arrow đã giải mã trong RAM để không tạo bản plaintext tạm.
