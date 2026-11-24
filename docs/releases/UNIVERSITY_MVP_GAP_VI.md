# Gap analysis University Project

Mốc rà soát 05/11/2026. Thang điểm nội bộ lấy từ bản audit 85/100. Bằng chứng PASS phải đến từ thao tác chạy và kết quả đối chiếu. Phạm vi từ Master Plan và checklist University MVP là mục tiêu nội bộ. Tài liệu môn gồm 7 chương Flask và 6 PDF, trong đó trang 16–17 PDF mạng ghi rõ bảy bài phải nộp. Rubric, yêu cầu nộp riêng Lab 1–5, mức độ cần minh chứng SMTP thật và tiêu chí Workbench của giảng viên chưa có xác nhận.

| Tiêu chí | Mốc | Bằng chứng trước sửa | Khoảng thiếu | Ưu tiên | Nghiệm thu |
|---|---:|---|---|---|---|
| Luồng nghiệp vụ | 23/25 | 100K BGL browser, `0004`, RBAC, upload, worker, evidence và CSV | Tài khoản chưa cấp dataset đăng nhập thành công nhưng Explorer gọi danh sách trả 403. Trang mặc định có thể mở DEMO dù có DB. | P1 | Manager mới đăng nhập, tạo dataset đầu tiên với grant từ service. Viewer chưa có grant thấy trạng thái rỗng, route dữ liệu riêng vẫn 403. Browser đi từ Explorer sang Investigation thật và giữ dataset khi trở lại. |
| Kiến thức môn | 18/20 | Ma trận 13 tài liệu, Tkinter/OOP, Jinja, Flask-WTF/CSRF, MySQL, Flask-Mail mock | Bài mạng có nhiều minh chứng dùng URL khác. Workbench GUI, YouTube key và rubric chưa có bằng chứng. | P1 | Gói bài mạng 1–7 bám đề có lệnh chạy, kết quả hoặc lỗi thực, tách phần cần API key. Đối chiếu Tk và MySQL trên ứng dụng. |
| Kiểm thử | 22/25 | 156 PASS discovery, 124 MySQL, browser BGL 12/12 từ lần trước | Thiếu regression onboarding từ account mới, cần kiểm chứng lại sau thay đổi. | P1 | API/MySQL, browser onboarding và BGL thật chạy trên schema riêng. Báo cáo riêng PASS/FAIL/SKIP/NOT RUN. |
| Báo cáo và demo | 15/20 | Báo cáo tiếng Việt, outline 11 slide, kịch bản 8:30 và 20 đáp án | Thiếu slide sẵn dùng. README còn kết quả cũ, ghi sai Tkinter. Chưa có buổi diễn tập có bấm giờ. | P1 | Deck 10–12 trang, số đo được gắn phạm vi, hướng dẫn nguồn thật/DEMO, kịch bản và Q&A dùng được. Ghi rõ phần diễn tập chưa chạy nếu chưa có người trình bày. |
| Nộp và tái lập | 7/10 | Workspace Windows chạy, Git HEAD chỉ mở được DEMO bằng venv sẵn có | Chưa cài candidate trong venv mới và chạy migration trên MySQL sạch. Candidate chưa đóng băng. | P1 | Cài từ danh sách source có thể phát hành vào thư mục mới, venv mới, MySQL datadir mới. Smoke từ DEMO đến nhập BGL và detector. Kiểm tra ignore/secret và giữ danh sách file để duyệt. |

Tài liệu đối chiếu gồm [checklist tám tuần](UNIVERSITY_MVP_V1_PLAN.md), [ma trận học phần](../../academic/course/COURSE_REQUIREMENTS_MATRIX_VI.md), [QA trước sửa](V1_RC1_RETEST.md) và [README](../../README.md).

