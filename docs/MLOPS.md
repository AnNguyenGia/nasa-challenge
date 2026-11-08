# MLOps và Data Analyst

Mô hình Isolation Forest tự train trong `ml/train.py`, phát hiện độ khác biệt so với dữ liệu tổng hợp 4 feature. Tách tập train và validation bằng RNG seed 42, ghi hash dataset, version artifact, feature schema, ROC AUC và false positive rate. Gate AUC >=0.90 và FPR <=0.12 chỉ kiểm tra benchmark tổng hợp; không chứng minh hiệu quả trên phi hành gia.

```bash
docker compose --profile ml up -d mlflow
docker compose --profile ml run --rm trainer
# Copy version từ output rồi promote rõ ràng:
docker compose --profile ml run --rm trainer python -m ml.promote <version>
```

MLflow tại http://localhost:5000 lưu experiment + artifact + registered model. Backend dùng manifest đã promote trong volume local, không phụ thuộc MLflow/network lúc inference. Train không tự promote. MLflow registry là catalog; manifest `current.json` mới là pointer phục vụ tại Edge. Chạy một operator promotion tại một thời điểm.

Rollback: chạy lại promote với version cũ đã đạt gate. Pointer được replace atomically; artifact checksum kiểm tra trước load. Artifact joblib có thể thực thi mã: chỉ dùng artifact do pipeline tin cậy tạo, checksum không thay thế chữ ký và xác thực nguồn.

Data Analyst có thể xuất reading JSON từ API và chạy:
```bash
python -m ml.drift models/current.json readings.json
```
Báo cáo shift trung bình chuẩn hóa với ít nhất 30 mẫu; chỉ gợi ý review, không tự retrain hoặc tự đổi ngưỡng. Chưa triển khai drift dashboard hoặc nhãn lâm sàng. Thay dữ liệu tổng hợp bằng dữ liệu được cho phép, split theo astronaut và thời gian, đánh giá calibration/subgroup, kiểm tra leakage rồi thêm gate có chuyên gia trước dùng thật.

Chưa fine-tune Qwen: agent dùng model nền tại Ollama. Tùy phần cứng có thể đổi QWEN_MODEL; phải pull model tương ứng trước. Prompt guardrails không bảo đảm hoàn toàn đầu ra LLM; demo không dùng lời đáp cho quyết định điều trị tự động.
