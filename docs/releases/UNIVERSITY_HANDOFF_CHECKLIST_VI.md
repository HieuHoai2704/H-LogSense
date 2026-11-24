# Kiểm tra bản giao nộp University MVP v1.0

Bản ZIP chứa source kỹ thuật, migrations, tests và tài liệu cài đặt. `MANIFEST.tsv` ghi SHA-256 và byte của từng payload. Đối chiếu SHA-256 toàn ZIP với tệp checksum đi kèm. Windows PowerShell có `Get-FileHash -Algorithm SHA256`. Giải nén vào thư mục mới trước khi chạy.

## Windows sạch

- [ ] Có Python 3.10, hỗ trợ Tk khi chạy companion, Microsoft Edge nếu chạy browser QA, và MySQL 8.4 ZIP vendor đã giải nén. Các thành phần vendor và tệp BGL nhập thử được cung cấp ngoài gói source.
- [ ] Tạo venv mới. Để tái lập cấu hình đã kiểm thử trên Windows/Python 3.10, chạy `python -m pip install -r requirements.txt -c WINDOWS-QA-CONSTRAINTS.txt` và `python -m pip check`. Playwright là phụ thuộc kiểm thử tùy chọn. Cài thêm bằng `python -m pip install playwright -c WINDOWS-QA-CONSTRAINTS.txt`.
- [ ] Theo [hướng dẫn cài sạch](UNIVERSITY_REPRODUCTION_VI.md) để mở DEMO, tạo MySQL runtime mới, áp dụng migration đến head `0004` và tạo manager chưa được cấp dataset. Không trỏ bài kiểm tra ghi dữ liệu tới schema đã có dữ liệu.
- [ ] Kiểm tra login/logout, dataset CRUD theo vai trò, nhập BGL, ingestion worker, hai detector, Log Explorer, Timeline, Evidence và CSV. Sau restart runtime thử nghiệm, so lại counts.
- [ ] Chạy `python -m unittest discover -s tests -q`. Đọc [hướng dẫn tích hợp](../database/TESTING.md) để chạy nhóm MySQL có guard. Ghi riêng kết quả của từng suite.
- [ ] Đọc [ma trận môn học](../../academic/course/COURSE_REQUIREMENTS_MATRIX_VI.md) và [bài nộp mạng](../../academic/course/NETWORK_SUBMISSION_VI.md) để xác định phần cần API key hoặc giảng viên xác nhận.

Tên bản ZIP đánh dấu phạm vi bàn giao cục bộ. Việc gắn tag hoặc phát hành Git cần duyệt riêng.

