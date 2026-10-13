# Nền tổng vùng và chính sách artifact

Ngày 11/10/2026; model `planning-studies-0.9`. Demo local synthetic, chưa
nghiệm thu toàn bộ kế hoạch. Không tiếp tục object counting ở giai đoạn này.

## Snapshot có chứa parcel đăng ký

Không có `background_snapshot`: người cung cấp input khai báo nền đã loại
registered parcels. Có snapshot: backend kiểm tra đóng góp từng parcel,
tách một lần thành `context.resolved_background`, rồi dùng cùng nền đã tách
cho baseline, options, phases và native SUMO/SWMM. `inputs` giữ nguyên tổng
vùng ban đầu. Ledger từng trạng thái công bố `background_normalization`.

Mẫu đầy đủ: [planning-inclusive-background.json](samples/planning-inclusive-background.json).
Trên preview `http://127.0.0.1:8005/simulation/planning`, chọn **Snapshot tổng
vùng đã chứa A**, nạp mẫu và chạy. Raw background 1.300 người gồm A 100 người;
nền sau tách là 1.200. Baseline toàn vùng vẫn 1.300; ABC là 1.500, tăng ròng
200. Mẫu có di dời 100 người A→C, không cộng lại 100 người đó thành cư dân mới.

### Hợp đồng dữ liệu

| Trường | Yêu cầu |
|---|---|
| `id`, `source`, `source_kind` | ID, nguồn cụ thể và synthetic/estimated/observed |
| `coverage` | Polygon phủ AOI; có traffic thì phủ cả mạng mô hình |
| `included_modules` | Các module tổng vùng đã bao gồm parcel: population/utilities/traffic/school/drainage |
| `parcels[].project_id` | Project đã đăng ký; một physical parcel chỉ có một contribution |
| `parcels[].baseline_sha256` | Hash baseline chuẩn hóa; stale hash bị từ chối |
| `parcels[].source` | Nguồn của phép tách contribution |
| `residents` | Population contribution bằng cư dân baseline đã biết |
| `utilities` | 24 giá trị `power_kw`, freshwater/wastewater m³/ngày |
| `traffic` | 24 số nguyên cars và motorcycles của parcel |
| `school_group_students` | Mapping group ID→số học sinh đã nằm trong group nền |
| `drainage` | `area_m2` của parcel và `impervious_m2` đã nằm trong catchment nền |
| `regional_traffic` | Profile cars/motorcycles 24 giờ trước tách; bắt buộc khi gồm traffic |
| `traffic_basis` | `planned_external_od_departures`; không nhận edge counts như OD |

Contribution module được chọn là bắt buộc; trường module không được chọn bị
từ chối để tránh input bị bỏ qua. Các contribution dân số/trips/trường cần
occupancy baseline đã biết. Không tự suy contribution thiếu bằng số 0.
Tổng vượt nền, âm sau tách, geometry/coverage sai, group/project ID lạ hoặc
hai contribution của thiết kế thay thế trên cùng parcel đều bị từ chối.

Baseline hash lấy bằng hàm dùng chung:

```python
from app.services.simulation.integrated.context import digest
from app.services.simulation.planning.context import canonical_numbers
baseline_sha256 = digest(canonical_numbers(project.baseline.model_dump(mode="json")))
```

Snapshot nguồn bổ sung vào source manifest; module chỉ nhận source ID này
khi sử dụng phép tách đó. Sensitivity thay đổi background traffic trên phần
đã sạch, cộng contribution trở lại raw case để giữ cùng quy tắc normalization.
Input case và nhãn synthetic được lưu, không gán input đã sửa là observed.

Đây là adapter dựa trên contribution được cung cấp, không phải thuật toán tự
nhận diện mọi nguồn chồng lặp. Counts xe qua đường phải chuyển thành OD bằng
mô hình/ledger riêng; không trừ trực tiếp counts khỏi số chuyến xuất phát.

## Retention

Chính sách demo: giữ vô thời hạn study/run/child và artifact được các document
tham chiếu, gồm uncertainty cases, cache và child của job partial cần retry.
Chỉ dọn workdir planning không còn tham chiếu, không được ghi trong ít nhất
7 ngày. Không xóa metric/document hoặc artifact để làm ZIP lịch sử mất dữ liệu.

CLI mặc định chỉ báo cáo, dùng cùng environment store/solver root của API:

```powershell
.venv/Scripts/python.exe -m app.services.simulation.planning.retention
```

Muốn áp dụng, root phải chỉ được dùng bởi **một planning store**. Dừng các
producer dùng root đó; không có job queued/running. Khóa transaction ngăn
worker claim/retry trong lúc kiểm tra và dọn. Với root dùng chung nhiều store
hoặc không rõ chủ sở hữu, chỉ dùng dry-run.

```powershell
.venv/Scripts/python.exe -m app.services.simulation.planning.retention --apply --exclusive-planning-root --min-age-days 7
```

Chỉ xét prefix `planning-network-`, `planning-sumo-`, `planning-swmm-`;
không dọn workdir single-site. Kiểm tra absolute containment trước xóa;
bỏ qua symlink/junction và thư mục có descendant liên kết. Thư mục có file
mới không bị dọn dù mtime thư mục cũ. CLI không tự chạy trong worker/API.
Nếu thao tác bị ngắt, chạy lại dry-run để xem thư mục còn lại. Policy chưa
có giới hạn dung lượng hay tự xóa lịch sử; theo dõi disk và archive trước
khi đặt chính sách hết hạn cho kết quả đã bàn giao.

## Bằng chứng local

- Regression trước retention: 68 passed, 84,86 giây,
  `test-results/planning-background-regression.xml`. Bao gồm planning và
  integrated theo danh sách test, không phải toàn repo.
- Background focused: 5 passed, 15,94 giây,
  `test-results/planning-background.xml`; có SUMO/SWMM thật, nền inclusive
  cho cùng kết quả với nền đã sạch, module order/hash và sensitivity.
- UI: 12 nhóm passed, `test-results/planning-studies/ui-report.json`, gồm
  raw 1.300→clean 1.200, ABC net 200, reload, native, retry, ZIP và mobile.
- Retention + jobs: 11 passed, 14,79 giây,
  `test-results/planning-retention-jobs.xml`; kiểm tra giữ nested manifest,
  child retry, chặn active jobs, opt-in, bad path và junction Windows thật.
- Background + provenance sau patch cuối: 11 passed, 36,59 giây,
  `test-results/planning-background-provenance.xml`, gồm API/worker screening
  và ZIP giữ raw snapshot/context đã sạch, cùng native SUMO/SWMM equivalence.
- Retention sau đổi traversal không đi xuyên junction: 4 passed, 1,32 giây,
  `test-results/planning-retention.xml`. Dry-run trên store demo thật: không
  có candidate đủ 7 ngày, không xóa thư mục; report `retention-report.json`
  trong `test-results/planning-studies/`.

Model 0.8 Docker/native uncertainty có bằng chứng lịch sử riêng; chưa coi
đó là kiểm chứng packaged image 0.9. Còn audit corner cases, layer/time
selectors và đóng gói end-to-end trước khi nghiệm thu toàn bộ demo.
