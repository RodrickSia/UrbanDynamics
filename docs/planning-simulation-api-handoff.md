# Bàn giao API demo nhiều khu đất và tác động cộng dồn

Cập nhật 11/10/2026. Backend local, dữ liệu synthetic; demo đã nghiệm thu
theo [audit cuối](planning-demo-final-audit.md). Frontend map của nhóm dùng API
này; trang `/simulation/planning` là preview độc lập để kiểm tra backend.
[Runbook](planning-demo-local-runbook.md) có cách dựng Docker và review cases.

**Cập nhật 12/10 — model 0.15:** [adapter parcel và snapshot hệ thống](planning-system-demo-connection.md)
đã thêm cho demo kiểm thử. Bật bằng environment gate ở API và worker;
frontend chính chưa bị thay đổi. Parcel thật và nền có nguồn được phân biệt
với mạng SUMO/SWMM tổng hợp và capacity chưa biết.

## Chạy local

**Bản đang phục vụ:** `http://127.0.0.1:8007/simulation/planning`, image
`planning-demo-backend:local`, API `planning-program-api`, worker
`planning-program-worker`, volume `planning-program-runtime`. Dùng bản này
để mở các job ID trong báo cáo; không khởi tạo lại store hoặc chạy worker
one-shot vào store khác. Các lệnh Windows dưới đây là cách dựng instance
riêng khi cần; cổng/store ví dụ cũ không phải instance Docker 8007.

Từ root repo, dùng cùng biến môi trường trong cả hai terminal PowerShell:

```powershell
$env:PYTHONPATH='backend;etl'
$env:PLANNING_SQLITE_PATH="$PWD/.runtime/planning-demo-expanded/studies.sqlite"
$env:SIMULATION_WORK_DIR="$PWD/.runtime/planning-demo-expanded/solvers"
```

Terminal API:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8005
```

Terminal worker:

```powershell
.venv/Scripts/python.exe scripts/planning-worker.py
```

Mở `http://127.0.0.1:8005/simulation/planning`. Không chạy thêm API/worker nếu
đã có tiến trình đang phục vụ demo trên cùng store. PostgreSQL dùng cấu hình
warehouse khi không đặt `PLANNING_SQLITE_PATH`. Store PostgreSQL/PostGIS đã
được kiểm tra local bằng `scripts/test-planning-postgres-local.py` trên
container riêng; không phải chứng nhận deploy server của nhóm.

## Luồng tích hợp frontend

Model 0.14 có [luồng một khu đất trên cùng nền vùng](planning-single-site-common-context.md).
Preset `single_site` và `POST /api/v1/planning/single-site/studies` nhận một
project; các API job/result/map/ZIP giữ nguyên. Worker screening/native một
project trả `execution_path=single_site_shared_context`. Đây là contract để
nối phần 1/2/3; API integrated legacy site-only chưa tự chuyển sang nền vùng.

1. `GET /api/v1/planning/presets`: lấy năm fixture (single-site, site selection,
   cumulative, rehousing, inclusive background); chuyển polygon/building plan
   từ map sang schema tương ứng. Các binding/công suất nền do adapter hệ thống
   hoặc fixture cung cấp, không bắt người dùng đoán thông số cống.
2. `POST /studies/preflight`: body `PlanningStudy`; kiểm tra hình học, IDs,
   chương trình chung, giai đoạn và số lượt solver. Preflight synthetic không
   xác nhận coverage dữ liệu thực hoặc hiệu chỉnh tại địa phương.
3. `POST /studies`: lưu revision bất biến; nhận `id`, `context_hash`, `inputs`.
4. `POST /studies/{id}/runs`: `{ "mode": "native", "idempotency_key": "unique-request-id" }`.
   Trả 202, job ID; `screening` không chạy SUMO/SWMM.
5. `GET /jobs/{id}`: poll trạng thái/tiến độ; không suy job đã dừng chỉ vì một
   request poll bị timeout. Worker là tiến trình riêng.
6. Khi `succeeded`, đọc `GET /runs/{result_id}` rồi lấy layer của option/phase.
7. `POST /jobs/{id}/cancel` yêu cầu hủy. Worker đóng solver con thuộc job;
   không publish kết quả sau yêu cầu hủy được chấp nhận.
8. Thay input: `POST /studies/{id}/revisions`, chạy revision mới. Ẩn kết quả cũ
   khi người dùng đổi plan. Mở lại run cũ hiển thị đúng input đã đóng băng.
9. Job `failed`/`partial`/`cancelled`: `POST /jobs/{id}/retry` trả 202, giữ
   input cũ và dùng lại child đã hoàn chỉnh nếu checksum/context/engine đúng.
   `GET /jobs/{id}/children` xem từng child; `GET /jobs/{id}/children/{child_key}`
   đọc child hoàn chỉnh. Job partial không có full run để so sánh/xếp hạng.
   Retry job succeeded trả 409; sửa input cần revision mới.

Mọi đường tương đối ở trên có prefix `/api/v1/planning`.

## Dữ liệu map

Handoff 0.14 bổ sung [chuỗi theo object có phân trang](planning-series-and-recovery-audit.md):
`GET /runs/{id}/timeseries?name=drainage_links&object_id=TRUNK&catchment_id=pilot`.
Chọn option/phase/case, hour/seed cho roads, offset/limit (tối đa 300); trả
pagination, units, nguồn và samples. Không nhét toàn bộ chuỗi vào GeoJSON.
SWMM layer có units cho flooding_duration_minutes; comparability row mới
giữ bốn trạng thái, nguyên nhân lỗi tách ở comparability_reason.

Model 0.13: [benchmark/preflight](planning-runtime-benchmarks.md).
`runtime_estimates[mode]` có status, estimated_compute_seconds (null khi
unavailable), số mẫu, khoảng quan sát và reference_run_ids khi có số đo.
Frontend hiển thị là thời gian tính toán tham khảo, không gồm queue/lưu/ZIP.
Docker demo local 8007 đã cập nhật; các run cũ vẫn giữ phiên bản của chúng.

Model hiện tại 0.12: [timeline/peak hydrograph và uncertainty](planning-hydrographs-and-current-uncertainty.md).
State drainage có timeline và phút peak; chỉ cộng các chuỗi cùng timestamp.
Demo Docker cổng 8007 giữ run cũ, phiên bản mới tạo revision/context mới.

Model 0.11 bổ sung [declared program, normalized comparison và ZIP](planning-program-normalization.md).
Instance Docker hiện tại là cổng 8007. `normalization_bases` mặc định GFA;
các mẫu số phục vụ khác do study chọn, không gộp trường/chung cư trên số căn.
SUMO dùng ID geometry ổn định; frontend nối bằng project_to_solver_parcel
hoặc project_ids/project_id của private road feature, không tách tên edge.

Model 0.10 bổ sung [hàng chờ lane/edge, cống và SWMM theo phút](planning-spatial-timeseries.md).
Instance mới kiểm thử ở cổng 8006 với store riêng; API 8005 đang chạy từ
mốc trước. Đọc báo cáo timeseries để biết đúng endpoint/runtime/evidence.

Model hiện tại 0.9 có [snapshot normalization và retention](planning-background-snapshot.md).
Giữ raw inputs, resolved background và ledger trong result/ZIP. Với run cũ,
tạo revision mới để chạy engine hiện tại; không sửa result đã lưu. Manifest
0.9 có thêm nguồn snapshot khi dùng inclusive background.

Model 0.8 có [manifest nguồn/coverage](planning-source-manifest.md) trong
context, comparison và GeoJSON. Collection có source manifest ID/module
coverage/units; feature có source object ID, source IDs, engine và units.
Đây là coverage mô hình synthetic, không phải observed coverage. Context
0.7 trở về trước cần revision mới để chạy với model 0.8; run cũ vẫn đọc được.

```text
GET /api/v1/planning/runs/{id}/map
    ?option_id=ABC&name=school

GET /api/v1/planning/runs/{id}/map
    ?option_id=phase_3&name=roads&hour=18&seed=2026&interval=4

GET /api/v1/planning/runs/{id}/map
    ?option_id=A_only&name=shadow&hour=9

GET /api/v1/planning/runs/{id}/map
    ?option_id=ABC&name=drainage_links&drainage_sample=20
```

Layer: `parcels`, `school`, `shadow`, `roads`, `drainage`, `drainage_links`. `option_id=baseline`
lấy hiện trạng. GeoJSON WGS84/EPSG:4326, kèm context hash, nguồn synthetic,
option/phase/run/study ID, cửa sổ thời gian và phạm vi phủ. Không dùng geometry
của vùng nghiên cứu làm tổng diện tích đất xây dựng.

- `school`: tuyến phân bổ và điểm trường. Chỗ học dùng chung; reserved places
  dành cho người ngoài các nhóm nhu cầu đã khai báo. Một nhóm có thể chia chỗ
  cho nhiều trường, nhưng mỗi học sinh chỉ được phân bổ một lần.
- `shadow`: polygon hợp nhất, chỉ xuất 9/12/15h. Vùng nhận bóng cố định giữa
  các phương án, loại union tất cả footprint có thể xây. Không phải nhiệt độ.
- `roads`: chọn đúng giờ/seed/khoảng 5 phút. `speed` m/s, `traveltime` giây,
  `entered/left` xe, `occupancy` %. Thiếu edge sample không đổi thành 0.
- `drainage`: nút tràn/mực nước cực đại trong trận mưa; không phải ngập 2D.
- `roads` thêm sampled peak queue/lane trong cửa sổ, không cộng chiều dài lane.
- `drainage_links`: geometry cống/orifice tổng hợp; sample trả flow/depth.
  Hai layer SWMM nhận `drainage_sample` index 0-based; sample 20 là phút 21.
  Bỏ selector để lấy summary cả event; xem units/method trong GeoJSON.

Layer native chưa có trong screening trả 409. Option/giờ/seed/khoảng không có
trong run trả 422. Không tự fetch dữ liệu mới khi đổi tab xem một run đã lưu.

## So sánh và nguồn

Model 0.7 bổ sung `state.baseline_ledger`, `resident_transfers` trong input,
mẫu `rehousing` ở presets và `baseline-ledger.csv` trong ZIP. Xem
[ledger/validation/case để thử](planning-baseline-ledger.md). Development
là toàn bộ trạng thái sau xây; công trình giữ lại cần có trong plan. Transfer
chỉ mô tả cư dân đã có trong final counts, không cộng demand lần nữa.

`comparison`: geometry, nhu cầu, trường học, bóng đổ. Native thêm
`traffic_comparison` theo cặp giờ/seed và `drainage_comparison` theo trận mưa.
Mỗi dòng có trước/sau/chênh lệch/đơn vị/phạm vi/khả năng so sánh.
Missing là null. `scenario_only` chưa phải kết luận ngoài thực địa.

Run model 0.6 có `method`, `time_window`, `limitations` ở mỗi dòng screening,
traffic và drainage comparison. `marginal_effects` có `rows`, `traffic_rows`,
`drainage_rows` so với phase trước. Các run bất biến từ model cũ có thể thiếu
trường mới: frontend kiểm tra version, không tự dựng metric 0 thay thế.

Các thiết kế trên cùng parcel dùng chung physical access và branch SWMM;
`project_to_physical_parcel` ở network provenance mô tả ánh xạ. Cùng parcel
nhưng khác `gate_lanes` bị preflight từ chối vì study giữ một mạng chung.

Đọc cả completed/unfinished/undeparted bên cạnh delay. So tác động lên dân
hiện hữu bằng `background_completed_delay_seconds`; trung bình mọi xe có
thể giảm khi thêm nhiều chuyến ngắn, dù xe nền chậm hơn.

`criteria` khai báo metric và direction. Không khai báo thì không xếp hạng.
Thiếu một metric yêu cầu ở bất kỳ option nào thì không tạo bảng xếp hạng từ
những số thay thế. Khi chọn trọng số, phải nhập cho tất cả tiêu chí; kết quả
ghi cách chuẩn hóa theo tập phương án. Đã có
[luồng độ nhạy/seed/trọng số](planning-uncertainty-demo.md) và selector case
trong preview.

`school_age_fraction=.18`, spine đi bộ, capacity/trips/nền là giả định demo.
Nhu cầu học = ceil(cư dân × tỷ lệ tuổi học) theo parcel, cộng nhóm nền một lần.
`daily_users` của trường dùng cho vận hành/trips, không cộng thành nhu cầu chỗ
học lần nữa. Healthcare/park allocation chưa có; không dùng giường bệnh như
chỗ học. Trường thiếu capacity và occupancy chưa biết làm kết luận unmet
không đủ căn cứ.

## Artifact và kiểm thử

Kiểm tra instance Docker đang có, dùng worker thường trực:

```powershell
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/unused-for-external-worker.sqlite --external-worker --run-mode native --output test-results/planning-single-site
.venv/Scripts/python.exe scripts/test-planning-portfolio-local.py --api http://127.0.0.1:8007
# Khi có job files rồi, kiểm tra lại chính các job đó:
.venv/Scripts/python.exe scripts/test-planning-portfolio-local.py --api http://127.0.0.1:8007 --resume
```

`--sqlite-path` là tham số bắt buộc của smoke script nhưng không được dùng
để chạy worker khi có `--external-worker`; API/worker Docker dùng store trong
volume. Không bỏ flag này khi kiểm tra Docker. Script portfolio ghi input
và job ID ngay khi tạo; observation timeout phải kiểm tra job đã ghi.

`GET /runs/{id}/artifacts` tải ZIP input/result, comparison CSV, GeoJSON theo
option/phase và artifact solver. CSV gồm giờ/seed; solver files kiểm tra hash
trước tải. ZIP map mặc định chứa bóng 9h và khoảng SUMO đầu tiên của giờ đầu;
dùng API map hoặc result timeseries để lấy cửa sổ khác.

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_planning_studies.py backend/tests/test_planning_services.py backend/tests/test_planning_comparison.py backend/tests/test_planning_native.py -q
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8005 --sqlite-path .runtime/planning-demo-expanded/studies.sqlite --solver-root .runtime/planning-demo-expanded/solvers --run-mode native
node scripts/test-planning-ui.cjs
```

HTTP smoke tự chạy worker `--once`: dùng store không có worker thường trực
để tránh hai worker cạnh tranh lượt xử lý test. Browser test dùng worker
thường trực và native report từ HTTP smoke. SUMO/swmm-toolkit phải đã cài.

## Còn cần nghiệm thu

Cập nhật cuối: các gate backend/local đã có bằng chứng trong audit cuối.
Những giới hạn vận hành và phạm vi tích hợp bên dưới tiếp tục áp dụng.

Retry/recovery/cache và partial child đã có test local; recovery chỉ tự làm
khi xác nhận đúng worker trên cùng host đã dừng. Heartbeat cũ không đủ để
chiếm job; owner từ host khác/không xác minh được cần vận hành xử lý riêng.
Windows Python launcher và tiến trình engine con được kiểm tra/dừng theo
identity; không chỉ dừng PID launcher. Compose profile `planning` có worker
module riêng và dùng chung volume solver với API.

Coverage/provenance/ledger, source/unit map, retention và các invariant đã
đối chiếu cho phạm vi synthetic trong audit cuối. Snapshot của nhóm phải
tuân thủ adapter explicit contribution; chưa tự suy dữ liệu thật còn thiếu.
Browser retry/unknown/portfolio/uncertainty có bằng chứng API/worker thật.
Object counting chưa tiếp tục; frontend map chính và deploy là mốc riêng.

Interaction có `metrics`, `comparability_by_metric`, `unavailable_reasons`
và `scenario_values`. Nếu bất kỳ constituent comparison thiếu hoặc không
tương thích, interaction metric trả null; số tính theo giả định/solver invalid
giữ riêng để kiểm tra, không dùng cho ranking. Occupancy unknown cũng trả
null trước/sau/delta ở demand/traffic comparisons; đọc `scenario_values`
nếu muốn xem phép tính theo giả định. Run cũ giữ nguyên; không backfill số liệu.
