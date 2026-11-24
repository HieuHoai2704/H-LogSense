# University MVP v1.0 — Baseline đã kiểm thử

Ngày đối chiếu 05/11/2026. **TESTED BASELINE**, phạm vi Windows, bản giao nộp cục bộ. Định danh là `LogSense_AI_University_MVP_v1.0_source.zip` với SHA-256 `1986d3836c11c5a674a089d8e6fadf2ee7e5476c5076e88caeb78a301aa49864`. Bản ZIP, `MANIFEST.tsv`, `SHA256.txt` và log gốc nằm tại `.local/university-handoff/`. Git base của bản giao nộp là `b801b773afefb86317470d4262a2704d00f5e02f` cùng phần worktree đã được đóng gói.

| Cổng kiểm tra | Bằng chứng |
|---|---|
| Artifact | SHA-256 khớp checksum và biên bản. CRC ZIP, tên entry duy nhất, đường dẫn an toàn và toàn bộ 309 payload khớp kích thước và SHA-256. Manifest trong và ngoài ZIP trùng byte. |
| Source và cấu hình | Source, tests, README, requirements và migrations khớp bản đóng gói. Phiên bản pin Windows thỏa các specifier trong requirements. Các liên kết nội bộ từ README, checklist và tài liệu môn học được kiểm tra trên ZIP. |
| Schema | Chuỗi revision `0001 → 0002 → 0003 → 0004` liền mạch. Biên bản gốc ghi Alembic check không phát hiện upgrade mới. |
| Nghiệm thu đã lưu | Unit 157 PASS và 113 SKIP có guard. MySQL riêng 125/125 PASS. Browser 7/7 nhóm PASS. Restart giữ 100.000 events, 158.218 predictions và 158 outputs. Các suite có phần giao nhau và được ghi riêng. |

Đợt này đối chiếu file và bằng chứng của lượt chạy từ ZIP trước đó. Khi so với workspace trước các bổ sung tài liệu mới, file trong manifest có khác biệt duy nhất là `docs/releases/BACKLOG.md`. Backlog tiếp tục được cập nhật độc lập sau khi đóng gói. Baseline được giữ bằng checksum của ZIP. [Biên bản nghiệm thu theo checksum](UNIVERSITY_HANDOFF_RESULT_VI.md) · [Checklist bàn giao](UNIVERSITY_HANDOFF_CHECKLIST_VI.md)

ISS dùng phương án dự báo có dữ liệu quỹ đạo thật để bổ sung bài học. Sự chấp nhận của giảng viên còn mở. YouTube cần API key hợp lệ. Workbench GUI cần máy có bản cài và bằng chứng thao tác trực tiếp. [Bổ sung minh chứng học phần](../course/EXTERNAL_REQUIREMENTS_EVIDENCE_VI.md)

