# Mô hình và quy tắc

Tạo lại checkpoint demo: `python scripts/build_demo_models.py`. Không thay manifest hash để che giấu checkpoint không tương thích.

Thêm model thật: tạo checkpoint ONNX cục bộ, SHA-256, mô tả input/output/preprocessing, nguồn dữ liệu, metrics kiểm định, giới hạn sử dụng và chứng cứ đánh giá. Mở rộng ModelContract và registry routing; loại dữ liệu phải phù hợp model. Hiện predict chỉ hỗ trợ vector ba số của hai mẫu, vì vậy không chỉ đổi manifest rồi coi là đã hỗ trợ ECG/EEG/BERT. Kiểm thử offline, hash mismatch, input shape, finite values và rollback trước khi kích hoạt. Quyền kích hoạt/rollback chỉ Medical Officer/Admin; rollback yêu cầu lịch sử activation trước.

`app/xai.py` có adapter tùy chọn Tree SHAP và Captum Integrated Gradients. Cài extra `[xai]` khi có model tương thích. Cần lưu background/baseline, phương pháp bất định phù hợp, convergence delta và giới hạn cùng checkpoint. Không coi attribution là nguyên nhân bệnh.

Rule YAML mặc định trong `configs/rules.yaml` chỉ dùng demo và chưa có người phê duyệt. Operational chỉ đọc bản trong DB có active và approved_by. Quy trình: Medical Officer đề xuất POST `/api/v1/alert-rules`; một Medical Officer/Admin khác POST `/{id}/approve`. Trước khi áp dụng, kiểm tra đơn vị canonical, chiều ngưỡng, hysteresis, duration, quality, gap, nguồn và clock. Các con số minh họa chưa có giá trị y khoa được xác nhận.

API `GET /api/v1/alert-rules` trả lịch sử version/payload. Mỗi đề xuất là bản ghi mới; không overwrite rule đã lưu. ACK chỉ xác nhận người đã xem; chỉ clear threshold mới resolve cảnh báo.
