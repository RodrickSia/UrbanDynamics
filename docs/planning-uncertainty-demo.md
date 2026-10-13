# Demo độ nhạy, seed và trọng số

Cập nhật hiện tại 0.14: [uncertainty API/browser và chuỗi phân trang](planning-series-and-recovery-audit.md).
Hai bài toán, ba case/ba seed/hai giờ đã đạt; browser 14 nhóm có reload và
case/seed/stability. Các mốc phía dưới là lịch sử, không phải số đo lượt mới.

Cập nhật 0.12: [bằng chứng CLI/API và hydrograph](planning-hydrographs-and-current-uncertainty.md).
CLI 36 SUMO/12 SWMM, API cả hai bài toán đã đạt; phần 0.4 bên dưới là
mốc lịch sử, không mô tả mọi tính năng còn thiếu ở code hiện tại.

11/10/2026. Model planning 0.4, synthetic. Đây là một giai đoạn đã triển khai;
[toàn kế hoạch](urban-planning-multisite-cumulative-plan.md) vẫn còn job
recovery/cache, PostgreSQL và audit cần hoàn thiện. Object counting vẫn chờ.

## Cách thử

Mở `/simulation/planning`, nạp mẫu và chọn **Độ nhạy + 3 seed**. Kiểm tra
JSON `uncertainty` rồi preflight trước khi chạy. Chế độ này chạy nhiều lượt
solver, không phải realtime. Khi xong, selector **Giả định đầu vào** thay
metric/layer/capacity theo reference/low/high/lower_capacity.

Khai báo trong study:

```json
{
  "uncertainty": {
    "engine": "native",
    "seeds": [2026, 2027, 2028],
    "traffic_material_delta_seconds": 0.5,
    "cases": [
      {"id": "low", "source": "Synthetic lower trip-generation assumption", "level": "low"},
      {"id": "high", "source": "Synthetic higher trip-generation assumption", "level": "high"},
      {"id": "lower_capacity", "source": "Synthetic shared utility capacities at 80 percent", "utility_capacity_scale": 0.8}
    ]
  }
}
```

Tạo run với `mode=uncertainty` trên API study đã lưu. Reference tự thêm, giữ
input gốc và dùng seed suite đã khai báo. `engine=screening` chỉ phân tích
geometry/demand/capacity; không tạo kết quả traffic từ seed.

## Giả định nào thay đổi?

Mỗi case giữ nguyên projects, building plan, baseline và program targets;
chỉ thay các trường được công khai:

| Trường | Phạm vi |
|---|---|
| `level` | Hệ số phát sinh trips trong library; mưa và xe nền study vẫn giữ nguyên |
| `rainfall_mm` | Cùng trận mưa mới cho baseline/options trong case |
| `background_vehicles_hour` | Cùng dòng xe nền mới cho mọi trạng thái |
| `school_age_fraction` | Nhu cầu tuổi học của cư dân trong các parcel; nhóm nền giữ số khai báo |
| `utility_capacity_scale` | Capacity vùng điện/nước/nước thải, không thay tải nền |
| `existing_school_capacity_scale` | Capacity trường hiện hữu; reserved enrollment giữ nguyên |

Unknown giữ null. Preflight chặn case không hợp lệ, ví dụ capacity trường
thấp hơn reserved places. Không tự giảm quy mô công trình mới để tạo lợi thế.
Các case là stress scenarios có nguồn giả định, không phải phân bố xác suất.

## Công thức và trạng thái

Theo một giờ/seed chung:

```text
delta(option, seed) = metric(option, seed) - metric(baseline, seed)
pair(A, B, seed) = metric(A, seed) - metric(B, seed)
```

Lưu min/max/mean của delta ghép cặp và dữ liệu từng seed. Với delay, ngưỡng
ý nghĩa do input chọn (mặc định 0,5 s). Ít hơn ba seed, thiếu sample hoặc delay
không đủ khả năng so sánh thì không kết luận ổn định. Cùng chiều qua các seed
chỉ là nhận xét trong các mẫu đã chạy. Đây không phải confidence interval.

- `seed_analysis`: biến thiên solver trong **mỗi case**, Pareto/top theo seed.
- `uncertainty_analysis`: delta qua các giả định, range các mean traffic,
  capacity có đổi trạng thái vượt ngưỡng hay không, và ranking tổng hợp.
- `weight_analysis`: nếu có đầy đủ trọng số, thay từng trọng số 0,5×/2× trên
  cùng kết quả solver. Ties giữ một tập ID, không phá hòa bằng thứ tự tên.

Kết luận tổng hợp xem cả input, seed và weights ở từng case. Mean qua case
ổn định nhưng ranking đổi theo seed vẫn báo `sensitive_in_sampled_cases`.
`stable_in_sampled_cases` không chứng minh hiệu chỉnh địa phương, tối ưu toàn
cục hoặc đủ cơ sở phê duyệt quy hoạch. Delay mọi xe chịu ảnh hưởng trip mix;
ưu tiên cohort xe nền khi đánh giá tác động lên người đang sử dụng mạng.

## Input, API map và artifact

Run lưu hai bộ input rõ ràng:

- `analysis_request` và `analysis_request_context_hash`: study ban đầu.
- `inputs/context`: reference thực sự được chạy bằng suite ba seed.
- `assumption_cases[]`: input/result/context hash/source từng case.

Không gán hash study một seed cho kết quả chạy ba seed. API map thêm
`case_id=low`, ví dụ:

```text
GET /api/v1/planning/runs/{id}/map?option_id=A_only&name=school&case_id=low
```

ZIP có `analysis-request.json`, input/result từng case, solver artifacts và
CSV có cột case ID. Map mặc định trong ZIP là reference; lấy case khác qua API
hoặc result của case. Mở lại run không tự fetch input mới.

## Bằng chứng local

- 44 test planning + integrated đạt, `test-results/planning-uncertainty.xml`.
- 4 test độ nhạy bổ sung đạt, `planning-uncertainty-focused.xml`.
- Native trực tiếp: 36 SUMO/12 SWMM, 3 case × 3 seed × 4 trạng thái × 1 giờ;
  41,20 s ở lượt đầu, continuity và vehicle balance đạt.
- HTTP + worker riêng: cùng bài toán qua durable queue, lưu/mở lại, case input
  và ZIP solver; lượt cuối 53,96 s, `http-uncertainty-report.json`.

Native fixture so vị trí dùng 18h. Mean Pareto qua các case giữ nguyên, nhưng
reference đổi Pareto và weighted-top theo seed. Đây là lý do phải hiển thị
cảnh báo thay vì công bố một site thắng chắc chắn. Các số không được điền sẵn.

Chạy lại:

```powershell
$env:PYTHONPATH='backend;etl'
$env:SIMULATION_WORK_DIR="$PWD/.runtime/planning-uncertainty/solvers"
.venv/Scripts/python.exe scripts/test-planning-uncertainty-local.py
```

HTTP smoke dùng store không có worker thường trực, rồi script tự chạy worker
`--once`:

```powershell
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8005 --sqlite-path .runtime/planning-demo-expanded/studies.sqlite --solver-root .runtime/planning-demo-expanded/solvers --run-mode uncertainty --study-mode site_selection --hours 18
```
