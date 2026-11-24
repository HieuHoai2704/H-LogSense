# Ba hạng mục học phần phụ thuộc bên ngoài

Đối chiếu `PYTHONNANGCAO_NET_DOCTHEM.pdf` tr. 16–17 và `PYTHONNANGCAO_LAB5.pdf` mục 8 với code bài nộp. Bổ sung này nằm ngoài ZIP University MVP đã niêm bằng checksum.

| Hạng mục | Kết quả có bằng chứng | Điều kiện còn mở |
|---|---|---|
| ISS bài 6 | URL gốc với `lat=37.78&lon=-122.41` trả **404**. Open Notify đã gỡ dịch vụ. Bản ghi ví dụ tr. 17 cho `response[0].duration = 630` giây. Đã tải TLE thật của ISS từ CelesTrak (HTTP 200), xác minh NORAD 25544 và checksum, rồi dự báo SGP4 bằng Skyfield 1.55. Lần đi qua đầu tiên dự báo trên chân trời hình học có thời lượng **334 giây**. | Cần giảng viên chấp nhận dự báo tính cục bộ từ TLE công bố hoặc cho phép dùng mẫu tr. 17. Đây là dự báo, chưa đo quan sát thực địa. |
| YouTube bài 7 | **SKIP live**. Biến `YOUTUBE_API_KEY` chưa được cấp. Đề yêu cầu truy vấn bốn video và lưu CSV. Code gửi `videos.list` với `part=statistics` và giữ trống trường dịch vụ không trả về. | Dùng key của project được phép, bật YouTube Data API v3 và giới hạn key cho API đó. Giảng viên xác nhận cách chấm trường chỉ có khi chủ video xác thực hoặc video không truy cập được. |
| MySQL Workbench Lab 5 | **PASS worksheet qua Connector 9.7.0**. Đã chạy nguyên worksheet trên schema học tập tại cổng 13309. INSERT/SELECT cho `reviewed=0`, UPDATE/SELECT cho `reviewed=1`, DELETE cho `remaining=0`. Số bản ghi trước/sau bằng 0. | **Workbench GUI NOT RUN**. Chưa tìm thấy bản cài trong PATH, vị trí chuẩn hoặc Windows registry đã kiểm tra. Nếu bắt buộc, mở worksheet trong Workbench, chạy trên schema học tập và ghi lại kết quả GUI. |

Nguồn chính thức [Open Notify](https://open-notify.org/Open-Notify-API/ISS-Pass-Times/) · [CelesTrak GP formats](https://celestrak.org/NORAD/documentation/gp-data-formats.php) · [Skyfield Earth satellites](https://rhodesmill.org/skyfield/earth-satellites.html) · [Google YouTube videos](https://developers.google.com/youtube/data/reference/rest/v3/videos#statistics)

Dự báo ISS tính cho tọa độ đề bài, TLE epoch `2026-11-04T21:15:15Z`, khoảng `2026-11-06T02:46:33Z` đến `02:52:07Z`, SHA-256 TLE `f2e8a7a89080a8297db75c5561addad48e23bbff6b6a6e6df196f49c762e98ad`. Dữ liệu thô và kết quả lưu trong `.local/iss-course-proof/`. Phiên bản quỹ đạo mới có thể cho kết quả khác.

```powershell
python -m venv .local/iss-course-env
.\.local\iss-course-env\Scripts\python.exe -m pip install skyfield==1.55
.\.local\iss-course-env\Scripts\python.exe -m academic.course.course_iss_prediction --output .local/iss-course-next
```

Dùng một thư mục output mới. Venv chỉ dành cho bài ISS. Worksheet và bằng chứng SQL ở `.local/university-handoff/mysql-course/workbench.sql` và `.local/university-handoff/workbench-worksheet-recheck.json`. Cấu hình YouTube theo [hướng dẫn bài mạng](NETWORK_SUBMISSION_VI.md).

