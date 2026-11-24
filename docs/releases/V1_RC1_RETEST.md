# Tái kiểm thử LogSense AI sau đổi thư mục

Ngày 05/11/2026 · Windows · `14)LogSense_AI` · **Kết quả chức năng PASS với tài khoản đã cấp grant. Release v1.0.0-rc1 HOLD vì lỗi onboarding P1.**

MySQL ZIP 8.4.7 trên loopback `127.0.0.1:13307` đang sẵn sàng, datadir thuộc runtime QA, session UTC. Flask đang chạy tại `http://127.0.0.1:5000/`, trả 200 ở trang chính và database health. Các lần ghi thử dùng schema mới, với tài khoản runtime và migrator riêng. Trong test DELETE, đối tượng bị xóa là metadata rỗng do chính test tạo. Dataset và dữ liệu có từ trước không bị xóa. Các schema kiểm thử được giữ lại.

## PASS / FAIL / SKIP

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Unit/API discovery | **156 PASS, 112 SKIP**, 268 tổng | 10,540 giây. Nhóm MySQL có guard và chạy ở mục kế tiếp. |
| MySQL integration | **124/124 PASS** | 21,668 giây trong runner, 0 fail/error/skip. Hai schema mới. Có guard trùng với discovery, do đó không cộng thành tổng độc lập. |
| Migration/ORM | **PASS** | Áp dụng 0001 → 0004 trên schema mới, model diff rỗng, 1,446 giây ở lần E2E. Server hiện có và code cùng head 0004. Test có FK chéo dataset và rollback. |
| Login/RBAC/CSRF với grant | **PASS** | Từ chối anonymous và dataset ngoài grant. MySQL bao phủ viewer/analyst/manager/admin. Browser có đăng nhập admin, viewer và manager. |
| Admin chưa được cấp dataset | **FAIL — P1** | Hai lần browser không chuyển khỏi form đăng nhập. API login và auth/me 200, /api/v1/logs/datasets 403, /api/v1/datasets và /manage/datasets 200 trong session. |
| Upload BGL và queued worker | **10/10 nhóm PASS** | Browser dùng schema mới với seed grant. 100.000 parsed, 0 malformed. Tổng thời gian 25,785 giây cả suite, 19,969 giây từ worker đến Explorer đã xác minh. Mục xóa seed đã có dữ liệu SKIP vì seed rỗng. Luồng từ chối xóa dataset mới đã nhập vẫn được xác minh. |
| Ingest từ archive, rollback, resume | **PASS** | Lần E2E mới giữ checkpoint 1.000 sau lỗi chèn trước commit ở dòng 1.500, rồi tiếp tục 10K/100K. Đối chiếu 100.000 raw/parsed/labels và byte nguồn. Lặp không nhân đôi. |
| Rule và Isolation Forest worker | **PASS** | 90.334 feature vectors mỗi detector. Mỗi run lưu 79.109 predictions, Rule gắn cờ 153 và IF gắn cờ 5. Job idempotency đã thử lại. |
| Explorer, Timeline, Evidence, CSV | **12/12 nhóm PASS ở mỗi bộ BGL** | Một lượt trên dataset 100K giữ từ trước, một lượt trên pipeline vừa tạo. 158 detector outputs, bin chọn 4 outputs và 4 dòng CSV. Có keyset, provenance, filter, network retry, dữ liệu rỗng, 400/403/404, và khôi phục focus. |
| Alerts và audit | **9/9 nhóm browser PASS** | Tạo 1 cảnh báo từ Rule, cooldown chặn 152 kết quả khác. Replay tạo 0. Browser xác nhận cảnh báo, thấy ghi chú/lịch sử và mở Evidence liên kết. SMTP mock trong SQL tests. |
| DEMO riêng biệt | **PASS** | Workspace 21/21, Evidence Drawer 13/13. Dữ liệu tổng hợp, gắn nhãn DEMO. |
| Browser layout/accessibility | **PASS trong phạm vi tự động** | Edge/Playwright không lỗi trang trong các nhóm PASS. Không tràn ngang trang ở 1366/1440/1920. Axe 4.10.3 kiểm tra DEMO, Logs và Investigation tại 1366, 0 violation tự động. Có kiểm tra cần đánh giá tay. |
| Dependency integrity | **PASS** | `python -m pip check` không báo lỗi trong venv hiện tại. |
| Restart, macOS, SMTP thật, screen reader, tải đồng thời | **SKIP** | Runtime cục bộ đang phục vụ dữ liệu QA, tái kiểm thử không restart. Có [chứng cứ restart trước đó](E2E_REAL_BGL.md). Clean install trên máy khác và phép đo 1M toàn chuỗi không thuộc các lượt chạy hiện tại. |

### Điều tra lỗi tài khoản mới

Tài khoản mới không có hàng `user_datasets`. Middleware ở [app/api/logs.py](../../app/api/logs.py#L51) từ chối mọi route log nếu tập grant rỗng. Trong [app/static/js/logs.js](../../app/static/js/logs.js#L198), UI đợi gọi danh sách log dataset thành công rồi mới ẩn login panel. Điều này chặn ngay đường vào quản lý dataset inline ở tài khoản chưa có dataset. Dùng tài khoản đã có grant để trình diễn hiện tại. Trường hợp tái hiện được giữ ở `.local/rc1-retest/no-dataset-admin.json`. Tiêu chí sửa ghi trong [kế hoạch rc1](V1_RC1_GIT_AUDIT.md).

### Tái chạy chuỗi BGL và đo thực tế

Các chặng ingest 1K, bổ sung đến 10K, bổ sung đến 100K đo lần lượt **0,395 s, 1,588 s, 23,344 s**. Tổng các chặng thành công khoảng 25,327 s, không tính lần ngắt cố ý, thời gian kiểm tra provenance hoặc lần lặp. Prefix BGL 13.259.718 byte có SHA-256 `d6b55a02a67d9ab027abae4b60c365edbf9a892fcb6810ff780528512ca01c83`. EXPLAIN query trang log theo dataset/UTC chọn `ix_events_dataset_time_id`, kiểu range và Extra `Using where; Using index`.

Rule worker **163,438 s**, peak RSS **676,12 MiB**. IF worker **119,102 s**, peak RSS **679,81 MiB**. RSS lấy mẫu tiến trình Python mỗi 20 ms, không gồm mysqld. Thời gian là một lần chạy cục bộ. Các thao tác kiểm thử khác trên máy có thể ảnh hưởng. Số dự đoán phục vụ xác minh pipeline. Chất lượng thuật toán trên holdout độc lập được trình bày trong [báo cáo July](../ml/IF_JULY_HOLDOUT.md).

HTTP dưới đây đo trên dataset giữ từ trước, Edge qua loopback, 12 lượt GET warm tuần tự mỗi endpoint. Đã nhận toàn bộ response body.

| Endpoint | p50 ms | p95 ms | Payload byte |
|---|---:|---:|---:|
| Logs, trang giới hạn | 29,38 | 45,40 | 11.653 |
| Anomaly Timeline | 31,41 | 35,16 | 21.980 |
| Investigation | 40,18 | 43,27 | 183.677 |
| Evidence | 18,96 | 26,00 | 3.416 |
| CSV theo bin | 11,15 | 12,27 | 562 |

Login đến log ready khoảng 343 ms và Investigation navigation đến ready khoảng 741 ms trong kịch bản này. Benchmark [10K/100K/1M parsed events](../database/IMPLEMENTATION_REPORT.md) là số đo lịch sử. Không dùng hai phép đo ở môi trường/thời điểm khác nhau để tính cải thiện trước/sau.

## Bằng chứng cục bộ

Tất cả nằm trong `.local/rc1-retest/`. `unit.txt`, `mysql.json`, `upload-browser-granted/dataset-crud-browser.json`, `real-browser/browser-after.json`, `new-pipeline/results/`, `new-pipeline/browser/browser-before.json`, `alerts-browser.json`, `accessibility.json` và `demo/` ghi các lượt chạy. Ảnh và log có thể chứa dữ liệu xem trên màn hình, do đó giữ trong thư mục cục bộ đã ignore. Các lượt browser onboarding FAIL được giữ riêng với lượt upload PASS.

