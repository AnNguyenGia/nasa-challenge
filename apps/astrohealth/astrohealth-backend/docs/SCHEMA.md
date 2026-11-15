# Schema hiện tại

`app/core.py` là metadata nguồn; Alembic 0001/0002 tạo schema. Bảng nghiệp vụ có id, created_at, updated_at, version, deleted_at. Service heartbeat là bảng kỹ thuật tạm; alert_evaluations dùng khóa hash kỹ thuật để chống replay.

| Nhóm | Cấu trúc thực tế |
|---|---|
| users / sessions | Tài khoản, Argon2id, vai trò, crew scope, khóa đăng nhập; session refresh hash/expiry/revoked |
| crew_members | name, callsign, mission_id |
| measurements_YYYYMM | metric/value/unit, UTC/MET, crew/device/source, quality/flags; index crew/metric/ts |
| measurements | View UNION ALL của phân vùng |
| alerts | Crew, metric, level, status, rule/measurement reference, nguồn, ACK actor/time, snapshot rule |
| audit_log | sequence, actor/action/resource, previous_hash/hash, payload |
| sync_outbox | ưu tiên, trạng thái, số lần thử, offset, checksum, ciphertext base64 |
| inference_runs | Crew, manifest/version/hash/input/output trong payload |
| service_jobs | Loại service, ưu tiên, trạng thái, input/result/error |
| records | Crew, loại nghiệp vụ, nguồn, payload; sleep/nutrition/environment/radiation/lab/cognitive/questionnaire/event |
| waveform_segments / explanations | Versioned payload cho con trỏ Parquet, hash, metadata; attribution cache |
| Các bảng domain còn lại | Tên bảng theo đặc tả, crew/source/payload versioned; là chỗ mở rộng, chưa phải schema quan hệ chuyên sâu đầy đủ |

Các bảng domain mở rộng gồm missions, environments, mission_phases, roles, permissions, devices, sensors, calibrations, data_sources, lab_results, cognitive_tests, questionnaires, sleep_sessions, nutrition_logs, food_items, nutrition_targets, environment_readings, radiation_exposure_cumulative, alert_rules, ai_models, model_versions, reports, report_items, sync_inbox, sync_state.

RBAC hiện được cưỡng chế trong API, không phải đọc dynamic bảng permissions. Không có API sửa dữ liệu đo. Record mới có UUID mới; chỉnh sửa/conflict 2 chiều chưa triển khai. Không gọi các bảng JSON mở rộng là mô hình quan hệ hoàn chỉnh.
