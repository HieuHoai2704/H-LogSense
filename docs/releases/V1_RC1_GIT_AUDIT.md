# Rà soát Git và kế hoạch v1.0.0-rc1

Ngày 05/11/2026, thư mục `14)LogSense_AI`. Trạng thái **HOLD**. Nhánh hiện tại `feature/mysql-database-foundation`, HEAD `b801b773afefb86317470d4262a2704d00f5e02f`. So với `main` cục bộ, nhánh này đi trước hai commit và đi sau không commit nào. Chỉ kiểm tra trạng thái cục bộ.

## Kiểm tra worktree

Có 179 file tracked, 31 file tracked đã sửa và 130 file untracked sau khi thêm năm tài liệu của lần rà soát. Index có 0 file staged.

| Khu vực | Nội dung rà soát và bằng chứng |
|---|---|
| App/API/UI | Dataset CRUD và grant, upload/worker, Flask-WTF/CSRF, trang Jinja, detector profile, i18n, SMTP/outbox. Đã đối chiếu source và các luồng browser/SQL trong [QA hiện tại](V1_RC1_RETEST.md). |
| Database | Không có thay đổi worktree trong `migrations/`. Head code và schema chạy cùng `0004`. DDL trên schema mới, rollback và FK chéo dataset được kiểm thử. Grant DELETE chỉ trên bảng metadata/ACL cần cho CRUD. |
| Dependencies | `pip check` PASS trong venv hiện tại. Có Flask-WTF, Bootstrap-Flask, Flask-Moment, Flask-Mail, requests và mysql-connector-python. Cài mới vào môi trường trống vẫn là một cổng release. |
| Tài liệu | README và runbook có hướng dẫn môi trường, worker và DB. Hồ sơ học phần và kết quả hiện tại được tách khỏi lịch sử. Kiểm tra các JSON đo lường và ảnh trước khi chọn artifact công khai. |
| Staged | Rỗng. `git diff --check` PASS cho tracked diff. Danh sách mọi file thay đổi, byte và SHA-256 ở `.local/rc1-retest/git/changed.tsv`. Xem toàn bộ tập xét ở `inventory.json`. |

### Bảo mật và dữ liệu

Kiểm tra ignore thực tế trên `.env`, `.local`, `.venv`, BGL archive, storage, dumps và các đường dẫn source/test. `.env.example` được giữ. So sánh các giá trị cấu hình nhạy cảm đang dùng trong QA cục bộ với tập file có thể commit, cộng kiểm tra token phổ biến, mẫu private key và URL DB. Hai kết quả regex đã được đọc lại, gồm `REPLACE_ME` trong `.env.example` và PEM giả kiểm thử redaction trong `tests/test_evidence.py`. Quét theo mẫu và giá trị đã biết có phạm vi hữu hạn. Các bản in secret, raw logs, mẫu email, ảnh có nội dung log, môi trường cục bộ và model bundle giữ ngoài Git.

### P0/P1 trước khi làm rc1

| Mức | Kết quả | Tiêu chí đóng |
|---|---|---|
| P0 | Chưa phát hiện P0 trong phạm vi thử. | Đợt review cuối không có secret thật, cross-dataset leak, migration gãy hoặc mất dữ liệu. |
| P1 | **Đã tái hiện.** Admin chưa có dataset grant đăng nhập 200 và `/api/v1/logs/datasets` trả 403 và UI giữ form đăng nhập. API quản lý metadata và trang `/manage/datasets` trả 200 trong session. | Cho người đã đăng nhập thấy trạng thái chưa có dataset và mở luồng đăng ký dataset theo role, giữ 403 cho log riêng. Test browser từ admin không grant qua tạo dataset đầu tiên và test viewer không grant. |
| P1 | Cài bản phát hành từ thư mục sạch chưa thử trong đợt này. Dev Windows đang dùng venv và runtime local có sẵn. | Làm đúng README trên Windows mới, kiểm tra head 0004, bootstrapping người dùng/dataset và hai worker với schema mới. Ghi rõ macOS SKIP cho đến khi chạy trên Mac. |
| P1 học phần | Bảy bài mạng có yêu cầu nộp. Một số minh chứng đồ án dùng nguồn khác. Workbench GUI và rubric riêng chưa xác minh. | Chốt bộ bài nộp và cách xử lý nguồn cũ/API key, theo [ma trận học phần](../../academic/course/COURSE_REQUIREMENTS_MATRIX_VI.md). |
| P2 / backlog | SMTP thật, screen reader, tải đồng thời và 1M anomaly outputs. | Tách thành đợt kiểm thử riêng theo điều kiện thực tế. |

## Trình tự release candidate

1. Xử lý P1 onboarding và test regression. Rehearse clean install, migration, đăng nhập, upload nhỏ và demo cục bộ. Cập nhật số liệu có timestamp và đóng phạm vi học phần.
2. Dùng manifest `changed.tsv` làm danh sách xem xét, quyết định từng file. Tách source/tests/dependencies, tài liệu/học phần và các báo cáo đo đủ điều kiện. Rà lại báo cáo nào cần kiểm tra dữ liệu riêng trước khi đưa vào release. Ghi danh sách đường dẫn đã duyệt thành file UTF-8 cục bộ, mỗi đường dẫn một dòng.
3. Sau khi được duyệt, stage đúng danh sách, kiểm tra `git diff --cached --name-status`, `git diff --cached --check`, đọc staged diff và quét lại file staged theo SHA/mẫu secret. So manifest staged với danh sách duyệt. Cần thấy từng thay đổi được kiểm chứng và staged chỉ chứa các file đã duyệt.
4. Commit theo nhóm đã duyệt, ghi commit hash và báo cáo QA. Sau khi phê duyệt tag, kiểm tra worktree sạch và tạo annotated tag `v1.0.0-rc1` trên commit release đã xác minh. Lệnh tham khảo `git tag -a v1.0.0-rc1 -m "LogSense AI University MVP release candidate 1" <commit-hash>`. Kiểm tra `git show --no-patch v1.0.0-rc1`.

Lần rà soát này chỉ đọc Git và tạo tài liệu. Index và HEAD giữ nguyên.

