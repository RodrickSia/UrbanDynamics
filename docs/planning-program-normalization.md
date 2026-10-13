# Quy mô phục vụ và tác động trên đơn vị phương án

Ngày 11/10/2026; model `planning-studies-0.11`. Demo synthetic, chưa nghiệm
thu toàn bộ kế hoạch. Phần này hoàn thiện đầu ra của `declared_programs` và
giữ bảng tuyệt đối cho cả equal-program/cumulative.

## Đầu vào và công thức

Study có `normalization_bases`, mặc định `["floor_area_m2"]`. Có thể chọn:

| Basis | Mẫu số trong development active | Công năng phù hợp |
|---|---|---|
| floor_area_m2 | Tổng GFA | Mọi công năng; chỉ là cường độ trên diện tích vật lý |
| housing_units | Số căn residential | Chỉ nhà ở |
| residents | Số cư dân residential | Chỉ nhà ở |
| school_places | service_capacity của school | Chỉ trường học |
| office_staff | staff của office | Chỉ văn phòng |

Mẫu số lấy từ building plan, không lấy dân số nền hoặc công suất của công
trình inactive. Đây là chương trình hoàn chỉnh sau xây, gồm phần giữ lại;
không gọi số đó là số căn/chỗ mới bổ sung ròng. Capacity trường là số chỗ
khai báo, không tự suy từ GFA. Chưa dùng capacity bệnh viện như số giường.

```text
value = (metric phương án - metric baseline chung) / quy mô phương án active
```

Mỗi option/phase có `declared_program` (uses, active IDs, values và policy)
và `normalized_comparison`. Row có numerator/numerator_unit, denominator/
denominator_unit, basis, value/unit, comparability, method, source IDs,
context/time/scope và unavailable_reason. Raw comparison giữ nguyên.

Các metric tỷ lệ gồm nhu cầu điện/nước/nước thải, trips, runoff, áp lực chỗ
học, thay đổi đất xanh/không thấm và native overflow/peak runoff. Không chia
trung bình delay hoặc hàng chờ cho số căn để tạo chỉ số khó diễn giải.

School và residential cùng active: tỷ lệ toàn portfolio trên số căn hoặc
chỗ học trả `not_comparable`, value null. GFA vẫn có thể dùng như đơn vị
vật lý, nhưng không làm lợi ích trường/nhà ở tương đương. Mẫu số bằng 0 hoặc
impact missing/unknown: `insufficient_data`, value null; không chia cho 1
hoặc thay bằng 0. Pareto/trọng số hiện dùng metric tuyệt đối do study chọn;
không tự thay ranking bằng các tỷ lệ mới.

## Bàn giao và thử

Preview có bảng **Tác động trên quy mô phương án**. Kết quả đầy đủ trong JSON;
ZIP thêm `declared-programs.json` và `normalized-comparison.csv`, theo case,
option và phase. Run cũ giữ nguyên, không tự tái tính. Thay basis tạo revision
và context mới; đảo thứ tự basis không thay context.

Case thử: so vị trí, đặt comparison_policy=declared_programs, chọn bases
housing_units/residents/GFA, sửa B từ 200 căn/600 người thành 100 căn/300
người. Xem cả delta tổng và delta trên quy mô; không kết luận B tốt hơn chỉ
vì nhỏ hơn. Với cumulative A+B+C, housing_units và school_places không phù
hợp cho toàn portfolio; GFA là phép so cường độ vật lý có giới hạn.

## Định danh solver ổn định

Test đổi A/B/C thành Zulu/Yankee/Xray từng phát hiện delay đổi khoảng
0,012 giây dù đầu vào vật lý giống nhau. SUMO nay dùng hash geometry cho ID
gate/edge/route/cohort, thứ tự tạo private network và route ổn định. ID
project vẫn dùng trong API/ledger; `project_to_solver_parcel` nối hai hệ ID.
Không yêu cầu frontend suy project từ tên engine edge.

Test native đổi tên/đảo thứ tự cả ba parcel nay giữ metric và delay/queue
trong tolerance 1e-6; runoff cùng thời điểm cũng được đối chiếu. Context
vẫn đổi khi đổi ID vì input/provenance khác nhau, không tái dùng cache chỉ
vì geometry giống nhau. Đây là invariant trên fixture được kiểm tra, không
phải bằng chứng mọi cấu hình đô thị đều được hiệu chỉnh.

## Bằng chứng

- Normalization/comparison/studies: 19 passed, 8,52 giây,
  `test-results/planning-normalization.xml`, gồm đủ 8 tập của 3 project,
  phase=option, thứ tự input, unknown, mixed use, zero denominator và ZIP.
- Focused rename native sau sửa: 1 passed, 19,90 giây,
  `test-results/planning-rename-focused.xml`.
- Regression tất cả `test_planning_*.py` và `test_integrated_simulation.py`:
  81 passed, 90,37 giây, `test-results/planning-program-regression.xml`.
  Không phải toàn bộ repo hoặc toàn ETL/frontend.
- Image backend 0.11 đã chạy native trên Linux: 5 child computed, job sau
  5 cache hits, queue/link/normalization và cancel/timeout/worker entrypoint
  đạt. Sau đó phát hiện API import cần pandas/geopandas từ router giá đất;
  dependency/lockfile backend được bổ sung và image được build lại. Bằng
  chứng API/image cuối được ghi riêng sau kiểm tra, không suy từ helper cũ.
- Sau dependency fix: packaged Linux check passed, 6,91 giây; report
  `test-results/planning-program/packaged-image-native-report.json`. HTTP
  native cả hai case passed, 37,72 giây, `http-native-report.json` cùng thư
  mục. API/worker chạy trong hai container cùng image và volume riêng.
- Focused sau metadata private edge: 2 passed, 7,76 giây,
  `test-results/planning-program-final-focused.xml`, có kiểm tra thiết kế B
  trên cùng parcel nhận project_id B trên map và API ZIP chuẩn hóa.
- Browser Docker API 8007: 12 nhóm passed, report
  `test-results/planning-program/ui-report.json`. Có 9 row screening và 11
  row native chuẩn hóa; tỷ lệ nhỏ -0,00232 hiển thị được, không làm tròn về 0.
  Đã xem ảnh panel `planning-normalization.png`; cùng lượt có mobile, retry,
  queue/cống/time selector, ZIP, manifest, ledger và snapshot inclusive.
  Lượt này chưa chạy/read native uncertainty phiên bản 0.11.

## Instance local hiện tại

Mở `http://127.0.0.1:8007/simulation/planning`. Container
`planning-program-api` và `planning-program-worker` dùng volume
`planning-program-runtime` (SQLite và solver artifacts), chỉ expose localhost.
Đây là demo Docker trên máy local, chưa deploy server hoặc push repo.
Kiểm tra trạng thái: `docker ps --filter name=planning-program`.

Reproduce HTTP với worker đã chạy (không spawn worker local cạnh worker Docker):

```powershell
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/planning-program/studies.sqlite --external-worker --run-mode native --output test-results/planning-program
$env:PLANNING_API_URL='http://127.0.0.1:8007'
$env:PLANNING_EVIDENCE_DIR='test-results/planning-program'
node scripts/test-planning-ui.cjs
```

Với external-worker, sqlite-path không được dùng để chạy/ghi store trên host;
store thật ở Docker volume. Nếu observation timeout, kiểm tra job ID đang có,
không tự tạo lại job. Browser chỉ tái hiện khi có native report từ API này.

Còn single-site equivalence trên cùng boundary/context, hydrograph/binding
corner cases, uncertainty model mới và audit toàn bộ hợp đồng/nghiệm thu.
