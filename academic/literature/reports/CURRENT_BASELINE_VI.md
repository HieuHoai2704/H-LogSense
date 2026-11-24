# Mốc kết quả LogSense AI trước khi cải tiến

Snapshot ngày 06/11/2026, dựa trên các phép đo lưu ngày 04/11/2026. Phạm vi là chất lượng phát hiện bất thường trên BGL và bằng chứng chạy qua ứng dụng. **Mốc chính để ghi nhớ là Isolation Forest đã chọn trên validation, đo trên tập test tháng 7.** Tập tháng 6 cung cấp một phép đo lịch sử trên giai đoạn khác.

## Phạm vi hai phép đo nội bộ

Đơn vị là **một host × 5 phút UTC**, chỉ gồm các cửa sổ có log đã parse và có host. Một cửa sổ dương tính khi ít nhất một log đủ điều kiện mang nhãn alert gốc BGL. Precision là tỷ lệ cảnh báo đúng trong số cảnh báo đã phát, recall là tỷ lệ bắt được trong số cửa sổ dương tính, FPR là tỷ lệ báo nhầm trên các cửa sổ âm tính. F1 kết hợp precision và recall tại một ngưỡng, còn AP là average precision của sklearn.

| Tập test BGL | Cửa sổ | Dương tính | Âm tính | Tỷ lệ dương tính | Nguồn |
|---|---:|---:|---:|---:|---|
| 20/06 07:45–25/06 18:50/2005 UTC | 89.119 | 658 | 88.461 | 0,73834% | [JSON tháng 6](../../../docs/ml/measurements/if-bgl-2026-11-04/test-results.json) |
| 21/07 00:00–28/07 00:00/2005 UTC | 172.529 | 184 | 172.345 | 0,10665% | [JSON tháng 7](../../../docs/ml/measurements/if-july-holdout-2026-11-04/test-results.json) |

Thời điểm cuối của mỗi tập là biên loại trừ. Trong tháng 7, 313.651 dòng thô thuộc khoảng test, trong đó 40 dòng bị parser từ chối và 17 sự kiện thiếu host. Phép đo dùng 313.594 sự kiện đã parse có host, với phạm vi bao phủ theo dữ liệu quan sát được. [Định nghĩa và audit parser](../../../docs/ml/IF_JULY_HOLDOUT.md#data-chronology-and-provenance)

## Kết quả trên từng tập test

| Tập test | Phương pháp | Precision | Recall | F1 | AP | FPR | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Tháng 6 | Rule đếm log cũ | 1,32% | 100,00% | 2,60% | 0,1014 | 55,7873% | 658 | 49.350 | 0 | 39.111 |
| Tháng 6 | Isolation Forest cũ | 14,27% | 21,88% | 17,28% | 0,0828 | 0,9778% | 144 | 865 | 514 | 87.596 |
| Tháng 6 | Isolation Forest chọn trên validation | 46,10% | 38,60% | 42,02% | 0,1845 | 0,3357% | 254 | 297 | 404 | 88.164 |
| Tháng 7 | Rule đếm log cũ | 0,24% | 3,80% | 0,44% | 0,0293 | 1,7163% | 7 | 2.958 | 177 | 169.387 |
| Tháng 7 | Isolation Forest cũ | 0,18% | 100,00% | 0,36% | 0,0260 | 58,8053% | 184 | 101.348 | 0 | 70.997 |
| Tháng 7 | Isolation Forest chọn trên validation | 22,52% | 55,43% | 32,03% | 0,2656 | 0,2037% | 102 | 351 | 82 | 171.994 |

Mỗi nhóm ba dòng dùng chung tập test và nhãn. Rule đếm log và Isolation Forest cũ dùng ngưỡng theo chính sách cũ. Hai mô hình được chọn trên validation dùng các cấu hình riêng cho từng nghiên cứu, với giới hạn **FPR ≤ 1% trên validation**. FPR trong bảng là giá trị thực đo trên test. Vì các ngưỡng thực nghiệm có FPR khác nhau, đây là đối chiếu các chính sách đã chạy trên cùng mẫu, còn phép so detector dưới một ngân sách báo nhầm chung vẫn chờ thực hiện. [Báo cáo tháng 6](../../../docs/ml/ISOLATION_FOREST_AUDIT.md) · [Báo cáo tháng 7](../../../docs/ml/IF_JULY_HOLDOUT.md)

**Kết quả tháng 7 dùng làm mốc chính.** Isolation Forest được chọn phát **453 cảnh báo**, gồm **102 đúng** và **351 nhầm**, bỏ sót **82/184** cửa sổ dương tính. Tháng 6 ghi F1 cao hơn với **42,02%**, còn tháng 7 ghi recall cao hơn với **55,43%**. Hai tập có tỷ lệ dương tính khác nhau và mô hình được chọn khác cấu hình, nên giữ cả hai số theo từng giai đoạn. [JSON tháng 6](../../../docs/ml/measurements/if-bgl-2026-11-04/test-results.json) · [JSON tháng 7](../../../docs/ml/measurements/if-july-holdout-2026-11-04/test-results.json)

## Kết quả về ngữ cảnh host

Thử nghiệm tháng 7 đã thử một nhóm bốn đặc trưng bổ sung gồm thống kê template và host. Cùng cấu hình **100 cây, max_samples = 256**, phiên bản năm đặc trưng cơ sở đạt F1 validation **39,80%**, phiên bản bổ sung đạt **25,52%**. Cả hai ngưỡng ở dưới giới hạn FPR validation 1%. Nhóm bổ sung chứa nhiều đặc trưng cùng lúc, vì vậy kết quả chỉ cho biết **gói đặc trưng đã thử chưa cải thiện F1 validation**, còn hiệu quả riêng của lịch sử host và cơ chế dùng mức nền chung khi host ít dữ liệu vẫn cần phép đối chứng. [Bảng lựa chọn trên validation](../../../docs/ml/IF_JULY_HOLDOUT.md#audit-features-fitting-score-direction-and-threshold)

## Chỉ số của các baseline trong paper

Trong phần này, dấu **—** nghĩa là bảng được dẫn không công bố chỉ số đó. FPR có dấu **≈** được tính bằng 100% trừ specificity đã làm tròn. PR-AUC là tên chỉ số trong paper, còn AP nội bộ ở trên là average precision của sklearn.

### Qi Xin (2026) — BGL_2k, cùng 298 cửa sổ test

Các mô hình Bảng 4 dùng cửa sổ trượt 20 log, bước 1, chia theo thời gian. Mỗi mô hình chọn ngưỡng tối đa F1 trên tập hiệu chỉnh. Bảng 7 báo thêm EventCount-Z trên cùng thiết lập cửa sổ W = 20, trong một nhóm thử nghiệm riêng. [Qi Xin, Bảng 1, 4 và 7](https://ejournals.itda.ac.id/index.php/avitec/article/viewFile/3974/pdf)

| Baseline | Precision | Recall | F1 | PR-AUC | FPR | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---:|
| TF-IDF + Logistic Regression | 66,67% | 64,34% | 65,48% | 0,5422 | 29,68% | 92 / 46 / 51 / 109¹ |
| Isolation Forest | 92,86% | 9,09% | 16,56% | 0,7501 | 0,65% | 13 / 1 / 130 / 154¹ |
| DeepLog-LSTM | 46,97% | 86,71% | 60,93% | 0,4114 | 90,32% | 124 / 140 / 19 / 15¹ |
| Transformer | 45,82% | 80,42% | 58,38% | 0,3225 | 87,74% | 115 / 136 / 28 / 19¹ |
| EventCount-Z (Bảng 7) | 43,21% | 73,43% | 54,40% | 0,3271 | 89,03% | 105 / 138 / 38 / 17 |

¹ Suy ra số nguyên khớp với các tỷ lệ làm tròn Bảng 4 trên cùng 143 cửa sổ dương và 155 cửa sổ âm theo Bảng 7. Số đếm EventCount-Z do tác giả công bố trực tiếp.

### Le & Zhang (2022) — BGL, cửa sổ 1 giờ, chọn train theo thời gian

| Baseline | Precision | Recall | F1 | PR-AUC | FPR | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---|
| DeepLog | 27,0% | 98,8% | 42,6% | — | ≈ 56,3% | — |
| LogAnomaly | 31,3% | 79,8% | 48,3% | — | ≈ 44,9% | — |
| PLELog | 70,2% | 79,1% | 74,4% | — | ≈ 10,1% | — |
| LogRobust | 99,4% | 94,2% | 96,7% | — | ≈ 0,1% | — |
| CNN | 87,1% | 94,7% | 90,8% | — | ≈ 3,0% | — |

Nguồn là cột BGL theo thời gian trong Bảng 2. Bảng 4 của cùng bài đổi sang gom phiên theo node ID, khi đó LogRobust và CNN có precision, recall, F1 và specificity đều hiển thị 100%. [Le & Zhang, Bảng 2 và 4](https://doi.org/10.1145/3510003.3510155)

### Các đối chiếu BGL khác

| Paper và thiết lập | Baseline | Precision | Recall | F1 | PR-AUC | FPR | Nguồn |
|---|---|---:|---:|---:|---:|---:|---|
| Ali et al., chuỗi 15 log | NeuralLog1 | 99,97% | 99,91% | 99,94% | — | ≈ 0,00% theo độ làm tròn | [Bảng 8–9](https://link.springer.com/article/10.1007/s10664-025-10669-3) |
| Ali et al., chuỗi 15 log | Random Forest | 93,29% | 78,96% | 85,46% | — | ≈ 0,54% | [Bảng 8–9](https://link.springer.com/article/10.1007/s10664-025-10669-3) |
| Ali et al., chuỗi 15 log | SVM | 97,52% | 92,38% | 94,88% | — | ≈ 0,22% | [Bảng 8–9](https://link.springer.com/article/10.1007/s10664-025-10669-3) |
| Guo et al., cửa sổ trượt 5 phút | Isolation Forest | 99,70% | 18,11% | 30,65% | — | — | [Bảng 2](https://doi.org/10.1109/IJCNN52387.2021.9534113) |
| Guo et al., cửa sổ trượt 5 phút | LogBERT | 89,40% | 92,32% | 90,83% | — | — | [Bảng 2](https://doi.org/10.1109/IJCNN52387.2021.9534113) |
| Yang et al., gom chuỗi có xét node | PLELog | 96,5% | 99,9% | 98,2% | — | — | [Bảng I](https://doi.org/10.1109/ICSE43902.2021.00130) |
| Xie et al., cửa sổ 100 log | LogSD | 96,00% | 96,64% | 96,27% | 0,9716 | — | [Bảng 2](https://doi.org/10.1145/3660800) |
| Landauer et al., cửa sổ thời gian, chọn train theo thời gian | Rule Event | — | — | 47,0% | — | — | [Bảng 2](https://doi.org/10.1145/3660768) |

Các bảng trên giữ nguyên từng đơn vị dự đoán và tập dữ liệu. BGL_2k có 143/298 cửa sổ dương tính, còn tập tháng 7 LogSense AI có 184/172.529 cửa sổ dương tính và gom theo host × 5 phút. So trực tiếp các mô hình dưới cùng ngân sách báo nhầm cần chạy lại trên cùng tập test. [Bảng tổng hợp paper](PAPER_RESULTS_VI.md) · [Phép đo tháng 7](../../../docs/ml/IF_JULY_HOLDOUT.md)

## Trạng thái trước thí nghiệm mới

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Mốc lịch sử detector trên BGL | **Đã đo** | Hai giai đoạn tháng 6 và tháng 7 với số đếm và artifact riêng. |
| Kiểm tra mô hình tháng 7 qua ứng dụng | **Đã kiểm chứng chức năng** | 20 cửa sổ BGL đã được chọn vì mô hình đánh dấu, kết quả khớp giữa MySQL, Timeline, Evidence và CSV. [Bằng chứng](../../../docs/ml/measurements/if-july-holdout-2026-11-04/actual-db-profile-proof.json) |
| Rule, Isolation Forest và Logistic Regression cùng giới hạn FPR trên một tập mới | **Chưa đo** | Protocol đã phác thảo. [Protocol khóa luận](../00_research_protocol/PROTOCOL_VI.md) |
| Lợi ích riêng của lịch sử host và mức bão hòa | **Chưa xác định** | Cần tách từng yếu tố trên tập theo thời gian còn kín và ghi FPR thực đạt. |

Tập tháng 6 và tháng 7 đã được mở để báo cáo. Khi cải tiến, giữ chúng làm mốc lịch sử và đăng ký một giai đoạn chưa dùng để chọn mô hình hoặc ngưỡng. [Quy tắc chia tập](../00_research_protocol/PROTOCOL_VI.md#cohort-splits-và-nhãn)
