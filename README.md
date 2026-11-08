# Space Health — NASA Space Apps project template

**Hybrid Edge–Cloud + Event-Driven Modular Monolith + AI Agent Architecture**

Template Ubuntu cho challenge “Create Health Monitoring Software for Astronauts on Space Missions”. Một backend Python/FastAPI chia module, chạy cùng code tại Edge và Cloud; không phải hệ thống microservice. Electron/React lưu dữ liệu offline trước khi gửi. Qwen chạy local qua Ollama. Pipeline Python tự train mô hình, quality gate, MLflow, promotion và rollback.

## Chạy nhanh
Yêu cầu: Ubuntu 22.04/24.04, Docker Engine + Compose v2, Node.js >=22.22.2 (xem `.nvmrc`), npm, Python 3.12 cho tests/ML local. Desktop cần phiên đồ họa Ubuntu và thư viện hệ thống Electron (GTK3, NSS, ALSA; Ubuntu 24.04 dùng các gói t64 tương ứng). Không chạy Electron bằng root hoặc `--no-sandbox`.

```bash
cd ~/Desktop/nasa-challenge
bash scripts/init-env.sh
# Backend Edge hoạt động cả khi không cấu hình Cloud/AI:
docker compose up -d --build edge
cd apps/desktop
npm ci
cd ../..
bash scripts/desktop.sh
```

Electron mở dashboard, ghi chỉ số, xem trend và hàng đợi, xuất bản sao JSON, hỏi Qwen. `npm run dev` đơn lẻ chỉ xem UI trình duyệt; Electron IPC mới kết nối backend. `npm run build` rồi `bash scripts/desktop.sh start` chạy bundle production. `npm run dist` trong apps/desktop đóng gói AppImage (cần môi trường Linux hỗ trợ build Electron).

### Qwen offline tại Edge
```bash
docker compose --profile ai up -d ollama
docker compose --profile ai exec ollama ollama pull qwen3:4b
```
Lần đầu cần Internet tải weights, sau đó chạy tại máy. Thiếu weights hoặc timeout sẽ dùng fallback. Qwen 4B CPU có thể chậm; tăng cấu hình phần cứng hoặc chọn model phù hợp.

### Cloud demo trên cùng máy
Trong `.env`, đặt `CLOUD_URL=http://cloud:8000/api/events`, sau đó:
```bash
docker compose --profile cloud up -d --build cloud edge
```
Cloud ở localhost:8001; Edge ở localhost:8000. Với Cloud thực, triển khai cùng image trên Ubuntu khác, NODE_ROLE=cloud, DB/secret riêng và HTTPS gateway; đặt CLOUD_URL và CLOUD_API_TOKEN ở Edge. **Chưa có cloud account được provision hoặc dịch vụ được deploy bởi template này.**

### Train và promote
Xem [MLOPS](docs/MLOPS.md). MLflow là tùy chọn; có thể train hoàn toàn local:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m ml.train
python -m ml.promote <version-in-output>
# Backend chạy Docker dùng volume models, hãy train/promote bằng profile ml để chia sẻ đúng volume.
```

### Kiểm thử
```bash
source .venv/bin/activate
bash scripts/check.sh
```
Tests bao gồm ghi atomic, duplicate/conflict, worker restart, mất ACK, retry, dead letter, xác thực, Qwen fallback và model checksum/gate. Runbook có diễn tập ngắt Edge/Cloud. Xem [VALIDATION](docs/VALIDATION.md) để biết những gì đã chạy khi bàn giao.

## Cấu trúc
```text
apps/desktop/           Electron + React + IndexedDB outbox/cache
backend/app/core/       config, SQLite transaction/persistence
backend/app/modules/    telemetry, event bus, analytics, AI agent
backend/tests/          integration/resilience tests
ml/                     train, evaluate, drift, promote/rollback
infra/systemd/          auto-start mẫu trên Ubuntu
scripts/                env, desktop, backup, deploy, requeue, checks
.github/workflows/      CI, manual CD, ML candidate pipeline
compose.yaml            Edge, Cloud profile, Ollama, trainer, MLflow
```

## Phạm vi và phần cần mở rộng
Đã có đường chạy từ UI → lưu offline → Edge event → analytics → Cloud sync, cùng agent và pipeline mẫu. Chưa có tích hợp wearable, ultrasound, huyết áp/đường huyết, cảnh báo lâm sàng đã thẩm định, tài khoản/RBAC, phân quyền nhiều nhiệm vụ, đồng bộ hai chiều, push notifications hoặc medical protocol engine. Các chức năng này có thể thêm qua module/event mới.

Đây là template hackathon; không phải thiết bị y tế hoặc phần mềm sẵn sàng bay. Dữ liệu tổng hợp và kết quả model không dùng chẩn đoán, kê đơn hay khẳng định sức khỏe. Dữ liệu lưu local chưa mã hóa ở tầng ứng dụng. Dependency versions được pin làm baseline; rà soát security và cập nhật lockfile trước production.

- [Kiến trúc và event contract](docs/ARCHITECTURE.md)
- [Offline, backup, deploy và rollback](docs/OFFLINE_RUNBOOK.md)
- [MLOps](docs/MLOPS.md)
- [Nguồn tài liệu](docs/SOURCES.md)
# nasa-challenge
