# Chạy lại LogSense AI từ thư mục sạch

Hướng dẫn này dùng Windows và MySQL ZIP chạy cục bộ. Chuẩn bị một bản source đầy đủ đã được người nộp duyệt, Python 3.10 trở lên, MySQL 8.4 native đúng kiến trúc và một tệp BGL hợp lệ. Máy cần truy cập nguồn package để cài dependencies. Giữ source tách khỏi runtime cũ.

## 1. Cài và kiểm tra DEMO

Trong thư mục source mới, mở PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1
```

Mở địa chỉ Flask in ra và thêm `/?source=demo`. Kiểm tra có nhãn DEMO và sáu kết quả mẫu. Dừng Flask vừa mở bằng Ctrl+C. Tạo venv trên chính hệ điều hành đang dùng. Đường dẫn tương ứng trên macOS là `.venv/bin/python`; kết quả kiểm thử trong báo cáo áp dụng cho Windows.

## 2. Khởi tạo MySQL mới

Đặt bản MySQL ZIP đã giải nén ở `vendor/mysql` trong thư mục thực hành mới, hoặc thay `--basedir` bằng đường dẫn tuyệt đối đến bản cài vendor. Chọn cổng loopback còn trống. Ví dụ dưới dùng 13308 và thư mục runtime mặc định mới.

```powershell
.\.venv\Scripts\python.exe -m scripts.mysql_runtime init --basedir vendor/mysql --port 13308
.\.venv\Scripts\python.exe -m scripts.mysql_runtime start
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role migrate -- -m flask --app app db current
.\.venv\Scripts\python.exe -m scripts.mysql_runtime grant-dataset-crud --schema logsense_dev
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role app -- -m scripts.database create-user --username investigator --role manager --no-dataset
```

Nhập mật khẩu cục bộ khi được hỏi. `db current` phải báo `0004 (head)`. Helper nạp URL và khóa phiên từ cấu hình riêng của runtime mới. [.env.example](../../.env.example) mô tả biến cho người tự cung cấp kết nối.

## 3. Chạy dữ liệu thật

Mở ba cửa sổ PowerShell tại cùng thư mục source. Chạy mỗi lệnh ở một cửa sổ.

```powershell
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role app -- -m scripts.ingestion_worker
.\.venv\Scripts\python.exe -m scripts.mysql_runtime exec --role app -- -m scripts.worker
```

1. Mở trang gốc. Đăng nhập bằng tài khoản manager vừa tạo. Xác nhận hiện trạng thái chưa có dataset.
2. Tạo dataset trống trong Log Explorer, chọn nguồn thật nếu nguồn tệp đã biết. Dataset mới phải xuất hiện trong danh sách của người tạo.
3. Upload tệp BGL TXT/LOG dưới 16 MiB hoặc CSV có một cột `raw_line`. Xác nhận job từ queued đến completed, số dòng parsed và checksum. Nếu dùng archive Loghub gốc, [runbook ingest CLI](../database/MYSQL_RUNBOOK.md) mô tả cách nhập theo prefix.
4. Chạy Rule và Isolation Forest qua phần Analysis. Đợi job completed, mở liên kết diễn biến bất thường. Kiểm tra cùng dataset, Evidence Drawer và CSV đúng phạm vi. Số output phụ thuộc nguồn và cửa sổ.
5. Đăng xuất rồi thử mở lại URL dataset riêng. Phiên ẩn danh phải bị từ chối. DEMO được truy cập riêng ở `/?source=demo`.
6. Có thể mở thêm `python -m scripts.desktop` để xem cùng dataset bằng Tkinter.

## Checklist nộp

- [ ] Người thứ hai đã chạy đủ các bước trên một bản source đã chốt, ghi hệ điều hành, phiên bản Python/MySQL và kết quả.
- [ ] Không đính kèm dữ liệu BGL lớn, thư mục `.venv`, `.local`, dump, khóa và mật khẩu. Tệp BGL đến từ nguồn được phép.
- [ ] Tài khoản dùng khi trình diễn chỉ có đúng vai trò và grant cần thiết.
- [ ] Ghi rõ các phần được chạy, phần lỗi và phần bị bỏ qua. Chạy SMTP ngoài máy nếu tiêu chí được xác nhận và đã có địa chỉ nhận hợp lệ.
- [ ] Tài liệu nộp bao gồm báo cáo, ERD, slide, [ma trận môn](../course/COURSE_REQUIREMENTS_MATRIX_VI.md) và [bảy bài mạng](../course/NETWORK_SUBMISSION_VI.md).

