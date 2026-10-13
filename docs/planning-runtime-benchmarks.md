# Benchmark thời gian và preflight planning

Ngày 11/10/2026; model `planning-studies-0.13`. Hoàn thiện một phần kế hoạch,
chưa nghiệm thu toàn bộ demo. Dữ liệu thử synthetic; counting vẫn hoãn.

## Hành vi

Preflight trả `runtime_estimates` cho screening/native và uncertainty khi
được cấu hình. Không có số đo phù hợp thì `status=unavailable`, giá trị thời
gian null; vẫn trả workload và số lượt solver.

Worker đo từ sau khi claim job đến sau tính toán, trước lưu run. Không gồm
chờ hàng đợi, lưu kết quả, đóng ZIP và download. Chỉ job thành công được ghi
benchmark cùng transaction với run. Lượt native có bất kỳ cache hit nào
không được đưa vào catalog thời gian chạy mới.

Mẫu phải cùng model, engine/Python/platform, nhãn máy và đầu vào vật lý/thư
viện hệ số. Title/nguồn mô tả/criteria không tạo nhóm benchmark riêng.
Thay physics cần số đo mới; không ngoại suy thời gian từ số solver. Giữ tối
đa 20 mẫu gần nhất khi truy vấn; trả median/min/max và run ID tham chiếu.
Một mẫu là ví dụ đo thực tế; khoảng quan sát không phải confidence interval.

## Cấu hình

API và worker cần cùng `PLANNING_BENCHMARK_MACHINE_ID` cho một môi trường
worker đồng nhất. Compose truyền biến này cho cả hai; mặc định rỗng nên không
đưa ra ETA. Docker demo local dùng `local-docker-worker`.

Đổi nhãn khi đổi CPU/GPU, giới hạn tài nguyên/container hoặc môi trường máy.
Không dùng chung nhãn cho pool có cấu hình khác nhau. Nhãn là cấu hình vận
hành, không phải phát hiện tự động phần cứng hay bảo đảm hiệu năng. Catalog
giữ các mẫu đã lưu; không có quota/expiry mới trong thay đổi này.

## Bằng chứng focused đã chạy

- `test-results/planning-benchmark-focused.xml`: 18 passed (benchmark và
  planning studies), gồm job screening thật, context hash không đổi do
  catalog, đổi physics/máy/model/engine, không cấu hình và failed/cancelled.
- `test-results/planning-benchmark/postgres-report.json`: PostgreSQL/PostGIS
  3.5.2, model 0.13, SUMO/SWMM thật; 5 child cold rồi 5 cache hits. Preflight
  có một mẫu cold, không thêm mẫu từ lượt cache. Toàn script 11,09 giây;
  mẫu tính toán 3,92 giây chỉ áp dụng fixture một project/một giờ trong lượt
  kiểm tra đó, không phải ETA cho case A/B/C.
- `node --check backend/app/static/planning.js` đạt; kiểm tra cú pháp không
  thay cho kiểm tra browser.

Script PostgreSQL tạo container test riêng, credentials phát sinh trong env
file ignored, dọn đúng container/env file của lượt test. Không sửa DB demo.
Các gate regression/HTTP/browser được ghi riêng sau khi hoàn tất.

## Kiểm tra bản hiện tại

- Regression planning + integrated single-site: **97 passed**, 101,47 giây,
  `test-results/planning-benchmark-regression.xml` (Windows). Không suy từ đó
  thành toàn bộ suite Linux hay độ chính xác dữ liệu địa phương.
- Build image backend Linux đạt; API/worker Docker local cổng 8007 đã cập
  nhật, giữ volume và các run cũ. Native HTTP cho site selection và cumulative
  đạt, 29,27 giây toàn script: `planning-benchmark/http-native-report.json`.
- `planning-benchmark/http-timing-report.json`: preflight sau run trả đúng
  run ID; hai mẫu cold lần lượt 10,17 và 14,92 giây. Đây là số đo hai fixture
  trên worker local, không phải cam kết realtime.
- Browser **12 nhóm passed**, `planning-benchmark/ui-report.json`; gồm
  screening, reload native, layer/time/seed, ZIP, mobile, retry, ledger và nền
  inclusive. Không có lượt uncertainty mới trong gate này.
- Browser focused đọc preflight của native run đã lưu và thấy thông báo
  số đo/phạm vi loại trừ: `planning-benchmark/ui-timing-report.json`.

Các report ở trên nằm dưới `test-results/` (ignored). Còn single-site common
context equivalence, các gate uncertainty/package và audit đầy đủ kế hoạch.
