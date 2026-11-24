# Hệ thống code H-logsen (LogSense AI)

Kiểm kê ngày 2026-11-24, nhánh `feature/mysql-database-foundation`, sau đợt sửa audit 1–5.
Thay cho bản kiểm kê ngày 2026-11-05 (272 file, trước khi sắp xếp lại thư mục).

## Tổng quan

H-logsen là một **Flask modular monolith**: một ứng dụng Python phục vụ cả giao diện (Jinja + JS thuần,
không React/Vue) lẫn REST API. Có hai cách chạy:

- **Workbench desktop** (`h-logsen`): cửa sổ pywebview (WebKitGTK trên Linux, WKWebView trên macOS,
  WebView2 trên Windows) mở ứng dụng Flask trên loopback, có bearer token. Gồm explorer dự án, trình
  soạn code, terminal, chạy và so sánh huấn luyện, xem trước dữ liệu.
- **Investigation trên MySQL**: điều tra log BGL đã nhập vào MySQL 8 (timeline, evidence, cảnh báo,
  incident). Không có MySQL thì giao diện dùng dữ liệu minh họa (`source=demo`).

Việc nặng (nhập log, chạy detector, gửi email) chạy trong **hai worker** ngoài request HTTP.

| Lớp | Thư mục | Số file | Số dòng (xấp xỉ) |
|---|---|---:|---:|
| Ứng dụng (backend) | `app/*.py`, `app/api`, `app/services`, `app/parsers` | 47 | 7 800 |
| Workbench desktop | `app/workbench`, `app/workbench/platforms` | 19 | 3 150 |
| Giao diện | `app/templates`, `app/static` (không tính `vendor/`) | 50 | 9 000 |
| Bản dịch | `app/locales` (14 ngôn ngữ + `workspace.json`) | 15 | 16 000 |
| Schema DB | `migrations` | 9 | 1 130 |
| Lệnh vận hành, QA, ML, đóng gói | `scripts` | 38 | 7 750 |
| Kiểm thử | `tests` | 27 | 6 000 |
| Đóng gói người dùng | `packaging` | 7 | 170 |
| Nghiên cứu / môn học | `academic` | 92 | 12 500 |
| Tài liệu | `docs` | 167 | 19 500 |

Không tính: `.git`, venv, `.local/` (runtime, backup, bản build), `sandbox/` (thư mục thí nghiệm, Git
bỏ qua), các archive dataset lớn trong `data/raw/` (Git bỏ qua), `app/static/vendor/` (thư viện bên
thứ ba: highlight.js, lucide, moment, xterm, xterm-fit).

## Luồng chính

```text
Trình duyệt / cửa sổ desktop
  │  HTML (Jinja, tr() dịch)       JSON (/api/v1/…, /api/local/v1/…)
  ▼
app/__init__.py ── security.py (session, RBAC, CSRF, CSP nonce, error handler)
  ├── app/api/*            REST cho Investigation, logs, upload, job, cảnh báo
  ├── web_datasets.py      trang quản lý dataset (server-rendered)
  └── workbench/api.py     API loopback của desktop (file, terminal, run, preview)
        │
        ▼
app/services/*  (nghiệp vụ, không phụ thuộc HTTP)  ──► app/models.py, app/domain.py ──► MySQL 8
        ▲                                                         ▲
scripts/run/worker.py, ingestion_worker.py ── supervision.py ─────┘ (hàng đợi processing_jobs,
                                                                     outbox email)
```

## Cây code có chú thích

### Thư mục gốc

```text
.
├── README.md                 (giới thiệu, cài đặt, bản đồ dự án)
├── THIRD_PARTY_NOTICES.md    (giấy phép thư viện bên thứ ba)
├── pyproject.toml            (nguồn duy nhất cho dependencies; extras: desktop, qa, ml, course)
├── requirements.txt          (chỉ cài dự án: -e .)
├── config.py                 (cấu hình Flask mặc định)
├── .env.example              (mẫu biến môi trường: DATABASE_URL, FLASK_SECRET_KEY, SMTP…)
├── .gitattributes / .gitignore
├── .github/workflows/workbench-ci.yml
│                             (CI: đóng gói, test academic, test MySQL thật, cài sạch trên
│                              Windows/macOS/Linux, phát hành)
└── data/raw/                 (dataset gốc; Git chỉ giữ LOGHUB_LICENSE.txt)
```

### `app/` — ứng dụng

```text
app/
├── __init__.py          (create_app: cấu hình, đăng ký blueprint, route trang chính)
├── access.py            (chính sách nguồn demo công khai; dữ liệu riêng không kết nối mặc định)
├── database.py          (nối MySQL tùy chọn; timeout kết nối/đọc/ghi; không tự tạo DDL)
├── demo.py              (fixture minh họa, không phải kết quả detector)
├── domain.py            (bảng user, quyền dataset, đánh giá, luật/quyết định cảnh báo, incident,
│                         outbox email)
├── extensions.py        (SQLAlchemy, Migrate, Mail, Moment dùng chung)
├── forms.py             (Flask-WTF cho dataset và upload)
├── i18n.py              (catalog ngôn ngữ, tr()/translate(), đổi ngôn ngữ chỉ từ cùng origin)
├── models.py            (bảng nguồn, artifact, raw log, event, unit, detector, run, anomaly,
│                         coverage, nhãn, processing_jobs; FK ghép theo dataset)
├── paths.py             (vị trí dữ liệu runtime; LOGSENSE_LOCAL_DIR)
├── permissions.py       (ghi file/thư mục chỉ chủ sở hữu đọc được, kiểm tra lại sau khi tạo)
├── presentation.py      (helper Jinja dùng chung cho trang và API)
├── repositories.py      (truy vấn đọc có giới hạn theo dataset)
├── security.py          (đăng nhập, session, RBAC, quyền dataset, header bảo mật, CSP nonce,
│                         trang/JSON lỗi đã dịch)
├── web_datasets.py      (trang quản lý dataset server-rendered)
│
├── api/                 REST /api/v1
│   ├── alerts.py        (incident, luật cảnh báo, lịch sử audit chỉ ghi thêm)
│   ├── anomalies.py     (Investigation: timeline, danh sách, evidence; demo và MySQL)
│   ├── database.py      (API kết quả MySQL riêng, phải bật rõ)
│   ├── datasets.py      (CRUD metadata dataset có RBAC)
│   ├── forms.py         (form multipart cho workspace)
│   ├── jobs.py          (gửi job phân tích, trạng thái, retry, model card)
│   ├── logs.py          (lọc, phân trang, biểu đồ volume, raw, CSV log đã parse)
│   ├── mysql_export.py  (xuất CSV anomaly theo đúng phạm vi lọc)
│   └── uploads.py       (nhận upload, kiểm tra và đưa vào hàng đợi; không nhập trong request)
│
├── parsers/             parser streaming, có version, không phụ thuộc Flask
│   ├── bgl.py           (Loghub BGL bgl-1.1.0: epoch là chuẩn, kiểm epoch khớp ngày in)
│   └── hdfs.py          (Loghub HDFS_v1: block id, đồng hồ nguồn không có múi giờ)
│
├── services/            nghiệp vụ, không phụ thuộc HTTP
│   ├── alerts.py               (quyết định cảnh báo idempotent; outbox SMTP claim → gửi → ghi)
│   ├── bgl_ingestion.py        (nhập ZIP BGL có giới hạn; dữ liệu + checkpoint commit nguyên tử)
│   ├── csv_safety.py           (chặn công thức trong ô CSV)
│   ├── database_evidence.py    (evidence từ dòng đã lưu; giới hạn và che dữ liệu nhạy cảm)
│   ├── dataset_management.py   (vòng đời dataset; cấp quyền rõ ràng; xóa thận trọng)
│   ├── detection.py            (detector baseline theo event; không dùng nhãn làm đặc trưng)
│   ├── detector_calibration.py (lấy mẫu tất định, hiệu chỉnh ngưỡng chỉ trên tập validation)
│   ├── evidence.py             (hợp đồng evidence trên dữ liệu demo)
│   ├── investigation.py        (hợp đồng truy vấn UTC, tổng hợp phía server)
│   ├── log_queries.py          (một hợp đồng lọc/snapshot cho trang log, volume và CSV)
│   ├── mysql_evidence.py       (Evidence Drawer trên MySQL; bỏ qua mẫu raw quá 256 KiB)
│   ├── mysql_investigation.py  (Investigation V2 trên MySQL; cache state theo request)
│   ├── redaction.py            (che dữ liệu khi hiển thị demo)
│   ├── uploads.py              (staging upload bất biến; từ chối tên file có ký tự điều khiển)
│   ├── validated_if.py         (suy luận từ nghiên cứu Isolation Forest đã chốt)
│   ├── window_deployment.py    (lưu dự đoán của model IF đã chốt)
│   ├── window_detection.py     (baseline theo cửa sổ host; chia theo thời gian; dọn cache mồ côi)
│   └── window_features.py      (đặc trưng ngữ cảnh cửa sổ, không dùng nhãn)
│
├── workbench/           desktop cục bộ, tách khỏi API phân tích công khai
│   ├── __main__.py      (lệnh h-logsen; không có màn hình thì chuyển sang trình duyệt;
│   │                     lỗi nghiêm trọng ghi ~/.h-logsen/desktop-error.log và hiện hộp thoại)
│   ├── api.py           (API loopback /api/local/v1, bảo vệ bằng token)
│   ├── attached.py      (quan sát tiến trình đang chạy trong dự án, chỉ đọc)
│   ├── code_tools.py    (công cụ editor theo dự án: tìm, format, kiểm tra)
│   ├── desktop.py       (cửa sổ native, chọn thư mục; DesktopUnavailable)
│   ├── external.py      (xem trước định dạng ngoài: HDFS, OpenStack…; giới hạn 64 KiB/bản ghi)
│   ├── files.py         (truy cập thư mục dự án đã duyệt; chặn thư mục hệ thống/home/ẩn)
│   ├── jobs.py          (interpreter, telemetry máy, các lượt huấn luyện độc lập)
│   ├── pdf_preview.py   (render trang PDF, không chạy script trong PDF)
│   ├── run_profile.py   (provenance có version cho một lượt chạy Python)
│   ├── runner.py        (supervisor nền cho tiến trình do workbench khởi chạy)
│   ├── tabular.py       (profile dữ liệu bảng: CSV, Parquet…)
│   ├── terminal.py      (phiên terminal độc lập, có giới hạn)
│   └── platforms/       code riêng từng hệ điều hành, nạp lười
│       ├── __init__.py  (chọn backend theo OS)
│       ├── linux.py     (WebKitGTK, kính khi có compositing, launcher menu, hộp thoại lỗi)
│       ├── macos.py     (WKWebView, vibrancy, hộp thoại lỗi qua osascript)
│       ├── posix.py     (terminal PTY dùng chung; tìm shell trong $SHELL và các thư mục chuẩn)
│       └── windows.py   (ConPTY, kính DWM, taskbar, shortcut)
│
├── templates/           Jinja
│   ├── base.html, error_page.html, query_error.html
│   ├── dashboard.html          (Investigation / workspace phân tích)
│   ├── logs.html               (trang log)
│   ├── project_workspace.html  (khung workbench: nav icon, explorer, editor, terminal, run)
│   ├── dataset_pages/          (index.html, edit.html: quản lý dataset)
│   ├── mail/alert.html         (email cảnh báo)
│   └── partials/               (workspace, explorer, navigation, chọn ngôn ngữ, assets…)
│
├── static/
│   ├── css/             (console.css, language.css)
│   ├── js/              (dashboard, datasets, evidence, i18n, incidents, logs, uploads)
│   ├── workspace/       (CSS/JS của workbench: appearance, controls, dock, explorer,
│   │                     code-editor + worker tô màu, terminal, live-terminal, machine-chart,
│   │                     run-detail, run-compare, local-api, local-project, project…)
│   ├── vendor/          (thư viện bên thứ ba, không sửa tay)
│   └── h-logsen.ico, h-logsen.png  (icon chữ H)
│
└── locales/             vi, de, fr, es, it, pt, nl, ru, ja, ko, zh-Hans, th, id, tr
                         (khóa là câu tiếng Anh) + workspace.json (nhãn workbench, ưu tiên hơn)
```

### `migrations/` — schema MySQL (Alembic)

```text
migrations/
├── env.py, alembic.ini, script.py.mako
└── versions/
    ├── 0001_database_foundation.py       (nền tảng MySQL 8, DDL cố định)
    ├── 0002_security_jobs_incidents.py   (xác thực, dự đoán cửa sổ, job, incident)
    ├── 0003_job_identity.py              (gửi job idempotent)
    ├── 0004_alert_decisions.py           (lưu quyết định cooldown cảnh báo)
    └── 0005_job_and_outbox_indexes.py    (cột sinh upload_id, index cho worker/outbox/phân trang
                                           theo run, CHECK cho outbox.state và outcome)
```

### `scripts/` — vận hành, QA, ML, phát hành

Chạy từ thư mục gốc: `python -m scripts.<nhóm>.<lệnh>`.

```text
scripts/
├── run/        chạy và vận hành
│   ├── supervision.py      (vòng lặp chung của worker: backoff khi mất DB, thu hồi job kẹt)
│   ├── worker.py           (worker phân tích: chạy detector, gửi outbox)
│   ├── ingestion_worker.py (worker nhập file BGL đã upload)
│   ├── database.py         (CLI vận hành DB)
│   ├── mysql_runtime.py    (vòng đời MySQL ZIP tự quản: init, start, backup, restore)
│   ├── desktop.py          (companion Tkinter)
│   ├── logsense_client.py  (client Python cho JSON API)
│   └── workbench.py, workbench_run.py (lối vào cũ, giữ tương thích)
├── qa/         kiểm tra sản phẩm
│   ├── qa_workbench_browser.py, qa_workbench_desktop.py   (E2E workbench trình duyệt / native)
│   ├── qa_investigation_v2.py, qa_evidence_drawer.py      (Investigation và Evidence)
│   ├── qa_dataset_crud.py, qa_platform.py, qa_accessibility.py, qa_university_e2e_browser.py
│   └── verify_mysql.py, verify_detectors.py, verify_import_restart.py,
│       verify_university_e2e.py, verify_university_filters.py, verify_validated_if_bgl.py
├── ml/         dựng và audit model sản phẩm nạp
│   ├── audit_isolation_forest.py, audit_if_holdout.py    (nghiên cứu IF, holdout BGL về sau)
│   └── bgl_window_baseline.py                            (baseline cửa sổ BGL; cần extra "ml")
├── bench/      benchmark_api.py, benchmark_bgl.py, benchmark_investigation_v3.py
└── release/    package_workbench.py (dựng ZIP nguồn + từng OS), qa_portfolio_install.py (cài sạch)
```

### `tests/` — kiểm thử

27 file. Không cần MySQL: parser, form, i18n, evidence, workbench, lưu trữ riêng tư, staging upload,
desktop Linux, worker/outbox, đặc trưng cửa sổ, hiệu chỉnh detector, nghiên cứu IF. Các file
`*_mysql.py` và `test_mysql_integration.py` chỉ chạy khi `LOGSENSE_RUN_MYSQL_TESTS=1` trên schema test
có token (do `scripts.qa.verify_mysql` tạo).

### `packaging/` — gói cho người dùng

```text
packaging/
├── posix/    Install-H-logsen.sh, Open-H-logsen.sh (có quyền thực thi), CAI_DAT_MAC_LINUX.txt
└── windows/  Install-H-logsen.cmd, Open-H-logsen.cmd, CAI_DAT_WINDOWS.txt
```

### `academic/` — nghiên cứu và môn học (không đóng gói)

```text
academic/
├── course/       bài tập, báo cáo, slide bảo vệ, lab MySQL và mạng
├── experiments/  thí nghiệm HDFS_v1 theo block (không dùng trong sản phẩm)
├── tools/        tải và kiểm tra bài báo / dataset công khai
├── literature/   tài liệu tham khảo theo chủ đề
├── notes/        ghi chú nghiên cứu, danh mục dataset, đo đạc
└── tests/        test cho experiments
```

### `docs/` — tài liệu

| Thư mục | Nội dung |
|---|---|
| `architecture/` | Đề xuất Investigation V3, dữ liệu, timeline API |
| `database/` | Pipeline BGL, schema, kiểm chứng MySQL |
| `ml/` | Nghiên cứu detector, Isolation Forest, kết quả |
| `benchmarks/` | Số đo hiệu năng |
| `ui/` | Thiết kế và ảnh chụp giao diện |
| `releases/` | Ghi chú phát hành và QA từng bản |
| `development/` | Cấu trúc code (file này), hướng dẫn sử dụng, báo cáo Git |
| `history/` | Tài liệu cũ được giữ lại |
