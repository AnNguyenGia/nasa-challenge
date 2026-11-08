# Kết quả kiểm tra bàn giao — 2026-11-08

## Đã chạy
- 11 tests Python: atomic transaction, duplicate/conflict, concurrent duplicate ingest, restart worker, authorization/schema, Cloud ingestion/no loop, mất ACK/retry, dead letter, agent fallback, ML gate/promotion và corruption rejection.
- 6 tests JavaScript: offline retry, mất ACK, conflict, sai ACK, backoff cap, persistence/re-import IndexedDB và drain idempotent (fake-indexeddb).
- React production build bằng Vite 8.3.6: thành công.
- Kiểm tra UI trong browser thực: lưu bản ghi mẫu khi không có Edge, reload trang, xác nhận dữ liệu và pending vẫn còn. Screenshot bàn giao đi kèm ZIP.
- Docker Compose parse/validate toàn bộ profile; workflow YAML parse; Electron main/preload syntax check.
- npm package-lock.json đã tạo, khớp package.json.

## Môi trường và giới hạn
Python tests chạy với Python 3.13.13, FastAPI 0.141.1, Pydantic 2.13.5, NumPy 2.5.4, scikit-learn 1.9.0, joblib 1.5.3, httpx 0.28.1, uvicorn 0.52.4, pytest 9.1.1. Requirements pin các phiên bản này. Có DeprecationWarning joblib/NumPy trong test artifact nhưng không có test failure.

JS tests và React build chạy trên Node 20.20.2. Electron 45 yêu cầu Node >=22.12; template yêu cầu >=22.22.2 và CI dùng Node 22. Chưa chạy binary Electron hoặc đóng gói AppImage trên máy này. npm install dùng ignore-scripts trong quá trình kiểm tra; khi sử dụng cần npm ci để tải binary Electron.

Đã thử build Docker nhưng dừng ở bước tải dependency lớn vì mạng chậm; **chưa xác nhận build/run container hoàn chỉnh**, profile MLflow hoặc Qwen weights thực. Tests mạng dùng httpx mock, chưa thay thế diễn tập ngắt mạng hệ thống. CI/CD là cấu hình mẫu, chưa chạy trên GitHub hay triển khai máy chủ thật. Hãy chạy scripts/check.sh và diễn tập trong OFFLINE_RUNBOOK.md trên Ubuntu mục tiêu trước bàn giao vận hành.
