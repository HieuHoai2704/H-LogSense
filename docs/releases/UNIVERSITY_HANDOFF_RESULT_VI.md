# Nghiệm thu kỹ thuật bản giao nộp University MVP v1.0

Ngày 05/11/2026. Bản kiểm tra áp dụng cho ZIP source cục bộ với SHA-256 `1986d3836c11c5a674a089d8e6fadf2ee7e5476c5076e88caeb78a301aa49864`, tạo từ workspace `14)LogSense_AI` tại Git base `b801b77` và các thay đổi đang làm việc được chọn. Kết quả ràng buộc với chính ZIP này. Manifest trong ZIP và bản bên cạnh ghi hash từng file. [Checklist cài và xác minh](UNIVERSITY_HANDOFF_CHECKLIST_VI.md).

## Điểm trước và sau

| Tiêu chí | Trước | Sau | Căn cứ |
|---|---:|---:|---|
| Luồng nghiệp vụ | 25/25 | 25/25 | Onboarding đã sửa. Browser tạo, đọc, đổi tên dataset và theo dõi upload → ingestion → hai detector → Investigation → Evidence → CSV. SQL suite xác nhận xóa metadata rỗng và bảo vệ dataset có log. |
| Kiến thức môn học | 19/20 | 19/20 | Đã đối chiếu 6 PDF và 7 chương HTML với source. Bài 1–5 chạy lại từ ZIP. ISS, YouTube, Workbench GUI và phần yêu cầu riêng chưa đủ bằng chứng để tăng điểm. |
| Kiểm thử | 25/25 | 25/25 | Unit/API, tích hợp MySQL, browser BGL và restart chạy từ source giải nén. |
| Báo cáo và demo, thang cũ | 18/20 | 18/20 | Bản cũ dành 2 điểm cho phạm vi trình bày đã được loại khỏi nhiệm vụ. Không chuyển 2 điểm này thành điểm đạt. |
| Nộp và chạy lại | 9/10 | 10/10 | ZIP được kiểm tra checksum, cài trên venv và MySQL datadir mới, chạy test từ đúng payload và xác nhận source vẫn khớp sau test. |
| **Tổng theo thang cũ** | **96/100** | **97/100** | Tăng một điểm từ bằng chứng bàn giao và tái lập. |

**Thang kỹ thuật riêng 97/98**. Giữ nguyên trọng số các nhóm khác và bỏ đúng 2 điểm ngoài phạm vi từ nhóm báo cáo. Nhóm này đạt 18/18 trên thang kỹ thuật. Mốc tương đương trước đợt này là 96/98. Đây là thang nội bộ. Còn 1 điểm học phần cần xác minh.

## Kết quả kiểm thử theo suite

| Suite | Kết quả | Phạm vi |
|---|---|---|
| Cài và kiểm tra ZIP | PASS | Windows cùng máy, thư mục giải nén mới, Python 3.10.11, venv mới. Cài runtime bằng constraints Windows đi kèm, Playwright 1.64.1 riêng cho QA. `pip check`, compile và DEMO 6 kết quả đều đạt. |
| Unit/API | **157 PASS, 0 FAIL, 113 SKIP** | 270 test, 11,310 giây. MySQL cases có guard và chạy riêng. |
| MySQL integration/API | **125 PASS, 0 FAIL, 0 SKIP** | MySQL 8.4.7, hai schema kiểm thử mới. Bao gồm auth, RBAC, CSRF, CRUD, xóa có giới hạn, parser, upload duplicate/retry và rollback. Không cộng suite này với discovery. |
| Migration/schema | PASS | Datadir MySQL mới tại 13309, Alembic `0001 → 0004`. `flask db check` báo không có thao tác upgrade mới. |
| Browser E2E | **7/7 nhóm PASS, 0 FAIL** | Edge, Playwright. Login/logout, viewer/manager, tạo/đọc/đổi tên dataset, kiểm tra 403 và empty state. Dropdown tự đổi vi/en, Investigation mở cùng dataset. |
| BGL thật và Evidence | PASS | Upload 100.000 dòng, 0 malformed và SHA-256 nguồn khớp. Upload trùng trả lại job. Worker nhập 16,948 giây. Rule 154,838 giây và IF 109,912 giây. Cả hai job đều replay idempotent. Lưu 158.218 predictions, 158 outputs. Evidence và CSV 158 dòng khớp. |
| Restart/recovery | PASS | Shutdown/start đúng runtime thử nghiệm cổng 13309. Head 0004, 100.000 log, 158.218 predictions và 158 outputs giữ nguyên. |
| Tkinter và MySQL Connector | PASS | Tk 8.6.12 đọc 25 dòng BGL thật qua API. Connector CRUD trên schema học tập riêng. |
| Workbench GUI, SMTP ngoài, macOS | NOT RUN | Không tìm thấy Workbench GUI trong các vị trí/đăng ký đã kiểm tra. Thiếu điều kiện xác minh SMTP ngoài. Lượt này chỉ kiểm thử Windows. |

## Học phần và phạm vi còn mở

- Labs 1–4 đã đối chiếu widgets, layout, menu/tab, callback, biến Tk và OOP với companion. Các ví dụ độc lập của Lab 3 về một số hộp thoại và callback Spinbox, phần `global` của Lab 4 và yêu cầu nộp riêng vẫn được ghi rõ trong ma trận. Không đánh đồng demo chức năng tương đương với việc chạy đúng từng ví dụ.
- Lab 5 đã chạy connector CRUD và có worksheet SQL. Cần mở worksheet bằng Workbench để có minh chứng GUI nếu giảng viên yêu cầu.
- Bài mạng 1–5 đều PASS từ bản ZIP. MDN tải 5 ảnh, bài truyện tạo 17 dòng CSV. Bài 6 HTTP 404 ở URL gốc, ba dịch vụ thay thế trả 403. Kết quả 630 giây là trích đúng mẫu trong tài liệu. Cần giảng viên chấp thuận mẫu hoặc chỉ định dịch vụ khác. [Thông báo ngừng API của Open Notify](https://open-notify.org/Open-Notify-API/ISS-Pass-Times/).
- Bài 7 SKIP vì không có `YOUTUBE_API_KEY` hợp lệ. Hướng dẫn đặt key trong phiên PowerShell cục bộ có trong [bài nộp mạng](../course/NETWORK_SUBMISSION_VI.md). Phần Flask 1–7 đối chiếu bằng factory, Blueprint, Jinja, Flask-WTF, ORM, PRG/flash, outbox và test. Xem [ma trận đầy đủ](../course/COURSE_REQUIREMENTS_MATRIX_VI.md).
- Chưa có rubric chính thức cho yêu cầu lab nộp riêng, Workbench và SMTP thật. Bản cài sạch kiểm tra trên một máy Windows với thư mục và runtime mới. Xác minh độc lập trên máy người nhận chưa chạy.

## Source, an toàn và bàn giao

Đã rà soát diff và file chưa commit theo nhóm factory/Blueprint, OOP, ORM/migrations, auth/RBAC, i18n, worker, upload và API. Không ghi nhận lỗi P0/P1 phần mềm trong phạm vi chạy. Quét ZIP theo secret cục bộ đã biết, mẫu token/key, URL credentials và đường dẫn profile. Hai ngoại lệ đã đọc lại là mật khẩu mẫu `REPLACE_ME` và private key giả của test. Các thành phần ngoài ZIP gồm MySQL vendor, BGL dùng thử, runtime, venv, credentials, logs QA và model artifact riêng. Core DEMO và Rule/IF chạy với prerequisites đã nêu. Không thiếu dependency runtime trong môi trường đã thử.

- `README.md` trỏ đến báo cáo kỹ thuật và checklist giao nộp.
- `docs/releases/UNIVERSITY_HANDOFF_CHECKLIST_VI.md` hướng dẫn cài đúng constraints, xác minh checksum và chạy lại.
- `docs/course/COURSE_REQUIREMENTS_MATRIX_VI.md` và `docs/course/NETWORK_SUBMISSION_VI.md` cập nhật ISS, kết quả theo đề và cấu hình YouTube key.
- `docs/releases/UNIVERSITY_HANDOFF_RESULT_VI.md` là biên bản kiểm thử bên ngoài ZIP. ZIP đã thử được giữ nguyên theo checksum.

**Kết luận bàn giao**. ZIP đạt cổng kỹ thuật Windows với phạm vi đã thử và sẵn sàng để người nhận kiểm tra. Còn các điều kiện học phần trên để chốt 100/100 kỹ thuật. Chưa gắn tag hoặc tạo Git release. Báo cáo chạy thô và manifest lưu ở `.local/university-handoff/`.

