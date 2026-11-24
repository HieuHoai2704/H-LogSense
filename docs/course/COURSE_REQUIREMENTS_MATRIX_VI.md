# Ma trận Python nâng cao — LogSense AI

Rà soát ngày 05/11/2026. Đã đọc 7 chương Flask dạng HTML và 6 PDF trong `Downloads/PythonNangCao`. Cả 13 file trùng SHA-256 với bản đính kèm, tổng cộng 3.357.592 byte. Ma trận tách kiến thức đã trình diễn trong đồ án, bài nộp có câu lệnh cụ thể trong tài liệu và tiêu chí của giảng viên chưa được cung cấp.

## Tkinter và MySQL

| Tài liệu | Nội dung | Bằng chứng LogSense AI | Phần cần xác nhận hoặc làm đúng đề |
|---|---|---|---|
| LAB1, tr. 1–4 | Cửa sổ, resize, Label/Entry/Button, callback, focus, Combobox, Checkbutton, Radiobutton, ScrolledText | [Tkinter companion](../../scripts/desktop.py) kết nối Flask, chọn dataset, tìm log và đọc kết quả. Đã chạy trên Tk 8.6.12, đọc 25 log BGL thật. | Ví dụ của lab dùng nhãn/màu và dữ liệu khác. Phạm vi phải nộp riêng chưa rõ. |
| LAB2, tr. 1–5 | Frame/LabelFrame, grid, padding/sticky/columnspan, menu, tab, sự kiện | Desktop chia Connection, Datasets, Logs và Jobs. Có menu File/Help, Notebook và binding chọn dataset. | Trình diễn ngay trên desktop. Giữ bài lab riêng nếu giảng viên yêu cầu. |
| LAB3, tr. 1–7 | Messagebox, icon, Spinbox, relief, tooltip, Progressbar, Canvas | Desktop có info, warning, yes/no, Spinbox giới hạn trang, tooltip, progress và Canvas báo trạng thái import. 1.000 dòng BGL thật nhập thành công trong lần minh chứng học phần. | Chưa đối chiếu bằng demo riêng cho mọi kiểu messagebox (error, yes/no/cancel) và callback riêng của Spinbox. |
| LAB4, tr. 1–4 | Biến Tk, phạm vi biến, callback, OOP và tooltip tái sử dụng | Desktop có `StringVar`, `IntVar`, `BooleanVar`, `DoubleVar`, lớp Desktop/Tooltip và tách HTTP client. | Phần minh họa `global` và shadowing làm trong bài lab độc lập nếu có chấm đúng ví dụ. |
| LAB5, tr. 1–8 | `mysql.connector`, cấu hình, DDL/CRUD, GUI lưu/đọc MySQL, Workbench | [Bài connector](../../scripts/mysql_course_lab.py) CRUD trên schema học tập riêng bằng dữ liệu trích BGL thật. Desktop thực hiện dataset CRUD qua HTTP. Worksheet SQL đã chạy qua connector. | MySQL Workbench GUI chưa chạy. Bài ví dụ `GUI_MySQL` về sách/trích dẫn dùng mô hình dữ liệu khác. |

## Chương 8 — Mạng

PDF `PYTHONNANGCAO_NET_DOCTHEM.pdf`, tr. 16–17, ghi rõ **“Yêu cầu sinh viên nộp bài”** cho cả bảy bài. Có minh chứng kỹ thuật trong [script mạng](../../scripts/network_lab.py) và [HTTP client](../../scripts/logsense_client.py). Bộ chạy theo URL và tham số gốc đã được tách riêng. [Bài nộp và kết quả thực tế](NETWORK_SUBMISSION_VI.md).

| Bài | Đầu bài | Bằng chứng đã chạy trên đồ án | Tình trạng bài đúng đề |
|---|---|---|---|
| 1 | Lưu HTML, xử lý HTTPError/URLError và nhận xét | Lưu HTML Log Explorer, bắt HTTP 404 và URLError thật. | Bản nộp mở đúng trang Google, lưu HTML và xác minh cả hai ngoại lệ. |
| 2 | Quan sát `urlopen` với Google search `q=test` | Truy vấn BGL qua URL có tham số, đọc status/Content-Type. Bộ lọc INFO trả 93.738 kết quả. | Bản nộp chạy đúng Google, HTTP 200. |
| 3 | So sánh `urlopen` thủ công và `with` trên python.org | Hai cách đọc cùng snapshot BGL, ID trùng, cả hai response đều đóng. | Đã chạy đúng URL trong đề. Hai response được đóng và dữ liệu trùng trong lượt chạy. |
| 4 | Tải các ảnh từ bài HTTP Messages của MDN | Script phân tích HTML và lưu logo từ python.org trong lần chạy có bằng chứng. | Bản nộp tải 5 ảnh từ trang MDN hiện tại. |
| 5 | Chuyển nội dung `sixty-north.com/c/t.txt` thành CSV | Chuyển robots.txt công khai thành CSV 23 hàng. | Đã xuất tệp truyện đúng đề, CSV 17 dòng. |
| 6 | Đọc `response[0].duration` từ JSON ISS pass | Đọc `items[0].timestamp` từ API LogSense, xuất CSV. | Open Notify đã gỡ endpoint, trả 404. Mẫu gốc trang 17 cho duration 630 giây. Các nguồn thay thế đã thử trả 403, chưa có lần ISS trực tiếp. |
| 7 | Gọi YouTube Data API với bốn video ID của đề, ghi CSV thống kê | Có nhánh YouTube dùng `YOUTUBE_API_KEY`. Lần chạy có bằng chứng gọi NASA APOD thật, lưu 3 hàng. | YouTube SKIP vì chưa có key. Kiểm tra các trường API trả về và ghi thiếu rõ ràng. |

Chương 8 cũng giới thiệu HTTP request/response, REST/JSON và XML. API hiện dùng JSON và kiểm thử mã 200/400/403/404/503. Chưa có minh chứng XML riêng. Dataset dùng PATCH cho thay đổi tên. Xác nhận với giảng viên nếu cần bài riêng cho XML hoặc PUT.

## Flask

| Chương | Kiến thức | Bằng chứng trong dự án | Kiểm chứng và giới hạn |
|---|---|---|---|
| 1 Installation | Python, venv, pip, Flask | [requirements](../../requirements.txt), [README](../../README.md), lệnh Flask trong venv. | Windows chạy được, `pip check` PASS. macOS SKIP. |
| 2 Basic Application Structure | App, route/view, request/response, cookie, HTTP status, CLI | [App factory](../../app/__init__.py), [auth](../../app/security.py), [log API](../../app/api/logs.py), Flask shell context. | Trang và JSON đã chạy, có session HttpOnly và SameSite. |
| 3 Templates | Jinja2, inheritance, control structures, errors, Bootstrap, Moment | [base.html](../../app/templates/base.html), [trang dataset](../../app/templates/dataset_pages/), [trang lỗi](../../app/templates/error_page.html). | Jinja kế thừa layout, Bootstrap-Flask với Bootstrap 5, Flask-Moment và asset cục bộ. |
| 4 Web Forms | Flask-WTF, validators, CSRF, thông báo lỗi, flash và redirect | [Forms](../../app/forms.py), [trang server-rendered](../../app/web_datasets.py), [upload](../../app/api/uploads.py). | Browser và MySQL xác minh token ký và header CSRF. Luồng HTML dùng flash và redirect 303 sau POST. |
| 5 Databases | ORM, bảng/quan hệ, CRUD, migrations | [ERD](../database/ERD.md), [models](../../app/models.py), [domain](../../app/domain.py), [migrations](../../migrations/versions/). | MySQL 8.4.7, head 0004. Xóa giới hạn ở dataset rỗng đủ điều kiện. |
| 6 Email | Flask-Mail, cấu hình SMTP, thông điệp, mẫu email | [Alert outbox](../../app/services/alerts.py), [HTML/plain templates](../../app/templates/mail/). | Có bài kiểm thử mock và chế độ chặn gửi. SMTP ngoài hệ thống SKIP. |
| 7 Large Application Structure | Config theo môi trường, factory, Blueprint, tests, migrations | [config.py](../../config.py), [factory](../../app/__init__.py), [Blueprint API](../../app/api/), [tests](../../tests/). | Unit/API, MySQL và browser được ghi trong báo cáo QA. |

## Checklist học phần tối thiểu

- [x] Có minh chứng thực hành cho Tkinter/OOP, Flask, Flask-WTF, Flask-Mail, Blueprint, MySQL CRUD, HTTP/JSON và xử lý lỗi.
- [ ] Chốt với giảng viên danh sách lab nộp riêng, định dạng nộp và rubric. Trong tài liệu đang có, bảy bài mạng được ghi rõ phải nộp.
- [ ] Xác nhận cách chấm bài 6 khi endpoint cũ trả 404 và chạy lại bài 7 bằng YouTube API key được phép dùng.
- [ ] Chạy worksheet trong Workbench GUI và ghi ảnh. Nếu cần minh chứng email gửi thật, cấu hình SMTP ngoài Git và dùng địa chỉ đã được phép.
- [ ] Tập demo từ một máy có Tk và MySQL. Minh chứng học phần hiện có nằm trong `.local/course-real-1f713ea2/` và `.local/course-network-a26f832d/`. Ảnh và dữ liệu cá nhân giữ cục bộ.

