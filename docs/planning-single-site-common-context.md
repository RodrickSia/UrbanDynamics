# Single-site và nhiều dự án trên cùng context

Ngày 11/10/2026; model `planning-studies-0.14`. Dữ liệu synthetic; chưa nghiệm
thu toàn bộ kế hoạch, counting vẫn hoãn.

## Thay đổi

Luồng single-site mới nằm ở `integrated.engine.predict_shared_study`.
Đầu vào là một `PlanningStudy` có đúng một project, với AOI, hiện trạng,
vùng điện/nước, trường, lưu vực, mưa, giờ và seed được khai báo đầy đủ.
Hàm có thể nhận frozen context; nội dung phải khớp study/model/library hiện
tại, không chỉ khớp chuỗi hash do caller gửi. Không thay đổi context đầu vào.

Single-site tự đánh giá trạng thái baseline/development và chạy solver.
Luồng portfolio tự xác định các trạng thái option/phase/standalone rồi chạy
solver. Hai luồng dùng chung `planning.engine.evaluate`, bộ tính native
`prepare_network/evaluate_native_state` và hợp đồng trình bày kết quả; không
gọi orchestration portfolio để giả làm phép kiểm chứng single-site.

Worker tự dùng luồng này cho job screening/native có một project. Result có
`execution_path=single_site_shared_context`, giữ schema planning để frontend
dùng chung bảng, layer, store, revision, cache và ZIP. Uncertainty vẫn dùng
orchestrator phân tích độ nhạy, với bộ tính trạng thái/native chung.

API tạo study tường minh: `POST /api/v1/planning/single-site/studies`.
Body là PlanningStudy một project; nhiều project bị từ chối 422. Chạy/lấy
kết quả qua `/studies/{id}/runs`, `/jobs/{id}` và `/runs/{id}` như các study
khác. `/studies` thông thường cũng nhận study một project và worker dispatch
tương tự. Snapshot phải bao gồm nền cho đúng phạm vi; bỏ các parcel khác
khỏi danh mục có thể đổi baseline, không tự coi bằng study ba parcel.

Preset `single_site` trong `/presets`, mẫu
`docs/samples/planning-single-site.json`, và preview có lựa chọn
**Một khu đất trên nền chung**. Mở lại job giữ đúng một project.

## Phạm vi tương đương

Phép đối chiếu áp dụng khi cùng toàn bộ context và danh mục parcel, không
chỉ cùng polygon building. Native test chạy hai orchestration độc lập, cùng
giờ 18h và seed 2026/2027; so baseline, development, standalone, comparisons,
ranking, validity, cùng cấu trúc mạng, queue/edge intervals và chuỗi SWMM.
Artifact ID khác nhau chứng minh đây là hai lượt chạy độc lập. Parse XML để
so toàn bộ topology/geometry/attributes, vì comment netconvert có thời gian
và thư mục riêng nên checksum toàn file không bắt buộc bằng nhau.

API legacy `/api/v1/scenarios/integrated/predict` vẫn dùng context site-only
và mạng của phiên bản integrated trước. Không tuyên bố output legacy đó
bằng study mới. Để tích hợp phần 1/2/3 trên một nền thống nhất, frontend dùng
luồng planning/shared-study mới; chưa có chuyển đổi tự động mọi run legacy.

## Bằng chứng đã hoàn tất

- `test-results/planning-single-site-equivalence.xml`: **4 passed**, 14,78
  giây; native độc lập, screening, stale context và API/worker screening.
- `test-results/planning-single-site/postgres-report.json`: model 0.14,
  PostgreSQL/PostGIS 3.5.2; native shared single-site, 5 child cold và 5 cache
  hits, revisions/idempotency/cancel/retry/lease, benchmark cold-only đạt.
- Packaged Linux check trong image backend: stdout `status=passed`, model
  0.14, 9,01 giây; native single-site, cache, normalized/source/time-series,
  cancel/timeout và worker entrypoint. Không phải toàn bộ suite Linux.
- `planning-single-site/http-native-report.json`: HTTP native so vị trí và
  cộng dồn đạt, 61,62 giây toàn script khi chạy đồng thời regression.
- `planning-single-site/single/http-native-report.json`: HTTP single-site
  native đạt, 8,52 giây; lưu/mở study, idempotency, source/layer và ZIP thật.

- `test-results/planning-single-site-regression.xml`: **101 passed**, 201,52
  giây (Windows planning + integrated); chạy đồng thời một số gate native.
- `planning-single-site/ui-report.json`: **13 nhóm browser passed**, gồm
  preset một project, mở lại native job và roads layer; các nhóm khác kiểm
  tra screening/native/map/selectors/ZIP/mobile/retry/ledger/background.

Các đường report trên thuộc `test-results/` ignored. Chưa có lượt native
uncertainty 0.14 trong các bằng chứng này; audit các yêu cầu còn lại vẫn cần.
