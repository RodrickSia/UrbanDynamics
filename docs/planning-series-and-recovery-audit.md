# Chuỗi phân trang, recovery và độ nhạy hiện tại

Ngày 11/10/2026; model vật lý `planning-studies-0.14`. Bổ sung API đọc kết
quả/metadata và guard recovery; không đổi phương trình hay mạng solver.
Demo synthetic; counting tiếp tục hoãn. Chưa nghiệm thu toàn bộ kế hoạch.

## API chuỗi số liệu cho frontend

```text
GET /api/v1/planning/runs/{id}/timeseries
    ?option_id=phase_3&name=drainage_links&catchment_id=pilot
    &object_id=TRUNK&offset=0&limit=60

GET /api/v1/planning/runs/{id}/timeseries
    ?option_id=ABC&name=roads&object_id=road_west_j0
    &hour=18&seed=2027&offset=0&limit=6
```

- `name`: roads, drainage (node), drainage_links (link), runoff (catchment).
- `object_id`: lấy từ edge_id/link_id/node id trong result/layer. Với runoff
  dùng catchment ID. SWMM bắt buộc chọn catchment, không nhận seed; roads
  chọn giờ/seed đã chạy, không nhận catchment.
- `case_id` chọn assumption case của run uncertainty; mỗi case trả đúng
  context hash/nguồn của nó. `option_id` có thể là baseline, option hoặc phase.
- Mỗi response chỉ một object và tối đa 300 mẫu (`limit` mặc định 60).
  `pagination` có offset/limit/count/total/next_offset. Offset bằng total
  trả trang rỗng kết thúc; lớn hơn total hoặc selector sai trả 422.
- Response có engine, source kind/IDs/manifest, context hash, units, method,
  selectors, phase/case ID. Không sửa result đã lưu và không chạy lại solver.
- Road không có report trả null với sample_status; không tự hiểu thành 0 xe.
  Queue là max lane được báo, không cộng các lane. SWMM minute/flow/depth
  khớp report; node depth không phải độ sâu ngập 2D trên map.
- Screening/legacy thiếu native series trả 409. Main result/ZIP vẫn giữ
  toàn bộ dữ liệu để tái hiện; API này giới hạn lượng dữ liệu trên mỗi
  response, chưa phải kho streaming riêng hoặc pagination khi đọc DB.

Map tiếp tục trả một thời điểm/interval; units đã bổ sung duration tràn nút.
Các row native mới dùng comparability trong bốn trạng thái đã quy định.
`comparability_reason` tách incomplete_trip_bias/invalid_solver_balance khỏi
trạng thái; các row lỗi tiếp tục chặn ranking. Run lịch sử không bị viết lại.

## Recovery

Owner khác host, identity thiếu/sai kiểu hoặc timestamp không hợp lệ là
unverifiable: giữ job, không chiếm lease hay dừng process. Descendant không
xác minh được khiến stop_orphan trả false trước khi terminate parent. Có
test process thật chứng minh parent vẫn sống; timeout/cancel/orphan hợp lệ
vẫn được kiểm tra. Recovery không thể tự xác minh host remote đã chết.

## Bằng chứng

- `test-results/planning-series-recovery.xml`: **19 passed**, 47,53 giây,
  native thật + chunk/API/unit/invalid selectors/null + job/recovery. Đây là
  lượt trước guard descendant cuối; guard cuối có lượt riêng dưới đây.
- `test-results/planning-recovery-final.xml`: **12 passed**, 17,63 giây,
  gồm malformed owner, timestamp cực lớn/descendant thiếu, orphan thật,
  timeout/cancel, retry/cache/lease. Không cộng hai số test thành suite mới.
- `test-results/planning-single-site/http-uncertainty-report.json`: hai bài
  toán native uncertainty 0.14 đạt; ba case reference/high/low, ba seed,
  hai giờ; toàn script 217,75 giây (có chạy test khác đồng thời).
  Đối chiếu bảng child của hai job: site selection 72 SUMO/12 SWMM/3 mạng;
  cumulative 108 SUMO/18 SWMM/3 mạng. Đây là số child đã hoàn tất, không lấy
  con số 36 SUMO của các lượt CLI một giờ trước đây để mô tả lượt này.
- `planning-single-site/http-series-report.json`: **8 trường hợp passed**:
  hai native và sáu case uncertainty; ghép toàn bộ chunk bằng đúng series
  lưu, source/case/seed, từ chối selector sai và result bất biến.
- `planning-single-site/ui-report.json`: **14 nhóm browser passed**, có mở
  run uncertainty hiện tại, đổi case và ba seed, cảnh báo stability; cùng
  single-site, native layers, retry, ledger, inclusive background và mobile.
- `planning-single-site/series-linux-native-report.json`: image backend
  hiện tại native/cache/normalized/source/selectors/cancel/timeout/worker
  entrypoint đạt, 4,91 giây. Không phải toàn bộ suite Linux.
- API/worker Docker 8007 đã cập nhật, giữ volume/run cũ; một request đọc node
  SWMM trên image cuối đã đối chiếu trực tiếp với mẫu lưu và đạt.

Report relative ở trên đều dưới `test-results/` ignored. Lượt full regression
gần nhất là 101 passed trước các bổ sung handoff/guard này; các gate focused
trên kiểm tra thay đổi mới, không ghi thành 101 test chạy lại trên patch cuối.

Tái hiện API series trên các run/report đã có:

```powershell
.venv/Scripts/python.exe scripts/test-planning-series-local.py --api http://127.0.0.1:8007 --evidence test-results/planning-single-site
```

Còn đối chiếu end-to-end các kịch bản/tổ hợp/thứ tự triển khai và mọi mục
nghiệm thu bằng evidence hiện tại trước khi tuyên bố toàn demo hoàn thành.
