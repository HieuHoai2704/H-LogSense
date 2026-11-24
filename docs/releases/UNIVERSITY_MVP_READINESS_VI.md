# University Project Readiness — LogSense AI

05/11/2026 · Workspace `14)LogSense_AI` · **96/100 theo thang kiểm toán nội bộ**. Cổng phát hành University MVP v1.0 chờ duyệt bản source, xác nhận bài học phần còn mở và diễn tập bảo vệ. [Gap analysis trước khi sửa](UNIVERSITY_MVP_GAP_VI.md).

## Before và After

| Tiêu chí | Before | After | Bằng chứng và phần giữ điểm |
|---|---:|---:|---|
| Luồng nghiệp vụ | 23/25 | **25/25** | Manager chưa có grant đăng nhập và tạo dataset đầu tiên. Viewer thấy danh sách rỗng, log ngoài quyền trả 403. Upload → worker → hai detector → Investigation MySQL → Evidence → CSV → logout chạy trên cùng dataset. |
| Kiến thức môn | 18/20 | **19/20** | Xác minh 13 tài liệu, Tkinter đọc 25 dòng thật và connector CRUD PASS. Bài mạng 1–5 đã chạy theo URL đề. Giữ 1 điểm do ISS trực tiếp 404, YouTube chưa có key, Workbench GUI và tiêu chí nộp riêng chưa xác nhận. |
| Kiểm thử | 22/25 | **25/25** | Regression API/MySQL về first dataset, browser sạch và browser hồi quy, retry/rollback/CSRF đã kiểm tra. Restart riêng môi trường sạch và xác minh lại counts. |
| Báo cáo và demo | 15/20 | **18/20** | README, API, ERD, kiến trúc và checklist cài sạch đã đối chiếu. Có báo cáo, PowerPoint 11 trang đã render, kịch bản 8:30 và 25 đáp án. Giữ 2 điểm vì chưa diễn tập bảo vệ do người trình bày thực hiện và bấm giờ. |
| Nộp và chạy lại | 7/10 | **9/10** | Candidate source chạy từ thư mục ngoài dự án với venv, vendor MySQL và datadir mới. Giữ 1 điểm cho bản source chốt đã duyệt và kiểm chứng từ bản giao nộp. |
| **Tổng** | **85/100** | **96/100** | Tăng 11 điểm theo các cổng trên. Điểm kỹ thuật này không thay thế rubric hoặc kết quả chấm của giảng viên. |

## Lượt chạy thực tế

| Phạm vi | Trạng thái | Môi trường và kết quả |
|---|---|---|
| Unit/API discovery | **PASS 157, SKIP 113** | 270 test, Python 3.10.11 / Windows, 10,698 giây. Skip do guard MySQL. |
| Tích hợp MySQL/API | **125/125 PASS** | MySQL 8.4.7, hai schema kiểm thử mới, 21,326 giây, 0 fail/error/skip. Bao gồm một số guard thuần đã chạy trong discovery. |
| Cài sạch | **PASS** | Source candidate copy vào thư mục mới ngoài dự án. Python cài mới bằng `venv` và `pip install -r requirements.txt`. `pip check` sạch. DEMO hiện 6 kết quả. Bản MySQL ZIP được sao chép như điều kiện đầu vào vendor, datadir và credentials được tạo lại ở cổng 13308. Migration `0001 → 0004` PASS. |
| Browser, sạch từ onboarding đến CSV | **6/6 nhóm PASS** | Playwright 1.64.1, Edge, Python trong venv mới, MySQL 13308. Đổi vi/en bằng select và không có nút thừa. Viewer/manager chưa có grant, tạo dataset đầu tiên, empty state, logout, duplicate upload và kiểm tra 403. |
| Upload và detector, cùng dataset sạch | **PASS** | 100.000 parsed, 0 malformed. SHA-256 nguồn `d6b55a02a67d9ab027abae4b60c365edbf9a892fcb6810ff780528512ca01c83`. Worker upload 16,671 giây, Rule 152,572 giây, IF 111,530 giây, một lần đo cục bộ. 158.218 predictions, 158 outputs. CSV 158 dòng và SHA-256 `46854cc05da8ac27314ad36c1bcf8b005afcf588f051c269a5e5a0b3010b5e92`. |
| Restart QA sạch | **PASS** | Tắt/mở đúng runtime mới 13308. Head `0004`, 100.000 events, 158.218 predictions và 158 outputs giống nhau trước/sau. |
| Browser hồi quy BGL giữ từ trước | **12/12 nhóm PASS** | Edge, bộ BGL 100K trên 13307. Có scope bin và CSV 4 dòng, Evidence, 403 và DEMO riêng. 6,72 giây. |
| Tkinter và MySQL Connector | **PASS** | Tk 8.6.12 đăng nhập qua Flask, lấy 25 dòng trong 100.000. Lab connector thực hiện CRUD trong schema học tập riêng. Workbench GUI NOT RUN. |
| Bài mạng | **PASS 1–5, FAIL 6 live, SKIP 7** | Bài 6 HTTP 404 trên endpoint đề, mẫu trang 17 trả 630 giây. Thiếu YouTube API key. Xem [bài nộp](../course/NETWORK_SUBMISSION_VI.md). |
| Bảo vệ, rubric, macOS, SMTP thật | **NOT RUN / chưa xác nhận** | Có bộ slide và kịch bản. Chưa có diễn tập người trình bày, rubric chính thức, chạy macOS hay gửi thư bên ngoài. |

Số lượng test giữa các bộ có phần trùng và được báo cáo riêng. Số đo từ bản cài sạch cho luồng chức năng. Nhãn upload là nhãn do người dùng cung cấp. Chất lượng mô hình được đo độc lập trong [thí nghiệm July](../ml/IF_JULY_HOLDOUT.md). Profile IF được chọn có precision 22,52%, recall 55,43%, F1 0,3203, 351 báo nhầm và 82 bỏ sót. Dữ liệu nguồn và runtime cũ được giữ. Các thao tác ghi, rollback và restart được thực hiện trên schema hoặc runtime kiểm thử tương ứng.

## File thay đổi trong đợt này

| Đường dẫn | Lý do |
|---|---|
| `app/__init__.py`, `app/templates/logs.html`, `app/templates/dashboard.html`, `app/static/js/logs.js` | Trang gốc dùng workspace MySQL khi đã cấu hình. Liên kết từ Explorer mở Investigation theo dataset hiện tại và đường trở về giữ dataset. |
| `app/api/logs.py`, `app/static/js/logs.js`, `scripts/database.py` | Cho tài khoản đã xác thực xem danh sách rỗng, giữ quyền trên truy vấn dữ liệu riêng, hỗ trợ bootstrap có chủ đích với `--no-dataset`. |
| `app/templates/partials/language_picker.html`, `app/static/css/language.css` | Gỡ nút xác nhận ngôn ngữ. JS có sẵn tự gửi lựa chọn. |
| `tests/test_dataset_crud_mysql.py`, `tests/test_i18n.py` | Thêm kiểm tra viewer không grant, manager tạo dataset đầu, route mặc định và DEMO riêng. |
| `scripts/course_network_submission.py`, `scripts/network_lab.py`, `docs/course/NETWORK_SUBMISSION_VI.md`, `docs/course/COURSE_REQUIREMENTS_MATRIX_VI.md` | Tách bảy bài mạng đúng đề, giới hạn origin tải ảnh MDN, ghi trạng thái từng bài và cập nhật ma trận môn. |
| `README.md`, `docs/architecture/README.md`, `docs/database/API.md`, `docs/database/ERD.md`, `docs/releases/UNIVERSITY_REPRODUCTION_VI.md` | Tài liệu bám theo source, cài sạch và quyền của tài khoản mới. Migration schema giữ head 0004. |
| `docs/course/BAO_CAO_LOGSENSE_AI_VI.md`, `docs/course/BAO_VE_LOGSENSE_AI_VI.md`, `docs/course/LogSense_AI_BaoVe.pptx` | Báo cáo tiếng Việt, kịch bản 8:30, 25 câu phản biện và PowerPoint 11 slide đã render. |
| `docs/releases/UNIVERSITY_MVP_GAP_VI.md`, `docs/releases/UNIVERSITY_MVP_V1_PLAN.md`, `docs/releases/UNIVERSITY_MVP_READINESS_VI.md` | Tiêu chuẩn nghiệm thu, kết quả, điểm và việc cần chốt. |

## Kiểm tra bản nộp

Quét file tracked và untracked dự kiến nộp theo giá trị bí mật cục bộ đã biết, định dạng key/token và URL có mật khẩu. Kết quả PASS trong phạm vi quét. Hai hit đã xác minh là placeholder của `.env.example` và private key giả của test. Kiểm tra `.gitignore` loại runtime, venv, BGL, dump và model artifact. Kiểm tra PPTX đọc được, đủ 11 slide, có notes và đã bỏ tên người dùng cục bộ khỏi metadata tác giả. Danh sách SHA-256 xem ở `.local/university-closure/release-review.tsv`. Index rỗng và HEAD giữ `b801b77`.

## Việc còn lại để chốt v1.0

1. Xin xác nhận cách nộp bài ISS khi endpoint 404, chạy YouTube với key được phép, xác nhận yêu cầu Workbench GUI, SMTP thật và nộp riêng Lab 1–5 theo rubric.
2. Tập bảo vệ trong 7–10 phút với bộ slide. Đo thời gian và ghi phần nào dùng kết quả chạy trước, phần nào chạy trực tiếp.
3. Duyệt danh sách Git, chốt candidate, kiểm tra nguồn giao nộp trên máy thứ hai và phê duyệt release. Không có commit/tag/push/merge được tạo trong đợt này.

Phiên Flask cũ tại cổng 5000 vẫn trả giao diện cũ. Chính sách thực thi chặn lệnh quản lý tiến trình để khởi động lại phiên đó. Bản cập nhật đã được xác minh bằng Flask trên môi trường sạch và browser QA riêng.

Bằng chứng riêng trên máy nằm tại `.local/university-closure/`. File log chạy thực có thể chứa token phiên truy vấn và thông tin cục bộ. Chỉ dùng số đo đã chọn để đưa vào hồ sơ nộp.

