# Bảo vệ LogSense AI — 11 slide, demo và 25 câu hỏi

## Outline 11 slide

| # | Slide | Nội dung và bằng chứng |
|---:|---|---|
| 1 | LogSense AI | Đồ án Python nâng cao. Mục tiêu truy từ một dấu hiệu đến dòng log và quy tắc/mô hình đã tạo dấu hiệu. |
| 2 | Bài toán | Giải thích raw log, parsed event, detection unit và detector output bằng ví dụ một host trong 5 phút. |
| 3 | Kiến trúc | Flask/Blueprint, MySQL, hai worker, Jinja/JS và desktop Tkinter cùng API. Vẽ sơ đồ từ báo cáo. |
| 4 | ERD MySQL | Dataset, artifact, raw/event, unit/run/output, user/grant và alert/audit. Khoanh FK ghép chống tham chiếu chéo. |
| 5 | Ingestion BGL | Raw byte, epoch UTC, nhãn, provenance, checksum. Minh họa commit/checkpoint và resume. |
| 6 | Rule và Isolation Forest | Host-window 300 giây, đặc trưng, ngưỡng và hướng điểm IF. Đưa một Evidence Drawer có thật. |
| 7 | Kiểm định mô hình | Chia theo thời gian, giữ test độc lập. Bảng July holdout cùng cohort và 102 TP, 351 FP, 82 FN. |
| 8 | Điều tra trong workspace | Log Explorer → Timeline Severity/Volume → chọn bin → Evidence → CSV. Nêu 158 outputs và 4 ở bin kiểm thử. |
| 9 | Quyền và cảnh báo | RBAC, grant dataset, CSRF, trạng thái, lịch sử, outbox và trạng thái kiểm thử email. |
| 10 | QA và hiệu năng | 124/124 MySQL, browser BGL 12/12, 100K upload và phạm vi đo lịch sử với 1M parsed logs. |
| 11 | Học phần và giới hạn | Tkinter/OOP, HTTP client, Flask-WTF/Mail, Workbench. Nêu macOS/SMTP còn SKIP và phạm vi nộp mạng. |

## Demo 8 phút 30 giây

Chuẩn bị server Flask đang chạy tại `http://127.0.0.1:5000/?workspace=logs`, MySQL localhost và tài khoản demo đã cấp đúng grant dataset BGL 100K. Mở sẵn cửa sổ Tkinter và báo cáo. Tắt hiển thị mật khẩu, terminal có biến môi trường và thư mục credential. Chuẩn bị ảnh cục bộ trong `.local/rc1-retest/real-browser/` và `.local/course-real-1f713ea2/` để đối chiếu nếu trình duyệt hoặc worker gặp lỗi.

| Mốc | Thao tác | Điều cần nói |
|---|---|---|
| 0:00–0:45 | Mở Log Explorer, chọn DEMO hoặc chỉ rõ nhãn nguồn, đăng nhập tài khoản đã cấp grant. | Phân biệt mẫu minh họa với BGL thật. |
| 0:45–1:45 | Chọn BGL 100K, lọc host, sang trang, mở một raw log. | Chỉ ra UTC, thời gian gốc, dòng nguồn và phân trang máy chủ. |
| 1:45–2:45 | Mở màn hình dataset server-rendered và Tkinter, truy vấn cùng dataset. | Chỉ ra Jinja/WTForms, OOP, callback, HTTP client và dữ liệu chung. |
| 2:45–3:50 | Mở job đã hoàn tất hoặc màn hình tiến độ của lần upload đã xác minh. | Nêu tệp BGL thật, checksum, worker và checkpoint. Có thể dùng tệp BGL nhỏ trong schema riêng nếu hội đồng yêu cầu thao tác trực tiếp. |
| 3:50–5:30 | Sang Investigation, đổi Severity/Volume, chọn bin, mở Evidence Drawer, đóng và xuất CSV. | Giải thích cùng filter scope, kiểm tra ngưỡng/phiên bản, đọc số dòng CSV theo kết quả đang lọc. |
| 5:30–6:20 | Mở Alert và audit của schema demo đã chuẩn bị. | Trình bày acknowledgement và liên kết anomaly. Email có minh chứng mock/chặn gửi. |
| 6:20–7:40 | Trình bày benchmark và holdout July. | Đọc đúng đơn vị, số lượng test và lỗi FP/FN. Mốc 1M thuộc parsed-log workload. |
| 7:40–8:30 | Nêu hai giới hạn quan trọng và kết luận. | Minh chứng học phần và môi trường chưa xác minh. Nhắc lại quy trình kiểm tra dấu hiệu qua log có nguồn gốc. |

Kịch bản dự trù 8:30. Thời lượng tập trình bày thực tế chưa được bấm giờ.

## 25 câu hỏi phản biện

1. **Dự án giải quyết bài toán gì?** Rút ngắn đường đi từ dữ liệu BGL đến dấu hiệu bất thường có thời gian, host và bằng chứng truy lại được.
2. **Vì sao Flask?** App factory và Blueprint tách chức năng, còn Jinja và API cho phép dùng một backend với cả web lẫn desktop.
3. **OOP thể hiện ở đâu?** Model SQLAlchemy, lớp client HTTP, lớp Desktop/Tooltip và parser record có trách nhiệm riêng.
4. **Tkinter dùng để làm gì?** Chọn dataset, đọc log, quản lý metadata theo quyền và xem tiến độ worker bằng cùng API.
5. **Tại sao tách raw log và parsed event?** Raw giữ nguyên nguồn để kiểm tra, parsed event có các trường chuẩn hóa phục vụ truy vấn và detector.
6. **Tại sao giữ hai dấu thời gian?** Epoch UTC phục vụ so sánh ổn định, chuỗi thời gian gốc giúp truy lại đúng thông tin trong tệp.
7. **Ngắt import giữa chừng có chuyện gì?** Batch chưa commit rollback, tiến độ trở về checkpoint cuối đã ghi. Chạy lại tiếp từ vị trí đó.
8. **Làm sao tránh log trùng?** Định danh artifact và vị trí dòng, ràng buộc duy nhất, kiểm tra checksum và idempotency khi chạy lại.
9. **Dataset này đọc được dữ liệu dataset kia không?** API kiểm tra grant, query ràng buộc dataset và FK ghép chặn tham chiếu chéo.
10. **Admin có xem mọi dataset không?** Admin có quyền thao tác cấp vai trò. Dữ liệu cụ thể vẫn cần grant. Khi chưa có grant, tài khoản chỉ thấy danh sách rỗng. Manager có thể tạo dataset đầu tiên.
11. **Đơn vị phát hiện là gì?** Một host-window có log đã parse trong 300 giây UTC. Một unit có thể có kết quả từ nhiều detector.
12. **Rule-based hoạt động ra sao?** Tính giá trị quan sát của cửa sổ, đối chiếu ngưỡng đã cấu hình rồi lưu giá trị và ngưỡng làm bằng chứng.
13. **Isolation Forest hoạt động ra sao?** Mô hình dùng các cây phân tách ngẫu nhiên. Mẫu dễ bị cô lập có điểm native thấp hơn và được đối chiếu ngưỡng.
14. **Dùng nhãn BGL thế nào?** Nhãn dùng cho validation/test và phép ánh xạ sự kiện sang window. Feature extraction dùng thống kê từ log.
15. **Tránh nhìn trước dữ liệu bằng cách nào?** Chia tập theo mốc thời gian. Fit trên train, chọn ngưỡng trên validation rồi mới đo trên test đã giữ riêng.
16. **Vì sao FPR thấp mà precision còn thấp?** Tập July rất hiếm bất thường. Một tỷ lệ báo nhầm nhỏ trên tập âm lớn vẫn tạo nhiều false positive.
17. **Đọc 158 trên timeline thế nào?** Đó là 158 detector outputs của hai run, cùng kỳ lịch sử ghi 153 unit được gắn cờ duy nhất. Bin chọn trong QA cho 4 output.
18. **CSV có đúng những gì đang lọc không?** Có kiểm tra ID và count theo cùng scope, gồm cả lựa chọn bin. Bản test chọn bin cho 4 dòng dữ liệu CSV.
19. **Điểm bất thường có ý nghĩa gì với sự cố?** Nó xếp mức ưu tiên điều tra. Rule, mô hình và raw logs cung cấp chứng cứ quan sát. Nguyên nhân chỉ điền khi được xác minh.
20. **1 triệu dòng đã kiểm tra gì?** Đã đo nhập và API parsed logs trên Windows/MySQL cục bộ. Browser E2E và anomaly workload có số đo riêng với 100K, cần trình bày đúng phạm vi.


21. **Hai lớp CSRF kiểm tra gì?** Header gắn với phiên đăng nhập bảo vệ thao tác theo vai trò. Token Flask-WTF ký theo phiên bảo vệ form HTML và multipart.
22. **Vì sao GET trả 200 với danh sách rỗng nhưng đọc log trả 403?** Người đã đăng nhập có thể xem danh sách quyền của chính họ. Mỗi truy vấn dữ liệu riêng vẫn cần grant cụ thể.
23. **Vì sao có worker upload và worker analysis riêng?** Hai loại job xử lý dữ liệu khác nhau. Chúng có tiến độ và retry riêng, giúp request web trả nhanh sau khi xếp hàng.
24. **Bản cài sạch chứng minh điều gì?** Bản source tự tạo venv, cài dependencies và chạy migration trên datadir mới. Cài từ tag cuối và chạy trên máy của giảng viên cần xác nhận riêng.
25. **Khi BGL upload có nhãn, có công bố được metric ngay không?** Nhãn do người dùng cung cấp được lưu để truy lại. Evaluator chỉ dùng nhãn đủ điều kiện theo đúng detection unit.
