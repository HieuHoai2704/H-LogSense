# H-logsen Window Baseline trên BGL thật

Đo ngày 09/11/2026 theo giờ Việt Nam. Dữ liệu là bản BGL gốc công khai từ Loghub, SHA-256 khớp với lần kiểm toán trước. Sáu mô hình được chạy trên cùng cửa sổ 5 phút theo host, dùng UTC và phạm vi [start,end). XGBoost là ứng viên thực nghiệm dựa trên kết quả của Xiao et al. Bộ biểu diễn và cách chia cửa sổ của nghiên cứu này khác paper. [BGL gốc](https://zenodo.org/records/8196385) · [Paper Xiao et al.](https://arxiv.org/html/2610.05807v1)

**Kết luận.** Window LR được chọn trên tập lựa chọn. Hai biến thể dùng nội dung đều đạt trần FPR 0,20% ở test tháng 9 và đều vượt trần trong giai đoạn sau. Window XGBoost có kết quả hậu kiểm tốt hơn về F1 và FPR ở cả hai giai đoạn, nên là ứng viên tiếp theo để hiệu chỉnh trên validation độc lập. Tình trạng triển khai cảnh báo ở mức FPR ≤ 0,20% là **NO-GO**.

## Nguồn và thời gian

| Giai đoạn | Ngày UTC [start,end) | Dòng gốc | Dòng hợp lệ có host | Cửa sổ | Cửa sổ dương |
| --- | --- | ---: | ---: | ---: | ---: |
| Train | 2005-06-03 → 2005-08-01 | 2,908,798 | 2,908,173 | 1,775,316 | 78,089 |
| Chọn mô hình | 2005-08-01 → 2005-08-18 | 153,415 | 153,377 | 43,433 | 12,376 |
| Hiệu chỉnh ngưỡng | 2005-08-18 → 2005-09-01 | 247,030 | 243,849 | 131,704 | 9,866 |
| Test chính | 2005-09-01 → 2005-10-01 | 222,533 | 222,507 | 75,470 | 36,978 |
| Test giai đoạn sau | 2005-10-01 → 2006-01-05 | 1,216,187 | 1,185,263 | 470,831 | 50,602 |

Tập train dùng 78.089 cửa sổ dương và 400.000 cửa sổ âm lấy mẫu cố định cho các mô hình có nhãn. Isolation Forest dùng 20.000 cửa sổ train lấy mẫu không theo nhãn. Mô hình, vector hóa và ngưỡng đều được khóa trước khi đọc nhãn test. Count dùng năm đặc trưng cũ, độ hiếm mẫu và tối đa 256 mẫu hay gặp. Window bổ sung 24 chiều SVD từ TF-IDF cụm ký tự 3–5 trên mẫu log, học từ train. Nhãn gốc, thời gian tuyệt đối, host ID và dòng nguồn không được đưa vào ma trận đặc trưng. Văn bản thông điệp có thể mang dấu hiệu đặc trưng của cùng hệ thống BGL.

Trên tập lựa chọn, Window LR đạt recall 87,48%, Window XGBoost đạt 80,76%, cùng trần 0,20%. Ngưỡng từng mô hình sau đó được tính trên tập hiệu chỉnh riêng bằng recall tối đa trong ngân sách. Tập hiệu chỉnh đã chọn ngưỡng với FPR 0,19862% cho Window LR và 0,08290% cho Window XGBoost.

## Kết quả tại các ngưỡng đã khóa

### Tháng 9/2005

| Phương pháp | Precision | Recall | F1 | AP | FPR | TP / FP / FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule đếm log | 7.49% | 0.14% | 0.0027 | 0.4656 | 1.606% | 50 / 618 / 36,928 |
| Isolation Forest | 0.28% | 0.05% | 0.0008 | 0.4287 | 15.562% | 17 / 5,990 / 36,961 |
| Count LR | 34.25% | 6.10% | 0.1036 | 0.7988 | 11.254% | 2,257 / 4,332 / 34,721 |
| Count XGBoost | 58.39% | 6.16% | 0.1114 | 0.6694 | 4.214% | 2,276 / 1,622 / 34,702 |
| H-logsen Window LR | 99.82% | 99.85% | 0.9984 | 0.9990 | 0.174% | 36,924 / 67 / 54 |
| H-logsen Window XGBoost | 99.87% | 99.99% | 0.9993 | 0.9990 | 0.127% | 36,976 / 49 / 2 |

### Tháng 10/2005 đến đầu tháng 1/2006

| Phương pháp | Precision | Recall | F1 | AP | FPR | TP / FP / FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule đếm log | 2.53% | 0.30% | 0.0054 | 0.0932 | 1.410% | 154 / 5,926 / 50,448 |
| Isolation Forest | 0.32% | 0.02% | 0.0004 | 0.1252 | 0.895% | 12 / 3,761 / 50,590 |
| Count LR | 54.14% | 13.49% | 0.2160 | 0.5938 | 1.376% | 6,826 / 5,782 / 43,776 |
| Count XGBoost | 73.32% | 22.69% | 0.3465 | 0.6749 | 0.994% | 11,480 / 4,177 / 39,122 |
| H-logsen Window LR | 93.82% | 98.05% | 0.9589 | 0.9789 | 0.778% | 49,615 / 3,268 / 987 |
| H-logsen Window XGBoost | 98.08% | 99.99% | 0.9903 | 0.9917 | 0.235% | 50,599 / 989 / 3 |

## Kiểm tra sau khi mở test

Hai mã KERNMNTF và APPSEV chiếm 35.970/37.835 dòng dương đã parse của tháng 9 (95,07%). Tỷ lệ cửa sổ dương giảm từ 49,00% ở tháng 9 xuống 10,75% ở test sau. Kết quả cao của tháng 9 nên được đọc trong bối cảnh này. Cả hai mô hình có nội dung vẫn phát hiện phần lớn cửa sổ toàn mẫu chưa gặp ở test sau, nhưng báo nhầm của nhóm này cao hơn ngân sách. Ở test sau, Window XGBoost có 989 FP trong khi ngân sách chỉ cho 840 FP.

Khoảng 95% ước lượng bằng bootstrap 2.000 lần theo ngày cho FPR của Window XGBoost là 0,037%–0,304% ở tháng 9 và 0,029%–0,723% ở giai đoạn sau. Mức 0,127% của tháng 9 là số đo điểm. Không đủ bằng chứng để bảo đảm trần FPR trên một thời kỳ mới. So sánh với số công bố trong paper cần tái chạy đúng đối chứng trên cùng lát dữ liệu và đơn vị phát hiện.

## Chạy lại và bằng chứng

Windows, Python 3.10.11, scikit-learn 1.7.2, XGBoost 3.2.0, CPU 6 luồng cấu hình. Fit, chọn và hiệu chỉnh tổng cộng 77.90 giây với peak working set 1773.34 MiB. Hai test mất 7.17 và 25.50 giây trong cùng tiến trình. Đã chạy 26 unit tests cho parser, calibration và baseline.

Cài XGBoost vào môi trường nghiên cứu hoặc dùng thư mục package riêng qua PYTHONPATH. Dùng một đường dẫn output mới để chạy lại. Bản BGL phải khớp SHA-256 đã khóa.

```text
python -m pip install xgboost==3.2.0
python -m scripts.ml.bgl_window_baseline --out .local/bgl-reproduction --stage fit
python -m scripts.ml.bgl_window_baseline --out .local/bgl-reproduction --stage test
python -m unittest tests.test_bgl_window_baseline tests.test_detector_calibration tests.test_bgl_parser
```

[Giao thức](measurements/bgl-window-2026-11-09/protocol.json) · [Mô hình và ngưỡng đã khóa](measurements/bgl-window-2026-11-09/freeze.json) · [Dấu mở test](measurements/bgl-window-2026-11-09/test-access.json) · [Kết quả đầy đủ](measurements/bgl-window-2026-11-09/test-results.json) · [Phân tích hậu kiểm](measurements/bgl-window-2026-11-09/posthoc.json)

Artifact nghiên cứu và điểm theo từng cửa sổ lưu cục bộ trong .local/bgl-window-20261109. Giữ artifact joblib trong phạm vi tin cậy. Thử nghiệm dùng một seed và một hệ thống BGL. Ứng viên chưa nối vào detector sản xuất.
