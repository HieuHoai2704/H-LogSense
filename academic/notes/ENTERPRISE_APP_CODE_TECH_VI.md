# Ứng dụng tham khảo cho H-logsen

Đối chiếu ngày 07/11/2026 theo giờ Việt Nam. Phạm vi gồm giao diện được hãng mô tả, kiến trúc công bố và các tệp mã công khai đã mở. Các liên kết mã nguồn ghim theo commit đã đọc. Commit tham chiếu có thể đi trước bản cài phát hành. Lượt này nghiên cứu tài liệu và mã, chưa cài hoặc đo hiệu năng của các sản phẩm.

## Bảng so sánh

| Sản phẩm | Người dùng thao tác thế nào | Công nghệ có bằng chứng | Giá trị tham khảo cho H-logsen |
|---|---|---|---|
| **Visual Studio Code · Microsoft** | Chọn thư mục, shell profile và phiên terminal. Shell integration biết lệnh bắt đầu ở đâu, thư mục hiện hành và trạng thái kết thúc ở shell được hỗ trợ. Remote SSH mở được workspace trên máy đích qua VS Code Server. | TypeScript, Electron, xterm.js, `node-pty`, tiến trình PTY host trao đổi qua IPC. [Terminal](https://code.visualstudio.com/docs/terminal/basics) · [Shell integration](https://code.visualstudio.com/docs/terminal/shell-integration) · [Remote SSH](https://code.visualstudio.com/docs/remote/ssh) | Phân biệt phiên terminal, ô hiển thị và kết nối máy. Dùng một phiên cho thao tác tách/gắn lại, có đường phục hồi đầu ra theo con trỏ. |
| **IntelliJ IDEA · JetBrains** | Terminal là một tool window. Cấu hình shell nằm trong Settings. Terminal mới vẫn hỗ trợ luồng nhập và ứng dụng terminal truyền thống, đồng thời trình bày kết quả tích hợp với editor. | IntelliJ Platform. JetBrains mô tả JediTerm là lõi xterm/VT100 của kiến trúc Reworked 2025. Mã plugin công khai có JediTerm và Pty4J trong cấu hình build. [Tài liệu Terminal](https://www.jetbrains.com/help/idea/terminal-emulator.html) · [Kiến trúc terminal](https://blog.jetbrains.com/idea/2025/04/jetbrains-terminal-a-new-architecture/) | Giữ PTY truyền nguyên đầu vào và đầu ra. Thông tin bổ sung về lệnh, project SDK hoặc thời điểm chạy nên nằm ở lớp riêng. |
| **GitHub Desktop · GitHub** | Chọn repository, quay lại repo gần đây rồi thực hiện tác vụ theo repo đang mở. Ứng dụng có trình cài Windows và macOS. | Electron, TypeScript, React và Dugite. Có mã công khai cho tiến trình chính, IPC và kho trạng thái repository. [Sản phẩm](https://desktop.github.com/) · [README nguồn](https://github.com/desktop/desktop/blob/1bfab971ad2d373d5ef996dda2b894232658f8f6/README.md) | Khôi phục dự án gần đây và trạng thái cửa sổ như một phần của startup. Nếu thử app desktop đóng gói, có thể giữ lớp thao tác tệp/terminal tách khỏi giao diện. |
| **Docker Desktop · Docker** | Mở đối tượng đang chạy rồi xem log, thống kê và thao tác dành cho container. Màn Logs hợp nhất nhiều nguồn và có tìm kiếm, lọc, tùy chọn hiển thị. | Tài liệu xác nhận Docker Engine API và tùy chọn backend WSL 2 trên Windows. Mã **Docker CLI** viết bằng Go cho thấy cách gọi Logs và Stats. Lượt này chưa xác minh framework dựng GUI của Docker Desktop. [Containers](https://docs.docker.com/desktop/use-desktop/container/) · [Logs](https://docs.docker.com/desktop/use-desktop/logs/) · [WSL 2](https://docs.docker.com/desktop/features/wsl/) · [Engine API](https://docs.docker.com/reference/api/engine/) | Lấy project/lượt chạy làm đối tượng trung tâm. Gắn log, tài nguyên máy và thao tác với cùng đối tượng. Tách trạng thái “đang theo dõi dòng cuối” khỏi trạng thái “đang xem log cũ”. |
| **TensorBoard · TensorFlow/Google** | Chọn log directory và lượt chạy, xem các chỉ số scalar theo step và so sánh nhiều run. | Event files, backend Python và plugin scalar. Mã có cơ chế giới hạn số điểm giữ trong RAM. RustBoard là một kiến trúc nạp dữ liệu được công bố với tiến trình Rust riêng và gRPC. [Bắt đầu với TensorBoard](https://www.tensorflow.org/tensorboard/get_started) · [Thiết kế RustBoard](https://github.com/tensorflow/tensorboard/blob/f5844be5ee5f9a05309d0e19fe528ff2504f0ab2/docs/design/rustboard.md) | Học cách đọc log metric ngoài tiến trình huấn luyện và cấp số điểm biểu đồ có giới hạn. Tách tệp dữ liệu đầy đủ khỏi tập điểm phục vụ hiển thị. |
| **Weights & Biases · W&B** | SDK tạo run, ghi metric, kết thúc run và hỗ trợ cấu hình offline. Theo dõi tài nguyên máy là một luồng trong vòng đời của run. | Mã công khai gồm SDK Python, lõi Go và mã monitor nhận mẫu từ sidecar `wandb-symon`. Phạm vi mã đã đọc là SDK và các thành phần đi kèm. [Kho W&B](https://github.com/wandb/wandb) · [Cấu hình offline trong SDK](https://github.com/wandb/wandb/blob/7247567e74f8dd2963e4139b33d4f1ac0e71cc1d/wandb/sdk/wandb_settings.py#L400) | Gắn log, loss, tài nguyên và artifact bằng cùng `run_id`. Ghi cục bộ khi chạy, khôi phục chỉ mục và lịch sử sau khi mở lại. |
| **Kibana Discover · Elastic** | Chọn phạm vi dữ liệu/thời gian, truy vấn, xem biểu đồ và bảng, rồi mở chi tiết của một bản ghi. Quyền đọc gắn với dữ liệu người dùng được phép xem. | Elasticsearch, ES|QL trong chế độ tương ứng, plugin Kibana bằng TypeScript và mã client TSX/React. Plugin Discover có phần client và route server riêng. [Explore logs in Discover](https://www.elastic.co/docs/solutions/observability/logs/discover-logs) · [Kiến trúc Discover](https://github.com/elastic/kibana/blob/b0d7bf4a78a08e1131dd3b619214c69be7503360/src/platform/plugins/shared/discover/README.md) | Tách query toàn dataset khỏi tìm kiếm trong đoạn đang mở. Dùng cùng phạm vi cho timeline, bảng, Evidence và CSV. |
| **Nsight Systems · NVIDIA** | Thu một phiên profiling, mở timeline, đặt tên đoạn chạy và đi sâu vào CPU/GPU ở khoảng thời gian cần điều tra. Có CLI xuất dữ liệu đã thu. | `nsys`, dấu mốc/khoảng NVTX và xuất report sang SQLite hoặc định dạng khác theo phiên bản. Mã công khai đã đọc là thư viện đánh dấu NVTX. [Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html) · [NVTX](https://github.com/NVIDIA/NVTX/blob/aeda87dd3a913acce29407b6555ddebff98a9e53/README.md) | Thêm dấu mốc có chủ đích như tải dữ liệu, bắt đầu epoch, lưu checkpoint hoặc lỗi. Giữ mẫu sử dụng GPU định kỳ tách khỏi trace profiler chi tiết. |

## Điểm đọc mã

### Terminal và desktop

1. **VS Code.** `ptyHostMain.ts` tạo `PtyService` và đăng ký kênh IPC. Đọc tiếp `createProcess`, `attachToProcess` trong service. Trong `terminalProcess.ts`, phần xác nhận đã tiêu thụ ký tự làm PTY tạm dừng khi vượt ngưỡng cao và tiếp tục khi hạ xuống ngưỡng thấp. Phần xterm nằm ở phía giao diện. [Khởi tạo PTY host](https://github.com/microsoft/vscode/blob/11820a2e4e1615137d363f44604548c282f0841d/src/vs/platform/terminal/node/ptyHostMain.ts#L87) · [Quản lý phiên](https://github.com/microsoft/vscode/blob/11820a2e4e1615137d363f44604548c282f0841d/src/vs/platform/terminal/node/ptyService.ts#L319) · [Điều tiết đầu ra](https://github.com/microsoft/vscode/blob/11820a2e4e1615137d363f44604548c282f0841d/src/vs/platform/terminal/node/terminalProcess.ts#L611) · [Xterm phía giao diện](https://github.com/microsoft/vscode/blob/11820a2e4e1615137d363f44604548c282f0841d/src/vs/workbench/contrib/terminal/browser/xterm/xtermTerminal.ts#L6)
2. **JetBrains.** `LocalTerminalDirectRunner` là điểm đọc cách tạo tiến trình shell và nối PTY. `JediEmulator.processChar` cho thấy lớp giải mã luồng terminal nằm riêng. Mã runner là điểm đọc backend của plugin, còn cách terminal Reworked dựng qua IDE editor được mô tả trong bài kỹ thuật của hãng. [Runner](https://github.com/JetBrains/intellij-community/blob/c3c7da799e66a6e61846fc1620987d5fc53cd58e/plugins/terminal/src/org/jetbrains/plugins/terminal/LocalTerminalDirectRunner.java#L105) · [Phụ thuộc backend](https://github.com/JetBrains/intellij-community/blob/c3c7da799e66a6e61846fc1620987d5fc53cd58e/plugins/terminal/backend/BUILD.bazel#L34) · [Emulator](https://github.com/JetBrains/jediterm/blob/1b354a63f9845aee3474b0749af0a62e406f0076/core/src/com/jediterm/terminal/emulator/JediEmulator.java#L40)
3. **GitHub Desktop.** `main.ts` là điểm đọc vòng đời cửa sổ và các handler IPC. `app-store.ts` giữ repo đã chọn và danh sách repo gần đây. `git/core.ts` là điểm đọc lớp bọc thực thi Git qua Dugite. Khi cân nhắc đóng gói H-logsen, đọc thêm mô hình main/renderer và cơ chế giao tiếp hẹp của Electron. [Main process](https://github.com/desktop/desktop/blob/1bfab971ad2d373d5ef996dda2b894232658f8f6/app/src/main-process/main.ts#L347) · [Store repo](https://github.com/desktop/desktop/blob/1bfab971ad2d373d5ef996dda2b894232658f8f6/app/src/lib/stores/app-store.ts#L2382) · [Git execution](https://github.com/desktop/desktop/blob/1bfab971ad2d373d5ef996dda2b894232658f8f6/app/src/lib/git/core.ts) · [Electron process model](https://www.electronjs.org/docs/latest/tutorial/process-model)

### Thu thập và đọc dữ liệu

4. **Docker CLI.** `logs.go` gọi `ContainerLogs` với tuỳ chọn follow. Xem cách CLI phân luồng đầu ra khi cần. `stats.go` điều phối việc thu thống kê theo từng container. Hai tệp này là ví dụ về giao tiếp với Engine từ CLI, còn hành vi màn Docker Desktop có tài liệu riêng. [Logs client](https://github.com/docker/cli/blob/7c0f1b261a24b36ad39b6031db6ffe41e60bc7e7/cli/command/container/logs.go#L62) · [Stats client](https://github.com/docker/cli/blob/7c0f1b261a24b36ad39b6031db6ffe41e60bc7e7/cli/command/container/stats.go#L105)
5. **TensorBoard.** Đọc `EventAccumulator` để thấy cách nạp event, `Reservoir` để thấy cách giới hạn bộ nhớ và `ScalarsPlugin` để thấy truy vấn scalar qua data provider với tham số downsample. Điều này giúp tách giới hạn số điểm hiển thị khỏi giới hạn lưu trữ tệp. [Event accumulator](https://github.com/tensorflow/tensorboard/blob/f5844be5ee5f9a05309d0e19fe528ff2504f0ab2/tensorboard/backend/event_processing/event_accumulator.py#L210) · [Reservoir](https://github.com/tensorflow/tensorboard/blob/f5844be5ee5f9a05309d0e19fe528ff2504f0ab2/tensorboard/backend/event_processing/reservoir.py#L24) · [Scalar provider](https://github.com/tensorflow/tensorboard/blob/f5844be5ee5f9a05309d0e19fe528ff2504f0ab2/tensorboard/plugins/scalar/scalars_plugin.py#L103)
6. **W&B.** `Run.log` và `Run.finish` là giao diện SDK ghi và đóng run. `core/go.mod` xác nhận lõi Go. `monitor.go` mô tả mẫu hệ thống nhận từ sidecar và lựa chọn giới hạn bộ đệm. Có thể học giao thức ghi cục bộ trước khi quyết định cần đồng bộ ra máy khác. [Run.log](https://github.com/wandb/wandb/blob/7247567e74f8dd2963e4139b33d4f1ac0e71cc1d/wandb/sdk/wandb_run.py#L1667) · [Run.finish](https://github.com/wandb/wandb/blob/7247567e74f8dd2963e4139b33d4f1ac0e71cc1d/wandb/sdk/wandb_run.py#L2262) · [Go core](https://github.com/wandb/wandb/blob/7247567e74f8dd2963e4139b33d4f1ac0e71cc1d/core/go.mod) · [Monitor](https://github.com/wandb/wandb/blob/7247567e74f8dd2963e4139b33d4f1ac0e71cc1d/core/internal/monitor/monitor.go#L43)
7. **Kibana.** Mã client đăng ký ứng dụng Discover và server đăng ký các route. Tài liệu trong repo nối khái niệm session/tab, cấu hình phạm vi và luồng đọc dữ liệu với các tệp triển khai. Khi muốn dùng lại code, đối chiếu giấy phép theo thư mục và header của tệp. [Client plugin](https://github.com/elastic/kibana/blob/b0d7bf4a78a08e1131dd3b619214c69be7503360/src/platform/plugins/shared/discover/public/plugin.tsx) · [Server routes](https://github.com/elastic/kibana/blob/b0d7bf4a78a08e1131dd3b619214c69be7503360/src/platform/plugins/shared/discover/server/api/register_routes.ts#L20) · [Giấy phép trong repo](https://github.com/elastic/kibana/blob/b0d7bf4a78a08e1131dd3b619214c69be7503360/LICENSE.txt)
8. **NVIDIA NVTX.** Đọc `nvtxRangePushA` và `nvtxRangePop` để hiểu cách ứng dụng đánh dấu đoạn công việc trên timeline. Ví dụ NVTX giúp H-logsen học mô hình marker. H-logsen có thể dùng marker nội bộ cho epoch/checkpoint và giữ nguồn NVIDIA tùy chọn. [API NVTX](https://github.com/NVIDIA/NVTX/blob/aeda87dd3a913acce29407b6555ddebff98a9e53/c/include/nvtx3/nvToolsExt.h#L1013) · [Ví dụ timeline](https://github.com/NVIDIA/NVTX/blob/aeda87dd3a913acce29407b6555ddebff98a9e53/README.md#L21)

## Đối chiếu với mã H-logsen

| Phần | H-logsen hiện có | Phần đáng thử tiếp | Cách nghiệm thu |
|---|---|---|---|
| **Terminal** | xterm.js, Python, ConPTY qua pywinpty trên Windows và PTY POSIX. Frontend hỏi đầu ra bằng HTTP với vòng chờ 160 ms. Server giữ bộ đệm giới hạn 262.144 ký tự theo cách đếm của Python và trả offset/reset. | Thử kết nối lại dựa trên ID phiên và con trỏ hiện có. Chỉ cân nhắc stream lâu dài và xác nhận tiêu thụ khi đo được nghẽn thật. | Ngắt kết nối khi shell đang in dữ liệu, gắn lại đúng phiên. Nếu con trỏ rơi ngoài bộ đệm, UI báo khoảng thiếu rõ ràng. |
| **Lượt train** | Supervisor chạy nền, history cục bộ, `train.log`, `metrics.csv`, `machine.jsonl`, psutil và `nvidia-smi`. | Chuẩn hóa dữ liệu quanh một `run_id` với định danh máy, step, timestamp, đơn vị và nguồn. Cho chọn hai run và đổi trục step/thời gian. | Khởi động lại app vẫn mở đúng lịch sử. Khi mẫu GPU mất, biểu đồ hiển thị thiếu dữ liệu. Click một mốc mở log tương ứng cùng run. |
| **Phân tích log** | BGL có quyền dataset, Timeline, Evidence và CSV. HDFS theo block chạy bằng CLI với SQLite và CSV riêng. | Tạo bộ đọc kết quả HDFS trong Phân tích. Truy vấn theo block, giữ mốc dòng gốc và hiển thị rõ kiểu đơn vị phân tích. | Bảng, Evidence và CSV phải khớp bộ lọc. Dữ liệu HDFS theo block và BGL theo host-window có nhãn riêng. |
| **Mở app và remote** | Launcher Flask bind loopback, capability cho các thao tác cục bộ, terminal SSH dùng OpenSSH với host key đã xác minh. | So sánh launcher hiện tại với một lớp cửa sổ desktop mỏng. Xác minh SSH thật trên máy Mac trước khi nghiên cứu tác nhân đọc tệp từ xa. | Mở từ shortcut đi thẳng vào workspace. Terminal vẫn dùng đúng quyền người dùng. Thử riêng terminal từ xa và truy cập filesystem từ xa nếu có tác nhân. |

Đối chiếu mã dự án qua [launcher](../../scripts/run/workbench.py), [quyền API cục bộ](../../app/workbench/api.py), [quản lý PTY](../../app/workbench/terminal.py), [frontend terminal](../../app/static/workspace/live-terminal.js), [supervisor](../../app/workbench/jobs.py) và [pipeline HDFS](../../app/services/hdfs_analysis.py).

### Luồng tham khảo do mình tổng hợp

Đây là cấu trúc đề xuất để đánh giá cùng stack hiện tại của H-logsen. Các luồng được tổng hợp từ điểm chung giữa tài liệu và mã ở trên.

```text
Launcher → mở dự án gần nhất → Workspace
                                  │
Terminal UI ↔ dịch vụ phiên ↔ PTY / OpenSSH
                                  │
Train supervisor → log + metric + mẫu máy + marker
                                  │
                           chỉ mục theo run_id
                                  │
                           timeline → Evidence
```

Ví dụ giao kèo cho một điểm metric. Mã minh hoạ đề xuất, chưa đưa vào runtime.

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetricPoint:
    run_id: str
    source_id: str
    sequence: int
    timestamp_utc: datetime
    step: int | None
    name: str
    value: float | None
    unit: str
```

Cặp `(source_id, sequence)` phân biệt các điểm khi nạp lại trong cùng run. `value=None` giữ ý nghĩa thiếu số liệu. Terminal giữ giao kèo luồng ký tự và con trỏ riêng. Log giữ tệp và số dòng để truy ngược Evidence.

## Thứ tự thử nghiệm

1. **Terminal và lịch sử dự án.** Đọc VS Code và GitHub Desktop trước. Kiểm tra mất kết nối, tách/gắn lại và mở lại project gần đây.
2. **Theo dõi train.** Dùng TensorBoard và W&B để thiết kế giao kèo run, dữ liệu mất, so sánh hai run và đánh dấu mốc.
3. **Điều tra.** Học Docker Desktop và Kibana ở thao tác log, bộ lọc, provenance. Dùng HDFS để kiểm tra luồng block → log gốc.
4. **Đóng gói và GPU.** Đo launcher hiện tại trước khi chọn lớp desktop. Xem NVTX/Nsight cho chế độ phân tích GPU chuyên sâu khi có nhu cầu.

