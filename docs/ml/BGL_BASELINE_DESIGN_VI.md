# Baseline BGL cho H-logsen

Trạng thái **thiết kế**, ngày 08/11/2026. Chưa có mô hình mới hoặc số đo mới. Mục tiêu là so sánh với baseline mạnh từ paper ở cùng đơn vị phát hiện, cùng dữ liệu theo thời gian và cùng ngân sách báo nhầm.

| Nghiên cứu | Cách dựng và kết quả gốc trên BGL | Dùng lại trong thử nghiệm |
| --- | --- | --- |
| He et al., ISSRE 2016, Hình 6–7 | Đếm mẫu log theo cửa sổ. Chia theo thời gian. SVM trượt đạt precision 99%, recall 75%, F1 0,85 với cửa sổ 6 giờ, bước 1 giờ. | SVM tuyến tính trên vector đếm làm đối chứng. Tính lại trên cửa sổ 5 phút theo host để so công bằng. [Bản tác giả](https://jiemingzhu.github.io/pub/slhe_issre2016.pdf) |
| Wu et al., 2023, Bảng 3 | Decision Tree và TF-IDF văn bản đạt F1 0,967. Logistic Regression và vector đếm đạt F1 0,917. Cửa sổ 6 giờ, chia ngẫu nhiên. | Dựng Logistic Regression đếm mẫu và cây với TF-IDF, khóa từ điển trước validation. [Bản tác giả](https://www.hengli.org/pdf/Wu2023LogRepresentation.pdf) |
| Sedláček et al., CNSM 2025, Bảng VII–VIII | Trong cấu hình 40 dòng hoặc 60 giây, trung vị F1 của SVM giảm 0,917 → 0,570 khi đổi từ xáo trộn sang tuần tự. | Giữ thứ tự thời gian và đánh giá riêng từng giai đoạn. [Proceedings](https://dl.ifip.org/db/conf/cnsm/cnsm2025/1571164872.pdf) |
| Xiao et al., 2026, Bảng V–VI | Semantic XGBoost đạt AP 0,676 ± 0,086 và F1 0,492 ± 0,165 với cửa sổ 100 dòng theo thời gian. Đổi parser làm AP thay đổi. | Đưa Count/XGB vào nhóm đối chứng. Thử Semantic/XGB nếu tái lập được encoder, parser và quyền truy cập corpus của tác giả. [Toàn văn](https://arxiv.org/html/2610.05807v1) |

Báo cáo [đối chiếu toàn văn và số liệu tháng 7](../../academic/literature/reports/BGL_LOW_FPR_FULLTEXT_RESULTS_VI.md) lưu kết quả theo đúng giao thức từng bài. Thử nghiệm 5 phút theo host giữ riêng với thí nghiệm tái lập giao thức gốc. Các mô hình chạy lại ở 5 phút là bản chuyển thể, cần ghi cấu hình và mọi sai khác.

## Baseline ứng viên

**H-logsen Window LR** là Logistic Regression có nhãn với đầu vào thưa và điểm xếp hạng càng cao càng bất thường. Một cửa sổ ứng với một host có log hợp lệ trong đoạn UTC cố định 300 giây dạng [start,end). Tính điểm sau khi cửa sổ kết thúc. Nhãn dương khi có ít nhất một dòng quan sát được mang nhãn bất thường gốc. Ghi riêng dòng bị parser loại, host thiếu và cửa sổ không quan sát được.

| Nhóm đặc trưng | Định nghĩa |
| --- | --- |
| Thống kê | Năm đặc trưng của Isolation Forest hiện tại gồm số dòng, tỷ lệ severity cao, tỷ lệ mẫu riêng biệt, tỷ lệ mẫu trội, độ dài trung bình. Dùng biến đổi đúng hợp đồng cũ để đối chiếu. |
| Vector đếm mẫu | Dùng thông điệp đã parse, chuẩn hóa giá trị động theo phiên bản cố định, tính log1p count cho các mẫu được gặp trong train. Có cột riêng đếm mẫu ngoài từ điển. |
| Nội dung ngoài từ điển | Character TF-IDF 3–5 ký tự trên thông điệp đã chuẩn hóa, tối đa 16.384 đặc trưng. Từ điển, tần suất tài liệu và phép chuẩn hóa chỉ fit trên train. Thử thêm nhóm này để kiểm tra nó có giúp với mẫu chưa gặp. |

Cấu hình dự kiến L2, C nhận một trong ba giá trị 0,1 / 1 / 10, seed 42, chuẩn hóa thống kê từ train, giữ tỷ lệ lớp tự nhiên ở validation và test. Đưa phương án cân bằng lớp vào ablation đã đăng ký cùng quy tắc chọn ngưỡng. Đầu ra dùng margin để xếp hạng. Evidence ghi mẫu hoặc đặc trưng có tích số trọng số và giá trị lớn nhất cùng số dòng, timestamp và tham chiếu log. Host dùng để gom cửa sổ và phân nhóm đánh giá. Host ID, label token, raw prefix, timestamp tuyệt đối, offset và số dòng nguồn ở ngoài bộ đặc trưng.

## Giao thức để đo ngang sức

1. Kiểm kê các khoảng đã dùng trong mọi báo cáo và lần chạy. Chọn các khoảng còn chưa xem kết quả; chốt tiêu chí đủ mẫu trước khi chạy. Nếu toàn bộ BGL đã được dùng để chọn mô hình, ghi là kiểm tra lại và chọn nguồn đánh giá độc lập thích hợp.
2. Chốt train → validation chọn mô hình → validation hiệu chỉnh ngưỡng → test độc lập, tất cả theo UTC. Cấu hình, parser, bộ feature, từ điển, ngưỡng và mã nguồn đều có hash trước khi đọc test. Cùng cohort cho Rule, IF, Count/LR, SVM, Tree/TF-IDF, Count/XGB và ứng viên. Các đối chứng cũng chọn ngưỡng theo cùng quy tắc.
3. Mốc vận hành chính FPR ≤ **0,20%**. Chọn ngưỡng tối đa recall trong ngân sách trên tập hiệu chỉnh, giữ nguyên cả nhóm điểm bằng nhau. Báo FPR và recall thực đạt trên test dù vượt ngân sách. Báo thêm đường precision–recall, AP, F1, confusion matrix, độ phủ, thời gian, RAM, kết quả theo ngày và host đã gặp/chưa gặp. Dùng bootstrap theo khối thời gian để biểu diễn biến động. Tập có quá ít khối hoặc quá ít ca dương chỉ dùng để thăm dò.
4. So sánh ghép cặp trên cùng test. Ứng viên được xem là cạnh tranh khi đạt FPR ≤ 0,20% và cận dưới 95% của chênh lệch so với đối chứng mạnh nhất đã chọn trên validation theo tiêu chí đăng ký đạt ít nhất −5 điểm % recall và −0,03 AP. Đặt mục tiêu cải thiện so với IF là +10 điểm % recall tại cùng trần FPR, đồng thời kiểm tra độ bất định và FPR theo từng giai đoạn. Khi chưa đủ bằng chứng, giữ trạng thái chưa xác nhận.

## Mốc nội bộ

Isolation Forest trên 21–28/07/2005 đạt **22,52% precision, 55,43% recall, F1 0,3203, AP 0,2656 và FPR 0,203661%**, với 102 TP, 351 FP, 82 FN. Mốc này hơi vượt trần nghiêm ngặt 0,20% đề xuất cho lần mới. Mức 99,46% recall là quét lại điểm trên test đã mở, dùng để phân tích độ nhạy. [Báo cáo IF](IF_JULY_HOLDOUT.md) · [Phân tích hậu kiểm](../../academic/literature/reports/BGL_LOW_FPR_FULLTEXT_RESULTS_VI.md)

Triển khai nghiên cứu theo thứ tự kiểm kê độ phơi nhiễm test, dựng Count/LR, thêm ablation và đối chứng mạnh, sau đó khóa giao thức và chạy. Đóng góp dự kiến cần kiểm chứng là khả năng tìm thêm bất thường trong cùng ngân sách báo nhầm trên cửa sổ ngắn có thể truy ra log gốc.
