# Research gaps và cổng GO/NO-GO

| Hướng | Câu hỏi | GO | NO-GO |
|---|---|---|---|
| **RQ1 ưu tiên** | Tại cap FPR 1% hiệu chỉnh trên validation, residual host có partial pooling tăng recall trên BGL tương lai so với cùng scorer global hay không? | Có cohort temporal kín, đủ support theo block và host lạnh. Cùng IDs, bỏ nhãn/proxy, CI paired theo block và ít nhất ablation global/host-only/pooled. Chốt trước mức lợi ích thực tế và FPR test tolerance theo application. | Leakage hoặc không đủ positive, hoặc FPR/CI vi phạm tiêu chí đã khóa. Kết quả âm được báo như vậy và vẫn có giá trị thực nghiệm. |
| **RQ2 có điều kiện** | Drift trigger với cập nhật quá khứ có giảm thời gian phục hồi hoặc vi phạm ngân sách sau shift so với fixed calibration? | RQ1 baseline tái lập, có prequential, nhãn đến trễ theo policy cố định, chốt drift measure và bounded state. So trigger on/off cùng scorer. | Không có nhãn đủ để đo drift, update dùng tương lai hoặc chỉ thắng khi chọn lại giai đoạn sau khi xem test. |
| **RQ3 đánh giá khái quát** | Lợi ích của host context còn xuất hiện ở cohort tương lai khác hoặc trên corpus có nhãn và unit tương thích? | Kiểm tra cohort BGL thứ hai chưa mở, sau đó cân nhắc Thunderbird nếu provenance/host/labels map được. HDFS block là phép thử riêng. | Không thể đối chiếu label/unit, khoảng tin cậy quá rộng hoặc cần retune trên cohort test. |

Động cơ đến từ tác động grouping và temporal order trong [Le & Zhang](https://doi.org/10.1145/3510003.3510155) và khác biệt benchmark trong [Landauer et al.](https://doi.org/10.1145/3660768). Không diễn giải thiếu một tổ hợp trong khảo sát này thành bằng chứng chưa từng được đề xuất. [Novelty audit](novelty_audit.md) · [Protocol](../00_research_protocol/PROTOCOL_VI.md)

