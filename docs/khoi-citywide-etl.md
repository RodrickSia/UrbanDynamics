# ETL toàn TP.HCM mở rộng — phần Khôi

Cập nhật 07/10/2026. Khôi phụ trách ngập lịch sử, ngập vệ tinh, mưa dự báo/lịch sử, cảnh báo nguy cơ ngập và bảng giá đất.

## Phạm vi và dữ liệu

- Ranh giới: [OCHA/HDX COD Việt Nam](https://data.humdata.org/dataset/cod-ab-vnm), bản nguồn hiện có 34 tỉnh/thành. Polygon TP.HCM đã hợp nhất được kiểm tra bao gồm các điểm đại diện TP.HCM cũ, Bình Dương, Vũng Tàu và Côn Đảo. Đây là ranh giới phân tích; metadata giữ nguồn, giấy phép và checksum, không tuyên bố là hồ sơ địa giới pháp lý.
- Mưa: [Open-Meteo forecast](https://open-meteo.com/en/docs) và [ERA5 historical API](https://open-meteo.com/en/docs/historical-weather-api). 117 ô lấy mẫu, bước 10 km, cắt theo polygon. Bước lấy mẫu không phải độ phân giải thực của mô hình. Metadata lưu cả tọa độ yêu cầu và ô nguồn được API lựa chọn. ERA5 là tái phân tích, không phải trạm đo.
- Ngập lịch sử: [DataSuds/IRD](https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU), 425 bản ghi trong ranh giới mở rộng. Nguồn không phủ đều cả ba khu vực; nơi thiếu ghi nhận chưa thể kết luận không ngập. Kiểm tra giấy phép CC BY-NC trước khi dùng thương mại.
- Ngập vệ tinh: Copernicus GFM, cảnh giao ranh giới trong 30 ngày gần nhất. Lưu raster và exclusion mask; xử lý theo cửa sổ để hạn chế RAM. [Tài liệu sản phẩm](https://extwiki.eodc.eu/GFM/PUM/Products). Vùng bị loại trừ/không quan sát không được coi là khô. STAC quá giới hạn cảnh sẽ báo lỗi, không âm thầm cắt danh sách.
- Giá đất: [Nghị quyết 87/2025/NQ-HĐND](https://congbao.hochiminhcity.gov.vn/cong-bao/van-ban/nghi-quyet/so/87-2025-nq-hdnd/ngay/26-12-2025/48983), [PDF đầy đủ 1.262 trang](https://xdcs.cdnchinhphu.vn/446259493575335936/2026/1/12/87-2025-nq-bang-gia-dat-nam-2026-phat-hanh-signed-1768193916980186481882.pdf), hiệu lực 01/01/2026. Trích 9.502 hàng ứng viên: TP.HCM cũ 5.480, Bình Dương 2.581, Bà Rịa–Vũng Tàu 1.441. 1.036 mục bị từ chối/đánh dấu để rà soát; hỗ trợ bảng đoạn đường có ba cột giá, chưa hỗ trợ mọi loại bảng. Đây là giá nhà nước tham chiếu, không phải giá giao dịch.

Đã tải 63.459 ways OSM, sinh 4.560 ứng viên ghép giá với đường. Ứng viên có thể gồm đường trùng tên ở nơi khác, chỉ để rà soát. Chỉ **một đoạn Trần Não đã được duyệt** được công bố trên map. Không có màu giá cho toàn TP cho đến khi kiểm tra giá và hình học các đoạn còn lại. Ba mẫu giá được đối chiếu trực quan với PDF: Trần Não trang 234; Bạch Đằng/Thủ Dầu Một trang 561; Thùy Vân/Tam Thắng trang 1036.

## Luồng chạy và lịch

`src.khoi_service` chạy liên tục trong một container, có khóa leader bằng PostgreSQL advisory lock (hoặc khóa OS khi chạy bằng file). Mỗi job có trạng thái và không chạy chồng chính nó.

| Job | Chu kỳ mặc định | Công việc |
|---|---:|---|
| forecast | 1 giờ | Batch mưa 117 ô → kiểm tra dữ liệu → công bố lớp mưa → tính lại nguy cơ ngập |
| history | 5 phút khi bootstrap; 1 tuần khi đủ | Tải tối đa 4 ô/lượt, cache từng năm và P90 từng tháng; cập nhật lớp mưa/nguy cơ sau khi có thêm lịch sử |
| flood_history | 1 tuần | Tải nguồn, lọc ranh giới → tính lại nguy cơ |
| satellite | 6 giờ | Tìm cảnh mới trong 30 ngày, tái dùng raster và kết quả xử lý theo checksum nguồn/ranh giới |
| land_price | 30 ngày | Kiểm tra PDF cấu hình, cache parser theo checksum, ghép với các đoạn đã duyệt |

Cập nhật mỗi giờ là tần suất lấy dữ liệu; mô hình nguồn có lịch phát hành riêng. Bảng giá đang trỏ văn bản 2026 cụ thể: khi có văn bản mới phải cập nhật URL, năm hiệu lực và duyệt lại. Không tự phát hiện mọi nghị quyết mới.

Mưa lịch sử mặc định từ 2016 đến năm đầy đủ gần nhất, có thể cố định bằng `RAIN_HISTORY_END_YEAR`. Khi sang năm mới, lịch sử thêm năm đã hoàn tất và tái dùng cache các năm cũ. Dữ liệu thiếu giữ là thiếu, không thay bằng 0; tổng 24 giờ chỉ trả số khi đủ 24 khoảng liên tục.

Nguy cơ ngập hiện là quy tắc sàng lọc: tìm mưa dự báo 3 giờ lớn nhất trong 24 giờ tiếp theo; so với P90 của các cửa sổ mưa 3 giờ lịch sử cùng tháng tại ô mưa gần nhất; đánh dấu quanh điểm từng ngập (250 m). Cần ít nhất 30 cửa sổ mưa. Chưa có xác suất ngập đã hiệu chỉnh, độ sâu, DEM, triều hay mạng thoát nước. Mưa gần đây 24 giờ được công bố để xem bối cảnh, chưa được đưa vào một mô hình thủy lực. Nơi không có điểm lịch sử không có cảnh báo theo quy tắc này.

## Lưu trữ và API cho frontend

- `data/raw/`: GeoPackage, raster, PDF, OSM và cache lịch sử mưa `.npz` theo năm.
- `data/inputs/hcmc_expanded_boundary.geojson`: ranh giới; `inputs/rainwater/runs/<id>/`: cặp dự báo/lịch sử; `rainwater_current.json` trỏ cặp hiện hành để tránh đọc chéo hai lượt.
- `data/layers/*.geojson`: snapshot lớp; `data/review/`: bảng giá và hình học chờ duyệt.
- `data/derived/flood_satellite/`: kết quả xử lý từng cảnh, tự đổi cache khi nguồn hoặc ranh giới đổi. `raw/flood_satellite/catalog-latest.json` giữ truy vấn STAC.
- PostgreSQL + PostGIS: bảng `layer_snapshots`, `layer_features` (geometry EPSG:4326, GiST index). Docker chỉ chạy dịch vụ database; PostGIS là phần mở rộng của PostgreSQL.
- `data/etl/khoi-service-status.json`: heartbeat, trạng thái, lần thành công/lỗi từng job. File snapshot và database không cùng một transaction; dùng metadata `rain_run_id` để đối chiếu các lớp.

| API | Dữ liệu |
|---|---|
| `GET /api/v1/layers/hcmc_boundary/features` | GeoJSON ranh giới |
| `GET /api/v1/weather/rain` | Polygon mưa, tổng 3/24h, P90 và freshness |
| `GET /api/v1/weather/rain/{station_id}` | Chuỗi mưa theo giờ và ngưỡng lịch sử |
| `GET /api/v1/etl/status` | Trạng thái scheduler |
| `GET /api/v1/floods/history` | Điểm ngập lịch sử |
| `GET /api/v1/floods/risk` | Cảnh báo theo quy tắc |
| `GET /api/v1/floods/satellite` | Polygon pixel ngập quan sát |
| `GET /api/v1/land-prices/rows` | Hàng bảng giá ứng viên |
| `GET /api/v1/land-prices` | Đoạn đường giá đã duyệt |

Frontend dùng GeoJSON source/layer của MapLibre, tùy chọn `bbox` để lọc. Lớp vệ tinh giữ nhiều thời điểm: dùng thêm `start`/`end` khi chọn ngày quan sát, không hiển thị toàn bộ 30 ngày như ngập hiện tại. Kiểm tra `metadata.truncated`; khi vượt giới hạn, thu hẹp bbox hoặc khoảng thời gian. Popup cần hiển thị nguồn, thời điểm, nhãn mô hình và coverage. Snapshot mưa hết hạn sau 2 giờ được API đánh dấu stale; lỗi nguồn giữ snapshot cũ và trạng thái lỗi, không tạo dữ liệu giả.

## Chạy local

Đặt `POSTGRES_PASSWORD` trong shell hoặc `.env` riêng (không commit). Từ thư mục repo:

```powershell
.venv/Scripts/python.exe scripts/prepare-hcmc-boundary.py --cached
# Khởi động database và API:
docker compose -p khoi-local -f compose.khoi.yaml up -d --build warehouse backend
# Bootstrap/cập nhật một lượt (các lượt sau tiếp tục cache):
docker compose -p khoi-local -f compose.khoi.yaml --profile etl-service run --rm etl-service python -m src.khoi_service --once --jobs forecast history land_price
# Service cập nhật liên tục:
docker compose -p khoi-local -f compose.khoi.yaml --profile etl-service up -d --build etl-service
# Kiểm thử Windows/Linux, PostGIS và API:
.venv/Scripts/python.exe scripts/test-khoi-local.py --linux-checks
```

Nếu cache ranh giới chưa tồn tại, script tải mạng; cần Python dependencies đã cài. Khi chạy script Python trực tiếp, đặt `PYTHONPATH=etl;backend` trên Windows; các CLI trong `scripts/` có đường dẫn import riêng. `data/` là volume dùng chung, bị gitignore; máy mới tải dữ liệu nguồn, không nhận cache qua Git. Không chạy thêm scheduler dùng cùng volume nhưng thiếu cùng cơ chế khóa database.

Trên máy mới, sau khi đã có bảng giá đầy đủ, chạy `scripts/prepare-land-price-demo.py` để dựng lại đoạn Trần Não được kiểm chứng theo fixture/giá PDF; script tải OSM nếu chưa có cache. Service sẽ công bố đoạn đã duyệt ở lượt giá đất kế tiếp, hoặc chạy lại job `land_price` khi scheduler đang dừng. Khi chưa có geometry đã duyệt, service giữ bảng giá ứng viên và công bố lớp giá rỗng, không tự lấy ứng viên tên đường làm giá trên map.

Các file chính: `etl/src/khoi_service.py`; `etl/src/pipelines/rainwater/{config,grid,extract,transform,load,pipeline}.py`; `etl/src/shared/hcmc_boundary.py`; `backend/app/routers/weather.py`; `compose.khoi.yaml`. Cấu hình ở `.env.example`.

CI kiểm thử offline bằng fixture và PostGIS thật; không crawl toàn bộ nguồn mỗi pull request. Deploy máy 156 cần secrets/runner và quyền truy cập máy đó; không có deploy trong thay đổi này.
