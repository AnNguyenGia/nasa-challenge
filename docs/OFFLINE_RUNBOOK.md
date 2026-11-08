# Mất mạng, phục hồi và vận hành

| Sự cố | Hành vi |
|---|---|
| Mất Internet | Electron, Edge, model và Qwen đã tải vẫn chạy tại máy; Cloud outbox tích lũy |
| Edge dừng | Electron tiếp tục lưu IndexedDB, hiển thị cache và số bản ghi đang chờ |
| App bị tắt | Bản ghi đã commit giữ trong profile Electron, gửi tiếp khi mở lại |
| Cloud nhận nhưng ACK mất | Gửi lại cùng UUID; Cloud xác nhận duplicate, không tạo bản ghi trùng |
| Cloud 429/5xx/timeout | Exponential backoff + jitter, giới hạn 5 phút, dừng batch lỗi |
| Sai token | Giữ pending, retry chậm; sửa token rồi restart node |
| 400/404/409/413/422 | Giữ dead letter, không bỏ dữ liệu; cần người vận hành xử lý |
| Ollama không có model/hỏng | Câu trả lời fallback, ingest không bị chặn |
| Không có model phân tích | Hiển thị unavailable, không giả tạo kết quả |
| Đĩa đầy | Không báo lưu thành công khi write lỗi; giải phóng đĩa và thử lại |

At-least-once + idempotency, **không tuyên bố exactly-once delivery**. IndexedDB strict durability và SQLite FULL/WAL giảm rủi ro crash; không bảo vệ khỏi hỏng ổ đĩa, mất profile, sự cố phần cứng hoặc xóa volume. Không chạy `docker compose down -v` nếu cần giữ dữ liệu.

## Diễn tập trên Ubuntu
1. Khởi động Edge + Cloud demo; đặt `CLOUD_URL=http://cloud:8000/api/events` trong `.env` và recreate Edge.
2. Ghi một bản ghi; đợi pending về 0.
3. `docker compose --profile cloud stop cloud`, ghi 3 bản ghi. Edge vẫn nhận; Cloud pending tăng.
4. `docker compose --profile cloud start cloud`; đợi tối đa khoảng 5 phút cho retry, pending về 0.
5. `docker compose stop edge`; ghi tiếp trên Electron; đóng/mở Electron và kiểm tra pending còn nguyên.
6. `docker compose start edge`; đợi Desktop pending về 0, số lượng ID không trùng.
7. `docker compose --profile ai stop ollama`; hỏi agent; xác nhận fallback và vẫn lưu được chỉ số.
8. Kiểm tra metrics bằng token: `curl -H "Authorization: Bearer $EDGE_API_TOKEN" http://localhost:8000/metrics` (export biến từ `.env` trong shell tin cậy).

## Backup/restore
`bash scripts/backup.sh` dùng SQLite backup API để snapshot nhất quán, kể cả WAL. Sao lưu thêm profile Electron (`~/.config/nasa-health-desktop` hoặc tên app trong bản đóng gói), volume `models`, cấu hình bí mật và DB Cloud. Đóng Electron trước khi sao lưu profile. Dữ liệu sức khỏe demo lưu plaintext: dùng mã hóa ổ đĩa Ubuntu/LUKS, quyền OS và bản backup mã hóa.

Restore DB Edge: dừng Edge; dùng `docker compose cp data/backups/<file>.db edge:/data/edge.db`; xóa file `edge.db-wal`/`edge.db-shm` cũ khi chắc chắn không còn writer, đảm bảo UID 10001 sở hữu DB rồi khởi động. Thử restore trên bản sao trước. Dữ liệu sau thời điểm backup có thể thiếu; không xóa profile Electron nếu còn bản ghi pending.

## Dead letter và dung lượng
`GET /api/status` hiển thị số dead letters. Đọc cột last_error bằng SQLite trong môi trường quản trị; không log toàn bộ payload sức khỏe. Sau sửa nguyên nhân, requeue UUID bằng `scripts/requeue.py` (copy vào container hoặc chạy với cùng DB_PATH). Không tự đổi ID của sự kiện đã ACK. Template chưa tự prune dữ liệu: theo dõi dung lượng và thiết kế retention theo nhiệm vụ trước khi vận hành lâu dài.

## Deploy và rollback
CI chạy tests, build frontend/AppImage và backend image. CD chỉ chạy `workflow_dispatch` qua SSH tới Ubuntu có repo tại `/opt/nasa-challenge`, Docker Compose và `.env`. Cấu hình secrets DEPLOY_TARGET, DEPLOY_SSH_KEY, DEPLOY_KNOWN_HOSTS; environment edge-production phải có required reviewers. Chưa cấu hình máy đích và secrets thì chưa triển khai.

Giữ image theo commit SHA. Rollback: đặt `IMAGE_TAG=<old-sha> docker compose up -d --no-build edge`, giữ volume. Schema v1 hiện tại chỉ tạo bảng idempotent; thay schema sau này cần migration có version, backup và kiểm thử rollback tương thích. systemd mẫu ở `infra/systemd` cho host được quản trị; không tự cài vào máy của người dùng.

## Chuẩn bị offline
Trước nhiệm vụ: build image, đóng gói AppImage, pull Qwen, train/promote model và diễn tập restore khi còn mạng. Dùng `docker save/load` cho image; sao lưu/khôi phục volume Ollama riêng vì weights không nằm trong image. Không kỳ vọng `npm install`, `pip install` hoặc `ollama pull` hoạt động khi mất mạng. CPU mặc định; GPU NVIDIA cần cấu hình Container Toolkit riêng.

## Cloud host
Trên Ubuntu Cloud, chạy `docker compose --profile cloud up -d --build cloud`. Caddyfile mẫu ở `infra/Caddyfile` proxy tới loopback 8001; cần hostname/DNS thuộc quyền quản lý của bạn, mở cổng 80/443 và cài Caddy trên host. Không public cổng Edge, Ollama hoặc MLflow. Template không tự tạo DNS, chứng chỉ hay tài khoản cloud.
