# Kiểm tra toàn văn và dữ liệu của các paper LogSense AI

Cập nhật 06/11/2026. Đối chiếu 34 mục trong registry và ưu tiên các corpus log tác giả trực tiếp dùng, dữ liệu chuẩn đi kèm và các gói tái lập có nội dung dữ liệu. Một corpus có thể có nhiều bản phát hành. Các bài tổng quan và phương pháp nền còn dẫn tới dữ liệu ngoài log như ảnh, tài chính và sinh học. Đợt này tải những bộ kiểm chứng liên quan trực tiếp và một số bộ chuẩn dùng trong bài gốc của các thuật toán. Phạm vi này không bao quát mọi dữ liệu ngoài log mà các paper hoặc tài liệu tham khảo của chúng đề cập. [Registry paper](../literature/metadata/paper_registry.csv)

## Tài liệu

Có 28 PDF cục bộ và 30 bài đã đối chiếu toàn văn. PDF Qi Xin S34 lấy từ endpoint của nhà xuất bản. S16 và S33 có bản đọc toàn văn trên web. Bốn bài còn thiếu toàn văn là S29 Page, S30 Wei et al., S31 LogOnline và S32 LogFlash. Riêng S31, README chính thức xác nhận tác giả dùng HDFS và BGL. [Audit paper](../literature/metadata/audit_summary.json) · [Qi Xin, PDF nhà xuất bản](https://ejournals.itda.ac.id/index.php/avitec/article/download/3974/pdf) · [Kho LogOnline](https://github.com/xUhEngwAng/LogOnline#dataset-preparation-and-dependencies)

## Tệp đã xác minh

Đã xác minh **58 tệp dữ liệu hoặc artifact**, gồm **50 tệp tải thêm** so với kho ban đầu, tổng **11,556 GB**. Kho Loghub v8 có **19/19 archive**.

Tệp nằm tại [data/raw](../../data/raw/). Manifest ghi bản phát hành hoặc nguồn, kích thước byte, SHA-256 và phạm vi kiểm tra. MD5 được đối chiếu khi nguồn cung cấp. Với nguồn CFDR dùng HTTP theo hướng dẫn của tác giả, SHA-256 là dấu vân tay của bản cục bộ và không có checksum từ nhà cung cấp để so. Dataset, biến thể và gói artifact được đếm theo tệp, vì vậy số tệp không tương ứng với số corpus độc lập. [Manifest](paper_dataset_artifacts.json) · [Nguồn CFDR](https://www.usenix.org/cfdr-data) · [Hướng dẫn tái lập S02](https://github.com/ait-aecid/anomaly-detection-log-datasets)

| Tệp | Dung lượng MB | Nguồn |
|---|---:|---|
| ADFA-LD.zip | 2,381 | [Nguồn](https://github.com/verazuo/a-labelled-version-of-the-ADFA-LD-dataset) |
| Android_v1.zip | 24,858 | [Nguồn](https://zenodo.org/records/8196385) |
| Android_v2.zip | 444,986 | [Nguồn](https://zenodo.org/records/8196385) |
| Apache.tar.gz | 0,263 | [Nguồn](https://zenodo.org/records/8196385) |
| BGL-CFDR.gz | 62,936 | [Nguồn](https://www.usenix.org/cfdr-data) |
| BGL-Loghub-3227177.tar.gz | 62,937 | [Nguồn](https://zenodo.org/records/3227177) |
| BGL.zip | 57,489 | [Nguồn](https://zenodo.org/records/8196385) |
| BGL_2k.log | 0,317 | [Nguồn](https://github.com/logpai/loghub/tree/master/BGL) |
| Electricity-OpenML-151.arff | 3,092 | [Nguồn](https://www.openml.org/d/151) |
| F-dataset-source-f16a73f.zip | 822,785 | [Nguồn](https://github.com/dessertlab/Fault-Injection-Dataset) |
| hades_data.zip | 417,537 | [Nguồn](https://zenodo.org/records/7609780) |
| Hadoop-Loghub-3227177.tar.gz | 2,565 | [Nguồn](https://zenodo.org/records/3227177) |
| Hadoop.zip | 3,416 | [Nguồn](https://zenodo.org/records/8196385) |
| HDFS_v1-Loghub-3227177.tar.gz | 161,886 | [Nguồn](https://zenodo.org/records/3227177) |
| HDFS_v1.zip | 186,646 | [Nguồn](https://zenodo.org/records/8196385) |
| HDFS_v2.zip | 823,701 | [Nguồn](https://zenodo.org/records/8196385) |
| HDFS_v3_TraceBench.zip | 567,419 | [Nguồn](https://zenodo.org/records/8196385) |
| HealthApp.tar.gz | 2,297 | [Nguồn](https://zenodo.org/records/8196385) |
| HPC.zip | 2,976 | [Nguồn](https://zenodo.org/records/8196385) |
| KDDCup99-full.gz | 18,116 | [Nguồn](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.fetch_kddcup99.html) |
| LADEmpStudy.zip | 43,263 | [Nguồn](https://figshare.com/articles/software/LADEmpStudy/22756871) |
| Liberty-CFDR.gz | 672,363 | [Nguồn](https://www.usenix.org/cfdr-data) |
| Linux.tar.gz | 0,232 | [Nguồn](https://zenodo.org/records/8196385) |
| Mac.tar.gz | 1,489 | [Nguồn](https://zenodo.org/records/8196385) |
| OpenStack-Kalaki.zip | 2,433 | [Nguồn](https://github.com/ParisaKalaki/openstack-logs) |
| OpenStack.tar.gz | 5,395 | [Nguồn](https://zenodo.org/records/8196385) |
| PimaDiabetes-OpenML-37.arff | 0,037 | [Nguồn](https://www.openml.org/d/37) |
| Proxifier.tar.gz | 0,172 | [Nguồn](https://zenodo.org/records/8196385) |
| S02-author-splits.zip | 121,576 | [Nguồn](https://github.com/ait-aecid/anomaly-detection-log-datasets) |
| S25-predictiondata.tar.bz2 | 1,631 | [Nguồn](https://doi.org/10.6084/m9.figshare.1245061) |
| S25-testdata.tar.bz2 | 218,139 | [Nguồn](https://doi.org/10.6084/m9.figshare.1245061) |
| Spark.tar.gz | 183,475 | [Nguồn](https://zenodo.org/records/8196385) |
| Spirit-CFDR.gz | 905,546 | [Nguồn](https://www.usenix.org/cfdr-data) |
| SSH.tar.gz | 4,597 | [Nguồn](https://zenodo.org/records/8196385) |
| Thunderbird-CFDR.gz | 2026,878 | [Nguồn](https://www.usenix.org/cfdr-data) |
| Thunderbird.tar.gz | 2016,100 | [Nguồn](https://zenodo.org/records/8196385) |
| UCI-Arrhythmia.zip | 0,099 | [Nguồn](https://archive.ics.uci.edu/dataset/5/arrhythmia) |
| UCI-BreastCancerWisconsin.zip | 0,087 | [Nguồn](https://archive.ics.uci.edu/dataset/15/breast+cancer+wisconsin+original) |
| UCI-Congressional-Votes.zip | 0,004 | [Nguồn](https://archive.ics.uci.edu/dataset/105/congressional+voting+records) |
| UCI-Covertype.zip | 11,251 | [Nguồn](https://archive.ics.uci.edu/dataset/31/covertype) |
| UCI-Deterding-Vowel.zip | 0,069 | [Nguồn](https://archive.ics.uci.edu/dataset/152/connectionist+bench+vowel+recognition+deterding+data) |
| UCI-Ecoli.zip | 0,006 | [Nguồn](https://archive.ics.uci.edu/dataset/39/ecoli) |
| UCI-German-Credit.zip | 0,030 | [Nguồn](https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data) |
| UCI-Glass.zip | 0,006 | [Nguồn](https://archive.ics.uci.edu/dataset/42/glass+identification) |
| UCI-Image-Segmentation.zip | 0,111 | [Nguồn](https://archive.ics.uci.edu/dataset/50/image+segmentation) |
| UCI-Ionosphere.zip | 0,030 | [Nguồn](https://archive.ics.uci.edu/dataset/52/ionosphere) |
| UCI-KDD-Cup-1999.zip | 0,007 | [Nguồn](https://archive.ics.uci.edu/dataset/130/kdd+cup+1999+data) |
| UCI-Letter-Recognition.zip | 0,387 | [Nguồn](https://archive.ics.uci.edu/dataset/59/letter+recognition) |
| UCI-Liver-Disorders.zip | 0,006 | [Nguồn](https://archive.ics.uci.edu/dataset/60/liver+disorders) |
| UCI-Sonar.zip | 0,065 | [Nguồn](https://archive.ics.uci.edu/dataset/151/connectionist+bench+sonar+mines+vs+rocks) |
| UCI-Soybean-Large.zip | 0,023 | [Nguồn](https://archive.ics.uci.edu/dataset/90/soybean+large) |
| UCI-Statlog-Landsat.zip | 0,103 | [Nguồn](https://archive.ics.uci.edu/dataset/146/statlog+landsat+satellite) |
| UCI-Statlog-Shuttle.zip | 0,430 | [Nguồn](https://archive.ics.uci.edu/dataset/148/statlog+shuttle) |
| UCI-Statlog-Vehicle.zip | 0,026 | [Nguồn](https://archive.ics.uci.edu/dataset/149/statlog+vehicle+silhouettes) |
| UCI-Thyroid-Disease.zip | 0,625 | [Nguồn](https://archive.ics.uci.edu/dataset/102/thyroid+disease) |
| UCI-Waveform-v1.zip | 0,509 | [Nguồn](https://archive.ics.uci.edu/dataset/107/waveform+database+generator+version+1) |
| Windows.tar.gz | 1670,099 | [Nguồn](https://zenodo.org/records/8196385) |
| Zookeeper.tar.gz | 0,460 | [Nguồn](https://zenodo.org/records/8196385) |

Bốn archive CFDR được giải nén theo luồng đến cuối để kiểm tra CRC và đếm dòng. BGL có 4.747.963 dòng, Thunderbird 211.212.192, Spirit 272.298.969 và Liberty 265.569.231. Các số khớp Bảng 2 của Oliner và Stearley. BGL CFDR và BGL Loghub có cùng số dòng nhưng dữ liệu giải nén khác kích thước byte. [Oliner & Stearley](https://doi.org/10.1109/DSN.2007.103) · [Tham chiếu các bản BGL của Landauer](https://github.com/ait-aecid/anomaly-detection-log-datasets#bgl)

LADEmpStudy dẫn bản Loghub cũ Zenodo 3227177. Manifest ghi riêng các archive BGL, Hadoop và HDFS của bản này khi đã xác minh. Thunderbird trong hai bản Zenodo có cùng kích thước byte và MD5 của nhà cung cấp, nên dùng một tệp. [Loghub 3227177](https://zenodo.org/records/3227177) · [Loghub v8](https://zenodo.org/records/8196385)

UCI-KDD-Cup-1999.zip chứa mô tả và các tệp trỏ tới dữ liệu. Payload đầy đủ nằm riêng trong KDDCup99-full.gz và khớp SHA-256 công bố trong mã scikit-learn. [Nguồn SHA-256](https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/datasets/_kddcup99.py)

## Đối chiếu theo paper

| Paper | Bộ dữ liệu và lưu ý về bản phát hành |
|---|---|
| S01, S18 | Survey. Kho ghi nhận các tập được paper dẫn làm ví dụ, không mở rộng sang toàn bộ tập dữ liệu của các nghiên cứu được dẫn. |
| S02 | HDFS, BGL, Thunderbird, OpenStack, Hadoop, ADFA-LD. Có gói tác giả với các split đã tiền xử lý. HDFS gốc của Xu cần tra riêng, HDFS_v1 và split tác giả được phân biệt. [Gói tác giả](https://github.com/ait-aecid/anomaly-detection-log-datasets) |
| S03, S26 | HDFS, BGL, Spirit. S03 còn dùng Thunderbird. Giữ archive gốc riêng với các chuỗi trích ra để đánh giá. |
| S04 | HDFS, Hadoop, BGL, Thunderbird, Spirit, Hades và F-dataset. Có gói LADEmpStudy. Archive Hades chứa CSV nhãn đã qua Drain. Nguồn F-dataset gốc của Cotroneo có trong manifest, tệp F-dataset_formatted_messages.json mà tác giả chỉ dẫn chuẩn bị tại chỗ chưa có. [Paper và artifact](https://link.springer.com/article/10.1007/s10664-025-10669-3) · [F-dataset gốc](https://github.com/dessertlab/Fault-Injection-Dataset) |
| S05, S13 | HDFS, BGL, Thunderbird. Thunderbird trong từng bài có thể là đoạn lấy mẫu riêng từ archive. |
| S06, S11, S12, S15, S31 | HDFS và BGL có tại kho. Các tập train/test hoặc phiên xử lý của từng paper vẫn cần dựng theo protocol riêng. |
| S07 | HDFS_v1 là bản Loghub. URL archive demo gốc của Xu trả 404 khi kiểm tra. Chưa tìm thấy bản công khai của log Darkstar đúng thí nghiệm. [Trang dữ liệu Xu](https://people.iiis.tsinghua.edu.cn/~weixu/sospdata.html) |
| S08, S09, S17, S22 | Dataset ngoài log hỗ trợ nghiên cứu thuật toán. Manifest ghi các bản công khai đã tải, gồm một số tập UCI, KDD Cup 99 và Electricity. Các bộ biến đổi theo lớp, split lịch sử và dữ liệu sinh trong thí nghiệm phải tái lập theo paper. |
| S10 | Có HDFS_v1 và OpenStack Loghub. Phiên bản OpenStack nguyên thủy của DeepLog không còn được tác giả S02 cung cấp. Nguồn VAST 2011 MC2 có trang nhiệm vụ và đáp án, chưa tải được archive dữ liệu thô từ hai cổng lưu trữ thử. [VAST MC2](https://vast.cs.umass.edu/VAST%20Challenge%202011/challenges/MC2%20-%20Computer%20Networking%20Operations/) |
| S14 | Có HDFS_v1. Các biến thể log bất ổn được dựng theo mô tả paper. Dữ liệu sản xuất Microsoft chưa tìm thấy bản công khai. [LogRobust](https://doi.org/10.1145/3338906.3338931) |
| S16 | Nguồn CFDR mô tả BGL, Thunderbird, Spirit, Liberty, Red Storm. Trang nguồn có link của bốn bộ đầu. Red Storm không có link tải trên trang này. [USENIX CFDR](https://www.usenix.org/cfdr-data) |
| S19, S20, S21 | Bài nền về hiệu chỉnh ngưỡng và đánh giá. Các thí nghiệm ngoài log gồm chuỗi giá, mô phỏng và tác vụ dự đoán chung. Chưa thu thập đầy đủ nhóm này. |
| S23 | Danh mục Loghub, kiểm kê theo từng tệp trong bản Zenodo v8. [Loghub v8](https://zenodo.org/records/8196385) |
| S24 | BGL, HPC, HDFS, Zookeeper và Proxifier có bản trong Loghub. |
| S25 | Gói dữ liệu và dự đoán T1/T2 của bài đánh giá precision-recall được kiểm tra từ Figshare. Xem trạng thái từng file trong manifest. [Figshare](https://doi.org/10.6084/m9.figshare.1245061) |
| S27 | Forum, Halo, Novel. Kho UnseenLog có mã, hướng dữ liệu của SLAD trỏ Drive trả 404. Chưa xác minh nguồn tải thay thế. [UnseenLog](https://github.com/ZhuoxingZhang/UnseenLog) · [SLAD](https://github.com/ZhuoxingZhang/SLAD) |
| S28, S29 | Bài nền về biểu đồ kiểm soát và phát hiện thay đổi. Chưa xác định archive dữ liệu riêng cần tải. |
| S30 | Wiley ghi dữ liệu nghiên cứu Ray không được chia sẻ. [Tuyên bố dữ liệu](https://onlinelibrary.wiley.com/doi/abs/10.1002/smr.2650) |
| S32 | Chưa xác minh chính xác dataset và phiên bản do chưa có toàn văn. [LogFlash](https://doi.org/10.1109/ISSRE52982.2021.00021) |
| S33 | BGL, HDFS và Thunderbird. Thunderbird-sshd là tập con do tác giả lọc theo node và dịch vụ. [TeleDAL, §4](https://link.springer.com/article/10.1007/s11227-023-05379-w) |
| S34 | Có BGL_2k đủ 2.000 dòng từ Loghub, HDFS_v1 và OpenStack. Cần dựng lại cửa sổ và chuỗi theo quy trình của paper để tái lập điểm số. [Qi Xin](https://ejournals.itda.ac.id/index.php/avitec/article/download/3974/pdf) |

Lần này xác minh file trên đĩa. Trạng thái import, chạy detector và đánh giá của từng tập cần bằng chứng riêng.
