# Khung code LogSense AI hiện tại

Kiểm đếm trực tiếp ngày 2026-11-05 (Asia/Saigon), tại `D:\1)_KHUTAOSONG\2)Project\14)LogSense_AI`.

**272 file thuộc phần dự án**, gồm file đang được Git quản lý và file mới chưa commit, theo quy tắc Git ignore. Đây không phải 272 file code chạy ứng dụng.

| Phần | Số file | Vai trò |
|---|---:|---|
| app | 54 | Ứng dụng chính: Flask backend và frontend |
| scripts | 23 | Workers, lệnh vận hành, benchmark và QA |
| tests | 19 | File unit/API/integration tests |
| migrations | 8 | Cấu hình và lịch sử schema MySQL |
| docs | 162 | Tài liệu, báo cáo, kết quả JSON/CSV và hình minh họa |
| data | 1 | File hỗ trợ cấu trúc dữ liệu; archive lớn bị loại khỏi Git |
| File ở thư mục gốc | 5 | README, cấu hình, dependencies và ignore |
| Tổng | 272 | Không đếm venv/runtime/backup/cache/dataset lớn |

Không tính `.git`, `.venv`, `.local`, cache và các dataset/archive lớn bị Git bỏ qua. Các thư mục này vẫn tồn tại và có thể chứa hàng nghìn file. Chỉ `app` là phần ứng dụng chính, có 54 file. `tests` có 19 file, khác với số test cases; báo cáo QA đã ghi 264 cases ở discovery và DB execution riêng.

## Frontend và backend nằm ở đâu?

- Backend: `app/api`, `app/services`, `app/parsers`, models/domain/security.
- Frontend: `app/templates` là HTML/Jinja; `app/static/css` là giao diện; `app/static/js` là tương tác.
- Database: models/domain mô tả ORM; migrations lưu thay đổi schema.
- Workers: scripts/ingestion_worker.py và scripts/worker.py chạy ngoài HTTP request.

Đây là Flask modular monolith: các module cùng một ứng dụng, không có hai app frontend/backend độc lập và không dùng React/Vue.

## Cây code có chú thích

Tất cả file code/cấu hình/kiểm thử được liệt kê dưới đây. Tài liệu và dữ liệu được gom theo nhóm để giữ cây dễ đọc.

```text
14)LogSense_AI/ (thư mục gốc)
├── app/ (54 file; ứng dụng chính)
│   ├── __init__.py (tạo Flask app và route giao diện chính)
│   ├── access.py (chính sách quyền nguồn Demo)
│   ├── database.py (kết nối SQLAlchemy/MySQL và đăng ký API)
│   ├── demo.py (fixture minh họa, không phải kết quả AI thật)
│   ├── domain.py (bảng user, quyền dataset, evaluation và incidents)
│   ├── extensions.py (SQLAlchemy, migrations và Base dùng chung)
│   ├── forms.py (WTForms cho dataset/upload, validation và CSRF)
│   ├── models.py (bảng source, logs, units, detector, runs và outputs)
│   ├── presentation.py (chuẩn bị dữ liệu Jinja và payload)
│   ├── repositories.py (truy vấn có giới hạn theo dataset)
│   ├── security.py (login/logout, session, RBAC và quyền dataset)
│   ├── api/ (10 file; HTTP/REST endpoints)
│   │   ├── __init__.py (khai báo package API)
│   │   ├── alerts.py (API luật cảnh báo và quản lý incident/audit)
│   │   ├── anomalies.py (Investigation, timeline và Evidence API)
│   │   ├── database.py (API kết quả MySQL được bảo vệ)
│   │   ├── datasets.py (tạo/đọc/đổi tên/xóa dataset rỗng)
│   │   ├── forms.py (nhận form dataset và signed CSRF)
│   │   ├── jobs.py (queue/status/retry analysis và model card)
│   │   ├── logs.py (filter, phân trang, volume, raw và CSV logs)
│   │   ├── mysql_export.py (xuất CSV anomaly cùng filter scope)
│   │   └── uploads.py (upload, trạng thái và retry import)
│   ├── parsers/ (2 file; đọc định dạng log)
│   │   ├── __init__.py (khai báo package parser)
│   │   └── bgl.py (BGL streaming, UTC, label, host, malformed rows)
│   ├── services/ (19 file; logic xử lý nghiệp vụ)
│   │   ├── __init__.py (khai báo package services)
│   │   ├── alerts.py (alert idempotent và SMTP outbox có retry)
│   │   ├── bgl_ingestion.py (batch import, checkpoint và resume)
│   │   ├── csv_safety.py (chặn công thức độc hại trong CSV)
│   │   ├── database_evidence.py (bằng chứng DB có giới hạn/redaction)
│   │   ├── dataset_management.py (CRUD/RBAC và bảo vệ dataset đã nhập)
│   │   ├── detection.py (rule/IF baseline cấp sự kiện)
│   │   ├── detector_calibration.py (split/sampling/threshold validation)
│   │   ├── evidence.py (hợp đồng Evidence Drawer cho Demo)
│   │   ├── investigation.py (scope và timeline aggregation Demo)
│   │   ├── log_queries.py (scope/snapshot chung logs, volume và CSV)
│   │   ├── mysql_evidence.py (Evidence Drawer từ anomaly/log MySQL thật)
│   │   ├── mysql_investigation.py (timeline/facets/bảng anomaly MySQL)
│   │   ├── redaction.py (che dữ liệu nhạy cảm khi hiển thị)
│   │   ├── uploads.py (private staging, checksum/provenance/import job)
│   │   ├── validated_if.py (inference frozen IF, không retrain)
│   │   ├── window_deployment.py (persist replay của frozen IF study)
│   │   ├── window_detection.py (features/rule/IF/prediction cho host-window)
│   │   └── window_features.py (tham chiếu feature fit trên train thôi)
│   ├── templates/ (4 file; HTML/Jinja2 frontend)
│   │   ├── dashboard.html (trang Investigation chính)
│   │   ├── logs.html (Log Explorer, login và panel inline)
│   │   ├── query_error.html (hiển thị lỗi tham số truy vấn)
│   │   └── partials/ (mảnh giao diện dùng lại)
│   │       └── workspace.html (timeline, filter và bảng Investigation)
│   └── static/ (8 file; frontend tĩnh)
│       ├── css/ (2 file; màu sắc và bố cục)
│       │   ├── main.css (Investigation và drawer chính)
│       │   └── console.css (console/Log Explorer MySQL)
│       └── js/ (6 file; tương tác trên trình duyệt)
│           ├── dashboard.js (filter, timeline, brush/zoom và state)
│           ├── evidence.js (drawer, raw/related logs và focus)
│           ├── logs.js (login, log query, paging, volume, raw drawer)
│           ├── datasets.js (dataset CRUD inline)
│           ├── uploads.js (upload, progress, refresh và retry)
│           └── incidents.js (analysis jobs, model card và incidents)
│
├── scripts/ (23 file; chạy từ terminal, không phải trang web)
│   ├── database.py (CLI đăng ký dataset, tạo user và import)
│   ├── mysql_runtime.py (start/stop/status, grants, backup/restore)
│   ├── ingestion_worker.py (worker thực thi upload/import jobs)
│   ├── worker.py (worker thực thi analysis jobs)
│   ├── audit_if_holdout.py (nghiên cứu July holdout độc lập)
│   ├── audit_isolation_forest.py (audit study train/validation/test MySQL)
│   ├── benchmark_api.py (đo latency HTTP/SQL dữ liệu thật)
│   ├── benchmark_bgl.py (đo import và kiểm tra provenance)
│   ├── benchmark_investigation_v3.py (benchmark fixture cho thiết kế V3)
│   ├── download_research.py (tải paper/dataset công khai theo catalog)
│   ├── inspect_research_archives.py (kiểm tra archive an toàn)
│   ├── qa_accessibility.py (quét axe tự động)
│   ├── qa_dataset_crud.py (browser QA CRUD/RBAC/form/upload)
│   ├── qa_evidence_drawer.py (browser regression drawer Demo)
│   ├── qa_investigation_v2.py (browser regression timeline Demo)
│   ├── qa_platform.py (browser QA auth/Explorer/alerts thật)
│   ├── qa_university_e2e_browser.py (browser E2E BGL đã nhập)
│   ├── verify_detectors.py (kiểm tra detector với held-out labels)
│   ├── verify_import_restart.py (crash/checkpoint/resume import)
│   ├── verify_mysql.py (schema riêng, migrate và DB tests)
│   ├── verify_university_e2e.py (toàn chuỗi BGL và restart QA)
│   ├── verify_university_filters.py (đối chiếu API filters với SQL)
│   └── verify_validated_if_bgl.py (proof BGL thật → frozen IF → evidence)
│
├── tests/ (19 file; mỗi file chứa nhiều test cases)
│   ├── test_bgl_parser.py (định dạng BGL và raw/timestamp/provenance)
│   ├── test_database_unit.py (unit test logic database)
│   ├── test_dataset_crud_mysql.py (CRUD/RBAC/rollback MySQL thật)
│   ├── test_dataset_privileges.py (giới hạn cấp quyền DB)
│   ├── test_detector_calibration.py (split và chọn threshold)
│   ├── test_evidence.py (hợp đồng bằng chứng và dữ liệu an toàn)
│   ├── test_forms.py (WTForms và signed CSRF)
│   ├── test_forms_mysql.py (form/API/RBAC với MySQL thật)
│   ├── test_if_holdout.py (gates và dữ liệu holdout)
│   ├── test_investigation_v2.py (timeline, filters và aggregation)
│   ├── test_isolation_study.py (IF study/artifact guards)
│   ├── test_mysql_integration.py (schema/FK/transaction/import thật)
│   ├── test_platform_mysql.py (auth/APIs/detector/alerts/email mocks)
│   ├── test_upload_staging.py (format, checksum, path và private ACL)
│   ├── test_uploads_mysql.py (upload/worker/retry/provenance MySQL)
│   ├── test_validated_if_mysql.py (frozen IF và actual membership)
│   ├── test_window_deployment_mysql.py (persist frozen study outputs)
│   ├── test_window_features.py (feature và train-only reference)
│   └── test_workspace.py (workspace Demo)
│
├── migrations/ (8 file; cập nhật schema MySQL)
│   ├── README (ghi chú migrations)
│   ├── alembic.ini (cấu hình Alembic)
│   ├── env.py (kết nối metadata và DB cho migration)
│   ├── script.py.mako (template migration mới)
│   └── versions/ (4 phiên bản schema)
│       ├── 0001_database_foundation.py (schema nền tảng log/detector)
│       ├── 0002_security_jobs_incidents.py (auth/jobs/predictions/incidents)
│       ├── 0003_job_identity.py (idempotency của analysis jobs)
│       └── 0004_alert_decisions.py (lưu quyết định cooldown/dedup)
│
├── docs/ (162 file; tài liệu và bằng chứng kiểm thử)
│   ├── architecture/ (4 file; kiến trúc hệ thống)
│   ├── benchmarks/ (6 file; workload và số đo benchmark)
│   ├── course/ (3 file; đối chiếu yêu cầu môn học)
│   ├── database/ (33 file; ERD, API, MySQL, ingestion và runbook)
│   ├── development/ (6 file; Git baseline, cây code, hướng dẫn dùng)
│   ├── ml/ (25 file; IF, feature, validation và kết quả)
│   ├── releases/ (29 file; checklist và báo cáo QA/release)
│   ├── research/ (10 file; paper, dataset và baseline đối chiếu)
│   ├── ui/ (37 file; thiết kế, ảnh và kiểm tra giao diện)
│   └── (9 file Markdown trực tiếp; workspace/UI/Evidence specifications)
│
├── data/ (1 file hỗ trợ thuộc danh sách dự án; log lớn bị Git bỏ qua)
│   └── raw/ (nơi lưu archive dataset nguồn)
├── config.py (cấu hình Flask/database từ môi trường)
├── requirements.txt (thư viện Python runtime)
├── .env.example (mẫu biến môi trường, không phải mật khẩu thật)
├── .gitignore (loại runtime/venv/dataset/cache khỏi Git)
└── README.md (giới thiệu, setup, trạng thái và tài liệu)
```

## Thư mục vận hành ngoài con số trên

```text
.local/ (Git bỏ qua; dữ liệu vận hành riêng trên máy)
├── run-logsense.py (launcher web, worker và tạo user cho BGL100K đã có)
├── mysql-foundation/ (MySQL phát triển cổng 13306)
├── university-e2e-mysql/ (MySQL QA cổng 13307, đang dùng cho web)
├── uploads/ (file gốc upload và manifest/checksum)
├── backups/gate1-20261104/ (backup Gate1 đã gom lại)
└── ... (private contexts, model/cache và log QA)
.venv/ (Python và các thư viện đã cài)
.git/ (lịch sử và metadata Git)
__pycache__/ (bytecode Python tự tạo)
```

Không xóa `.local` để dọn code: nó chứa database, upload, model và backup. Git ignore không có nghĩa là không quan trọng.

## Luồng chạy dễ hiểu

```text
Trình duyệt → templates/static → api → services → models/domain + MySQL
                 ↑                                   ↓
                 └────────── HTML/JSON trả về ────────┘

Upload → job queued → ingestion_worker → parser BGL → MySQL
Analysis queued → worker → features → rule/IF → anomalies → Timeline/Evidence
```

Nên đọc theo thứ tự: README → app/__init__.py → templates/static → api → services → models/domain/migrations → tests.

Cách mở web và sử dụng: [USER_GUIDE_VI.md](USER_GUIDE_VI.md).
