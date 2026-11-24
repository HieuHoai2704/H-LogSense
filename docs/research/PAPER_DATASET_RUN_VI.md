# Chạy thử kho dataset paper trên LogSense AI

Ngày 06/11/2026. Kiểm tra đủ **58 tệp** theo manifest và đọc tối đa **1.000 dòng của một thành phần đại diện** cho mỗi nguồn log hoặc trace. Kiểm tra file và giới hạn đọc khác với import toàn bộ corpus. Thử nghiệm thực tế trên **MySQL 8.4.7**, Python 3.10.11, Windows và runtime QA loopback 13308. Schema mới migrate đến 0004 và đối chiếu ORM. [Manifest nguồn](paper_dataset_artifacts.json) · [Kết quả đo và ma trận đủ 58 tệp](measurements/paper-dataset-matrix-2026-11-06.json)

| Phạm vi | Kết quả |
|---|---|
| Đọc tệp và so SHA-256 | **58/58 PASS** |
| Định dạng BGL | **4 tệp tương thích**, nhập **302.000 dòng** qua cùng BGL importer |
| Mẫu log hoặc trace dùng cấu trúc khác | **27 tệp** bị bộ kiểm tra upload chặn, 25 vì schema và 2 vì encoding. Detector **NOT RUN** |
| Dữ liệu bảng, gói tái lập hoặc tệp nghiên cứu | **27 tệp** ngoài hợp đồng đầu vào của BGL importer. Detector **NOT APPLICABLE** với pipeline này |

HDFS, OpenStack, Spirit, Thunderbird, Liberty, Hades, Hadoop và các log hệ thống còn lại nằm trong nhóm chưa tương thích. ADFA-LD dùng chuỗi syscall, HDFS_v3 có graph/trace, các bộ này cần mô hình dữ liệu khác. Không gán nhãn BGL cho các nguồn đó.

## Import và truy vấn ứng dụng

Ba bản BGL lớn dùng 100.000 dòng đầu của từng bản. BGL_2k dùng đủ 2.000 dòng. Đếm mỗi dòng theo tệp nguồn, bao gồm hai bản Loghub có cùng byte trong đoạn 100K. Khi nguồn là TAR/GZIP hoặc log rời, gói thử ZIP chứa byte nguyên gốc theo đúng thứ tự để gọi importer hiện tại. Kiểm tra toàn bộ số dòng nhập, byte offset, SHA-256 tiền tố và so từng nhãn đã lưu với token gốc của 302.000 dòng.

| Tệp | Parsed events | Alert theo nhãn nguồn | Import giây | Logs API | Timeline và CSV | Evidence API |
|---|---:|---:|---:|---|---|---|
| BGL.zip | 100.000 | 2.609 | 24.04 | PASS | PASS | PASS |
| BGL-Loghub-3227177.tar.gz | 100.000 | 2.609 | 25.14 | PASS | PASS | PASS |
| BGL-CFDR.gz | 100.000 | 2.613 | 23.70 | PASS | PASS | PASS |
| BGL_2k.log | 2.000 | 143 | 0.38 | PASS | PASS | PASS |

Thời gian là từng lượt trong schema QA, ba nguồn lớn nhập đồng thời. Kiểm thử giao diện ở lớp API qua Flask test client và MySQL thật. Kiểm tra Timeline và CSV đối chiếu tập ID trong cơ sở dữ liệu. Evidence lấy một anomaly thật theo dataset và kiểm tra dòng nguồn.

## Detector và chất lượng trên mẫu

Dùng Rule count p99 trên train và Isolation Forest ngưỡng p01 của score validation theo chính sách hiện tại, seed 42. Chia train/validation/test theo thời gian của từng mẫu. Đơn vị là **host × 5 phút UTC** và dương tính khi có ít nhất một alert gốc trong các log quan sát được của cửa sổ. AP là average precision. Đây là phép chạy chức năng trên các mẫu đã biết, chưa mở thêm holdout độc lập.

| Tệp | Detector | Worker | Cửa sổ test | Precision | Recall | F1 | FPR | AP | TP / FP / FN |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| BGL.zip | Rule đếm log | PASS | 79.109 | 60,13% | 17,39% | 26,98% | 0,0776% | 0.1772 | 92 / 61 / 437 |
| BGL.zip | Isolation Forest mặc định | PASS | 79.109 | 0,00% | 0,00% | 0,00% | 0,0064% | 0.2546 | 0 / 5 / 529 |
| BGL-Loghub-3227177.tar.gz | Rule đếm log | PASS | 79.109 | 60,13% | 17,39% | 26,98% | 0,0776% | 0.1772 | 92 / 61 / 437 |
| BGL-Loghub-3227177.tar.gz | Isolation Forest mặc định | PASS | 79.109 | 0,00% | 0,00% | 0,00% | 0,0064% | 0.2546 | 0 / 5 / 529 |
| BGL-CFDR.gz | Rule đếm log | PASS | 79.109 | 60,78% | 17,55% | 27,23% | 0,0764% | 0.1817 | 93 / 60 / 437 |
| BGL-CFDR.gz | Isolation Forest mặc định | PASS | 79.109 | 0,00% | 0,00% | 0,00% | 0,0064% | 0.2558 | 0 / 5 / 530 |
| BGL_2k.log | Rule đếm log | PASS | 257 | — | 0,00% | 0,00% | 0,0000% | 0.0856 | 0 / 0 / 22 |
| BGL_2k.log | Isolation Forest mặc định | PASS | 257 | 0,00% | 0,00% | 0,00% | 0,8511% | 0.0770 | 0 / 2 / 22 |

Trình đánh giá gắn trong ứng dụng chỉ truy vấn nguồn nhãn loghub-bgl/original. Ba biến thể được lưu với nguồn riêng nên báo cáo native có 0 cửa sổ đủ nhãn. Ma trận trên tính điểm riêng từ các prediction đã lưu, đối chiếu đúng nhãn theo nguồn và kiểm tra số log đầy đủ cho từng cửa sổ. Giá trị — là chỉ số không xác định, ví dụ precision khi không có cảnh báo.

Hai bản Loghub có SHA-256 tiền tố 100K trùng nhau. BGL CFDR khác 4 dòng và cả 4 khác ở nhãn nhị phân. Host và epoch của từng cặp tương ứng giữ nguyên. Cùng một anomaly score có thể cho metric khác do nhãn nguồn thay đổi.

| Bản so với BGL Loghub v8 | Detector | Cửa sổ khớp host và thời gian | Quyết định khác nhau | Chênh lệch score tối đa |
|---|---|---:|---:|---:|
| BGL-Loghub-3227177.tar.gz | rule | 79.109 | 0 | 0.0 |
| BGL-Loghub-3227177.tar.gz | isolation_forest | 79.109 | 0 | 0.0 |
| BGL-CFDR.gz | rule | 79.109 | 0 | 0.0 |
| BGL-CFDR.gz | isolation_forest | 79.109 | 0 | 0.0 |

Chạy 36/36 unit test PASS cho parser, upload staging và calibration. Một lần gửi lại job bằng cùng khóa idempotency trong lúc worker ghi dự đoán trả HTTP **503 database_unavailable**. Sau khi các worker hoàn tất, **8/8** lần gửi lại trả HTTP 200 và giữ nguyên 8 job. Lượt kiểm tra API đầu tiên trong harness dài trả 400. Lượt kiểm tra lại với Flask client mới, sau khi chạy detector, đã PASS cho cả bốn bộ. [Số liệu chi tiết](measurements/paper-dataset-matrix-2026-11-06.json)
