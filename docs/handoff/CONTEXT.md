# Bàn giao ngữ cảnh: tiếp tục H-logsen trên máy khác

File này tóm tắt mọi thứ đã làm và đã quyết định, để tiếp tục làm việc trên máy Mac (hoặc máy bất kỳ)
với một trợ lý lập trình mới. Toàn bộ lời nhắn qua lại nằm trong [CHAT_TRANSCRIPT.md](CHAT_TRANSCRIPT.md)
(đã che mật khẩu, token, email).

**Cách dùng trên máy mới:** làm theo [START_PROMPT.md](START_PROMPT.md): cài công cụ, clone repo, rồi dán prompt
ở đó vào đoạn chat mới.

---

## 1. Dự án là gì

**H-logsen** là ứng dụng **web Flask** để điều tra log hệ thống và phát hiện bất thường (dữ liệu thật Loghub BGL),
kèm một "project workbench" cục bộ (cây thư mục, trình soạn code, terminal). Đây là **đồ án môn Lập trình Python
nâng cao** (mẫu báo cáo của giảng viên: Flask, Jinja2, Flask-WTF, Flask-SQLAlchemy, Flask-Mail, lập trình mạng).

**Định vị khi thuyết trình:** *"Một Datadog thu nhỏ, tự cài, có ML phát hiện bất thường, cho đội vận hành hệ
thống."* Bản mã nguồn mở tương đương gần nhất: Grafana Loki. Người dùng chính: SRE/DevOps, kỹ sư trực ca;
phụ: data engineer lo đường ống nạp log.

**Từ commit `0b53c87`: chỉ còn bản web.** Đã bỏ cửa sổ desktop (pywebview), gói cài cho Windows/macOS/Linux,
app Tkinter và các job CI đóng gói, phát hành. `python -m app.workbench` chạy server ở `127.0.0.1` rồi mở trình
duyệt; chạy lại khi server đang chạy thì chỉ mở lại trình duyệt vào đúng server đó.

## 2. Chạy trên Mac

```bash
git clone git@github.com:HieuHoai2704/H-LogSense.git && cd H-LogSense
git checkout feature/mysql-database-foundation          # main đang trùng nhánh này
python3.12 -m venv .venv && . .venv/bin/activate        # Python 3.10–3.14
python -m pip install -e ".[dev,qa]"
# Cần Docker Desktop đang chạy:
python -m scripts.run.demo        # bật MySQL 8.4 trong Docker (127.0.0.1:3308), migrate, tạo tài khoản demo, nạp BGL, mở trình duyệt
python -m scripts.run.demo accounts   # in lại tài khoản demo
```

- Dữ liệu BGL thật **không có trong git**: cần `data/raw/BGL.zip`. Chép từ máy cũ, hoặc tải trên Zenodo
  (record 8196385, file `BGL.zip`). Không có file đó thì bộ dữ liệu demo rỗng.
- Tài khoản demo được **tạo mới với mật khẩu ngẫu nhiên** trên mỗi máy, lưu ở `.local/demo/accounts.txt`
  (chỉ chủ máy đọc được, không có trong git). Có 2 tài khoản: `admin` (cổng Quản trị) và `staff` (cổng Nhân viên).
- Email (chào mừng, duyệt đăng ký, đặt lại mật khẩu) ghi thành tệp `.eml` trong `~/.h-logsen/outbox`, trừ khi đặt
  `SMTP_ENABLED=1` cùng các biến `SMTP_*` trong `.env.example`.

## 3. Quy ước làm việc (bắt buộc giữ)

- **Không có dấu AI trong repo:** không thêm dòng `Co-Authored-By: Claude`, không "Generated with…", không nhắc AI
  trong commit, PR hay file. (Riêng thư mục `docs/handoff/` này do chủ dự án yêu cầu; xóa trước khi chia sẻ repo.)
- **Tác giả commit:** `git -c user.name="Truong Hieu Hoai" -c user.email="truon@example.com" commit ...`
- **Push:** nhánh `feature/mysql-database-foundation` và `HEAD:main` (main luôn trùng feature). Chỉ push khi chủ
  dự án đồng ý.
- **Repo `H-LogSense` là riêng tư.** Repo công khai `H-LogSense-PL` chỉ có README và ảnh giới thiệu, **không có code**.
- **Trao đổi bằng tiếng Việt.** Chủ dự án thích được hỏi trước khi làm việc lớn, và muốn có "vòng lặp kiểm tra"
  (sửa, kiểm tra đến khi xanh rồi mới sang bước sau).
- Đồ án: giảng viên **chủ yếu xem demo trực tiếp**, không tải về chạy thử. Nên demo trên trình duyệt.
- Không nhập mật khẩu hay token thật thay chủ dự án.

## 4. Vòng kiểm tra trước mỗi commit

```bash
ruff check . && ruff format --check .
mypy --platform linux && mypy --platform win32
python -B -m pytest -q tests                     # ~250 test, phần MySQL tự bỏ qua
# MySQL thật (140 test) trong một container tạm:
docker run -d --name hlogsen-mysql-test -p 127.0.0.1:3307:3306 -e MYSQL_ROOT_PASSWORD=<root> \
  -e MYSQL_DATABASE=logsense_dev -e MYSQL_USER=logsense -e MYSQL_PASSWORD=<app> mysql:8.4 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_as_cs
export MYSQL_ADMIN_URL=mysql+pymysql://root:<root>@127.0.0.1:3307/mysql
export DATABASE_URL=mysql+pymysql://logsense:<app>@127.0.0.1:3307/logsense_dev
export MYSQL_GRANT_HOST=%
PYTHONPATH=tests python -B -m scripts.qa.verify_mysql
docker rm -f hlogsen-mysql-test
# Giao diện (24 test, Playwright). Trên Mac có Chrome: LOGSENSE_BROWSER_CHANNEL=chrome
python -m scripts.qa.qa_workbench_browser
```

Lần chạy gần nhất (commit `0b53c87`): ruff, mypy, 253 test thường, 140 test MySQL, 24 test giao diện đều đạt.

## 5. Kiến trúc chính

- `app/__init__.py`: app factory; `config.py`: các profile cấu hình. MySQL bắt buộc dùng `mysql+pymysql`.
- **Tài khoản** `app/web_accounts.py`, `app/forms.py`:
  - Mọi trang đều phải đăng nhập (chặn mặc định). Một thẻ đăng nhập có 3 chế độ: Nhân viên, Đăng ký, Quản trị.
    Chuyển chế độ có hiệu ứng, không tải lại trang.
  - Hai loại tài khoản: `staff` (dùng toàn bộ app) và `admin` (thêm quản lý người dùng).
  - Đăng ký phải chờ admin duyệt (migration 0009); duyệt hoặc từ chối đều gửi email.
  - Admin đặt mật khẩu dài tùy ý; tự đăng ký và đặt lại mật khẩu cần tối thiểu 8 ký tự.
  - Quản lý người dùng có CRUD, tìm kiếm, lọc vai trò và trạng thái, phân trang 20 dòng, cấp quyền bộ dữ liệu.
  - Quên mật khẩu dùng link ký số, mỗi link dùng một lần (`auth_version`), hết hạn sau 1 giờ.
- **Log Explorer** (giống Datadog) `app/api/logs.py`, `app/services/log_queries.py`, `log_patterns.py`,
  `static/js/log-explorer.js`:
  - Cú pháp tìm kiếm `host:R02* level:ERROR -service:KERNEL "cụm từ"`.
  - Facet có số đếm; biểu đồ khối lượng tách màu theo mức log; tab Patterns.
  - Insights: lỗi tăng đột biến (trung vị + 3×MAD, tối thiểu 10), mẫu log mới, bất thường từ detector.
  - Log xung quanh cùng máy chủ; bộ lọc đã lưu (migration 0008); chế độ Trực tiếp làm mới mỗi 15 giây.
- **Điều tra bất thường** `app/services/investigation.py`, `mysql_investigation.py`: timeline theo detector,
  ngăn kéo bằng chứng.
- **Lập trình mạng:** danh mục Loghub đọc từ Zenodo REST API bằng `urllib` (`app/services/dataset_catalog.py`,
  biến tùy chọn `ZENODO_TOKEN`).
- **ML:** detector luật và Isolation Forest theo cửa sổ host 5 phút, có chia train/validation/test theo thời gian.
- **Migration:** `migrations/versions/0001`–`0009` (0006 email, 0007 hai loại tài khoản, 0008 saved views,
  0009 pending).
- **i18n:** 15 ngôn ngữ trong `app/locales/*.json`, file dùng CRLF. Chuỗi mới phải thêm vào đủ 14 catalog;
  `tests/test_i18n.py` kiểm tra placeholder.

## 6. Việc còn lại (theo thứ tự chủ dự án đã chốt)

**Giai đoạn 1 (bắt buộc, chưa bắt đầu):**
1. Trang **Analysis**: bỏ cây thư mục bên trái (`partials/analysis_explorer.html`, dùng trong `logs.html` và
   `dashboard.html`); thay bằng **menu chức năng**: Tổng quan, Log Explorer, Điều tra bất thường, Cảnh báo,
   Chất lượng dữ liệu, Pipeline & job, Lịch chạy, Bộ dữ liệu, Danh mục Loghub. Chuyển ô "Phân tích tệp dữ liệu"
   (`partials/workbench_external.html` và `static/workspace/external.js`, đang cần cây thư mục) sang trang Project.
2. **Chất lượng dữ liệu** (giống Great Expectations): điểm chất lượng; các kiểm tra (dòng sai định dạng, trùng lặp,
   thiếu trường, khoảng trống thời gian, số dòng tụt so với kỳ trước); lưới độ phủ theo giờ. Dữ liệu lấy từ bộ đếm
   lúc nạp và bảng độ phủ.
3. **Pipeline & job** (giống Airflow và Dagster): lưới trạng thái job (hàng là loại job, cột là lần chạy, bảng
   `processing_jobs`); sơ đồ luồng log thô → nạp → kiểm tra → ML → cảnh báo tô màu theo trạng thái; nút chạy lại.

**Giai đoạn 2:** trang Tổng quan (số liệu chính và mục "Cần chú ý"); tách Cảnh báo thành trang riêng, thêm cảnh báo
theo truy vấn. **Giai đoạn 3:** lập lịch chạy nạp và phát hiện theo giờ. **Không làm:** dashboard kéo thả,
ngôn ngữ truy vấn riêng, streaming quy mô lớn.

**Sau khi làm xong tính năng, mới viết báo cáo** `.docx` và `.pdf` đúng mẫu:
- Định dạng: A4, Times New Roman 13, giãn dòng 1,5, lề 2/2/3/2 cm, chương 1–5 dài 5–10 trang.
- Nội dung: sơ đồ use case, ERD, wireframe, ảnh chụp màn hình thật, bảng kiểm thử (dòng 1 là "Đăng ký tài khoản
  mới"), tài liệu tham khảo kiểu IEEE.
- Phụ lục A: tài khoản demo và cách chạy. Phụ lục B: **file dữ liệu mẫu nhỏ, hiện chưa có trong repo**.
- **Cần chủ dự án cung cấp:** đề tài số, nhóm số, thành viên (tối đa 3: MSSV, họ tên, nhiệm vụ, % đóng góp).
- Lưu ý: báo cáo `v9.docx` của em chủ dự án cũng viết về H-LogSense. Nếu nộp cùng lớp thì dễ bị coi là trùng
  bài; cần làm rõ trước khi nộp.
- Nộp mã nguồn: repo đang riêng tư, nên mời giảng viên vào repo hoặc nộp file nén (không kèm `.venv`).

**Tùy chọn:** đưa lên mạng (PythonAnywhere có Flask và MySQL miễn phí). Khi đưa lên mạng phải **tắt phần Project/Code**
(terminal, mở thư mục máy), vì phần đó cho chạy lệnh trên máy chủ.

## 7. Bài học đã gặp (đừng lặp lại)

- `@view-transition` (hiệu ứng mờ khi chuyển trang) làm WebKitGTK 2.52 sập khi gửi form. Đã gỡ, và có test
  cấm dùng lại. Cửa sổ desktop giờ đã bỏ, nhưng test vẫn giữ.
- Kết quả `dict(Result.tuples())` của SQLAlchemy làm hỏng điều tra trên MySQL; phải dùng `.tuples().all()`.
- Ràng buộc CHECK trong migration phải đặt tên bằng `op.f("ck_users_role")`, vì quy ước đặt tên sẽ nhân đôi tiền tố.
- Lỗi chỉ hiện trên MySQL thật: luôn chạy `verify_mysql` trước khi push.
- Catalog dịch và nhiều file trong `app/static/workspace` dùng CRLF; khi sửa giữ nguyên kiểu xuống dòng.
