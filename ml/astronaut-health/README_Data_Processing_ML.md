# NASA Challenge – Data Processing & Machine Learning

## Các notebook
- `04_Data_Integration_completed.ipynb`: tích hợp CBC + Serum và Plasma Proteomics, kiểm tra chất lượng, xuất bảng.
- `05_Machine_Learning.ipynb`: kiểm tra label, phân bố lớp, xác minh quy ước thời điểm, so sánh Dummy/Logistic Regression/SVM/Random Forest bằng Leave-One-Astronaut-Out.

## Chạy
1. Giải nén dự án.
2. Mở thư mục `nasa challenge` trong VS Code/Jupyter.
3. Cài thư viện: `python -m pip install pandas numpy matplotlib scikit-learn openpyxl`.
4. Chạy `04_Data_Integration_completed.ipynb` từ đầu đến cuối.
5. Chạy `05_Machine_Learning.ipynb` từ đầu đến cuối.

Notebook đọc trực tiếp các thư mục OSD đã giải nén, không yêu cầu ZIP nguồn hoặc `data_raw`.

## Dữ liệu và giới hạn
- Phân tích ML hiện dùng OSD-569 + OSD-575 (CBC + Serum) và OSD-571 (Plasma) thành hai bài toán riêng.
- OSD-573 và OSD-574 chưa được đưa vào ML trong hai notebook này.
- `L-92`, `L-44`, `L-3` biểu thị số ngày trước launch; `R+1`, `R+45`, `R+194` biểu thị số ngày sau return. Số âm trong dạng relative-day là hợp lệ theo quy ước này, không đồng nghĩa ngày lịch âm.
- Chỉ có 4 phi hành gia và 21–28 mẫu mỗi bảng; kết quả ML mang tính thăm dò, không đủ để tuyên bố mô hình đã tổng quát hóa tốt cho phi hành đoàn khác.
- Không ép metric cao, không chỉnh nhãn để tăng điểm. Báo cáo cả Balanced Accuracy, F1 và kết quả từng fold.

## Đầu ra ML
Notebook 05 tạo trong `processed_data/`:
- `Label_Validation_Report.csv`
- `Label_Distribution_Report.csv`
- `ML_Model_Comparison_LOAO.csv`
- `ML_LOAO_Fold_Results.csv`
