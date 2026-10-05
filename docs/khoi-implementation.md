# Hướng dẫn phần Khôi

## Phạm vi đã viết

| Thư mục | Công việc |
|---|---|
| `etl/src/pipelines/flood_history/` | Tải GeoPackage/TSV DataSuds, chuẩn hóa CRS, ngày và độ sâu, lọc ranh giới Thủ Đức, giữ các quan sát khác nhau dù trùng ID nguồn. |
| `etl/src/pipelines/flood_satellite/` | Tìm STAC GFM, tải raster, cắt vùng, xử lý mask/nodata và chuyển pixel ngập thành polygon. Catalog chỉ mô tả ảnh, không phải vùng ngập. |
| `etl/src/pipelines/flood_risk/` | Ngưỡng P90 mưa 3 giờ cùng tháng, tối thiểu 30 cửa sổ có mưa; đánh giá 24 giờ tới quanh điểm từng ngập. |
| `etl/src/pipelines/land_price/` | Đọc phụ lục giá đất An Khánh, xuất hàng cần duyệt, đổi nghìn đồng sang VND/m², chỉ công bố hình học đoạn đường đã duyệt. |
| `etl/src/shared/` | Download có retry/checksum, kiểm tra không gian, snapshot và giao dịch PostGIS. |
| `backend/app/routers/`, `backend/app/services/` | API lớp dữ liệu, lọc không gian/thời gian và kịch bản mưa. |
| `infra/warehouse/migrations/001_khoi_layers.sql` (tên migration lịch sử; không đổi sau khi đã áp dụng) | Migration cho bảng snapshot, feature và chỉ mục không gian trong kho PostGIS dùng chung. |
| `scripts/` | Chuẩn bị dữ liệu thật, lấy ứng viên đường OSM và chạy kiểm thử local. |

Đây là cảnh báo theo quy tắc có bằng chứng, không phải mô hình học máy dự đoán độ sâu hoặc ranh giới ngập. Dữ liệu vector được lưu trong hai bảng dùng chung `public.layer_snapshots` và `public.layer_features`; population raster vẫn ở `population.population_raster`.

## Chạy local trên Windows

Python và Docker Desktop đã được thêm vào User PATH. Mở terminal mới và bật Docker Desktop trước khi chạy:

```powershell
python -m venv .venv
& .venv/Scripts/python.exe -m pip install -r requirements-dev.txt
$warehousePasswordInput = Read-Host 'Nhap mat khau database local' -AsSecureString
$env:WAREHOUSE_PASSWORD = [System.Net.NetworkCredential]::new('', $warehousePasswordInput).Password
& .venv/Scripts/python.exe scripts/test-khoi-local.py
```

Script kiểm thử tự dựng stack tạm, chạy migrations hai lần, test ETL/API trong mạng Compose rồi xóa volume thử nghiệm. Nó không tải nguồn dữ liệu trực tiếp.

Để chuẩn bị ranh giới và dữ liệu mưa trong thư mục dùng chung `etl/data/`:

```powershell
$env:DATA_DIR = 'etl/data'
& .venv/Scripts/python.exe scripts/prepare-khoi-data.py all
```

Script dùng project cô lập `khoi-local` từ `compose.yaml`, cùng PostGIS 17 và migration của kho chính. Database và backend không publish port lên host; bài kiểm tra kết nối qua mạng Compose. Không có password mặc định: đặt `WAREHOUSE_PASSWORD` trong môi trường. Lệnh phía trên nhập ẩn password trên PowerShell. Đổi biến môi trường không tự đổi password của database trong volume đã tồn tại. ETL dùng `etl/data/`; log và kết quả ở `test-results/`; các thư mục này không được commit.

Tạo ứng viên hình học đường giá đất từ OSM (cần chạy pipeline để tạo `land_price_rows.json` trước):

```powershell
& .venv/Scripts/python.exe scripts/prepare-land-road-review.py
```

Các pipeline dùng cấu hình `WAREHOUSE_*` của Compose. Database phải được khởi động và migrations đã áp dụng:

```powershell
docker compose --profile etl-flood-history run --rm etl-flood-history run --stage all --boundary /app/data/inputs/thu_duc_boundary.geojson
docker compose --profile etl-flood-risk run --rm etl-flood-risk run --stage all
docker compose --profile etl-flood-satellite run --rm etl-flood-satellite run --stage all --boundary /app/data/inputs/thu_duc_boundary.geojson --limit 1
docker compose --profile etl-land-price run --rm etl-land-price run --stage all --segments /app/data/review/land_price_reviewed.geojson
```

Mọi ETL service kết nối tới `postgis:5432` trong mạng Compose. Khi chạy local mà chưa cấu hình `WAREHOUSE_PASSWORD`, pipeline lưu snapshot GeoJSON trong `etl/data/layers/` để kiểm tra ngoại tuyến.

## Đầu vào mưa cho flood-risk

Hai tệp `etl/data/inputs/rainfall_forecast.json` và `rainfall_history.json` có `source_url`, `stations`; dự báo có thêm `issued_at`. Mỗi station gồm `id`, `longitude`, `latitude`, `hourly: [{time, precipitation_mm}]`. Thời gian ISO 8601 phải có múi giờ; station ID phải khớp giữa lịch sử và dự báo. Chỉ dùng lịch sử trước thời điểm phát hành dự báo.

Mẫu local hiện chỉ có một điểm lưới Open-Meteo và lịch sử 2016–2025. Đầu vào hiện là một điểm lưới và chưa đủ để đại diện toàn Thủ Đức. API trả khoảng cách đến station, nguồn, ngưỡng và `stale` khi dự báo hết hạn.

## API cho frontend

Backend chỉ truy cập qua mạng Compose; giao diện gọi API cùng origin qua frontend proxy tại `/api/`.

| Endpoint | Nội dung |
|---|---|
| `GET /health`, `GET /ready` | Tiến trình và kết nối kho dữ liệu |
| `GET /api/v1/layers` | Các lớp đã nạp và metadata |
| `GET /api/v1/floods/history` | Điểm ngập; hỗ trợ `bbox`, `start`, `end`, `limit` |
| `GET /api/v1/floods/satellite` | Polygon pixel ngập dương tính |
| `GET /api/v1/floods/risk` | Vùng lân cận điểm từng ngập và căn cứ cảnh báo |
| `GET /api/v1/land-prices` | Đoạn đường đã kiểm chứng cùng ba loại giá |
| `GET /api/v1/land-prices/rows` | Các hàng trích PDF; vẫn có cờ cần duyệt |
| `POST /api/v1/scenarios/rain` | JSON `{"rain_3h_mm":60}`; hỗ trợ `radius_m`, `polygon` |

`bbox` dùng `west,south,east,north` WGS84. Kết quả GeoJSON có metadata và cờ truncated. Hết hạn phải hiển thị dữ liệu cũ. Vùng đệm 250 m là phạm vi tìm kiếm, không phải vùng nước ngập. Kịch bản không thay đổi snapshot dự báo.

## Duyệt giá đất

1. Đối chiếu từng hàng trong `etl/data/review/land_price_rows.json` với trang PDF gốc. Parser hiện hỗ trợ An Khánh, có lỗi tiềm tàng ở tên đường xuống dòng và mép trang.
2. Kiểm tra ứng viên `etl/data/review/land_price_candidates.geojson` bằng OSM và hai đầu đoạn ghi trong phụ lục; cắt đúng đoạn, loại nhánh và đường trùng tên.
3. Lưu FeatureCollection ở `etl/data/review/land_price_reviewed.geojson`; mỗi LineString/MultiLineString có `price_record_id`, `reviewed: true`, `price_values_reviewed: true` sau khi đã kiểm chứng cả giá và hình học. Nên ghi người duyệt, nguồn và ngày duyệt.
4. Chạy `docker compose --profile etl-land-price run --rm etl-land-price run --stage all --segments /app/data/review/land_price_reviewed.geojson`. Hàng chưa ghép nằm trong `land_price_pending.json`.

Parser đã chuyển sang đọc đường kẻ của bảng scan, hỗ trợ hàng qua trang và “trọn đường”. Bản nguồn hiện tạo **195 hàng ứng viên**, vẫn phải duyệt OCR; **118** hàng có ứng viên OSM.

Repo có mẫu nhỏ `docs/samples/land-price-tran-nao-reviewed.geojson`: hai phần carriageway OSM nằm bên trong một khoảng giá Trần Não, xuất thành **một feature**. Giá đã đối chiếu trang PDF 36 (trang in 37): đất ở 152.900, thương mại 91.700, sản xuất 76.500 nghìn đồng/m². `geometry_coverage=partial_published_segment` phải hiển thị trong popup; mẫu không phủ toàn bộ khoảng giá và không tính là 25 đoạn hoàn chỉnh.

Để tái tạo demo trên máy khác, sau khi đã chạy pipeline giá đất:

```powershell
& .venv/Scripts/python.exe scripts/prepare-land-road-review.py
& .venv/Scripts/python.exe scripts/prepare-land-price-demo.py
& .venv/Scripts/python.exe scripts/test-khoi-local.py
```

Script demo kiểm tra giá và tọa độ OSM so với mẫu đã duyệt; nguồn thay đổi sẽ yêu cầu duyệt lại. Nếu đã có OSM trong cache, dùng `prepare-land-road-review.py --cached`. Dữ liệu mẫu trong repo có attribution OSM/ODbL; dữ liệu gốc lớn vẫn nằm trong `etl/data/` và không commit.

Giá này là bảng giá Nhà nước hiệu lực năm 2026, không phải giá giao dịch thị trường. Chưa đạt mục tiêu 25 đoạn đã duyệt của kế hoạch.

## Nguồn và vận hành

- [DataSuds: ngập TP.HCM](https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU): CC BY-NC 4.0; giữ attribution và điều kiện sử dụng.
- [GFM STAC](https://stac.eodc.eu/api/v1/collections/GFM/items), [hướng dẫn sản phẩm](https://extwiki.eodc.eu/GFM/PUM/Products): ensemble đã được nhà cung cấp áp dụng mask; khi không tải được exclusion mask riêng, số pixel không đánh giá được vẫn là unknown.
- [Phụ lục Nghị quyết 87/2025/NQ-HĐND](https://congbao.hochiminhcity.gov.vn/cong-bao/van-ban/nghi-quyet/so/87-2025-nq-hdnd/ngay/26-12-2025/tai-ve/48983?cbid=48993).
- OpenStreetMap qua Overpass: giữ attribution OSM/ODbL khi dùng hình học đường.
- Ranh giới demo: hợp ba quận cũ Thủ Đức, 9, 2 từ bộ dữ liệu nguồn; không phải ranh giới phường hành chính hiện tại.

Workflow `.github/workflows/integration-tests.yaml` sinh password ngẫu nhiên mỗi lần chạy, khởi động image PostGIS và migration chính qua Compose mà không publish port, chạy pytest trong cùng mạng rồi dọn volume kiểm thử. Không cần password CI cố định. Pipeline chạy thủ công qua `.github/workflows/etl.yaml` với lựa chọn pipeline và stage `all` hoặc `extract`; database deployment tiếp tục dùng workflow migration riêng.
