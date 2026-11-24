# Mở và sử dụng H-logsen

Cập nhật: 2026-11-07 (Asia/Saigon).

Thư mục: `D:\1)_KHUTAOSONG\2)Project\14)LogSense_AI`.

## Web hiện tại

- Log Explorer/đăng nhập: http://127.0.0.1:5000/?workspace=logs&dataset_id=1
- Bàn làm việc: http://127.0.0.1:5000/
- Điều tra dữ liệu mẫu: http://127.0.0.1:5000/?source=demo
- Anomaly Timeline thật: http://127.0.0.1:5000/?source=db-1 (đăng nhập trước).

Launcher `.local/run-logsense.py web` mở H-logsen cùng cấu hình BGL hiện có trên MySQL cổng 13307. Dùng tab **Phân tích** để đăng nhập và chọn dataset được cấp quyền.

## Tạo tài khoản của bạn một lần

Mở CMD rồi chạy:

```cmd
cd /d "D:\1)_KHUTAOSONG\2)Project\14)LogSense_AI"
.venv\Scripts\python.exe .local\run-logsense.py create-user --username hieu
```

Nhập mật khẩu ít nhất 12 ký tự khi được hỏi. Không hiện ký tự trên màn hình là bình thường. Lệnh tạo tài khoản admin có quyền dataset BGL 1; không ghi đè tài khoản đã tồn tại. Nếu đã có tài khoản phù hợp, dùng tài khoản đó. Không có mật khẩu mặc định; không đặt mật khẩu trong câu lệnh.

## Khởi chạy web khi server cũ đã dừng

Nếu phiên web cũ đang dùng cổng 5000, dừng phiên đó trước khi mở lại. Cài thêm yêu cầu Workbench một lần trong venv.

```cmd
cd /d "D:\1)_KHUTAOSONG\2)Project\14)LogSense_AI"
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m scripts.run.mysql_runtime --root .local/university-e2e-mysql start
.venv\Scripts\python.exe .local\run-logsense.py web
```

Giữ cửa sổ chạy. Launcher tự mở một tab có quyền thao tác tệp cục bộ và dùng terminal. Dùng **Dự án → Mở dự án**, nhập đường dẫn thư mục. Đổi ngôn ngữ trong **Thiết lập → Ngôn ngữ**. Ctrl+C dừng phiên web tự mở.

## Chạy worker cho upload và phân tích

Web và cả hai worker phải dùng cùng launcher để cùng database. Mỗi worker chạy trong một cửa sổ CMD, vào thư mục dự án bằng lệnh `cd /d` như trên.

Worker nhập file:

```cmd
.venv\Scripts\python.exe .local\run-logsense.py ingestion
```

Worker phân tích:

```cmd
.venv\Scripts\python.exe .local\run-logsense.py analysis
```

Giữ các cửa sổ chạy; Ctrl+C dừng worker bạn tự khởi chạy. `Queued` nghĩa là đang chờ worker, chưa hoàn thành. Launcher chỉ là tiện ích local cho workspace có sẵn, nằm trong `.local` và không được Git track.

## Đọc dữ liệu đã có

1. Đăng nhập Log Explorer và chọn dataset được cấp quyền. Dataset 1 hiện có 100.000 parsed BGL logs thật.
2. Chọn Start/End theo UTC, host, log level hoặc Search message, rồi bấm Apply. Khoảng thời gian là `[start,end)`: không bao gồm mốc End.
3. Dùng Previous/Next để phân trang. Click ô Log volume để giới hạn thời gian. Export scoped CSV xuất đúng phạm vi đang xem.
4. Bấm Evidence ở một dòng để xem raw log và nguồn file/dòng; Escape đóng drawer, giữ ngữ cảnh.
5. Mở `/?source=db-1` để xem anomaly đã lưu. Severity hiển thị priority; Volume hiển thị số anomaly. Click cell để lọc bảng, kéo brush rồi zoom để xem khoảng nhỏ hơn.
6. Click anomaly để xem detector/run/version, observed/reference và raw provenance. Score không phải xác suất hoặc bằng chứng root cause.

## Upload mới và chạy detector

1. Mở Manage datasets → Register a dataset. Nhập tên và key riêng như `bgl-my-study-01`. Tạo dataset chưa tự nhập log.
2. Mở Import BGL log data, chọn dataset mới và file, rồi Queue BGL import.
3. File phải là BGL `.txt`/`.log`, hoặc CSV chỉ có một cột `raw_line`, tối đa 16 MiB. ZIP lớn và CSV tùy ý có cột timestamp/message không phải định dạng upload được hỗ trợ.
4. Chạy ingestion worker, theo dõi progress và Refresh import status đến Completed. Nếu Failed, đọc lỗi; chỉ Retry khi hệ thống cho phép.
5. Chọn dataset đã nhập, mở Alerts and analysis jobs → Queue window rule. Chạy analysis worker; Check job đến Completed.
6. Mở `/?source=db-ID` với ID dataset thật để xem anomaly. Job Completed có thể không tạo anomaly; bảng rỗng không luôn có nghĩa là lỗi.
7. Queue Isolation Forest là baseline hiện có. Queue validated BGL IF chỉ dùng frozen model cho windows từ 21/07/2005 UTC trở đi. Dataset tháng 6 không phù hợp profile này nên nút có thể bị khóa.

## Quyền và giới hạn

- Viewer xem dữ liệu được cấp quyền; Analyst thêm upload/analysis; Manager/Admin tạo/đổi tên dataset; chỉ Admin xóa dataset mới còn trống.
- Dataset đã có log/job/detection được bảo vệ khỏi Delete.
- Nhãn upload là supplied/unverified; metric có thể null khi không đủ ground truth phù hợp.
- Credentials, database, uploads, model và backup nằm trong `.local`; không xóa thư mục này để dọn code.
- `127.0.0.1` là máy đang chạy ứng dụng; từ máy khác không truy cập bằng localhost của máy đó.
- Chuyển máy cần setup venv/MySQL native theo README và runbook; launcher này dùng workspace hiện có trên máy Windows này.

## Tkinter, bài mạng và quản lý dataset

Web và companion dùng chung tài khoản và quyền dataset. Khi cần tài khoản mới có quyền trên cả BGL 100K và dataset 12 vừa nhập, tạo một username mới rồi nhập mật khẩu tại CMD.

```cmd
.venv\Scripts\python.exe .local\run-logsense.py create-user --username hieu_course --dataset 12
.venv\Scripts\python.exe -m scripts.run.desktop
```

- Trong desktop, đăng nhập rồi chọn dataset, bấm **Read logs** để đọc từ API. **New**, **Rename** và **Delete empty** sử dụng quyền của tài khoản. Tab **Import progress** theo dõi job của file vừa upload khi ingestion worker chạy.
- Trong Log Explorer, mở **Manage datasets** để dùng form render bằng Jinja. Sau khi lưu, Flask trả 303 và hiển thị thông báo ở trang GET.
- Trang quản lý dùng Bootstrap 5 từ Bootstrap-Flask và Moment.js lưu cục bộ. Thời gian UTC vẫn có sẵn trong HTML.
- `LOGSENSE_PROFILE` nhận `development`, `testing` hoặc `production`. Profile production yêu cầu HTTPS cho cookie đăng nhập. Profile testing chặn gửi email.

Xuất log thật bằng Python client, sau đó chạy các bài HTTP và lưu kết quả vào thư mục mới.

```cmd
.venv\Scripts\python.exe -m scripts.run.logsense_client --username hieu_course --dataset 12 --csv .local\course-logs.csv
.venv\Scripts\python.exe -m academic.course.network_lab --username hieu_course --dataset 12 --output .local\course-network-results
.venv\Scripts\python.exe -m academic.course.mysql_course_lab --source-csv .local\course-logs.csv --output .local\course-mysql-results
```

Các bài mạng đọc HTTP/JSON thật, tải ảnh từ trang Python và xuất CSV. Bài 7 gọi YouTube theo đề khi có biến môi trường `YOUTUBE_API_KEY`. Khi chưa cấu hình khóa YouTube, script lấy các bản ghi APOD thật từ NASA qua khóa công khai của API.

Script MySQL tạo một schema thực hành riêng, dùng `mysql.connector` để chạy INSERT → SELECT → UPDATE → DELETE rồi lưu `workbench.sql`. Mở worksheet trong MySQL Workbench, kết nối `127.0.0.1:13307` với user `logsense_app` và mật khẩu của runtime đó. Worksheet chứa transaction tự rollback và chỉ truy cập schema thực hành ghi trong file.

## Kiểm tra email cảnh báo

Đặt `ID_CANH_BAO` bằng ID của một alert đang chờ gửi trong cùng workspace.

```cmd
set SMTP_ENABLED=1
set MAIL_SUPPRESS_SEND=1
.venv\Scripts\python.exe .local\run-logsense.py notify --alert-id ID_CANH_BAO
```

Kết quả `suppressed` ghi số thư Flask-Mail dựng được và số gửi là 0. Thư có phần văn bản, HTML và CSV tham chiếu. Notification vẫn ở trạng thái chờ. Để gửi thực tế, cấu hình `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO` ở máy chạy, đặt `MAIL_SUPPRESS_SEND=0` và chỉ định alert cần gửi. Thông tin xác thực thuộc biến môi trường cục bộ.
