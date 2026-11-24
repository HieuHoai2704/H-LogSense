# Nộp riêng bảy bài lập trình mạng

Đề gốc là PDF `PYTHONNANGCAO_NET_DOCTHEM.pdf`, tr. 16–17. Chạy bài nộp trong venv LogSense AI. Script dùng đúng URL, tọa độ và danh sách video của đề. Flask và MySQL không cần chạy.

```powershell
python -m scripts.course_network_submission --output .local/network-bai-nop
```

Thư mục output phải mới để giữ các lần chạy. `results.json` ghi trạng thái từng bài. Mở file HTML cục bộ bằng trình duyệt để nhận xét nội dung trả về.

| Bài | Kết quả đã chạy trên Windows | Nhận xét |
|---|---|---|
| 1 | PASS. Google trả HTTP 200, lưu `01-google.html`. Probe riêng bắt HTTPError 404 và URLError. | Nội dung là HTML máy chủ trả về. HTTPError có mã phản hồi. URLError xảy ra khi không hoàn thành kết nối. |
| 2 | PASS. `q=test` trả HTTP 200 và `text/html`. | `urlopen` trả đối tượng response. Đọc body mới thu được nội dung HTML, không phải một danh sách JSON kết quả. |
| 3 | PASS. Cả hai cách đọc URL trong đề cho kết quả cùng bytes và đều đóng response. | Cách thủ công dùng `try/finally` để đóng khi có lỗi. `with` tự gọi phương thức giải phóng khi rời khối. |
| 4 | PASS. Tải 5 ảnh PNG/SVG được tham chiếu bởi trang HTTP Messages. | URL cũ chuyển sang bản hướng dẫn hiện tại. Các tệp ảnh thực tế nằm trên CDN của MDN. [Trang MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Messages) |
| 5 | PASS. URL truyện đúng đề trả nội dung, lưu CSV 17 dòng dữ liệu. | CSV giữ số dòng và nội dung văn bản. |
| 6 | FAIL ở endpoint trực tiếp, HTTP 404. Hàm trích `response[0].duration` trả 630 giây với mẫu được in ở tr. 17. | Kết quả 630 thuộc mẫu trong tài liệu. Open Notify xác nhận đã gỡ endpoint. Ba endpoint thay thế được thử cùng tọa độ và đều trả 403 trong môi trường này. [Thông báo của Open Notify](https://open-notify.org/Open-Notify-API/ISS-Pass-Times/) |
| 7 | SKIP. Môi trường không có `YOUTUBE_API_KEY`. | Khi có key, script gọi `videos.list` và giữ trống trường không được API trả về. Google giới hạn `dislikeCount` cho truy vấn được chủ video xác thực và đã loại bỏ việc dùng `favoriteCount` như một số thống kê hữu ích. [YouTube Data API](https://developers.google.com/youtube/data/reference/rest/v3/videos#statistics) |

Bài 6 cần giảng viên chấp nhận dùng dữ liệu mẫu hoặc chỉ định endpoint thay thế. Với bài 7, chạy lại bằng API key được phép dùng và ghi các video/trường mà dịch vụ thực sự trả về. Lượt chạy giữ ở `.local/university-closure/network-final/`.


Khi có key được phép, đặt biến môi trường trong một phiên PowerShell 7 cục bộ. Sau đó chạy lại bộ bài vào thư mục mới.

```powershell
$env:YOUTUBE_API_KEY = Read-Host -MaskInput "YouTube API key"
try { python -m scripts.course_network_submission --output .local/network-youtube }
finally { Remove-Item Env:YOUTUBE_API_KEY }
```
