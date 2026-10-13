# Simulation dùng dữ liệu chung — bàn giao backend

Ngày triển khai: 11/10/2026. Model hiện tại `integrated-building-1.4`, library `thu-duc-demo-library-1.3`. Hệ số nhu cầu và API độ nhạy được mô tả trong [bàn giao hệ số](simulation-demand-coefficients.md).
Frontend do thành viên khác tích hợp. Không tạo map mới, không sửa frontend trong phần việc này.
Chưa commit/push, merge main hoặc deploy server. Máy 156 chỉ được đọc qua SSH/API.

## 1. Phần đã triển khai

1. Script đọc API đang chạy trên server: parcels, population, flood history/risk và giá đất theo bbox khu demo.
2. Lấy OSM đường, footprint có tag, đất xanh và cơ sở giáo dục/y tế; bổ sung cửa sổ ESA WorldCover 2021 v200 qua COG, không tải toàn bộ tile.
3. Xuất snapshot bất biến có bbox, thời điểm lấy, nguồn, giấy phép và hash. Snapshot nằm local, không chứa thông tin đăng nhập.
4. Backend chọn snapshot phủ khu đất hoặc snapshot ID được ghim. Không gọi Overpass/Internet trong request predict.
5. Dựng baseline: footprint OSM được cắt theo khu đất, chiều cao/tầng từ tag nếu có; lớp phủ xanh và built-up từ WorldCover. Phần không phân loại vẫn giả định và ghi diện tích thiếu.
6. Đọc dân số WorldPop của nhóm; chỉ chọn năm <= năm hiện tại. Loại bản tương lai khỏi nền hiện tại. Có snapshot thì dùng dân số snapshot, không tự đổi sang dữ liệu warehouse mới.
7. Thay cơ sở dịch vụ mẫu bằng vị trí OSM; tính quãng đường đi bộ theo graph OSM với đoạn nối giả định đến đường. Capacity chưa có thì ghi `unknown`, không gán 750 chỗ cho mỗi trường thực.
8. SUMO nhập topology OSM, hướng đường và tag đường. Lọc xe cơ giới và bbox; thêm cổng nối tới nút đường gần nhất trong 500 m, có nhãn synthetic. Không âm thầm quay về graph 4 nút nếu network thật không routable.
9. Luồng nền được ước lượng từ dân số và thư viện chuyến đi. Nguồn/đích chọn các hướng tiếp cận mạng; trọng số theo khoảng cách nghịch đảo bình phương. Đây là OD prior, **chưa phải Gravity/Radiation được hiệu chỉnh hoặc counts camera**.
10. Baseline, development và recommendations dùng cùng giờ cao điểm của development, snapshot và seed. SUMO trả GeoJSON WGS84 theo cạnh kèm thống kê mô phỏng.
11. Registry nguồn cho tham số điện/nước/runoff/soil/profile/costs. Phân biệt tài liệu phương pháp với nguồn của trị số; không đổi nhãn synthetic thành verified chỉ bằng cách gắn link.
12. Nhận building hiện trạng từ map qua `map_context`, ưu tiên footprint map trước OSM; chiều cao fallback để vẽ không được coi là chiều cao nguồn. Công trình lân cận trong 300 m được giữ cố định khi tính bóng đổ. Xem [hợp đồng API và payload cho frontend](simulation-map-context-handoff.md).

## 2. API để frontend sử dụng

### POST `/api/v1/scenarios/integrated/context`

Preflight, không chạy SUMO/SWMM và không lưu scenario. Nhận cùng payload với predict:

```json
{
  "title": "Phương án chung cư",
  "site": {"type": "Polygon", "coordinates": [[[106.76,10.82],[106.761,10.82],[106.761,10.821],[106.76,10.821],[106.76,10.82]]]},
  "development": {
    "buildings": [{"name":"Block A","use":"residential","footprint":{"type":"Polygon","coordinates":[[[106.7603,10.8203],[106.7607,10.8203],[106.7607,10.8207],[106.7603,10.8207],[106.7603,10.8203]]]},"floors":12,"height_m":36,"units":200,"residents":600}],
    "paved_m2": 5000,
    "permeable_m2": 2000,
    "green_m2": 3000
  },
  "data_mode": "snapshot_required",
  "conditions": {"level":"base","seed":2026,"solar_date":"2026-04-15"}
}
```

Ví dụ trên minh họa schema, **chưa cân bằng diện tích thiết kế**; payload chạy được lấy ở `GET /api/v1/scenarios/integrated/presets` → `default`, giữ toàn bộ diện tích và thêm `data_mode`.

Chọn thửa đất trên map: frontend lấy polygon từ API parcel hiện có và truyền `site`. API này chưa nhận `parcel_id` thay polygon.

Preflight trả:

- `baseline`, `baseline_provenance`: thiết kế nền và phương pháp/giả định.
- `data_inventory.snapshot_id`, `sources`, `bbox`, `captured_at`, `site_parcels`, `coverage`, `baseline_quality`, `warnings`.
- `population_provenance`, `background_population`.
- `services`, `service_provenance`, `roads`, `surrounding_buildings` là geometry nguồn để xem trước. `roads` ở preflight **không phải** mạng SUMO đã biên dịch.
- `traffic_network_kind`, `synthetic_components`, `sha256`.

### POST `/api/v1/scenarios/integrated/predict`

Frontend giữ building plan của người dùng, không gửi baseline 15/15/70 từ preset nếu muốn backend tự lấy nền.
Nếu muốn dùng đúng bộ dữ liệu đã xem preflight: gửi lại `snapshot_id = data_inventory.snapshot_id` và `data_mode = snapshot_required`.
Nếu người dùng có khảo sát hiện trạng: `baseline.design` + `baseline.source` vẫn được ưu tiên, có nhãn user supplied.

Chế độ:

| `data_mode` | Hành vi |
|---|---|
| `auto` mặc định | Chọn snapshot mới nhất phủ site; nếu không có thì dùng warehouse cho dân số/parcels khi được cấu hình, các thành phần chưa có dùng nền tổng hợp có nhãn |
| `snapshot_required` | Phải có snapshot phủ site; thiếu/ngoài vùng trả 422 |
| `synthetic` | Bỏ nền OSM/population snapshot; giữ demo tổng hợp để kiểm thử. Các lớp context hiện có vẫn có thể được đọc |

Frontend phải hiện cảnh báo khi coverage thiếu hoặc baseline chưa survey. Snapshot phủ site không đồng nghĩa đủ footprint/occupancy.

Các phần response để dựng UI:

- `variants.baseline/development.metrics` và `assessment.rows`: so sánh có đơn vị và verdict.
- `variants.*.buildings_map`: footprint thiết kế/nền.
- `variants.*.traffic.network`: GeoJSON theo cạnh SUMO; thuộc tính `simulated.speed` (m/s), `traveltime` (s), `waitingTime/timeLoss` (s, thống kê tích lũy theo cạnh), `occupancy` (%), `entered/left` (xe) nếu có mẫu.
- Thống kê cạnh dùng interval 0–4.200 s, không phải dữ liệu realtime và không phải mỗi xe trên cạnh đều là một completed trip. Thiếu thuộc tính là thiếu mẫu, không tự điền 0.
- `variants.*.traffic.network_provenance`, `background_provenance`, `completed_fraction`, `delay_comparability`.
- Nếu còn xe chưa hoàn thành/chưa xuất phát ở một phương án, verdict delay có thể là `incomplete_trip_bias`: không tô xanh “tốt hơn” theo riêng mean delay.
- `variants.*.drainage.map`: tràn/depth trong nút SWMM; **không phải polygon ngập mặt đường**.
- `variants.*.shadow`: polygon và chuỗi thời gian bóng đổ, không phải nhiệt độ.
- `variants.*.services.map`: vị trí nguồn, capacity unknown, khoảng cách đi bộ nếu routable; không có tuyến trả null.

API lưu/mở lại/recommendations/artifacts giữ nguyên. Recommendation giữ context và giờ so sánh, không fetch lại nguồn.
API vẫn đồng bộ: native OSM SUMO timeout tối đa 120 s/lượt; các solver khác 60 s. Luồng gợi ý chạy nhiều lượt nên có thể vượt proxy 300 s với case nặng. Job API/polling persistent **chưa triển khai**, frontend cần loading/error/retry và nhóm cần nâng phần này trước khi chạy nhiều người.

Lỗi: input/coverage/topology không phù hợp 422; source DB/native/storage không dùng được 503; hai worker đều bận 429. Clients không được truyền URL hay đường dẫn snapshot.

## 3. Chuẩn bị dữ liệu và chạy local

Từ root repo, Python venv có dependency backend và ETL (rasterio chỉ cần khi tải WorldCover):

```powershell
$env:PYTHONPATH = 'backend;etl'
& .venv/Scripts/python.exe scripts/prepare-simulation-background.py --ssh-host 192.168.20.156
& .venv/Scripts/python.exe scripts/test-simulation-background-local.py
```

Script SSH đọc `http://127.0.0.1:51873` trên server; không deploy hay thay database/container. Không cần đưa password DB vào máy local.
Cũng hỗ trợ `--base-url` (HTTP/tunnel), `--site-file` (Polygon/Feature), `--radius-m` 500–1500, `--output-dir`, `--without-osm`, `--without-landcover`.
OSM thất bại thì không publish snapshot đầy đủ; có thể chọn rõ `--without-osm` để bàn giao phần dữ liệu khác. WorldCover lỗi thì công bố thiếu nguồn có nhãn.

Mặc định snapshot ở `data/simulation_snapshots/<SHA256>.json` (gitignored). `SIMULATION_SNAPSHOT_DIR` chọn thư mục khác.
Stack riêng `compose.khoi.yaml` mount `./data:/data:ro` nên dùng `/data/simulation_snapshots`.
Stack chung `compose.yaml` mount `./etl/data:/data:ro`: chuẩn bị với `--output-dir etl/data/simulation_snapshots`, hoặc copy snapshot vào đó. Snapshot mới không tự chuyển tới server khi push code.

Chạy API Windows:

```powershell
$env:PYTHONPATH = 'backend;etl'
$env:SCENARIO_DATA_DIR = '.runtime/background-smoke/runs'
$env:SIMULATION_WORK_DIR = '.runtime/background-smoke/solvers'
& .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

Swagger: `http://127.0.0.1:8003/api/v1/docs`. Demo riêng còn ở `/simulation/integrated` để kiểm tra engine; chưa tích hợp map React.
Muốn site khác tự lấy nền thì phải chuẩn bị snapshot AOI đó hoặc bổ sung pipeline nền citywide; bản này **chưa tự tải OSM toàn thành phố** trong predict.

## 4. Kiểm chứng local và giới hạn dữ liệu

Xem [báo cáo kiểm thử](simulation-background-test-report.md). Dữ liệu thật có nguồn không đồng nghĩa thông số tất cả module đã được hiệu chỉnh.

- Footprint OSM thiếu: tại site pilot hiện không có footprint được mapping. Không kết luận đất trống; `baseline_quality` báo chưa khảo sát, occupancy unknown.
- WorldCover năm 2021, 10 m: built-up không phân biệt mái và sân. Chỉ dùng làm paved proxy sau khi trừ footprint biết; diện tích còn thiếu chia 50% paved/10% permeable/40% green với nhãn giả định.
- Dân số là WorldPop 2026 của kho nhóm, tổng các pixel bbox khoảng 4,5 km²; không phải cư dân trên từng thửa hay đúng buffer tròn. Các nhóm tuổi/công năng/occupancy chưa suy ra tự động.
- Các cơ sở giáo dục/y tế không được xem là capacity thay thế nhau. Combined service-capacity vẫn chỉ là screening giả định, không số chỗ trống thực.
- Luồng xe nền dựa dân số và suất trips; OD, modal split và tín hiệu chưa calibration. Camera counting chưa triển khai.
- Mạng cống, đất/cao độ SWMM, công suất dư điện/nước, chi phí và mục tiêu vẫn tổng hợp. Tài liệu QCVN/DOE/EPA/SUMO chỉ là reference phương pháp; numeric defaults chưa được xác nhận theo nguồn địa phương.
- Không gọi node overflow là flood depth 2D, bóng đổ là nhiệt độ, giá tham chiếu là giá thị trường hoặc kết quả targets_met là phê duyệt quy hoạch.

## 5. Code phụ trách

- `integrated/background.py`: chọn/kiểm tra snapshot, baseline và dữ liệu chung.
- `integrated/landcover.py`: tải cửa sổ COG khi chuẩn bị snapshot.
- `integrated/road_network.py`: OSM→SUMO, OD prior, graph đi bộ.
- `integrated/context.py`, `solvers.py`, `engine.py`: nối dữ liệu, chạy engine, giờ chung và attribution.
- `integrated/models.py`, router `integrated_scenarios.py`: hợp đồng API và preflight.
- `integrated/library.py`: registry tham số và trạng thái numeric nguồn.
- `scripts/prepare-simulation-background.py`, `scripts/test-simulation-background-local.py`: acquisition/smoke.
- `backend/tests/test_simulation_background.py`: integrity, phạm vi, dữ liệu tương lai, nhãn thiếu, API và native OSM.
