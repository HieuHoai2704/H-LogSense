# Protocol dự thảo cho khóa luận LogSense AI

Trạng thái **DRAFT, chờ duyệt trước khi chạy**. Khóa luận tiếp nối [baseline phần mềm University MVP](../../docs/releases/UNIVERSITY_MVP_BASELINE_VI.md). Mọi số dưới đây là lựa chọn thiết kế hoặc cổng nghiệm thu. Chưa mở holdout mới và chưa huấn luyện.

## Câu hỏi chính

Khi mọi detector dùng cùng ngân sách false positives trên validation, chuẩn hóa theo lịch sử host có cải thiện recall của các BGL host-window ở một giai đoạn tương lai chưa mở không? Câu hỏi phụ về độ ổn định theo host lạnh và drift chỉ mở sau khi baseline toàn cục tái lập được. [Novelty audit](../reviews/novelty_audit.md)

## Cohort, splits và nhãn

- Đơn vị BGL chính là host-window UTC 300 giây, khoảng `[start,end)`, có ít nhất một log đã parse. Y=1 nếu có ít nhất một alert token gốc trong các log đủ điều kiện của cửa sổ. Ghi số dòng malformed, host thiếu, nhóm loại, source hashes và coverage. Không gán Y=0 cho khoảng không quan sát. Một phiên HDFS block-id là bài toán phụ riêng.
- Freeze phiên bản archive, parser, mapping nhãn, ranh giới UTC, feature names, seeds và quy tắc trùng lặp trước khi fit. Ấn định train → validation phát triển → validation hiệu chỉnh → final temporal test. Có khoảng cách ít nhất bằng độ dài cửa sổ hoặc lookback có khả năng trùng, tùy cách tạo sample. Lịch sử quá khứ có thể được dùng theo đúng quy tắc online đã khóa. Kiểm tra sample ID và log ID không chồng giữa các tập.
- June và July 21–28 đã được mở. Dùng chúng để kiểm tra đường ống hoặc làm đối chứng lịch sử. Chọn cohort tương lai còn kín bằng timestamp và provenance trước khi xem nhãn/kết quả, ghi ngày và quyền truy cập trong manifest. Nếu không còn đoạn đủ nhãn, chọn corpus độc lập và đăng ký protocol mới trước khi mở.
- Loại nhãn, marker đầu dòng, id, timestamp tuyệt đối và host ID khỏi feature đầu vào. Audit severity/component và template để tìm proxy nhãn. Fit vocabulary, scaler, imputer và reference stats bằng train. Phiên bản online phải score trước rồi mới cập nhật bằng dữ liệu quá khứ đã được phép.
- Định nghĩa đủ số positive và negative theo khối thời gian trước khi mở test bằng phân tích power trên development và độ phân giải `1/n_negative`. Cohort không đủ điều kiện được ghi thiếu lực kiểm định. Giữ nguyên các cohort đã khóa.

## Baseline và ngân sách báo nhầm

1. Dùng Rule count, Isolation Forest và Logistic Regression có trọng số hoặc regularization cố định qua validation phát triển. Bổ sung EWMA, Random Forest và PCA trong shortlist thứ hai. Cả ba chính dùng cùng sample IDs, điều kiện bao phủ và trình tự thời gian. Rule dùng count. IF và supervised dùng cùng năm feature cơ sở khi so trực tiếp.
2. Chuẩn hóa score cao là đáng ngờ, riêng sklearn IF lấy âm của `score_samples`. Chốt ngân sách chính `α = 1%` trên tập hiệu chỉnh chung, độ nhạy `0,1%/0,5%` đã định trước nếu số âm đủ. So các mô hình ở cùng cap. Không ép FPR thực đạt bằng nhau bằng cách chia nhóm điểm hòa. Dùng ngưỡng nghiêm `s > t`, quét nhóm điểm đồng hạng trên validation. Trong các mức dưới cap, tối đa recall, ưu tiên ít FP khi hòa và ghi rõ threshold. Nếu không có mức khác không dưới cap, dùng không phát cảnh báo và báo giới hạn độ phân giải.
3. Đóng băng threshold, tie policy và seeds trước khi đọc test. Báo recall, FPR thực đạt, FP/1.000 cửa sổ âm, precision, AP, confusion matrix, prevalence và coverage. AP theo sklearn. Ghi kết quả khi FPR test vượt cap. Cap là ràng buộc thực nghiệm trên validation, bảo đảm population FPR cần giả định riêng. [NP-ROC](https://doi.org/10.1126/sciadv.aao1659)
4. Dùng paired block bootstrap theo ngày hoặc block dài hơn nếu phụ thuộc kéo dài. Chốt block length, seed và số lần lặp từ development. Ghi CI cho chênh recall/FPR và giới hạn khi số positive theo block quá thấp. Phân nhóm host đã thấy, host lạnh và support thấp. Ghi cả micro và macro theo host với mẫu số.
5. Ablation trên cùng split và FPR cap. So global score, host residual với fallback, adaptive calibration không đổi score, drift trigger không đổi scorer và full nếu đủ bằng chứng. Tách severity proxy, độ dài cửa sổ và cold-start như sensitivity preregistered. Bài test generalization đầu tiên dùng giai đoạn BGL độc lập. Thunderbird chỉ vào so sánh nếu mapping nhãn và đơn vị tương thích. HDFS tách riêng.

## Biên bản nghiệm thu

Lưu hash dữ liệu/code/protocol, config, seed, package versions, feature cohort, threshold, test access log và metrics; ghi Python/CPU/RAM, time và peak RSS. Rerun độc lập và đối chiếu số đếm chính xác cùng dung sai score đã chốt trước. Báo GO/NO-GO theo [research gaps](../reviews/research_gaps.md). Nếu thay quy tắc sau khi thấy test, chuyển kết quả thành exploratory và dùng holdout mới trước khi khẳng định. [Roadmap và điểm mục tiêu](../../docs/releases/GRADUATION_THESIS_ROADMAP_VI.md)

