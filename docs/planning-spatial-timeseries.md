# Layer theo thời gian của demo planning

Model `planning-studies-0.10`, ngày 11/10/2026. Dữ liệu synthetic. Thay đổi
model tạo context/cache mới; run cũ được giữ bất biến và vẫn đọc được.

## SUMO: hàng chờ theo lane và edge

Mỗi traffic run có `queue_intervals`, cùng cửa sổ 300 giây với
`edge_intervals`. Record có begin/end, số mẫu và danh sách lane/edge.
Lane ID được nối với edge bằng file network.xml của đúng child solver,
không tách ID bằng dấu gạch dưới để suy tên đường.

`sampled_peak_queue_m` là chiều dài queueing_length lớn nhất ở lane trong
cửa sổ, lấy tại các mẫu cách 30 giây. Giá trị edge là max lane, **không phải
tổng chiều dài các lane**, không phải hàng chờ cực đại liên tục giữa hai mẫu.
Cửa sổ là [begin,end), tránh tính một timestamp vào hai khoảng.

Map roads vẫn chọn option/phase, giờ, seed và interval. Thêm:

- `sampled_peak_queue_m`: số hoặc null khi không có reported lane record.
- `queue_lanes`: các lane đã báo cáo và peak trong cửa sổ.
- `queue_sample_status`: reported/no_reported_queue/legacy_unavailable.
- `queue_method`: công bố cách tổng hợp và giới hạn lấy mẫu.

Không biến thiếu record thành giá trị 0 đo được. Run cũ không có
queue_intervals công bố legacy_unavailable. Không dùng sampled peak này để
thay định nghĩa global `max_queue_length_m` của solver output đã có.

```text
GET /api/v1/planning/runs/{id}/map
    ?option_id=ABC&name=roads&hour=18&seed=2026&interval=4
```

## SWMM: nút và cống theo phút

Catchment child có `map` cho nodes và `link_map` cho conduits/orifices.
Geometry dùng chính endpoints của graph SWMM synthetic. Cống không được
coi là mạng khảo sát thật chỉ vì đã có LineString trên bản đồ.

Không có `drainage_sample`: trả summary cả event và recession (nodes:
flooding_m3/peak_depth_m; links: peak_abs_flow_m3_s/peak_depth_m).
Có sample: giữ summary và thêm các đại lượng tại mẫu, có index và minute:

| Layer | Giá trị tại mẫu |
|---|---|
| `drainage` | depth_m và flooding_m3_s |
| `drainage_links` | flow_m3_s có dấu và depth_m |

Sample 0 tương ứng phút 1; sample 20 là phút 21. Cả hai đều là output tại
report timestep 60 giây, không nội suy. Mưa và recession theo conditions của
run, không tự đồng nhất với giờ giao thông. Tổng overflow là tích phân xấp
xỉ report samples, không phải continuity-ledger volume hoặc ngập mặt đất 2D.

```text
GET /api/v1/planning/runs/{id}/map
    ?option_id=phase_3&name=drainage&drainage_sample=20
GET /api/v1/planning/runs/{id}/map
    ?option_id=ABC&name=drainage_links&drainage_sample=20
```

Sample vượt phạm vi trả 422. Screening hoặc run lịch sử không có link geometry
trả 409 cho layer cống. Tạo revision mới để có layer mới; không chạy lại solver
khi chỉ đổi selector. GeoJSON có units/source IDs/context/time window; ZIP
thêm `maps/{option}/drainage_links.geojson`, chuỗi đầy đủ nằm trong result.json
và output solver. `case_id` giữ nguyên cách chọn uncertainty case ở endpoint.

## Preview và kiểm chứng

Preview thêm seed SUMO, thời điểm SWMM và lựa chọn **Cống SWMM**. Tooltip
trả các số theo selector. Tích hợp frontend nhóm dùng API bên trên.

Instance kiểm thử 0.10: `http://127.0.0.1:8006/simulation/planning`; store/root
riêng `.runtime/planning-demo-timeseries/`. API 8005 cũ không bị dừng. Bằng
chứng của instance mới nằm trong `test-results/planning-timeseries/`.

- Regression native/provenance/studies: 21 passed, 36,20 giây,
  `test-results/planning-timeseries-regression.xml`. Có kiểm tra queue/XML
  thật, node/link samples đúng output solver, selector ngoài phạm vi và map
  không làm thay đổi result gốc. Các guard/source-object-ID cuối được kiểm
  tra bằng focused test sau regression.
- HTTP native site-selection và cumulative: passed, 59,60 giây,
  `http-native-report.json` trong thư mục evidence mới. Có worker riêng,
  immutable input/result, idempotency và ZIP. Không bao gồm uncertainty hoặc
  UI trong lượt HTTP này.
- Focused native sau guard/source-object-ID cuối: 1 passed, 12,82 giây,
  `test-results/planning-timeseries-focused.xml`.
- Browser: 12 nhóm passed trên API 8006/worker thật; có layer cống thay đổi
  theo phút, queue tooltip, chọn seed 2027, API sample và sample lỗi, mobile,
  retry, ledger, ZIP. Chưa có uncertainty run 0.10 trong lượt browser này;
  không cộng lượt đọc run uncertainty 0.8 ở instance khác vào bằng chứng mới.

Worker của instance 8006 đang chạy bằng phiên terminal có handle; API là
process hidden. Không tự mở thêm worker trên cùng store khi đang có phiên
phục vụ. Handoff CLI local có thể dùng cùng environment với đường dẫn store
và root của instance 8006 khi chuyển sang terminal của nhóm.

Còn audit invariant/corner cases và package end-to-end hiện tại trước khi
nghiệm thu toàn bộ kế hoạch; không suy độ chính xác địa phương từ test native.
