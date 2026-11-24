# HDFS_v1 theo block · H-logsen

Pipeline đọc trực tiếp HDFS_v1 ZIP của Loghub, tổng hợp theo block ID và ghép nhãn từ `preprocessed/anomaly_label.csv`. Dùng SQLite phân tích riêng cho từng lượt chạy. Chạy từ gốc dự án hoặc trong terminal của H-logsen.

```powershell
python -m academic.experiments.hdfs_baseline --archive data/raw/HDFS_v1.zip --output .local/hdfs-block-run
```

Dùng thư mục đầu ra mới. Kết quả gồm `blocks.sqlite3`, `report.json`, `count_rule-test.csv` và `isolation_forest-test.csv`. CSV có ID, nhãn, dự đoán, điểm gốc, số sự kiện, dòng gốc đầu và cuối của block. `report.json` có SHA-256 của ZIP và CSV. Lượt thất bại ghi `failed.txt`.

## Giao thức

- Một sự kiện có nhiều block ID được tính cho từng block khác nhau. Nhắc lại cùng ID trong một dòng chỉ tính một lần. Dòng lỗi và dòng không có ID có số đếm riêng.
- Dùng giờ gốc của bộ dữ liệu, không gán múi giờ. Chia theo độ dài trục thời gian 60/20/20. Chỉ giữ block nằm trọn trong một khoảng nửa mở `[start, end)`. Block chạm hai khoảng bị loại khỏi đánh giá.
- Dùng 6 đặc trưng từ sự kiện. Các trường gồm tổng số dòng, số WARN/ERROR, số dòng thuộc từng nhóm thành phần và số dòng nhóm còn lại. ID, thời điểm và nhãn không là đầu vào mô hình.
- Rule xếp hạng theo số sự kiện. Isolation Forest dùng `log1p` của các đặc trưng, seed 42, 100 cây và 256 mẫu mỗi cây, fit trên reservoir 50.000 block train. Điểm cao hơn biểu thị bất thường hơn ở cả hai phương pháp.
- Chọn ngưỡng để tối đa F1 trên validation với FPR không quá 1%, xử lý cả nhóm điểm bằng nhau. Khóa ngưỡng trước khi chấm test. AP là average precision. Chỉ số không xác định ghi `null`.

## Kết quả trên toàn bộ HDFS_v1

SHA-256 của ZIP `04f919f2185821f23f045dca611a7586429bdabc601bd7b43f30005f8e289b01`. Lượt Windows đầu chạy 78,147 giây, gồm 75,285 giây đọc và lập bảng. Đọc 11.175.629 dòng, 0 dòng lỗi, ghép đúng 575.061 block với 575.061 nhãn. Loại 169.367 block cắt qua ranh giới. Giữ 111.854 train, 38.615 validation và 255.225 test. Test có 6.071 block bất thường.

| Phương pháp | Precision | Recall | F1 | AP | FPR | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---:|
| Rule đếm sự kiện | 54,61% | 30,62% | 39,24% | 33,93% | 0,6201% | 1.859 / 1.545 / 4.212 / 247.609 |
| Isolation Forest | 79,34% | 98,09% | 87,72% | 89,51% | 0,6225% | 5.955 / 1.551 / 116 / 247.603 |

Lượt chạy lại trên Windows mất 78,764 giây và cho cùng SHA-256 của cả hai CSV. Đã đối chiếu đủ 255.225 dòng mỗi CSV với SQLite chỉ đọc, gồm ID, nhãn, dòng nguồn, quyết định ngưỡng và confusion matrix.

Phạm vi của kết quả là các block đầy đủ còn lại sau khi cắt theo thời gian, tương đương khoảng 70,55% toàn bộ block. Các đặc trưng dựa trên log của cả phiên. Kết quả dùng để phát hiện sau khi block đã kết thúc. Đơn vị này khác host-window của BGL và VM của OpenStack.

Nguồn [Loghub HDFS](https://github.com/logpai/loghub/tree/master/HDFS) · [Bản dữ liệu Loghub v8](https://zenodo.org/records/8196385).
