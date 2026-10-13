# Hydrograph và độ nhạy model 0.12

Ngày 11/10/2026. Synthetic demo; chưa nghiệm thu toàn bộ kế hoạch. API/worker
Docker local cổng 8007 đã được cập nhật model `planning-studies-0.12`, giữ
nguyên volume và các run lịch sử. Chưa push hoặc deploy server.

## Ghép hydrograph đúng thời điểm

Trước đây code chỉ kiểm tra số lượng mẫu. Hai chuỗi cùng độ dài nhưng lệch
timestamp có thể vượt qua điều kiện này. `drainage.combine_runoff` nay kiểm
tra timestamp và report step trước khi cộng:

- Danh sách catchment phải có ít nhất một phần tử, không lặp ID.
- Runoff và timestamp có cùng số mẫu, không rỗng; mọi giá trị finite.
- Runoff không âm; report step dương; timestamp bắt đầu sau 0 và tăng đúng step.
- Mọi catchment có cùng report step và chính xác cùng timestamp.
- Không nội suy hoặc dịch chuỗi thiếu dữ liệu để ghép bằng index.

Sau đó tính:

```text
Q_total(t) = tổng Q_catchment(t)
Q_peak = max theo t của Q_total(t)
```

Fixture kiểm tra A=[1,5,1,0], B=[0,1,5,1] cho đỉnh chung 6, không phải
5+5=10. Hai hydrograph cùng đỉnh [1,5,1,0] cho đỉnh chung 10. Timestamp tính
theo phút, cửa sổ hiện tại sample 60 giây. `peak_minute` là thời điểm đầu
tiên đạt peak sampled; không trả một peak time có ý nghĩa khi runoff bằng 0.

State native có `combined_runoff_m3_s`, `combined_runoff_time_minutes`,
`combined_runoff_peak_minute` và metric `runoff_peak_m3_s`. Giữ giới hạn:
sampled runoff không phải surface flood depth; overflow integration không
thay thế continuity ledger. Tăng model version làm mất cache cũ đúng context.

## Binding và test native hai lưu vực

Test native chạy danh mục A/B/C với A nối vào urban, B/C nối vào green.
Urban có nền 20.000 m²/100% impervious; green có nền 80.000 m²/0% impervious.
Mọi thông số là synthetic. Test kiểm tra node/branch đúng catchment, continuity,
profile thật khác nhau và combined series/peak/time của pipeline trùng kết
quả ghép theo thời điểm. Catchment ID chưa khai báo bị schema từ chối.

Không gọi fixture này là bằng chứng hai peak native nhất thiết lệch nhau:
test lệch/trùng peak có chuỗi xác định ở trên; test native chứng minh wiring,
output solver và phép ghép thật trên hai graph.

## Bằng chứng đã quan sát

| Gate | Kết quả | Artifact |
|---|---|---|
| Hydrograph + native trước mở rộng pipeline test | 15 passed, 29,08 giây | `test-results/planning-hydrographs.xml` |
| Native đầy đủ hai catchment sau mở rộng | 1 passed, 16,40 giây | `test-results/planning-hydrographs-native.xml` |
| Regression planning/integrated hiện tại | 90 passed, 136,21 giây | `test-results/planning-hydrographs-regression.xml` |
| CLI native uncertainty 0.12 | 36 SUMO + 12 SWMM passed, 62,07 giây | `test-results/planning-hydrographs/uncertainty-native-report.json` |
| HTTP uncertainty cả hai bài toán, worker Docker | Passed, 151,64 giây | `test-results/planning-hydrographs/http-uncertainty-report.json` |
| HTTP native cả hai bài toán 0.12 | Passed, 22,59 giây | `test-results/planning-hydrographs/http-native-report.json` |
| Browser trên Docker API/worker 0.12 | 13 nhóm passed | `test-results/planning-hydrographs/ui-report.json` |

Regression gồm tất cả `backend/tests/test_planning_*.py` và
`test_integrated_simulation.py`; không phải toàn bộ ETL/frontend/repo. Lượt
HTTP kiểm tra lưu study/input/result bất biến, idempotency, các case, API và
ZIP; không tự chứng minh PostgreSQL hay UI. Native CLI chạy trên Windows,
HTTP chạy solver trong Linux Docker. Không cộng hai phạm vi thành một bộ
test Windows/Linux có cùng số test.

CLI dùng cùng ba seed 2026/2027/2028 cho reference/low/high. Kết quả Pareto
thay đổi theo giả định và seed; `overall_ranking_assessment` báo
`sensitive_in_sampled_cases`. Trung bình case ổn định không đủ khẳng định
ranking ổn định. Spread của các mẫu không phải confidence interval.

Browser đã mở lại uncertainty run 0.12 thật, đổi reference/high/low, kiểm tra
ba seed và cảnh báo độ ổn định. Đã sửa preview giữ option đang chọn khi đổi
case, tránh âm thầm chuyển C sang A rồi so hai khu khác nhau. Test xác nhận
C_only giữ nguyên qua high/low. Các nhóm còn lại gồm native/time/map, mobile,
retry, normalized table, manifest, ledger, inclusive background và ZIP.

## Tái hiện

```powershell
$env:SIMULATION_WORK_DIR="$PWD/.runtime/planning-hydrograph-uncertainty/solvers"
.venv/Scripts/python.exe scripts/test-planning-uncertainty-local.py --output test-results/planning-hydrographs
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/planning-program/studies.sqlite --external-worker --run-mode uncertainty --hours 18 --output test-results/planning-hydrographs
```

External worker sử dụng store trong Docker volume, không ghi sqlite-path trên
host. Nếu timeout quan sát, kiểm tra job ID hiện tại. Mở
`http://127.0.0.1:8007/simulation/planning`; dùng Job UUID từ HTTP report để
xem run đã lưu, chọn case/seed và tải ZIP, không tự tái chạy solver khi đổi tab.

Còn single-site equivalence trên cùng context/boundary, benchmark/preflight
thời gian từ số đo, PostgreSQL và audit đầy đủ mọi hợp đồng/invariant trước
khi nghiệm thu toàn bộ. Object counting tiếp tục hoãn.
