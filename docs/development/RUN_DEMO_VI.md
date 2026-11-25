# Chạy H-logsen từ A đến Z

Hướng dẫn từng bước để cài, chạy bản demo trên trình duyệt, đăng nhập, thử các tính năng, tắt máy chủ và
chạy vòng kiểm tra. Các lệnh viết cho macOS và Linux; trên Windows thay `source .venv/bin/activate` bằng
`.venv\Scripts\activate`.

## Cần có

| | |
| --- | --- |
| Python | 3.10 – 3.14 (khuyên dùng 3.12) |
| Docker | Docker Desktop đang chạy (bản demo bật MySQL 8.4 trong container) |
| Dữ liệu | `data/raw/BGL.zip` (Loghub BGL, không có trong git) |
| Trình duyệt | Chrome, Edge, Firefox hoặc Safari |

## 1. Cài đặt lần đầu

Lấy mã nguồn:

```bash
git clone https://github.com/HieuHoai2704/H-LogSense.git
cd H-LogSense
```

Tạo môi trường Python. Nếu máy không có `python3.12` (ví dụ chỉ có 3.15), dùng `uv` để cài bản 3.12 riêng
cho dự án:

```bash
python3.12 -m venv .venv
# hoặc: uv python install 3.12 && "$(uv python find 3.12)" -m venv .venv
```

Cài dự án cùng công cụ kiểm tra:

```bash
.venv/bin/python -m pip install -e ".[dev,qa]"
```

Tải dữ liệu BGL (khoảng 57 MB) từ Zenodo, bản ghi 8196385, rồi kiểm tra mã MD5
`4452953c470f2d95fcb32d5f6e733f7a`:

```bash
curl -L -o data/raw/BGL.zip https://zenodo.org/api/records/8196385/files/BGL.zip/content
```

## 2. Mỗi lần chạy demo

Vào thư mục dự án, bật Docker Desktop và kích hoạt môi trường Python:

```bash
cd H-LogSense
open -a Docker            # macOS; Linux: sudo systemctl start docker
source .venv/bin/activate
```

Trên macOS, nếu Terminal báo không tìm thấy lệnh `docker`, thêm nó vào PATH:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

Chạy bản demo (giữ cửa sổ Terminal này mở trong suốt buổi demo):

```bash
python -m scripts.run.demo
```

Lần đầu, lệnh này mất khoảng 1–2 phút. Nó bật MySQL 8.4 trong container ở `127.0.0.1:3308`, tạo bảng, tạo
2 tài khoản demo, nạp 60.000 dòng BGL thật, chạy detector luật và Isolation Forest, rồi mở app trên trình
duyệt. Các lần sau chỉ bật container và mở app.

## 3. Tài khoản đăng nhập

Mật khẩu được tạo ngẫu nhiên trên từng máy và chỉ lưu trong `.local/demo/accounts.txt` (chỉ chủ máy đọc
được, không có trong git). In ra bằng:

```bash
python -m scripts.run.demo accounts
```

| Cổng đăng nhập | Tài khoản | Dùng được |
| --- | --- | --- |
| **Đăng nhập nhân viên** | `staff` | Toàn bộ app |
| **Đăng nhập quản trị** | `admin` | Toàn bộ app, thêm trang Quản lý người dùng |

Nếu đổi mật khẩu trong trang Quản lý người dùng thì tệp `accounts.txt` vẫn ghi mật khẩu cũ. Quên mật khẩu
`staff` thì đăng nhập `admin` → Quản lý người dùng → **Sửa** dòng `staff` → nhập mật khẩu mới.

## 4. Chạy worker để job "Chạy lại" chạy xong ngay (tùy chọn)

App web không tự chạy job. Nút **Chạy lại** ở trang Pipeline & job chỉ đưa job vào hàng đợi. Muốn job chạy
ngay, mở thêm một cửa sổ Terminal:

```bash
cd H-LogSense && source .venv/bin/activate
export DATABASE_URL="$(python -c "import json; from app.workbench.local_database import demo_url; print(demo_url(json.load(open('.local/demo/demo.json'))))")"
python -m scripts.run.worker
```

## 5. Những gì nên thử

- **Phân tích** (biểu tượng biểu đồ), menu bên trái:
  - **Trình xem log**: cú pháp `host:R02-M1* level:ERROR -service:KERNEL "machine check"`, facet, Patterns,
    Insights, bộ lọc đã lưu, chế độ Trực tiếp.
  - **Điều tra bất thường**: dòng thời gian theo detector và ngăn kéo bằng chứng.
  - **Cảnh báo**: danh sách cảnh báo và luật cảnh báo.
  - **Chất lượng dữ liệu**: điểm chất lượng, 5 kiểm tra, lưới độ phủ theo giờ.
  - **Pipeline & job**: sơ đồ luồng dữ liệu, lưới job, nút chạy lại.
  - **Bộ dữ liệu** và **Danh mục Loghub** (đọc trực tiếp từ Zenodo API, cần mạng).
- **Dự án** (biểu tượng thư mục): mở một thư mục, bấm tệp `.csv`, `.jsonl` hoặc `.parquet` để dùng
  **Phân tích tệp dữ liệu**.
- **`admin`**: **Quản lý người dùng** (biểu tượng người) để duyệt đăng ký, thêm, sửa, xóa tài khoản.
- **Đăng ký**: ở trang đăng nhập bấm **Đăng ký**; tài khoản mới chờ quản trị viên duyệt. Email được ghi thành
  tệp `.eml` trong `~/.h-logsen/outbox`.

## 6. Tắt khi xong

Nhấn `Ctrl+C` ở cửa sổ đang chạy app, rồi tắt MySQL demo (dữ liệu vẫn được giữ cho lần sau):

```bash
python -m scripts.run.demo stop
```

## 7. Vòng kiểm tra trước khi commit

Lint, kiểu và test thường:

```bash
ruff check . && ruff format --check . && mypy --platform linux && mypy --platform win32
python -B -m unittest discover -s tests
```

Test giao diện (Playwright). Đặt `LOGSENSE_BROWSER_CHANNEL` theo trình duyệt có trên máy: `chrome` hoặc
`msedge`:

```bash
LOGSENSE_BROWSER_CHANNEL=msedge python -m scripts.qa.qa_workbench_browser
```

Test trên MySQL thật, trong một container tạm ở cổng 3307 (mật khẩu tạo ngẫu nhiên cho mỗi lần chạy):

```bash
ROOT=$(openssl rand -hex 16); APPPW=$(openssl rand -hex 16)
docker run -d --name hlogsen-mysql-test -p 127.0.0.1:3307:3306 -e MYSQL_ROOT_PASSWORD=$ROOT \
  -e MYSQL_DATABASE=logsense_dev -e MYSQL_USER=logsense -e MYSQL_PASSWORD=$APPPW mysql:8.4 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_as_cs
# chờ khoảng 20–30 giây cho MySQL khởi động xong
export MYSQL_ADMIN_URL=mysql+pymysql://root:$ROOT@127.0.0.1:3307/mysql
export DATABASE_URL=mysql+pymysql://logsense:$APPPW@127.0.0.1:3307/logsense_dev
export MYSQL_GRANT_HOST=%
PYTHONPATH=tests python -B -m scripts.qa.verify_mysql
docker rm -f hlogsen-mysql-test
```

Kết quả đạt khi `verify_mysql` in `"mysql_integration": "PASS"`.
