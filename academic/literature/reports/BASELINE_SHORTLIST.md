# Shortlist baseline cho BGL và LogSense AI

Chọn theo giá trị đối chứng trên BGL host-window, khả năng tái lập và chi phí. Hiệu năng paper dùng đơn vị khác chỉ làm bằng chứng chọn ứng viên. Chưa chạy baseline hoặc mở test mới.

| Ưu tiên | Baseline | Input và học | Compute / tái lập | Leakage và giá trị đối chứng |
|---|---|---|---|---|
| 1 | **Rule count hiện có** | Số log/cửa sổ 300 giây. Score đơn điệu theo count, ngưỡng validation. | CPU thấp, có code dự án. | Dễ kiểm tra ties. Làm mốc tối thiểu cho host-aware và learned score. |
| 2 | **Isolation Forest hiện có** | Năm feature tổng hợp cùng cohort, fit label-blind trên train. Score dùng dấu âm của sklearn score_samples. | CPU thấp–vừa. Cố định seed, max_samples và cấu hình sklearn. | Không lọc train bằng nhãn khi chạy bản label-blind. Tách việc fit khỏi calibration có nhãn. [S08](../reviews/individual_papers/S08.md) |
| 3 | **Logistic Regression L2** | Năm feature chung, scaler fit train, nhãn cửa sổ BGL đủ điều kiện. C chọn trên validation phát triển. | CPU thấp. Có đối chứng logistic trên event-count logs, tái lập dễ. | Không dùng proxy từ alert token; không resample trước split. Cho baseline supervised dễ giải thích. [S06](../reviews/individual_papers/S06.md) |
| 4 | EWMA residual | Chuỗi log-count biến đổi log1p. Điểm residual dùng trạng thái quá khứ và α đã khóa. | CPU thấp, bộ nhớ cố định theo trạng thái. | Score-before-update. Dùng global EWMA làm control để tách lợi ích host-specific. [Roberts](https://doi.org/10.1080/00401706.1959.10489860) |
| 5 | Random Forest | Cùng feature cơ sở và train labels như LR. Cố định độ sâu, số cây, cách cân bằng lớp. | CPU vừa, chi phí đo riêng. | OOB không thay temporal test. Kiểm tra cải thiện phi tuyến và độ nhạy dữ liệu hiếm. [S09](../reviews/individual_papers/S09.md) · [S04](../reviews/individual_papers/S04.md) |
| 6 | PCA residual | Ma trận count/template hoặc năm feature. Fit vocabulary, scaler và PCA trên train. | CPU vừa. Code loglizer/ sklearn, cần kiểm tra bản parser. | Không fit full corpus. Đối chứng subspace và tách giá trị template counts. [S07](../reviews/individual_papers/S07.md) |
| 7 | Streaming Half-Space Trees | Cùng vector theo thứ tự thời gian, mass reference/current, scaler chỉ dùng quá khứ. | CPU vừa, bounded tree/mass. River là implementation tham chiếu. | Reference có thể nhiễm anomaly. Cần prequential và reporting latency. Chỉ mở nếu RQ drift được duyệt. [S22](../reviews/individual_papers/S22.md) |
| 8 | DeepLog adaptation | Template sequence theo host, LSTM next-key, context/top-k freeze. | Cao hơn baseline CPU, phụ thuộc parser và framework. Có reimplementation. | Label-normal training, unseen keys và context qua split phải báo rõ. Là đối chứng sequence giai đoạn sau. [S10](../reviews/individual_papers/S10.md) · [S03](../reviews/individual_papers/S03.md) |

## Nghiệm thu ba baseline đầu

1. Rule count phát lại đúng detector hiện có trên fixture; anchor, count, ties và orientation được kiểm tra. Calibration tạo threshold có thể truy lại từng mức FPR.
2. IF cho score giống nhau trong dung sai đã khóa với dữ liệu/seed/cấu hình cố định. Kiểm tra rằng fit và vocabulary lấy đúng tập train. Score semantics được test.
3. LR chỉ fit trên train có nhãn đủ điều kiện. Log cấu hình scaler, regularization, class weights và số positive. Kiểm tra kiểm định severity proxy bằng ablation.

Cổng chung gồm cohort IDs giống nhau, freeze ngưỡng từ calibration và báo đủ confusion counts, AP, recall/FPR, CI theo thời gian và CPU/RSS. So bằng tiêu chí đã định kể cả khi Rule thắng. [Protocol](../00_research_protocol/PROTOCOL_VI.md)

