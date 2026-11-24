# Prompt khởi động trên máy mới

## Trước khi mở trợ lý (làm một lần trên Mac)

```bash
# 1. Công cụ: Git, GitHub CLI, Python 3.12, Docker Desktop
brew install git gh python@3.12
brew install --cask docker            # rồi mở Docker Desktop một lần

# 2. Đăng nhập GitHub (repo đang riêng tư) và tải code
gh auth login
gh repo clone HieuHoai2704/H-LogSense
cd H-LogSense
git checkout feature/mysql-database-foundation

# 3. Chép data/raw/BGL.zip từ máy cũ vào cùng đường dẫn (không có trong git)

# 4. Mở trợ lý lập trình trong thư mục dự án
claude
```

## Prompt dán vào đoạn chat mới

```text
Tôi đang tiếp tục dự án H-logsen từ một máy khác (Linux) sang máy Mac này. Toàn bộ ngữ cảnh nằm trong repo.

1. Đọc kỹ docs/handoff/CONTEXT.md. Sau đó đọc docs/handoff/CHAT_TRANSCRIPT.md: phần cuối (khoảng 200 tin
   nhắn cuối) quan trọng nhất, cho thấy cách tôi làm việc và các quyết định gần đây. Phần đầu chỉ cần đọc lướt.

2. Giữ đúng mọi quy ước ở mục 3 của CONTEXT.md, và lưu chúng vào bộ nhớ dài hạn của bạn:
   - Không có dấu AI trong repo: không dòng Co-Authored-By, không "Generated with", không nhắc AI trong commit,
     PR hay file (trừ docs/handoff/).
   - Tác giả commit: Truong Hieu Hoai <truon@example.com>, dùng git -c user.name=... -c user.email=..., không sửa
     cấu hình git.
   - Push nhánh feature/mysql-database-foundation và HEAD:main, và chỉ push khi tôi đồng ý.
   - Repo H-LogSense là riêng tư; repo công khai H-LogSense-PL không có code.
   - Trả lời tôi bằng tiếng Việt.

3. Thiết lập môi trường trên Mac theo mục 2 của CONTEXT.md:
   python3.12 -m venv .venv, rồi pip install -e ".[dev,qa]". Kiểm tra Docker Desktop đang chạy và có
   data/raw/BGL.zip. Thiếu gì thì báo tôi, đừng tự tải file lớn hay cài phần mềm khi chưa hỏi.

4. Chạy vòng kiểm tra ở mục 4 để xác nhận mọi thứ vẫn xanh trên Mac: ruff, mypy, test thường, test MySQL thật
   trong Docker, và test giao diện với LOGSENSE_BROWSER_CHANNEL=chrome nếu máy có Google Chrome. Báo kết quả.
   Có gì đỏ thì tìm nguyên nhân và sửa trước.

5. Tóm tắt cho tôi bằng tiếng Việt: hiện trạng dự án, việc còn lại (mục 6 của CONTEXT.md), và đề xuất làm
   Giai đoạn 1 theo thứ tự:
     (1) Menu chức năng thay cây thư mục ở trang Analysis;
     (2) Trang Chất lượng dữ liệu;
     (3) Trang Pipeline & job.
   Chờ tôi đồng ý rồi mới làm. Sau mỗi bước chạy lại vòng kiểm tra đến khi xanh, rồi commit riêng từng bước.
```
