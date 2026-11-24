# Roadmap Graduation Thesis LogSense AI

**Kế hoạch và tiêu chí nghiệm thu.** Điểm tham chiếu gần nhất **71/100**, mục tiêu **90–100/100**. Chấm lại bằng kết quả thực tế sau các cổng nghiên cứu. Baseline phần mềm là [University MVP v1.0 đã kiểm thử](UNIVERSITY_MVP_BASELINE_VI.md). Real-Time AI Training Monitoring nằm ở [backlog DEFERRED](BACKLOG.md) đến sau khi hoàn thiện khóa luận.

## Trình tự và bằng chứng nghiệm thu

| Giai đoạn | Đầu ra cần duyệt | Cổng nghiệm thu |
|---|---|---|
| 1. Định nghĩa đề tài | Literature matrix, câu hỏi chính, đơn vị đo, mục tiêu ứng dụng | Nêu đúng phạm vi host-window BGL. Phân biệt bằng chứng prior art với giả thuyết còn kiểm tra. |
| 2. Khóa protocol | Manifest dữ liệu, temporal boundaries, label rules, FPR budget và kế hoạch đo | Có holdout chưa mở và bản protocol hash trước khi trích kết quả. Kiểm toán leakage ở dữ liệu, parser, feature, split và threshold. |
| 3. Baseline sau khi duyệt | Rule đếm, Isolation Forest và classifier supervised có nhãn đủ điều kiện | Cùng feature cohort, metric và ngân sách FPR trên validation. Có test score direction, tie handling và reproducibility. |
| 4. Kiểm định giả thuyết | Ablation và kiểm tra generalization | Tách score, host context, threshold và drift update. Báo kết quả âm, uncertainty và subgroup coverage. |
| 5. Đóng gói bằng chứng | Bảng kết quả, cấu hình, hashes, hướng dẫn chạy lại và giới hạn | Người khác chạy được pipeline nghiên cứu và đối chiếu kết quả theo tolerance đã định. |

## Mốc đánh giá

| Tiêu chí | Mốc | Điểm tối đa | Điều kiện để xét đủ điểm |
|---|---:|---:|---|
| Bài toán | 16 | 20 | RQ rõ, có ích, gắn với ngân sách báo nhầm và giới hạn của BGL |
| Phương pháp | 22 | 30 | Protocol đóng băng, ba baseline chính, score direction, temporal holdout và leakage checks |
| Đối chứng và khái quát | 14 | 20 | Matched FPR budget, ablation, một cohort temporal bổ sung hoặc dataset ngoài có đơn vị/nhãn phù hợp |
| Tái lập | 12 | 20 | Code nghiên cứu, version dữ liệu, seeds, hashes, môi trường và rerun độc lập |
| Báo cáo | 7 | 10 | Bảng kết quả có nguồn, sai số, trường hợp thất bại và phạm vi kết luận |
| **Tổng** | **71** | **100** | Điểm 90–100 chỉ xét khi có kết quả, kiểm toán và minh chứng đạt các tiêu chí |

Chi tiết thí nghiệm nằm trong [protocol dự thảo](../../academic/literature/00_research_protocol/PROTOCOL_VI.md). Chưa mở holdout mới hoặc chạy huấn luyện trong đợt này.

