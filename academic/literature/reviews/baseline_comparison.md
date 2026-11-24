# So sánh baseline

[Bảng shortlist tám ứng viên](../reports/BASELINE_SHORTLIST.md) là bảng chính cho input, unit, supervision, compute, leakage và tiêu chí nghiệm thu.

Số đo nội bộ có thể đối chiếu hiện tại thuộc [July holdout](../../../docs/ml/IF_JULY_HOLDOUT.md). Ở cùng cohort, Rule cũ có recall 3,80% và FPR 1,72%; IF cũ recall 100% và FPR 58,81%; IF đã chọn recall 55,43% và FPR 0,204%. Chính sách huấn luyện và ngưỡng khác nhau, nên bảng đó giúp xác định vấn đề nhưng chưa trả lời câu hỏi matched FPR. Chỉ dùng các số này làm lịch sử. Với nghiên cứu mới, rule, IF và LR phải hiệu chỉnh trên cùng cap, rồi đo FPR thực trên holdout tương lai.

Các benchmark paper sau đây dùng đơn vị/protocol khác. BGL time-window của S02, S03, fixed log-count của S26 và sequence của S12/S13 không so trực tiếp với host-window 300 giây của khóa luận. Dùng [literature matrix](literature_matrix.md) để xác định dòng nào đủ điều kiện đối chiếu.

