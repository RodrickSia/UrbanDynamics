# Báo cáo ghép giá đất theo đoạn đường — 07/10/2026

## Dữ liệu thật

- Bảng giá: 9.502 dòng ứng viên từ PDF đầy đủ; có 1.036 mục bị parser từ chối và giữ để kiểm tra. Việc trích được dòng không xác nhận giá đã được duyệt thủ công.
- SHA256 PDF: `a8e6fee0a6c5698b2937662d71cc858009edf0406c1f2655a4de494f479cfcb6`.
- OSM: 63.459 ways trong phạm vi TP.HCM hợp nhất; 159 polygon phường/xã hợp lệ. Catalog phường OSM có timestamp `2026-10-07T13:50:50Z`.
- [Workflow tải polygon thành công](https://github.com/RodrickSia/UrbanDynamics/actions/runs/37631862612). Tải riêng polygon để dùng lại road cache có sẵn; các lượt cold fetch đường qua Overpass bị quá tải, không ghi đè snapshot cũ.
- Snapshot: **1.848 dòng giá có hình học**, gồm 1.343 TP.HCM cũ, 149 Bình Dương và 356 Bà Rịa–Vũng Tàu.
- **7.654 dòng chờ** có lý do trong `etl/data/review/land_price_pending.json`. Không tự gán giá cho các đường còn thiếu hoặc đầu mút mơ hồ.
- Kiểm tra toàn snapshot: 1.848 định danh duy nhất, hình học LineString/MultiLineString hợp lệ và trong ranh phân tích; 1 đoạn có nhãn partial do cắt theo ranh thành phố.
- 1.847 dòng ghép tự động chưa duyệt thủ công; 1 đoạn đã duyệt cả hình học và giá. Các số lượng này không phải xác nhận độ chính xác pháp lý hoặc độ phủ toàn bộ bảng giá.

## Kiểm thử

| Kiểm tra | Kết quả |
| --- | --- |
| Windows: matcher, PDF, chuyển đơn vị và API | 38 đạt; 1 PostGIS test bỏ qua vì Docker local chưa chạy |
| Frontend Vitest | 80/80 đạt |
| Frontend production build / ESLint | Đạt |
| Chromium + MapLibre thật | 1/1 đạt: vector tile, click chi tiết giá, opacity, đổi nền, tắt lớp |
| API file mode trên snapshot thật | 3 endpoint HTTP 200; 1.848 features / 9.502 rows / metadata 1.848 |
| Linux/PostGIS và Docker | GitHub Actions trên [PR #9](https://github.com/RodrickSia/UrbanDynamics/pull/9) |

Test matcher bao gồm: trùng tên đường ở vùng khác, phường thiếu/trùng, ward level cũ, đầu mút không giao đường, cầu vượt khác layer, đường đứt/rẽ/vòng, làn một chiều song song, polygon có lỗ/vòng không kín, override duyệt thủ công, lỗi nguồn/overlay và cắt ranh thành phố.

Healthcheck PostGIS dùng TCP `127.0.0.1` để không nhận nhầm database tạm lúc khởi tạo là database production đã sẵn sàng.

## UI và triển khai

UI Land price trước đây chưa nối dữ liệu. Đã bật lớp, dùng vector tiles cho vùng đang nhìn, chú giải giá, thông tin ba loại đất và trạng thái duyệt; metadata được kiểm tra mỗi 5 phút. Các lần thêm data tiếp theo không cần sửa UI nếu giữ hợp đồng API.

Dữ liệu/cache không đưa toàn bộ vào Git. Có gói local `.runtime/khoi-land-price-spatial-citywide.tgz` chứa snapshot, roads và cache polygon để nạp offline trên server. Gói không chứa `.env` hoặc credentials và không ghi đè file reviewed hiện có trên server; cung cấp seed reviewed riêng.

Lúc kiểm tra server cuối đợt, repo đã chuyển sang `fix/population-raster-seams` (`2cdf341`) và containers vừa được deploy lại; `.env` cùng cache giá đất trong repo không còn. Cần phối hợp với phiên đang deploy trước khi đổi code/container. Snapshot mới và UI đã được kiểm chứng ở local; báo cáo này chưa xác nhận production đã nhận 1.848 dòng.
