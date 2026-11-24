# Literature review cho LogSense AI

## Log anomaly detection và nguồn dữ liệu

Loghub giúp khóa phiên bản và phân biệt BGL event label với HDFS block/session. Việc chọn parser, template vocabulary, window và cách map label là một phần của phương pháp. Drain là parser online; kết quả parsing accuracy không đo chất lượng anomaly detector. Loghub-2.0 phục vụ benchmark parser và có thể khác corpus BGL dùng trong đánh giá alert. [Loghub](https://doi.org/10.1109/ISSRE59848.2023.00071) · [Drain](https://doi.org/10.1109/ICWS.2017.13)

## Baseline cổ điển và mô hình sâu

He và cộng sự dùng count vectors theo nhóm log để so PCA, invariant/clustering và classifier. Xu và cộng sự cho thấy vai trò của biến nhóm và PCA residual. IF có score dựa isolation path và CPU fit hữu ích. EWMA/CUSUM là đối chứng cho thay đổi qua thời gian. Logistic Regression và RF kiểm tra mức lợi ích của nhãn. Một empirical study sau này ghi RF cạnh tranh với nhiều mô hình sâu trong phạm vi bảy benchmark. [He](https://doi.org/10.1109/ISSRE.2016.21) · [Xu](https://doi.org/10.1145/1629575.1629587) · [IF](https://doi.org/10.1109/ICDM.2008.17) · [Ali](https://doi.org/10.1007/s10664-025-10669-3)

DeepLog dự đoán next key; LogAnomaly thêm count và semantic template; PLELog khai thác nhãn mềm; LogBERT dùng masked prediction; LogSD kiểm tra masking/reconstruction qua ablation. Các thiết lập HDFS session, BGL fixed log-count và BGL host-window đo các quần thể khác nhau. Chỉ so số đo nội bộ khi source, nhãn, unit, split, feature và policy thống nhất. [DeepLog](https://doi.org/10.1145/3133956.3134015) · [LogAnomaly](https://doi.org/10.24963/ijcai.2019/658) · [PLELog](https://doi.org/10.1109/ICSE43902.2021.00130) · [LogBERT](https://doi.org/10.1109/IJCNN52387.2021.9534113) · [LogSD](https://doi.org/10.1145/3660800)

## Host, drift và kiểm soát ngưỡng

TeleDAL đã dùng xử lý riêng mỗi node BGL. RT-Log theo hướng field-aware và environment generalization. LogRobust xử lý template instability, còn LogOnline/LogFlash khai thác cập nhật online. ADWIN và HST là đối chứng gọn về drift và streaming. Một paper năm 2026 áp conformal alert trên BGL_2k và đưa evidence vào ticket. Câu hỏi khóa luận nên tập trung vào lợi ích tăng thêm của host normalization/pooling trong điều kiện temporal và matched empirical FPR, có cold-start và ablation. [TeleDAL](https://doi.org/10.1007/s11227-023-05379-w) · [RT-Log](https://doi.org/10.1145/3588918) · [LogRobust](https://doi.org/10.1145/3338906.3338931) · [Conformal alert](https://doi.org/10.28989/avitec.v8i2.3974)

## Đo lường công bằng

Kết quả random split dễ lạc quan. Le & Zhang báo BGL DeepLog F1 0,927 khi random và 0,426 khi chronological trong cùng bảng. Critical review chỉ ra các baseline đơn giản có thể nắm phần lớn bất thường của vài corpus và phiên bản dữ liệu ảnh hưởng kết luận. Dùng temporal holdout, cùng validation budget, confusion counts, AP theo đúng định nghĩa, prevalence và block CI. Cùng cap validation vẫn có thể dẫn đến FPR test khác nhau. Chỉ phát biểu bảo đảm population nếu giả định của phương pháp được kiểm tra. [Le & Zhang](https://doi.org/10.1145/3510003.3510155) · [Critical review](https://doi.org/10.1145/3660768) · [PR/ROC](https://doi.org/10.1371/journal.pone.0118432) · [NP-ROC](https://doi.org/10.1126/sciadv.aao1659)

[Reviews từng bài](../reviews/individual_papers/) · [Literature matrix](../reviews/literature_matrix.md) · [Baseline shortlist](BASELINE_SHORTLIST.md)

