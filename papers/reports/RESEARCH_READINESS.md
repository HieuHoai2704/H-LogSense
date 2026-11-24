# Research readiness cho Graduation Thesis

Trạng thái **chuẩn bị đủ để duyệt protocol**. Mốc kiểm toán khóa luận là **71/100**. Mục tiêu **90–100/100** trong [roadmap](../../docs/releases/GRADUATION_THESIS_ROADMAP_VI.md) còn phụ thuộc thí nghiệm và tái lập độc lập. Đợt này khóa lại baseline University MVP, rà soát literature và chọn thiết kế. Chưa chạy training hoặc baseline mới.

## Kiểm toán thư viện

| Hạng mục | Số |
|---|---:|
| Ứng viên đưa vào registry, không tính toàn bộ hit tìm kiếm | 34 |
| Identity đã xác minh với venue/DOI hoặc proceedings | 34 |
| DOI xác minh được | 31 |
| PDF cục bộ khớp hash và số trang | 23 |
| Full text có review | 25 |
| Chỉ đọc abstract | 6 |
| Chỉ xác minh metadata | 3 |
| Có liên kết code hoặc artifact truy cập được, gồm thư viện và reimplementation | 17 |
| PDF chưa có cục bộ | 11 |

Hai bài S33/S34 đọc qua full text trên web. Ba bản ghi chưa có DOI xác minh là S05, S19 và S21, được định danh bằng trang proceedings. Danh sách PDF chưa có trên máy gồm S15, S16, S18 và S27–S34. Tình trạng từng nguồn nằm trong [audit summary](../metadata/audit_summary.json). Code link chỉ chứng minh truy cập được metadata, chưa có reproduction. 16 link code có license đối chiếu được. PDF S19, S20 có cảnh báo cross-reference mà trình đọc phục hồi được. Số trang và hash vẫn khớp. Bốn PDF trùng byte với thư viện lịch sử dùng hardlink NTFS, giữ các đường dẫn cũ và mới với một bản nội dung. Trong `papers/` không có ID, DOI, tiêu đề chuẩn hóa hoặc PDF hash trùng. [Registry](../metadata/paper_registry.csv) · [Verification log](../metadata/verification_log.csv) · [Deduplication](../metadata/local_deduplication.json)

## Dữ liệu và phần cứng

- Workspace có BGL ZIP 57.489.019 byte cùng HDFS_v1, Thunderbird và OpenStack. BGL có anchor provenance đã đo từ archive thật. HDFS cần bài toán block riêng. Thunderbird chỉ dùng nếu audit xác nhận host và nhãn tương thích. [Dataset inventory](../../docs/research/DATASETS.md) · [July holdout](../../docs/ml/IF_JULY_HOLDOUT.md)
- Máy Windows ghi nhận Intel i5-14600K, 20 logical CPU, 31,7 GiB RAM và RTX 4060 Ti. Rule, IF và LR có thể lên kế hoạch chạy CPU trên cache feature giới hạn bộ nhớ. Chi phí chạy trên holdout mới, GPU training và khả năng tái lập trên máy khác chưa đo. Không dùng worker time của University MVP làm dự đoán chắc chắn cho thí nghiệm.
- Rủi ro chính là các giai đoạn BGL đã xem, nhãn alert ít và không đồng đều theo host, parser/feature leakage và FPR không ổn định dưới drift. Khóa đoạn thời gian còn kín, kiểm tra support theo block và báo subgroup coverage trước khi đặt tuyên bố khái quát.

## Thứ tự thực hiện sau duyệt

Lịch dự kiến gồm một đợt chốt literature/protocol, một đợt chuẩn hóa dữ liệu và leak tests, một đợt so ba baseline, một đợt ablation/generalization và một đợt rerun độc lập. Ước tính thời gian từng đợt sau pilot trên development. GO khi có temporal cohort chưa mở, nhãn đáng tin, support và ngân sách compute phù hợp. NO-GO cho tuyên bố mới nếu prior art trùng hoặc độ tin cậy không đủ. [Protocol](../00_research_protocol/PROTOCOL_VI.md) · [Novelty audit](../reviews/novelty_audit.md) · [GO/NO-GO](../reviews/research_gaps.md)

