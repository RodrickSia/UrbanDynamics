# Báo cáo local — Khôi, TP.HCM mở rộng

Ngày 07/10/2026. Phạm vi: TP.HCM cũ, Bình Dương, Bà Rịa–Vũng Tàu và Côn Đảo. Hướng dẫn chạy: [khoi-citywide-etl.md](khoi-citywide-etl.md).

**Bản gộp simulation + ETL:** toàn bộ bộ kiểm thử cuối đạt **115/115 trên Windows và Linux**, cùng kiểm tra API/native solver/PostGIS và 9 nhóm browser. Xem [báo cáo bản gộp](integrated-simulation-test-report.md). Các số 112 bên dưới ghi lại lượt kiểm tra ETL trước đó.

## Kiểm thử và dữ liệu thực tế

- Windows Python 3.13 và Linux Python 3.12 Docker: **112/112 đạt trên mỗi môi trường**, gồm PostGIS thật. Sau các sửa đổi cuối, kiểm thử cache/raster **3/3** và nguy cơ/kịch bản mưa **7/7** đạt trên cả hai môi trường. Các bộ nhỏ kiểm tra trực tiếp mã cuối, không phải chạy lại toàn bộ 112 bài.
- Build backend, ETL, ETL service và frontend thành công. SUMO 1.27.1 chạy được trong backend Linux sau bổ sung thư viện runtime. Pipeline giá đất cũng chạy thành công trong Linux.
- ETL thật trong Docker: job forecast công bố 117 ô vào PostGIS; job history đủ 117/117 ô; job land_price công bố một đoạn đã duyệt; scheduler tự chạy job flood_history thành công với 425 bản ghi.
- Ranh giới và hợp của các polygon mưa khớp trong sai số diện tích tọa độ dưới `1e-8`; API bbox Côn Đảo trả bốn ô giao vùng truy vấn.
- API mưa trả 117 ô, 98 ô nguồn dự báo phân biệt; chuỗi theo giờ trả 96 giờ; mưa và nguy cơ có cùng `rain_run_id`.
- PDF giá đất chính thức 1.262 trang, SHA256 `a8e6fee0a6c5698b2937662d71cc858009edf0406c1f2655a4de494f479cfcb6`. 9.502 hàng ứng viên, gồm 5.480/2.581/1.441 hàng theo ba khu vực; 1.036 mục bị loại/đánh dấu cần rà soát. Đã đối chiếu ba trang 234, 561, 1036 bằng ảnh render. Chưa duyệt tất cả hàng giá.
- GFM: xử lý đủ **82 cảnh**, công bố **11.055 polygon** ngập quan sát vào PostGIS; tổng 326.178 pixel ngập trên các quan sát (có lặp không gian giữa các ngày, không phải diện tích ngập duy nhất). API bbox Côn Đảo trả 120 polygon; lọc ngày 06/10 trả 1.247 polygon, không truncated. Truy vấn toàn vùng với limit 10.000 có `truncated=true`, nên frontend cần lọc bbox/ngày.
- Cả năm job scheduler đều đã thành công. Job forecast tự chạy thêm trong lúc xử lý vệ tinh, lần thành công cuối lúc 12:48:33 ngày 07/10 (UTC+7), chứng minh cập nhật mưa hoạt động độc lập với job vệ tinh dài.
- Xử lý vệ tinh lần đầu là bước nặng: job cuối từ 10:46 đến 12:50 (UTC+7). Kiểm tra đọc/ghép đủ 82 kết quả cache trên Linux mất **1,134 giây**, trả đúng 11.055 polygon mà không đọc lại raster. Thời gian này chưa gồm truy vấn STAC, checksum nguồn và ghi PostGIS; không phải thời gian toàn bộ một lượt ETL.

## API đã kiểm tra

Các API ranh giới, mưa, mưa theo giờ, ngập lịch sử, nguy cơ ngập, bảng giá, đoạn giá đã duyệt, vệ tinh mở rộng và trạng thái ETL trả **HTTP 200**. Kết quả API đã cập nhật sau khi vệ tinh công bố: `test-results/khoi-citywide-api.json`, `khoi-citywide-satellite.json`. Smoke sau sửa timeout **PASS**, gồm kịch bản mưa, trang simulation, lưu/mở lại kịch bản building và gợi ý cải thiện: `test-results/khoi-api-smoke-report.json`.

## Các lỗi đã sửa trong đợt kiểm tra

- Lưới reprojection gây sliver ở mép: cắt lại theo ranh giới WGS84 gốc.
- Mưa API ghi thời điểm cuối khoảng: chuyển về đầu khoảng một giờ trước khi tính tổng.
- Lỗi thụt dòng trong module integrated simulation ngăn thu thập test toàn backend.
- Linux SUMO thiếu runtime `libatomic`, X11/Xext/Xrender/OpenGL: bổ sung Docker và CI.
- Khi mở rộng lên 425 điểm và 117 ô, smoke API kịch bản mưa vượt timeout 30 giây. Vector hóa phép chiếu tìm ô gần nhất; dữ liệu thật chạy khoảng 9,92 giây trên Python local và API Docker trả HTTP 200, 425 features trong 18,91 giây. Bản ghi full harness giữ nguyên lỗi timeout ban đầu; kiểm tra API sau sửa lưu riêng để không sửa lịch sử kết quả.
- DNS/mạng mất tạm thời làm tải nguồn và apt thất bại. Dữ liệu đã công bố được giữ; tải lại tận dụng cache. Sửa việc đóng descriptor file tạm trên Windows khi GET lỗi, có kiểm thử giữ nguồn cũ và dọn file tạm.

## Giới hạn cần giữ trên giao diện

- Cảnh báo ngập là heuristic mưa gần điểm từng ngập, không phải xác suất hay độ sâu đã hiệu chỉnh. Ngập lịch sử chưa phủ đều toàn TP; nơi không có ghi nhận không có cơ sở cảnh báo theo quy tắc này.
- ERA5 và dự báo là dữ liệu mô hình, không phải quan trắc cấp đường. Lấy mẫu 10 km không tạo thêm độ phân giải.
- Giá đất đã tải bảng cho cả ba khu vực, nhưng map chỉ công bố một đoạn Trần Não đã duyệt, hình học có nhãn phần được kiểm chứng. Không lấy ứng viên OSM chưa duyệt làm giá đất thật trên map.
- Không có push mới, chạy GitHub Actions mới hoặc deploy máy 156 trong đợt này. `.github/workflows/khoi-checks.yaml` đã bao gồm test mới và thư viện Linux cần thiết; kết quả bên trên là local.

## Bằng chứng local

- `test-results/khoi-local-report.json`: build/pipeline/Windows/Linux thành công; giữ lỗi timeout ở smoke ban đầu để có lịch sử kiểm tra.
- `test-results/khoi-api-smoke-report.json`: smoke API sau sửa, trạng thái `passed`.
- `test-results/khoi-local.xml`, `khoi-linux.xml`: JUnit.
- `test-results/khoi-citywide-api.json`: kiểm tra API và phạm vi thực.
- `data/etl/khoi-service-status.json`: trạng thái job và heartbeat; truy cập tại `http://127.0.0.1:8001/api/v1/etl/status`.
- `data/raw/flood_satellite/catalog-latest.json`: catalog được truy vấn với bbox/thời điểm thực.
- API docs: `http://127.0.0.1:8001/docs`.

Các thư mục dữ liệu, runtime và test-results bị gitignore; không đưa cache hoặc mật khẩu lên Git.
